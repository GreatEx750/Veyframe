from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from demodirector_contracts import Project
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

from demodirector_api.auth_routes import CurrentIdentity
from demodirector_api.job_monitor import ACTIVE, JobMonitor
from demodirector_api.repositories import ProjectRepository

NonEmptyString = Annotated[str, Field(min_length=1)]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: NonEmptyString = "Untitled demo"
    website_url: HttpUrl
    product_summary: NonEmptyString
    audience: NonEmptyString
    tone: NonEmptyString
    requested_duration_seconds: int = Field(gt=0, le=600)
    cta: NonEmptyString
    brand_kit_id: NonEmptyString | None = None
    demo_mode: Literal["product_demo", "presentation_demo", "spotlight_demo", "short_demo"] = (
        "product_demo"
    )
    output_orientation: Literal["landscape", "vertical"] = "landscape"
    zoom_enabled: bool = True

    @model_validator(mode="after")
    def presentation_demo_uses_mvp_duration(self) -> ProjectCreate:
        if self.demo_mode == "presentation_demo" and self.requested_duration_seconds != 120:
            raise ValueError("Presentation Demo must be exactly 120 seconds for the MVP")
        expected = {"spotlight_demo": 30, "short_demo": 45}.get(self.demo_mode)
        if expected and self.requested_duration_seconds != expected:
            raise ValueError(f"{self.demo_mode} requires {expected} seconds")
        if self.output_orientation == "vertical" and not expected:
            raise ValueError("Vertical output is supported by Spotlight and Short")
        return self


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: NonEmptyString | None = None
    website_url: HttpUrl | None = None
    product_summary: NonEmptyString | None = None
    audience: NonEmptyString | None = None
    tone: NonEmptyString | None = None
    requested_duration_seconds: int | None = Field(default=None, gt=0, le=600)
    cta: NonEmptyString | None = None
    brand_kit_id: NonEmptyString | None = None
    demo_mode: (
        Literal["product_demo", "presentation_demo", "spotlight_demo", "short_demo"] | None
    ) = None
    output_orientation: Literal["landscape", "vertical"] | None = None
    zoom_enabled: bool | None = None

    @model_validator(mode="after")
    def contains_an_update(self) -> ProjectUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one project field must be provided")
        return self


def get_project_repository(request: Request) -> ProjectRepository:
    return request.app.state.project_repository  # type: ignore[no-any-return]


RepositoryDependency = Annotated[ProjectRepository, Depends(get_project_repository)]

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    repository: RepositoryDependency,
    identity: CurrentIdentity,
) -> Project:
    now = datetime.now(UTC)
    project = Project(
        id=str(uuid4()),
        **payload.model_dump(),
        status="draft",
        job_status="idle",
        owner_user_id=identity.user_id,
        created_at=now,
        updated_at=now,
    )
    return repository.create(project)


@router.get("", response_model=list[Project])
def list_projects(repository: RepositoryDependency, identity: CurrentIdentity) -> list[Project]:
    return repository.list(identity.user_id)


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: str,
    repository: RepositoryDependency,
    identity: CurrentIdentity,
) -> Project:
    project = repository.get(project_id)
    if project is None or project.owner_user_id != identity.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=Project)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    repository: RepositoryDependency,
    identity: CurrentIdentity,
) -> Project:
    existing = repository.get(project_id)
    if existing is None or existing.owner_user_id != identity.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    updated_values = {
        **existing.model_dump(),
        **payload.model_dump(exclude_unset=True),
        "updated_at": datetime.now(UTC),
    }
    try:
        updated = Project.model_validate(updated_values)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=jsonable_encoder(
                [
                    {key: value for key, value in issue.items() if key != "ctx"}
                    for issue in error.errors(include_url=False)
                ]
            ),
        ) from error
    if repository.update(updated) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return updated


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    repository: RepositoryDependency,
    identity: CurrentIdentity,
    request: Request,
) -> Response:
    existing = repository.get(project_id)
    if existing is None or existing.owner_user_id != identity.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    monitor: JobMonitor = request.app.state.job_monitor
    if any(job.status in ACTIVE for _, job in monitor.saved_jobs(existing)):
        raise HTTPException(
            409, "A generation is still in progress. Open Jobs before deleting this project."
        )
    if not repository.delete(project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
