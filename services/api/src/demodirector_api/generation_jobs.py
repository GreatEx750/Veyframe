from __future__ import annotations

import json
import logging
import os
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.fernet import Fernet
from demodirector_contracts import (
    Project,
    SceneCaptureResult,
    SceneClip,
    Storyboard,
    Timeline,
)
from demodirector_contracts.jobs import GenerationJob, GenerationStage

from demodirector_api.cloud import CloudTasksGateway, CloudTasksSettings
from demodirector_api.generation import (
    DemoGenerationService,
    allocate_scene_durations,
    assemble_timeline,
    prepare_continuous_capture,
)
from demodirector_api.product_understanding import website_sources
from demodirector_api.records import RecordConflict, RecordStore, SQLiteRecordStore

STAGES: tuple[GenerationStage, ...] = (
    "inspection",
    "research",
    "understanding",
    "storyboard",
    "capture",
    "narration",
    "render",
    "done",
)
PAID_STAGES = {"research", "understanding", "storyboard", "narration"}
logger = logging.getLogger(__name__)


class JobConflict(ValueError):
    pass


class ApprovalNeeded(ValueError):
    pass


class JobDispatcher(Protocol):
    def dispatch(self, job_id: str, version: int) -> None: ...


class LocalJobDispatcher:
    def dispatch(self, job_id: str, version: int) -> None:
        # The separate local worker scans the durable queue; no request-bound background thread.
        del job_id, version


class CloudGenerationDispatcher:
    def __init__(self, client: CloudTasksGateway, settings: CloudTasksSettings) -> None:
        self.client = client
        self.settings = settings

    def dispatch(self, job_id: str, version: int) -> None:
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import tasks_v2

        with suppress(AlreadyExists):
            self.client.create_task(
                parent=self.settings.parent,
                task={
                    "name": f"{self.settings.parent}/tasks/generate-{job_id}-{version}",
                    "http_request": {
                        "http_method": tasks_v2.HttpMethod.POST,
                        "url": f"{self.settings.worker_url.rstrip('/')}/tasks/generate",
                        "headers": {"Content-Type": "application/json"},
                        "body": json.dumps({"job_id": job_id}).encode(),
                        "oidc_token": {
                            "service_account_email": self.settings.invoker_service_account,
                            "audience": self.settings.worker_url.rstrip("/"),
                        },
                    },
                    "dispatch_deadline": "900s",
                },
            )


class CaptureTokenVault:
    def __init__(self, root: Path, cloud: bool) -> None:
        self.root = root
        self.cloud = cloud

    def _cipher(self) -> Fernet:
        supplied = os.getenv("DEMO_JOB_TOKEN_KEY")
        if supplied:
            return Fernet(supplied.encode())
        if self.cloud:
            raise JobConflict(
                "Authenticated capture requires DEMO_JOB_TOKEN_KEY from Secret Manager."
            )
        path = self.root / "job-token.key"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(Fernet.generate_key())
        except FileExistsError:
            pass
        return Fernet(path.read_bytes())

    def encrypt(self, value: str) -> str:
        return self._cipher().encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._cipher().decrypt(value.encode(), ttl=43_200).decode()


class StageExecutor(Protocol):
    def execute(self, job: GenerationJob) -> dict[str, Any]: ...


class StoryboardApproval(Protocol):
    def approved_inputs(self, project_id: str) -> tuple[Storyboard, Project]: ...


