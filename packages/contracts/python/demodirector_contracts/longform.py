from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from demodirector_contracts.models import ContractModel, NonEmptyString, Viewport

LongFormSectionId = Literal[
    "hook",
    "problem",
    "promise",
    "product_walkthrough",
    "trust_technology",
    "editing_control",
    "finished_result",
    "closing",
]
LongFormStepKind = Literal["narrative", "template", "attention", "style"]

SECTION_PROFILE: tuple[tuple[LongFormSectionId, int], ...] = (
    ("hook", 4_000),
    ("problem", 6_000),
    ("promise", 10_000),
    ("product_walkthrough", 75_000),
    ("trust_technology", 35_000),
    ("editing_control", 25_000),
    ("finished_result", 20_000),
    ("closing", 5_000),
)


class LongFormDirectionRequest(ContractModel):
    plan_id: NonEmptyString
    run_id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    parent_motion_run_id: NonEmptyString
    visual_variant: Literal[
        "editorial_story", "product_spotlight", "technical_proof"
    ]
    research_status: Literal["complete", "degraded"]
    evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=160)
    parallel_source_refs: list[NonEmptyString] = Field(default_factory=list, max_length=80)
    product_clip_refs: list[NonEmptyString] = Field(min_length=1, max_length=80)
    target_ids: list[NonEmptyString] = Field(default_factory=list, max_length=160)
    created_at: datetime


class NarrativeSection(ContractModel):
    id: LongFormSectionId
    order: int = Field(ge=0, le=7)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    narration: str = Field(min_length=1, max_length=1_800)
    source_refs: list[NonEmptyString] = Field(min_length=1, max_length=40)
    product_clip_ref: NonEmptyString
    product_visible: Literal[True] = True


class VisualBeat(ContractModel):
    id: NonEmptyString
    section_id: LongFormSectionId
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    purpose: Literal[
        "hook",
        "problem",
        "promise",
        "product_operation",
        "create_action",
        "finished_glimpse",
        "walkthrough",
        "evidence",
        "control",
        "result",
        "closing",
    ]
    template_id: Literal[
        "hook",
        "framed_product",
        "feature_callout",
        "split_explanation",
        "proof_safety",
        "closing",
    ]
    product_clip_ref: NonEmptyString
    target_id: NonEmptyString | None = None
    source_refs: list[NonEmptyString] = Field(default_factory=list, max_length=20)


