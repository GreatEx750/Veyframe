from __future__ import annotations

import os
import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from demodirector_api.exports import ExportService, SQLiteExportRepository
from demodirector_api.generation import assemble_timeline, prepare_continuous_capture
from demodirector_api.google_ai import FakeGoogleAIService, GoogleAISettings
from demodirector_api.main import create_app
from demodirector_api.repositories import (
    SQLiteProductUnderstandingRepository,
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
    SQLiteStoryboardRepository,
    SQLiteTimelineRepository,
)
from demodirector_contracts import (
    CaptionStyleConfig,
    CaptureAction,
    CapturePlan,
    NarrationVoiceConfig,
    ProductFeature,
    ProductUnderstanding,
    RenderConfig,
    ResearchSource,
    Scene,
)
from demodirector_worker import (
    AutoCameraService,
    CaptionService,
    FFmpegRenderer,
    FFmpegSettings,
    FixtureTTSAdapter,
    NarrationService,
    PlaywrightCaptureWorker,
)
from fastapi.testclient import TestClient
from pydantic import HttpUrl


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args


@contextmanager
def fixture_server(directory: Path) -> Iterator[str]:
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(directory))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/index.html"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def media_binary(name: str) -> str:
    discovered = shutil.which(name)
    if discovered:
        return discovered
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        matches = sorted(root.glob(f"Gyan.FFmpeg*/*/bin/{name}.exe"))
        if matches:
            return str(matches[0])
    pytest.skip(f"{name} is required for the golden-path test")


def capture_plan(url: str, title: str) -> CapturePlan:
    action_labels = {
        "Dashboard": [],
        "Insights": ["Insights"],
        "Goals": ["Goals"],
        "Team": ["Team"],
        "Recommendation export": ["Recommendation", "Export recommendation"],
    }
    expected_text = {
        "Dashboard": "Executive dashboard",
        "Insights": "Activation increased 18% after the onboarding update.",
        "Goals": "73% complete",
        "Team": "Product, Growth, and Success are aligned.",
        "Recommendation export": "Export ready",
    }
    actions = [
        CaptureAction(
            type="click",
            locator_strategy="role",
            locator=f"button:{label}",
            description=f"Open {label}",
        )
        for label in action_labels[title]
    ]
    return CapturePlan(
        start_url=HttpUrl(url),
        actions=actions,
        success_assertions=[
            CaptureAction(
                type="assert_visible",
                locator_strategy="text",
                locator=expected_text[title],
                description=f"Confirm {title.lower()}",
            )
        ],
        timeout_seconds=10,
    )


def storyboard_payload(project_id: str, url: str) -> dict[str, object]:
    titles = ["Dashboard", "Insights", "Goals", "Team", "Recommendation export"]
    return {
        "id": "storyboard-golden",
        "project_id": project_id,
        "version": 1,
        "total_duration_seconds": 20,
        "status": "draft",
        "scenes": [
            {
                "id": f"scene-{index + 1}",
                "storyboard_id": "storyboard-golden",
                "order": index,
                "title": title,
                "objective": f"Show {title.lower()}",
                "narration": f"Explore the {title.lower()} workflow.",
                "source_ids": ["source-golden"],
                "capture_plan": capture_plan(url, title).model_dump(mode="json"),
                "expected_evidence": [expected],
                "duration_seconds": 4,
            }
            for index, (title, expected) in enumerate(
                zip(
                    titles,
                    [
                        "Executive dashboard",
                        "Activation increased 18% after the onboarding update.",
                        "73% complete",
                        "Product, Growth, and Success are aligned.",
                        "Export ready",
                    ],
                    strict=True,
                )
            )
        ],
    }


def seed_grounding(
    project_id: str,
    url: str,
    sources: SQLiteResearchSourceRepository,
    understandings: SQLiteProductUnderstandingRepository,
) -> None:
    sources.replace_website_sources(
        project_id,
        [
            ResearchSource(
                id="source-golden",
                project_id=project_id,
                title="Northstar fixture",
                url=HttpUrl(url),
                snippet="Dashboard, insights, goals, team, recommendation, and export.",
                source_type="website",
                retrieved_at=datetime.now(UTC),
            )
        ],
    )
    understandings.save(
        ProductUnderstanding(
            project_id=project_id,
            value_proposition="Turn product signals into a recommended action.",
            audience="Product leaders",
            features=[
                ProductFeature(
                    id="recommendation",
                    name="Recommendations",
                    description="Recommends and exports the next action.",
                    source_ids=["source-golden"],
                )
            ],
        )
    )


