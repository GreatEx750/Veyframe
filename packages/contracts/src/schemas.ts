import { z } from "zod";

const nonEmptyString = z.string().trim().min(1);
const milliseconds = z.number().int().nonnegative();
const dateTime = z.string().refine((value) => !Number.isNaN(Date.parse(value)), {
  message: "Invalid datetime",
});

export const boundingBoxSchema = z
  .object({
    x: z.number().nonnegative(),
    y: z.number().nonnegative(),
    width: z.number().positive(),
    height: z.number().positive(),
  })
  .strict();

export const viewportSchema = z
  .object({
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    scroll_x: z.number().nonnegative().default(0),
    scroll_y: z.number().nonnegative().default(0),
    device_scale_factor: z.number().positive().default(1),
  })
  .strict();

export const projectSchema = z
  .object({
    id: nonEmptyString,
    name: nonEmptyString,
    website_url: z.string().url(),
    product_summary: nonEmptyString,
    audience: nonEmptyString,
    tone: nonEmptyString,
    requested_duration_seconds: z.number().int().positive(),
    cta: nonEmptyString,
    brand_kit_id: nonEmptyString.nullable().default(null),
    status: z
      .enum([
        "draft",
        "storyboarding",
        "ready",
        "capturing",
        "editing",
        "rendering",
        "published",
        "failed",
      ])
      .default("draft"),
    job_status: z.enum(["idle", "queued", "running", "succeeded", "failed"]).default("idle"),
    owner_user_id: nonEmptyString.default("system"),
    created_at: dateTime,
    updated_at: dateTime,
  })
  .strict();

export const userIdentitySchema = z
  .object({
    user_id: nonEmptyString,
    email: nonEmptyString,
    role: z.enum(["customer", "judge_demo", "system"]).default("customer"),
    email_verified: z.boolean().default(false),
  })
  .strict();

export const userProfileSchema = z
  .object({
    user_id: nonEmptyString,
    email: nonEmptyString,
    role: z.enum(["customer", "judge_demo", "system"]).default("customer"),
    created_at: dateTime,
    updated_at: dateTime,
  })
  .strict();

export const sessionSummarySchema = z
  .object({
    session_id: nonEmptyString,
    user: userIdentitySchema,
    created_at: dateTime,
    expires_at: dateTime,
  })
  .strict();

export const signupRequestSchema = z
  .object({
    email: z.string().trim().email().max(254),
    password: z.string().min(12).max(128),
  })
  .strict();

export const signupResultSchema = z
  .object({
    status: z.enum(["signed_in", "verification_required"]),
    session: sessionSummarySchema.nullable().default(null),
    session_token: nonEmptyString.nullable().default(null),
    message: nonEmptyString,
  })
  .strict()
  .superRefine((result, context) => {
    if (result.status === "signed_in" && (!result.session || !result.session_token)) {
      context.addIssue({ code: "custom", message: "signed-in signup results require a session and token" });
    }
    if (result.status === "verification_required" && (result.session || result.session_token)) {
      context.addIssue({ code: "custom", message: "verification-required signup results may not include a session" });
    }
  });

export const authErrorSchema = z
  .object({
    code: z.enum([
      "authentication_required",
      "invalid_credentials",
      "verification_required",
      "account_unavailable",
      "session_expired",
      "session_revoked",
      "rate_limited",
    ]),
    message: nonEmptyString,
  })
  .strict();

export const loginRequestSchema = z
  .object({
    email: z.string().trim().email().max(254),
    password: z.string().min(1).max(128),
    return_to: z.string().min(1).max(500).default("/projects"),
  })
  .strict()
  .superRefine((request, context) => {
    if (!request.return_to.startsWith("/") || request.return_to.startsWith("//")) {
      context.addIssue({ code: "custom", message: "return_to must be an internal application path", path: ["return_to"] });
    }
  });

export const loginResultSchema = z
  .object({
    session: sessionSummarySchema,
    session_token: nonEmptyString,
    landing_path: nonEmptyString,
  })
  .strict();