class CaptureChapter(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    order: int = Field(ge=0, le=7)
    section_ids: list[LongFormSectionId] = Field(min_length=1, max_length=4)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    viewport: Viewport
    account_ref: NonEmptyString
    project_state_ref: NonEmptyString
    style_version: Literal["style-v1"] = "style-v1"
    cursor_continuity_key: NonEmptyString


class ChapterCheckpoint(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    plan_id: NonEmptyString
    chapter_id: NonEmptyString
    status: Literal["pending", "captured", "failed", "approved"]
    attempt: int = Field(ge=0, le=3)
    artifact_ref: NonEmptyString | None = None
    artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    elapsed_ms: int | None = Field(default=None, ge=0)
    replaces_checkpoint_id: NonEmptyString | None = None
    created_at: datetime

    @model_validator(mode="after")
    def artifact_matches_status(self) -> ChapterCheckpoint:
        has_artifact = self.artifact_ref is not None and self.artifact_sha256 is not None
        if self.status in {"captured", "approved"} and not has_artifact:
            raise ValueError("Captured chapters require a validated artifact")
        if self.status in {"pending", "failed"} and has_artifact:
            raise ValueError("Incomplete chapters cannot claim a validated artifact")
        return self


class CondensedInterval(ContractModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    actual_elapsed_ms: int = Field(gt=0)
    label: NonEmptyString = "Time compressed"

    @model_validator(mode="after")
    def preserves_measurement(self) -> CondensedInterval:
        if self.end_ms <= self.start_ms:
            raise ValueError("Condensed interval must have positive display duration")
        if self.actual_elapsed_ms <= self.end_ms - self.start_ms:
            raise ValueError("Actual elapsed time must exceed the condensed display interval")
        return self


class AudioMixPlan(ContractModel):
    narration_lufs: float = Field(default=-16, ge=-24, le=-12)
    music_lufs: float = Field(default=-28, ge=-40, le=-20)
    ducking_db: float = Field(default=-8, ge=-18, le=-3)
    fade_ms: int = Field(default=500, ge=100, le=2_000)


class LongFormVideoPlan(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    adk_run_id: NonEmptyString
    parent_motion_run_id: NonEmptyString
    version: Literal["longform-v1"] = "longform-v1"
    motion_version: Literal["motion-v1"] = "motion-v1"
    style_version: Literal["style-v1"] = "style-v1"
    visual_variant: Literal[
        "editorial_story", "product_spotlight", "technical_proof"
    ]
    duration_ms: Literal[180000] = 180_000
    research_status: Literal["complete", "degraded"]
    evidence_refs: list[NonEmptyString] = Field(min_length=1, max_length=160)
    parallel_source_refs: list[NonEmptyString] = Field(default_factory=list, max_length=80)
    product_clip_refs: list[NonEmptyString] = Field(min_length=1, max_length=80)
    target_ids: list[NonEmptyString] = Field(default_factory=list, max_length=160)
    sections: list[NarrativeSection] = Field(min_length=8, max_length=8)
    beats: list[VisualBeat] = Field(min_length=20, max_length=30)
    chapters: list[CaptureChapter] = Field(min_length=2, max_length=8)
    condensed_intervals: list[CondensedInterval] = Field(default_factory=list, max_length=12)
    audio_mix: AudioMixPlan = Field(default_factory=AudioMixPlan)
    first_product_operation_ms: int = Field(ge=0, le=20_000)
    create_action_ms: int = Field(ge=0, le=30_000)
    finished_glimpse_ms: int = Field(ge=0, le=45_000)
    product_presence_percent: float = Field(ge=90, le=100)
    created_at: datetime

    @model_validator(mode="after")
    def proof_first_structure_is_valid(self) -> LongFormVideoPlan:
        expected_ids = [item[0] for item in SECTION_PROFILE]
        expected_durations = [item[1] for item in SECTION_PROFILE]
        if [item.id for item in self.sections] != expected_ids:
            raise ValueError("Long-form sections must use the fixed narrative order")
        cursor = 0
        for index, section in enumerate(self.sections):
            if section.order != index or section.start_ms != cursor:
                raise ValueError("Long-form sections must be contiguous")
            if section.end_ms - section.start_ms != expected_durations[index]:
                raise ValueError("Long-form section duration does not match the profile")
            cursor = section.end_ms
        if cursor != self.duration_ms:
            raise ValueError("Long-form sections must total exactly 180 seconds")
        words = sum(len(section.narration.split()) for section in self.sections)
        if not 350 <= words <= 430:
            raise ValueError("Long-form narration must contain 350 to 430 words")
        allowed_evidence = set(self.evidence_refs)
        allowed_clips = set(self.product_clip_refs)
        allowed_targets = set(self.target_ids)
        if self.research_status == "complete" and not self.parallel_source_refs:
            raise ValueError("Complete research requires direct Parallel evidence")
        if set(self.parallel_source_refs) - allowed_evidence:
            raise ValueError("Parallel references must be saved project evidence")
        for section in self.sections:
            section_words = len(section.narration.split())
            section_seconds = (section.end_ms - section.start_ms) / 1_000
            if section_words > section_seconds * 3:
                raise ValueError("Narration exceeds the readable speech rate for its section")
            if set(section.source_refs) - allowed_evidence:
                raise ValueError("Narrative sections must cite saved project evidence")
            if section.product_clip_ref not in allowed_clips:
                raise ValueError("Narrative sections must use approved product clips")
        section_by_id = {section.id: section for section in self.sections}
        beat_sections: set[LongFormSectionId] = set()
        for beat in self.beats:
            section = section_by_id[beat.section_id]
            beat_sections.add(beat.section_id)
            if beat.start_ms < section.start_ms or beat.end_ms > section.end_ms:
                raise ValueError("Visual beats must fit their narrative section")
            if beat.end_ms <= beat.start_ms or beat.product_clip_ref not in allowed_clips:
                raise ValueError("Visual beats must use valid time and product footage")
            if beat.target_id is not None and beat.target_id not in allowed_targets:
                raise ValueError("Visual beats must use approved attention targets")
            if set(beat.source_refs) - allowed_evidence:
                raise ValueError("Visual beats must cite saved project evidence")
        if beat_sections != set(expected_ids):
            raise ValueError("Every narrative section requires a visual beat")
        milestone_beats = {
            purpose: [beat for beat in self.beats if beat.purpose == purpose]
            for purpose in ("product_operation", "create_action", "finished_glimpse")
        }
        if any(len(beats) != 1 for beats in milestone_beats.values()):
            raise ValueError("Proof-first milestones require exactly one visual beat")
        if (
            milestone_beats["product_operation"][0].start_ms
            != self.first_product_operation_ms
            or milestone_beats["create_action"][0].start_ms != self.create_action_ms
            or milestone_beats["finished_glimpse"][0].start_ms
            != self.finished_glimpse_ms
        ):
            raise ValueError("Proof-first milestones require matching visual beats")
        chapter_sections = [item for chapter in self.chapters for item in chapter.section_ids]
        if chapter_sections != expected_ids:
            raise ValueError("Capture chapters must cover each section once in order")
        first_chapter = self.chapters[0]
        continuity = (
            first_chapter.viewport,
            first_chapter.account_ref,
            first_chapter.project_state_ref,
            first_chapter.style_version,
            first_chapter.cursor_continuity_key,
        )
        for index, chapter in enumerate(self.chapters):
            chapter_sections_data = [section_by_id[item] for item in chapter.section_ids]
            if (
                chapter.project_id != self.project_id
                or chapter.order != index
                or chapter.start_ms != chapter_sections_data[0].start_ms
                or chapter.end_ms != chapter_sections_data[-1].end_ms
                or chapter.end_ms <= chapter.start_ms
            ):
                raise ValueError("Capture chapter lineage or timing is invalid")
            if (
                chapter.viewport,
                chapter.account_ref,
                chapter.project_state_ref,
                chapter.style_version,
                chapter.cursor_continuity_key,
            ) != continuity:
                raise ValueError("Capture chapters must preserve recording continuity")
        previous_end = 0
        for interval in self.condensed_intervals:
            if interval.start_ms < previous_end or interval.end_ms > self.duration_ms:
                raise ValueError("Condensed intervals must be ordered within the video")
            previous_end = interval.end_ms
        return self

    def narration_word_count(self) -> int:
        return sum(len(section.narration.split()) for section in self.sections)


class LongFormADKStep(ContractModel):
    id: NonEmptyString
    run_id: NonEmptyString
    project_id: NonEmptyString
    kind: LongFormStepKind
    status: Literal["succeeded", "failed"]
    tool_call_count: int = Field(ge=0, le=1)
    artifact_refs: list[NonEmptyString] = Field(default_factory=list, max_length=160)
    output_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    created_at: datetime


class LongFormADKRun(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    parent_motion_run_id: NonEmptyString
    session_id: NonEmptyString
    agent_name: Literal["demodirector_longform_director"]
    model: NonEmptyString
    status: Literal["running", "succeeded", "failed"]
    runner_completed: bool
    workflow_runs: int = Field(ge=0, le=1)
    step_ids: list[NonEmptyString] = Field(default_factory=list, max_length=4)
    output_plan_id: NonEmptyString | None = None
    started_at: datetime
    completed_at: datetime | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    message: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def successful_run_is_complete(self) -> LongFormADKRun:
        if self.status == "succeeded" and (
            not self.runner_completed
            or self.workflow_runs != 1
            or len(self.step_ids) != 4
            or self.output_plan_id is None
            or self.completed_at is None
        ):
            raise ValueError("Successful long-form runs require four completed ADK steps")
        if self.status == "failed" and (self.runner_completed or self.output_plan_id):
            raise ValueError("Failed ADK runs cannot claim consumed output")
        return self


class LongFormValidationReport(ContractModel):
    project_id: NonEmptyString
    plan_id: NonEmptyString
    duration_ms: Literal[180000]
    width: Literal[2560]
    height: Literal[1440]
    fps: Literal[30]
    narration_word_count: int = Field(ge=350, le=430)
    visual_beat_count: int = Field(ge=20, le=30)
    product_presence_percent: float = Field(ge=90, le=100)
    has_audio: bool
    has_captions: bool
    synchronized: bool
    issues: list[NonEmptyString] = Field(default_factory=list)
    passed: bool

    @model_validator(mode="after")
    def passed_matches_checks(self) -> LongFormValidationReport:
        expected = self.has_audio and self.has_captions and self.synchronized and not self.issues
        if self.passed != expected:
            raise ValueError("Long-form validation status must match its checks")
        return self


class CompiledLongFormPlan(ContractModel):
    project_id: NonEmptyString
    plan_id: NonEmptyString
    chapter_count: int = Field(ge=2, le=8)
    beat_count: int = Field(ge=20, le=30)
    deterministic_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
