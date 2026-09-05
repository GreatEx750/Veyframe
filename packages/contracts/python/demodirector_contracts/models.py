from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, model_validator

NonEmptyString = Annotated[str, Field(min_length=1)]
Milliseconds = Annotated[int, Field(ge=0)]
JsonScalar = str | int | float | bool | None

CaptureActionType = Literal[
    "navigate",
    "click",
    "fill",
    "select",
    "scroll",
    "wait_for",
    "assert_visible",
    "upload",
]
LocatorStrategy = Literal[
    "role",
    "label",
    "text",
    "test_id",
    "css",
    "xpath",
    "placeholder",
    "alt_text",
]
EditOperationType = Literal[
    "trim_scene",
    "delete_scene",
    "reorder_scene",
    "update_narration",
    "add_zoom",
    "update_zoom",
    "delete_zoom",
    "add_caption",
    "update_caption",
    "change_voice_config",
    "change_cta_text",
    "change_presentation",
]
ProjectStatus = Literal[
    "draft",
    "storyboarding",
    "ready",
    "capturing",
    "editing",
    "rendering",
    "published",
    "failed",
]
ProjectJobStatus = Literal["idle", "queued", "running", "succeeded", "failed"]
UserRole = Literal["customer", "judge_demo", "system"]
DemoMode = Literal["product_demo", "presentation_demo"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BoundingBox(ContractModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class Viewport(ContractModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    scroll_x: float = Field(default=0, ge=0)
    scroll_y: float = Field(default=0, ge=0)
    device_scale_factor: float = Field(default=1, gt=0)


class Project(ContractModel):
    id: NonEmptyString
    name: NonEmptyString
    website_url: HttpUrl
    product_summary: NonEmptyString
    audience: NonEmptyString
    tone: NonEmptyString
    requested_duration_seconds: int = Field(gt=0)
    cta: NonEmptyString
    brand_kit_id: NonEmptyString | None = None
    demo_mode: DemoMode = "product_demo"
    zoom_enabled: bool = True
    status: ProjectStatus = "draft"
    job_status: ProjectJobStatus = "idle"
    owner_user_id: NonEmptyString = "system"
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def presentation_demo_uses_mvp_duration(self) -> Project:
        if self.demo_mode == "presentation_demo" and self.requested_duration_seconds != 120:
            raise ValueError("Presentation Demo must be exactly 120 seconds for the MVP")
        return self


class UserIdentity(ContractModel):
    user_id: NonEmptyString
    email: NonEmptyString
    role: UserRole = "customer"
    email_verified: bool = False


class UserProfile(ContractModel):
    user_id: NonEmptyString
    email: NonEmptyString
    role: UserRole = "customer"
    created_at: datetime
    updated_at: datetime


class SessionSummary(ContractModel):
    session_id: NonEmptyString
    user: UserIdentity
    created_at: datetime
    expires_at: datetime


class SignupRequest(ContractModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=128)


class SignupResult(ContractModel):
    status: Literal["signed_in", "verification_required"]
    session: SessionSummary | None = None
    session_token: NonEmptyString | None = None
    message: NonEmptyString

    @model_validator(mode="after")
    def signed_in_results_include_session(self) -> SignupResult:
        if self.status == "signed_in" and (self.session is None or self.session_token is None):
            raise ValueError("signed-in signup results require a session and token")
        if self.status == "verification_required" and (
            self.session is not None or self.session_token is not None
        ):
            raise ValueError("verification-required signup results may not include a session")
        return self


class AuthError(ContractModel):
    code: Literal[
        "authentication_required",
        "invalid_credentials",
        "verification_required",
        "account_unavailable",
        "session_expired",
        "session_revoked",
        "rate_limited",
    ]
    message: NonEmptyString


class LoginRequest(ContractModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=1, max_length=128)
    return_to: str = Field(default="/projects", min_length=1, max_length=500)

    @model_validator(mode="after")
    def return_path_is_internal(self) -> LoginRequest:
        if not self.return_to.startswith("/") or self.return_to.startswith("//"):
            raise ValueError("return_to must be an internal application path")
        return self


class LoginResult(ContractModel):
    session: SessionSummary
    session_token: NonEmptyString
    landing_path: NonEmptyString


class SessionState(ContractModel):
    status: Literal["active", "absent", "expired", "revoked"]
    session: SessionSummary | None = None

    @model_validator(mode="after")
    def active_state_has_session(self) -> SessionState:
        if self.status == "active" and self.session is None:
            raise ValueError("active session state requires a session")
        if self.status != "active" and self.session is not None:
            raise ValueError("inactive session state may not include a session")
        return self


class LogoutResult(ContractModel):
    status: Literal["logged_out", "already_absent"]
    reason: Literal["user_requested", "absent", "expired", "revoked"]
    message: NonEmptyString


class ReauthenticationRequired(ContractModel):
    required: bool
    reason: Literal["expired", "revoked", "sensitive_operation"]
    message: NonEmptyString


class JudgeSandbox(ContractModel):
    sandbox_id: NonEmptyString
    project_id: NonEmptyString
    owner_user_id: NonEmptyString
    fixture_version: NonEmptyString
    created_at: datetime
    expires_at: datetime


class JudgeSession(ContractModel):
    session: SessionSummary
    session_token: NonEmptyString
    sandbox: JudgeSandbox
    capabilities: list[
        Literal[
            "view_project",
            "explore_editor",
            "preview_fixture",
            "reset_sandbox",
            "create_project",
            "generate_demo",
            "edit_timeline",
            "export_video",
        ]
    ] = Field(min_length=1)
    landing_path: NonEmptyString


class JudgeDemoHealth(ContractModel):
    enabled: bool
    ready: bool
    fixture_version: NonEmptyString
    message: NonEmptyString


class ResearchSource(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    title: NonEmptyString
    url: HttpUrl
    snippet: NonEmptyString
    source_type: Literal["website", "partner_search", "user"]
    retrieved_at: datetime


class InspectedElement(ContractModel):
    kind: Literal["button", "link", "input", "select", "textarea"]
    tag: NonEmptyString
    text: str = ""
    accessible_name: str = ""
    href: str | None = None
    input_type: str | None = None
    label: str | None = None


class InspectedPage(ContractModel):
    title: str
    url: HttpUrl
    headings: list[str] = Field(default_factory=list)
    elements: list[InspectedElement] = Field(default_factory=list)
    screenshot_path: NonEmptyString
    viewport: Viewport


class WebsiteInspection(ContractModel):
    project_id: NonEmptyString
    pages: list[InspectedPage] = Field(default_factory=list)
    max_pages: int = Field(gt=0)
    max_depth: int = Field(ge=0)
    warning: str | None = None


class ProductFeature(ContractModel):
    id: NonEmptyString
    name: NonEmptyString
    description: NonEmptyString
    source_ids: list[NonEmptyString] = Field(default_factory=list)
    user_provided: bool = False

    @model_validator(mode="after")
    def has_grounding(self) -> ProductFeature:
        if not self.user_provided and not self.source_ids:
            raise ValueError("external product features require at least one source ID")
        return self


class SuggestedDemoFlow(ContractModel):
    title: NonEmptyString
    steps: list[NonEmptyString] = Field(min_length=1)
    feature_ids: list[NonEmptyString] = Field(default_factory=list)


class GroundedClaim(ContractModel):
    text: NonEmptyString
    source_ids: list[NonEmptyString] = Field(default_factory=list)
    user_provided: bool = False

    @model_validator(mode="after")
    def has_grounding(self) -> GroundedClaim:
        if not self.user_provided and not self.source_ids:
            raise ValueError("external claims require at least one source ID")
        return self


class ProductUnderstanding(ContractModel):
    project_id: NonEmptyString
    value_proposition: NonEmptyString
    audience: NonEmptyString
    features: list[ProductFeature] = Field(default_factory=list)
    suggested_demo_flows: list[SuggestedDemoFlow] = Field(default_factory=list)
    claims: list[GroundedClaim] = Field(default_factory=list)

    @model_validator(mode="after")
    def identifiers_are_unique_and_referenced(self) -> ProductUnderstanding:
        feature_ids = [feature.id for feature in self.features]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("product feature IDs must be unique")
        known = set(feature_ids)
        if any(set(flow.feature_ids) - known for flow in self.suggested_demo_flows):
            raise ValueError("demo flows may reference known feature IDs only")
        return self


class CaptureAction(ContractModel):
    type: CaptureActionType
    locator_strategy: LocatorStrategy | None = None
    locator: NonEmptyString | None = None
    value: JsonScalar = None
    description: NonEmptyString


class CapturePlan(ContractModel):
    start_url: HttpUrl
    actions: list[CaptureAction] = Field(default_factory=list)
    success_assertions: list[CaptureAction] = Field(default_factory=list)
    timeout_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def assertions_are_safe(self) -> CapturePlan:
        if any(action.type != "assert_visible" for action in self.success_assertions):
            raise ValueError("success assertions must use the assert_visible action type")
        return self


class Scene(ContractModel):
    id: NonEmptyString
    storyboard_id: NonEmptyString
    order: int = Field(ge=0)
    title: NonEmptyString
    objective: NonEmptyString
    narration: NonEmptyString
    source_ids: list[NonEmptyString] = Field(default_factory=list)
    capture_plan: CapturePlan
    expected_evidence: list[NonEmptyString] = Field(default_factory=list)
    duration_seconds: float = Field(gt=0)


class Storyboard(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    version: int = Field(gt=0)
    total_duration_seconds: float = Field(gt=0)
    status: Literal["draft", "approved", "capturing", "captured", "failed"]
    scenes: list[Scene] = Field(default_factory=list)


class InteractionEvent(ContractModel):
    timestamp_ms: Milliseconds
    event_type: CaptureActionType
    scene_id: NonEmptyString | None = None
    locator: NonEmptyString | None = None
    x: float | None = Field(default=None, ge=0)
    y: float | None = Field(default=None, ge=0)
    bounding_box: BoundingBox | None = None
    viewport: Viewport

    @model_validator(mode="after")
    def coordinates_fit_viewport(self) -> InteractionEvent:
        if self.x is not None and self.x > self.viewport.width:
            raise ValueError("x coordinate must fit within viewport")
        if self.y is not None and self.y > self.viewport.height:
            raise ValueError("y coordinate must fit within viewport")
        return self


class CaptureActionResult(ContractModel):
    action_index: int = Field(ge=0)
    action_type: CaptureActionType
    status: Literal["succeeded", "failed"]
    elapsed_ms: Milliseconds
    message: NonEmptyString


class SceneCaptureResult(ContractModel):
    scene_id: NonEmptyString
    status: Literal["succeeded", "failed"]
    retryable: bool
    duration_ms: Milliseconds
    raw_clip_path: NonEmptyString | None = None
    screenshot_paths: list[NonEmptyString] = Field(default_factory=list)
    action_results: list[CaptureActionResult] = Field(default_factory=list)
    interaction_events: list[InteractionEvent] = Field(default_factory=list)
    logs: list[NonEmptyString] = Field(default_factory=list)
    error: NonEmptyString | None = None

    @model_validator(mode="after")
    def events_fit_clip_clock(self) -> SceneCaptureResult:
        if any(event.timestamp_ms > self.duration_ms for event in self.interaction_events):
            raise ValueError("interaction timestamps may not exceed capture duration")
        return self


class NarrationVoiceConfig(ContractModel):
    voice_name: NonEmptyString = "Kore"
    language_code: NonEmptyString = "en-US"
    pace: Literal["slow", "normal", "fast"] = "normal"


class NarrationSegment(ContractModel):
    scene_id: NonEmptyString
    order: int = Field(ge=0)
    text: NonEmptyString
    audio_path: NonEmptyString
    duration_ms: int = Field(gt=0)


class NarrationJobResult(ContractModel):
    status: Literal["succeeded", "failed"]
    retryable: bool
    voice_config: NarrationVoiceConfig
    segments: list[NarrationSegment] = Field(default_factory=list)
    preserved_capture_paths: list[NonEmptyString] = Field(default_factory=list)
    error: NonEmptyString | None = None

    @model_validator(mode="after")
    def segment_order_is_deterministic(self) -> NarrationJobResult:
        orders = [segment.order for segment in self.segments]
        if orders != list(range(len(orders))):
            raise ValueError("narration segment order must be contiguous")
        if len({segment.scene_id for segment in self.segments}) != len(self.segments):
            raise ValueError("narration may contain one segment per scene only")
        return self


class CaptionStyleConfig(ContractModel):
    enabled: bool = True
    font_family: NonEmptyString = "Inter"
    font_size: int = Field(default=32, ge=12, le=96)
    text_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    background_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    position: Literal["top", "middle", "bottom"] = "bottom"


class TimelineClip(ContractModel):
    id: NonEmptyString
    start_ms: Milliseconds
    end_ms: Milliseconds

    @model_validator(mode="after")
    def end_follows_start(self) -> TimelineClip:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class SceneClip(TimelineClip):
    scene_id: NonEmptyString
    source_uri: NonEmptyString
    source_start_ms: Milliseconds = 0


class CaptionClip(TimelineClip):
    scene_id: NonEmptyString
    text: NonEmptyString


class CaptionTrack(ContractModel):
    scene_id: NonEmptyString
    duration_ms: int = Field(gt=0)
    style: CaptionStyleConfig
    clips: list[CaptionClip] = Field(default_factory=list)

    @model_validator(mode="after")
    def clips_fit_scene(self) -> CaptionTrack:
        if any(clip.scene_id != self.scene_id for clip in self.clips):
            raise ValueError("caption clips must reference the track scene")
        if any(clip.end_ms > self.duration_ms for clip in self.clips):
            raise ValueError("caption clips may not exceed scene duration")
        if not self.style.enabled and self.clips:
            raise ValueError("disabled caption tracks may not contain clips")
        return self


class AudioClip(TimelineClip):
    scene_id: NonEmptyString
    source_uri: NonEmptyString


class ZoomClip(TimelineClip):
    scale: float = Field(ge=1, le=4)
    target_rect: BoundingBox
    focus_x: float | None = Field(default=None, ge=0)
    focus_y: float | None = Field(default=None, ge=0)
    source_viewport: Viewport | None = None
    easing: Literal["linear", "ease_in", "ease_out", "ease_in_out"]
    source: Literal["auto", "manual", "prompt_edit"]

    @model_validator(mode="after")
    def focus_coordinates_are_complete(self) -> ZoomClip:
        if (self.focus_x is None) != (self.focus_y is None):
            raise ValueError("focus_x and focus_y must be provided together")
        if self.source_viewport is not None:
            if self.focus_x is not None and self.focus_x > self.source_viewport.width:
                raise ValueError("focus_x must fit within source_viewport")
            if self.focus_y is not None and self.focus_y > self.source_viewport.height:
                raise ValueError("focus_y must fit within source_viewport")
        return self


class VideoPresentationConfig(ContractModel):
    template: Literal["edge_to_edge", "soft_frame", "spotlight"] = "edge_to_edge"
    zoom_enabled: bool = True


class Timeline(ContractModel):
    project_id: NonEmptyString
    duration_ms: int = Field(gt=0)
    demo_mode: DemoMode = "product_demo"
    presentation_pack_id: Literal["presentation-story@1"] | None = None
    motion_plan_id: NonEmptyString | None = None
    motion_design_version: Literal["motion-v1"] | None = None
    attention_plan_id: NonEmptyString | None = None
    attention_design_version: Literal["attention-v1"] | None = None
    style_plan_id: NonEmptyString | None = None
    style_design_version: Literal["style-v1"] | None = None
    visual_variant: Literal[
        "editorial_story", "product_spotlight", "technical_proof"
    ] | None = None
    long_form_plan_id: NonEmptyString | None = None
    long_form_version: Literal["longform-v1"] | None = None
    scene_clips: list[SceneClip] = Field(default_factory=list)
    caption_clips: list[CaptionClip] = Field(default_factory=list)
    zoom_clips: list[ZoomClip] = Field(default_factory=list)
    cursor_events: list[InteractionEvent] = Field(default_factory=list)
    audio_clips: list[AudioClip] = Field(default_factory=list)
    narration_overrides: dict[NonEmptyString, NonEmptyString] = Field(default_factory=dict)
    voice_config: NarrationVoiceConfig | None = None
    cta_text: NonEmptyString | None = None
    presentation: VideoPresentationConfig = Field(default_factory=VideoPresentationConfig)

    @model_validator(mode="after")
    def clips_fit_duration(self) -> Timeline:
        clips = self.scene_clips + self.caption_clips + self.zoom_clips + self.audio_clips
        if any(clip.end_ms > self.duration_ms for clip in clips):
            raise ValueError("clip time range must fit within the timeline duration")
        if any(event.timestamp_ms >= self.duration_ms for event in self.cursor_events):
            raise ValueError("cursor timestamps must be earlier than timeline duration")
        if (self.motion_plan_id is None) != (self.motion_design_version is None):
            raise ValueError("motion plan ID and design version must be stored together")
        if (self.attention_plan_id is None) != (self.attention_design_version is None):
            raise ValueError("attention plan ID and design version must be stored together")
        style_values = (
            self.style_plan_id,
            self.style_design_version,
            self.visual_variant,
        )
        if any(value is None for value in style_values) != all(
            value is None for value in style_values
        ):
            raise ValueError("style plan, version, and visual variant must be stored together")
        if (self.long_form_plan_id is None) != (self.long_form_version is None):
            raise ValueError("long-form plan ID and version must be stored together")
        if self.demo_mode == "presentation_demo" and self.presentation_pack_id is None:
            raise ValueError("Presentation Demo requires the shipped presentation template pack")
        if self.demo_mode == "presentation_demo" and self.duration_ms != 120_000:
            raise ValueError("Presentation Demo must be exactly 120 seconds for the MVP")
        if self.demo_mode == "presentation_demo":
            ordered_scenes = sorted(self.scene_clips, key=lambda clip: clip.start_ms)
            expected_start = 0
            for scene in ordered_scenes:
                if scene.start_ms != expected_start:
                    raise ValueError(
                        "Presentation Demo product footage must cover the complete timeline"
                    )
                expected_start = scene.end_ms
            if not ordered_scenes or expected_start != self.duration_ms:
                raise ValueError(
                    "Presentation Demo product footage must cover the complete timeline"
                )
            has_visible_click = any(
                event.event_type == "click"
                and event.x is not None
                and event.y is not None
                and 5_000 < event.timestamp_ms < 115_000
                for event in self.cursor_events
            )
            if not has_visible_click:
                raise ValueError(
                    "Presentation Demo requires a captured click inside the visible "
                    "product interval"
                )
        if self.demo_mode == "product_demo" and self.presentation_pack_id is not None:
            raise ValueError("Product Demo may not apply a presentation template pack")
        return self


class RenderConfig(ContractModel):
    width: int = Field(default=1280, ge=320, le=3840)
    height: int = Field(default=720, ge=180, le=2160)
    fps: int = Field(default=30, ge=12, le=60)
    output_filename: str = Field(default="preview.mp4", pattern=r"^[A-Za-z0-9._-]+\.mp4$")


class RenderResult(ContractModel):
    status: Literal["succeeded", "failed"]
    output_path: NonEmptyString | None = None
    thumbnail_path: NonEmptyString | None = None
    duration_ms: Milliseconds
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    has_video: bool
    has_audio: bool
    motion_composition_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    long_form_composition_hash: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    error: NonEmptyString | None = None


class EditOperation(ContractModel):
    operation_type: EditOperationType
    target_id: NonEmptyString
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    rationale: NonEmptyString


class EditPlan(ContractModel):
    supported: bool
    summary: NonEmptyString
    explanation: NonEmptyString
    operations: list[EditOperation] = Field(default_factory=list)

    @model_validator(mode="after")
    def unsupported_plans_do_not_mutate(self) -> EditPlan:
        if not self.supported and self.operations:
            raise ValueError("unsupported edit requests may not contain operations")
        return self


class TimelineVersion(ContractModel):
    project_id: NonEmptyString
    version: int = Field(gt=0)
    timeline: Timeline
    change_summary: NonEmptyString
    affected_ids: list[NonEmptyString] = Field(default_factory=list)


class TimelineHistoryState(ContractModel):
    current: TimelineVersion
    can_undo: bool
    can_redo: bool


class QACheck(ContractModel):
    requirement_id: NonEmptyString
    requirement: NonEmptyString
    status: Literal["covered", "partial", "missing"]
    scene_ids: list[NonEmptyString] = Field(default_factory=list)
    evidence: list[NonEmptyString] = Field(default_factory=list)
    suggested_repair: NonEmptyString | None = None


class CoverageRequirement(ContractModel):
    id: NonEmptyString
    text: NonEmptyString
    source_excerpt: NonEmptyString


class BriefCoverageReport(ContractModel):
    project_id: NonEmptyString
    requirements: list[CoverageRequirement] = Field(default_factory=list)
    checks: list[QACheck] = Field(default_factory=list)
    summary: NonEmptyString
    all_covered: bool

    @model_validator(mode="after")
    def checks_cover_each_requirement_once(self) -> BriefCoverageReport:
        requirement_ids = [requirement.id for requirement in self.requirements]
        check_ids = [check.requirement_id for check in self.checks]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("brief coverage requirement IDs must be unique")
        if sorted(requirement_ids) != sorted(check_ids):
            raise ValueError("brief coverage must check each requirement exactly once")
        for check in self.checks:
            if check.status == "covered" and (not check.scene_ids or not check.evidence):
                raise ValueError("covered requirements must cite scenes and evidence")
            if check.status == "missing" and not check.suggested_repair:
                raise ValueError("missing requirements must include a suggested repair")
        if self.all_covered != all(check.status == "covered" for check in self.checks):
            raise ValueError("all_covered must match the requirement check statuses")
        return self


class MissingRequirementRepairProposal(ContractModel):
    requirement_id: NonEmptyString
    scene: Scene
    insert_after_scene_id: NonEmptyString | None = None
    explanation: NonEmptyString


class MissingRequirementRepairResult(ContractModel):
    project_id: NonEmptyString
    requirement_id: NonEmptyString
    status: Literal["succeeded", "requires_approval", "failed"]
    storyboard: Storyboard
    timeline: Timeline
    qa_report: BriefCoverageReport
    capture_result: SceneCaptureResult | None = None
    render_result: RenderResult | None = None
    message: NonEmptyString

    @model_validator(mode="after")
    def successful_repairs_are_verified(self) -> MissingRequirementRepairResult:
        target = next(
            (
                check
                for check in self.qa_report.checks
                if check.requirement_id == self.requirement_id
            ),
            None,
        )
        if target is None:
            raise ValueError("repair result must retain the target QA requirement")
        if self.status == "succeeded":
            if target.status != "covered":
                raise ValueError("successful repairs must cover the target requirement")
            if self.capture_result is None or self.capture_result.status != "succeeded":
                raise ValueError("successful repairs require a successful capture")
            if self.render_result is None or self.render_result.status != "succeeded":
                raise ValueError("successful repairs require a successful render")
        if self.status == "requires_approval" and (
            self.capture_result is not None or self.render_result is not None
        ):
            raise ValueError("approval-gated repairs may not execute capture or render")
        return self


class VideoExport(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    status: Literal["succeeded", "failed"]
    quality: Literal["1440p", "1080p", "720p"]
    filename: NonEmptyString
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    duration_ms: Milliseconds
    size_bytes: int = Field(ge=0)
    thumbnail_path: NonEmptyString | None = None
    download_url: NonEmptyString | None = None
    retryable: bool
    error: NonEmptyString | None = None
    created_at: datetime

    @model_validator(mode="after")
    def successful_exports_are_downloadable(self) -> VideoExport:
        if self.status == "succeeded" and (not self.download_url or self.size_bytes == 0):
            raise ValueError("successful exports must include a non-empty download")
        if self.status == "failed" and not self.error:
            raise ValueError("failed exports must include an error")
        return self


class DemoGenerationResult(ContractModel):
    project: Project
    export: VideoExport
    timeline_version: int = Field(gt=0)
    warnings: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def represents_a_completed_generation(self) -> DemoGenerationResult:
        if self.project.status != "published" or self.project.job_status != "succeeded":
            raise ValueError("generation results require a published, successful project")
        if self.export.status != "succeeded":
            raise ValueError("generation results require a successful export")
        if self.export.project_id != self.project.id:
            raise ValueError("generation export must belong to the generated project")
        return self