export const sessionStateSchema = z
  .object({
    status: z.enum(["active", "absent", "expired", "revoked"]),
    session: sessionSummarySchema.nullable().default(null),
  })
  .strict()
  .superRefine((state, context) => {
    if (state.status === "active" && !state.session) {
      context.addIssue({ code: "custom", message: "active session state requires a session", path: ["session"] });
    }
    if (state.status !== "active" && state.session) {
      context.addIssue({ code: "custom", message: "inactive session state may not include a session", path: ["session"] });
    }
  });

export const logoutResultSchema = z
  .object({
    status: z.enum(["logged_out", "already_absent"]),
    reason: z.enum(["user_requested", "absent", "expired", "revoked"]),
    message: nonEmptyString,
  })
  .strict();

export const reauthenticationRequiredSchema = z
  .object({
    required: z.boolean(),
    reason: z.enum(["expired", "revoked", "sensitive_operation"]),
    message: nonEmptyString,
  })
  .strict();

export const judgeSandboxSchema = z
  .object({
    sandbox_id: nonEmptyString,
    project_id: nonEmptyString,
    owner_user_id: nonEmptyString,
    fixture_version: nonEmptyString,
    created_at: dateTime,
    expires_at: dateTime,
  })
  .strict();

export const judgeSessionSchema = z
  .object({
    session: sessionSummarySchema,
    session_token: nonEmptyString,
    sandbox: judgeSandboxSchema,
    capabilities: z.array(z.enum(["view_project", "explore_editor", "preview_fixture", "reset_sandbox"])).min(1),
    landing_path: nonEmptyString,
  })
  .strict();

export const judgeDemoHealthSchema = z
  .object({
    enabled: z.boolean(),
    ready: z.boolean(),
    fixture_version: nonEmptyString,
    message: nonEmptyString,
  })
  .strict();

export const researchSourceSchema = z
  .object({
    id: nonEmptyString,
    project_id: nonEmptyString,
    title: nonEmptyString,
    url: z.string().url(),
    snippet: nonEmptyString,
    source_type: z.enum(["website", "partner_search", "user"]),
    retrieved_at: dateTime,
  })
  .strict();

export const projectResearchResponseSchema = z
  .object({
    project_id: nonEmptyString,
    sources: z.array(researchSourceSchema),
    warning: z.string().nullable().default(null),
  })
  .strict();

export const aiRuntimeHealthSchema = z
  .object({
    status: z.enum(["ready", "unavailable"]),
    provider: z.literal("google"),
    model: nonEmptyString,
    tts_model: nonEmptyString,
    agent: nonEmptyString,
    detail: z.string().nullable().default(null),
  })
  .strict();

export const partnerSearchHealthSchema = z
  .object({
    status: z.enum(["ready", "unavailable"]),
    provider: z.literal("parallel"),
    mode: nonEmptyString,
  })
  .strict();

export const runtimeProvenanceSchema = z
  .object({
    ai: aiRuntimeHealthSchema,
    research: partnerSearchHealthSchema,
  })
  .strict();

export const inspectedElementSchema = z
  .object({
    kind: z.enum(["button", "link", "input", "select", "textarea"]),
    tag: nonEmptyString,
    text: z.string().default(""),
    accessible_name: z.string().default(""),
    href: z.string().nullable().default(null),
    input_type: z.string().nullable().default(null),
    label: z.string().nullable().default(null),
  })
  .strict();

export const inspectedPageSchema = z
  .object({
    title: z.string(),
    url: z.string().url(),
    headings: z.array(z.string()).default([]),
    elements: z.array(inspectedElementSchema).default([]),
    screenshot_path: nonEmptyString,
    viewport: viewportSchema,
  })
  .strict();

export const websiteInspectionSchema = z
  .object({
    project_id: nonEmptyString,
    pages: z.array(inspectedPageSchema).default([]),
    max_pages: z.number().int().positive(),
    max_depth: z.number().int().nonnegative(),
    warning: z.string().nullable().default(null),
  })
  .strict();

