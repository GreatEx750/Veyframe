from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from demodirector_contracts.longform import (
    ChapterCheckpoint,
    LongFormADKRun,
    LongFormADKStep,
    LongFormDirectionRequest,
    LongFormStepKind,
    LongFormVideoPlan,
)
from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from demodirector_api.records import RecordConflict, RecordStore

AGENT_NAME: Literal["demodirector_longform_director"] = (
    "demodirector_longform_director"
)
APP_NAME = "demodirector_longform"
STEP_ORDER: tuple[LongFormStepKind, ...] = (
    "narrative",
    "template",
    "attention",
    "style",
)
INSTRUCTION = """You are DemoDirector's bounded long-form director in Google ADK.
Call read_project_evidence once, then call record_narrative_direction,
record_template_direction, record_attention_direction, and record_style_direction exactly once
and in that order. Cite only supplied artifact references. Finally return only one JSON object
matching the LongFormVideoPlan schema and the exact IDs in the request. Use the fixed section
timings, 350-430 words, 20-30 beats, product operation at 20 seconds, Create by 30 seconds,
finished glimpse by 45 seconds, and product footage in every section. Do not return browser
commands, JavaScript, shell commands, CSS, or unapproved claims.
"""


@dataclass(frozen=True, slots=True)
class LongFormGatewayResult:
    output: str
    evidence_reads: int
    steps: tuple[tuple[LongFormStepKind, tuple[str, ...]], ...]


class LongFormGateway(Protocol):
    model_name: str

    def execute(
        self,
        request: LongFormDirectionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> LongFormGatewayResult: ...


class GoogleADKLongFormGateway:
    def __init__(self, model: str | BaseLlm) -> None:
        self.model = model
        self.model_name = model if isinstance(model, str) else model.model

    def execute(
        self,
        request: LongFormDirectionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> LongFormGatewayResult:
        return asyncio.run(self._execute(request, context, session_id))

    async def _execute(
        self,
        request: LongFormDirectionRequest,
        context: dict[str, object],
        session_id: str,
    ) -> LongFormGatewayResult:
        evidence_reads = 0
        recorded: list[tuple[LongFormStepKind, tuple[str, ...]]] = []
        allowed = set(request.evidence_refs)

        def read_project_evidence() -> dict[str, object]:
            """Read the approved project artifacts and direct Parallel source references."""
            nonlocal evidence_reads
            evidence_reads += 1
            return context

        def record(kind: LongFormStepKind, artifact_refs: list[str]) -> dict[str, object]:
            if len(recorded) >= len(STEP_ORDER) or kind != STEP_ORDER[len(recorded)]:
                raise ValueError("Long-form director steps were called out of order")
            if not artifact_refs or set(artifact_refs) - allowed:
                raise ValueError("Long-form director step cited an unknown artifact")
            recorded.append((kind, tuple(artifact_refs)))
            return {"status": "recorded", "kind": kind}

        def record_narrative_direction(artifact_refs: list[str]) -> dict[str, object]:
            """Record the evidence used for the bounded narrative direction."""
            return record("narrative", artifact_refs)

        def record_template_direction(artifact_refs: list[str]) -> dict[str, object]:
            """Record the evidence used for fixed editorial template selection."""
            return record("template", artifact_refs)

        def record_attention_direction(artifact_refs: list[str]) -> dict[str, object]:
            """Record the evidence used for target-aware attention direction."""
            return record("attention", artifact_refs)

        def record_style_direction(artifact_refs: list[str]) -> dict[str, object]:
            """Record the evidence used for the selected fixed visual variant."""
            return record("style", artifact_refs)

        agent = Agent(
            name=AGENT_NAME,
            model=self.model,
            instruction=INSTRUCTION,
            tools=[
                read_project_evidence,
                record_narrative_direction,
                record_template_direction,
                record_attention_direction,
                record_style_direction,
            ],
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
        )
        sessions = InMemorySessionService()
        user_id = f"project-{hashlib.sha256(request.project_id.encode()).hexdigest()[:20]}"
        await sessions.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        runner = Runner(app_name=APP_NAME, agent=agent, session_service=sessions)
        final_text: str | None = None
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=json.dumps({
                        "request": request.model_dump(mode="json"),
                        "required_output_schema": LongFormVideoPlan.model_json_schema(),
                    }, sort_keys=True, separators=(",", ":")))],
                ),
            ):
                if event.is_final_response() and event.content is not None:
                    text_parts = [part.text for part in event.content.parts or [] if part.text]
                    if text_parts:
                        final_text = "".join(text_parts)
        finally:
            await runner.close()
        if final_text is None:
            raise ValueError("Google ADK returned no long-form plan")
        return LongFormGatewayResult(
            output=final_text,
            evidence_reads=evidence_reads,
            steps=tuple(recorded),
        )


