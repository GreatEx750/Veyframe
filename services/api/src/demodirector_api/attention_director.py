from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from demodirector_contracts.attention import (
    AnimatedCallout,
    AttentionDraft,
    AttentionPlan,
    AttentionRequest,
    AttentionRunStep,
    TargetObservation,
)
from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from demodirector_api.records import RecordStore

AGENT_NAME = "demodirector_attention_director"
APP_NAME = "demodirector_attention"
INSTRUCTION = """You are the attention director inside DemoDirector's ADK workflow.
Call read_approved_attention_context first. Use only supplied target IDs, narration statement IDs,
callout types, placements, and timing. Return only JSON matching the supplied schema. Never create
selectors, coordinates, code, commands, browser actions, or unsupported claims.
"""


class AttentionGateway(Protocol):
    model_name: str

    def execute(
        self,
        request: AttentionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> str: ...


class GoogleADKAttentionGateway:
    def __init__(self, model: str | BaseLlm) -> None:
        self.model = model
        self.model_name = model if isinstance(model, str) else model.model

    def execute(
        self,
        request: AttentionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> str:
        return asyncio.run(self._execute(request, context, session_id))

    async def _execute(
        self,
        request: AttentionRequest,
        context: dict[str, object],
        session_id: str,
    ) -> str:
        def read_approved_attention_context() -> dict[str, object]:
            """Return approved narration, observed targets, camera cues, and callout catalog."""
            return context

        agent = Agent(
            name=AGENT_NAME,
            model=self.model,
            instruction=INSTRUCTION,
            tools=[read_approved_attention_context],
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
        )
        sessions = InMemorySessionService()
        user_id = f"project-{hashlib.sha256(request.project_id.encode()).hexdigest()[:20]}"
        await sessions.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        runner = Runner(app_name=APP_NAME, agent=agent, session_service=sessions)
        final_text: str | None = None
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=json.dumps(
                                {
                                    "request": request.model_dump(mode="json"),
                                    "required_output_schema": AttentionDraft.model_json_schema(),
                                },
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                        )
                    ],
                ),
            ):
                if event.is_final_response() and event.content is not None:
                    pieces = [part.text for part in event.content.parts or [] if part.text]
                    if pieces:
                        final_text = "".join(pieces)
        finally:
            await runner.close()
        if final_text is None:
            raise ValueError("Google ADK returned no attention plan")
        return final_text


class AttentionDirector:
    agent_name = AGENT_NAME

    def __init__(self, records: RecordStore, gateway: AttentionGateway) -> None:
        self.records = records
        self.gateway = gateway
        self.model_name = gateway.model_name

    def direct(
        self,
        request: AttentionRequest,
        targets: list[TargetObservation],
        context: dict[str, object],
    ) -> tuple[AttentionRunStep, AttentionPlan]:
        run_id = str(uuid4())
        session_id = str(uuid4())
        started_at = datetime.now(UTC)
        base = AttentionRunStep(
            id=run_id,
            project_id=request.project_id,
            job_id=request.job_id,
            parent_run_id=request.parent_run_id,
            session_id=session_id,
            agent_name="demodirector_attention_director",
            model=self.model_name,
            status="running",
            started_at=started_at,
            workflow_runs=0,
            input_target_count=len(targets),
            proposed_cue_count=0,
            accepted_cue_count=0,
            validation_status="pending",
            message="Google ADK attention direction started.",
        )
        key = f"adk-attention-run-{run_id}"
        self.records.put(key, 0, base.model_dump(mode="json"))
        try:
            draft = AttentionDraft.model_validate_json(
                self.gateway.execute(request, context, session_id=session_id)
            )
            plan = AttentionPlan(
                id=str(uuid4()),
                project_id=request.project_id,
                job_id=request.job_id,
                parent_run_id=request.parent_run_id,
                duration_ms=request.duration_ms,
                targets=targets,
                narration_statement_ids=request.narration_statement_ids,
                summary=draft.summary,
                callouts=[
                    AnimatedCallout(id=f"callout-{index + 1}", **item.model_dump())
                    for index, item in enumerate(draft.callouts)
                ],
                caption_emphasis=draft.caption_emphasis,
                created_at=datetime.now(UTC),
            )
            self.records.put(f"attention-plan-{plan.id}", 0, plan.model_dump(mode="json"))
            completed = datetime.now(UTC)
            succeeded = base.model_copy(
                update={
                    "status": "succeeded",
                    "completed_at": completed,
                    "elapsed_ms": max(
                        0, round((completed - started_at).total_seconds() * 1_000)
                    ),
                    "workflow_runs": 1,
                    "proposed_cue_count": len(draft.callouts),
                    "accepted_cue_count": len(plan.callouts),
                    "validation_status": "passed",
                    "output_plan_id": plan.id,
                    "message": "Validated Google ADK attention plan saved.",
                }
            )
            self.records.put(key, 1, succeeded.model_dump(mode="json"))
            return succeeded, plan
        except Exception as error:
            completed = datetime.now(UTC)
            failed = base.model_copy(
                update={
                    "status": "failed",
                    "completed_at": completed,
                    "elapsed_ms": max(
                        0, round((completed - started_at).total_seconds() * 1_000)
                    ),
                    "workflow_runs": 1,
                    "validation_status": "failed",
                    "message": "Google ADK attention output failed typed validation.",
                }
            )
            self.records.put(key, 1, failed.model_dump(mode="json"))
            if isinstance(error, ValidationError):
                raise ValueError("ADK attention plan was invalid") from error
            raise ValueError("ADK attention planning failed") from error
