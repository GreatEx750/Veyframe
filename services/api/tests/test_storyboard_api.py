from datetime import UTC, datetime
from pathlib import Path

from demodirector_api.google_ai import FakeGoogleAIService, GoogleAISettings
from demodirector_api.main import create_app
from demodirector_api.repositories import (
    SQLiteProductUnderstandingRepository,
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
    SQLiteStoryboardRepository,
)
from demodirector_contracts import ProductUnderstanding, Project, ResearchSource
from fastapi.testclient import TestClient


def project() -> Project:
    now = datetime.now(UTC)
    return Project.model_validate(
        {
            "id": "project-1",
            "name": "Launch demo",
            "website_url": "https://example.com",
            "product_summary": "A focused workflow product.",
            "audience": "Product leaders",
            "tone": "Professional",
            "requested_duration_seconds": 90,
            "cta": "Book a demo",
            "created_at": now,
            "updated_at": now,
        }
    )


def understanding() -> ProductUnderstanding:
    return ProductUnderstanding.model_validate(
        {
            "project_id": "project-1",
            "value_proposition": "Focused workflows",
            "audience": "Product leaders",
            "features": [
                {
                    "id": "dashboard",
                    "name": "Dashboard",
                    "description": "Team dashboard",
                    "source_ids": ["source-1"],
                }
            ],
            "suggested_demo_flows": [],
            "claims": [],
        }
    )


def source() -> ResearchSource:
    return ResearchSource.model_validate(
        {
            "id": "source-1",
            "project_id": "project-1",
            "title": "Official dashboard",
            "url": "https://example.com/dashboard",
            "snippet": "Team dashboard",
            "source_type": "website",
            "retrieved_at": datetime.now(UTC),
        }
    )


def storyboard_payload(scene_count: int = 5) -> dict[str, object]:
    return {
        "id": "storyboard-1",
        "project_id": "project-1",
        "version": 1,
        "total_duration_seconds": 90,
        "status": "draft",
        "scenes": [
            {
                "id": f"scene-{index + 1}",
                "storyboard_id": "storyboard-1",
                "order": index,
                "title": f"Scene {index + 1}",
                "objective": "Show the dashboard",
                "narration": "See the dashboard in action.",
                "source_ids": ["source-1"],
                "capture_plan": {
                    "start_url": "https://example.com/dashboard",
                    "actions": [
                        {
                            "type": "navigate",
                            "description": "Open dashboard",
                            "value": "https://example.com/dashboard",
                        }
                    ],
                    "success_assertions": [
                        {
                            "type": "assert_visible",
                            "locator_strategy": "text",
                            "locator": "Team dashboard",
                            "description": "Confirm dashboard",
                        }
                    ],
                    "timeout_seconds": 30,
                },
                "expected_evidence": ["Dashboard"],
                "duration_seconds": 90 / scene_count,
            }
            for index in range(scene_count)
        ],
    }


def configured_client(
    database_path: Path,
    payload: dict[str, object],
) -> tuple[TestClient, SQLiteProjectRepository, FakeGoogleAIService]:
    projects = SQLiteProjectRepository(database_path)
    sources = SQLiteResearchSourceRepository(database_path)
    understandings = SQLiteProductUnderstandingRepository(database_path)
    storyboards = SQLiteStoryboardRepository(database_path)
    projects.create(project())
    sources.replace_website_sources("project-1", [source()])
    understandings.save(understanding())
    fake_ai = FakeGoogleAIService(payload)
    app = create_app(
        repository=projects,
        research_repository=sources,
        product_understanding_repository=understandings,
        storyboard_repository=storyboards,
        ai_service=fake_ai,
        ai_settings=GoogleAISettings(
            model_name="fake-gemini",
            api_key="test-key",
            project=None,
            location="us-central1",
        ),
    )
    return TestClient(app), projects, fake_ai


def test_storyboard_endpoint_persists_versions_and_project_state(tmp_path: Path) -> None:
    client, projects, _ = configured_client(tmp_path / "projects.db", storyboard_payload())

    first = client.post("/projects/project-1/storyboard")
    second = client.post("/projects/project-1/storyboard")
    stored = client.get("/projects/project-1/storyboard")

    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2
    assert stored.json() == second.json()
    saved_project = projects.get("project-1")
    assert saved_project is not None
    assert saved_project.status == "ready"
    assert saved_project.job_status == "succeeded"


def test_invalid_storyboard_marks_project_failed(tmp_path: Path) -> None:
    client, projects, _ = configured_client(
        tmp_path / "projects.db",
        storyboard_payload(scene_count=4),
    )

    response = client.post("/projects/project-1/storyboard")

    assert response.status_code == 422
    failed = projects.get("project-1")
    assert failed is not None
    assert failed.status == "failed"
    assert failed.job_status == "failed"


def test_storyboard_edits_and_single_scene_regeneration_create_versions(
    tmp_path: Path,
) -> None:
    client, _, fake_ai = configured_client(tmp_path / "projects.db", storyboard_payload())
    original = client.post("/projects/project-1/storyboard").json()
    reversed_scenes = list(reversed(original["scenes"]))

    edited = client.put(
        "/projects/project-1/storyboard",
        json={"expected_version": 1, "scenes": reversed_scenes},
    )

    assert edited.status_code == 200
    assert edited.json()["version"] == 2
    assert [scene["order"] for scene in edited.json()["scenes"]] == list(range(5))

    selected = {**edited.json()["scenes"][1], "narration": "Only this narration changed."}
    fake_ai.payload = selected
    regenerated = client.post(
        f"/projects/project-1/storyboard/scenes/{selected['id']}/regenerate"
    )

    assert regenerated.status_code == 200
    assert regenerated.json()["version"] == 3
    assert regenerated.json()["scenes"][0] == edited.json()["scenes"][0]
    assert regenerated.json()["scenes"][1]["narration"] == "Only this narration changed."
