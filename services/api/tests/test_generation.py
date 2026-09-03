from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from demodirector_api.generation import (
    CaptureWorker,
    DemoGenerationError,
    DemoGenerationService,
    prepare_continuous_capture,
    prepare_scene_for_capture,
)
from demodirector_api.parallel_search import ResearchRunResult
from demodirector_api.repositories import (
    SQLiteProductUnderstandingRepository,
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
    SQLiteStoryboardRepository,
    SQLiteTimelineRepository,
    SQLiteWebsiteInspectionRepository,
)
from demodirector_contracts import (
    BoundingBox,
    CaptionStyleConfig,
    CaptureAction,
    InspectedPage,
    InteractionEvent,
    NarrationJobResult,
    NarrationSegment,
    NarrationVoiceConfig,
    ProductFeature,
    ProductUnderstanding,
    Project,
    ResearchSource,
    Scene,
    SceneCaptureResult,
    Storyboard,
    Timeline,
    VideoExport,
    Viewport,
    WebsiteInspection,
)
from demodirector_worker import AutoCameraService, CaptionService


def project_fixture() -> Project:
    now = datetime.now(UTC)
    return Project.model_validate(
        {
            "id": "project-one-click",
            "name": "One-click demo",
            "website_url": "https://example.com",
            "product_summary": (
                "Show a complete product workflow and finish with a clear invitation."
            ),
            "audience": "Product leaders",
            "tone": "Professional",
            "requested_duration_seconds": 20,
            "cta": "Start a trial",
            "status": "draft",
            "job_status": "idle",
            "created_at": now,
            "updated_at": now,
        }
    )


class FakeInspector:
    def inspect(self, *, project_id: str, website_url: str) -> WebsiteInspection:
        return WebsiteInspection(
            project_id=project_id,
            pages=[
                InspectedPage.model_validate(
                    {
                        "title": "Example product",
                        "url": website_url,
                        "headings": ["Product overview"],
                        "elements": [],
                        "screenshot_path": "artifacts/inspection.png",
                        "viewport": Viewport(width=1280, height=720),
                    }
                )
            ],
            max_pages=1,
            max_depth=0,
        )


class FakeResearchService:
    def analyze(self, project: Project) -> ResearchRunResult:
        del project
        return ResearchRunResult(sources=[], warning="Partner research unavailable.")


class FakeUnderstandingService:
    def generate(
        self,
        *,
        project: Project,
        inspection: WebsiteInspection,
        sources: list[ResearchSource],
    ) -> ProductUnderstanding:
        del inspection
        source_id = sources[0].id
        return ProductUnderstanding(
            project_id=project.id,
            value_proposition="A focused product workflow.",
            audience=project.audience,
            features=[
                ProductFeature(
                    id="feature-1",
                    name="Overview",
                    description="A clear overview.",
                    source_ids=[source_id],
                )
            ],
            suggested_demo_flows=[],
            claims=[],
        )


class FakeStoryboardService:
    def generate(
        self,
        *,
        project: Project,
        understanding: ProductUnderstanding,
        sources: list[ResearchSource],
    ) -> Storyboard:
        del understanding
        source_id = sources[0].id
        scenes = [
            Scene.model_validate(
                {
                    "id": f"scene-{index + 1}",
                    "storyboard_id": "storyboard-one-click",
                    "order": index,
                    "title": f"Scene {index + 1}",
                    "objective": "Show the product.",
                    "narration": "See the product workflow in action.",
                    "source_ids": [source_id],
                    "capture_plan": {
                        "start_url": str(project.website_url),
                        "actions": [],
                        "success_assertions": [],
                        "timeout_seconds": 5,
                    },
                    "expected_evidence": ["Product overview"],
                    "duration_seconds": 4,
                }
            )
            for index in range(5)
        ]
        return Storyboard(
            id="storyboard-one-click",
            project_id=project.id,
            version=1,
            total_duration_seconds=20,
            status="draft",
            scenes=scenes,
        )


