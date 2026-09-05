from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from demodirector_contracts.models import ContractModel, NonEmptyString, Viewport

CalloutType = Literal[
    "label_connector",
    "spotlight",
    "numbered_step",
    "feature_card",
    "status_badge",
    "metric_card",
    "before_after",
]
CalloutPlacement = Literal["top_left", "top_right", "bottom_left", "bottom_right"]
CaptionEmphasisStyle = Literal["weight", "underline", "accent"]


class NormalizedRect(ContractModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def fits_viewport(self) -> NormalizedRect:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Normalized target rectangle must fit the viewport")
        return self


class TargetObservation(ContractModel):
    id: NonEmptyString
    scene_id: NonEmptyString
    locator_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    timestamp_ms: int = Field(ge=0)
    rect: NormalizedRect
    viewport: Viewport


class AnimatedCalloutDraft(ContractModel):
    target_id: NonEmptyString
    callout_type: CalloutType
    placement: CalloutPlacement
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=72)

    @model_validator(mode="after")
    def has_readable_duration(self) -> AnimatedCalloutDraft:
        if not 600 <= self.end_ms - self.start_ms <= 8_000:
            raise ValueError("Callout duration must be between 0.6 and 8 seconds")
        return self


class AnimatedCallout(AnimatedCalloutDraft):
    id: NonEmptyString


class CaptionEmphasis(ContractModel):
    statement_id: NonEmptyString
    word: str = Field(min_length=1, max_length=32)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    style: CaptionEmphasisStyle

    @model_validator(mode="after")
    def has_valid_interval(self) -> CaptionEmphasis:
        if self.end_ms <= self.start_ms or self.end_ms - self.start_ms > 2_000:
            raise ValueError("Caption emphasis interval is invalid")
        return self


class AttentionDraft(ContractModel):
    summary: str = Field(min_length=1, max_length=240)
    callouts: list[AnimatedCalloutDraft] = Field(max_length=40)
    caption_emphasis: list[CaptionEmphasis] = Field(max_length=80)


class AttentionRequest(ContractModel):
    project_id: NonEmptyString
    job_id: NonEmptyString
    parent_run_id: NonEmptyString
    duration_ms: int = Field(gt=0, le=600_000)
    target_ids: list[NonEmptyString] = Field(max_length=120)
    narration_statement_ids: list[NonEmptyString] = Field(max_length=120)
    created_at: datetime


class AttentionPlan(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    parent_run_id: NonEmptyString
    manual_override_of: NonEmptyString | None = None
    duration_ms: int = Field(gt=0, le=600_000)
    targets: list[TargetObservation] = Field(max_length=120)
    narration_statement_ids: list[NonEmptyString] = Field(max_length=120)
    summary: str = Field(min_length=1, max_length=240)
    callouts: list[AnimatedCallout] = Field(max_length=40)
    caption_emphasis: list[CaptionEmphasis] = Field(max_length=80)
    created_at: datetime

    @model_validator(mode="after")
    def references_are_visible_and_non_competing(self) -> AttentionPlan:
        targets = {target.id for target in self.targets}
        if any(callout.target_id not in targets for callout in self.callouts):
            raise ValueError("Callouts must reference an observed target")
        if any(callout.end_ms > self.duration_ms for callout in self.callouts):
            raise ValueError("Callouts must fit the video duration")
        statements = set(self.narration_statement_ids)
        if any(item.statement_id not in statements for item in self.caption_emphasis):
            raise ValueError("Caption emphasis must reference approved narration")
        ordered = sorted(self.callouts, key=lambda item: item.start_ms)
        if any(
            current.start_ms < previous.end_ms
            for previous, current in zip(ordered, ordered[1:], strict=False)
        ):
            raise ValueError("Only one primary callout may appear at a time")
        return self


class AttentionRunStep(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    parent_run_id: NonEmptyString
    session_id: NonEmptyString
    agent_name: Literal["demodirector_attention_director"]
    model: NonEmptyString
    status: Literal["running", "succeeded", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    workflow_runs: int = Field(ge=0, le=1)
    input_target_count: int = Field(ge=0)
    proposed_cue_count: int = Field(ge=0)
    accepted_cue_count: int = Field(ge=0)
    validation_status: Literal["pending", "passed", "failed"]
    output_plan_id: NonEmptyString | None = None
    message: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def state_is_consistent(self) -> AttentionRunStep:
        if self.status == "running" and (
            self.completed_at is not None
            or self.elapsed_ms is not None
            or self.workflow_runs != 0
            or self.validation_status != "pending"
            or self.output_plan_id is not None
        ):
            raise ValueError("Running attention step cannot claim completion")
        if self.status == "succeeded" and (
            self.completed_at is None
            or self.elapsed_ms is None
            or self.workflow_runs != 1
            or self.validation_status != "passed"
            or self.output_plan_id is None
            or self.accepted_cue_count > self.proposed_cue_count
        ):
            raise ValueError("Successful attention step requires one validated output")
        if self.status == "failed" and (
            self.completed_at is None
            or self.elapsed_ms is None
            or self.workflow_runs != 1
            or self.validation_status != "failed"
            or self.output_plan_id is not None
        ):
            raise ValueError("Failed attention step cannot expose validated output")
        if any(
            marker in self.message.casefold()
            for marker in ("api_key=", "bearer ", "password=", "secret=")
        ):
            raise ValueError("Attention run message cannot contain credentials")
        return self


class CollisionReport(ContractModel):
    callout_id: NonEmptyString
    placement: CalloutPlacement
    inside_safe_area: bool
    overlaps_caption: bool
    overlaps_target: bool


class CompiledCallout(ContractModel):
    id: NonEmptyString
    callout_type: CalloutType
    placement: CalloutPlacement
    anchor_x: int = Field(ge=0)
    anchor_y: int = Field(ge=0)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)


class CompiledAttentionPlan(ContractModel):
    project_id: NonEmptyString
    plan_id: NonEmptyString
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(gt=0)
    callouts: list[CompiledCallout]
    collisions: list[CollisionReport]
    deterministic_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
