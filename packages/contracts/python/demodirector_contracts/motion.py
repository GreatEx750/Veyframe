from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from demodirector_contracts.editorial import EditorialTemplateDraft, EditorialTemplatePlan
from demodirector_contracts.models import ContractModel, NonEmptyString

MotionPrimitive = Literal[
    "fade_slide",
    "scale_settle",
    "stagger_text",
    "highlight_reveal",
    "browser_frame_move",
    "background_dim",
]
MotionLayer = Literal[
    "background",
    "product",
    "mask",
    "cursor",
    "callout",
    "captions",
    "transition",
]
MotionEasing = Literal["linear", "standard", "emphasized"]
MotionDesignVersion = Literal["motion-v1"]
MOTION_LAYER_ORDER: tuple[MotionLayer, ...] = (
    "background",
    "product",
    "mask",
    "cursor",
    "callout",
    "captions",
    "transition",
)
UNSAFE_GENERATED_TEXT = re.compile(
    r"(?i)(<\s*script|javascript\s*:|data\s*:\s*text/html|\$\(|`[^`]*`|(?:^|\s)(?:rm|del)\s+-[rf])"
)


class MotionTokenSet(ContractModel):
    version: MotionDesignVersion = "motion-v1"
    font_family: Literal["Inter"] = "Inter"
    title_size: int = Field(default=64, ge=32, le=96)
    body_size: int = Field(default=32, ge=18, le=48)
    fast_ms: int = Field(default=200, ge=100, le=400)
    normal_ms: int = Field(default=600, ge=300, le=900)
    deliberate_ms: int = Field(default=1200, ge=700, le=1800)
    standard_easing: Literal["cubic-bezier(0.22, 1, 0.36, 1)"] = (
        "cubic-bezier(0.22, 1, 0.36, 1)"
    )
    emphasized_easing: Literal["cubic-bezier(0.16, 1, 0.3, 1)"] = (
        "cubic-bezier(0.16, 1, 0.3, 1)"
    )
    background: Literal["#111214"] = "#111214"
    surface: Literal["#1B1D20"] = "#1B1D20"
    text: Literal["#F5F6F7"] = "#F5F6F7"
    accent: Literal["#86E1A8"] = "#86E1A8"
    layer_order: list[MotionLayer] = Field(default_factory=lambda: list(MOTION_LAYER_ORDER))

    @model_validator(mode="after")
    def tokens_are_ordered(self) -> MotionTokenSet:
        if not self.fast_ms < self.normal_ms < self.deliberate_ms:
            raise ValueError("Motion durations must increase from fast to deliberate")
        if tuple(self.layer_order) != MOTION_LAYER_ORDER:
            raise ValueError("Motion layer order is fixed for deterministic composition")
        return self


class MotionCueDraft(ContractModel):
    scene_id: NonEmptyString
    primitive: MotionPrimitive
    layer: MotionLayer
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    easing: MotionEasing
    text: str | None = Field(default=None, max_length=120)
    product_clip_ref: str = Field(pattern=r"^scene:[A-Za-z0-9._:-]+$")

    @field_validator("text")
    @classmethod
    def text_is_content_only(cls, value: str | None) -> str | None:
        if value is not None and UNSAFE_GENERATED_TEXT.search(value):
            raise ValueError("Motion text cannot contain executable content")
        return value

    @model_validator(mode="after")
    def interval_and_text_are_valid(self) -> MotionCueDraft:
        if self.end_ms <= self.start_ms:
            raise ValueError("Motion cue end must follow its start")
        if self.primitive in {"stagger_text", "highlight_reveal"} and not self.text:
            raise ValueError("Text motion primitives require text")
        return self


class MotionCue(MotionCueDraft):
    id: NonEmptyString


class MotionDirectionDraft(ContractModel):
    summary: str = Field(min_length=1, max_length=240)
    cues: list[MotionCueDraft] = Field(min_length=1, max_length=80)
    editorial: EditorialTemplateDraft | None = None