class GenerationStages:
    def __init__(
        self,
        service: DemoGenerationService,
        records: RecordStore,
        vault: CaptureTokenVault,
        approval: StoryboardApproval | None = None,
    ) -> None:
        self.service = service
        self.records = records
        self.vault = vault
        self.approval = approval

    def _context(self, job: GenerationJob) -> dict[str, Any]:
        result = self.records.get(f"job-input-{job.id}")
        if result is None:
            raise JobConflict("Generation input is missing")
        return result[1]

    def execute(self, job: GenerationJob) -> dict[str, Any]:
        s = self.service
        context = self._context(job)
        project = Project.model_validate(context["project"])
        token = (
            self.vault.decrypt(context["capture_token"])
            if job.stage in {"inspection", "capture"} and context.get("capture_token")
            else None
        )
        if job.stage == "inspection":
            inspection = s.inspector.inspect(
                project_id=project.id, website_url=str(project.website_url), session_token=token
            )
            if not inspection.pages:
                raise JobConflict("No usable website pages")
            s.inspections.save(inspection)
            s.research_sources.replace_website_sources(
                project.id, website_sources(project.id, inspection)
            )
            return {"warning": inspection.warning}
        if job.stage == "research":
            result = s.research.analyze(project)
            return {"warning": result.warning}
        if job.stage == "understanding":
            saved_inspection = s.inspections.get(project.id)
            if saved_inspection is None:
                raise JobConflict("Inspection checkpoint is missing")
            understanding_result = s.understanding_generator.generate(
                project=project,
                inspection=saved_inspection,
                sources=s.research_sources.list_for_project(project.id),
            )
            s.understandings.save(understanding_result)
            return {"project_id": project.id}
        if job.stage == "storyboard":
            understanding = s.understandings.get(project.id)
            if understanding is None:
                raise JobConflict("Understanding checkpoint is missing")
            storyboard_result = s.storyboard_generator.generate(
                project=project,
                understanding=understanding,
                sources=s.research_sources.list_for_project(project.id),
            )
            s.storyboards.save(storyboard_result)
            return {"storyboard": storyboard_result.model_dump(mode="json")}
        board = s.storyboards.get_latest(project.id)
        if job.stage == "capture" and self.approval is not None:
            board, project = self.approval.approved_inputs(project.id)
        if board is None:
            raise JobConflict("Storyboard is missing")
        scenes = sorted(board.scenes, key=lambda scene: scene.order)
        durations = allocate_scene_durations(scenes, project.requested_duration_seconds * 1000)
        if job.stage == "capture":
            scene = prepare_continuous_capture(scenes, durations)
            capture = s.capture_worker.capture_scene(scene, session_token=token)
            if capture.status != "succeeded" or capture.raw_clip_path is None:
                failed_actions = [
                    result.action_index
                    for result in capture.action_results
                    if result.status == "failed"
                ]
                logger.warning(
                    "Capture failed for project %s after %sms; error=%s; failed_actions=%s",
                    project.id,
                    capture.duration_ms,
                    capture.error or "no usable video was returned",
                    failed_actions,
                )
                raise JobConflict("Capture did not produce a usable video")
            media = s.timeline_media_store.persist(
                Timeline(
                    project_id=project.id,
                    duration_ms=sum(durations),
                    scene_clips=[
                        SceneClip(
                            id="capture",
                            scene_id=capture.scene_id,
                            start_ms=0,
                            end_ms=sum(durations),
                            source_uri=capture.raw_clip_path,
                        )
                    ],
                )
            )
            return {
                "capture": capture.model_dump(mode="json"),
                "media": media.model_dump(mode="json"),
                "storyboard": board.model_dump(mode="json"),
                "project": project.model_dump(mode="json"),
            }
        capture_checkpoint = self.records.get(f"job-stage-{job.id}-capture")
        if capture_checkpoint is None:
            raise JobConflict("Capture checkpoint is missing")
        # Freeze the exact captured script; later storyboard edits cannot change narration silently.
        board = Storyboard.model_validate(capture_checkpoint[1]["storyboard"])
        project = Project.model_validate(capture_checkpoint[1].get("project", context["project"]))
        scenes = sorted(board.scenes, key=lambda scene: scene.order)
        durations = allocate_scene_durations(scenes, project.requested_duration_seconds * 1000)
        if job.stage == "narration":
            media = s.timeline_media_store.materialize(
                Timeline.model_validate(capture_checkpoint[1]["media"])
            )
            capture = SceneCaptureResult.model_validate(capture_checkpoint[1]["capture"])
            capture = capture.model_copy(update={"raw_clip_path": media.scene_clips[0].source_uri})
            narration = s.narration.generate(
                scenes, s.voice, capture_clip_paths=[media.scene_clips[0].source_uri]
            )
            if narration.status != "succeeded" or len(narration.segments) != len(scenes):
                raise JobConflict("Narration did not produce every scene")
            timeline = assemble_timeline(
                project,
                scenes,
                durations,
                capture,
                narration,
                s.caption_style,
                s.captions,
                s.camera,
            )
            saved = s.timeline_media_store.persist(timeline)
            return {"timeline": saved.model_dump(mode="json")}
        checkpoint = self.records.get(f"job-stage-{job.id}-narration")
        if checkpoint is None:
            raise JobConflict("Narration checkpoint is missing")
        timeline = Timeline.model_validate(checkpoint[1]["timeline"])
        history = s.timelines.current(project.id) or s.timelines.initialize(timeline)
        if history.current.timeline != timeline:
            raise JobConflict("Timeline changed before generation finished")
        video = s.exports.create(project.id, timeline, "1440p")
        if video.status != "succeeded":
            raise JobConflict("Renderer could not finish the export")
        s._set_status(project.id, "published", "succeeded")
        return {"export_id": video.id, "timeline_version": history.current.version}


