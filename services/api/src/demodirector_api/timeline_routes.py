from collections.abc import Callable
from typing import Annotated

from demodirector_contracts import EditOperation, Timeline, TimelineHistoryState
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from demodirector_api.repositories import TimelineRepository, TimelineVersionConflict
from demodirector_api.timeline_edits import TimelineEditError, TimelineEditService


class TimelineApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    base_timeline: Timeline
    summary: str = Field(min_length=1, max_length=500)
    operations: list[EditOperation] = Field(min_length=1, max_length=20)


def get_timelines(request: Request) -> TimelineRepository:
    return request.app.state.timeline_repository  # type: ignore[no-any-return]


def get_timeline_editor(request: Request) -> TimelineEditService:
    return request.app.state.timeline_edit_service  # type: ignore[no-any-return]


Timelines = Annotated[TimelineRepository, Depends(get_timelines)]
Editor = Annotated[TimelineEditService, Depends(get_timeline_editor)]
router = APIRouter(tags=["timelines"])


@router.get("/projects/{project_id}/timeline", response_model=TimelineHistoryState)
def get_timeline(project_id: str, timelines: Timelines) -> TimelineHistoryState:
    state = timelines.current(project_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timeline not found")
    return state


@router.post("/projects/{project_id}/timeline/apply", response_model=TimelineHistoryState)
def apply_timeline_edits(
    project_id: str,
    payload: TimelineApplyRequest,
    editor: Editor,
) -> TimelineHistoryState:
    if payload.base_timeline.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Timeline project does not match the route project.",
        )
    try:
        return editor.apply(
            payload.base_timeline,
            payload.expected_version,
            payload.operations,
            payload.summary,
        )
    except TimelineVersionConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except TimelineEditError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.post("/projects/{project_id}/timeline/undo", response_model=TimelineHistoryState)
def undo_timeline(project_id: str, timelines: Timelines) -> TimelineHistoryState:
    return _move_history(timelines.undo, project_id)


@router.post("/projects/{project_id}/timeline/redo", response_model=TimelineHistoryState)
def redo_timeline(project_id: str, timelines: Timelines) -> TimelineHistoryState:
    return _move_history(timelines.redo, project_id)


def _move_history(
    action: Callable[[str], TimelineHistoryState],
    project_id: str,
) -> TimelineHistoryState:
    try:
        return action(project_id)
    except TimelineVersionConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
