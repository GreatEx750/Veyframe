from typing import Annotated

from demodirector_contracts import SessionSummary
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from demodirector_api.auth_routes import Auth, bearer_token
from demodirector_api.export_routes import Exports, Projects
from demodirector_api.youtube import (
    ConnectionStatus,
    LocalYouTube,
    UploadInput,
    UploadStatus,
)

router = APIRouter(prefix="/youtube", tags=["youtube"])


def session(request: Request, auth: Auth) -> SessionSummary:
    token = bearer_token(request.headers.get("authorization"))
    if not token:
        raise HTTPException(401, "Sign in before connecting YouTube.")
    from demodirector_api.auth import AuthenticationError

    try:
        result = auth.authenticate(token)
    except AuthenticationError as error:
        raise HTTPException(401, "Sign in again before connecting YouTube.") from error
    youtube: LocalYouTube = request.app.state.youtube
    if request.method != "GET" and request.headers.get("origin") != youtube.origin:
        raise HTTPException(403, "YouTube changes must originate from this Veyframe application.")
    return result


Session = Annotated[SessionSummary, Depends(session)]


def service(request: Request) -> LocalYouTube:
    return request.app.state.youtube  # type: ignore[no-any-return]


YouTube = Annotated[LocalYouTube, Depends(service)]


def owned(project_id: str, projects: Projects, current: SessionSummary) -> None:
    project = projects.get(project_id)
    if project is None or project.owner_user_id != current.user.user_id:
        raise HTTPException(404, "Project not found")


class ConnectInput(BaseModel):
    project_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w-]+$")


class CallbackInput(BaseModel):
    state: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=4096)


@router.get("/status", response_model=ConnectionStatus)
def connection_status(current: Session, youtube: YouTube) -> ConnectionStatus:
    return youtube.status(current.session_id)


@router.post("/connect")
def connect(
    payload: ConnectInput, current: Session, youtube: YouTube, projects: Projects
) -> dict[str, str]:
    owned(payload.project_id, projects, current)
    return {"url": youtube.connect(current.session_id, payload.project_id)}


@router.post("/callback")
def callback(payload: CallbackInput, current: Session, youtube: YouTube) -> dict[str, str]:
    return {"project_id": youtube.callback(current.session_id, payload.state, payload.code)}


@router.post("/disconnect")
def disconnect(current: Session, youtube: YouTube) -> dict[str, bool]:
    youtube.disconnect(current.session_id)
    return {"disconnected": True}


@router.post("/projects/{project_id}/uploads", response_model=UploadStatus)
def upload(
    project_id: str,
    payload: UploadInput,
    current: Session,
    youtube: YouTube,
    projects: Projects,
    exports: Exports,
    tasks: BackgroundTasks,
) -> UploadStatus:
    owned(project_id, projects, current)
    item = exports.repository.get(project_id, payload.export_id)
    if item is None or item.export.status != "succeeded" or not item.file_path:
        raise HTTPException(404, "A completed saved export is required.")
    path = exports.artifact_store.resolve(item.file_path)
    if path is None:
        raise HTTPException(404, "The saved MP4 is unavailable.")
    result = youtube.start(current.session_id, project_id, payload, path)
    if result.status == "queued":
        tasks.add_task(youtube.upload, result.id)
    return result


@router.get("/projects/{project_id}/uploads/{job_id}", response_model=UploadStatus)
def upload_status(
    project_id: str, job_id: str, current: Session, youtube: YouTube, projects: Projects
) -> UploadStatus:
    owned(project_id, projects, current)
    return youtube.job(current.session_id, project_id, job_id)
