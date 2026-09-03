from typing import Annotated

from demodirector_contracts import (
    BriefCoverageReport,
    MissingRequirementRepairResult,
    RenderConfig,
    Storyboard,
    Timeline,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from demodirector_api.google_ai import StructuredGenerationError
from demodirector_api.repair import MissingRequirementRepairService, RepairValidationError


class RepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: str = Field(min_length=1, max_length=5_000)
    requirement_id: str = Field(min_length=1)
    storyboard: Storyboard
    timeline: Timeline
    qa_report: BriefCoverageReport
    capture_evidence: dict[str, list[str]] = Field(default_factory=dict)
    max_duration_seconds: float = Field(gt=0, le=600)
    approve_duration_overage: bool = False
    render_config: RenderConfig | None = None


def get_repair_service(request: Request) -> MissingRequirementRepairService:
    service = request.app.state.repair_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Repair media services are not configured.",
        )
    return service  # type: ignore[no-any-return]


RepairService = Annotated[MissingRequirementRepairService, Depends(get_repair_service)]
router = APIRouter(tags=["demo-repair"])


@router.post(
    "/projects/{project_id}/qa/repair",
    response_model=MissingRequirementRepairResult,
)
def repair_missing_requirement(
    project_id: str,
    payload: RepairRequest,
    service: RepairService,
) -> MissingRequirementRepairResult:
    try:
        return service.repair(
            project_id=project_id,
            brief=payload.brief,
            requirement_id=payload.requirement_id,
            storyboard=payload.storyboard,
            timeline=payload.timeline,
            qa_report=payload.qa_report,
            capture_evidence=payload.capture_evidence,
            max_duration_seconds=payload.max_duration_seconds,
            approve_duration_overage=payload.approve_duration_overage,
            render_config=payload.render_config,
        )
    except (RepairValidationError, StructuredGenerationError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