export const productFeatureSchema = z
  .object({
    id: nonEmptyString,
    name: nonEmptyString,
    description: nonEmptyString,
    source_ids: z.array(nonEmptyString).default([]),
    user_provided: z.boolean().default(false),
  })
  .strict()
  .refine((feature) => feature.user_provided || feature.source_ids.length > 0, {
    message: "external product features require at least one source ID",
    path: ["source_ids"],
  });

export const suggestedDemoFlowSchema = z
  .object({
    title: nonEmptyString,
    steps: z.array(nonEmptyString).min(1),
    feature_ids: z.array(nonEmptyString).default([]),
  })
  .strict();

export const groundedClaimSchema = z
  .object({
    text: nonEmptyString,
    source_ids: z.array(nonEmptyString).default([]),
    user_provided: z.boolean().default(false),
  })
  .strict()
  .refine((claim) => claim.user_provided || claim.source_ids.length > 0, {
    message: "external claims require at least one source ID",
    path: ["source_ids"],
  });

export const productUnderstandingSchema = z
  .object({
    project_id: nonEmptyString,
    value_proposition: nonEmptyString,
    audience: nonEmptyString,
    features: z.array(productFeatureSchema).default([]),
    suggested_demo_flows: z.array(suggestedDemoFlowSchema).default([]),
    claims: z.array(groundedClaimSchema).default([]),
  })
  .strict()
  .superRefine((understanding, context) => {
    const featureIds = understanding.features.map((feature) => feature.id);
    if (new Set(featureIds).size !== featureIds.length) {
      context.addIssue({ code: "custom", message: "product feature IDs must be unique", path: ["features"] });
    }
    const knownIds = new Set(featureIds);
    understanding.suggested_demo_flows.forEach((flow, flowIndex) => {
      flow.feature_ids.forEach((featureId, featureIndex) => {
        if (!knownIds.has(featureId)) {
          context.addIssue({
            code: "custom",
            message: "demo flows may reference known feature IDs only",
            path: ["suggested_demo_flows", flowIndex, "feature_ids", featureIndex],
          });
        }
      });
    });
  });

export const captureActionSchema = z
  .object({
    type: z.enum([
      "navigate",
      "click",
      "fill",
      "select",
      "scroll",
      "wait_for",
      "assert_visible",
      "upload",
    ]),
    locator_strategy: z
      .enum(["role", "label", "text", "test_id", "css", "xpath", "placeholder", "alt_text"])
      .nullable()
      .default(null),
    locator: nonEmptyString.nullable().default(null),
    value: z.union([z.string(), z.number(), z.boolean()]).nullable().default(null),
    description: nonEmptyString,
  })
  .strict();

export const capturePlanSchema = z
  .object({
    start_url: z.string().url(),
    actions: z.array(captureActionSchema).default([]),
    success_assertions: z.array(captureActionSchema).default([]),
    timeout_seconds: z.number().int().positive(),
  })
  .strict()
  .superRefine((plan, context) => {
    plan.success_assertions.forEach((action, index) => {
      if (action.type !== "assert_visible") {
        context.addIssue({
          code: "custom",
          message: "success assertions must use the assert_visible action type",
          path: ["success_assertions", index, "type"],
        });
      }
    });
  });

export const sceneSchema = z
  .object({
    id: nonEmptyString,
    storyboard_id: nonEmptyString,
    order: z.number().int().nonnegative(),
    title: nonEmptyString,
    objective: nonEmptyString,
    narration: nonEmptyString,
    source_ids: z.array(nonEmptyString).default([]),
    capture_plan: capturePlanSchema,
    expected_evidence: z.array(nonEmptyString).default([]),
    duration_seconds: z.number().positive(),
  })
  .strict();

export const storyboardSchema = z
  .object({
    id: nonEmptyString,
    project_id: nonEmptyString,
    version: z.number().int().positive(),
    total_duration_seconds: z.number().positive(),
    status: z.enum(["draft", "approved", "capturing", "captured", "failed"]),
    scenes: z.array(sceneSchema).default([]),
  })
  .strict();

