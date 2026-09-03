from __future__ import annotations

import json

from demodirector_contracts import ProductUnderstanding, Project, ResearchSource, Scene, Storyboard

from demodirector_api.google_ai import StructuredAIService

MIN_SCENES = 5
MAX_SCENES = 10
DURATION_TOLERANCE = 0.10
INTERACTIVE_ACTIONS = {"click", "fill", "select", "upload"}


class StoryboardValidationError(RuntimeError):
    """Raised when an AI-proposed storyboard is unsafe or outside the brief."""


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
        storyboard = self.ai_service.generate_structured(
            prompt=build_storyboard_prompt(project, understanding, sources),
            response_model=Storyboard,
        )
        validate_storyboard(storyboard, project, sources)
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
    return (
        f"Create a timed storyboard with {MIN_SCENES}-{MAX_SCENES} scenes. Keep total duration "
        f"within {int(DURATION_TOLERANCE * 100)}% of the requested duration. Every scene must "
        "have grounded source IDs, narration, expected evidence, and a typed deterministic "
        "CapturePlan. Interactive actions require assert_visible success assertions. Use only "
        "the CaptureAction allowlist; never output code or shell commands.\n\n"
        + json.dumps(context, separators=(",", ":"))
    )


def validate_storyboard(
    storyboard: Storyboard,
    project: Project,
    sources: list[ResearchSource],
) -> None:
    if storyboard.project_id != project.id:
        raise StoryboardValidationError("Storyboard project ID does not match the request.")
    if not MIN_SCENES <= len(storyboard.scenes) <= MAX_SCENES:
        raise StoryboardValidationError(
            f"Generated storyboard must contain {MIN_SCENES}-{MAX_SCENES} scenes."
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
        raise StoryboardValidationError(f"Scene {scene.id} requires grounded source IDs.")
    if set(scene.source_ids) - allowed_sources:
        raise StoryboardValidationError(f"Scene {scene.id} references an unknown source ID.")
    is_interactive = any(
        action.type in INTERACTIVE_ACTIONS for action in scene.capture_plan.actions
    )
    if is_interactive and not scene.capture_plan.success_assertions:
        raise StoryboardValidationError(
            f"Interactive scene {scene.id} requires a success assertion."
        )
