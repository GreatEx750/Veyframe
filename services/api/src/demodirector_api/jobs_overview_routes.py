from datetime import UTC, datetime

from demodirector_contracts.jobs import JobDetails, JobsOverview
from fastapi import APIRouter, HTTPException, Request

from demodirector_api.auth_routes import CurrentIdentity
from demodirector_api.job_monitor import ACTIVE, JobMonitor
from demodirector_api.presentation_jobs import PresentationJobs

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=JobsOverview)
def overview(request: Request, identity: CurrentIdentity) -> JobsOverview:
    monitor: JobMonitor = request.app.state.job_monitor
    presentations: PresentationJobs | None = request.app.state.presentation_jobs
    details = []
    for project in monitor.projects.list(identity.user_id):
        for key, job in monitor.saved_jobs(project):
            if presentations is not None and key.startswith("presentation-"):
                job = (
                    presentations.latest(
                        project.id, preview=key.startswith("presentation-preview:")
                    )
                    or job
                )
            details.append(
                monitor.detail(
                    project,
                    job,
                    "presentation_preview"
                    if key.startswith("presentation-preview:")
                    else "presentation"
                    if key.startswith("presentation-full:")
                    else "generation",
                )
            )
    details.sort(key=lambda item: (item.job.status in ACTIVE, item.job.updated_at), reverse=True)
    return JobsOverview(
        jobs=details,
        active_count=sum(v.job.status in ACTIVE for v in details),
        server_time=datetime.now(UTC),
    )


@router.get("/jobs/{job_id}", response_model=JobDetails)
def detail(job_id: str, request: Request, identity: CurrentIdentity) -> JobDetails:
    for entry in overview(request, identity).jobs:
        if entry.job.id == job_id:
            return entry
    raise HTTPException(404, "Job not found")
