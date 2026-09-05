from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from demodirector_contracts.editorial import EditorialScene, EditorialTemplatePlan
from demodirector_contracts.motion import (
    ADKMotionRun,
    MotionCue,
    MotionDirectionDraft,
    MotionDirectionPlan,
    MotionDirectionRequest,
    MotionTokenSet,
)
from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from demodirector_api.records import RecordStore

AGENT_NAME = "demodirector_motion_director"
APP_NAME = "demodirector_motion"
MOTION_INSTRUCTION = """You direct motion for a product video.
Call read_approved_motion_context before planning. Use only the returned approved IDs and facts.
Choose only the supplied motion primitives, scene IDs, product clip references, layers, and easing
names. Keep the product visible. Return only JSON matching the supplied schema. Never return code,
CSS, JavaScript, shell commands, browser actions, file paths, or facts absent from the context.
Assign one trusted editorial template to every scene using the exact scene timing and product clip
reference from the context. Product footage must remain visible for the complete scene.
"""


class MotionPlanningGateway(Protocol):
    model_name: str
    agent_name: str

    def execute(
        self,
        request: MotionDirectionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> str: ...


class GoogleADKMotionGateway:
    agent_name = AGENT_NAME

    def __init__(self, model: str | BaseLlm) -> None:
        self.model = model
        self.model_name = model if isinstance(model, str) else model.model

    def execute(
        self,
        request: MotionDirectionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> str:
        return asyncio.run(self._execute(request, context, session_id))

    async def _execute(
        self,
        request: MotionDirectionRequest,
        context: dict[str, object],
        session_id: str,
    ) -> str:
        def read_approved_motion_context() -> dict[str, object]:
            """Return the approved project, evidence, storyboard, and allowed motion catalog."""
            return context

        agent = Agent(
            name=self.agent_name,
            model=self.model,
            description="Creates a typed motion direction from approved product evidence.",
            instruction=MOTION_INSTRUCTION,
            tools=[read_approved_motion_context],
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
        )
        sessions = InMemorySessionService()
        await sessions.create_session(
            app_name=APP_NAME,
            user_id=_opaque_user_id(request.project_id),
            session_id=session_id,
        )
        runner = Runner(
            app_name=APP_NAME,
            agent=agent,
            session_service=sessions,
        )
        prompt = {
            "request": request.model_dump(mode="json"),
            "required_output_schema": MotionDirectionDraft.model_json_schema(),
        }
        final_text: str | None = None
        try:
            async for event in runner.run_async(
                user_id=_opaque_user_id(request.project_id),
                session_id=session_id,
                new_message=types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=json.dumps(prompt, sort_keys=True, separators=(",", ":"))
                        )
                    ],
                ),
            ):
                if not event.is_final_response() or event.content is None:
                    continue
                pieces = [part.text for part in event.content.parts or [] if part.text]
                if pieces:
                    final_text = "".join(pieces)
        finally:
            await runner.close()
        if final_text is None:
            raise ValueError("Google ADK returned no final motion direction")
        return final_text