class LongFormDirector:
    agent_name: str = AGENT_NAME

    def __init__(self, records: RecordStore, gateway: LongFormGateway) -> None:
        self.records = records
        self.gateway = gateway
        self.model_name = gateway.model_name

    def direct(
        self,
        request: LongFormDirectionRequest,
        context: dict[str, object],
    ) -> tuple[LongFormADKRun, LongFormVideoPlan]:
        session_id = hashlib.sha256(
            f"{request.run_id}:{request.project_id}".encode()
        ).hexdigest()[:32]
        started_at = datetime.now(UTC)
        base = LongFormADKRun(
            id=request.run_id,
            project_id=request.project_id,
            job_id=request.job_id,
            parent_motion_run_id=request.parent_motion_run_id,
            session_id=session_id,
            agent_name=AGENT_NAME,
            model=self.model_name,
            status="running",
            runner_completed=False,
            workflow_runs=0,
            started_at=started_at,
            message="Google ADK long-form direction started.",
        )
        run_key = f"adk-longform-run-{request.run_id}"
        self.records.put(run_key, 0, base.model_dump(mode="json"))
        try:
            gateway_result = self.gateway.execute(request, context, session_id=session_id)
            if gateway_result.evidence_reads != 1:
                raise ValueError("ADK must read approved evidence exactly once")
            if tuple(item[0] for item in gateway_result.steps) != STEP_ORDER:
                raise ValueError("ADK long-form workflow did not complete its four steps")
            plan = LongFormVideoPlan.model_validate_json(gateway_result.output)
            self._validate_plan_identity(plan, request)
            now = datetime.now(UTC)
            steps: list[LongFormADKStep] = []
            for _index, (kind, refs) in enumerate(gateway_result.steps):
                digest = hashlib.sha256(
                    json.dumps(
                        {"kind": kind, "refs": refs, "plan": plan.id},
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                step = LongFormADKStep(
                    id=f"{request.run_id}-{kind}",
                    run_id=request.run_id,
                    project_id=request.project_id,
                    kind=kind,
                    status="succeeded",
                    tool_call_count=1,
                    artifact_refs=list(refs),
                    output_sha256=digest,
                    created_at=now,
                )
                self.records.put(
                    f"adk-longform-step-{step.id}", 0, step.model_dump(mode="json")
                )
                steps.append(step)
            self.records.put(
                f"longform-plan-{plan.id}", 0, plan.model_dump(mode="json")
            )
            for chapter in plan.chapters:
                checkpoint = ChapterCheckpoint(
                    id=f"checkpoint-{chapter.id}-0",
                    project_id=plan.project_id,
                    plan_id=plan.id,
                    chapter_id=chapter.id,
                    status="pending",
                    attempt=0,
                    created_at=now,
                )
                self.records.put(
                    f"longform-checkpoint-{plan.id}-{chapter.id}",
                    0,
                    checkpoint.model_dump(mode="json"),
                )
            completed = datetime.now(UTC)
            succeeded = base.model_copy(update={
                "status": "succeeded",
                "runner_completed": True,
                "workflow_runs": 1,
                "step_ids": [step.id for step in steps],
                "output_plan_id": plan.id,
                "completed_at": completed,
                "elapsed_ms": max(
                    0, round((completed - started_at).total_seconds() * 1_000)
                ),
                "message": "Validated Google ADK three-minute direction saved.",
            })
            self.records.put(run_key, 1, succeeded.model_dump(mode="json"))
            return succeeded, plan
        except Exception as error:
            completed = datetime.now(UTC)
            failed = base.model_copy(update={
                "status": "failed",
                "completed_at": completed,
                "elapsed_ms": max(
                    0, round((completed - started_at).total_seconds() * 1_000)
                ),
                "message": "Google ADK long-form output failed typed validation.",
            })
            self.records.put(run_key, 1, failed.model_dump(mode="json"))
            raise ValueError("ADK long-form planning failed") from error

    @staticmethod
    def _validate_plan_identity(
        plan: LongFormVideoPlan,
        request: LongFormDirectionRequest,
    ) -> None:
        expected = (
            request.plan_id,
            request.project_id,
            request.job_id,
            request.run_id,
            request.parent_motion_run_id,
            request.visual_variant,
            request.research_status,
            request.evidence_refs,
            request.parallel_source_refs,
            request.product_clip_refs,
            request.target_ids,
        )
        actual = (
            plan.id,
            plan.project_id,
            plan.job_id,
            plan.adk_run_id,
            plan.parent_motion_run_id,
            plan.visual_variant,
            plan.research_status,
            plan.evidence_refs,
            plan.parallel_source_refs,
            plan.product_clip_refs,
            plan.target_ids,
        )
        if actual != expected:
            raise ValueError("Long-form plan identity or artifact references changed")

    def plan(self, project_id: str, plan_id: str) -> LongFormVideoPlan:
        stored = self.records.get(f"longform-plan-{plan_id}")
        if stored is None:
            raise KeyError("Long-form plan not found")
        plan = LongFormVideoPlan.model_validate(stored[1])
        if plan.project_id != project_id:
            raise KeyError("Long-form plan not found")
        return plan

    def checkpoints(self, project_id: str, plan_id: str) -> list[ChapterCheckpoint]:
        plan = self.plan(project_id, plan_id)
        result = []
        for chapter in plan.chapters:
            stored = self.records.get(f"longform-checkpoint-{plan.id}-{chapter.id}")
            if stored is None:
                raise KeyError("Long-form checkpoint not found")
            result.append(ChapterCheckpoint.model_validate(stored[1]))
        return result

    def retry_chapter(
        self,
        project_id: str,
        plan_id: str,
        chapter_id: str,
    ) -> ChapterCheckpoint:
        plan = self.plan(project_id, plan_id)
        if chapter_id not in {chapter.id for chapter in plan.chapters}:
            raise KeyError("Long-form chapter not found")
        key = f"longform-checkpoint-{plan.id}-{chapter_id}"
        stored = self.records.get(key)
        if stored is None:
            raise KeyError("Long-form checkpoint not found")
        current = ChapterCheckpoint.model_validate(stored[1])
        if current.status not in {"failed", "captured", "approved"}:
            raise RecordConflict("Only completed or failed chapters can be regenerated")
        if current.attempt >= 3:
            raise RecordConflict("Chapter retry limit reached")
        next_checkpoint = ChapterCheckpoint(
            id=f"checkpoint-{chapter_id}-{current.attempt + 1}",
            project_id=project_id,
            plan_id=plan_id,
            chapter_id=chapter_id,
            status="pending",
            attempt=current.attempt + 1,
            replaces_checkpoint_id=current.id,
            created_at=datetime.now(UTC),
        )
        self.records.put(key, stored[0], next_checkpoint.model_dump(mode="json"))
        return next_checkpoint

    def record_chapter_result(
        self,
        project_id: str,
        plan_id: str,
        chapter_id: str,
        *,
        artifact_ref: str | None,
        artifact_sha256: str | None,
        elapsed_ms: int,
    ) -> ChapterCheckpoint:
        plan = self.plan(project_id, plan_id)
        if chapter_id not in {chapter.id for chapter in plan.chapters}:
            raise KeyError("Long-form chapter not found")
        key = f"longform-checkpoint-{plan.id}-{chapter_id}"
        stored = self.records.get(key)
        if stored is None:
            raise KeyError("Long-form checkpoint not found")
        current = ChapterCheckpoint.model_validate(stored[1])
        if current.status != "pending":
            raise RecordConflict("Chapter checkpoint is not awaiting capture")
        succeeded = artifact_ref is not None and artifact_sha256 is not None
        completed = current.model_copy(update={
            "status": "captured" if succeeded else "failed",
            "artifact_ref": artifact_ref,
            "artifact_sha256": artifact_sha256,
            "elapsed_ms": elapsed_ms,
        })
        self.records.put(key, stored[0], completed.model_dump(mode="json"))
        return completed
