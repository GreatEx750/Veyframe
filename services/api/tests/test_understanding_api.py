from datetime import UTC, datetime
from pathlib import Path

from demodirector_api.google_ai import FakeGoogleAIService, GoogleAISettings
from demodirector_api.main import create_app
from demodirector_api.product_understanding import website_sources
from demodirector_api.repositories import (
    SQLiteProductUnderstandingRepository,
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
    SQLiteWebsiteInspectionRepository,
)
from demodirector_contracts import Project, WebsiteInspection
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


def inspection() -> WebsiteInspection:
    return WebsiteInspection.model_validate(
        {
            "project_id": "project-1",
            "pages": [
                {
                    "title": "Example",
                    "url": "https://example.com",
                    "headings": ["Team dashboard"],
                    "elements": [],
                    "screenshot_path": "artifacts/example.png",
                    "viewport": {"width": 1280, "height": 720},
                }
            ],
            "max_pages": 3,
            "max_depth": 1,
        }
    )


def test_understanding_endpoint_generates_and_persists_grounded_model(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    projects = SQLiteProjectRepository(database_path)
    inspections = SQLiteWebsiteInspectionRepository(database_path)
    sources = SQLiteResearchSourceRepository(database_path)
    understandings = SQLiteProductUnderstandingRepository(database_path)
    projects.create(project())
    inspections.save(inspection())
    source_id = website_sources("project-1", inspection())[0].id
    fake_ai = FakeGoogleAIService(
        {
            "project_id": "project-1",
            "value_proposition": "Focused team workflows",
            "audience": "Product leaders",
            "features": [
                {
                    "id": "dashboard",
                    "name": "Team dashboard",
                    "description": "A team activity dashboard.",
                    "source_ids": [source_id],
                }
            ],
            "suggested_demo_flows": [
                {"title": "Overview", "steps": ["Open dashboard"], "feature_ids": ["dashboard"]}
            ],
            "claims": [],
        }
    )
    app = create_app(
        repository=projects,
        ai_service=fake_ai,
        ai_settings=GoogleAISettings(
            model_name="fake-gemini",
            api_key="test-key",
            project=None,
            location="us-central1",
        ),
        research_repository=sources,
        inspection_repository=inspections,
        product_understanding_repository=understandings,
    )
    client = TestClient(app)

    generated = client.post("/projects/project-1/understanding")
    stored = client.get("/projects/project-1/understanding")

    assert generated.status_code == 200
    assert stored.json() == generated.json()
    assert sources.list_for_project("project-1")[0].source_type == "website"


def test_understanding_requires_inspection_first(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    projects = SQLiteProjectRepository(database_path)
    projects.create(project())
    client = TestClient(create_app(repository=projects))

    response = client.post("/projects/project-1/understanding")

    assert response.status_code == 409
