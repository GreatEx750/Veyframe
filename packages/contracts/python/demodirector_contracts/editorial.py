from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from demodirector_contracts.models import ContractModel, NonEmptyString

EditorialTemplateId = Literal[
    "hook",
    "framed_product",
    "feature_callout",
    "split_explanation",
    "proof_safety",
    "closing",
]
ProductClipRef = str
ProductTreatment = Literal[
    "full_focus",
    "framed_product",
    "split_explanation",
    "moving_background",
]
NarrativeSection = Literal[
    "hook",
    "problem",
    "promise",
    "product_walkthrough",
    "trust_technology",
    "editing_control",
    "finished_result",
    "closing",
]
EDITORIAL_TEMPLATE_IDS: tuple[EditorialTemplateId, ...] = (
    "hook",
    "framed_product",
    "feature_callout",
    "split_explanation",
    "proof_safety",
    "closing",
)


class EditorialTemplateCatalog(ContractModel):
    version: Literal["editorial-v1"] = "editorial-v1"
    template_ids: list[EditorialTemplateId] = Field(
        default_factory=lambda: list(EDITORIAL_TEMPLATE_IDS)
    )

    @model_validator(mode="after")
    def contains_exact_catalog(self) -> EditorialTemplateCatalog:
        if tuple(self.template_ids) != EDITORIAL_TEMPLATE_IDS:
            raise ValueError("Editorial template catalog is fixed and versioned")
        return self


class RenderSafeCrop(ContractModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def fits_frame(self) -> RenderSafeCrop:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Editorial crop must fit the product frame")
        return self


class EditorialSceneDraft(ContractModel):
    scene_id: NonEmptyString
    section: NarrativeSection
    template_id: EditorialTemplateId
    product_clip_ref: str = Field(pattern=r"^scene:[A-Za-z0-9._:-]+$")
    product_treatment: ProductTreatment
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    eyebrow: str | None = Field(default=None, max_length=32)
    title: str = Field(min_length=1, max_length=80)
    body: str | None = Field(default=None, max_length=180)
    crop: RenderSafeCrop

    @model_validator(mode="after")
    def has_valid_hold(self) -> EditorialSceneDraft:
        if self.end_ms - self.start_ms < 1_000:
            raise ValueError("Editorial scenes require a one-second minimum hold")
        return self


class EditorialScene(EditorialSceneDraft):
    id: NonEmptyString


class EditorialTemplateDraft(ContractModel):
    summary: str = Field(min_length=1, max_length=240)
    scenes: list[EditorialSceneDraft] = Field(min_length=1, max_length=80)


class PresenceViolation(ContractModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def end_follows_start(self) -> PresenceViolation:
        if self.end_ms <= self.start_ms:
            raise ValueError("Presence violation end must follow start")
        return self


class ProductPresenceReport(ContractModel):
    duration_ms: int = Field(gt=0)
    visible_product_ms: int = Field(ge=0)
    percentage: float = Field(ge=0, le=100)
    violating_intervals: list[PresenceViolation] = Field(default_factory=list)

    @model_validator(mode="after")
    def meets_policy(self) -> ProductPresenceReport:
        expected = round(self.visible_product_ms / self.duration_ms * 100, 3)
        if abs(expected - self.percentage) > 0.01:
            raise ValueError("Product presence percentage must match visible duration")
        if self.percentage < 90:
            raise ValueError("Product footage must remain visible in at least 90% of frames")
        return self


class EditorialTemplatePlan(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    job_id: NonEmptyString
    run_id: NonEmptyString
    motion_plan_id: NonEmptyString
    catalog_version: Literal["editorial-v1"]
    design_version: Literal["motion-v1"]
    duration_ms: int = Field(gt=0, le=600_000)
    scene_ids: list[NonEmptyString] = Field(min_length=1, max_length=80)
    product_clip_refs: list[str] = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=240)
    scenes: list[EditorialScene] = Field(min_length=1, max_length=80)
    created_at: datetime

    @model_validator(mode="after")
    def validates_owned_contiguous_product_scenes(self) -> EditorialTemplatePlan:
        if [scene.scene_id for scene in self.scenes] != self.scene_ids:
            raise ValueError("Editorial scenes must cover every requested scene in order")
        clips = set(self.product_clip_refs)
        if any(scene.product_clip_ref not in clips for scene in self.scenes):
            raise ValueError("Editorial scenes may use project-owned product clips only")
        expected_start = 0
        for scene in self.scenes:
            if scene.start_ms != expected_start:
                raise ValueError("Editorial scenes must be contiguous")
            expected_start = scene.end_ms
        if expected_start != self.duration_ms:
            raise ValueError("Editorial scenes must cover the complete video")
        return self

    def product_presence(self) -> ProductPresenceReport:
        visible = sum(scene.end_ms - scene.start_ms for scene in self.scenes)
        return ProductPresenceReport(
            duration_ms=self.duration_ms,
            visible_product_ms=min(visible, self.duration_ms),
            percentage=round(min(visible, self.duration_ms) / self.duration_ms * 100, 3),
            violating_intervals=[],
        )


class CompiledEditorialScene(ContractModel):
    scene_id: NonEmptyString
    template_id: EditorialTemplateId
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    safe_margin_x: int = Field(gt=0)
    safe_margin_y: int = Field(gt=0)


class CompiledEditorialComposition(ContractModel):
    project_id: NonEmptyString
    plan_id: NonEmptyString
    width: int = Field(ge=320, le=3840)
    height: int = Field(ge=180, le=2160)
    fps: int = Field(ge=12, le=60)
    scenes: list[CompiledEditorialScene]
    product_presence: ProductPresenceReport
    deterministic_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