def test_golden_path_project_to_download_with_fake_ai(tmp_path: Path) -> None:
    fixture = Path(__file__).parents[2] / "worker" / "tests" / "fixtures" / "golden_saas"
    ffmpeg = media_binary("ffmpeg")
    ffprobe = media_binary("ffprobe")
    database = tmp_path / "golden.db"
    projects = SQLiteProjectRepository(database)
    sources = SQLiteResearchSourceRepository(database)
    understandings = SQLiteProductUnderstandingRepository(database)
    storyboards = SQLiteStoryboardRepository(database)
    timelines = SQLiteTimelineRepository(database)
    fake_ai = FakeGoogleAIService({})
    app = create_app(
        repository=projects,
        research_repository=sources,
        product_understanding_repository=understandings,
        storyboard_repository=storyboards,
        timeline_repository=timelines,
        ai_service=fake_ai,
        ai_settings=GoogleAISettings("fake-gemini", None, None, "us-central1"),
    )
    client = TestClient(app)

    with fixture_server(fixture) as url:
        created = client.post(
            "/projects",
            json={
                "name": "Golden path",
                "website_url": url,
                "product_summary": "Northstar turns product signals into actions.",
                "audience": "Product leaders",
                "tone": "Clear",
                "requested_duration_seconds": 20,
                "cta": "Export recommendation",
            },
        )
        assert created.status_code == 201
        project_id = created.json()["id"]
        seed_grounding(project_id, url, sources, understandings)

        fake_ai.payload = storyboard_payload(project_id, url)
        storyboard_response = client.post(f"/projects/{project_id}/storyboard")
        assert storyboard_response.status_code == 200
        storyboard = storyboard_response.json()

        capture_worker = PlaywrightCaptureWorker(tmp_path / "artifacts" / "captures")
        scenes = [Scene.model_validate(item) for item in storyboard["scenes"]]
        continuous_scene = prepare_continuous_capture(scenes, [4_000] * 5)
        capture = capture_worker.capture_scene(continuous_scene)
        assert capture.status == "succeeded", (capture.error, capture.logs)
        assert capture.raw_clip_path is not None
        assert len(capture.interaction_events) == 5

        failed_scene = scenes[0].model_copy(
            update={
                "id": "scene-failure-diagnostic",
                "capture_plan": CapturePlan(
                    start_url=HttpUrl(url),
                    actions=[
                        CaptureAction(
                            type="click",
                            locator_strategy="role",
                            locator="button:Does not exist",
                            description="Trigger deterministic failure",
                        )
                    ],
                    success_assertions=[],
                    timeout_seconds=1,
                ),
            }
        )
        failed_capture = capture_worker.capture_scene(failed_scene)
        assert failed_capture.status == "failed"
        assert Path(failed_capture.screenshot_paths[0]).is_file()

    artifact_root = tmp_path / "artifacts"
    renderer = FFmpegRenderer(
        artifact_root,
        artifact_root / "renders",
        FFmpegSettings(ffmpeg_path=ffmpeg, ffprobe_path=ffprobe, timeout_seconds=60),
    )
    raw_clip = Path(capture.raw_clip_path or "")
    raw_duration = round(float(renderer.probe(raw_clip)["format"]["duration"]) * 1_000)
    assert raw_duration >= 20_000
    duration_ms = 20_000
    scene = scenes[-1]
    narration = NarrationService(
        FixtureTTSAdapter(), artifact_root / "narration"
    ).generate(
        scenes,
        NarrationVoiceConfig(),
        capture_clip_paths=[str(raw_clip)],
    )
    assert narration.status == "succeeded"
    assert len(narration.segments) == 5
    project = projects.get(project_id)
    assert project is not None
    timeline = assemble_timeline(
        project,
        scenes,
        [4_000] * 5,
        capture,
        narration,
        CaptionStyleConfig(enabled=True),
        CaptionService(),
        AutoCameraService(),
    )
    assert len(timeline.scene_clips) == 1
    assert timeline.scene_clips[0].start_ms == 0
    assert timeline.scene_clips[0].end_ms == duration_ms
    assert len(timeline.cursor_events) == 5
    render = renderer.render(timeline, RenderConfig(output_filename="golden-preview.mp4"))
    assert render.status == "succeeded"
    assert Path(render.output_path or "").stat().st_size > 0
    assert render.width == 1280 and render.height == 720
    assert render.has_audio is True
    assert render.duration_ms == pytest.approx(20_000, abs=150)

    caption_start = duration_ms - 4_000
    caption_end = caption_start + 1_500
    continuous_scene_id = timeline.scene_clips[0].scene_id
    fake_ai.payload = {
        "supported": True,
        "summary": "Add a recommendation caption",
        "explanation": "The caption reinforces the exported result.",
        "operations": [
            {
                "operation_type": "add_caption",
                "target_id": continuous_scene_id,
                "arguments": {
                    "id": "caption-golden",
                    "scene_id": continuous_scene_id,
                    "start_ms": caption_start,
                    "end_ms": caption_end,
                    "text": "Recommendation ready to export",
                },
                "rationale": "Emphasize the final action.",
            }
        ],
    }
    edit_plan = client.post(
        f"/projects/{project_id}/edit-plan",
        json={
            "instruction": "Add a caption to the recommendation",
            "timeline": timeline.model_dump(mode="json"),
        },
    )
    assert edit_plan.status_code == 200
    applied = client.post(
        f"/projects/{project_id}/timeline/apply",
        json={
            "expected_version": 0,
            "base_timeline": timeline.model_dump(mode="json"),
            "summary": edit_plan.json()["summary"],
            "operations": edit_plan.json()["operations"],
        },
    )
    assert applied.status_code == 200
    edited_timeline = applied.json()["current"]["timeline"]
    assert any(
        clip["id"] == "caption-golden"
        and clip["text"] == "Recommendation ready to export"
        for clip in edited_timeline["caption_clips"]
    )

    brief = "Show the recommendation export flow."
    fake_ai.payload = {
        "project_id": project_id,
        "requirements": [
            {
                "id": "recommendation-export",
                "text": "Show the recommendation export flow",
                "source_excerpt": "Show the recommendation export flow",
            }
        ],
        "checks": [
            {
                "requirement_id": "recommendation-export",
                "requirement": "Show the recommendation export flow",
                "status": "covered",
                "scene_ids": [scene.id],
                "evidence": [f"capture:{scene.id}:0"],
            }
        ],
        "summary": "The recommendation export is covered.",
        "all_covered": True,
    }
    qa = client.post(
        f"/projects/{project_id}/qa/brief-coverage",
        json={
            "brief": brief,
            "storyboard": storyboard,
            "timeline": edited_timeline,
            "capture_evidence": {scene.id: ["Export ready is visible"]},
        },
    )
    assert qa.status_code == 200
    assert qa.json()["all_covered"] is True

    export_root = artifact_root / "exports"
    app.state.export_service = ExportService(
        FFmpegRenderer(
            artifact_root,
            export_root,
            FFmpegSettings(ffmpeg_path=ffmpeg, ffprobe_path=ffprobe, timeout_seconds=60),
        ),
        SQLiteExportRepository(database),
        export_root,
    )
    exported = client.post(
        f"/projects/{project_id}/exports",
        json={"timeline": edited_timeline, "quality": "720p"},
    )
    assert exported.status_code == 200
    assert exported.json()["status"] == "succeeded"
    assert exported.json()["duration_ms"] == pytest.approx(20_000, abs=150)
    download_url = exported.json()["download_url"]
    token = parse_qs(urlparse(download_url).query)["token"][0]
    downloaded = client.get(urlparse(download_url).path, params={"token": token})
    assert downloaded.status_code == 200
    assert downloaded.content[:4] != b""
    assert len(fake_ai.prompts) == 3
