from typing import Annotated, Literal

from demodirector_contracts import Timeline, VideoExport
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from demodirector_api.exports import ExportError, ExportService
from demodirector_api.repositories import ProjectRepository
from demodirector_api.streaming_file import StreamingFileResponse as FileResponse


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeline: Timeline
    quality: Literal["1440p", "1080p", "720p"] = "1440p"


def get_export_service(request: Request) -> ExportService:
    return request.app.state.export_service  # type: ignore[no-any-return]


def get_projects(request: Request) -> ProjectRepository:
    return request.app.state.project_repository  # type: ignore[no-any-return]


Exports = Annotated[ExportService, Depends(get_export_service)]
Projects = Annotated[ProjectRepository, Depends(get_projects)]
router = APIRouter(tags=["exports"])


@router.post("/projects/{project_id}/exports", response_model=VideoExport)
def create_export(
    project_id: str,
    payload: ExportRequest,
    exports: Exports,
    projects: Projects,
) -> VideoExport:
    if projects.get(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        result = exports.create(project_id, payload.timeline, payload.quality)
        if result.status == "succeeded" and exports.records is not None:
            key = f"preferred-{project_id}"
            current = exports.records.get(key)
            exports.records.put(key, current[0] if current else 0, {"export_id": result.id})
        return result
    except ExportError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get("/projects/{project_id}/exports/latest", response_model=VideoExport)
def get_latest_export(project_id: str, exports: Exports) -> VideoExport:
    item = exports.latest(project_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return item


@router.get("/projects/{project_id}/exports/latest/video")
def play_latest_export(project_id: str, exports: Exports) -> FileResponse:
    try:
        path = exports.latest_path(project_id)
    except ExportError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=path.name,
        content_disposition_type="inline",
    )


@router.get("/projects/{project_id}/exports/{export_id}", response_model=VideoExport)
def get_export(project_id: str, export_id: str, exports: Exports) -> VideoExport:
    item = exports.get(project_id, export_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return item


@router.get("/projects/{project_id}/exports/{export_id}/download")
def download_export(
    project_id: str,
    export_id: str,
    exports: Exports,
    token: str = Query(min_length=20, max_length=200),
) -> FileResponse:
    try:
        path = exports.authorize_download(project_id, export_id, token)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ExportError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/projects/{project_id}/exports/{export_id}/video")
def play_export(project_id: str, export_id: str, exports: Exports) -> FileResponse:
    item = exports.repository.get(project_id, export_id)
    if item is None or item.file_path is None or item.export.status != "succeeded":
        raise HTTPException(404, "Export not found")
    path = exports.artifact_store.resolve(item.file_path)
    if path is None:
        raise HTTPException(404, "Export media unavailable")
    return FileResponse(path, media_type="video/mp4", content_disposition_type="inline")
