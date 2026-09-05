from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from demodirector_api import presentation_pipeline as pipeline
from demodirector_api.activity_cards import ActivityPanel
from demodirector_api.presentation_pilot import SlideScript
from demodirector_api.repositories import (
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
    SQLiteTimelineRepository,
)
from demodirector_contracts import ResearchSource, SceneCaptureResult
from demodirector_worker.presentation_assets import load_pack
from test_generation import FakeCaptureWorker, build_service


@pytest.mark.parametrize("bad_audio", [False, True])
@pytest.mark.parametrize(
    "preview,expected_count,expected_ms", [(True, 5, 61000), (False, 9, 120000)]
)
def test_pipeline_completes_each_slide_then_publishes_measured_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    preview: bool,
    expected_count: int,
    expected_ms: int,
    bad_audio: bool,
) -> None:
    _, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
    original = projects.get("project-one-click")
    assert original
    project = original.model_copy(
        update={
            "demo_mode": "presentation_demo",
            "requested_duration_seconds": 120,
            "zoom_enabled": False,
        }
    )
    db = tmp_path / "pipeline.db"
    SQLiteProjectRepository(db).create(project)
    source = ResearchSource(
        id="page",
        project_id=project.id,
        title="Observed product",
        url=project.website_url,
        snippet="Observed public links",
        source_type="website",
        retrieved_at=project.created_at,
    )
    SQLiteResearchSourceRepository(db).replace_website_sources(project.id, [source])
    output = tmp_path / "artifacts" / "presentation"
    calls: list[tuple[str, int]] = []
    durations: dict[str, float] = {}
    synthesized: list[str] = []

    def touch(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test media")
        return path

    class Renderer:
        def __init__(self, directory: Path) -> None:
            self.pack = load_pack()

        def copy_layer(self, *args: Any) -> None:
            pass

        def capture(self, scene: Any, duration: int, template: Any, **kwargs: Any) -> Any:
            index = scene.order
            calls.append(("capture", index))
            path = touch(output / f"capture-{index}.mp4")
            return path, SceneCaptureResult(
                scene_id=scene.id,
                status="succeeded",
                duration_ms=duration,
                retryable=False,
                raw_clip_path=str(path),
            )

        def compose(
            self,
            template: Any,
            copy: Any,
            duration: int,
            voice: Any,
            narration: Any,
            product: Any,
            index: int,
            beats: Any,
            **kwargs: Any,
        ) -> Path:
            calls.append(("compose", index))
            assert beats is None
            assert kwargs["narration_duration"] == duration / 1000
            assert bool(product) == bool(template["requires_product"])
            path = touch(output / f"slide-{index + 1:02d}" / "composed.mp4")
            durations[str(path)] = duration / 1000
            return path

    class Director:
        def __init__(self, directory: Path) -> None:
            pass

        def direct(
            self, context: Any, template: Any, recipe: str, duration: int, index: int
        ) -> SlideScript:
            if index:
                assert ("compose", index - 1) in calls
            assert context["slide_count"] == expected_count
            calls.append(("direct", index))
            return SlideScript.model_validate(
                {
                    "template_id": template["id"],
                    "capture_recipe": recipe,
                    "source_ids": ["page"],
                    "narration": "Explore the product in action.",
                    "narration_beats": [
                        "Show Formation and evolution.",
                        "Show General characteristics.",
                        "Return to the overview.",
                    ]
                    if recipe == "article"
                    else ["Explore the product in action."] * 3
                    if recipe != "title"
                    else [],
                    "text": [
                        {"slot_id": s["id"], "text": "Example"}
                        for s in template["copy_slots"]
                        if s["id"] != "caption"
                    ],
                }
            )

    def render(timeline: Any, config: Any) -> Any:
        assert len(timeline.scene_clips) == expected_count
        assert timeline.duration_ms == expected_ms
        path = touch(tmp_path / "artifacts" / "exports" / config.output_filename)
        durations[str(path)] = expected_ms / 1000
        return SimpleNamespace(status="succeeded", output_path=str(path), thumbnail_path=None)

    monkeypatch.setattr(pipeline, "AuthoredSlideRenderer", Renderer)
    monkeypatch.setattr(pipeline, "PresentationPilotDirector", Director)
    def activity(context: Any) -> ActivityPanel:
        assert context["sources"][0]["id"] == "page"
        return ActivityPanel.model_validate({
            "heading": "PRODUCT ACTIVITY",
            "cards": [{"label": f"FEATURE {i}", "detail": "Inspect the product",
                       "status": "OBSERVED", "source_ids": ["page"]}
                      for i in range(4)],
        })

    monkeypatch.setattr(
        pipeline, "ActivityCardDirector", lambda *_: SimpleNamespace(generate=activity)
    )
    monkeypatch.setattr(
        pipeline, "ParallelSearchAdapter", lambda *_: SimpleNamespace(search=lambda **_: {})
    )
    monkeypatch.setattr(pipeline, "normalize_sources", lambda *_: [])
    monkeypatch.setattr(pipeline, "GeminiTTSAdapter", lambda *_: None)
    def synthesize(scenes: Any, voice: Any) -> Any:
        assert len(scenes) == 1
        synthesized.append(scenes[0].narration)
        return SimpleNamespace(
            status="succeeded",
            segments=[SimpleNamespace(audio_path=str(touch(output / "voice.wav")))],
        )

    monkeypatch.setattr(
        pipeline,
        "NarrationService",
        lambda *_: SimpleNamespace(generate=synthesize),
    )
    monkeypatch.setattr(
        pipeline, "prepare_narration",
        lambda source, destination, duration: (
            touch(destination) and {"speech_duration": duration}
        ),
    )
    monkeypatch.setattr(pipeline, "run_ffmpeg", lambda args, _: touch(Path(args[-1])))
    monkeypatch.setattr(
        pipeline,
        "media_probe",
        lambda path: {
            "format": {"duration": durations.get(str(path), 1)},
            "streams": [
                {"codec_type": "video", "width": 2560, "height": 1440},
                {"codec_type": "audio"},
            ],
        },
    )
    monkeypatch.setattr(pipeline, "speech_metrics", lambda _: {
        "max_internal_silence": 3 if bad_audio else .5,
        "peak": .8, "duration": expected_ms / 1000,
    })
    monkeypatch.setattr(pipeline, "FFmpegRenderer", lambda *_: SimpleNamespace(render=render))
    progress: list[str] = []
    if bad_audio:
        with pytest.raises(ValueError, match="excessive gap"):
            pipeline.run_presentation(
                project, tmp_path, output, db, progress.append, preview=preview
            )
        assert SQLiteTimelineRepository(db).current(project.id) is None
        assert not (output / "result.json").exists()
        return
    report = pipeline.run_presentation(
        project, tmp_path, output, db, progress.append, preview=preview
    )
    assert report["export"]["duration_ms"] == expected_ms  # type: ignore[index]
    assert len([c for c in calls if c[0] == "capture"]) == expected_count - (
        2 if not preview else 1
    )
    assert len(synthesized) == expected_count
    audio_sources = (output / "narration" / "concat.txt").read_text()
    assert "composed.mp4" not in audio_sources
    assert audio_sources.count("-ready.wav") == expected_count
    assert SQLiteTimelineRepository(db).current(project.id)
    published = SQLiteProjectRepository(db).get(project.id)
    assert published and published.status == "published"
    assert f"Finished: {expected_count} slides, {expected_ms // 1000} seconds" in progress
