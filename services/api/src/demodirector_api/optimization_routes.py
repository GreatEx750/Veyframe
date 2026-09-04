from typing import Annotated

from demodirector_contracts.quality import OptimizationRun
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from demodirector_api.optimization import OptimizationService
from demodirector_api.video_reviews import ReviewConflict

router = APIRouter(tags=["optimization"])


def service(request: Request) -> OptimizationService:
    result: OptimizationService | None = request.app.state.optimization_service
    if result is None:
        raise HTTPException(503, "Video review must be configured first.")
    return result


Optimizations = Annotated[OptimizationService, Depends(service)]


class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str = Field(min_length=1)


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(gt=0)
    approved: bool = False


@router.post("/projects/{project_id}/optimizations", response_model=OptimizationRun)
def propose(project_id: str, payload: ProposalRequest, service: Optimizations) -> OptimizationRun:
    try:
        return service.propose(project_id, payload.review_id)
    except KeyError as error:
        raise HTTPException(404, "Review not found") from error
    except ReviewConflict as error:
        raise HTTPException(409, str(error)) from error


@router.get("/projects/{project_id}/optimizations/{run_id}", response_model=OptimizationRun)
def get(project_id: str, run_id: str, service: Optimizations) -> OptimizationRun:
    try:
        return service.get(project_id, run_id)
    except KeyError as error:
        raise HTTPException(404, "Optimization not found") from error


@router.post("/projects/{project_id}/optimizations/{run_id}/apply", response_model=OptimizationRun)
def apply(
    project_id: str, run_id: str, payload: ApplyRequest, service: Optimizations
) -> OptimizationRun:
    try:
        return service.apply(project_id, run_id, payload.expected_version, payload.approved)
    except KeyError as error:
        raise HTTPException(404, "Optimization not found") from error
    except ReviewConflict as error:
        raise HTTPException(409, str(error)) from error


@router.post("/projects/{project_id}/optimizations/{run_id}/cancel", response_model=OptimizationRun)
def cancel(project_id: str, run_id: str, service: Optimizations) -> OptimizationRun:
    try:
        return service.cancel(project_id, run_id)
    except KeyError as error:
        raise HTTPException(404, "Optimization not found") from error
    except ReviewConflict as error:
        raise HTTPException(409, str(error)) from error
