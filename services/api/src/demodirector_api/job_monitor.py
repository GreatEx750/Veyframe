"""Account-wide admission and durable, customer-safe generation telemetry."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from subprocess import TimeoutExpired
from threading import Event, Thread
from typing import Any, Literal

from demodirector_contracts import Project
from demodirector_contracts.jobs import GenerationJob, JobActivity, JobDetails
from demodirector_worker.narration import NARRATION_QUOTA_MESSAGE, NarrationQuotaError
from google.genai.errors import APIError
from pydantic import ValidationError

from demodirector_api.presentation_pilot import NarrationWordBudgetError, SlideDirectionError
from demodirector_api.records import RecordConflict, RecordStore
from demodirector_api.repositories import ProjectRepository

ACTIVE = {"queued", "running", "awaiting_approval"}
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)


class ActiveJobConflict(RecordConflict):
    def __init__(self) -> None:
        super().__init__(
            "You already have a demo generation in progress. "
            "Open Jobs to follow it before starting another."
        )


def safe_message(message: str) -> str:
    message = re.sub(r"https?://\S+|[A-Za-z]:[\\/]\S+", "[private reference]", message)
    message = re.sub(
        r"(?i)(bearer\s+|(?:api[_-]?key|token|password|secret)\s*[=:]\s*)\S+", "[redacted]", message
    )
    return message[:500] or "Progress update"


def failure_summary(error: Exception) -> str:
    """Describe known failure categories without forwarding provider payloads."""
    cause: BaseException | None = error
    for _ in range(5):
        if isinstance(cause, SlideDirectionError):
            return str(cause)
        if isinstance(cause, NarrationWordBudgetError):
            return (
                "The narration script did not meet its word budget after text correction. "
                "No speech was requested for that paragraph."
            )
        if isinstance(cause, NarrationQuotaError):
            return NARRATION_QUOTA_MESSAGE
        if isinstance(cause, APIError):
            provider_explanations = {
                400: "Google rejected the generation request; inspect model/schema compatibility",
                401: "Google authentication failed",
                403: "Google denied access to the configured model or project",
                404: "The configured Google model or resource was not found",
                429: "Google rate or quota limit reached",
                500: "Google returned an internal service error",
                503: "Google generation is temporarily unavailable",
            }
            if cause.code in provider_explanations:
                return f"{provider_explanations[cause.code]} (HTTP {cause.code})."
            return "Google rejected the generation request."
        if isinstance(cause, ValidationError):
            return f"Generated output failed typed validation ({cause.error_count()} issues)."
        cause = cause.__cause__ if cause else None
        if cause is None:
            break
    if isinstance(error, TimeoutExpired):
        timeout = error.timeout
        if isinstance(timeout, (int, float)) and 0 < timeout < 86_400:
            return f"Media processing exceeded its {timeout:g}-second time limit."
        return "Media processing exceeded its time limit."
    if isinstance(error, TimeoutError):
        return "The current operation did not respond within its time limit."
    if type(error).__name__ == "RendererError":
        return {
            "Media path is outside the approved project directory.": (
                "Video assembly could not access recordings in its configured media folder."
            ),
            "Timeline media file does not exist.": (
                "Video assembly could not find a required recording or narration file."
            ),
        }.get(str(error), "Video assembly failed its media processing or validation check.")
    if type(error).__name__ == "StoryboardValidationError":
        categories = {
            "scene_count": "The generated storyboard did not contain between five and ten scenes.",
            "missing_sources": "A generated scene had no grounded evidence sources.",
            "unknown_source": (
                "A generated scene referenced a source that was not in the inspected evidence."
            ),
            "missing_assertion": "A generated interaction had no visible success check.",
            "missing_submit": "A scene promised a submission but only planned to fill the form.",
        }
        code = getattr(error, "code", None)
        if code in categories:
            return categories[code]
        explanations = {
            "Storyboard duration is outside the requested 10% budget.": (
                "The generated script duration did not match the requested video length."
            ),
            "Storyboard total must equal the sum of scene durations.": (
                "Generated scene durations did not add up to the storyboard duration."
            ),
            "Storyboard scene order must be contiguous from zero.": (
                "Generated scenes were not in a valid sequence."
            ),
            "Storyboard project ID does not match the request.": (
                "The generated storyboard did not match this project."
            ),
        }
        return explanations.get(
            str(error),
            "The generated storyboard failed validation of its structure, "
            "timing, evidence references, or browser action requirements.",
        )
    return f"The operation stopped ({type(error).__name__})."


class JobMonitor:
    def __init__(self, records: RecordStore, projects: ProjectRepository) -> None:
        self.records = records
        self.projects = projects

    def saved_jobs(self, project: Project) -> list[tuple[str, GenerationJob]]:
        result = []
        pointer = self.records.get(f"generation-project-{project.id}")
        keys = [f"presentation-preview:{project.id}", f"presentation-full:{project.id}"]
        if pointer:
            keys.append(f"generation-{pointer[1]['job_id']}")
        for key in keys:
            record = self.records.get(key)
            if record:
                result.append((key, GenerationJob.model_validate(record[1])))
        return result

    def acquire(self, project: Project, job_id: str, record_key: str) -> None:
        # CAS lives in the shared database, not in a web-process semaphore.
        owner = project.owner_user_id or "system"
        key = "generation-owner-" + hashlib.sha256(owner.encode()).hexdigest()
        for _ in range(8):
            current = self.records.get(key)
            if current and current[1]["job_id"] == job_id:
                return
            if current:
                held = self.records.get(current[1]["record_key"])
                if held and held[1].get("status") in ACTIVE:
                    raise ActiveJobConflict()
                if (
                    not held
                    and (
                        datetime.now(UTC) - datetime.fromisoformat(current[1]["reserved_at"])
                    ).total_seconds()
                    < 60
                ):
                    raise ActiveJobConflict()
            # Include generations created before the admission record was introduced.
            for owned in self.projects.list(project.owner_user_id):
                if owned.owner_user_id != project.owner_user_id:
                    continue
                for _, existing in self.saved_jobs(owned):
                    if existing.id != job_id and existing.status in ACTIVE:
                        raise ActiveJobConflict()
            try:
                self.records.put(
                    key,
                    current[0] if current else 0,
                    {
                        "job_id": job_id,
                        "record_key": record_key,
                        "reserved_at": datetime.now(UTC).isoformat(),
                    },
                )
                return
            except RecordConflict:
                continue
        raise ActiveJobConflict()

    def _write(
        self,
        job: GenerationJob,
        message: str | None = None,
        level: Literal["info", "warning", "error"] = "info",
        at: datetime | None = None,
    ) -> None:
        now = at or datetime.now(UTC)
        key = f"job-monitor-{job.id}"
        for _ in range(8):
            record = self.records.get(key)
            data: dict[str, Any] = dict(record[1]) if record else {"events": [], "sequence": 0}
            data["heartbeat_at"] = now.isoformat()
            if job.status == "running" and not data.get("started_at"):
                data["started_at"] = now.isoformat()
            if message is not None:
                sequence = data["sequence"] + 1
                event = JobActivity(
                    sequence=sequence,
                    at=now,
                    stage=job.stage,
                    level=level,
                    message=safe_message(message),
                )
                data.update(
                    sequence=sequence,
                    last_progress_at=now.isoformat(),
                    events=[*data["events"], event.model_dump(mode="json")][-500:],
                )
            try:
                self.records.put(key, record[0] if record else 0, data)
                return
            except RecordConflict:
                continue
        logger.warning("Job telemetry update conflicted: job=%s", job.id)

    def event(
        self,
        job: GenerationJob,
        message: str | None = None,
        level: Literal["info", "warning", "error"] = "info",
        at: datetime | None = None,
    ) -> None:
        text = safe_message(message or job.message)
        self._write(job, text, level, at)
        logger.info(
            "generation_progress job=%s project=%s stage=%s status=%s message=%s",
            job.id,
            job.project_id,
            job.stage,
            job.status,
            text,
        )

    @contextmanager
    def heartbeat(self, job: GenerationJob) -> Iterator[None]:
        stopped = Event()
        self._write(job)

        def pulse() -> None:
            while not stopped.wait(10):
                try:
                    self._write(job)
                except Exception:
                    logger.warning("Unable to save worker heartbeat: job=%s", job.id)

        worker = Thread(target=pulse, daemon=True, name="generation-heartbeat")
        worker.start()
        try:
            yield
        finally:
            stopped.set()
            worker.join(timeout=2)

    def detail(
        self,
        project: Project,
        job: GenerationJob,
        kind: Literal["generation", "presentation_preview", "presentation"],
    ) -> JobDetails:
        now = datetime.now(UTC)
        record = self.records.get(f"job-monitor-{job.id}")
        data = record[1] if record else {}
        events = [JobActivity.model_validate(v) for v in data.get("events", [])]
        last = (
            datetime.fromisoformat(data["last_progress_at"])
            if data.get("last_progress_at")
            else job.updated_at
        )
        heartbeat = (
            datetime.fromisoformat(data["heartbeat_at"]) if data.get("heartbeat_at") else None
        )
        terminal = job.status in {"succeeded", "failed"}
        elapsed = max(
            0, int(((job.updated_at if terminal else now) - job.created_at).total_seconds())
        )
        quiet = max(0, int((now - last).total_seconds()))
        health: Any = (
            "finished"
            if terminal
            else "paused"
            if job.status in {"awaiting_retry", "awaiting_approval"}
            else "queued"
            if job.status == "queued"
            else "responding"
        )
        explanation = {
            "finished": "Generation finished."
            if job.status == "succeeded"
            else "Generation stopped; review the latest error before retrying.",
            "paused": "Waiting for your approval. No automatic paid retry will run.",
            "queued": "Waiting for a worker to claim this job.",
            "responding": "Worker is responding; activity below shows its last completed update.",
        }[health]
        if job.status == "running" and (not heartbeat or (now - heartbeat).total_seconds() > 45):
            health, explanation = (
                "unresponsive",
                "No recent worker heartbeat. The worker may have stopped; "
                "do not assume the job is advancing.",
            )
        elif job.status == "running" and quiet > 180:
            health, explanation = (
                "slow",
                "Worker heartbeat is present, but no step progress has been reported for "
                "over three minutes. It may be waiting on a provider or renderer.",
            )
        elif job.status == "queued" and quiet > 60:
            explanation = (
                "No worker has claimed this job. Check that the local generation worker "
                "or cloud task queue is running."
            )
        budget = (
            600 if kind == "presentation_preview" else 180 + project.requested_duration_seconds * 6
        )
        started = datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
        processing = max(0, int((now - started).total_seconds())) if started else 0
        lower: int | None = max(0, int(budget * 0.7) - processing)
        upper: int | None = max(0, int(budget * 1.5) - processing)
        estimate = (
            "Rough planning range based on format and video length, excluding queue wait. "
            "Not a deadline: provider and render times vary."
        )
        if health != "responding" or upper == 0:
            lower = upper = None
            estimate = (
                "No reliable remaining-time estimate while queued, paused, unresponsive, "
                "finished, or beyond the planning range."
            )
        clean = job.model_copy(update={"message": safe_message(job.message)})
        return JobDetails(
            job=clean,
            project_name=project.name,
            format_label={"spotlight_demo": "Spotlight · 30 seconds",
                          "short_demo": "Short · 45 seconds"}.get(project.demo_mode),
            kind=kind,
            elapsed_seconds=elapsed,
            step_elapsed_seconds=max(
                0, int(((job.updated_at if terminal else now) - last).total_seconds())
            ),
            last_progress_at=last,
            heartbeat_at=heartbeat,
            health=health,
            health_message=explanation,
            eta_min_seconds=lower,
            eta_max_seconds=upper,
            estimate_basis=estimate,
            events=events,
        )