class GenerationJobs:
    def __init__(
        self,
        records: RecordStore,
        executor: StageExecutor,
        dispatcher: JobDispatcher,
        generation: DemoGenerationService,
        vault: CaptureTokenVault,
    ) -> None:
        self.records = records
        self.executor = executor
        self.dispatcher = dispatcher
        self.generation = generation
        self.vault = vault

    def get(self, job_id: str, project_id: str | None = None) -> GenerationJob:
        record = self.records.get(f"generation-{job_id}")
        if record is None or (project_id is not None and record[1]["project_id"] != project_id):
            raise KeyError("Generation job not found")
        return GenerationJob.model_validate(record[1])

    def latest(self, project_id: str) -> GenerationJob | None:
        record = self.records.get(f"generation-project-{project_id}")
        return None if record is None else self.get(str(record[1]["job_id"]), project_id)

    def start(self, project_id: str, session_token: str | None = None) -> GenerationJob:
        existing = self.latest(project_id)
        if existing is not None:
            if existing.status == "queued":
                self.dispatcher.dispatch(existing.id, existing.version)
            return existing
        project = self.generation.projects.get(project_id)
        if project is None:
            raise KeyError("Project not found")
        if self.generation.timelines.current(project_id) is not None:
            raise JobConflict("This project already has a timeline; open the editor.")
        parts = urlsplit(str(project.website_url))
        origin = f"{parts.scheme}://{parts.netloc}"
        allowed = {
            v.strip().rstrip("/") for v in os.getenv("DEMO_CAPTURE_AUTH_ORIGINS", "").split(",")
        }
        encrypted = (
            self.vault.encrypt(session_token) if session_token and origin in allowed else None
        )
        now = datetime.now(UTC)
        job = GenerationJob(
            id=str(uuid4()),
            project_id=project_id,
            status="queued",
            stage="inspection",
            version=1,
            created_at=now,
            updated_at=now,
            message="Queued. You may close this browser; progress is saved on the server.",
        )
        self.records.put(
            f"job-input-{job.id}",
            0,
            {"project": project.model_dump(mode="json"), "capture_token": encrypted},
        )
        self.records.put(f"generation-{job.id}", 0, job.model_dump(mode="json"))
        try:
            self.records.put(f"generation-project-{project_id}", 0, {"job_id": job.id})
        except RecordConflict:
            winner = self.latest(project_id)
            assert winner is not None
            return winner
        self.generation._set_status(project_id, "storyboarding", "queued")
        self.dispatcher.dispatch(job.id, job.version)
        return job

    def _save(self, job: GenerationJob, **updates: Any) -> GenerationJob:
        updated = GenerationJob.model_validate(
            {
                **job.model_dump(),
                **updates,
                "version": job.version + 1,
                "updated_at": datetime.now(UTC),
            }
        )
        self.records.put(f"generation-{job.id}", job.version, updated.model_dump(mode="json"))
        return updated

    def step(self, job_id: str) -> GenerationJob:
        job = self.get(job_id)
        canonical = self.latest(job.project_id)
        if canonical is None or canonical.id != job.id:
            raise JobConflict("Job is not the active project generation")
        now = datetime.now(UTC)
        checkpoint_key = f"job-stage-{job.id}-{job.stage}"
        checkpoint = self.records.get(checkpoint_key)
        if job.status == "running":
            if job.lease_until and job.lease_until > now:
                raise JobConflict("This stage already has an active worker lease")
            if checkpoint is None and job.stage in PAID_STAGES:
                return self._save(
                    job,
                    status="awaiting_retry",
                    lease_until=None,
                    message="Paid stage interrupted; approve retry before spending again.",
                )
        elif job.status != "queued":
            return job
        if job.attempts >= 3 and checkpoint is None:
            return self._save(
                job,
                status="failed",
                lease_until=None,
                message="Three-attempt limit reached for this stage.",
            )
        try:
            claimed = self._save(
                job,
                status="running",
                attempts=job.attempts + (checkpoint is None),
                lease_until=now + timedelta(seconds=960),
                message=f"Running {job.stage}.",
            )
        except RecordConflict as error:
            raise JobConflict("Another worker claimed this stage") from error
        try:
            if checkpoint is None:
                result = self.executor.execute(claimed)
                self.records.put(checkpoint_key, 0, result)
            else:
                result = checkpoint[1]
        except ApprovalNeeded:
            return self._save(
                claimed,
                status="awaiting_approval",
                lease_until=None,
                attempts=max(0, claimed.attempts - 1),
                message="Review storyboard evidence, then approve capture and narration.",
            )
        except Exception:
            logger.exception(
                "Generation stage %s failed for project %s",
                job.stage,
                job.project_id,
            )
            failed = self._save(
                claimed,
                status="awaiting_retry",
                lease_until=None,
                message=f"{job.stage.capitalize()} failed. Completed checkpoints are safe. "
                "Explicit retry may repeat this stage's provider work.",
            )
            self.generation._set_status(job.project_id, "failed", "failed")
            return failed
        next_stage = STAGES[STAGES.index(job.stage) + 1]
        saved = self._save(
            claimed,
            stage=next_stage,
            attempts=0,
            lease_until=None,
            completed_stages=[*job.completed_stages, job.stage],
            status="succeeded" if next_stage == "done" else "queued",
            message="Video ready."
            if next_stage == "done"
            else f"{job.stage.capitalize()} saved; {next_stage} queued.",
            export_id=result.get("export_id"),
            timeline_version=result.get("timeline_version"),
        )
        if saved.status == "queued":
            # Delivery failures leave a durable queued job. Retrying the current task dispatches it.
            self.dispatcher.dispatch(saved.id, saved.version)
        return saved

    def retry(self, project_id: str, job_id: str, approved: bool) -> GenerationJob:
        job = self.get(job_id, project_id)
        if job.status == "queued":
            self.dispatcher.dispatch(job.id, job.version)
            return job
        if job.status != "awaiting_retry" or not approved or job.attempts >= 3:
            raise JobConflict("Retry requires explicit approval and remaining attempts.")
        queued = self._save(
            job, status="queued", message="Retry approved; completed stages will be reused."
        )
        self.generation._set_status(project_id, "storyboarding", "queued")
        self.dispatcher.dispatch(job.id, queued.version)
        return queued

    def local_tick(self) -> bool:
        if not isinstance(self.records, SQLiteRecordStore):
            raise JobConflict("Use authenticated Cloud Tasks for cloud generation.")
        import sqlite3

        with sqlite3.connect(self.records.database) as connection:
            rows = connection.execute(
                "SELECT r.payload FROM workflow_records r JOIN "
                "(SELECT key, MAX(version) AS version FROM workflow_records "
                "WHERE key LIKE 'generation-%' GROUP BY key) latest "
                "ON r.key=latest.key AND r.version=latest.version"
            ).fetchall()
        for row in rows:
            value = json.loads(row[0])
            if "status" not in value:
                continue
            job = GenerationJob.model_validate(value)
            if job.status == "queued" or (
                job.status == "running" and job.lease_until and job.lease_until < datetime.now(UTC)
            ):
                try:
                    self.step(job.id)
                    return True
                except JobConflict:
                    continue
        return False

    def resume_approved(self, project_id: str) -> GenerationJob | None:
        job = self.latest(project_id)
        if job is None or job.status != "awaiting_approval":
            return job
        resumed = self._save(job, status="queued", message="Storyboard approved; capture queued.")
        self.generation._set_status(project_id, "ready", "queued")
        self.dispatcher.dispatch(job.id, resumed.version)
        return resumed
