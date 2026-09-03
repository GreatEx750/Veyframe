from typing import Annotated

from demodirector_contracts import EditPlan, Timeline
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from demodirector_api.edit_planner import EditPlannerService, EditPlanValidationError
from demodirector_api.google_ai import StructuredGenerationError


class EditPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=1, max_length=1_000)
    timeline: Timeline


def get_edit_planner(request: Request) -> EditPlannerService:
    return request.app.state.edit_planner_service  # type: ignore[no-any-return]


Planner = Annotated[EditPlannerService, Depends(get_edit_planner)]
router = APIRouter(tags=["timeline-edits"])


@router.post("/projects/{project_id}/edit-plan", response_model=EditPlan)
def propose_edit(project_id: str, payload: EditPlanRequest, planner: Planner) -> EditPlan:
    if payload.timeline.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Timeline project does not match the route project.",
        )
    try:
        return planner.plan(payload.timeline, payload.instruction)
    except (EditPlanValidationError, StructuredGenerationError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
