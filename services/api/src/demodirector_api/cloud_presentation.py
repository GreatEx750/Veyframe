"""Request-bound authored slides with durable cloud checkpoints and explicit recovery."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from demodirector_contracts import CaptureAction, Project
from demodirector_contracts.jobs import GenerationJob
from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2
from pydantic import BaseModel, ConfigDict, Field

from demodirector_api.cloud import CloudTasksGateway, CloudTasksSettings
from demodirector_api.exports import CloudBucket
from demodirector_api.generation import DemoGenerationService
from demodirector_api.generation_jobs import CaptureTokenVault
from demodirector_api.job_monitor import failure_summary
from demodirector_api.presentation_jobs import PresentationJobs
from demodirector_api.presentation_pipeline import run_presentation
from demodirector_api.records import RecordConflict, RecordStore


class PresentationDispatch(Protocol):
    def dispatch(self, project_id: str, preview: bool, attempt: int, step: int) -> None: ...


class CloudPresentationDispatcher:
    def __init__(self, client: CloudTasksGateway, settings: CloudTasksSettings) -> None:
        self.client = client
        self.settings = settings

    def dispatch(self, project_id: str, preview: bool, attempt: int, step: int) -> None:
        payload = dict(project_id=project_id, preview=preview, attempt=attempt, step=step)
        identity = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with suppress(AlreadyExists):
            self.client.create_task(
                parent=self.settings.parent,
                task={
                    "name": f"{self.settings.parent}/tasks/presentation-{identity}",
                    "http_request": {
                        "http_method": tasks_v2.HttpMethod.POST,
                        "url": f"{self.settings.worker_url.rstrip('/')}/tasks/presentation",
                        "headers": {"Content-Type": "application/json"},
                        "body": json.dumps(payload).encode(),
                        "oidc_token": {
                            "service_account_email": self.settings.invoker_service_account,
                            "audience": self.settings.worker_url.rstrip("/"),
                        },
                    },
                    "dispatch_deadline": "900s",
                },
            )


class CachedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0, le=512 * 1024 * 1024)


class CloudPresentationCache:
    """Content-addressed private files; the job record commits a complete manifest last."""

    def __init__(self, bucket: CloudBucket) -> None:
        self.bucket = bucket

    def _prefix(self, project_id: str, preview: bool) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
            raise ValueError("Invalid presentation project identifier")
        return f"presentation-cache/{project_id}/{'preview' if preview else 'full'}/"

    def _path(self, root: Path, relative: str) -> Path:
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts or "\\" in relative or ":" in relative:
            raise ValueError("Invalid presentation cache path")
        path = (root / relative).resolve()
        if root.resolve() not in path.parents:
            raise ValueError("Presentation cache path escaped its project")
        return path

    def save(self, root: Path, project_id: str, preview: bool) -> dict[str, Any]:
        prefix = self._prefix(project_id, preview)
        manifest: dict[str, Any] = {}
        for source in sorted(root.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(root).as_posix()
            self._path(root, relative)
            entry = CachedFile(
                sha256=hashlib.sha256(source.read_bytes()).hexdigest(), size=source.stat().st_size
            )
            blob = self.bucket.blob(prefix + entry.sha256)
            if not blob.exists():
                blob.upload_from_filename(str(source))
            manifest[relative] = entry.model_dump()
        return manifest

    def restore(self, root: Path, project_id: str, preview: bool, manifest: dict[str, Any]) -> None:
        if len(manifest) > 2000:
            raise ValueError("Presentation cache manifest is too large")
        prefix = self._prefix(project_id, preview)
        for relative, data in manifest.items():
            entry = CachedFile.model_validate(data)
            path = self._path(root, relative)
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry.sha256:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            self.bucket.blob(prefix + entry.sha256).download_to_filename(str(path))
            if (
                path.stat().st_size != entry.size
                or hashlib.sha256(path.read_bytes()).hexdigest() != entry.sha256
            ):
                raise ValueError("Presentation cache checksum mismatch")


class CloudPresentationJobs(PresentationJobs):
    def __init__(
        self,
        generation: DemoGenerationService,
        records: RecordStore,
        root: Path,
        database: Path,
        artifact_root: Path,
        dispatcher: PresentationDispatch,
        cache: CloudPresentationCache,
    ) -> None:
        super().__init__(generation, records, root, database, artifact_root)
        self.dispatcher = dispatcher
        self.cache = cache
        self.vault = CaptureTokenVault(artifact_root, cloud=True)

    def latest(self, project_id: str, preview: bool = True) -> GenerationJob | None:
        stored = self.records.get(self._key(project_id, preview))
        if not stored:
            return None
        job = GenerationJob.model_validate(stored[1])
        if job.status == "running" and job.lease_until and job.lease_until < datetime.now(UTC):
            return self._fail(
                project_id, preview, "Worker lease expired. Retry to resume saved slides."
            )
        return job

    def _state_key(self, project_id: str, preview: bool) -> str:
        return self._key(project_id, preview) + ":checkpoint"

    def _dispatch(
        self, project: Project, preview: bool, token: str | None, job: GenerationJob
    ) -> None:
        key = self._state_key(project.id, preview)
        previous = self.records.get(key)
        state = previous[1] if previous else {}
        try:
            self.records.put(
                key,
                previous[0] if previous else 0,
                {
                    "project": project.model_dump(mode="json"),
                    "attempt": job.attempts,
                    "step": 0,
                    "files": state.get("files", {}),
                    "token": self.vault.encrypt(token) if token else None,
                    "recipes": state.get("recipes"),
                },
            )
            self.dispatcher.dispatch(project.id, preview, job.attempts, 0)
        except Exception:
            self._fail(project.id, preview, "Cloud dispatch failed. Retry to resume saved slides.")
            raise ValueError("Cloud presentation dispatch is unavailable") from None
        finally:
            self.active.discard(project.id)

    def _fail(self, project_id: str, preview: bool, message: str) -> GenerationJob:
        project = self.generation.projects.get(project_id)
        if project:
            self.generation.projects.update(project.model_copy(update={"job_status": "failed"}))
        return self._update(
            project_id, preview=preview, status="failed", lease_until=None, message=message
        )

    def step(self, project_id: str, preview: bool, attempt: int, step: int) -> GenerationJob:
        job = self.latest(project_id, preview)
        if job is None:
            raise KeyError(project_id)
        if job.status != "queued" or job.attempts != attempt:
            return job
        key = self._state_key(project_id, preview)
        saved = self.records.get(key)
        if not saved or saved[1]["attempt"] != attempt or saved[1]["step"] != step:
            return job
        # CAS on the exact queued version prevents duplicate task deliveries across instances.
        claimed = job.model_copy(
            update={
                "status": "running",
                "version": job.version + 1,
                "updated_at": datetime.now(UTC),
                "lease_until": datetime.now(UTC) + timedelta(seconds=960),
                "message": f"Cloud worker: slide {step + 1}"
                if step < (5 if preview else 9)
                else "Assemble presentation",
            }
        )
        try:
            self.records.put(
                self._key(project_id, preview), job.version, claimed.model_dump(mode="json")
            )
        except RecordConflict:
            return self.latest(project_id, preview) or job
        self.monitor.event(claimed)
        state = dict(saved[1])
        project = Project.model_validate(state["project"])
        output = self.artifact_root / "presentations" / project_id
        if not preview:
            output /= "full"
        count = 5 if preview else 9
        try:
            with self.monitor.heartbeat(claimed):
                self.generation.projects.update(
                    project.model_copy(update={"job_status": "running"})
                )
                self.cache.restore(output, project_id, preview, state["files"])
                token = self.vault.decrypt(state["token"]) if state.get("token") else None
                if not state.get("recipes"):
                    recipes = self._recipes(project, token)
                    state["recipes"] = {
                        name: {"url": url, "actions": [a.model_dump(mode="json") for a in actions]}
                        for name, (url, actions) in recipes.items()
                    }
                else:
                    recipes = {
                        name: (
                            entry["url"],
                            [CaptureAction.model_validate(a) for a in entry["actions"]],
                        )
                        for name, entry in state["recipes"].items()
                    }

                def progress(message: str) -> None:
                    current = self.latest(project_id, preview)
                    if not current or current.status != "running" or current.attempts != attempt:
                        raise ValueError("Presentation lease is no longer active")
                    stage = (
                        "render"
                        if any(s in message for s in ["Assemble", "render", "verified"])
                        else "capture"
                        if "record" in message
                        else "narration"
                        if "narration" in message
                        else "research"
                        if "Research" in message
                        else "storyboard"
                    )
                    self._update(project_id, preview=preview, stage=stage, message=message)

                report = run_presentation(
                    project,
                    self.root,
                    output,
                    self.database,
                    progress,
                    recipes,
                    preview=preview,
                    session_token=token,
                    generation=self.generation,
                    slide_limit=step + 1 if step < count else None,
                )
                state["files"] = self.cache.save(output, project_id, preview)
                state["step"] = step + 1
                self.records.put(key, saved[0], state)
                if "export" in report:
                    export = report["export"]
                    assert isinstance(export, dict)
                    return self._update(
                        project_id,
                        preview=preview,
                        status="succeeded",
                        stage="done",
                        lease_until=None,
                        export_id=export["id"],
                        timeline_version=1,
                        completed_stages=[
                            "inspection",
                            "research",
                            "storyboard",
                            "capture",
                            "narration",
                            "render",
                        ],
                        message=(
                            f"Ready: {count} slides · {61 if preview else 120} seconds"
                            " · cloud video saved"
                        ),
                    )
                queued = self._update(
                    project_id,
                    preview=preview,
                    status="queued",
                    lease_until=None,
                    message=f"Saved slide {step + 1}/{count} to cloud storage; continuing",
                    completed_stages=["inspection", "research"],
                )
                self.dispatcher.dispatch(project_id, preview, attempt, step + 1)
                return queued
        except Exception as error:
            self.monitor.event(claimed, failure_summary(error), "error")
            return self._fail(
                project_id,
                preview,
                f"Presentation stopped ({type(error).__name__}). "
                "Retry to resume cloud-saved slides.",
            )
