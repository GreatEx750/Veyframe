from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from demodirector_contracts.models import ContractModel, EditOperation, NonEmptyString

VideoReviewDimension = Literal[
    "visual_clarity",
    "narration_sync",
    "caption_readability",
    "pacing",
    "camera_quality",
    "cta_effectiveness",
]
DIMENSIONS = (
    "visual_clarity",
    "narration_sync",
    "caption_readability",
    "pacing",
    "camera_quality",
    "cta_effectiveness",
)
VideoReviewStatus = Literal["running", "succeeded", "failed"]


class MediaEvidence(ContractModel):
    id: NonEmptyString
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    media_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class VideoReviewFinding(ContractModel):
    id: NonEmptyString
    dimension: VideoReviewDimension
    severity: Literal["low", "medium", "high"]
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    observation: str = Field(min_length=1, max_length=800)
    evidence_summary: str = Field(min_length=1, max_length=800)
    evidence_ids: list[NonEmptyString] = Field(min_length=1, max_length=4)
    repair_category: Literal[
        "camera", "caption", "pacing", "narration", "cta", "recapture", "manual"
    ]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end_ms <= self.start_ms:
            raise ValueError("Finding timestamps must be ordered")
        return self


class VideoReviewScore(ContractModel):
    dimension: VideoReviewDimension
    score: int = Field(ge=0, le=100)
    explanation: str = Field(min_length=1, max_length=800)
    finding_ids: list[NonEmptyString] = Field(max_length=12)


class CriticOutput(ContractModel):
    scores: list[VideoReviewScore] = Field(min_length=6, max_length=6)
    findings: list[VideoReviewFinding] = Field(max_length=12)

    @model_validator(mode="after")
    def complete(self) -> Self:
        if sorted(s.dimension for s in self.scores) != sorted(DIMENSIONS):
            raise ValueError("Each quality dimension must be scored exactly once")
        findings = {f.id: f for f in self.findings}
        if len(findings) != len(self.findings):
            raise ValueError("Finding IDs must be unique")
        for score in self.scores:
            if set(score.finding_ids) != {
                f.id for f in self.findings if f.dimension == score.dimension
            }:
                raise ValueError("Scores must reference their dimension's findings exactly")
        return self


class VideoReview(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    export_id: NonEmptyString
    timeline_version: int = Field(gt=0)
    status: VideoReviewStatus
    model_name: NonEmptyString
    prompt_version: NonEmptyString
    created_at: datetime
    duration_ms: int = Field(gt=0, le=180_000)
    evidence: list[MediaEvidence] = Field(min_length=1, max_length=180)
    result: CriticOutput | None = None
    overall_score: float | None = Field(default=None, ge=0, le=100)
    error: str | None = None
    model_calls: int = Field(ge=0, le=1)
    retryable: bool = False

    @model_validator(mode="after")
    def grounded(self) -> Self:
        evidence = {e.id: e for e in self.evidence}
        if len(evidence) != len(self.evidence) or any(
            e.end_ms <= e.start_ms or e.end_ms > self.duration_ms for e in self.evidence
        ):
            raise ValueError("Invalid media evidence windows")
        if self.status == "succeeded":
            if self.result is None or self.error or self.retryable:
                raise ValueError("Successful reviews require a result and no failure")
            expected = round(sum(s.score for s in self.result.scores) / 6, 2)
            if self.overall_score != expected:
                raise ValueError("Overall score must be the mean of the six dimensions")
            for finding in self.result.findings:
                if finding.end_ms > self.duration_ms or any(
                    eid not in evidence
                    or evidence[eid].start_ms >= finding.end_ms
                    or evidence[eid].end_ms <= finding.start_ms
                    for eid in finding.evidence_ids
                ):
                    raise ValueError("Findings must cite overlapping submitted media evidence")
        elif self.result is not None or self.overall_score is not None:
            raise ValueError("Incomplete reviews cannot claim scores")
        if self.status == "failed" and (not self.error or not self.retryable):
            raise ValueError("Failed reviews must expose a retryable error")
        return self


class OptimizationProposal(ContractModel):
    operations: list[EditOperation] = Field(max_length=3)
    finding_ids: list[NonEmptyString] = Field(max_length=3)
    explanation: NonEmptyString
    unsupported_findings: list[NonEmptyString] = Field(default_factory=list)


class OptimizationRun(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    review_id: NonEmptyString
    before_export_id: NonEmptyString
    before_version: int = Field(gt=0)
    before_score: float = Field(ge=0, le=100)
    proposal: OptimizationProposal
    status: Literal["proposed", "running", "succeeded", "failed", "cancelled"]
    stop_reason: Literal[
        "awaiting_approval",
        "target_reached",
        "improved",
        "no_improvement",
        "unsupported",
        "render_failed",
        "review_failed",
        "version_conflict",
        "cancelled",
        "apply_failed",
        "budget_limit",
    ]
    after_version: int | None = None
    after_export_id: str | None = None
    after_review_id: str | None = None
    after_score: float | None = Field(default=None, ge=0, le=100)
    score_delta: float | None = None
    cycles: int = Field(default=0, ge=0, le=1)
    model_calls: int = Field(default=0, ge=0, le=1)
    created_at: datetime
    message: NonEmptyString