class FakeCaptureWorker:
    def __init__(self) -> None:
        self.scenes: list[Scene] = []

    def capture_scene(self, scene: Scene) -> SceneCaptureResult:
        self.scenes.append(scene)
        holds = [action for action in scene.capture_plan.actions if action.type == "wait_for"]
        assert [hold.value for hold in holds] == [4_000] * 5
        return SceneCaptureResult(
            scene_id=scene.id,
            status="succeeded",
            retryable=False,
            duration_ms=20_100,
            raw_clip_path=f"artifacts/captures/{scene.id}.webm",
            interaction_events=[
                InteractionEvent(
                    timestamp_ms=timestamp_ms,
                    event_type="click",
                    locator="button:Continue",
                    x=640,
                    y=360,
                    bounding_box=BoundingBox(x=580, y=330, width=120, height=60),
                    viewport=Viewport(width=1280, height=720),
                )
                for timestamp_ms in (1_000, 5_000, 9_000, 13_000, 17_000)
            ],
        )


class FailingCaptureWorker(FakeCaptureWorker):
    def capture_scene(self, scene: Scene) -> SceneCaptureResult:
        return SceneCaptureResult(
            scene_id=scene.id,
            status="failed",
            retryable=True,
            duration_ms=100,
            error="The planned target was not visible.",
        )


class FakeNarrationService:
    def generate(
        self,
        scenes: Sequence[Scene],
        voice: NarrationVoiceConfig,
        *,
        capture_clip_paths: Sequence[str] = (),
    ) -> NarrationJobResult:
        return NarrationJobResult(
            status="succeeded",
            retryable=False,
            voice_config=voice,
            segments=[
                NarrationSegment(
                    scene_id=scene.id,
                    order=index,
                    text=scene.narration,
                    audio_path=f"artifacts/narration/{scene.id}.wav",
                    duration_ms=6_000 if index == 0 else 2_000,
                )
                for index, scene in enumerate(scenes)
            ],
            preserved_capture_paths=list(capture_clip_paths),
        )


class FakeExportService:
    def __init__(self) -> None:
        self.timeline: Timeline | None = None

    def create(
        self,
        project_id: str,
        timeline: Timeline,
        quality: Literal["1080p", "720p"],
    ) -> VideoExport:
        assert quality == "1080p"
        self.timeline = timeline
        return VideoExport(
            id="export-one-click",
            project_id=project_id,
            status="succeeded",
            quality="1080p",
            filename="demo.mp4",
            width=1920,
            height=1080,
            duration_ms=20_000,
            size_bytes=1024,
            download_url=(
                f"/projects/{project_id}/exports/export-one-click/download"
                "?token=12345678901234567890"
            ),
            retryable=False,
            created_at=datetime.now(UTC),
        )


def build_service(tmp_path: Path, capture_worker: CaptureWorker) -> tuple[
    DemoGenerationService,
    SQLiteProjectRepository,
    SQLiteTimelineRepository,
    FakeExportService,
]:
    database = tmp_path / "generation.db"
    projects = SQLiteProjectRepository(database)
    projects.create(project_fixture())
    timelines = SQLiteTimelineRepository(database)
    exports = FakeExportService()
    service = DemoGenerationService(
        projects=projects,
        research_sources=SQLiteResearchSourceRepository(database),
        inspections=SQLiteWebsiteInspectionRepository(database),
        understandings=SQLiteProductUnderstandingRepository(database),
        storyboards=SQLiteStoryboardRepository(database),
        timelines=timelines,
        research=FakeResearchService(),
        inspector=FakeInspector(),
        understanding_generator=FakeUnderstandingService(),
        storyboard_generator=FakeStoryboardService(),
        capture_worker=capture_worker,
        narration=FakeNarrationService(),
        captions=CaptionService(),
        camera=AutoCameraService(),
        exports=exports,
        caption_style=CaptionStyleConfig(enabled=True),
    )
    return service, projects, timelines, exports


def test_one_click_generation_persists_an_exact_timeline_and_export(tmp_path: Path) -> None:
    capture = FakeCaptureWorker()
    service, projects, timelines, exports = build_service(tmp_path, capture)

    result = service.generate("project-one-click")

    assert result.project.status == "published"
    assert result.project.job_status == "succeeded"
    assert result.timeline_version == 1
    assert result.warnings == ["Partner research unavailable."]
    assert len(capture.scenes) == 1
    assert capture.scenes[0].title == "Continuous product walkthrough"
    state = timelines.current("project-one-click")
    assert state is not None
    timeline = state.current.timeline
    assert timeline.duration_ms == 20_000
    assert len(timeline.scene_clips) == 1
    assert timeline.scene_clips[0].start_ms == 0
    assert timeline.scene_clips[-1].end_ms == 20_000
    assert timeline.audio_clips[0].end_ms == 4_000
    assert Path(timeline.audio_clips[0].source_uri).is_absolute()
    assert max(clip.end_ms for clip in timeline.caption_clips) <= 20_000
    assert [event.timestamp_ms for event in timeline.cursor_events] == [
        1_000,
        5_000,
        9_000,
        13_000,
        17_000,
    ]
    assert all(
        clip.source_viewport == Viewport(width=1280, height=720)
        for clip in timeline.zoom_clips
    )
    assert exports.timeline == timeline
    assert projects.get("project-one-click") == result.project