export const interactionEventSchema = z
  .object({
    timestamp_ms: milliseconds,
    event_type: captureActionSchema.shape.type,
    scene_id: nonEmptyString.nullable().default(null),
    locator: nonEmptyString.nullable().default(null),
    x: z.number().nonnegative().nullable().default(null),
    y: z.number().nonnegative().nullable().default(null),
    bounding_box: boundingBoxSchema.nullable().default(null),
    viewport: viewportSchema,
  })
  .strict();

export const captureActionResultSchema = z
  .object({
    action_index: z.number().int().nonnegative(),
    action_type: captureActionSchema.shape.type,
    status: z.enum(["succeeded", "failed"]),
    elapsed_ms: milliseconds,
    message: nonEmptyString,
  })
  .strict();

export const sceneCaptureResultSchema = z
  .object({
    scene_id: nonEmptyString,
    status: z.enum(["succeeded", "failed"]),
    retryable: z.boolean(),
    duration_ms: milliseconds,
    raw_clip_path: nonEmptyString.nullable().default(null),
    screenshot_paths: z.array(nonEmptyString).default([]),
    action_results: z.array(captureActionResultSchema).default([]),
    interaction_events: z.array(interactionEventSchema).default([]),
    logs: z.array(nonEmptyString).default([]),
    error: nonEmptyString.nullable().default(null),
  })
  .strict()
  .superRefine((capture, context) => {
    capture.interaction_events.forEach((event, index) => {
      if (event.timestamp_ms > capture.duration_ms) {
        context.addIssue({
          code: "custom",
          message: "interaction timestamps may not exceed capture duration",
          path: ["interaction_events", index, "timestamp_ms"],
        });
      }
    });
  });

export const narrationVoiceConfigSchema = z
  .object({
    voice_name: nonEmptyString.default("Kore"),
    language_code: nonEmptyString.default("en-US"),
    pace: z.enum(["slow", "normal", "fast"]).default("normal"),
  })
  .strict();

export const narrationSegmentSchema = z
  .object({
    scene_id: nonEmptyString,
    order: z.number().int().nonnegative(),
    text: nonEmptyString,
    audio_path: nonEmptyString,
    duration_ms: z.number().int().positive(),
  })
  .strict();

export const narrationJobResultSchema = z
  .object({
    status: z.enum(["succeeded", "failed"]),
    retryable: z.boolean(),
    voice_config: narrationVoiceConfigSchema,
    segments: z.array(narrationSegmentSchema).default([]),
    preserved_capture_paths: z.array(nonEmptyString).default([]),
    error: nonEmptyString.nullable().default(null),
  })
  .strict()
  .superRefine((job, context) => {
    const expectedOrder = job.segments.map((_, index) => index);
    if (job.segments.some((segment, index) => segment.order !== expectedOrder[index])) {
      context.addIssue({
        code: "custom",
        message: "narration segment order must be contiguous",
        path: ["segments"],
      });
    }
    if (new Set(job.segments.map((segment) => segment.scene_id)).size !== job.segments.length) {
      context.addIssue({
        code: "custom",
        message: "narration may contain one segment per scene only",
        path: ["segments"],
      });
    }
  });

const timelineClipSchema = z
  .object({
    id: nonEmptyString,
    start_ms: milliseconds,
    end_ms: milliseconds,
  })
  .strict()
  .refine((clip) => clip.end_ms > clip.start_ms, {
    message: "end_ms must be greater than start_ms",
    path: ["end_ms"],
  });

export const sceneClipSchema = timelineClipSchema.safeExtend({
  scene_id: nonEmptyString,
  source_uri: nonEmptyString,
});

export const captionClipSchema = timelineClipSchema.safeExtend({
  scene_id: nonEmptyString,
  text: nonEmptyString,
});

export const captionStyleConfigSchema = z
  .object({
    enabled: z.boolean().default(true),
    font_family: nonEmptyString.default("Inter"),
    font_size: z.number().int().min(12).max(96).default(32),
    text_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/).default("#FFFFFF"),
    background_color: z.string().regex(/^#[0-9A-Fa-f]{6}$/).default("#000000"),
    position: z.enum(["top", "middle", "bottom"]).default("bottom"),
  })
  .strict();

