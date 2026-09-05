from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from demodirector_contracts.models import ContractModel, NonEmptyString

GenerationStage = Literal[
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
]


class GenerationJob(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    status: Literal[
        "queued", "running", "awaiting_approval", "awaiting_retry", "failed", "succeeded"
    ]
    stage: GenerationStage
    completed_stages: list[GenerationStage] = Field(default_factory=list)
    attempts: int = Field(default=0, ge=0, le=3)
    version: int = Field(gt=0)
    created_at: datetime
    updated_at: datetime
    lease_until: datetime | None = None
    message: NonEmptyString
    export_id: str | None = None
    timeline_version: int | None = None


TraceStageKind = Literal[
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
]


class StageContribution(ContractModel):
    key: Literal[
        "pages_inspected",
        "controls_observed",
        "sources_saved",
        "workflow_runs",
        "validated_motion_plans",
        "motion_cues",
        "templates_assigned",
        "product_presence",
        "attention_targets",
        "callouts_proposed",
        "callouts_accepted",
        "style_recommendations",
        "style_overrides",
        "longform_plans",
        "director_steps",
        "parallel_sources_linked",
        "chapters_planned",
        "features_understood",
        "claims_attributed",
        "scenes_planned",
        "actions_planned",
        "actions_executed",
        "interactions_recorded",
        "recordings_created",
        "narration_segments",
        "zooms_created",
        "captions_created",
        "exports_created",
        "output_width",
        "output_height",
        "output_duration",
        "adk_plan_consumed",
    ]
    label: NonEmptyString
    value: int = Field(ge=0)
    unit: NonEmptyString


class GenerationTraceStage(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    kind: TraceStageKind
    sequence: int = Field(ge=0)
    attempt: int = Field(ge=0, le=3)
    retry_count: int = Field(ge=0, le=2)
    status: Literal["pending", "running", "succeeded", "failed", "not_used"]
    label: NonEmptyString
    service: NonEmptyString
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    message: str = Field(min_length=1, max_length=300)
    contributions: list[StageContribution] = Field(default_factory=list)
    output_href: str | None = Field(default=None, pattern=r"^(?:/|#)[^\s]*$")

    @model_validator(mode="after")
    def timing_and_attempt_are_consistent(self) -> "GenerationTraceStage":
        if self.status in {"running", "succeeded", "failed"} and self.attempt < 1:
            raise ValueError("Executed trace stages require an attempt")
        if self.status in {"pending", "not_used"} and self.attempt != 0:
            raise ValueError("Unexecuted trace stages cannot have an attempt")
        if self.status == "running" and (
            self.started_at is None or self.completed_at is not None or self.elapsed_ms is not None
        ):
            raise ValueError("Running trace stage timing is invalid")
        if self.status in {"succeeded", "failed"}:
            if self.started_at is None or self.completed_at is None or self.elapsed_ms is None:
                raise ValueError("Completed trace stages require timing")
            expected = max(0, round((self.completed_at - self.started_at).total_seconds() * 1000))
            if abs(expected - self.elapsed_ms) > 5:
                raise ValueError("Trace elapsed time must match its timestamps")
        unsafe = self.message.casefold()
        if any(marker in unsafe for marker in ("api_key=", "bearer ", "password=", "secret=")):
            raise ValueError("Trace messages cannot contain credentials")
        return self


class GenerationTrace(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    status: Literal["running", "awaiting_approval", "awaiting_retry", "failed", "succeeded"]
    created_at: datetime
    updated_at: datetime
    stages: list[GenerationTraceStage]

    @model_validator(mode="after")
    def stages_are_owned_and_ordered(self) -> "GenerationTrace":
        if any(stage.project_id != self.project_id for stage in self.stages):
            raise ValueError("Trace stages must belong to the project")
        if [stage.sequence for stage in self.stages] != sorted(
            stage.sequence for stage in self.stages
        ):
            raise ValueError("Trace stages must be chronological")
        stage_ids = [stage.id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("Trace stage IDs must be unique")
        return self
