from __future__ import annotations

from demodirector_contracts import CaptionStyleConfig, NarrationSegment
from demodirector_worker.captions import CaptionService


def narration(duration_ms: int = 2_400) -> NarrationSegment:
    return NarrationSegment(
        scene_id="scene-1",
        order=0,
        text="Create a polished product demo and share it with your team.",
        audio_path="narration/scene-1.wav",
        duration_ms=duration_ms,
    )


def test_captions_cover_known_narration_and_fit_audio_duration() -> None:
    track = CaptionService(max_words_per_caption=4).generate_track(
        narration(),
        CaptionStyleConfig(font_size=36, position="bottom"),
    )

    assert " ".join(clip.text for clip in track.clips) == narration().text
    assert track.clips[0].start_ms == 0
    assert track.clips[-1].end_ms == narration().duration_ms
    assert all(clip.end_ms <= track.duration_ms for clip in track.clips)
    assert track.model_validate_json(track.model_dump_json()) == track


def test_captions_can_be_disabled() -> None:
    track = CaptionService().generate_track(
        narration(),
        CaptionStyleConfig(enabled=False),
    )

    assert track.style.enabled is False
    assert track.clips == []


def test_short_audio_still_produces_valid_non_negative_timing() -> None:
    track = CaptionService(max_words_per_caption=1).generate_track(
        narration(1),
        CaptionStyleConfig(),
    )

    assert len(track.clips) == 1
    assert track.clips[0].start_ms == 0
    assert track.clips[0].end_ms == 1
