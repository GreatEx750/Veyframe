from datetime import UTC, datetime
from typing import Annotated

from demodirector_contracts import Scene, Storyboard
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from demodirector_api.google_ai import StructuredGenerationError
from demodirector_api.repositories import (
    ProductUnderstandingRepository,
    ProjectRepository,
    ResearchSourceRepository,
    StoryboardRepository,
)
from demodirector_api.storyboard_generation import (
    StoryboardGenerationService,
    StoryboardValidationError,
)


def get_projects(request: Request) -> ProjectRepository:
    return request.app.state.project_repository  # type: ignore[no-any-return]


def get_understandings(request: Request) -> ProductUnderstandingRepository:
    return request.app.state.product_understanding_repository  # type: ignore[no-any-return]


def get_sources(request: Request) -> ResearchSourceRepository:
    return request.app.state.research_source_repository  # type: ignore[no-any-return]


def get_storyboards(request: Request) -> StoryboardRepository:
    return request.app.state.storyboard_repository  # type: ignore[no-any-return]


def get_generator(request: Request) -> StoryboardGenerationService:
    return request.app.state.storyboard_generation_service  # type: ignore[no-any-return]


Projects = Annotated[ProjectRepository, Depends(get_projects)]
Understandings = Annotated[ProductUnderstandingRepository, Depends(get_understandings)]
Sources = Annotated[ResearchSourceRepository, Depends(get_sources)]
Storyboards = Annotated[StoryboardRepository, Depends(get_storyboards)]
Generator = Annotated[StoryboardGenerationService, Depends(get_generator)]

router = APIRouter(tags=["storyboards"])


class StoryboardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(gt=0)
    scenes: list[Scene]


@router.post(
    "/projects/{project_id}/storyboard",
    response_model=Storyboard,
    status_code=status.HTTP_200_OK,
)
def generate_storyboard(
    project_id: str,
    projects: Projects,
    understandings: Understandings,
    sources: Sources,
    storyboards: Storyboards,
    generator: Generator,
) -> Storyboard:
    project = projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    understanding = understandings.get(project_id)
    if understanding is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generate product understanding before the storyboard.",
        )

    projects.update(
        project.model_copy(
            update={
                "status": "storyboarding",
                "job_status": "running",
                "updated_at": datetime.now(UTC),
            }
        )
    )
    try:
        generated = generator.generate(
            project=project,
            understanding=understanding,
            sources=sources.list_for_project(project_id),
        )
        saved = storyboards.save(generated)
    except (StoryboardValidationError, StructuredGenerationError) as error:
        projects.update(
            project.model_copy(
                update={"status": "failed", "job_status": "failed", "updated_at": datetime.now(UTC)}
            )
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    projects.update(
        project.model_copy(
            update={"status": "ready", "job_status": "succeeded", "updated_at": datetime.now(UTC)}
        )
    )
    return saved


@router.get("/projects/{project_id}/storyboard", response_model=Storyboard)
def get_storyboard(project_id: str, storyboards: Storyboards) -> Storyboard:
    storyboard = storyboards.get_latest(project_id)
    if storyboard is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storyboard not found")
    return storyboard


@router.put("/projects/{project_id}/storyboard", response_model=Storyboard)
def update_storyboard(
    project_id: str,
    payload: StoryboardUpdate,
    storyboards: Storyboards,
) -> Storyboard:
    current = storyboards.get_latest(project_id)
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Storyboard not found")
    if current.version != payload.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Storyboard changed; reload before saving edits.",
        )
    normalized_scenes = [
        scene.model_copy(
            update={
                "storyboard_id": current.id,
                "order": order,
            }
        )
        for order, scene in enumerate(payload.scenes)
    ]
    updated = current.model_copy(
        update={
            "scenes": normalized_scenes,
            "total_duration_seconds": sum(
                scene.duration_seconds for scene in normalized_scenes
            ),
            "status": "draft",
        }
    )
    return storyboards.save(updated)


@router.post(
    "/projects/{project_id}/storyboard/scenes/{scene_id}/regenerate",
    response_model=Storyboard,
)
def regenerate_storyboard_scene(
    project_id: str,
    scene_id: str,
    projects: Projects,
    understandings: Understandings,
    sources: Sources,
    storyboards: Storyboards,
    generator: Generator,
) -> Storyboard:
    project = projects.get(project_id)
    understanding = understandings.get(project_id)
    current = storyboards.get_latest(project_id)
    if project is None or current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if understanding is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Understanding not found")
    try:
        regenerated = generator.regenerate_scene(
            project=project,
            understanding=understanding,
            sources=sources.list_for_project(project_id),
            storyboard=current,
            scene_id=scene_id,
        )
    except (StoryboardValidationError, StructuredGenerationError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    scenes = [regenerated if scene.id == scene_id else scene for scene in current.scenes]
    return storyboards.save(current.model_copy(update={"scenes": scenes, "status": "draft"}))
