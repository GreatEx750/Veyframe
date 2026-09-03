from typing import Annotated

from demodirector_contracts import ProductUnderstanding
from fastapi import APIRouter, Depends, HTTPException, Request, status

from demodirector_api.product_understanding import ProductUnderstandingService, website_sources
from demodirector_api.repositories import (
    ProductUnderstandingRepository,
    ProjectRepository,
    ResearchSourceRepository,
    WebsiteInspectionRepository,
)


def get_projects(request: Request) -> ProjectRepository:
    return request.app.state.project_repository  # type: ignore[no-any-return]


def get_inspections(request: Request) -> WebsiteInspectionRepository:
    return request.app.state.website_inspection_repository  # type: ignore[no-any-return]


def get_sources(request: Request) -> ResearchSourceRepository:
    return request.app.state.research_source_repository  # type: ignore[no-any-return]


def get_understandings(request: Request) -> ProductUnderstandingRepository:
    return request.app.state.product_understanding_repository  # type: ignore[no-any-return]


def get_understanding_service(request: Request) -> ProductUnderstandingService:
    return request.app.state.product_understanding_service  # type: ignore[no-any-return]


ProjectDependency = Annotated[ProjectRepository, Depends(get_projects)]
InspectionDependency = Annotated[WebsiteInspectionRepository, Depends(get_inspections)]
SourceDependency = Annotated[ResearchSourceRepository, Depends(get_sources)]
UnderstandingRepositoryDependency = Annotated[
    ProductUnderstandingRepository,
    Depends(get_understandings),
]
UnderstandingServiceDependency = Annotated[
    ProductUnderstandingService,
    Depends(get_understanding_service),
]

router = APIRouter(tags=["product-understanding"])


@router.post(
    "/projects/{project_id}/understanding",
    response_model=ProductUnderstanding,
    status_code=status.HTTP_200_OK,
)
def generate_product_understanding(
    project_id: str,
    projects: ProjectDependency,
    inspections: InspectionDependency,
    sources: SourceDependency,
    understandings: UnderstandingRepositoryDependency,
    service: UnderstandingServiceDependency,
) -> ProductUnderstanding:
    project = projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    inspection = inspections.get(project_id)
    if inspection is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inspect the project website before generating product understanding.",
        )
    persisted_website_sources = website_sources(project_id, inspection)
    sources.replace_website_sources(project_id, persisted_website_sources)
    all_sources = sources.list_for_project(project_id)
    understanding = service.generate(
        project=project,
        inspection=inspection,
        sources=all_sources,
    )
    return understandings.save(understanding)


@router.get("/projects/{project_id}/understanding", response_model=ProductUnderstanding)
def get_product_understanding(
    project_id: str,
    understandings: UnderstandingRepositoryDependency,
) -> ProductUnderstanding:
    understanding = understandings.get(project_id)
    if understanding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Understanding not found")
    return understanding
