from datetime import UTC, datetime
from typing import cast

import pytest
from demodirector_api.google_ai import FakeGoogleAIService
from demodirector_api.storyboard_generation import (
    StoryboardGenerationService,
    StoryboardValidationError,
    build_storyboard_prompt,
)
from demodirector_contracts import ProductUnderstanding, Project, ResearchSource


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
            "suggested_demo_flows": [
                {"title": "Overview", "steps": ["Open dashboard"], "feature_ids": ["dashboard"]}
            ],
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


def storyboard_payload(scene_count: int = 5, duration: float = 90) -> dict[str, object]:
    scene_duration = duration / scene_count
    return {
        "id": "storyboard-1",
        "project_id": "project-1",
        "version": 1,
        "total_duration_seconds": duration,
        "status": "draft",
        "scenes": [
            {
                "id": f"scene-{index + 1}",
                "storyboard_id": "storyboard-1",
                "order": index,
                "title": f"Scene {index + 1}",
                "objective": "Show the team dashboard",
                "narration": "See the team dashboard in action.",
                "source_ids": ["source-1"],
                "capture_plan": {
                    "start_url": "https://example.com/dashboard",
                    "actions": [
                        {
                            "type": "navigate",
                            "description": "Open the dashboard",
                            "value": "https://example.com/dashboard",
                        }
                    ],
                    "success_assertions": [
                        {
                            "type": "assert_visible",
                            "locator_strategy": "role",
                            "locator": "heading:Team dashboard",
                            "description": "Confirm dashboard heading",
                        }
                    ],
                    "timeout_seconds": 30,
                },
                "expected_evidence": ["Team dashboard heading"],
                "duration_seconds": scene_duration,
            }
            for index in range(scene_count)
        ],
    }


def test_storyboard_service_accepts_grounded_timed_scene_plan() -> None:
    fake = FakeGoogleAIService(storyboard_payload())
    service = StoryboardGenerationService(fake)

    result = service.generate(
        project=project(),
        understanding=understanding(),
        sources=[source()],
    )

    assert len(result.scenes) == 5
    assert result.total_duration_seconds == 90
    assert "CaptureAction allowlist" in fake.prompts[0]


def test_storyboard_prompt_distinguishes_fixed_presentation_from_product_capture() -> None:
    product_prompt = build_storyboard_prompt(project(), understanding(), [source()])
    presentation = project().model_copy(
        update={"demo_mode": "presentation_demo", "requested_duration_seconds": 120}
    )
    presentation_prompt = build_storyboard_prompt(
        presentation,
        understanding(),
        [source()],
    )

    assert "one continuous product walkthrough" in product_prompt
    assert "presentation-story@1" in presentation_prompt
    assert "exactly 120 seconds" in presentation_prompt
    assert "first and final five seconds" in presentation_prompt
    assert "Do not invent slide layouts" in presentation_prompt
    assert "real click actions" in presentation_prompt


def test_storyboard_service_canonicalizes_one_based_scene_order() -> None:
    payload = storyboard_payload()
    scenes = cast(list[dict[str, object]], payload["scenes"])
    for index, scene in enumerate(scenes, start=1):
        scene["order"] = index
    service = StoryboardGenerationService(FakeGoogleAIService(payload))

    result = service.generate(
        project=project(),
        understanding=understanding(),
        sources=[source()],
    )

    assert [scene.order for scene in result.scenes] == [0, 1, 2, 3, 4]


def test_storyboard_service_repairs_a_nearby_human_readable_locator() -> None:
    payload = storyboard_payload()
    first_plan = payload["scenes"][0]["capture_plan"]  # type: ignore[index]
    first_plan["actions"] = [
        {
            "type": "click",
            "locator_strategy": "text",
            "locator": "Browse hackathons",
            "description": "Open the public hackathon directory",
        }
    ]
    first_plan["success_assertions"] = [
        {
            "type": "assert_visible",
            "locator_strategy": "text",
            "locator": "Search hackathons",
            "description": "Confirm the directory control",
        }
    ]
    grounded_source = source().model_copy(
        update={"snippet": "Devpost homepage\nSearch hackathons\nFind your next hackathon"}
    )

    result = StoryboardGenerationService(FakeGoogleAIService(payload)).generate(
        project=project(), understanding=understanding(), sources=[grounded_source]
    )

    assert result.scenes[0].capture_plan.actions[0].locator == "Search hackathons"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (storyboard_payload(scene_count=4), "5-10 scenes"),
        (storyboard_payload(duration=120), "10% budget"),
    ],
)
def test_storyboard_rejects_scene_count_and_duration_budget(
    payload: dict[str, object],
    message: str,
) -> None:
    service = StoryboardGenerationService(FakeGoogleAIService(payload))

    with pytest.raises(StoryboardValidationError, match=message):
        service.generate(project=project(), understanding=understanding(), sources=[source()])


def test_storyboard_rejects_unknown_source_and_missing_interaction_assertion() -> None:
    unknown_source_payload = storyboard_payload()
    unknown_source_payload["scenes"][0]["source_ids"] = ["invented"]  # type: ignore[index]
    with pytest.raises(StoryboardValidationError, match="unknown source"):
        StoryboardGenerationService(FakeGoogleAIService(unknown_source_payload)).generate(
            project=project(), understanding=understanding(), sources=[source()]
        )

    unsafe_payload = storyboard_payload()
    first_plan = unsafe_payload["scenes"][0]["capture_plan"]  # type: ignore[index]
    first_plan["actions"] = [
        {
            "type": "click",
            "locator_strategy": "role",
            "locator": "button:Create report",
            "description": "Create a report",
        }
    ]
    first_plan["success_assertions"] = []
    with pytest.raises(StoryboardValidationError, match="success assertion"):
        StoryboardGenerationService(FakeGoogleAIService(unsafe_payload)).generate(
            project=project(), understanding=understanding(), sources=[source()]
        )


def test_storyboard_rejects_submit_intent_without_an_action_after_fill() -> None:
    payload = storyboard_payload()
    first_scene = payload["scenes"][0]  # type: ignore[index]
    first_scene["objective"] = "Type a query and submit the search"
    first_plan = first_scene["capture_plan"]
    first_plan["actions"] = [
        {
            "type": "fill",
            "locator_strategy": "placeholder",
            "locator": "Search",
            "value": "Google Gemini",
            "description": "Type the search query",
        }
    ]

    with pytest.raises(StoryboardValidationError, match="submit action after filling"):
        StoryboardGenerationService(FakeGoogleAIService(payload)).generate(
            project=project(), understanding=understanding(), sources=[source()]
        )
