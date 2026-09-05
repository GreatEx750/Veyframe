from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.fernet import Fernet
from demodirector_contracts import (
    InteractionEvent,
    ProductUnderstanding,
    Project,
    Scene,
    SceneCaptureResult,
    SceneClip,
    Storyboard,
    Timeline,
    WebsiteInspection,
)
from demodirector_contracts.attention import (
    AnimatedCallout,
    AttentionPlan,
    AttentionRequest,
    AttentionRunStep,
    NormalizedRect,
    TargetObservation,
)
from demodirector_contracts.evidence import SourceContributionMap
from demodirector_contracts.jobs import (
    GenerationJob,
    GenerationStage,
    GenerationTrace,
    GenerationTraceStage,
    StageContribution,
    TraceStageKind,
)
from demodirector_contracts.longform import (
    CaptureChapter,
    ChapterCheckpoint,
    LongFormADKRun,
    LongFormDirectionRequest,
    LongFormVideoPlan,
)
from demodirector_contracts.motion import (
    ADKMotionRun,
    MotionDirectionPlan,
    MotionDirectionRequest,
)
from demodirector_contracts.style import (
    StyleDirectionPlan,
    StyleDirectionRequest,
    StyleRunStep,
    VariantOverride,
    VisualVariantId,
)
from pydantic import ValidationError

from demodirector_api.cloud import CloudTasksGateway, CloudTasksSettings
from demodirector_api.generation import (
    DemoGenerationService,
    allocate_scene_durations,
    assemble_timeline,
    prepare_continuous_capture,
)
from demodirector_api.job_monitor import JobMonitor, failure_summary
from demodirector_api.product_understanding import website_sources
from demodirector_api.records import RecordConflict, RecordStore, SQLiteRecordStore
from demodirector_api.storyboard_generation import StoryboardValidationError

STAGES: tuple[GenerationStage, ...] = (
    "inspection",
    "research",
    "understanding",
    "storyboard",
    "motion",
    "capture",
    "attention",
    "style",
    "narration",
    "render",
    "done",
)
PAID_STAGES = {
    "research",
    "understanding",
    "storyboard",
    "motion",
    "attention",
    "style",
    "narration",
}
logger = logging.getLogger(__name__)
TRACE_ORDER: tuple[TraceStageKind, ...] = (
    "inspection",
    "research",
    "adk_coordination",
    "understanding",
    "storyboard",
    "capture",
    "narration",
    "auto_camera",
    "captions",
    "render",
)
TRACE_LABELS: dict[TraceStageKind, str] = {
    "inspection": "Inspect website",
    "research": "Research public context",
    "adk_coordination": "Coordinate planning workflow",
    "understanding": "Understand product",
    "storyboard": "Plan storyboard",
    "capture": "Record browser flow",
    "narration": "Create narration",
    "auto_camera": "Frame interactions",
    "captions": "Build captions",
    "render": "Render video",
}


def _trace_kind(stage: GenerationStage) -> TraceStageKind:
    return (
        "adk_coordination"
        if stage in {"motion", "attention", "style"}
        else cast(TraceStageKind, stage)
    )


def _trace_attempt_id(stage: GenerationStage, attempt: int) -> str:
    kind = _trace_kind(stage)
    suffix = f"-{stage}" if kind == "adk_coordination" else ""
    return f"{kind}{suffix}:{attempt}"


def _trace_label(stage: GenerationStage) -> str:
    if stage == "attention":
        return "Direct viewer attention"
    if stage == "style":
        return "Direct visual style"
    return TRACE_LABELS[_trace_kind(stage)]


