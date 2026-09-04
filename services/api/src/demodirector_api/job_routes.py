import os
from typing import Annotated

from demodirector_contracts.jobs import GenerationJob
from fastapi import APIRouter, Depends, HTTPException, Request
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel, ConfigDict, Field

from demodirector_api.auth_routes import bearer_token
from demodirector_api.generation_jobs import GenerationJobs, JobConflict
from demodirector_api.records import RecordConflict

router = APIRouter(tags=["generation jobs"])


def service(request: Request) -> GenerationJobs:
    jobs: GenerationJobs | None = request.app.state.generation_jobs
    if jobs is None:
        raise HTTPException(503, "Configure Gemini and the durable generation task queue first.")
    return jobs


Jobs = Annotated[GenerationJobs, Depends(service)]


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool = False


class TaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str = Field(pattern=r"^[a-f0-9-]{36}$")


@router.post("/projects/{project_id}/generate", response_model=GenerationJob, status_code=202)
def start(project_id: str, request: Request, jobs: Jobs) -> GenerationJob:
    try:
        return jobs.start(project_id, bearer_token(request.headers.get("authorization")))
    except KeyError as error:
        raise HTTPException(404, "Project not found") from error
    except (JobConflict, RecordConflict) as error:
        raise HTTPException(409, str(error)) from error
    except Exception as error:
        raise HTTPException(
            503, "Dispatch unavailable. Retry Start to recover the saved job."
        ) from error


@router.get("/projects/{project_id}/generation", response_model=GenerationJob)
def latest(project_id: str, jobs: Jobs) -> GenerationJob:
    job = jobs.latest(project_id)
    if job is None:
        raise HTTPException(404, "Generation has not started")
    return job


@router.post("/projects/{project_id}/generation/{job_id}/retry", response_model=GenerationJob)
def retry(project_id: str, job_id: str, payload: RetryRequest, jobs: Jobs) -> GenerationJob:
    try:
        return jobs.retry(project_id, job_id, payload.approved)
    except KeyError as error:
        raise HTTPException(404, "Job not found") from error
    except (JobConflict, RecordConflict) as error:
        raise HTTPException(409, str(error)) from error


def verify_task(request: Request) -> None:
    audience = os.getenv("DEMO_GENERATION_TASK_URL", "").rstrip("/")
    account = os.getenv("DEMO_TASK_INVOKER_SERVICE_ACCOUNT", "")
    token = bearer_token(request.headers.get("authorization"))
    if not audience or not account or not token:
        raise HTTPException(403, "Task authentication required")
    try:
        claims = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
            token, GoogleRequest(), audience=audience,
        )
        if claims.get("email") != account or claims.get("email_verified") is not True:
            raise ValueError("Unexpected task identity")
    except Exception as error:
        raise HTTPException(403, "Invalid task identity") from error


@router.post("/tasks/generate", response_model=GenerationJob, dependencies=[Depends(verify_task)])
def execute(payload: TaskRequest, jobs: Jobs) -> GenerationJob:
    try:
        return jobs.step(payload.job_id)
    except KeyError as error:
        raise HTTPException(404, "Job not found") from error
    except (JobConflict, RecordConflict) as error:
        raise HTTPException(409, str(error)) from error
