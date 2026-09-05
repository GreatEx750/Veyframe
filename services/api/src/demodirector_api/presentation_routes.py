from demodirector_contracts.jobs import GenerationJob
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

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
        raise HTTPException(503, "The authored preview requires the configured local worker.")
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