def _motion_input_fingerprint(
    project: Project,
    board: Storyboard,
    sources: list[Any],
) -> str:
    payload = {
        "project": project.model_dump(mode="json"),
        "storyboard": board.model_dump(mode="json"),
        "sources": [source.model_dump(mode="json") for source in sources],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _media_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _prepare_chapter_capture(
    board: Storyboard,
    scenes: list[Scene],
    chapter: CaptureChapter,
) -> Scene:
    chapter_duration = chapter.end_ms - chapter.start_ms
    continuous = prepare_continuous_capture(
        scenes,
        allocate_scene_durations(scenes, chapter_duration),
    )
    return continuous.model_copy(update={
        "id": chapter.id,
        "storyboard_id": board.id,
        "order": chapter.order,
        "title": f"Capture chapter {chapter.order + 1}",
        "objective": "Capture the approved product sequence for this chapter.",
        "narration": "Product footage remains visible throughout this chapter.",
        "duration_seconds": chapter_duration / 1_000,
    })


def sanitize_trace_message(message: str) -> str:
    compact = " ".join(message.split())[:300]
    if not compact or re.search(
        r"(?i)(api[_-]?key\s*=|bearer\s+|password\s*=|secret\s*=|[a-z]:\\|/(?:tmp|home|var|users)/)",
        compact,
    ):
        return "Sensitive diagnostic details were removed."
    return compact


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

    def contribution_map(self, project_id: str) -> SourceContributionMap: ...


class MotionDirector(Protocol):
    model_name: str
    agent_name: str

    def direct(
        self,
        request: MotionDirectionRequest,
        context: dict[str, object],
        *,
        retry_count: int = 0,
    ) -> tuple[ADKMotionRun, MotionDirectionPlan]: ...

    def plan(self, project_id: str, job_id: str) -> MotionDirectionPlan: ...

    def run(self, project_id: str, job_id: str) -> ADKMotionRun: ...


class AttentionDirectorProtocol(Protocol):
    model_name: str
    agent_name: str

    def direct(
        self,
        request: AttentionRequest,
        targets: list[TargetObservation],
        context: dict[str, object],
    ) -> tuple[AttentionRunStep, AttentionPlan]: ...


class StyleDirectorProtocol(Protocol):
    model_name: str
    agent_name: str

    def direct(
        self,
        request: StyleDirectionRequest,
        context: dict[str, object],
    ) -> tuple[StyleRunStep, StyleDirectionPlan]: ...


class LongFormDirectorProtocol(Protocol):
    model_name: str
    agent_name: str

    def direct(
        self,
        request: LongFormDirectionRequest,
        context: dict[str, object],
    ) -> tuple[LongFormADKRun, LongFormVideoPlan]: ...

    def plan(self, project_id: str, plan_id: str) -> LongFormVideoPlan: ...

    def checkpoints(
        self, project_id: str, plan_id: str
    ) -> list[ChapterCheckpoint]: ...

    def retry_chapter(
        self, project_id: str, plan_id: str, chapter_id: str
    ) -> ChapterCheckpoint: ...

    def record_chapter_result(
        self,
        project_id: str,
        plan_id: str,
        chapter_id: str,
        *,
        artifact_ref: str | None,
        artifact_sha256: str | None,
        elapsed_ms: int,
    ) -> ChapterCheckpoint: ...


class GenerationStages:
    def __init__(
        self,
        service: DemoGenerationService,
        records: RecordStore,
        vault: CaptureTokenVault,
        approval: StoryboardApproval | None = None,
        motion_director: MotionDirector | None = None,
        attention_director: AttentionDirectorProtocol | None = None,
        style_director: StyleDirectorProtocol | None = None,
        longform_director: LongFormDirectorProtocol | None = None,
    ) -> None:
        self.service = service
        self.records = records
        self.vault = vault
        self.approval = approval
        self.motion_director = motion_director
        self.attention_director = attention_director
        self.style_director = style_director
        self.longform_director = longform_director

    def _context(self, job: GenerationJob) -> dict[str, Any]:
        result = self.records.get(f"job-input-{job.id}")
        if result is None:
            raise JobConflict("Generation input is missing")
        return result[1]

    def execute(self, job: GenerationJob) -> dict[str, Any]:
        s = self.service
        monitor = JobMonitor(self.records, s.projects)
        context = self._context(job)
        project = Project.model_validate(context["project"])
        token = (
            self.vault.decrypt(context["capture_token"])
            if (
                job.stage in {"inspection", "capture"}
                or (
                    job.stage == "narration"
                    and project.requested_duration_seconds == 180
                )
            )
            and context.get("capture_token")
            else None
        )
        if job.stage == "inspection":
            inspection = s.inspector.inspect(
                project_id=project.id, website_url=str(project.website_url), session_token=token
            )
            if not inspection.pages:
                raise JobConflict("No usable website pages")
            s.inspections.save(inspection)
            monitor.event(job, f"Inspected {len(inspection.pages)} website pages; structure saved.")
            s.research_sources.replace_website_sources(
                project.id, website_sources(project.id, inspection)
            )
            return {"warning": inspection.warning}
        if job.stage == "research":
            result = s.research.analyze(project)
            sources = s.research_sources.list_for_project(project.id)
            count = sum(source.source_type == "partner_search" for source in sources)
            monitor.event(job, f"Research finished: {count} saved Parallel sources.")
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
            try:
                storyboard_result = s.storyboard_generator.generate(
                    project=project,
                    understanding=understanding,
                    sources=s.research_sources.list_for_project(project.id),
                )
            except StoryboardValidationError as error:
                if error.candidate is not None:
                    # Diagnostics are never treated as approved execution checkpoints.
                    key = f"job-invalid-storyboard-{job.id}-{job.attempts}"
                    current = self.records.get(key)
                    self.records.put(key, current[0] if current else 0, {
                        "code": error.code,
                        "candidate": error.candidate.model_dump(mode="json"),
                    })
                raise
            s.storyboards.save(storyboard_result)
            monitor.event(job, f"Validated and saved {len(storyboard_result.scenes)} scenes.")
            return {"storyboard": storyboard_result.model_dump(mode="json")}
        board = s.storyboards.get_latest(project.id)
        evidence_map: SourceContributionMap | None = None
        if job.stage in {"motion", "capture"} and self.approval is not None:
            board, project = self.approval.approved_inputs(project.id)
            evidence_map = self.approval.contribution_map(project.id)
        if board is None:
            raise JobConflict("Storyboard is missing")
        scenes = sorted(board.scenes, key=lambda scene: scene.order)
        durations = allocate_scene_durations(scenes, project.requested_duration_seconds * 1000)
        if job.stage == "motion":
            if self.motion_director is None:
                raise JobConflict("Google ADK motion direction is unavailable")
            sources = s.research_sources.list_for_project(project.id)
            fingerprint = (
                evidence_map.fingerprint
                if evidence_map is not None
                else _motion_input_fingerprint(project, board, sources)
            )
            request = MotionDirectionRequest(
                project_id=project.id,
                job_id=job.id,
                storyboard_id=board.id,
                storyboard_version=board.version,
                duration_ms=sum(durations),
                evidence_fingerprint=fingerprint,
                source_ids=[source.id for source in sorted(sources, key=lambda item: item.id)],
                scene_ids=[scene.id for scene in scenes],
                product_clip_refs=[f"scene:{scene.id}" for scene in scenes],
                created_at=job.updated_at,
            )
            run, plan = self.motion_director.direct(
                request,
                {
                    "project": project.model_dump(mode="json"),
                    "storyboard": board.model_dump(mode="json"),
                    "evidence": (
                        evidence_map.model_dump(mode="json")
                        if evidence_map is not None
                        else {"fingerprint": fingerprint, "status": "legacy_context"}
                    ),
                    "sources": [source.model_dump(mode="json") for source in sources],
                    "motion_catalog": {
                        "primitives": [
                            "fade_slide",
                            "scale_settle",
                            "stagger_text",
                            "highlight_reveal",
                            "browser_frame_move",
                            "background_dim",
                        ],
                        "layers": [
                            "background",
                            "product",
                            "mask",
                            "cursor",
                            "callout",
                            "captions",
                            "transition",
                        ],
                        "easing": ["linear", "standard", "emphasized"],
                        "editorial_templates": [
                            "hook",
                            "framed_product",
                            "feature_callout",
                            "split_explanation",
                            "proof_safety",
                            "closing",
                        ],
                        "scene_timing": [
                            {
                                "scene_id": scene.id,
                                "product_clip_ref": f"scene:{scene.id}",
                                "start_ms": sum(durations[:index]),
                                "end_ms": sum(durations[: index + 1]),
                            }
                            for index, scene in enumerate(scenes)
                        ],
                    },
                },
                retry_count=max(0, job.attempts - 1),
            )
            return {
                "adk_motion_run": run.model_dump(mode="json"),
                "motion_plan": plan.model_dump(mode="json"),
            }
        if job.stage == "capture":
            capture_durations = (
                allocate_scene_durations(scenes, 45_000)
                if project.requested_duration_seconds == 180
                else durations
            )
            scene = prepare_continuous_capture(scenes, capture_durations)
            monitor.event(
                job, f"Recording continuous browser footage for {sum(capture_durations) // 1000} "
                "seconds, including cursor movement and click indicators.",
            )
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
            monitor.event(
                job, f"Recorded {capture.duration_ms // 1000} seconds and "
                f"{len(capture.interaction_events)} browser interaction events; saving footage.",
            )
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
        if job.stage == "attention":
            if self.attention_director is None:
                raise JobConflict("Google ADK attention direction is unavailable")
            capture = SceneCaptureResult.model_validate(capture_checkpoint[1]["capture"])
            motion_checkpoint = self.records.get(f"job-stage-{job.id}-motion")
            if motion_checkpoint is None:
                raise JobConflict("Motion direction checkpoint is missing")
            motion_plan = MotionDirectionPlan.model_validate(motion_checkpoint[1]["motion_plan"])
            targets: list[TargetObservation] = []
            for index, event in enumerate(capture.interaction_events):
                if event.x is None or event.y is None:
                    continue
                viewport = event.viewport
                box = event.bounding_box
                x = box.x if box is not None else max(0, event.x - 20)
                y = box.y if box is not None else max(0, event.y - 20)
                width = box.width if box is not None else 40
                height = box.height if box is not None else 40
                normalized_x = min(x / viewport.width, 0.98)
                normalized_y = min(y / viewport.height, 0.98)
                normalized = NormalizedRect(
                    x=normalized_x,
                    y=normalized_y,
                    width=min(max(width / viewport.width, 0.005), 1 - normalized_x),
                    height=min(max(height / viewport.height, 0.005), 1 - normalized_y),
                )
                targets.append(
                    TargetObservation(
                        id=f"target-{index + 1}",
                        scene_id=event.scene_id or scenes[0].id,
                        locator_fingerprint=hashlib.sha256(
                            (event.locator or f"point:{event.x}:{event.y}").encode()
                        ).hexdigest(),
                        timestamp_ms=event.timestamp_ms,
                        rect=normalized,
                        viewport=viewport,
                    )
                )
            statements = [f"{scene.id}-statement-1" for scene in scenes]
            attention_request = AttentionRequest(
                project_id=project.id,
                job_id=job.id,
                parent_run_id=motion_plan.run_id,
                duration_ms=sum(durations),
                target_ids=[target.id for target in targets],
                narration_statement_ids=statements,
                created_at=job.updated_at,
            )
            attention_run, attention_plan = self.attention_director.direct(
                attention_request,
                targets,
                {
                    "targets": [target.model_dump(mode="json") for target in targets],
                    "narration": [
                        {
                            "statement_id": statement_id,
                            "text": scene.narration,
                            "scene_id": scene.id,
                        }
                        for statement_id, scene in zip(statements, scenes, strict=True)
                    ],
                    "camera_intervals": [
                        {"start_ms": event.timestamp_ms, "target_id": f"target-{index + 1}"}
                        for index, event in enumerate(capture.interaction_events)
                        if event.x is not None and event.y is not None
                    ],
                    "callout_catalog": [
                        "label_connector",
                        "spotlight",
                        "numbered_step",
                        "feature_card",
                        "status_badge",
                        "metric_card",
                        "before_after",
                    ],
                    "placements": [
                        "top_left",
                        "top_right",
                        "bottom_left",
                        "bottom_right",
                    ],
                },
            )
            return {
                "attention_run": attention_run.model_dump(mode="json"),
                "attention_plan": attention_plan.model_dump(mode="json"),
            }
        if job.stage == "style":
            if self.style_director is None:
                raise JobConflict("Google ADK style direction is unavailable")
            motion_checkpoint = self.records.get(f"job-stage-{job.id}-motion")
            attention_checkpoint = self.records.get(f"job-stage-{job.id}-attention")
            if motion_checkpoint is None or attention_checkpoint is None:
                raise JobConflict("Style direction inputs are missing")
            motion_plan = MotionDirectionPlan.model_validate(motion_checkpoint[1]["motion_plan"])
            attention_plan = AttentionPlan.model_validate(attention_checkpoint[1]["attention_plan"])
            if attention_plan.parent_run_id != motion_plan.run_id:
                raise JobConflict("Style inputs do not share the approved ADK workflow")
            sources = s.research_sources.list_for_project(project.id)
            evidence_refs = [
                f"storyboard:{board.id}:{board.version}",
                f"attention:{attention_plan.id}",
                *[f"source:{source.id}" for source in sorted(sources, key=lambda item: item.id)],
            ]
            style_request = StyleDirectionRequest(
                project_id=project.id,
                job_id=job.id,
                parent_run_id=motion_plan.run_id,
                audience=project.audience,
                purpose=project.product_summary,
                scene_ids=[scene.id for scene in scenes],
                evidence_refs=evidence_refs,
                created_at=job.updated_at,
            )
            style_run, style_plan = self.style_director.direct(
                style_request,
                {
                    "audience": project.audience,
                    "purpose": project.product_summary,
                    "approved_storyboard": board.model_dump(mode="json"),
                    "template_coverage": (
                        motion_plan.editorial_plan.model_dump(mode="json")
                        if motion_plan.editorial_plan is not None
                        else None
                    ),
                    "variants": [
                        "editorial_story",
                        "product_spotlight",
                        "technical_proof",
                    ],
                    "evidence_refs": evidence_refs,
                },
            )
            style_result = {
                "style_run": style_run.model_dump(mode="json"),
                "style_plan": style_plan.model_dump(mode="json"),
            }
            if project.requested_duration_seconds == 180:
                if self.longform_director is None:
                    raise JobConflict("Google ADK long-form direction is unavailable")
                parallel_refs = [
                    f"source:{source.id}"
                    for source in sorted(sources, key=lambda item: item.id)
                    if source.source_type == "partner_search"
                ]
                run_id = str(uuid4())
                plan_id = str(uuid4())
                longform_request = LongFormDirectionRequest(
                    plan_id=plan_id,
                    run_id=run_id,
                    project_id=project.id,
                    job_id=job.id,
                    parent_motion_run_id=motion_plan.run_id,
                    visual_variant=style_plan.decision.selected_variant,
                    research_status="complete" if parallel_refs else "degraded",
                    evidence_refs=evidence_refs,
                    parallel_source_refs=parallel_refs,
                    product_clip_refs=motion_plan.product_clip_refs,
                    target_ids=[target.id for target in attention_plan.targets],
                    created_at=job.updated_at,
                )
                longform_run, generated_longform_plan = self.longform_director.direct(
                    longform_request,
                    {
                        "project": project.model_dump(mode="json"),
                        "approved_storyboard": board.model_dump(mode="json"),
                        "saved_sources": [
                            source.model_dump(mode="json") for source in sources
                        ],
                        "direct_parallel_source_refs": parallel_refs,
                        "motion_plan": motion_plan.model_dump(mode="json"),
                        "attention_plan": attention_plan.model_dump(mode="json"),
                        "style_plan": style_plan.model_dump(mode="json"),
                    },
                )
                style_result["longform_run"] = longform_run.model_dump(mode="json")
                style_result["longform_plan"] = generated_longform_plan.model_dump(
                    mode="json"
                )
            return style_result
        if job.stage == "narration":
            media = s.timeline_media_store.materialize(
                Timeline.model_validate(capture_checkpoint[1]["media"])
            )
            capture = SceneCaptureResult.model_validate(capture_checkpoint[1]["capture"])
            capture = capture.model_copy(update={"raw_clip_path": media.scene_clips[0].source_uri})
            narration_scenes = scenes
            longform_plan: LongFormVideoPlan | None = None
            chapter_results: list[SceneCaptureResult] = []
            style_checkpoint = self.records.get(f"job-stage-{job.id}-style")
            if project.requested_duration_seconds == 180:
                if style_checkpoint is None or "longform_plan" not in style_checkpoint[1]:
                    raise JobConflict("Long-form direction checkpoint is missing")
                longform_plan = LongFormVideoPlan.model_validate(
                    style_checkpoint[1]["longform_plan"]
                )
                if longform_plan.project_id != project.id:
                    raise JobConflict("Long-form direction does not match the project")
                narration_scenes = [
                    scenes[index % len(scenes)].model_copy(update={
                        "id": section.id,
                        "order": index,
                        "title": section.id.replace("_", " ").title(),
                        "objective": f"Direct the {section.id.replace('_', ' ')} section.",
                        "narration": section.narration,
                        "duration_seconds": (section.end_ms - section.start_ms) / 1_000,
                    })
                    for index, section in enumerate(longform_plan.sections)
                ]
                durations = [
                    section.end_ms - section.start_ms
                    for section in longform_plan.sections
                ]
                if self.longform_director is None:
                    raise JobConflict("Long-form chapter capture is unavailable")
                checkpoints = {
                    item.chapter_id: item
                    for item in self.longform_director.checkpoints(
                        project.id, longform_plan.id
                    )
                }
                for chapter in longform_plan.chapters:
                    chapter_checkpoint = checkpoints[chapter.id]
                    result_key = f"longform-chapter-result-{longform_plan.id}-{chapter.id}"
                    saved_result = self.records.get(result_key)
                    if (
                        chapter_checkpoint.status in {"captured", "approved"}
                        and saved_result
                    ):
                        chapter_results.append(
                            SceneCaptureResult.model_validate(saved_result[1])
                        )
                        continue
                    if chapter_checkpoint.status == "failed":
                        chapter_checkpoint = self.longform_director.retry_chapter(
                            project.id, longform_plan.id, chapter.id
                        )
                    chapter_scene = _prepare_chapter_capture(board, scenes, chapter)
                    chapter_capture = s.capture_worker.capture_scene(
                        chapter_scene, session_token=token
                    )
                    succeeded = (
                        chapter_capture.status == "succeeded"
                        and chapter_capture.raw_clip_path is not None
                        and Path(chapter_capture.raw_clip_path).is_file()
                    )
                    self.longform_director.record_chapter_result(
                        project.id,
                        longform_plan.id,
                        chapter.id,
                        artifact_ref=(
                            chapter_capture.raw_clip_path if succeeded else None
                        ),
                        artifact_sha256=(
                            _media_sha256(chapter_capture.raw_clip_path)
                            if succeeded and chapter_capture.raw_clip_path
                            else None
                        ),
                        elapsed_ms=sum(
                            item.elapsed_ms for item in chapter_capture.action_results
                        ),
                    )
                    if not succeeded:
                        raise JobConflict(
                            "Capture chapter "
                            f"{chapter.order + 1} failed; earlier chapters are saved"
                        )
                    self.records.put(
                        result_key, 0, chapter_capture.model_dump(mode="json")
                    )
                    chapter_results.append(chapter_capture)
                merged_events: list[InteractionEvent] = []
                for chapter, chapter_capture in zip(
                    longform_plan.chapters, chapter_results, strict=True
                ):
                    merged_events.extend(
                        event.model_copy(update={
                            "timestamp_ms": min(
                                chapter.end_ms,
                                chapter.start_ms + event.timestamp_ms,
                            )
                        })
                        for event in chapter_capture.interaction_events
                    )
                capture = capture.model_copy(update={
                    "duration_ms": 180_000,
                    "interaction_events": merged_events,
                })
            monitor.event(
                job, f"Gemini TTS is generating {len(narration_scenes)} narration segments."
            )
            narration = s.narration.generate(
                narration_scenes,
                s.voice,
                capture_clip_paths=[media.scene_clips[0].source_uri],
            )
            if (
                narration.status != "succeeded"
                or len(narration.segments) != len(narration_scenes)
            ):
                raise JobConflict("Narration did not produce every scene")
            monitor.event(job, f"Saved {len(narration.segments)} narration segments.")
            motion_checkpoint = self.records.get(f"job-stage-{job.id}-motion")
            if motion_checkpoint is None:
                raise JobConflict("Motion direction checkpoint is missing")
            motion_plan = MotionDirectionPlan.model_validate(motion_checkpoint[1]["motion_plan"])
            if motion_plan.project_id != project.id or motion_plan.duration_ms != sum(durations):
                raise JobConflict("Motion direction does not match the approved project")
            attention_checkpoint = self.records.get(f"job-stage-{job.id}-attention")
            if attention_checkpoint is None:
                raise JobConflict("Attention direction checkpoint is missing")
            attention_plan = AttentionPlan.model_validate(attention_checkpoint[1]["attention_plan"])
            if (
                attention_plan.project_id != project.id
                or attention_plan.parent_run_id != motion_plan.run_id
            ):
                raise JobConflict("Attention direction does not match the motion workflow")
            if style_checkpoint is None:
                raise JobConflict("Style direction checkpoint is missing")
            style_plan = StyleDirectionPlan.model_validate(style_checkpoint[1]["style_plan"])
            if (
                style_plan.project_id != project.id
                or style_plan.parent_run_id != motion_plan.run_id
                or style_plan.scene_ids != [scene.id for scene in scenes]
            ):
                raise JobConflict("Style direction does not match the approved narrative")
            timeline = assemble_timeline(
                project,
                narration_scenes,
                durations,
                capture,
                narration,
                s.caption_style,
                s.captions,
                s.camera,
                motion_plan_id=motion_plan.id,
                motion_design_version=motion_plan.design_tokens.version,
                attention_plan_id=attention_plan.id,
                attention_design_version="attention-v1",
                style_plan_id=style_plan.id,
                style_design_version=style_plan.version,
                visual_variant=style_plan.decision.selected_variant,
                long_form_plan_id=longform_plan.id if longform_plan else None,
                long_form_version=longform_plan.version if longform_plan else None,
            )
            if longform_plan is not None:
                timeline = timeline.model_copy(update={
                    "scene_clips": [
                        SceneClip(
                            id=f"scene-clip-{chapter.id}",
                            scene_id=chapter.id,
                            start_ms=chapter.start_ms,
                            end_ms=chapter.end_ms,
                            source_uri=chapter_capture.raw_clip_path or "missing",
                        )
                        for chapter, chapter_capture in zip(
                            longform_plan.chapters, chapter_results, strict=True
                        )
                    ]
                })
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
        trace_services: dict[TraceStageKind, str] | None = None,
    ) -> None:
        self.records = records
        self.executor = executor
        self.dispatcher = dispatcher
        self.generation = generation
        self.vault = vault
        self.trace_services = trace_services or self._runtime_services()
        self.monitor = JobMonitor(records, generation.projects)

    def _runtime_services(self) -> dict[TraceStageKind, str]:
        ai = getattr(self.generation.understanding_generator, "ai_service", None)
        ai_provider = str(getattr(ai, "provider", "google")).title()
        if ai_provider.casefold() == "google":
            ai_provider = "Google Gemini"
        ai_model = str(getattr(ai, "model_name", "Gemini"))
        search = getattr(self.generation.research, "search", None)
        search_mode = getattr(search, "mode", None)
        tts = getattr(getattr(self.generation.narration, "adapter", None), "model_name", None)
        motion_director = getattr(self.executor, "motion_director", None)
        adk_model = getattr(motion_director, "model_name", None)
        return {
            "inspection": "Playwright",
            "research": f"Parallel Search{f' · {search_mode}' if search_mode else ''}",
            "adk_coordination": f"Google ADK{f' · {adk_model}' if adk_model else ''}",
            "understanding": f"{ai_provider} · {ai_model}",
            "storyboard": f"{ai_provider} · {ai_model}",
            "capture": "Playwright",
            "narration": f"Gemini TTS{f' · {tts}' if tts else ''}",
            "auto_camera": "Auto Camera",
            "captions": "Caption engine",
            "render": "FFmpeg",
        }

    def _trace_key(self, job_id: str) -> str:
        return f"generation-trace-{job_id}"

    def _initial_trace(self, job: GenerationJob) -> GenerationTrace:
        stages = []
        for index, kind in enumerate(TRACE_ORDER):
            stages.append(
                GenerationTraceStage(
                    id=f"{kind}:0",
                    project_id=job.project_id,
                    kind=kind,
                    sequence=(index + 1) * 10,
                    attempt=0,
                    retry_count=0,
                    status="pending",
                    label=TRACE_LABELS[kind],
                    service=self.trace_services[kind],
                    message="Waiting for the previous saved stage.",
                    contributions=[],
                )
            )
        return GenerationTrace(
            id=f"trace-{job.id}",
            project_id=job.project_id,
            job_id=job.id,
            status="running",
            created_at=job.created_at,
            updated_at=job.updated_at,
            stages=stages,
        )

    def _load_trace(self, job: GenerationJob) -> tuple[int, GenerationTrace]:
        saved = self.records.get(self._trace_key(job.id))
        if saved is None:
            trace = self._initial_trace(job)
            version = self.records.put(self._trace_key(job.id), 0, trace.model_dump(mode="json"))
            return version, trace
        return saved[0], GenerationTrace.model_validate(saved[1])

    def _save_trace(self, version: int, trace: GenerationTrace, **updates: Any) -> GenerationTrace:
        updated = GenerationTrace.model_validate(
            {**trace.model_dump(), **updates, "updated_at": datetime.now(UTC)}
        )
        self.records.put(self._trace_key(trace.job_id), version, updated.model_dump(mode="json"))
        return updated

    def _start_trace_attempt(self, job: GenerationJob, started_at: datetime) -> None:
        if job.stage == "done":
            return
        kind = _trace_kind(job.stage)
        version, trace = self._load_trace(job)
        stages = list(trace.stages)
        replacement = GenerationTraceStage(
            id=_trace_attempt_id(job.stage, job.attempts),
            project_id=job.project_id,
            kind=kind,
            sequence=(TRACE_ORDER.index(kind) + 1) * 10 + job.attempts,
            attempt=job.attempts,
            retry_count=max(0, job.attempts - 1),
            status="running",
            label=_trace_label(job.stage),
            service=self.trace_services[kind],
            started_at=started_at,
            message=f"{_trace_label(job.stage)} started.",
        )
        existing = next((stage for stage in stages if stage.id == replacement.id), None)
        if existing is not None:
            return
        placeholder = next(
            (
                index
                for index, stage in enumerate(stages)
                if stage.kind == kind and stage.status == "pending"
            ),
            None,
        )
        if placeholder is None:
            insertion = max(index for index, stage in enumerate(stages) if stage.kind == kind) + 1
            stages.insert(insertion, replacement)
        else:
            stages[placeholder] = replacement
        stages.sort(key=lambda item: item.sequence)
        self._save_trace(version, trace, status="running", stages=stages)

    def _finish_trace_attempt(
        self,
        job: GenerationJob,
        *,
        succeeded: bool,
        result: dict[str, Any] | None = None,
        terminal: bool = False,
    ) -> None:
        if job.stage == "done":
            return
        kind = _trace_kind(job.stage)
        version, trace = self._load_trace(job)
        completed_at = datetime.now(UTC)
        stages = list(trace.stages)
        attempt_id = _trace_attempt_id(job.stage, job.attempts)
        position = next(
            (index for index, stage in enumerate(stages) if stage.id == attempt_id), None
        )
        if position is None:
            self._start_trace_attempt(job, job.updated_at)
            version, trace = self._load_trace(job)
            stages = list(trace.stages)
            position = next(index for index, stage in enumerate(stages) if stage.id == attempt_id)
        running = stages[position]
        if succeeded and running.status == "succeeded":
            return
        assert running.started_at is not None
        elapsed = max(0, round((completed_at - running.started_at).total_seconds() * 1000))
        contributions, output_href, related = (
            self._stage_output(job, result or {}) if succeeded else ([], None, {})
        )
        message = (
            self._success_message(kind, contributions)
            if succeeded
            else f"{_trace_label(job.stage)} failed. Saved checkpoints are unchanged."
        )
        stages[position] = running.model_copy(
            update={
                "status": "succeeded" if succeeded else "failed",
                "completed_at": completed_at,
                "elapsed_ms": elapsed,
                "message": sanitize_trace_message(message),
                "contributions": contributions if succeeded else [],
                "output_href": output_href if succeeded else None,
            }
        )
        if succeeded:
            for kind, sub_contributions in related.items():
                sub_position = next(
                    index for index, stage in enumerate(stages) if stage.kind == kind
                )
                pending = stages[sub_position]
                stages[sub_position] = pending.model_copy(
                    update={
                        "id": f"{kind}:{job.attempts}",
                        "attempt": job.attempts,
                        "retry_count": max(0, job.attempts - 1),
                        "status": "succeeded",
                        "started_at": running.started_at,
                        "completed_at": completed_at,
                        "elapsed_ms": elapsed,
                        "message": self._success_message(kind, sub_contributions),
                        "contributions": sub_contributions,
                        "output_href": f"/projects/{job.project_id}/editor",
                    }
                )
        trace_status = "running" if succeeded else "failed" if terminal else "awaiting_retry"
        if succeeded and job.stage == "render":
            trace_status = "succeeded"
        self._save_trace(version, trace, status=trace_status, stages=stages)

    def _reset_trace_attempt_for_approval(self, job: GenerationJob) -> None:
        kind = _trace_kind(job.stage)
        version, trace = self._load_trace(job)
        stages = list(trace.stages)
        position = next(
            index
            for index, stage in enumerate(stages)
            if stage.id == _trace_attempt_id(job.stage, job.attempts)
        )
        stages[position] = GenerationTraceStage(
            id=_trace_attempt_id(job.stage, 0),
            project_id=job.project_id,
            kind=kind,
            sequence=(TRACE_ORDER.index(kind) + 1) * 10,
            attempt=0,
            retry_count=0,
            status="pending",
            label=_trace_label(job.stage),
            service=self.trace_services[kind],
            message="Waiting for approved storyboard evidence.",
        )
        self._save_trace(version, trace, status="awaiting_approval", stages=stages)

    def _stage_output(
        self, job: GenerationJob, result: dict[str, Any]
    ) -> tuple[
        list[StageContribution],
        str | None,
        dict[TraceStageKind, list[StageContribution]],
    ]:
        project_id = job.project_id
        link = f"/projects/{project_id}/editor"
        related: dict[TraceStageKind, list[StageContribution]] = {}
        if job.stage == "inspection":
            inspection = self.generation.inspections.get(project_id)
            parsed = WebsiteInspection.model_validate(inspection)
            return (
                [
                    StageContribution(
                        key="pages_inspected",
                        label="Pages inspected",
                        value=len(parsed.pages),
                        unit="pages",
                    ),
                    StageContribution(
                        key="controls_observed",
                        label="Controls observed",
                        value=sum(len(page.elements) for page in parsed.pages),
                        unit="controls",
                    ),
                ],
                f"{link}#source-group-website_inspection",
                related,
            )
        if job.stage == "style":
            style_run = StyleRunStep.model_validate(result["style_run"])
            StyleDirectionPlan.model_validate(result["style_plan"])
            longform_run = (
                LongFormADKRun.model_validate(result["longform_run"])
                if "longform_run" in result
                else None
            )
            longform_plan = (
                LongFormVideoPlan.model_validate(result["longform_plan"])
                if "longform_plan" in result
                else None
            )
            workflow_runs = style_run.workflow_runs + (
                longform_run.workflow_runs if longform_run else 0
            )
            contributions = [
                StageContribution(
                    key="workflow_runs",
                    label="ADK workflow runs",
                    value=workflow_runs,
                    unit="runs",
                ),
                StageContribution(
                    key="style_recommendations",
                    label="Validated style recommendations",
                    value=1,
                    unit="recommendations",
                ),
                StageContribution(
                    key="style_overrides",
                    label="User overrides",
                    value=0,
                    unit="overrides",
                ),
            ]
            if longform_plan is not None and longform_run is not None:
                contributions.extend([
                    StageContribution(
                        key="longform_plans",
                        label="Validated three-minute plans",
                        value=1,
                        unit="plans",
                    ),
                    StageContribution(
                        key="director_steps",
                        label="Completed ADK director steps",
                        value=len(longform_run.step_ids),
                        unit="steps",
                    ),
                    StageContribution(
                        key="parallel_sources_linked",
                        label="Direct Parallel sources linked",
                        value=len(longform_plan.parallel_source_refs),
                        unit="sources",
                    ),
                    StageContribution(
                        key="chapters_planned",
                        label="Restartable capture chapters",
                        value=len(longform_plan.chapters),
                        unit="chapters",
                    ),
                ])
            return (
                contributions,
                f"{link}#style-direction",
                related,
            )
        if job.stage == "attention":
            attention_run = AttentionRunStep.model_validate(result["attention_run"])
            attention_plan = AttentionPlan.model_validate(result["attention_plan"])
            return (
                [
                    StageContribution(
                        key="workflow_runs",
                        label="ADK workflow runs",
                        value=attention_run.workflow_runs,
                        unit="runs",
                    ),
                    StageContribution(
                        key="attention_targets",
                        label="Observed targets",
                        value=attention_run.input_target_count,
                        unit="targets",
                    ),
                    StageContribution(
                        key="callouts_proposed",
                        label="Callouts proposed",
                        value=attention_run.proposed_cue_count,
                        unit="callouts",
                    ),
                    StageContribution(
                        key="callouts_accepted",
                        label="Callouts accepted",
                        value=len(attention_plan.callouts),
                        unit="callouts",
                    ),
                ],
                f"{link}#attention-direction",
                related,
            )
        if job.stage == "research":
            count = sum(
                source.source_type == "partner_search"
                for source in self.generation.research_sources.list_for_project(project_id)
            )
            return (
                [
                    StageContribution(
                        key="sources_saved", label="Sources saved", value=count, unit="sources"
                    )
                ],
                f"{link}#source-group-parallel_search",
                related,
            )
        if job.stage == "understanding":
            understanding = self.generation.understandings.get(project_id)
            parsed_understanding = ProductUnderstanding.model_validate(understanding)
            return (
                [
                    StageContribution(
                        key="features_understood",
                        label="Features understood",
                        value=len(parsed_understanding.features),
                        unit="features",
                    ),
                    StageContribution(
                        key="claims_attributed",
                        label="Claims attributed",
                        value=len(parsed_understanding.claims),
                        unit="statements",
                    ),
                ],
                None,
                related,
            )
        if job.stage == "storyboard":
            board = Storyboard.model_validate(result["storyboard"])
            return (
                [
                    StageContribution(
                        key="scenes_planned",
                        label="Scenes planned",
                        value=len(board.scenes),
                        unit="scenes",
                    ),
                    StageContribution(
                        key="actions_planned",
                        label="Actions planned",
                        value=sum(len(scene.capture_plan.actions) for scene in board.scenes),
                        unit="actions",
                    ),
                ],
                f"/projects/{project_id}/storyboard",
                related,
            )
        if job.stage == "motion":
            motion_run = ADKMotionRun.model_validate(result["adk_motion_run"])
            motion_plan = MotionDirectionPlan.model_validate(result["motion_plan"])
            editorial = motion_plan.editorial_plan
            return (
                [
                    StageContribution(
                        key="workflow_runs",
                        label="ADK workflow runs",
                        value=motion_run.workflow_runs,
                        unit="runs",
                    ),
                    StageContribution(
                        key="validated_motion_plans",
                        label="Validated motion plans",
                        value=1,
                        unit="plans",
                    ),
                    StageContribution(
                        key="motion_cues",
                        label="Motion cues",
                        value=len(motion_plan.cues),
                        unit="cues",
                    ),
                    StageContribution(
                        key="templates_assigned",
                        label="Product-present templates",
                        value=len(editorial.scenes) if editorial is not None else 0,
                        unit="scenes",
                    ),
                    StageContribution(
                        key="product_presence",
                        label="Product footage visible",
                        value=(round(editorial.product_presence().percentage) if editorial else 0),
                        unit="percent",
                    ),
                ],
                f"{link}#motion-direction",
                related,
            )
        if job.stage == "capture":
            capture = SceneCaptureResult.model_validate(result["capture"])
            return (
                [
                    StageContribution(
                        key="actions_executed",
                        label="Actions executed",
                        value=sum(item.status == "succeeded" for item in capture.action_results),
                        unit="actions",
                    ),
                    StageContribution(
                        key="interactions_recorded",
                        label="Interactions recorded",
                        value=len(capture.interaction_events),
                        unit="interactions",
                    ),
                    StageContribution(
                        key="recordings_created",
                        label="Continuous recordings",
                        value=1 if capture.raw_clip_path else 0,
                        unit="recordings",
                    ),
                ],
                f"{link}#editor-preview",
                related,
            )
        if job.stage == "narration":
            timeline = Timeline.model_validate(result["timeline"])
            related = {
                "auto_camera": [
                    StageContribution(
                        key="zooms_created",
                        label="Camera moves",
                        value=len(timeline.zoom_clips),
                        unit="zooms",
                    )
                ],
                "captions": [
                    StageContribution(
                        key="captions_created",
                        label="Caption clips",
                        value=len(timeline.caption_clips),
                        unit="captions",
                    )
                ],
            }
            return (
                [
                    StageContribution(
                        key="narration_segments",
                        label="Narration segments",
                        value=len(timeline.audio_clips),
                        unit="segments",
                    )
                ],
                link,
                related,
            )
        if job.stage == "render":
            export = self.generation.exports.get(project_id, str(result.get("export_id", "")))
            if export is None:
                return (
                    [
                        StageContribution(
                            key="exports_created", label="Exports created", value=0, unit="exports"
                        )
                    ],
                    None,
                    related,
                )
            contributions = [
                    StageContribution(
                        key="exports_created", label="Exports created", value=1, unit="exports"
                    ),
                    StageContribution(
                        key="output_width", label="Output width", value=export.width, unit="pixels"
                    ),
                    StageContribution(
                        key="output_height",
                        label="Output height",
                        value=export.height,
                        unit="pixels",
                    ),
                    StageContribution(
                        key="output_duration",
                        label="Output duration",
                        value=export.duration_ms,
                        unit="milliseconds",
                    ),
                ]
            timeline_state = self.generation.timelines.current(project_id)
            current_timeline = (
                timeline_state.current.timeline if timeline_state is not None else None
            )
            if (
                current_timeline is not None
                and current_timeline.long_form_plan_id is not None
                and export.duration_ms == 180_000
                and (export.width, export.height) == (2560, 1440)
            ):
                contributions.append(StageContribution(
                    key="adk_plan_consumed",
                    label="Validated ADK plan consumed by export",
                    value=1,
                    unit="plans",
                ))
            return (
                contributions,
                f"{link}#editor-preview",
                related,
            )
        return [], None, related

    @staticmethod
    def _success_message(kind: TraceStageKind, contributions: list[StageContribution]) -> str:
        if not contributions:
            return f"{TRACE_LABELS[kind]} completed with no saved output."
        primary = contributions[0]
        if primary.value == 0:
            return f"{TRACE_LABELS[kind]} completed; no {primary.unit} were saved."
        return f"{TRACE_LABELS[kind]} completed and saved {primary.value} {primary.unit}."

    def trace(self, project_id: str) -> GenerationTrace:
        job = self.latest(project_id)
        if job is None:
            raise KeyError("Generation trace not found")
        saved = self.records.get(self._trace_key(job.id))
        if saved is None:
            raise KeyError("Generation trace not found")
        trace = GenerationTrace.model_validate(saved[1])
        if trace.project_id != project_id or trace.job_id != job.id:
            raise KeyError("Generation trace not found")
        return trace

    def motion_plan(self, project_id: str) -> MotionDirectionPlan:
        job = self.latest(project_id)
        director = getattr(self.executor, "motion_director", None)
        if job is None or director is None:
            raise KeyError("Motion direction plan not found")
        return cast(MotionDirector, director).plan(project_id, job.id)

    def motion_run(self, project_id: str) -> ADKMotionRun:
        job = self.latest(project_id)
        director = getattr(self.executor, "motion_director", None)
        if job is None or director is None:
            raise KeyError("ADK motion run not found")
        return cast(MotionDirector, director).run(project_id, job.id)

    def attention_plan(self, project_id: str) -> AttentionPlan:
        job = self.latest(project_id)
        if job is None:
            raise KeyError("Attention plan not found")
        timeline_state = self.generation.timelines.current(project_id)
        if timeline_state is not None:
            plan_id = timeline_state.current.timeline.attention_plan_id
            if plan_id is not None:
                saved = self.records.get(f"attention-plan-{plan_id}")
                if saved is not None:
                    plan = AttentionPlan.model_validate(saved[1])
                    if plan.project_id == project_id:
                        return plan
        checkpoint = self.records.get(f"job-stage-{job.id}-attention")
        if checkpoint is None:
            raise KeyError("Attention plan not found")
        plan = AttentionPlan.model_validate(checkpoint[1]["attention_plan"])
        if plan.project_id != project_id or plan.job_id != job.id:
            raise KeyError("Attention plan not found")
        return plan

    def style_plan(self, project_id: str) -> StyleDirectionPlan:
        job = self.latest(project_id)
        if job is None:
            raise KeyError("Style direction plan not found")
        timeline_state = self.generation.timelines.current(project_id)
        if timeline_state is not None:
            plan_id = timeline_state.current.timeline.style_plan_id
            if plan_id is not None:
                saved = self.records.get(f"style-plan-{plan_id}")
                if saved is not None:
                    plan = StyleDirectionPlan.model_validate(saved[1])
                    if plan.project_id == project_id:
                        return plan
        checkpoint = self.records.get(f"job-stage-{job.id}-style")
        if checkpoint is None:
            raise KeyError("Style direction plan not found")
        plan = StyleDirectionPlan.model_validate(checkpoint[1]["style_plan"])
        if plan.project_id != project_id or plan.job_id != job.id:
            raise KeyError("Style direction plan not found")
        return plan

    def longform_plan(self, project_id: str) -> LongFormVideoPlan:
        job = self.latest(project_id)
        if job is None:
            raise KeyError("Long-form plan not found")
        timeline_state = self.generation.timelines.current(project_id)
        plan_id = (
            timeline_state.current.timeline.long_form_plan_id
            if timeline_state is not None
            else None
        )
        director = getattr(self.executor, "longform_director", None)
        if plan_id is not None and director is not None:
            return cast(LongFormDirectorProtocol, director).plan(project_id, plan_id)
        checkpoint = self.records.get(f"job-stage-{job.id}-style")
        if checkpoint is None or "longform_plan" not in checkpoint[1]:
            raise KeyError("Long-form plan not found")
        plan = LongFormVideoPlan.model_validate(checkpoint[1]["longform_plan"])
        if plan.project_id != project_id:
            raise KeyError("Long-form plan not found")
        return plan

    def longform_checkpoints(self, project_id: str) -> list[ChapterCheckpoint]:
        plan = self.longform_plan(project_id)
        director = getattr(self.executor, "longform_director", None)
        if director is None:
            raise KeyError("Long-form checkpoints not found")
        return cast(LongFormDirectorProtocol, director).checkpoints(project_id, plan.id)

    def retry_longform_chapter(
        self,
        project_id: str,
        chapter_id: str,
    ) -> ChapterCheckpoint:
        plan = self.longform_plan(project_id)
        director = getattr(self.executor, "longform_director", None)
        if director is None:
            raise KeyError("Long-form chapter not found")
        chapter = next(
            (item for item in plan.chapters if item.id == chapter_id),
            None,
        )
        if chapter is None:
            raise KeyError("Long-form chapter not found")
        typed_director = cast(LongFormDirectorProtocol, director)
        typed_director.retry_chapter(project_id, plan.id, chapter_id)
        project = self.generation.projects.get(project_id)
        board = self.generation.storyboards.get_latest(project_id)
        if project is None or board is None:
            raise KeyError("Long-form chapter inputs not found")
        scenes = sorted(board.scenes, key=lambda scene: scene.order)
        job = self.latest(project_id)
        if job is None:
            raise KeyError("Long-form generation job not found")
        job_input = self.records.get(f"job-input-{job.id}")
        encrypted_token = job_input[1].get("capture_token") if job_input else None
        token = self.vault.decrypt(encrypted_token) if encrypted_token else None
        chapter_scene = _prepare_chapter_capture(board, scenes, chapter)
        try:
            result = self.generation.capture_worker.capture_scene(
                chapter_scene,
                session_token=token,
            )
        except Exception:
            return typed_director.record_chapter_result(
                project_id,
                plan.id,
                chapter_id,
                artifact_ref=None,
                artifact_sha256=None,
                elapsed_ms=0,
            )
        minimum_duration = max(0, chapter.end_ms - chapter.start_ms - 1_000)
        succeeded = (
            result.status == "succeeded"
            and result.raw_clip_path is not None
            and Path(result.raw_clip_path).is_file()
            and result.duration_ms >= minimum_duration
        )
        checkpoint = typed_director.record_chapter_result(
            project_id,
            plan.id,
            chapter_id,
            artifact_ref=result.raw_clip_path if succeeded else None,
            artifact_sha256=(
                _media_sha256(result.raw_clip_path)
                if succeeded and result.raw_clip_path
                else None
            ),
            elapsed_ms=result.duration_ms,
        )
        if not succeeded or result.raw_clip_path is None:
            return checkpoint
        result_key = f"longform-chapter-result-{plan.id}-{chapter.id}"
        saved_result = self.records.get(result_key)
        self.records.put(
            result_key,
            saved_result[0] if saved_result else 0,
            result.model_dump(mode="json"),
        )
        timeline_state = self.generation.timelines.current(project_id)
        if timeline_state is None:
            raise JobConflict("Long-form timeline is missing")
        prior = timeline_state.current.timeline
        replacement = SceneClip(
            id=f"scene-clip-{chapter.id}",
            scene_id=chapter.id,
            start_ms=chapter.start_ms,
            end_ms=chapter.end_ms,
            source_uri=str(Path(result.raw_clip_path).resolve()),
        )
        scene_clips = [
            replacement if clip.scene_id == chapter.id else clip
            for clip in prior.scene_clips
        ]
        cursor_events = [
            event
            for event in prior.cursor_events
            if not chapter.start_ms <= event.timestamp_ms < chapter.end_ms
        ]
        cursor_events.extend(
            event.model_copy(update={
                "timestamp_ms": min(
                    chapter.end_ms,
                    chapter.start_ms + event.timestamp_ms,
                )
            })
            for event in result.interaction_events
        )
        cursor_events.sort(key=lambda event: event.timestamp_ms)
        updated = prior.model_copy(update={
            "scene_clips": scene_clips,
            "cursor_events": cursor_events,
        })
        self.generation.timelines.commit(
            timeline_state.current.version,
            self.generation.timeline_media_store.persist(updated),
            f"Regenerated capture chapter {chapter.order + 1}",
            [chapter.id],
        )
        return checkpoint

    def select_style(
        self,
        project_id: str,
        expected_timeline_version: int,
        variant_id: VisualVariantId,
        scene_id: str | None = None,
        reset_scene: bool = False,
    ) -> StyleDirectionPlan:
        plan = self.style_plan(project_id)
        timeline_state = self.generation.timelines.current(project_id)
        if timeline_state is None or timeline_state.current.version != expected_timeline_version:
            raise RecordConflict("Timeline changed; reload before selecting a style.")
        if scene_id is not None and scene_id not in plan.scene_ids:
            raise JobConflict("Style override scene is not part of this project")
        overrides = [item for item in plan.overrides if item.scene_id != scene_id]
        if scene_id is not None and not reset_scene:
            overrides.append(VariantOverride(scene_id=scene_id, variant_id=variant_id))
            overrides.sort(key=lambda item: plan.scene_ids.index(item.scene_id))
        selected_variant = variant_id if scene_id is None else plan.decision.selected_variant
        outcome = (
            "accepted" if selected_variant == plan.decision.recommended_variant else "overridden"
        )
        now = datetime.now(UTC)
        new_plan = StyleDirectionPlan.model_validate(
            {
                **plan.model_dump(mode="json"),
                "id": str(uuid4()),
                "decision": {
                    "recommended_variant": plan.decision.recommended_variant,
                    "selected_variant": selected_variant,
                    "outcome": outcome,
                    "decided_at": now,
                },
                "overrides": overrides,
                "manual_override_of": plan.id,
                "created_at": now,
            }
        )
        self.records.put(f"style-plan-{new_plan.id}", 0, new_plan.model_dump(mode="json"))
        affected = [scene_id] if scene_id is not None else list(plan.scene_ids)
        self.generation.timelines.commit(
            expected_timeline_version,
            timeline_state.current.timeline.model_copy(
                update={
                    "style_plan_id": new_plan.id,
                    "style_design_version": new_plan.version,
                    "visual_variant": selected_variant,
                }
            ),
            "Reset scene style" if reset_scene else "Selected visual style",
            affected,
        )
        return new_plan

    def edit_attention(
        self,
        project_id: str,
        callout_id: str,
        expected_timeline_version: int,
        changes: dict[str, Any],
    ) -> AttentionPlan:
        plan = self.attention_plan(project_id)
        selected = next((item for item in plan.callouts if item.id == callout_id), None)
        if selected is None:
            raise KeyError("Callout not found")
        allowed = {"text", "placement", "start_ms", "end_ms", "target_x", "target_y", "remove"}
        if set(changes) - allowed:
            raise JobConflict("Unsupported attention edit")
        callouts = [item for item in plan.callouts if item.id != callout_id]
        targets = list(plan.targets)
        if not changes.get("remove", False):
            callout_updates = {
                key: value
                for key, value in changes.items()
                if key in {"text", "placement", "start_ms", "end_ms"} and value is not None
            }
            callouts.append(
                AnimatedCallout.model_validate({**selected.model_dump(), **callout_updates})
            )
            callouts.sort(key=lambda item: item.start_ms)
        if changes.get("target_x") is not None or changes.get("target_y") is not None:
            target_index = next(
                (index for index, item in enumerate(targets) if item.id == selected.target_id),
                None,
            )
            if target_index is None:
                raise JobConflict("Callout target is unavailable")
            target = targets[target_index]
            x = float(changes.get("target_x", target.rect.x))
            y = float(changes.get("target_y", target.rect.y))
            rect = target.rect.model_copy(
                update={
                    "x": min(max(0, x), 1 - target.rect.width),
                    "y": min(max(0, y), 1 - target.rect.height),
                }
            )
            targets[target_index] = target.model_copy(update={"rect": rect})
        new_plan = AttentionPlan.model_validate(
            {
                **plan.model_dump(),
                "id": str(uuid4()),
                "manual_override_of": plan.id,
                "targets": targets,
                "callouts": callouts,
                "created_at": datetime.now(UTC),
            }
        )
        timeline_state = self.generation.timelines.current(project_id)
        if timeline_state is None or timeline_state.current.version != expected_timeline_version:
            raise RecordConflict("Timeline changed; reload before editing callouts.")
        self.records.put(f"attention-plan-{new_plan.id}", 0, new_plan.model_dump(mode="json"))
        self.generation.timelines.commit(
            expected_timeline_version,
            timeline_state.current.timeline.model_copy(update={"attention_plan_id": new_plan.id}),
            "Updated viewer attention",
            [callout_id],
        )
        return new_plan

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
        self.monitor.acquire(project, job.id, f"generation-{job.id}")
        self.records.put(
            f"job-input-{job.id}",
            0,
            {"project": project.model_dump(mode="json"), "capture_token": encrypted},
        )
        self.records.put(f"generation-{job.id}", 0, job.model_dump(mode="json"))
        self.records.put(
            self._trace_key(job.id), 0, self._initial_trace(job).model_dump(mode="json")
        )
        try:
            self.records.put(f"generation-project-{project_id}", 0, {"job_id": job.id})
        except RecordConflict:
            winner = self.latest(project_id)
            assert winner is not None
            return winner
        self.generation._set_status(project_id, "storyboarding", "queued")
        self.monitor.event(job)
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
        self.monitor.event(updated)
        return updated

    def step(self, job_id: str) -> GenerationJob:
        job = self.get(job_id)
        project = self.generation.projects.get(job.project_id)
        if project is None:
            raise KeyError("Project not found")
        if job.status in {"queued", "running"}:
            self.monitor.acquire(project, job.id, f"generation-{job.id}")
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
                self._finish_trace_attempt(job, succeeded=False, terminal=job.attempts >= 3)
                return self._save(
                    job,
                    status="failed" if job.attempts >= 3 else "awaiting_retry",
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
        self._start_trace_attempt(claimed, claimed.updated_at)
        try:
            if checkpoint is None:
                with self.monitor.heartbeat(claimed):
                    result = self.executor.execute(claimed)
                self.records.put(checkpoint_key, 0, result)
            else:
                result = checkpoint[1]
        except ApprovalNeeded:
            self._reset_trace_attempt_for_approval(claimed)
            return self._save(
                claimed,
                status="awaiting_approval",
                lease_until=None,
                attempts=max(0, claimed.attempts - 1),
                message="Review storyboard evidence, then approve capture and narration.",
            )
        except Exception as error:
            self.monitor.event(
                claimed, f"{job.stage.capitalize()}: {failure_summary(error)} "
                "Completed checkpoints are preserved.", "error",
            )
            terminal = claimed.attempts >= 3
            self._finish_trace_attempt(claimed, succeeded=False, terminal=terminal)
            failed = self._save(
                claimed,
                status="failed" if terminal else "awaiting_retry",
                lease_until=None,
                message=(
                    f"{job.stage.capitalize()} failed after three attempts."
                    if terminal
                    else f"{job.stage.capitalize()} failed. Completed checkpoints are safe. "
                    "Explicit retry may repeat this stage's provider work."
                ),
            )
            self.generation._set_status(job.project_id, "failed", "failed")
            return failed
        self._finish_trace_attempt(claimed, succeeded=True, result=result)
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
        project = self.generation.projects.get(project_id)
        if project is None:
            raise KeyError("Project not found")
        self.monitor.acquire(project, job.id, f"generation-{job.id}")
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
                "SELECT r.key, r.payload FROM workflow_records r JOIN "
                "(SELECT key, MAX(version) AS version FROM workflow_records "
                "WHERE key LIKE 'generation-%' GROUP BY key) latest "
                "ON r.key=latest.key AND r.version=latest.version"
            ).fetchall()
        for key, payload in rows:
            value = json.loads(payload)
            if (
                re.fullmatch(r"generation-[a-f0-9-]{36}", key) is None
                or key != f"generation-{value.get('id', '')}"
            ):
                continue
            try:
                job = GenerationJob.model_validate(value)
            except ValidationError:
                logger.warning("Ignoring invalid local generation queue record %s", key)
                continue
            if job.status == "queued" or (
                job.status == "running" and job.lease_until and job.lease_until < datetime.now(UTC)
            ):
                try:
                    self.step(job.id)
                    return True
                except (JobConflict, RecordConflict):
                    continue
        return False

    def resume_approved(self, project_id: str) -> GenerationJob | None:
        job = self.latest(project_id)
        if job is None or job.status != "awaiting_approval":
            return job
        project = self.generation.projects.get(project_id)
        if project is None:
            raise KeyError("Project not found")
        self.monitor.acquire(project, job.id, f"generation-{job.id}")
        resumed = self._save(job, status="queued", message="Storyboard approved; capture queued.")
        self.generation._set_status(project_id, "ready", "queued")
        self.dispatcher.dispatch(job.id, resumed.version)
        return resumed
