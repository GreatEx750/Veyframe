from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from demodirector_api import presentation_pipeline as pipeline
from demodirector_api.activity_cards import ActivityPanel
from demodirector_api.exports import (
    CloudExportArtifactStore,
    CloudTimelineMediaStore,
    ExportService,
    SQLiteExportRepository,
)
from demodirector_api.presentation_pilot import SlideScript, narration_word_budget
from demodirector_api.repositories import (
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
    SQLiteTimelineRepository,
)
from demodirector_contracts import ResearchSource, SceneCaptureResult
from demodirector_worker.presentation_assets import load_pack
from demodirector_worker.renderer import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, FFmpegRenderer
from test_exports import MemoryBucket
from test_generation import FakeCaptureWorker, build_service


@pytest.mark.parametrize("bad_audio", [False, True])
@pytest.mark.parametrize("cloud", [False, True])
@pytest.mark.parametrize("extended", [False, True, "mixed"])
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
    cloud: bool,
    extended: bool | str,
) -> None:
    if extended == "mixed":
        expected_ms += 3000
    elif extended:
        expected_ms += 20000
    generation, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
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
    media_root = tmp_path / ("cloud-runtime" if cloud else "artifacts")
    output = media_root / "presentation"
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
                    "narration": f"Explore{index} " * narration_word_budget(duration),
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
    monkeypatch.setattr(pipeline, "GeminiTTSAdapter", lambda *_, **__: None)
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
    def prepare(source: Path, destination: Path, duration: float, *, max_duration: float,
                min_duration: float, allow_silent_hold: bool) -> Any:
        assert allow_silent_hold
        touch(destination)
        if extended == "mixed":
            index = int(destination.stem.split("-")[1]) - 1
            fitted = max_duration if index == 1 else min_duration if index == 2 else duration
            if index == 2:
                assert min_duration == duration - 2
        else:
            fitted = max_duration if extended else duration
        return {"speech_duration": fitted, "slide_duration": fitted}

    monkeypatch.setattr(pipeline, "prepare_narration", prepare)
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
        "max_internal_silence": 3,
        "peak": 1 if bad_audio else .8, "duration": expected_ms / 1000,
    })
    def assembly_renderer(media_directory: Path, export_directory: Path) -> Any:
        validator = FFmpegRenderer(media_directory, export_directory)

        def checked_render(timeline: Any, config: Any) -> Any:
            for clip in timeline.scene_clips:
                validator._safe_media_path(clip.source_uri, VIDEO_EXTENSIONS)
            for clip in timeline.audio_clips:
                validator._safe_media_path(clip.source_uri, AUDIO_EXTENSIONS)
            return render(timeline, config)

        return SimpleNamespace(render=checked_render)

    monkeypatch.setattr(pipeline, "FFmpegRenderer", assembly_renderer)
    if cloud:
        from demodirector_api.repositories import SQLiteStoryboardRepository

        generation.storyboards = SQLiteStoryboardRepository(db)
        generation.projects = SQLiteProjectRepository(db)
        generation.research_sources = SQLiteResearchSourceRepository(db)
        generation.timelines = SQLiteTimelineRepository(db)
        bucket = MemoryBucket()
        generation.timeline_media_store = CloudTimelineMediaStore(
            bucket, media_root, tmp_path / "cache"
        )
        generation.exports = ExportService(
            SimpleNamespace(render=render), SQLiteExportRepository(db),
            tmp_path / "artifacts" / "exports",
            artifact_store=CloudExportArtifactStore(bucket, tmp_path / "export-cache"),
        )
    progress: list[str] = []
    if cloud:
        partial = pipeline.run_presentation(
            project, tmp_path, output, db, progress.append, preview=preview,
            generation=generation, slide_limit=1,
        )
        assert partial == {"completed_slides": 1}
        assert calls == [("direct", 0), ("compose", 0)]
        assert generation.timelines.current(project.id) is None
    if bad_audio:
        with pytest.raises(ValueError, match="clipping"):
            pipeline.run_presentation(
                project, tmp_path, output, db, progress.append, preview=preview,
                generation=generation if cloud else None,
            )
        assert SQLiteTimelineRepository(db).current(project.id) is None
        assert not (output / "result.json").exists()
        original_requests = len(synthesized)
        for ready in (output / "narration").glob("*-ready.wav"):
            ready.unlink()
        with pytest.raises(ValueError, match="clipping"):
            pipeline.run_presentation(
                project, tmp_path, output, db, progress.append, preview=preview,
                generation=generation if cloud else None,
            )
        assert len(synthesized) == original_requests
        assert any("reusing saved speech" in message for message in progress)
        return
    report = pipeline.run_presentation(
        project, tmp_path, output, db, progress.append, preview=preview,
        generation=generation if cloud else None,
    )
    assert report["export"]["duration_ms"] == expected_ms  # type: ignore[index]
    from demodirector_api.repositories import SQLiteStoryboardRepository

    storyboard = SQLiteStoryboardRepository(db).get_latest(project.id)
    assert storyboard and storyboard.status == "captured"
    assert len(storyboard.scenes) == expected_count
    assert storyboard.total_duration_seconds == expected_ms / 1000
    assert [s.narration for s in storyboard.scenes] == synthesized
    from demodirector_api.evidence import EvidenceService
    from demodirector_api.records import SQLiteRecordStore

    source_map = EvidenceService(
        SQLiteProjectRepository(db), SQLiteResearchSourceRepository(db),
        SQLiteStoryboardRepository(db), generation.understandings, SQLiteRecordStore(db),
    ).contribution_map(project.id)
    assert source_map.status == "approval_required"
    assert len(source_map.scenes) == expected_count
    history = SQLiteTimelineRepository(db).current(project.id)
    assert history
    timeline = history.current.timeline
    assert timeline.scene_clips[0].start_ms == 0
    for left, right in zip(timeline.scene_clips, timeline.scene_clips[1:], strict=False):
        assert left.end_ms == right.start_ms
    assert timeline.scene_clips[-1].end_ms == expected_ms
    assert timeline.audio_clips[0].end_ms == expected_ms
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
    if cloud:
        stored = SQLiteExportRepository(db).latest_successful(project.id)
        assert stored and stored.file_path and stored.file_path.startswith("gs://")
        history = generation.timelines.current(project.id)
        assert history and all(c.source_uri.startswith("gs://")
                               for c in history.current.timeline.scene_clips)