export const captionTrackSchema = z
  .object({
    scene_id: nonEmptyString,
    duration_ms: z.number().int().positive(),
    style: captionStyleConfigSchema,
    clips: z.array(captionClipSchema).default([]),
  })
  .strict()
  .superRefine((track, context) => {
    track.clips.forEach((clip, index) => {
      if (clip.scene_id !== track.scene_id) {
        context.addIssue({
          code: "custom",
          message: "caption clips must reference the track scene",
          path: ["clips", index, "scene_id"],
        });
      }
      if (clip.end_ms > track.duration_ms) {
        context.addIssue({
          code: "custom",
          message: "caption clips may not exceed scene duration",
          path: ["clips", index, "end_ms"],
        });
      }
    });
    if (!track.style.enabled && track.clips.length > 0) {
      context.addIssue({
        code: "custom",
        message: "disabled caption tracks may not contain clips",
        path: ["clips"],
      });
    }
  });

export const audioClipSchema = timelineClipSchema.safeExtend({
  scene_id: nonEmptyString,
  source_uri: nonEmptyString,
});

export const zoomClipSchema = timelineClipSchema.safeExtend({
  scale: z.number().min(1).max(4),
  target_rect: boundingBoxSchema,
  focus_x: z.number().nonnegative().nullable().default(null),
  focus_y: z.number().nonnegative().nullable().default(null),
  source_viewport: viewportSchema.nullable().default(null),
  easing: z.enum(["linear", "ease_in", "ease_out", "ease_in_out"]),
  source: z.enum(["auto", "manual", "prompt_edit"]),
}).superRefine((zoom, context) => {
  if ((zoom.focus_x === null) !== (zoom.focus_y === null)) {
    context.addIssue({ code: "custom", message: "focus_x and focus_y must be provided together", path: ["focus_x"] });
  }
  if (zoom.source_viewport && zoom.focus_x !== null && zoom.focus_x > zoom.source_viewport.width) {
    context.addIssue({ code: "custom", message: "focus_x must fit within source_viewport", path: ["focus_x"] });
  }
  if (zoom.source_viewport && zoom.focus_y !== null && zoom.focus_y > zoom.source_viewport.height) {
    context.addIssue({ code: "custom", message: "focus_y must fit within source_viewport", path: ["focus_y"] });
  }
});

export const videoPresentationSchema = z
  .object({
    template: z.enum(["edge_to_edge", "soft_frame", "spotlight"]).default("edge_to_edge"),
  })
  .strict();

export const timelineSchema = z
  .object({
    project_id: nonEmptyString,
    duration_ms: z.number().int().positive(),
    scene_clips: z.array(sceneClipSchema).default([]),
    caption_clips: z.array(captionClipSchema).default([]),
    zoom_clips: z.array(zoomClipSchema).default([]),
    cursor_events: z.array(interactionEventSchema).default([]),
    audio_clips: z.array(audioClipSchema).default([]),
    narration_overrides: z.record(nonEmptyString, nonEmptyString).default({}),
    voice_config: narrationVoiceConfigSchema.nullable().default(null),
    cta_text: nonEmptyString.nullable().default(null),
    presentation: videoPresentationSchema.default({ template: "edge_to_edge" }),
  })
  .strict()
  .superRefine((timeline, context) => {
    const tracks = ["scene_clips", "caption_clips", "zoom_clips", "audio_clips"] as const;
    tracks.forEach((track) => {
      timeline[track].forEach((clip, index) => {
        if (clip.end_ms > timeline.duration_ms) {
          context.addIssue({
            code: "custom",
            message: "clip time range must fit within the timeline duration",
            path: [track, index, "end_ms"],
          });
        }
      });
    });
    timeline.cursor_events.forEach((event, index) => {
      if (event.timestamp_ms > timeline.duration_ms) {
        context.addIssue({
          code: "custom",
          message: "cursor timestamps may not exceed timeline duration",
          path: ["cursor_events", index, "timestamp_ms"],
        });
      }
    });
  });

