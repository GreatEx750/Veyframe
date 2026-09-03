from typing import Annotated, Literal

from demodirector_contracts import ResearchSource
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from demodirector_api.parallel_search import ProjectResearchService
from demodirector_api.repositories import ProjectRepository


class ProjectResearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    sources: list[ResearchSource]
    warning: str | None = None


class PartnerSearchHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "unavailable"]
    provider: Literal["parallel"]
    mode: str


def get_project_repository(request: Request) -> ProjectRepository:
    return request.app.state.project_repository  # type: ignore[no-any-return]


def get_research_service(request: Request) -> ProjectResearchService:
    return request.app.state.project_research_service  # type: ignore[no-any-return]


ProjectRepositoryDependency = Annotated[ProjectRepository, Depends(get_project_repository)]
ResearchServiceDependency = Annotated[ProjectResearchService, Depends(get_research_service)]

router = APIRouter(tags=["research"])


@router.get("/research/health", response_model=PartnerSearchHealth)
def research_health(request: Request) -> PartnerSearchHealth:
    search = request.app.state.project_research_service.search
    return PartnerSearchHealth(
        status="ready" if search.configured else "unavailable",
        provider="parallel",
        mode=request.app.state.parallel_search_mode,
    )


@router.post(
    "/projects/{project_id}/research",
    response_model=ProjectResearchResponse,
    status_code=status.HTTP_200_OK,
)
def research_project(
    project_id: str,
    projects: ProjectRepositoryDependency,
    research: ResearchServiceDependency,
) -> ProjectResearchResponse:
    project = projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    result = research.analyze(project)
    return ProjectResearchResponse(
        project_id=project_id,
        sources=result.sources,
        warning=result.warning,
    )


@router.get(
    "/projects/{project_id}/research",
    response_model=ProjectResearchResponse,
)
def get_saved_project_research(
    project_id: str,
    projects: ProjectRepositoryDependency,
    research: ResearchServiceDependency,
) -> ProjectResearchResponse:
    if projects.get(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectResearchResponse(
        project_id=project_id,
        sources=research.repository.list_for_project(project_id),
    )
