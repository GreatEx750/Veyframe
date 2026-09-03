from datetime import UTC, datetime

import pytest
from demodirector_api.google_ai import FakeGoogleAIService, StructuredGenerationError
from demodirector_api.product_understanding import (
    GroundingError,
    ProductUnderstandingService,
    validate_grounding,
    website_sources,
)
from demodirector_contracts import ProductUnderstanding, Project, ResearchSource, WebsiteInspection


def project() -> Project:
    now = datetime.now(UTC)
    return Project.model_validate(
        {
            "id": "project-1",
            "name": "Launch demo",
            "website_url": "https://example.com",
            "product_summary": "A focused workflow product with team dashboards.",
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
                    "title": "Example Dashboard",
                    "url": "https://example.com/dashboard",
                    "headings": ["Team dashboard"],
                    "elements": [
                        {
                            "kind": "button",
                            "tag": "button",
                            "accessible_name": "Create report",
                        }
                    ],
                    "screenshot_path": "artifacts/dashboard.png",
                    "viewport": {"width": 1280, "height": 720},
                }
            ],
            "max_pages": 3,
            "max_depth": 1,
        }
    )


def understanding_payload(source_id: str) -> dict[str, object]:
    return {
        "project_id": "project-1",
        "value_proposition": "Focused team workflows",
        "audience": "Product leaders",
        "features": [
            {
                "id": "team-dashboard",
                "name": "Team dashboard",
                "description": "A dashboard for team activity.",
                "source_ids": [source_id],
                "user_provided": False,
            }
        ],
        "suggested_demo_flows": [
            {
                "title": "Dashboard overview",
                "steps": ["Open the dashboard", "Create a report"],
                "feature_ids": ["team-dashboard"],
            }
        ],
        "claims": [
            {
                "text": "Built for focused teams",
                "source_ids": [],
                "user_provided": True,
            }
        ],
    }


def test_website_inspection_becomes_stable_grounding_source() -> None:
    timestamp = datetime.now(UTC)

    first = website_sources("project-1", inspection(), timestamp)
    second = website_sources("project-1", inspection(), timestamp)

    assert first == second
    assert first[0].source_type == "website"
    assert "Create report" in first[0].snippet


def test_service_combines_context_and_accepts_grounded_output() -> None:
    source_id = website_sources("project-1", inspection())[0].id
    fake = FakeGoogleAIService(understanding_payload(source_id))
    service = ProductUnderstandingService(fake)

    result = service.generate(project=project(), inspection=inspection(), sources=[])

    assert result.features[0].source_ids == [source_id]
    assert result.claims[0].user_provided
    assert project().product_summary in fake.prompts[0]


def test_fixture_rejects_invented_feature_without_support() -> None:
    payload = understanding_payload("unused")
    payload["features"] = [
        {
            "id": "invented",
            "name": "Invented feature",
            "description": "Unsupported",
            "source_ids": [],
            "user_provided": False,
        }
    ]
    service = ProductUnderstandingService(FakeGoogleAIService(payload))

    with pytest.raises(StructuredGenerationError, match="external product features"):
        service.generate(project=project(), inspection=inspection(), sources=[])


def test_grounding_rejects_unknown_source_identifier() -> None:
    understanding = ProductUnderstanding.model_validate(understanding_payload("unknown-source"))
    source = ResearchSource.model_validate(
        {
            "id": "known-source",
            "project_id": "project-1",
            "title": "Known source",
            "url": "https://example.com",
            "snippet": "Known",
            "source_type": "website",
            "retrieved_at": datetime.now(UTC),
        }
    )

    with pytest.raises(GroundingError, match="unsupported source IDs"):
        validate_grounding(understanding, "project-1", [source])
