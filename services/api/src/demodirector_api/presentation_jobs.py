"""Local, authenticated authored presentation jobs with saved progress."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

from demodirector_contracts import CaptureAction, Project
from demodirector_contracts.jobs import GenerationJob

from demodirector_api.generation import DemoGenerationService
from demodirector_api.job_monitor import JobMonitor, failure_summary
from demodirector_api.presentation_pipeline import RECIPES, action, run_presentation
from demodirector_api.product_understanding import website_sources
from demodirector_api.records import RecordStore


class PresentationJobs:
    def __init__(
        self,
        generation: DemoGenerationService,
        records: RecordStore,
        root: Path,
        database: Path,
        artifact_root: Path,
    ) -> None:
        self.generation = generation
        self.records = records
        self.root = root.resolve()
        self.database = database.resolve()
        self.artifact_root = artifact_root.resolve()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="presentation")
        self.active: set[str] = set()
        self.lock = RLock()
        self.monitor = JobMonitor(records, generation.projects)

    def _key(self, project_id: str, preview: bool = True) -> str:
        return f"presentation-{'preview' if preview else 'full'}:{project_id}"

    def latest(self, project_id: str, preview: bool = True) -> GenerationJob | None:
        with self.lock:
            stored = self.records.get(self._key(project_id, preview))
            if not stored:
                return None
            job = GenerationJob.model_validate(stored[1])
            if job.status in {"queued", "running"} and project_id not in self.active:
                project = self.generation.projects.get(project_id)
                if project is not None:
                    self.generation.projects.update(
                        project.model_copy(update={"job_status": "failed"})
                    )
                return self._update(
                    project_id,
                    preview=preview,
                    status="failed",
                    message="Local worker stopped. Retry to resume saved slides.",
                )
            return job

    def _update(self, project_id: str, *, preview: bool = True, **changes: Any) -> GenerationJob:
        with self.lock:
            stored = self.records.get(self._key(project_id, preview))
            if not stored:
                raise KeyError(project_id)
            job = GenerationJob.model_validate(
                {**stored[1], **changes, "version": stored[0] + 1, "updated_at": datetime.now(UTC)}
            )
            self.records.put(self._key(project_id, preview), stored[0], job.model_dump(mode="json"))
            self.monitor.event(job)
            return job

    def start(
        self,
        project_id: str,
        *,
        preview: bool = True,
        session_token: str | None = None,
        rebuild: bool = False,
    ) -> GenerationJob:
        with self.lock:
            project = self.generation.projects.get(project_id)
            if project is None:
                raise KeyError(project_id)
            if project.demo_mode != "presentation_demo":
                raise ValueError("Choose Presentation Demo for authored slides.")
            existing = self.latest(project_id, preview)
            if (
                existing
                and existing.status != "failed"
                and not (rebuild and existing.status == "succeeded")
            ):
                return existing
            timeline = self.generation.timelines.current(project_id)
            if timeline is not None and (existing is None or timeline.current.version != 1):
                raise ValueError("Create a new project to generate another presentation.")
            if not existing and project.job_status in {"running", "queued"}:
                raise ValueError("This project already has an active generation job.")
            if existing and existing.attempts >= 3:
                raise ValueError("Retry limit reached. Create a new project to try again.")
            now = datetime.now(UTC)
            record = self.records.get(self._key(project_id, preview))
            version = record[0] if record else 0
            job = GenerationJob(
                id=existing.id if existing else str(uuid4()),
                project_id=project_id,
                status="queued",
                stage="inspection",
                attempts=(existing.attempts if existing else 0) + 1,
                version=version + 1,
                created_at=existing.created_at if existing else now,
                updated_at=now,
                message=(
                    "Queued: first five slides · 61-second preview"
                    if preview
                    else "Queued: nine authored slides · 120-second presentation"
                ),
            )
            self.monitor.acquire(project, job.id, self._key(project_id, preview))
            self.records.put(self._key(project_id, preview), version, job.model_dump(mode="json"))
            self.monitor.event(job)
            self.active.add(project_id)
            self.generation.projects.update(project.model_copy(update={"job_status": "queued"}))
            origin = urlsplit(str(project.website_url))
            allowed = {
                s.strip().rstrip("/")
                for s in os.getenv("DEMO_CAPTURE_AUTH_ORIGINS", "").split(",")
                if s.strip()
            }
            token = session_token if f"{origin.scheme}://{origin.netloc}" in allowed else None
            # Kept only in worker memory; retry supplies the current authenticated session.
            self._dispatch(project, preview, token, job)
            return job

    def _dispatch(
        self, project: Project, preview: bool, token: str | None, job: GenerationJob
    ) -> None:
        self.pool.submit(self._run, project, preview, token)

    def _recipes(
        self,
        project: Project,
        session_token: str | None = None,
    ) -> dict[str, tuple[str, list[CaptureAction]]]:
        inspection = self.generation.inspector.inspect(
            project_id=project.id,
            website_url=str(project.website_url),
            session_token=session_token,
        )
        self.generation.inspections.save(inspection)
        self.generation.research_sources.replace_website_sources(
            project.id, website_sources(project.id, inspection)
        )
        host = urlsplit(str(project.website_url)).hostname or ""
        if host in {
            "wikipedia.com",
            "www.wikipedia.com",
            "wikipedia.org",
            "www.wikipedia.org",
            "en.wikipedia.org",
        }:
            return RECIPES
        # Other sites use observed public navigation, never invented executable actions.
        recipes: dict[str, tuple[str, list[CaptureAction]]] = {
            "title": (str(project.website_url), [])
        }
        candidates: list[tuple[str, str, str]] = []
        for page in inspection.pages:
            for element in page.elements:
                href = urljoin(str(page.url), element.href or "")
                if (
                    element.kind == "link"
                    and element.href
                    and urlsplit(href).hostname == host
                    and urlsplit(href).scheme in {"https", "http"}
                    and not any(
                        word in href.casefold()
                        for word in ["logout", "delete", "remove", "signout", "checkout"]
                    )
                ):
                    candidates.append(
                        (
                            str(page.url),
                            element.href,
                            element.accessible_name or element.text or "linked page",
                        )
                    )
        if not candidates:
            raise ValueError("No public navigation links were observed for this presentation.")
        for index, recipe in enumerate(["search", "article", "related"]):
            start, href, label = candidates[index % len(candidates)]
            recipes[recipe] = (
                start,
                [
                    action("click", f"a[href={json.dumps(href)}] >> nth=0", f"Open {label}"),
                    CaptureAction(
                        type="scroll", description="Scroll to explore the page", value="500"
                    ),
                    CaptureAction(
                        type="scroll", description="Continue reading the page", value="500"
                    ),
                ],
            )
        return recipes

    def _run(
        self, project: Project, preview: bool = True, session_token: str | None = None
    ) -> None:
        job = self.latest(project.id, preview)
        if job is None:
            return
        with self.monitor.heartbeat(job):
            self._execute(project, preview, session_token)

    def _execute(
        self, project: Project, preview: bool = True, session_token: str | None = None
    ) -> None:
        def update(**changes: Any) -> GenerationJob:
            return self._update(project.id, preview=preview, **changes)

        try:
            update(status="running", message="Inspecting the website")
            recipes = self._recipes(project, session_token)
            self.generation.projects.update(project.model_copy(update={"job_status": "running"}))
            update(completed_stages=["inspection"], stage="research")

            def progress(message: str) -> None:
                stage = (
                    "render"
                    if any(
                        term in message for term in ["Assemble", "render", "completed and verified"]
                    )
                    else "capture"
                    if "record" in message
                    else "narration"
                    if "narration" in message
                    else "research"
                    if "Research" in message
                    else "storyboard"
                )
                update(stage=stage, message=message)

            report = run_presentation(
                project,
                self.root,
                self.artifact_root / "presentations" / project.id / "full"
                if not preview
                else self.artifact_root / "presentations" / project.id,
                self.database,
                progress,
                recipes,
                preview=preview,
                session_token=session_token,
            )
            export = report["export"]
            assert isinstance(export, dict)
            update(
                status="succeeded",
                stage="done",
                completed_stages=[
                    "inspection",
                    "research",
                    "storyboard",
                    "capture",
                    "narration",
                    "render",
                ],
                export_id=export["id"],
                timeline_version=1,
                message=(
                    "Ready: five slides · 61 seconds · word highlighting"
                    if preview
                    else "Ready: nine slides · 120 seconds · word highlighting"
                ),
            )
        except Exception as error:
            # Provider payloads and local paths never enter customer-visible failure messages.
            job = self.latest(project.id, preview)
            if job:
                self.monitor.event(
                    job,
                    f"{job.stage.capitalize()}: {failure_summary(error)} "
                    "Saved slides are preserved.",
                    "error",
                )
            update(
                status="failed",
                message=(
                    f"Presentation stopped at {job.stage if job else 'initialization'} "
                    f"({type(error).__name__}). Retry to resume saved slides; "
                    "unsaved provider work may be charged again."
                ),
            )
            self.generation.projects.update(project.model_copy(update={"job_status": "failed"}))
        finally:
            with self.lock:
                self.active.discard(project.id)
