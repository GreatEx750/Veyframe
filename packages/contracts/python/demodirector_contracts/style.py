from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from demodirector_contracts.models import ContractModel, NonEmptyString

VisualVariantId = Literal["editorial_story", "product_spotlight", "technical_proof"]
VisualVariantVersion = Literal["style-v1"]


class VariantSceneDefaults(ContractModel):
    variant_id: VisualVariantId
    product_scale: Literal["composed", "large", "evidence_focused"]
    callout_density: Literal["low", "medium"]
    motion_pace: Literal["calm", "deliberate", "precise"]


class VariantOverride(ContractModel):
    scene_id: NonEmptyString
    variant_id: VisualVariantId


class StyleDirectionDraft(ContractModel):
    recommended_variant: VisualVariantId
    rationale: str = Field(min_length=1, max_length=240)
    evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=40)


class StyleDirectionRequest(ContractModel):
    project_id: NonEmptyString
    job_id: NonEmptyString
    parent_run_id: NonEmptyString
    audience: NonEmptyString
    purpose: NonEmptyString
    scene_ids: list[NonEmptyString] = Field(min_length=1, max_length=80)
    evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=120)
    created_at: datetime


class StyleDirectionDecision(ContractModel):
    recommended_variant: VisualVariantId
    selected_variant: VisualVariantId
    outcome: Literal["recommended", "accepted", "overridden"]
    decided_at: datetime


class StyleDirectionPlan(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    parent_run_id: NonEmptyString
    version: VisualVariantVersion = "style-v1"
    audience: NonEmptyString
    purpose: NonEmptyString
    scene_ids: list[NonEmptyString] = Field(min_length=1, max_length=80)
    allowed_evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=120)
    recommendation_evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=40)
    rationale: str = Field(min_length=1, max_length=240)
    decision: StyleDirectionDecision
    defaults: list[VariantSceneDefaults] = Field(min_length=3, max_length=3)
    overrides: list[VariantOverride] = Field(default_factory=list, max_length=80)
    manual_override_of: NonEmptyString | None = None
    created_at: datetime

    @model_validator(mode="after")
    def references_and_variants_are_valid(self) -> StyleDirectionPlan:
        variants = [item.variant_id for item in self.defaults]
        expected = ["editorial_story", "product_spotlight", "technical_proof"]
        if variants != expected:
            raise ValueError("Style defaults must contain the three fixed variants")
        scenes = set(self.scene_ids)
        if any(item.scene_id not in scenes for item in self.overrides):
            raise ValueError("Style overrides must reference planned scenes")
        if len({item.scene_id for item in self.overrides}) != len(self.overrides):
            raise ValueError("Each scene may have one style override")
        if set(self.recommendation_evidence_refs) - set(self.allowed_evidence_refs):
            raise ValueError("Style recommendation must cite approved project inputs")
        return self


class StyleRunStep(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    parent_run_id: NonEmptyString
    session_id: NonEmptyString
    agent_name: Literal["demodirector_style_director"]
    model: NonEmptyString
    status: Literal["running", "succeeded", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    workflow_runs: int = Field(ge=0, le=1)
    validation_status: Literal["pending", "passed", "failed"]
    output_plan_id: NonEmptyString | None = None
    message: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def state_is_consistent(self) -> StyleRunStep:
        if self.status == "running" and (
            self.completed_at is not None
            or self.workflow_runs != 0
            or self.validation_status != "pending"
        ):
            raise ValueError("Running style steps cannot claim completion")
        if self.status == "succeeded" and (
            self.completed_at is None
            or self.elapsed_ms is None
            or self.workflow_runs != 1
            or self.validation_status != "passed"
            or self.output_plan_id is None
        ):
            raise ValueError("Successful style steps require validated output")
        if self.status == "failed" and (
            self.completed_at is None
            or self.workflow_runs != 1
            or self.validation_status != "failed"
            or self.output_plan_id is not None
        ):
            raise ValueError("Failed style steps cannot expose output")
        return self


class CompiledStyleDirection(ContractModel):
    project_id: NonEmptyString
    plan_id: NonEmptyString
    variant_id: VisualVariantId
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    safe_margin_x: int = Field(gt=0)
    safe_margin_y: int = Field(gt=0)
    deterministic_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