class MotionDirectionRequest(ContractModel):
    project_id: NonEmptyString
    job_id: NonEmptyString
    storyboard_id: NonEmptyString
    storyboard_version: int = Field(gt=0)
    duration_ms: int = Field(gt=0, le=600_000)
    evidence_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_ids: list[NonEmptyString] = Field(max_length=100)
    scene_ids: list[NonEmptyString] = Field(min_length=1, max_length=80)
    product_clip_refs: list[str] = Field(min_length=1, max_length=80)
    created_at: datetime

    @model_validator(mode="after")
    def references_are_unique_and_bounded(self) -> MotionDirectionRequest:
        for values, label in (
            (self.source_ids, "source"),
            (self.scene_ids, "scene"),
            (self.product_clip_refs, "product clip"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Motion request {label} references must be unique")
        expected_clips = {f"scene:{scene_id}" for scene_id in self.scene_ids}
        if set(self.product_clip_refs) - expected_clips:
            raise ValueError("Product clip references must identify requested scenes")
        return self


class MotionDirectionPlan(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    run_id: NonEmptyString
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    design_tokens: MotionTokenSet
    duration_ms: int = Field(gt=0, le=600_000)
    scene_ids: list[NonEmptyString] = Field(min_length=1, max_length=80)
    product_clip_refs: list[str] = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=240)
    cues: list[MotionCue] = Field(min_length=1, max_length=80)
    editorial_plan: EditorialTemplatePlan | None = None
    created_at: datetime

    @model_validator(mode="after")
    def cues_are_owned_ordered_and_non_overlapping(self) -> MotionDirectionPlan:
        if len(self.scene_ids) != len(set(self.scene_ids)):
            raise ValueError("Motion plan scene references must be unique")
        if len(self.product_clip_refs) != len(set(self.product_clip_refs)):
            raise ValueError("Motion plan product clip references must be unique")
        ids = [cue.id for cue in self.cues]
        if len(ids) != len(set(ids)):
            raise ValueError("Motion cue IDs must be unique")
        scenes = set(self.scene_ids)
        clips = set(self.product_clip_refs)
        if any(cue.scene_id not in scenes for cue in self.cues):
            raise ValueError("Motion cues may reference planned scenes only")
        if any(cue.product_clip_ref not in clips for cue in self.cues):
            raise ValueError("Motion cues may reference planned product clips only")
        if any(cue.end_ms > self.duration_ms for cue in self.cues):
            raise ValueError("Motion cues must fit the planned duration")
        ordered = sorted(self.cues, key=lambda cue: (cue.layer, cue.start_ms, cue.end_ms))
        previous_by_layer: dict[MotionLayer, MotionCue] = {}
        for cue in ordered:
            previous = previous_by_layer.get(cue.layer)
            if previous is not None and cue.start_ms < previous.end_ms:
                raise ValueError("Motion cues on the same layer cannot overlap")
            previous_by_layer[cue.layer] = cue
        return self


class ADKMotionRun(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    session_id: NonEmptyString
    agent_name: Literal["demodirector_motion_director"]
    model: NonEmptyString
    status: Literal["running", "succeeded", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    retry_count: int = Field(ge=0, le=2)
    workflow_runs: int = Field(ge=0, le=1)
    input_artifact_ids: list[NonEmptyString] = Field(min_length=1, max_length=120)
    output_plan_id: NonEmptyString | None = None
    validation_status: Literal["pending", "passed", "failed"]
    message: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def execution_state_is_consistent(self) -> ADKMotionRun:
        if self.status == "running":
            if self.completed_at is not None or self.elapsed_ms is not None:
                raise ValueError("Running ADK motion runs cannot have completion timing")
            if self.validation_status != "pending" or self.output_plan_id is not None:
                raise ValueError("Running ADK motion runs cannot have validated output")
        else:
            if self.completed_at is None or self.elapsed_ms is None:
                raise ValueError("Completed ADK motion runs require timing")
            expected = max(
                0,
                round((self.completed_at - self.started_at).total_seconds() * 1000),
            )
            if abs(expected - self.elapsed_ms) > 5:
                raise ValueError("ADK motion elapsed time must match its timestamps")
        if self.status == "succeeded" and (
            self.workflow_runs != 1
            or self.validation_status != "passed"
            or self.output_plan_id is None
        ):
            raise ValueError("Successful ADK motion runs require one validated output")
        if self.status == "failed" and (
            self.validation_status != "failed" or self.output_plan_id is not None
        ):
            raise ValueError("Failed ADK motion runs cannot expose an output plan")
        unsafe = self.message.casefold()
        if any(marker in unsafe for marker in ("api_key=", "bearer ", "password=", "secret=")):
            raise ValueError("ADK motion messages cannot contain credentials")
        return self


class CompiledMotionCue(ContractModel):
    cue_id: NonEmptyString
    primitive: MotionPrimitive
    layer: MotionLayer
    layer_index: int = Field(ge=0, le=6)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    easing: MotionEasing


class CompiledMotionComposition(ContractModel):
    project_id: NonEmptyString
    plan_id: NonEmptyString
    design_version: Literal["motion-v1"]
    width: int = Field(ge=320, le=3840)
    height: int = Field(ge=180, le=2160)
    fps: int = Field(ge=12, le=60)
    duration_ms: int = Field(gt=0)
    cues: list[CompiledMotionCue]
    deterministic_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