export const renderConfigSchema = z
  .object({
    width: z.number().int().min(320).max(3840).default(1280),
    height: z.number().int().min(180).max(2160).default(720),
    fps: z.number().int().min(12).max(60).default(30),
    output_filename: z
      .string()
      .regex(/^[A-Za-z0-9._-]+\.mp4$/)
      .default("preview.mp4"),
  })
  .strict();

export const renderResultSchema = z
  .object({
    status: z.enum(["succeeded", "failed"]),
    output_path: nonEmptyString.nullable().default(null),
    thumbnail_path: nonEmptyString.nullable().default(null),
    duration_ms: milliseconds,
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    has_video: z.boolean(),
    has_audio: z.boolean(),
    error: nonEmptyString.nullable().default(null),
  })
  .strict();

export const editOperationSchema = z
  .object({
    operation_type: z.enum([
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
    ]),
    target_id: nonEmptyString,
    arguments: z.record(z.string(), z.json()).default({}),
    rationale: nonEmptyString,
  })
  .strict();

export const editPlanSchema = z
  .object({
    supported: z.boolean(),
    summary: nonEmptyString,
    explanation: nonEmptyString,
    operations: z.array(editOperationSchema).default([]),
  })
  .strict()
  .refine((plan) => plan.supported || plan.operations.length === 0, {
    message: "unsupported edit requests may not contain operations",
    path: ["operations"],
  });

export const timelineVersionSchema = z
  .object({
    project_id: nonEmptyString,
    version: z.number().int().positive(),
    timeline: timelineSchema,
    change_summary: nonEmptyString,
    affected_ids: z.array(nonEmptyString).default([]),
  })
  .strict();

export const timelineHistoryStateSchema = z
  .object({
    current: timelineVersionSchema,
    can_undo: z.boolean(),
    can_redo: z.boolean(),
  })
  .strict();

export const qaCheckSchema = z
  .object({
    requirement_id: nonEmptyString,
    requirement: nonEmptyString,
    status: z.enum(["covered", "partial", "missing"]),
    scene_ids: z.array(nonEmptyString).default([]),
    evidence: z.array(nonEmptyString).default([]),
    suggested_repair: nonEmptyString.nullable().default(null),
  })
  .strict();

export const coverageRequirementSchema = z
  .object({
    id: nonEmptyString,
    text: nonEmptyString,
    source_excerpt: nonEmptyString,
  })
  .strict();

export const briefCoverageReportSchema = z
  .object({
    project_id: nonEmptyString,
    requirements: z.array(coverageRequirementSchema).default([]),
    checks: z.array(qaCheckSchema).default([]),
    summary: nonEmptyString,
    all_covered: z.boolean(),
  })
  .strict()
  .superRefine((report, context) => {
    const requirementIds = report.requirements.map((requirement) => requirement.id);
    const checkIds = report.checks.map((check) => check.requirement_id);
    if (new Set(requirementIds).size !== requirementIds.length) {
      context.addIssue({ code: "custom", message: "brief coverage requirement IDs must be unique", path: ["requirements"] });
    }
    if ([...requirementIds].sort().join("|") !== [...checkIds].sort().join("|")) {
      context.addIssue({ code: "custom", message: "brief coverage must check each requirement exactly once", path: ["checks"] });
    }
    report.checks.forEach((check, index) => {
      if (check.status === "covered" && (check.scene_ids.length === 0 || check.evidence.length === 0)) {
        context.addIssue({ code: "custom", message: "covered requirements must cite scenes and evidence", path: ["checks", index] });
      }
      if (check.status === "missing" && !check.suggested_repair) {
        context.addIssue({ code: "custom", message: "missing requirements must include a suggested repair", path: ["checks", index] });
      }
    });
    if (report.all_covered !== report.checks.every((check) => check.status === "covered")) {
      context.addIssue({ code: "custom", message: "all_covered must match the requirement check statuses", path: ["all_covered"] });
    }
  });

