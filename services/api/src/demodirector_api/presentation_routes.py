from demodirector_contracts.jobs import GenerationJob
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from demodirector_api.auth_routes import bearer_token
from demodirector_api.presentation_jobs import PresentationJobs

router = APIRouter(tags=["presentation preview"])


class PresentationStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool = False
    rebuild: bool = False


def service(request: Request) -> PresentationJobs:
    jobs: PresentationJobs | None = request.app.state.presentation_jobs
    if jobs is None:
        raise HTTPException(503, "Configure the presentation generation worker and task queue.")
    return jobs


@router.post(
    "/projects/{project_id}/generation/presentation-preview",
    response_model=GenerationJob,
    status_code=202,
)
def start(project_id: str, request: Request) -> GenerationJob:
    try:
        return service(request).start(
            project_id, session_token=bearer_token(request.headers.get("authorization"))
        )
    except KeyError as error:
        raise HTTPException(404, "Project not found") from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/projects/{project_id}/generation/presentation-preview", response_model=GenerationJob)
def latest(project_id: str, request: Request) -> GenerationJob:
    job = service(request).latest(project_id)
    if job is None:
        raise HTTPException(404, "Presentation preview has not started")
    return job


@router.post(
    "/projects/{project_id}/generation/presentation", response_model=GenerationJob, status_code=202
)
def start_full(
    project_id: str,
    request: Request,
    payload: PresentationStartRequest | None = None,
) -> GenerationJob:
    try:
        return service(request).start(
            project_id,
            preview=False,
            session_token=bearer_token(request.headers.get("authorization")),
            rebuild=bool(payload and payload.rebuild),
        )
    except KeyError as error:
        raise HTTPException(404, "Project not found") from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/projects/{project_id}/generation/presentation", response_model=GenerationJob)
def latest_full(project_id: str, request: Request) -> GenerationJob:
    job = service(request).latest(project_id, preview=False)
    if job is None:
        raise HTTPException(404, "Presentation has not started")
    return job


# Task identity is checked independently of end-user project sessions.
from demodirector_api.job_routes import verify_task  # noqa: E402


class PresentationTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=128)
    preview: bool
    attempt: int = Field(ge=1, le=3)
    step: int = Field(ge=0, le=9)


@router.post(
    "/tasks/presentation", response_model=GenerationJob, dependencies=[Depends(verify_task)]
)
def execute_presentation(payload: PresentationTask, request: Request) -> GenerationJob:
    from demodirector_api.cloud_presentation import CloudPresentationJobs

    jobs = service(request)
    if not isinstance(jobs, CloudPresentationJobs):
        raise HTTPException(503, "Cloud presentation worker is unavailable")
    try:
        return jobs.step(payload.project_id, payload.preview, payload.attempt, payload.step)
    except KeyError as error:
        raise HTTPException(404, "Presentation job not found") from error