def test_continuous_capture_preserves_beat_order_without_reloading_start_page() -> None:
    storyboard = FakeStoryboardService().generate(
        project=project_fixture(),
        understanding=ProductUnderstanding(
            project_id="project-one-click",
            value_proposition="A focused product workflow.",
            audience="Product leaders",
        ),
        sources=[
            ResearchSource.model_validate(
                {
                    "id": "source-1",
                    "project_id": "project-one-click",
                    "title": "Example",
                    "url": "https://example.com",
                    "snippet": "Product overview",
                    "source_type": "website",
                    "retrieved_at": datetime.now(UTC),
                }
            )
        ],
    )
    scenes = []
    for index, scene in enumerate(storyboard.scenes):
        actions = [
            CaptureAction(
                type="navigate",
                value="https://example.com/",
                description="Reload the product",
            ),
            CaptureAction(
                type="click",
                locator_strategy="role",
                locator=f"button:Beat {index + 1}",
                description=f"Open beat {index + 1}",
            ),
        ]
        assertions = [
            CaptureAction(
                type="assert_visible",
                locator_strategy="text",
                locator=f"Result {index + 1}",
                description=f"Confirm beat {index + 1}",
            )
        ]
        scenes.append(
            scene.model_copy(
                update={
                    "capture_plan": scene.capture_plan.model_copy(
                        update={"actions": actions, "success_assertions": assertions}
                    )
                }
            )
        )

    continuous = prepare_continuous_capture(scenes, [4_000] * 5)

    actions = continuous.capture_plan.actions
    assert all(action.type != "navigate" for action in actions)
    assert [action.locator for action in actions if action.type == "click"] == [
        "button:Beat 1",
        "button:Beat 2",
        "button:Beat 3",
        "button:Beat 4",
        "button:Beat 5",
    ]
    assert [action.type for action in actions] == [
        item
        for _ in range(5)
        for item in ("click", "assert_visible", "wait_for")
    ]
    assert continuous.capture_plan.success_assertions == []
    assert continuous.capture_plan.timeout_seconds >= 50
    assert continuous.duration_seconds == 20


def test_one_click_generation_marks_the_project_failed_when_capture_fails(
    tmp_path: Path,
) -> None:
    service, projects, timelines, _ = build_service(tmp_path, FailingCaptureWorker())

    with pytest.raises(DemoGenerationError, match="capture"):
        service.generate("project-one-click")

    failed = projects.get("project-one-click")
    assert failed is not None
    assert failed.status == "failed"
    assert failed.job_status == "failed"
    assert timelines.current("project-one-click") is None


def test_capture_preparation_uses_the_validated_start_url_for_targetless_navigation() -> None:
    scene = FakeStoryboardService().generate(
        project=project_fixture(),
        understanding=ProductUnderstanding(
            project_id="project-one-click",
            value_proposition="A focused product workflow.",
            audience="Product leaders",
        ),
        sources=[
            ResearchSource.model_validate(
                {
                    "id": "source-1",
                    "project_id": "project-one-click",
                    "title": "Example",
                    "url": "https://example.com",
                    "snippet": "Product overview",
                    "source_type": "website",
                    "retrieved_at": datetime.now(UTC),
                }
            )
        ],
    ).scenes[0]
    targetless_navigation = scene.capture_plan.model_copy(
        update={
            "actions": [
                CaptureAction(
                    type="navigate",
                    description="Open the dashboard",
                )
            ]
        }
    )
    scene = scene.model_copy(update={"capture_plan": targetless_navigation})

    prepared = prepare_scene_for_capture(scene, 4_000)

    assert prepared.capture_plan.actions[0].value == str(scene.capture_plan.start_url)
