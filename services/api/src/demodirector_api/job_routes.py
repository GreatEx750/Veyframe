import os
from typing import Annotated

from demodirector_contracts.attention import AttentionPlan
from demodirector_contracts.jobs import GenerationJob, GenerationTrace
from demodirector_contracts.longform import ChapterCheckpoint, LongFormVideoPlan
from demodirector_contracts.motion import ADKMotionRun, MotionDirectionPlan
from demodirector_contracts.style import StyleDirectionPlan, VisualVariantId
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


class AttentionEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callout_id: str = Field(min_length=1)
    expected_timeline_version: int = Field(gt=0)
    text: str | None = Field(default=None, min_length=1, max_length=72)
    placement: str | None = Field(
        default=None,
        pattern=r"^(top_left|top_right|bottom_left|bottom_right)$",
    )
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)
    target_x: float | None = Field(default=None, ge=0, le=1)
    target_y: float | None = Field(default=None, ge=0, le=1)
    remove: bool = False


class StyleSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_timeline_version: int = Field(gt=0)
    variant_id: VisualVariantId
    scene_id: str | None = Field(default=None, min_length=1)
    reset_scene: bool = False


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


@router.get("/projects/{project_id}/generation/trace", response_model=GenerationTrace)
def trace(project_id: str, jobs: Jobs) -> GenerationTrace:
    try:
        return jobs.trace(project_id)
    except KeyError as error:
        raise HTTPException(404, "Generation trace not found") from error


@router.get(
    "/projects/{project_id}/generation/motion-plan",
    response_model=MotionDirectionPlan,
)
def motion_plan(project_id: str, jobs: Jobs) -> MotionDirectionPlan:
    try:
        return jobs.motion_plan(project_id)
    except KeyError as error:
        raise HTTPException(404, "Motion direction plan not found") from error


@router.get(
    "/projects/{project_id}/generation/motion-run",
    response_model=ADKMotionRun,
)
def motion_run(project_id: str, jobs: Jobs) -> ADKMotionRun:
    try:
        return jobs.motion_run(project_id)
    except KeyError as error:
        raise HTTPException(404, "ADK motion run not found") from error


@router.get(
    "/projects/{project_id}/generation/attention-plan",
    response_model=AttentionPlan,
)
def attention_plan(project_id: str, jobs: Jobs) -> AttentionPlan:
    try:
        return jobs.attention_plan(project_id)
    except KeyError as error:
        raise HTTPException(404, "Attention plan not found") from error


@router.patch(
    "/projects/{project_id}/generation/attention-plan",
    response_model=AttentionPlan,
)
def edit_attention(
    project_id: str,
    payload: AttentionEditRequest,
    jobs: Jobs,
) -> AttentionPlan:
    changes = payload.model_dump(
        exclude={"callout_id", "expected_timeline_version"},
        exclude_none=True,
    )
    try:
        return jobs.edit_attention(
            project_id,
            payload.callout_id,
            payload.expected_timeline_version,
            changes,
        )
    except KeyError as error:
        raise HTTPException(404, "Callout not found") from error
    except (JobConflict, RecordConflict) as error:
        raise HTTPException(409, str(error)) from error


@router.get(
    "/projects/{project_id}/generation/style-plan",
    response_model=StyleDirectionPlan,
)
def style_plan(project_id: str, jobs: Jobs) -> StyleDirectionPlan:
    try:
        return jobs.style_plan(project_id)
    except KeyError as error:
        raise HTTPException(404, "Style direction plan not found") from error


@router.patch(
    "/projects/{project_id}/generation/style-plan",
    response_model=StyleDirectionPlan,
)
def select_style(
    project_id: str,
    payload: StyleSelectionRequest,
    jobs: Jobs,
) -> StyleDirectionPlan:
    try:
        return jobs.select_style(
            project_id,
            payload.expected_timeline_version,
            payload.variant_id,
            payload.scene_id,
            payload.reset_scene,
        )
    except KeyError as error:
        raise HTTPException(404, "Style direction plan not found") from error
    except (JobConflict, RecordConflict) as error:
        raise HTTPException(409, str(error)) from error


@router.get(
    "/projects/{project_id}/generation/long-form-plan",
    response_model=LongFormVideoPlan,
)
def longform_plan(project_id: str, jobs: Jobs) -> LongFormVideoPlan:
    try:
        return jobs.longform_plan(project_id)
    except KeyError as error:
        raise HTTPException(404, "Long-form plan not found") from error


@router.get(
    "/projects/{project_id}/generation/long-form-checkpoints",
    response_model=list[ChapterCheckpoint],
)
def longform_checkpoints(project_id: str, jobs: Jobs) -> list[ChapterCheckpoint]:
    try:
        return jobs.longform_checkpoints(project_id)
    except KeyError as error:
        raise HTTPException(404, "Long-form checkpoints not found") from error


@router.post(
    "/projects/{project_id}/generation/long-form-chapters/{chapter_id}/retry",
    response_model=ChapterCheckpoint,
)
def retry_longform_chapter(
    project_id: str,
    chapter_id: str,
    jobs: Jobs,
) -> ChapterCheckpoint:
    try:
        return jobs.retry_longform_chapter(project_id, chapter_id)
    except KeyError as error:
        raise HTTPException(404, "Long-form chapter not found") from error
    except (JobConflict, RecordConflict) as error:
        raise HTTPException(409, str(error)) from error


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
            token,
            GoogleRequest(),
            audience=audience,
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