class ADKMotionDirector:
    def __init__(self, records: RecordStore, gateway: MotionPlanningGateway) -> None:
        self.records = records
        self.gateway = gateway
        self.model_name = gateway.model_name
        self.agent_name = gateway.agent_name

    def direct(
        self,
        request: MotionDirectionRequest,
        context: dict[str, object],
        *,
        retry_count: int = 0,
    ) -> tuple[ADKMotionRun, MotionDirectionPlan]:
        if context.get("project") is None:
            raise ValueError("Approved motion context is missing the project")
        run_id = str(uuid4())
        session_id = str(uuid4())
        started_at = datetime.now(UTC)
        artifacts = [
            f"storyboard:{request.storyboard_id}:{request.storyboard_version}",
            f"evidence:{request.evidence_fingerprint}",
            *[f"source:{source_id}" for source_id in request.source_ids],
        ]
        running = ADKMotionRun(
            id=run_id,
            project_id=request.project_id,
            job_id=request.job_id,
            session_id=session_id,
            agent_name="demodirector_motion_director",
            model=self.model_name,
            status="running",
            started_at=started_at,
            retry_count=retry_count,
            workflow_runs=0,
            input_artifact_ids=artifacts,
            validation_status="pending",
            message="Google ADK motion direction started.",
        )
        run_key = f"adk-motion-run-{run_id}"
        self.records.put(run_key, 0, running.model_dump(mode="json"))
        pointer_key = f"adk-motion-run-job-{request.job_id}"
        previous_pointer = self.records.get(pointer_key)
        self.records.put(
            pointer_key,
            previous_pointer[0] if previous_pointer else 0,
            {"project_id": request.project_id, "run_id": run_id},
        )
        try:
            raw = self.gateway.execute(request, context, session_id=session_id)
            draft = MotionDirectionDraft.model_validate_json(raw)
            if draft.editorial is None:
                raise ValueError("ADK motion plan did not include editorial template direction")
            created_at = datetime.now(UTC)
            plan_id = str(uuid4())
            editorial_plan = EditorialTemplatePlan(
                id=str(uuid4()),
                project_id=request.project_id,
                job_id=request.job_id,
                run_id=run_id,
                motion_plan_id=plan_id,
                catalog_version="editorial-v1",
                design_version="motion-v1",
                duration_ms=request.duration_ms,
                scene_ids=request.scene_ids,
                product_clip_refs=request.product_clip_refs,
                summary=draft.editorial.summary,
                scenes=[
                    EditorialScene(
                        id=f"editorial-scene-{index + 1}",
                        **scene.model_dump(),
                    )
                    for index, scene in enumerate(draft.editorial.scenes)
                ],
                created_at=created_at,
            )
            fingerprint = _fingerprint(request.model_dump(mode="json"))
            plan = MotionDirectionPlan(
                id=plan_id,
                project_id=request.project_id,
                job_id=request.job_id,
                run_id=run_id,
                request_fingerprint=fingerprint,
                design_tokens=MotionTokenSet(),
                duration_ms=request.duration_ms,
                scene_ids=request.scene_ids,
                product_clip_refs=request.product_clip_refs,
                summary=draft.summary,
                cues=[
                    MotionCue(id=f"motion-cue-{index + 1}", **cue.model_dump())
                    for index, cue in enumerate(draft.cues)
                ],
                editorial_plan=editorial_plan,
                created_at=created_at,
            )
            self.records.put(
                f"editorial-plan-{editorial_plan.id}",
                0,
                editorial_plan.model_dump(mode="json"),
            )
            self.records.put(
                f"motion-plan-{plan.id}", 0, plan.model_dump(mode="json")
            )
            plan_pointer_key = f"motion-plan-job-{request.job_id}"
            previous_plan = self.records.get(plan_pointer_key)
            self.records.put(
                plan_pointer_key,
                previous_plan[0] if previous_plan else 0,
                {"project_id": request.project_id, "plan_id": plan.id},
            )
            completed_at = datetime.now(UTC)
            succeeded = running.model_copy(
                update={
                    "status": "succeeded",
                    "completed_at": completed_at,
                    "elapsed_ms": _elapsed(started_at, completed_at),
                    "workflow_runs": 1,
                    "output_plan_id": plan.id,
                    "validation_status": "passed",
                    "message": "Validated Google ADK motion direction saved.",
                }
            )
            self.records.put(run_key, 1, succeeded.model_dump(mode="json"))
            return succeeded, plan
        except Exception as error:
            completed_at = datetime.now(UTC)
            failed = running.model_copy(
                update={
                    "status": "failed",
                    "completed_at": completed_at,
                    "elapsed_ms": _elapsed(started_at, completed_at),
                    "workflow_runs": 1,
                    "validation_status": "failed",
                    "message": "Google ADK motion output failed typed validation.",
                }
            )
            self.records.put(run_key, 1, failed.model_dump(mode="json"))
            if isinstance(error, ValidationError):
                raise ValueError("ADK motion plan was invalid") from error
            raise ValueError("ADK motion planning failed") from error

    def run(self, project_id: str, job_id: str) -> ADKMotionRun:
        pointer = self.records.get(f"adk-motion-run-job-{job_id}")
        if pointer is None or pointer[1].get("project_id") != project_id:
            raise KeyError("ADK motion run not found")
        saved = self.records.get(f"adk-motion-run-{pointer[1]['run_id']}")
        if saved is None:
            raise KeyError("ADK motion run not found")
        run = ADKMotionRun.model_validate(saved[1])
        if run.project_id != project_id or run.job_id != job_id:
            raise KeyError("ADK motion run not found")
        return run

    def plan(self, project_id: str, job_id: str) -> MotionDirectionPlan:
        pointer = self.records.get(f"motion-plan-job-{job_id}")
        if pointer is None or pointer[1].get("project_id") != project_id:
            raise KeyError("Motion direction plan not found")
        saved = self.records.get(f"motion-plan-{pointer[1]['plan_id']}")
        if saved is None:
            raise KeyError("Motion direction plan not found")
        plan = MotionDirectionPlan.model_validate(saved[1])
        if plan.project_id != project_id or plan.job_id != job_id:
            raise KeyError("Motion direction plan not found")
        return plan


def _fingerprint(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _elapsed(started_at: datetime, completed_at: datetime) -> int:
    return max(0, round((completed_at - started_at).total_seconds() * 1000))


def _opaque_user_id(project_id: str) -> str:
    return f"project-{hashlib.sha256(project_id.encode()).hexdigest()[:20]}"
