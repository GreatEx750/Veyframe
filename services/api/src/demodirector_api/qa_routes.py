from typing import Annotated

from demodirector_contracts import BriefCoverageReport, Storyboard, Timeline
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from demodirector_api.brief_coverage import (
    BriefCoverageService,
    BriefCoverageValidationError,
)
from demodirector_api.google_ai import StructuredGenerationError


class BriefCoverageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: str = Field(min_length=1, max_length=5_000)
    storyboard: Storyboard
    timeline: Timeline
    capture_evidence: dict[str, list[str]] = Field(default_factory=dict)


def get_coverage_service(request: Request) -> BriefCoverageService:
    return request.app.state.brief_coverage_service  # type: ignore[no-any-return]


CoverageService = Annotated[BriefCoverageService, Depends(get_coverage_service)]
router = APIRouter(tags=["demo-qa"])


@router.post("/projects/{project_id}/qa/brief-coverage", response_model=BriefCoverageReport)
def analyze_brief_coverage(
    project_id: str,
    payload: BriefCoverageRequest,
    service: CoverageService,
) -> BriefCoverageReport:
    try:
        return service.analyze(
            project_id,
            payload.brief,
            payload.storyboard,
            payload.timeline,
            payload.capture_evidence,
        )
    except (BriefCoverageValidationError, StructuredGenerationError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
