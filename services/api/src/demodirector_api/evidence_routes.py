from typing import Annotated

from demodirector_contracts.evidence import StoryboardEvidence
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from demodirector_api.evidence import EvidenceService
from demodirector_api.generation_jobs import GenerationJobs

router = APIRouter(tags=["storyboard evidence"])


def service(request: Request) -> EvidenceService:
    result: EvidenceService = request.app.state.evidence_service
    return result


Evidence = Annotated[EvidenceService, Depends(service)]


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(gt=0)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    acknowledge_unverified: bool = False


@router.get("/projects/{project_id}/evidence", response_model=StoryboardEvidence)
def evidence(project_id: str, service: Evidence) -> StoryboardEvidence:
    try:
        return service.dashboard(project_id)
    except KeyError as error:
        raise HTTPException(404, "Storyboard not found") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/projects/{project_id}/storyboard-approval", response_model=StoryboardEvidence)
def approve(
    project_id: str, payload: ApprovalRequest, request: Request, service: Evidence
) -> StoryboardEvidence:
    try:
        result = service.approve(
            project_id,
            payload.expected_version,
            payload.fingerprint,
            payload.acknowledge_unverified,
        )
        jobs: GenerationJobs | None = request.app.state.generation_jobs
        if jobs is not None:
            jobs.resume_approved(project_id)
        return result
    except KeyError as error:
        raise HTTPException(404, "Storyboard not found") from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
