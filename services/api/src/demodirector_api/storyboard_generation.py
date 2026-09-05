from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from demodirector_contracts import (
    CaptureAction,
    ProductUnderstanding,
    Project,
    ResearchSource,
    Scene,
    Storyboard,
)
from pydantic import Field

from demodirector_api.google_ai import StructuredAIService

MIN_SCENES = 5
MAX_SCENES = 10
DURATION_TOLERANCE = 0.10
INTERACTIVE_ACTIONS = {"click", "fill", "select", "upload"}


class GeneratedStoryboard(Storyboard):
    # Advertise the generation budget to Gemini; business validation below remains authoritative.
    scenes: list[Scene] = Field(json_schema_extra={"minItems": MIN_SCENES, "maxItems": MAX_SCENES})


class StoryboardValidationError(RuntimeError):
    """Raised when an AI-proposed storyboard is unsafe or outside the brief."""

    def __init__(self, message: str, *, code: str = "invalid_storyboard") -> None:
        super().__init__(message)
        self.code = code
        self.candidate: Storyboard | None = None


class StoryboardGenerationService:
    def __init__(self, ai_service: StructuredAIService) -> None:
        self.ai_service = ai_service

    def generate(
        self,
        *,
        project: Project,
        understanding: ProductUnderstanding,
        sources: list[ResearchSource],
    ) -> Storyboard:
        storyboard: Storyboard = self.ai_service.generate_structured(
            prompt=build_storyboard_prompt(project, understanding, sources),
            response_model=GeneratedStoryboard,
        )
        storyboard = canonicalize_scene_order(storyboard)
        storyboard = ground_capture_locators(storyboard, sources)
        try:
            validate_storyboard(storyboard, project, sources)
        except StoryboardValidationError as error:
            error.candidate = storyboard
            raise
        return storyboard

    def regenerate_scene(
        self,
        *,
        project: Project,
        understanding: ProductUnderstanding,
        sources: list[ResearchSource],
        storyboard: Storyboard,
        scene_id: str,
    ) -> Scene:
        current = next((scene for scene in storyboard.scenes if scene.id == scene_id), None)
        if current is None:
            raise StoryboardValidationError("Selected scene was not found.")
        prompt = (
            "Regenerate only the selected Scene. Preserve its id, storyboard_id, order, and "
            "duration_seconds. Return one typed Scene with grounded sources and deterministic "
            "CaptureActions. Do not modify any other scene.\n\n"
            + json.dumps(
                {
                    "project": project.model_dump(mode="json"),
                    "product_understanding": understanding.model_dump(mode="json"),
                    "sources": [source.model_dump(mode="json") for source in sources],
                    "selected_scene": current.model_dump(mode="json"),
                },
                separators=(",", ":"),
            )
        )
        regenerated = self.ai_service.generate_structured(
            prompt=prompt,
            response_model=Scene,
        )
        if (
            regenerated.id != current.id
            or regenerated.storyboard_id != current.storyboard_id
            or regenerated.order != current.order
            or regenerated.duration_seconds != current.duration_seconds
        ):
            raise StoryboardValidationError(
                "Regenerated scene must preserve identity, order, and duration."
            )
        validate_scene(regenerated, {source.id for source in sources})
        return regenerated


def build_storyboard_prompt(
    project: Project,
    understanding: ProductUnderstanding,
    sources: list[ResearchSource],
) -> str:
    context = {
        "project": project.model_dump(mode="json"),
        "product_understanding": understanding.model_dump(mode="json"),
        "sources": [source.model_dump(mode="json") for source in sources],
    }
    mode_direction = (
        "This is a Presentation Demo using the fixed presentation-story@1 pack and exactly "
        "120 seconds. Plan authentic product actions and narration for the complete recording. "
        "The deterministic renderer owns the first and final five seconds as the authored intro "
        "and outro and keeps captured product footage visible between them. Do not invent slide "
        "layouts, animation code, render expressions, or template geometry. Provide "
        "project-specific copy through the typed scene fields only. Plan six to eight focused "
        "scenes rather than grouping the whole brief into only three or four scenes. "
        if project.demo_mode == "presentation_demo"
        else "This is a Product Demo: plan one continuous product walkthrough with narration, "
        "captions, recorded pointer movement, and optional smooth camera direction. "
    )
    return (
        mode_direction
        + f"Create a timed storyboard with {MIN_SCENES}-{MAX_SCENES} scenes. Keep total duration "
        f"within {int(DURATION_TOLERANCE * 100)}% of the requested duration. Every scene must "
        "have grounded source IDs, narration, expected evidence, and a typed deterministic "
        "CapturePlan. Set scene order to the zero-based array index (0 through n-1). Interactive "
        "actions require assert_visible success assertions. Every human-readable locator must "
        "use an inspected accessible name or visible label exactly as written in a website "
        "source; never paraphrase a control label. When a scene objective says to submit after "
        "filling a field, include a click action for the submit control after the fill action. "
        "When inspected interactive controls support the story, include real click actions so "
        "captured click feedback can be shown; never fabricate interaction coordinates. "
        "Use only the CaptureAction allowlist; never output code or shell commands.\n\n"
        + json.dumps(context, separators=(",", ":"))
    )