export const missingRequirementRepairProposalSchema = z
  .object({
    requirement_id: nonEmptyString,
    scene: sceneSchema,
    insert_after_scene_id: nonEmptyString.nullable().default(null),
    explanation: nonEmptyString,
  })
  .strict();

export const missingRequirementRepairResultSchema = z
  .object({
    project_id: nonEmptyString,
    requirement_id: nonEmptyString,
    status: z.enum(["succeeded", "requires_approval", "failed"]),
    storyboard: storyboardSchema,
    timeline: timelineSchema,
    qa_report: briefCoverageReportSchema,
    capture_result: sceneCaptureResultSchema.nullable().default(null),
    render_result: renderResultSchema.nullable().default(null),
    message: nonEmptyString,
  })
  .strict()
  .superRefine((result, context) => {
    const target = result.qa_report.checks.find(
      (check) => check.requirement_id === result.requirement_id,
    );
    if (!target) {
      context.addIssue({
        code: "custom",
        message: "repair result must retain the target QA requirement",
        path: ["qa_report"],
      });
    }
    if (result.status === "succeeded") {
      if (target?.status !== "covered") {
        context.addIssue({
          code: "custom",
          message: "successful repairs must cover the target requirement",
          path: ["qa_report"],
        });
      }
      if (result.capture_result?.status !== "succeeded") {
        context.addIssue({
          code: "custom",
          message: "successful repairs require a successful capture",
          path: ["capture_result"],
        });
      }
      if (result.render_result?.status !== "succeeded") {
        context.addIssue({
          code: "custom",
          message: "successful repairs require a successful render",
          path: ["render_result"],
        });
      }
    }
    if (result.status === "requires_approval" && (result.capture_result || result.render_result)) {
      context.addIssue({
        code: "custom",
        message: "approval-gated repairs may not execute capture or render",
        path: ["status"],
      });
    }
  });

export const videoExportSchema = z
  .object({
    id: nonEmptyString,
    project_id: nonEmptyString,
    status: z.enum(["succeeded", "failed"]),
    quality: z.enum(["1080p", "720p"]),
    filename: nonEmptyString,
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    duration_ms: milliseconds,
    size_bytes: z.number().int().nonnegative(),
    thumbnail_path: nonEmptyString.nullable().default(null),
    download_url: nonEmptyString.nullable().default(null),
    retryable: z.boolean(),
    error: nonEmptyString.nullable().default(null),
    created_at: dateTime,
  })
  .strict()
  .superRefine((item, context) => {
    if (item.status === "succeeded" && (!item.download_url || item.size_bytes === 0)) {
      context.addIssue({ code: "custom", message: "successful exports must include a non-empty download", path: ["download_url"] });
    }
    if (item.status === "failed" && !item.error) {
      context.addIssue({ code: "custom", message: "failed exports must include an error", path: ["error"] });
    }
  });

export const demoGenerationResultSchema = z
  .object({
    project: projectSchema,
    export: videoExportSchema,
    timeline_version: z.number().int().positive(),
    warnings: z.array(nonEmptyString).default([]),
  })
  .strict()
  .superRefine((result, context) => {
    if (result.project.status !== "published" || result.project.job_status !== "succeeded") {
      context.addIssue({
        code: "custom",
        message: "generation results require a published, successful project",
        path: ["project"],
      });
    }
    if (result.export.status !== "succeeded") {
      context.addIssue({
        code: "custom",
        message: "generation results require a successful export",
        path: ["export"],
      });
    }
    if (result.export.project_id !== result.project.id) {
      context.addIssue({
        code: "custom",
        message: "generation export must belong to the generated project",
        path: ["export", "project_id"],
      });
    }
  });

