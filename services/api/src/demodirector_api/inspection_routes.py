from typing import Annotated

from demodirector_contracts import WebsiteInspection
from demodirector_worker import WebsiteInspector
from fastapi import APIRouter, Depends, HTTPException, Request, status

from demodirector_api.repositories import (
    ProjectRepository,
    WebsiteInspectionRepository,
)


def get_project_repository(request: Request) -> ProjectRepository:
    return request.app.state.project_repository  # type: ignore[no-any-return]


def get_inspector(request: Request) -> WebsiteInspector:
    return request.app.state.website_inspector  # type: ignore[no-any-return]


def get_inspection_repository(request: Request) -> WebsiteInspectionRepository:
    return request.app.state.website_inspection_repository  # type: ignore[no-any-return]


ProjectDependency = Annotated[ProjectRepository, Depends(get_project_repository)]
InspectorDependency = Annotated[WebsiteInspector, Depends(get_inspector)]
InspectionRepositoryDependency = Annotated[
    WebsiteInspectionRepository,
    Depends(get_inspection_repository),
]

router = APIRouter(tags=["website-inspection"])


@router.post(
    "/projects/{project_id}/inspect",
    response_model=WebsiteInspection,
    status_code=status.HTTP_200_OK,
)
def inspect_project_website(
    project_id: str,
    projects: ProjectDependency,
    inspector: InspectorDependency,
    inspections: InspectionRepositoryDependency,
) -> WebsiteInspection:
    project = projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    result = inspector.inspect(project_id=project.id, website_url=str(project.website_url))
    return inspections.save(result)


@router.get("/projects/{project_id}/inspection", response_model=WebsiteInspection)
def get_project_inspection(
    project_id: str,
    inspections: InspectionRepositoryDependency,
) -> WebsiteInspection:
    result = inspections.get(project_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    return result