def canonicalize_scene_order(storyboard: Storyboard) -> Storyboard:
    return storyboard.model_copy(
        update={
            "scenes": [
                scene.model_copy(update={"order": index})
                for index, scene in enumerate(storyboard.scenes)
            ]
        }
    )


def ground_capture_locators(
    storyboard: Storyboard,
    sources: list[ResearchSource],
) -> Storyboard:
    """Reconcile near-miss visible labels to inspected website text."""
    candidates_by_source = {
        source.id: _source_locator_candidates(source)
        for source in sources
        if source.source_type == "website"
    }
    all_candidates = list(
        dict.fromkeys(
            candidate
            for candidates in candidates_by_source.values()
            for candidate in candidates
        )
    )
    grounded_scenes: list[Scene] = []
    for scene in storyboard.scenes:
        scoped = list(
            dict.fromkeys(
                candidate
                for source_id in scene.source_ids
                for candidate in candidates_by_source.get(source_id, [])
            )
        )
        candidates = scoped or all_candidates
        plan = scene.capture_plan
        grounded_scenes.append(
            scene.model_copy(
                update={
                    "capture_plan": plan.model_copy(
                        update={
                            "actions": [
                                _ground_action_locator(action, candidates)
                                for action in plan.actions
                            ],
                            "success_assertions": [
                                _ground_action_locator(action, candidates)
                                for action in plan.success_assertions
                            ],
                        }
                    )
                }
            )
        )
    return storyboard.model_copy(update={"scenes": grounded_scenes})


def _source_locator_candidates(source: ResearchSource) -> list[str]:
    values = [source.title, *source.snippet.splitlines()]
    return [value.strip() for value in values if value.strip()]


def _ground_action_locator(action: CaptureAction, candidates: list[str]) -> CaptureAction:
    if (
        not action.locator
        or action.locator_strategy not in {"text", "label", "placeholder", "alt_text", "role"}
        or not candidates
    ):
        return action
    role_prefix = ""
    locator_name = action.locator
    if action.locator_strategy == "role":
        role, separator, name = action.locator.partition(":")
        if not separator or not name:
            return action
        role_prefix = f"{role}:"
        locator_name = name
    normalized_locator = _normalize_locator(locator_name)
    if any(normalized_locator in _normalize_locator(candidate) for candidate in candidates):
        return action
    locator_tokens = set(normalized_locator.split())
    ranked = [
        (
            SequenceMatcher(None, normalized_locator, _normalize_locator(candidate)).ratio(),
            candidate,
        )
        for candidate in candidates
        if locator_tokens & set(_normalize_locator(candidate).split())
    ]
    if not ranked:
        return action
    score, replacement = max(ranked, key=lambda item: item[0])
    if score < 0.55:
        return action
    return action.model_copy(update={"locator": f"{role_prefix}{replacement}"})


def _normalize_locator(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def validate_storyboard(
    storyboard: Storyboard,
    project: Project,
    sources: list[ResearchSource],
) -> None:
    if storyboard.project_id != project.id:
        raise StoryboardValidationError("Storyboard project ID does not match the request.")
    if not MIN_SCENES <= len(storyboard.scenes) <= MAX_SCENES:
        raise StoryboardValidationError(
            f"Generated storyboard must contain {MIN_SCENES}-{MAX_SCENES} scenes.",
            code="scene_count",
        )
    orders = [scene.order for scene in storyboard.scenes]
    if orders != list(range(len(storyboard.scenes))):
        raise StoryboardValidationError("Storyboard scene order must be contiguous from zero.")

    scene_total = sum(scene.duration_seconds for scene in storyboard.scenes)
    if abs(scene_total - storyboard.total_duration_seconds) > 0.5:
        raise StoryboardValidationError("Storyboard total must equal the sum of scene durations.")
    requested = project.requested_duration_seconds
    if abs(scene_total - requested) > requested * DURATION_TOLERANCE:
        raise StoryboardValidationError("Storyboard duration is outside the requested 10% budget.")

    allowed_sources = {source.id for source in sources}
    for scene in storyboard.scenes:
        validate_scene(scene, allowed_sources)


def validate_scene(scene: Scene, allowed_sources: set[str]) -> None:
    if not scene.source_ids:
        raise StoryboardValidationError(
            f"Scene {scene.id} requires grounded source IDs.", code="missing_sources"
        )
    if set(scene.source_ids) - allowed_sources:
        raise StoryboardValidationError(
            f"Scene {scene.id} references an unknown source ID.", code="unknown_source"
        )
    is_interactive = any(
        action.type in INTERACTIVE_ACTIONS for action in scene.capture_plan.actions
    )
    if is_interactive and not scene.capture_plan.success_assertions:
        raise StoryboardValidationError(
            f"Interactive scene {scene.id} requires a success assertion.", code="missing_assertion"
        )
    objective = re.sub(
        r"\b(?:do not|don't|never|without|avoid|not)\s+submit(?:ting)?\b",
        "", scene.objective.casefold(),
    )
    if re.search(r"\bsubmit(?:ting)?\b", objective):
        actions = scene.capture_plan.actions
        last_fill = max(
            (index for index, action in enumerate(actions) if action.type == "fill"),
            default=-1,
        )
        if last_fill >= 0 and not any(
            action.type == "click" for action in actions[last_fill + 1 :]
        ):
            raise StoryboardValidationError(
                f"Scene {scene.id} requires a submit action after filling the field.",
                code="missing_submit",
            )
