from pathlib import Path

from demodirector_api.google_ai import FakeGoogleAIService, GoogleAISettings
from demodirector_api.main import create_app
from demodirector_api.parallel_search import FakeParallelSearchAdapter, ProjectResearchService
from demodirector_api.repositories import (
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
    SQLiteWebsiteInspectionRepository,
)
from demodirector_contracts import WebsiteInspection
from fastapi.testclient import TestClient


class FakeWebsiteInspector:
    def __init__(self, inspection: WebsiteInspection) -> None:
        self.inspection = inspection
        self.calls: list[tuple[str, str]] = []

    def inspect(
        self,
        *,
        project_id: str,
        website_url: str,
        session_token: str | None = None,
    ) -> WebsiteInspection:
        del session_token
        self.calls.append((project_id, website_url))
        return self.inspection.model_copy(update={"project_id": project_id})


def inspection() -> WebsiteInspection:
    return WebsiteInspection.model_validate(
        {
            "project_id": "placeholder",
            "pages": [
                {
                    "title": "Fixture Product",
                    "url": "https://example.com",
                    "headings": ["Build calmer workflows"],
                    "elements": [],
                    "screenshot_path": "artifacts/page-1.png",
                    "viewport": {"width": 1280, "height": 720},
                }
            ],
            "max_pages": 3,
            "max_depth": 1,
        }
    )


def project_payload() -> dict[str, object]:
    return {
        "name": "Inspection demo",
        "website_url": "https://example.com",
        "product_summary": "A product for focused teams",
        "audience": "Product leaders",
        "tone": "Professional",
        "requested_duration_seconds": 90,
        "cta": "Start a trial",
    }


def test_inspection_endpoint_runs_worker_and_persists_latest_result(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    projects = SQLiteProjectRepository(database_path)
    research_sources = SQLiteResearchSourceRepository(database_path)
    inspections = SQLiteWebsiteInspectionRepository(database_path)
    fake_inspector = FakeWebsiteInspector(inspection())
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
        project_research_service=ProjectResearchService(
            FakeParallelSearchAdapter(),
            research_sources,
        ),
        inspection_repository=inspections,
        website_inspector=fake_inspector,
    )
    client = TestClient(app)
    project = client.post("/projects", json=project_payload()).json()

    response = client.post(f"/projects/{project['id']}/inspect")
    stored = client.get(f"/projects/{project['id']}/inspection")

    assert response.status_code == 200
    assert stored.status_code == 200
    assert stored.json() == response.json()
    assert fake_inspector.calls == [(project["id"], "https://example.com/")]


def test_missing_project_and_inspection_return_not_found(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    inspections = SQLiteWebsiteInspectionRepository(database_path)
    app = create_app(
        repository=SQLiteProjectRepository(database_path),
        inspection_repository=inspections,
        website_inspector=FakeWebsiteInspector(inspection()),
    )
    client = TestClient(app)

    assert client.post("/projects/missing/inspect").status_code == 404
    assert client.get("/projects/missing/inspection").status_code == 404
