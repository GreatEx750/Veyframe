from __future__ import annotations

from typing import Annotated, Protocol

from demodirector_contracts import Scene
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict


class CaptureDispatcher(Protocol):
    def dispatch(self, project_id: str, scene: Scene) -> str: ...


class CaptureDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene: Scene


class CaptureDispatchResponse(BaseModel):
    task_name: str
    status: str = "queued"


def get_dispatcher(request: Request) -> CaptureDispatcher:
    dispatcher: CaptureDispatcher | None = request.app.state.capture_dispatcher
    if dispatcher is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cloud capture dispatch is not configured.",
        )
    return dispatcher


router = APIRouter(prefix="/projects", tags=["capture"])
DispatcherDependency = Annotated[CaptureDispatcher, Depends(get_dispatcher)]


@router.post("/{project_id}/capture-tasks", response_model=CaptureDispatchResponse)
def dispatch_capture(
    project_id: str,
    payload: CaptureDispatchRequest,
    dispatcher: DispatcherDependency,
) -> CaptureDispatchResponse:
    return CaptureDispatchResponse(task_name=dispatcher.dispatch(project_id, payload.scene))
