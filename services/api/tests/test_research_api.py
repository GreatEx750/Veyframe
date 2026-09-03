from pathlib import Path
from typing import cast

from demodirector_api.google_ai import FakeGoogleAIService, GoogleAISettings
from demodirector_api.main import create_app
from demodirector_api.parallel_search import (
    FakeParallelSearchAdapter,
    ParallelResultItem,
    ParallelSearchError,
    ParallelSearchSettings,
    ProjectResearchService,
)
from demodirector_api.repositories import (
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
)
from fastapi.testclient import TestClient
from google.adk.agents import Agent


def project_payload() -> dict[str, object]:
    return {
        "name": "Launch demo",
        "website_url": "https://example.com/product",
        "product_summary": "A product for focused teams",
        "audience": "Product leaders",
        "tone": "Professional",
        "requested_duration_seconds": 90,
        "cta": "Start a trial",
        "brand_kit_id": "default-brand",
    }


def client_with_search(
    database_path: Path,
    search: FakeParallelSearchAdapter,
) -> tuple[TestClient, SQLiteResearchSourceRepository]:
    projects = SQLiteProjectRepository(database_path)
    research_sources = SQLiteResearchSourceRepository(database_path)
    research = ProjectResearchService(search, research_sources)
    app = create_app(
        repository=projects,
        ai_service=FakeGoogleAIService({"unused": True}),
        ai_settings=GoogleAISettings(
            model_name="fake-gemini",
            api_key="test-key",
            project=None,
            location="us-central1",
        ),
        research_repository=research_sources,
        project_research_service=research,
        parallel_settings=ParallelSearchSettings(api_key="test-key", mode="fast"),
    )
    return TestClient(app), research_sources


def test_project_research_endpoint_invokes_parallel_and_persists_sources(
    tmp_path: Path,
) -> None:
    search = FakeParallelSearchAdapter(
        [
            ParallelResultItem(
                url="https://example.com/docs",
                title="Official docs",
                excerpts=("The official product workflow.",),
            )
        ]
    )
    client, repository = client_with_search(tmp_path / "projects.db", search)
    project = client.post("/projects", json=project_payload()).json()

    response = client.post(f"/projects/{project['id']}/research")

    assert response.status_code == 200
    assert response.json()["warning"] is None
    assert response.json()["sources"][0]["source_type"] == "partner_search"
    assert len(search.calls) == 1
    assert search.calls[0]["domain"] == "example.com"
    assert len(repository.list_for_project(project["id"])) == 1

    saved_response = client.get(f"/projects/{project['id']}/research")

    assert saved_response.status_code == 200
    assert saved_response.json()["sources"][0]["title"] == "Official docs"
    assert len(search.calls) == 1


def test_parallel_failure_degrades_to_visible_website_only_warning(tmp_path: Path) -> None:
    search = FakeParallelSearchAdapter(
        error=ParallelSearchError(
            "Partner search unavailable; continuing with website-only context."
        )
    )
    client, repository = client_with_search(tmp_path / "projects.db", search)
    project = client.post("/projects", json=project_payload()).json()

    response = client.post(f"/projects/{project['id']}/research")

    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert "website-only" in response.json()["warning"]
    assert repository.list_for_project(project["id"]) == []


def test_research_health_and_missing_project_behavior(tmp_path: Path) -> None:
    client, _ = client_with_search(
        tmp_path / "projects.db",
        FakeParallelSearchAdapter(),
    )

    assert client.get("/research/health").json() == {
        "status": "ready",
        "provider": "parallel",
        "mode": "fast",
    }
    assert client.post("/projects/missing/research").status_code == 404
    assert client.get("/projects/missing/research").status_code == 404
    workflow_agent = cast(Agent, client.app.state.director_workflow.root_agent)  # type: ignore[attr-defined]
    assert len(workflow_agent.tools) == 1