export type BoundingBox = z.infer<typeof boundingBoxSchema>;
export type Viewport = z.infer<typeof viewportSchema>;
export type Project = z.infer<typeof projectSchema>;
export type UserIdentity = z.infer<typeof userIdentitySchema>;
export type UserProfile = z.infer<typeof userProfileSchema>;
export type SessionSummary = z.infer<typeof sessionSummarySchema>;
export type SignupRequest = z.infer<typeof signupRequestSchema>;
export type SignupResult = z.infer<typeof signupResultSchema>;
export type AuthError = z.infer<typeof authErrorSchema>;
export type LoginRequest = z.infer<typeof loginRequestSchema>;
export type LoginResult = z.infer<typeof loginResultSchema>;
export type SessionState = z.infer<typeof sessionStateSchema>;
export type LogoutResult = z.infer<typeof logoutResultSchema>;
export type ReauthenticationRequired = z.infer<typeof reauthenticationRequiredSchema>;
export type JudgeSandbox = z.infer<typeof judgeSandboxSchema>;
export type JudgeSession = z.infer<typeof judgeSessionSchema>;
export type JudgeDemoHealth = z.infer<typeof judgeDemoHealthSchema>;
export type ResearchSource = z.infer<typeof researchSourceSchema>;
export type ProjectResearchResponse = z.infer<typeof projectResearchResponseSchema>;
export type AIRuntimeHealth = z.infer<typeof aiRuntimeHealthSchema>;
export type PartnerSearchHealth = z.infer<typeof partnerSearchHealthSchema>;
export type RuntimeProvenance = z.infer<typeof runtimeProvenanceSchema>;
export type InspectedElement = z.infer<typeof inspectedElementSchema>;
export type InspectedPage = z.infer<typeof inspectedPageSchema>;
export type WebsiteInspection = z.infer<typeof websiteInspectionSchema>;
export type ProductFeature = z.infer<typeof productFeatureSchema>;
export type SuggestedDemoFlow = z.infer<typeof suggestedDemoFlowSchema>;
export type GroundedClaim = z.infer<typeof groundedClaimSchema>;
export type ProductUnderstanding = z.infer<typeof productUnderstandingSchema>;
export type CaptureAction = z.infer<typeof captureActionSchema>;
export type CapturePlan = z.infer<typeof capturePlanSchema>;
export type Scene = z.infer<typeof sceneSchema>;
export type Storyboard = z.infer<typeof storyboardSchema>;
export type InteractionEvent = z.infer<typeof interactionEventSchema>;
export type CaptureActionResult = z.infer<typeof captureActionResultSchema>;
export type SceneCaptureResult = z.infer<typeof sceneCaptureResultSchema>;
export type NarrationVoiceConfig = z.infer<typeof narrationVoiceConfigSchema>;
export type NarrationSegment = z.infer<typeof narrationSegmentSchema>;
export type NarrationJobResult = z.infer<typeof narrationJobResultSchema>;
export type SceneClip = z.infer<typeof sceneClipSchema>;
export type CaptionClip = z.infer<typeof captionClipSchema>;
export type CaptionStyleConfig = z.infer<typeof captionStyleConfigSchema>;
export type CaptionTrack = z.infer<typeof captionTrackSchema>;
export type AudioClip = z.infer<typeof audioClipSchema>;
export type ZoomClip = z.infer<typeof zoomClipSchema>;
export type Timeline = z.infer<typeof timelineSchema>;
export type VideoPresentation = z.infer<typeof videoPresentationSchema>;
export type RenderConfig = z.infer<typeof renderConfigSchema>;
export type RenderResult = z.infer<typeof renderResultSchema>;
export type EditOperation = z.infer<typeof editOperationSchema>;
export type EditPlan = z.infer<typeof editPlanSchema>;
export type TimelineVersion = z.infer<typeof timelineVersionSchema>;
export type TimelineHistoryState = z.infer<typeof timelineHistoryStateSchema>;
export type QACheck = z.infer<typeof qaCheckSchema>;
export type CoverageRequirement = z.infer<typeof coverageRequirementSchema>;
export type BriefCoverageReport = z.infer<typeof briefCoverageReportSchema>;
export type MissingRequirementRepairProposal = z.infer<typeof missingRequirementRepairProposalSchema>;
export type MissingRequirementRepairResult = z.infer<typeof missingRequirementRepairResultSchema>;
export type VideoExport = z.infer<typeof videoExportSchema>;
export type DemoGenerationResult = z.infer<typeof demoGenerationResultSchema>;
