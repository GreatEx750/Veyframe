from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from demodirector_contracts.style import (
    StyleDirectionDecision,
    StyleDirectionDraft,
    StyleDirectionPlan,
    StyleDirectionRequest,
    StyleRunStep,
    VariantSceneDefaults,
)
from google.adk.agents import Agent
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from demodirector_api.records import RecordStore

AGENT_NAME = "demodirector_style_director"
APP_NAME = "demodirector_style"
INSTRUCTION = """You are the bounded style director in DemoDirector's ADK workflow.
Call read_approved_style_context first. Recommend exactly one catalog variant and cite only the
provided project-input IDs. Return only JSON matching the supplied schema. Never create themes,
CSS, code, provider claims, or facts.
"""


class StyleGateway(Protocol):
    model_name: str

    def execute(
        self,
        request: StyleDirectionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> str: ...


class GoogleADKStyleGateway:
    def __init__(self, model: str | BaseLlm) -> None:
        self.model = model
        self.model_name = model if isinstance(model, str) else model.model

    def execute(
        self,
        request: StyleDirectionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> str:
        return asyncio.run(self._execute(request, context, session_id))

    async def _execute(
        self,
        request: StyleDirectionRequest,
        context: dict[str, object],
        session_id: str,
    ) -> str:
        def read_approved_style_context() -> dict[str, object]:
            """Return audience, purpose, narrative coverage, and fixed style metadata."""
            return context

        agent = Agent(
            name=AGENT_NAME,
            model=self.model,
            instruction=INSTRUCTION,
            tools=[read_approved_style_context],
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
        )
        sessions = InMemorySessionService()
        user_id = f"project-{hashlib.sha256(request.project_id.encode()).hexdigest()[:20]}"
        await sessions.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
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
                            "required_output_schema": (
                                StyleDirectionDraft.model_json_schema()
                            ),
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
            raise ValueError("Google ADK returned no style direction")
        return final_text


class StyleDirector:
    agent_name = AGENT_NAME

    def __init__(self, records: RecordStore, gateway: StyleGateway) -> None:
        self.records = records
        self.gateway = gateway
        self.model_name = gateway.model_name

    def direct(
        self,
        request: StyleDirectionRequest,
        context: dict[str, object],
    ) -> tuple[StyleRunStep, StyleDirectionPlan]:
        run_id = str(uuid4())
        session_id = str(uuid4())
        started_at = datetime.now(UTC)
        base = StyleRunStep(
            id=run_id,
            project_id=request.project_id,
            job_id=request.job_id,
            parent_run_id=request.parent_run_id,
            session_id=session_id,
            agent_name="demodirector_style_director",
            model=self.model_name,
            status="running",
            started_at=started_at,
            workflow_runs=0,
            validation_status="pending",
            message="Google ADK style direction started.",
        )
        key = f"adk-style-run-{run_id}"
        self.records.put(key, 0, base.model_dump(mode="json"))
        try:
            draft = StyleDirectionDraft.model_validate_json(
                self.gateway.execute(request, context, session_id=session_id)
            )
            if set(draft.evidence_refs) - set(request.evidence_refs):
                raise ValueError("ADK style recommendation cited an unknown project input")
            now = datetime.now(UTC)
            plan = StyleDirectionPlan(
                id=str(uuid4()),
                project_id=request.project_id,
                job_id=request.job_id,
                parent_run_id=request.parent_run_id,
                audience=request.audience,
                purpose=request.purpose,
                scene_ids=request.scene_ids,
                allowed_evidence_refs=request.evidence_refs,
                recommendation_evidence_refs=draft.evidence_refs,
                rationale=draft.rationale,
                decision=StyleDirectionDecision(
                    recommended_variant=draft.recommended_variant,
                    selected_variant=draft.recommended_variant,
                    outcome="recommended",
                    decided_at=now,
                ),
                defaults=_defaults(),
                created_at=now,
            )
            self.records.put(f"style-plan-{plan.id}", 0, plan.model_dump(mode="json"))
            completed = datetime.now(UTC)
            succeeded = base.model_copy(
                update={
                    "status": "succeeded",
                    "completed_at": completed,
                    "elapsed_ms": max(0, round((completed - started_at).total_seconds() * 1_000)),
                    "workflow_runs": 1,
                    "validation_status": "passed",
                    "output_plan_id": plan.id,
                    "message": "Validated Google ADK style recommendation saved.",
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
                    "elapsed_ms": max(0, round((completed - started_at).total_seconds() * 1_000)),
                    "workflow_runs": 1,
                    "validation_status": "failed",
                    "message": "Google ADK style output failed typed validation.",
                }
            )
            self.records.put(key, 1, failed.model_dump(mode="json"))
            if isinstance(error, ValidationError):
                raise ValueError("ADK style direction was invalid") from error
            raise ValueError("ADK style planning failed") from error


def _defaults() -> list[VariantSceneDefaults]:
    return [
        VariantSceneDefaults(
            variant_id="editorial_story",
            product_scale="composed",
            callout_density="medium",
            motion_pace="deliberate",
        ),
        VariantSceneDefaults(
            variant_id="product_spotlight",
            product_scale="large",
            callout_density="low",
            motion_pace="calm",
        ),
        VariantSceneDefaults(
            variant_id="technical_proof",
            product_scale="evidence_focused",
            callout_density="medium",
            motion_pace="precise",
        ),
    ]
