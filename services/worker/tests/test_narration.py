from __future__ import annotations

import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from demodirector_contracts import NarrationVoiceConfig, Scene
from demodirector_worker.narration import FixtureTTSAdapter, NarrationService
from google import genai
from google.genai.errors import ClientError


@pytest.mark.parametrize("status", [429, 400, 403, 500])
def test_tts_fallback_only_on_rate_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                       status: int) -> None:
    from demodirector_worker import narration as module
    calls: list[str] = []
    events: list[str] = []

    def generate(**kwargs: Any) -> Any:
        calls.append(kwargs["model"])
        if kwargs["model"] == module.DEFAULT_TTS_MODEL:
            raise ClientError(status, {"error": {"message": "private"}})
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(
            parts=[SimpleNamespace(inline_data=SimpleNamespace(data=b"\x01\x00" * 2400))]))])

    monkeypatch.setattr(genai, "Client", lambda **_: SimpleNamespace(
        models=SimpleNamespace(generate_content=generate)))
    adapter = module.GeminiTTSAdapter(module.GeminiTTSSettings(
        module.DEFAULT_TTS_MODEL, "test"), on_progress=events.append)
    if status != 429:
        with pytest.raises(ClientError):
            adapter.synthesize("Hello", NarrationVoiceConfig())
        assert calls == [module.DEFAULT_TTS_MODEL]
    else:
        assert adapter.synthesize("Hello", NarrationVoiceConfig())
        assert adapter.synthesize("Again", NarrationVoiceConfig())
        assert calls == [module.DEFAULT_TTS_MODEL, module.FALLBACK_TTS_MODEL,
                         module.FALLBACK_TTS_MODEL]
        assert adapter.model_name == module.FALLBACK_TTS_MODEL
        assert any("fallback" in event for event in events)
        assert all("private" not in event for event in events)


def test_both_tts_models_limited_stop_after_two_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    from demodirector_worker import narration as module
    calls: list[str] = []

    def generate(**kwargs: Any) -> Any:
        calls.append(kwargs["model"])
        raise ClientError(429, {"error": {"message": "limited"}})

    monkeypatch.setattr(genai, "Client", lambda **_: SimpleNamespace(
        models=SimpleNamespace(generate_content=generate)))
    adapter = module.GeminiTTSAdapter(module.GeminiTTSSettings(module.DEFAULT_TTS_MODEL, "test"))
    with pytest.raises(ClientError):
        adapter.synthesize("Hello", NarrationVoiceConfig())
    assert calls == [module.DEFAULT_TTS_MODEL, module.FALLBACK_TTS_MODEL]


def make_scene(scene_id: str, order: int, narration: str) -> Scene:
    return Scene.model_validate(
        {
            "id": scene_id,
            "storyboard_id": "storyboard-1",
            "order": order,
            "title": f"Scene {order + 1}",
            "objective": "Explain the product flow",
            "narration": narration,
            "source_ids": ["source-1"],
            "capture_plan": {
                "start_url": "https://example.com",
                "actions": [],
                "success_assertions": [],
                "timeout_seconds": 10,
            },
            "expected_evidence": [],
            "duration_seconds": 3,
        }
    )


def test_fixture_narration_writes_ordered_scene_audio(tmp_path: Path) -> None:
    service = NarrationService(FixtureTTSAdapter(), tmp_path / "narration")
    voice = NarrationVoiceConfig(voice_name="Kore", language_code="en-US", pace="normal")

    result = service.generate(
        [
            make_scene("scene-2", 1, "Then save the demo."),
            make_scene("scene-1", 0, "Start the workflow."),
        ],
        voice,
        capture_clip_paths=["capture/scene-1.webm", "capture/scene-2.webm"],
    )

    assert result.status == "succeeded"
    assert [segment.scene_id for segment in result.segments] == ["scene-1", "scene-2"]
    assert result.voice_config == voice
    assert result.preserved_capture_paths == ["capture/scene-1.webm", "capture/scene-2.webm"]
    for segment in result.segments:
        with wave.open(segment.audio_path, "rb") as audio:
            assert audio.getframerate() == 24_000
            assert audio.getnchannels() == 1
            assert audio.getnframes() > 0


class BrokenTTSAdapter:
    def synthesize(self, text: str, voice: NarrationVoiceConfig) -> bytes:
        del text, voice
        raise RuntimeError("temporary provider outage")


def test_failure_is_retryable_and_preserves_capture_paths(tmp_path: Path) -> None:
    service = NarrationService(BrokenTTSAdapter(), tmp_path / "narration")

    result = service.generate(
        [make_scene("scene-1", 0, "Start the workflow.")],
        NarrationVoiceConfig(),
        capture_clip_paths=["capture/scene-1.webm"],
    )

    assert result.status == "failed"
    assert result.retryable is True
    assert result.preserved_capture_paths == ["capture/scene-1.webm"]
    assert result.segments == []
    assert result.error is not None and "temporary provider outage" in result.error


def test_narration_metadata_round_trips_through_shared_contract(tmp_path: Path) -> None:
    result = NarrationService(FixtureTTSAdapter(), tmp_path).generate(
        [make_scene("scene-1", 0, "Start the workflow.")],
        NarrationVoiceConfig(language_code="en-GB", pace="slow"),
    )

    assert result.model_validate_json(result.model_dump_json()) == result


def test_speech_quota_failure_is_safe_and_does_not_retry(tmp_path: Path) -> None:
    class QuotaTTSAdapter:
        calls = 0

        def synthesize(self, text: str, voice: NarrationVoiceConfig) -> bytes:
            self.calls += 1
            raise ClientError(429, {"error": {"message": "private api_key=abc"}})

    adapter = QuotaTTSAdapter()
    result = NarrationService(adapter, tmp_path).generate(
        [make_scene("scene-1", 0, "Start here.")], NarrationVoiceConfig(),
        capture_clip_paths=["saved.webm"],
    )
    assert result.status == "failed"
    assert result.error is not None and "Google speech rate or quota limit" in result.error
    assert "private" not in result.error and "abc" not in result.error
    assert result.preserved_capture_paths == ["saved.webm"]
    assert adapter.calls == 1
