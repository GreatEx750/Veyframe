"""Application-owned, sequential authored presentation generation."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any
from uuid import uuid4

from demodirector_contracts import (
    AudioClip,
    CaptureAction,
    CapturePlan,
    NarrationVoiceConfig,
    Project,
    RenderConfig,
    ResearchSource,
    Scene,
    SceneCaptureResult,
    SceneClip,
    Storyboard,
    Timeline,
    VideoExport,
)
from demodirector_contracts.jobs import StageContribution
from demodirector_worker.auto_camera import AutoCameraService, AutoCameraSettings
from demodirector_worker.narration import (
    NARRATION_QUOTA_MESSAGE,
    GeminiTTSAdapter,
    GeminiTTSSettings,
    NarrationQuotaError,
    NarrationService,
)
from demodirector_worker.presentation_assets import (
    AuthoredSlideRenderer,
    capture_settings_for_template,
    media_probe,
    run_ffmpeg,
)
from demodirector_worker.presentation_narration import (
    NARRATION_VERSION,
    NarrationTimingError,
    prepare_narration,
    speech_metrics,
)
from demodirector_worker.renderer import FFmpegRenderer
from pydantic import HttpUrl

from demodirector_api.activity_cards import ActivityCardDirector
from demodirector_api.exports import ExportService, SQLiteExportRepository, StoredExport
from demodirector_api.generation import DemoGenerationService
from demodirector_api.parallel_search import (
    ParallelSearchAdapter,
    ParallelSearchSettings,
    research_product,
)
from demodirector_api.presentation_pilot import (
    PresentationPilotDirector,
    SlideScript,
    SlideText,
    narration_word_budget,
    validate_capture_narration,
    validate_slide,
    validate_word_budget,
)
from demodirector_api.presentation_trace import PresentationTraceRecorder, recorded_call
from demodirector_api.recording_workflows import RecordingRecipe, approved_workflow
from demodirector_api.repositories import (
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
    SQLiteStoryboardRepository,
    SQLiteTimelineRepository,
)


def action(kind: str, selector: str, description: str, value: str | None = None) -> CaptureAction:
    return CaptureAction.model_validate(
        {
            "type": kind,
            "locator_strategy": "css",
            "locator": selector,
            "description": description,
            "value": value,
        }
    )


RECIPES = {
    "title": ("https://www.wikipedia.org/", []),
    "search": (
        "https://www.wikipedia.org/",
        [
            action("click", "#searchInput", "Click the search field"),
            action("fill", "#searchInput", "Type Solar System", "Solar System"),
            action("click", "button[type=submit]", "Search for Solar System"),
        ],
    ),
    "article": (
        "https://en.wikipedia.org/wiki/Solar_System",
        [
            action(
                "click",
                '#vector-toc a[href="#Formation_and_evolution"]',
                "Jump to Formation and evolution using the table of contents",
            ),
            action(
                "click",
                '#vector-toc a[href="#General_characteristics"]',
                "Jump to General characteristics",
            ),
            action("click", '#vector-toc a[href="#"]', "Return to the article overview"),
        ],
    ),
    "related": (
        "https://en.wikipedia.org/wiki/Solar_System",
        [
            action(
                "click",
                '#mw-content-text a[title="Earth"] >> nth=0',
                "Follow the Earth link to its article",
            ),
            action(
                "click",
                '#vector-toc a[href="#Natural_history"]',
                "Navigate to Earth's Natural history",
            ),
            action("click", '#vector-toc a[href="#"]', "Return to the Earth overview"),
        ],
    ),
}


def presentation_schedule(
    pack: dict[str, Any],
    *,
    preview: bool,
) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    recipes = [
        "title",
        "related",
        "search",
        "article",
        "related",
        "article",
        "search",
        "related",
        "title",
    ]
    templates = {template["id"]: template for template in pack["templates"]}
    schedule = pack["schedule"]
    if len(schedule) != len(recipes):
        raise ValueError("The authored presentation schedule must contain nine slides")
    previous = 0
    result = []
    for timing, recipe in zip(schedule, recipes, strict=True):
        if timing["start_ms"] != previous or timing["end_ms"] <= previous:
            raise ValueError("Presentation slide timing must be positive and contiguous")
        template = templates[timing["template_id"]]
        if bool(template["requires_product"]) != (recipe != "title"):
            raise ValueError("Product footage must match the assigned slide")
        result.append((template, timing, recipe))
        previous = timing["end_ms"]
    if previous != 120_000:
        raise ValueError("Full Presentation Demo must be exactly 120 seconds")
    return result[:5] if preview else result


def run_presentation(
    project: Project,
    root: Path,
    output: Path,
    db: Path,
    progress: Callable[[str], None],
    recipes: dict[str, tuple[str, list[CaptureAction]]] | None = None,
    *,
    preview: bool = True,
    session_token: str | None = None,
    generation: DemoGenerationService | None = None,
    slide_limit: int | None = None,
    template_theme: str = "default",
    recording_workflow: dict[str, RecordingRecipe] | None = None,
    trace_recorder: PresentationTraceRecorder | None = None,
) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    from demodirector_worker.promo_assets import PROMO_MODES, promo_root, promo_schedule

    is_promo = project.demo_mode in PROMO_MODES
    if is_promo and preview:
        raise ValueError("Spotlight and Short do not have a presentation preview")
    renderer = (
        AuthoredSlideRenderer(
            output,
            pack_root=promo_root(
                project.demo_mode, project.output_orientation, theme=template_theme,
            ),
        )
        if is_promo
        else AuthoredSlideRenderer(output, theme=template_theme)
        if template_theme != "default"
        else AuthoredSlideRenderer(output)
    )
    canvas = renderer.pack.get("canvas", {"width": 2560, "height": 1440})
    width, height = canvas["width"], canvas["height"]
    export_service = generation.exports if generation else None
    if export_service is not None and not isinstance(export_service, ExportService):
        raise ValueError("Presentation requires the configured export storage service")
    projects = generation.projects if generation else SQLiteProjectRepository(db)
    sources_repository = (
        generation.research_sources if generation else SQLiteResearchSourceRepository(db)
    )
    recipes = recipes or RECIPES
    recording_workflow = recording_workflow or approved_workflow(str(project.website_url))
    inspected = [
        s for s in sources_repository.list_for_project(project.id) if s.source_type == "website"
    ]
    research_path = output / "research.json"
    receipt_path = output / "research-receipt.json"
    cached = json.loads(research_path.read_text("utf-8")) if research_path.exists() else []
    if not cached and not (research_path.exists() and receipt_path.exists()):
        progress("Research: direct Parallel Search using inspected destination")
        adapter = ParallelSearchAdapter(ParallelSearchSettings.from_environment())
        research_result = recorded_call(
            trace_recorder, "research", "Retrieve project sources", "Parallel Search direct",
            partial(research_product, adapter, project, inspected),
        )
        if trace_recorder:
            search_failed = any("error" in attempt for attempt in research_result.attempts)
            trace_recorder.describe_last(
                f"{len(research_result.attempts)} search attempts; "
                f"{len(research_result.sources)} usable sources saved. "
                + ("Research unavailable; using inspected website evidence." if search_failed
                   else "Continuing with inspected website evidence." if not research_result.sources
                   else "Retrieved evidence is available for slide direction."),
                [StageContribution(key="parallel_sources_linked", label="Saved research sources",
                                   value=len(research_result.sources), unit="sources")],
                failed=search_failed,
            )
        cached = [s.model_dump(mode="json") for s in research_result.sources]
        sources_repository.replace_partner_sources(project.id, research_result.sources)
        research_path.write_text(json.dumps(cached, indent=2), "utf-8")
        receipt_path.write_text(json.dumps({
            "attempts": research_result.attempts, "warning": research_result.warning,
        }, indent=2), "utf-8")
    partner_sources = [ResearchSource.model_validate(s) for s in cached]
    research = [s.model_dump(mode="json") for s in [*partner_sources, *inspected]]
    progress(
        f"Research: {len(partner_sources)} saved Parallel sources; "
        f"{len(inspected)} inspected website sources"
    )
    if not research:
        raise ValueError("No retrieved or inspected evidence is available for slide direction")
    director = PresentationPilotDirector(output)
    speech_adapter = GeminiTTSAdapter(
        GeminiTTSSettings.from_environment(),
        on_progress=lambda message: progress(f"TTS narration: {message}"),
    )
    speech = NarrationService(speech_adapter, output / "narration")
    clips = []
    scenes = []
    schedule = (
        promo_schedule(renderer.pack)
        if is_promo
        else presentation_schedule(renderer.pack, preview=preview)
    )
    extension_budget = 0 if is_promo else 20_000
    slide_count = len(schedule)
    baseline_duration_ms = schedule[-1][1]["end_ms"]
    elapsed_ms = 0
    measured_schedule = []
    for index, (template, timing, recipe) in enumerate(schedule):
        number = index + 1
        duration_ms = timing["end_ms"] - timing["start_ms"]
        baseline_ms = duration_ms
        # Spend only previously earned extra time, keeping the overall minimum intact.
        min_duration_ms = baseline_ms - (
            min(2000, max(0, elapsed_ms - timing["start_ms"]))
            if template["requires_product"]
            else 0
        )
        remaining_extension_ms = extension_budget - (elapsed_ms - timing["start_ms"])
        max_duration_ms = baseline_ms + (
            min(5000, max(0, remaining_extension_ms)) if template["requires_product"] else 0
        )
        progress(f"Slide {number}/{slide_count}: {template['name']}")
        script_path = output / f"slide-{number:02d}-script.json"
        start_url, actions = recipes[recipe]
        reviewed_recipe = None
        if recording_workflow:
            reviewed_recipe = recording_workflow.get(f"slide-{number}", recording_workflow[recipe])
            actions = reviewed_recipe.actions
        context = {
            "sources": research,
            "project": project.model_dump(mode="json"),
            "slide_count": slide_count,
            **(
                {
                    "promo_mode": project.demo_mode,
                    "story_role": template["role"],
                    "story_intent": template["story_intent"],
                }
                if is_promo
                else {}
            ),
            "capture_behavior": {
                "start_url": start_url,
                "actions": [a.description for a in actions],
                "direction_note": reviewed_recipe.direction_note if reviewed_recipe else "",
            },
            "previous_template_ids": [t[0]["id"] for t in schedule[:index]],
        }
        direction_template = template
        if template.get("activity_panel"):
            direction_template = {
                **template,
                "copy_slots": [
                    s for s in template["copy_slots"] if not s["id"].startswith("activity_")
                ],
            }
        if script_path.exists():
            draft = SlideScript.model_validate_json(script_path.read_text("utf-8"))
            if template.get("activity_panel"):
                draft = draft.model_copy(
                    update={
                        "text": [s for s in draft.text if not s.slot_id.startswith("activity_")]
                    }
                )
            try:
                validate_slide(draft, direction_template, {s["id"] for s in research}, recipe)
                validate_capture_narration(draft, context)
            except ValueError as error:
                context["validation_feedback"] = str(error)
                draft = recorded_call(
                    trace_recorder, "storyboard", f"Slide {number}: write validated copy",
                    "Google ADK / Gemini",
                    partial(director.direct, context, direction_template,
                            recipe, duration_ms, index),
                )
                script_path.write_text(draft.model_dump_json(indent=2), "utf-8")
        else:
            progress(
                f"Slide {number}/{slide_count}: Google ADK / Gemini is writing "
                "and validating slide copy"
            )
            draft = recorded_call(
                trace_recorder, "storyboard", f"Slide {number}: write validated copy",
                "Google ADK / Gemini",
                partial(director.direct, context, direction_template, recipe, duration_ms, index),
            )
            script_path.write_text(draft.model_dump_json(indent=2), "utf-8")
        if template.get("activity_panel"):
            progress(f"Slide {number}: Gemini / ADK product activity cards")
            workflow = [
                {"ref": f"{name}:{i}", "description": a.description, "start_url": url}
                for name, (url, steps) in recipes.items()
                for i, a in enumerate(steps)
            ]
            recorded: set[str] = set()
            for prior_index, (_, _, prior_recipe) in enumerate(schedule):
                receipt = output / f"slide-{prior_index + 1:02d}-capture.json"
                if receipt.exists() and (
                    json.loads(receipt.read_text("utf-8"))["status"] == "succeeded"
                ):
                    recorded.update(
                        f"{prior_recipe}:{i}" for i in range(len(recipes[prior_recipe][1]))
                    )
            panel = ActivityCardDirector(output).generate(
                {
                    "target": {"website_url": str(project.website_url), "name": project.name},
                    "sources": [
                        {key: source[key] for key in ("id", "title", "url", "snippet")}
                        for source in research
                    ],
                    "workflow": workflow,
                    "recorded_action_refs": sorted(recorded),
                }
            )
            draft = draft.model_copy(
                update={
                    "text": [
                        *[s for s in draft.text if not s.slot_id.startswith("activity_")],
                        *[SlideText(slot_id=k, text=v) for k, v in panel.slot_copy().items()],
                    ]
                }
            )
            script_path.write_text(draft.model_dump_json(indent=2), "utf-8")
        validate_slide(draft, template, {s["id"] for s in research}, recipe)
        validate_capture_narration(draft, context)
        copy = {s.slot_id: s.text for s in draft.text}
        if "counter" in copy:
            copy["counter"] = f"{number:02d} / {slide_count:02d}"
        for attempt in range(3):
            try:
                renderer.copy_layer(template, copy, output / f"slide-{number:02d}-copy-check.png")
                break
            except ValueError as error:
                if attempt == 2 or template.get("activity_panel"):
                    raise
                context["rewrite_feedback"] = str(error)
                draft = recorded_call(
                    trace_recorder, "storyboard", f"Slide {number}: fit slide copy",
                    "Google ADK / Gemini",
                    partial(director.direct, context, direction_template,
                            recipe, duration_ms, index),
                )
                script_path.write_text(draft.model_dump_json(indent=2), "utf-8")
                copy = {s.slot_id: s.text for s in draft.text}
                if "counter" in copy:
                    copy["counter"] = f"{number:02d} / {slide_count:02d}"
        scene = Scene.model_validate(
            {
                "id": f"presentation-slide-{number}",
                "storyboard_id": project.id,
                "order": index,
                "title": copy.get("headline", copy.get("prompt", project.name)),
                "objective": f"Demonstrate {recipe}",
                "narration": draft.narration,
                "source_ids": draft.source_ids,
                "duration_seconds": duration_ms / 1000,
                "capture_plan": CapturePlan(
                    start_url=HttpUrl(start_url), actions=actions, timeout_seconds=60
                ),
            }
        )
        narration = output / "narration" / f"slide-{number:02d}-ready.wav"
        voice_receipt = narration.with_suffix(".json")
        voice = NarrationVoiceConfig()

        def narration_key(
            text: str,
            voice: NarrationVoiceConfig = voice,
            duration_ms: int = duration_ms,
            max_duration_ms: int = max_duration_ms,
        ) -> str:
            return hashlib.sha256(
                json.dumps(
                    {
                        "text": text,
                        "version": NARRATION_VERSION,
                        "voice": voice.model_dump(mode="json"),
                        "model": GeminiTTSSettings.from_environment().model_name,
                        "duration_ms": duration_ms,
                        "max_duration_ms": max_duration_ms,
                    **({"promo_audio_policy": "continuous-1"} if is_promo else {}),
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()

        voice_key = narration_key(draft.narration)
        saved_voice = json.loads(voice_receipt.read_text("utf-8")) if voice_receipt.exists() else {}
        voice_changed = saved_voice.get("text_hash") != voice_key
        if not narration.exists() or voice_changed:
            budget = narration_word_budget(duration_ms)
            try:
                if is_promo and len(draft.narration.split()) < budget * .8:
                    raise ValueError(f"Expand the narration to about {budget} words")
                validate_word_budget(draft.narration, budget, allow_short=True)
            except ValueError as error:
                progress(f"Slide {number}: validating script before speech ({budget} words)")
                context["narration_word_budget"] = budget
                context["rewrite_feedback"] = str(error)
                draft = recorded_call(
                    trace_recorder, "storyboard", f"Slide {number}: revise narration script",
                    "Google ADK / Gemini", partial(director.rewrite_narration, context, draft),
                )
                validate_word_budget(draft.narration, budget, allow_short=True)
                validate_capture_narration(draft, context)
                validate_slide(draft, template, {s["id"] for s in research}, recipe)
                scene = scene.model_copy(update={"narration": draft.narration})
                script_path.write_text(draft.model_dump_json(indent=2), "utf-8")
                voice_key = narration_key(draft.narration)
            for voice_attempt in range(2):
                progress(f"Slide {number}: continuous Gemini narration ({voice_attempt + 1}/2)")
                raw = output / "narration" / f"saved-{voice_key}.wav"
                raw_receipt = raw.with_suffix(".json")
                if not raw.exists():
                    result = recorded_call(
                        trace_recorder, "narration", f"Slide {number}: synthesize narration",
                        "Gemini TTS", partial(speech.generate, [scene], voice),
                    )
                    if result.status != "succeeded":
                        if result.error == NARRATION_QUOTA_MESSAGE:
                            raise NarrationQuotaError(NARRATION_QUOTA_MESSAGE)
                        raise ValueError(result.error)
                    raw.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(result.segments[0].audio_path, raw)
                    raw_receipt.write_text(
                        json.dumps(
                            {
                                "model": getattr(speech_adapter, "model_name", "fixture"),
                            }
                        ),
                        "utf-8",
                    )
                else:
                    progress(f"Slide {number}: reusing saved speech; no new TTS request")
                try:
                    metrics = prepare_narration(
                        raw,
                        narration,
                        duration_ms / 1000,
                        max_duration=max_duration_ms / 1000,
                        min_duration=min_duration_ms / 1000,
                        allow_silent_hold=not is_promo,
                    )
                    break
                except NarrationTimingError as error:
                    progress(f"Slide {number}: narration timing check — {error}")
                    if voice_attempt == 1:
                        raise
                    observed = speech_metrics(raw)
                    measured_budget = max(
                        2,
                        round(
                            len(draft.narration.split())
                            * (duration_ms / 1000 - 0.3)
                            / (observed["end"] - observed["start"])
                        ),
                    )
                    context["narration_word_budget"] = measured_budget
                    context["rewrite_feedback"] = (
                        f"Rewrite narration only. Current narration: {draft.narration}. {error} "
                        "Keep the same grounded actions in order, using connected explanatory "
                        "sentences. Do not add unobserved actions or claims."
                    )
                    replacement = recorded_call(
                        trace_recorder, "storyboard", f"Slide {number}: adjust narration length",
                        "Google ADK / Gemini", partial(director.rewrite_narration, context, draft),
                    )
                    validate_word_budget(replacement.narration, measured_budget, allow_short=True)
                    draft = draft.model_copy(
                        update={
                            "narration": replacement.narration,
                            "narration_beats": replacement.narration_beats,
                        }
                    )
                    validate_capture_narration(draft, context)
                    validate_slide(draft, template, {s["id"] for s in research}, recipe)
                    scene = scene.model_copy(update={"narration": draft.narration})
                    script_path.write_text(draft.model_dump_json(indent=2), "utf-8")
                    voice_key = narration_key(draft.narration)
            saved_voice = {
                "text_hash": voice_key,
                "version": NARRATION_VERSION,
                **metrics,
                **json.loads(raw_receipt.read_text("utf-8")),
            }
            voice_receipt.write_text(json.dumps(saved_voice, indent=2), "utf-8")
        resolved_duration = float(saved_voice["slide_duration"])
        if not math.isfinite(resolved_duration):
            raise ValueError("Invalid saved narration timing")
        duration_ms = round(resolved_duration * 1000)
        if not min_duration_ms <= duration_ms <= max_duration_ms:
            raise ValueError("Saved narration exceeds the remaining presentation timing budget")
        scene = scene.model_copy(update={"duration_seconds": duration_ms / 1000})
        scenes.append(scene)
        hold = max(0, resolved_duration - float(saved_voice["speech_duration"]))
        if hold > 1.25:
            progress(f"Slide {number}: narration finished; allowing a {hold:.1f}s quiet hold")
        measured_schedule.append(
            {
                "slide": number,
                "start_ms": elapsed_ms,
                "end_ms": elapsed_ms + duration_ms,
                "baseline_duration_ms": baseline_ms,
                "duration_ms": duration_ms,
            }
        )
        (output / "measured-schedule.json").write_text(
            json.dumps(measured_schedule, indent=2), "utf-8"
        )
        if duration_ms != baseline_ms:
            progress(
                f"Slide {number}: adjusted from {baseline_ms / 1000:g}s "
                f"to {duration_ms / 1000:g}s for natural narration"
            )
        product = None
        zoom_clips = []
        if template["requires_product"]:
            capture_path = output / f"slide-{number:02d}-capture.json"
            settings = capture_settings_for_template(template)
            if capture_path.exists():
                capture = SceneCaptureResult.model_validate_json(capture_path.read_text("utf-8"))
                product = Path(str(capture.raw_clip_path))
                if product.is_file():
                    stream = next(
                        s for s in media_probe(product)["streams"] if s["codec_type"] == "video"
                    )
                    if (stream["width"], stream["height"]) != (
                        settings.viewport_width,
                        settings.viewport_height,
                    ):
                        product = None
                else:
                    product = None
                expected_interactions = sum(
                    action.type in {"click", "fill", "select"}
                    for action in scene.capture_plan.actions
                )
                if (
                    len(capture.interaction_events) != expected_interactions
                    or capture.duration_ms != duration_ms
                ):
                    # Older captures could trim late actions when navigation was slow.
                    product = None
            if product is None:
                progress(f"Slide {number}: record website actions")
                preparation = reviewed_recipe.preparation if reviewed_recipe else []
                if preparation:
                    progress(f"Slide {number}: preparing page and waiting for visible results")
                product, capture = recorded_call(
                    trace_recorder, "capture", f"Slide {number}: record website interactions",
                    "Playwright recorder",
                    partial(renderer.capture, scene, duration_ms, template,
                            session_token=session_token, preparation=preparation,
                            on_progress=progress),
                )
                progress(
                    f"Slide {number}/{slide_count}: recording saved, "
                    f"{len(capture.interaction_events)} "
                    f"interactions, {capture.duration_ms / 1000:g} seconds"
                )
                capture_path.write_text(capture.model_dump_json(indent=2), "utf-8")
            if project.zoom_enabled:
                zoom_clips = AutoCameraService(
                    settings=AutoCameraSettings(
                        max_scale=1.5,
                        focus_duration_ms=2500,
                    )
                ).generate(capture.interaction_events, duration_ms)
        composed = output / f"slide-{number:02d}" / "composed.mp4"
        composition_receipt = output / f"slide-{number:02d}-composition.json"
        composition_key = hashlib.sha256(
            json.dumps(
                {
                    "copy": copy,
                    **({"template_theme": template_theme} if template_theme != "default" else {}),
                    **(
                        {"visual_revision": template["visual_revision"]}
                        if "visual_revision" in template
                        else {}
                    ),
                    **(
                        {"copy_palette": "dark-card-ink-2"}
                        if template["id"] == "trust-cards@2"
                        else {}
                    ),
                    "voice": voice_key,
                    "audio_hash": hashlib.sha256(narration.read_bytes()).hexdigest(),
                    "recipe": "authored-v2-quiet-hold-2",
                    "duration_ms": duration_ms,
                    "product_hash": hashlib.sha256(product.read_bytes()).hexdigest()
                    if product
                    else None,
                    "aperture": template.get("product_aperture"),
                    "zoom": [z.model_dump(mode="json") for z in zoom_clips],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        changed = (
            not composition_receipt.exists()
            or json.loads(composition_receipt.read_text("utf-8"))["hash"] != composition_key
        )
        if not composed.exists() or changed:
            progress(f"Slide {number}: render fitted template with narration and captions")
            composed = renderer.compose(
                template,
                copy,
                duration_ms,
                narration,
                draft.narration,
                product,
                index,
                None,
                zoom_clips=zoom_clips,
                narration_duration=saved_voice["speech_duration"],
            )
            composition_receipt.write_text(json.dumps({"hash": composition_key}), "utf-8")
        # Each completed slide is verified before the next slide begins.
        probe = media_probe(composed)
        video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
        if (video_stream["width"], video_stream["height"]) != (width, height):
            raise ValueError("Slide resolution does not match the selected template")
        if abs(float(probe["format"]["duration"]) - duration_ms / 1000) > 0.1:
            raise ValueError("Slide duration does not match its authored timing")
        if not any(s["codec_type"] == "audio" for s in probe["streams"]):
            raise ValueError("Slide has no narration audio")
        run_ffmpeg(
            [
                "-ss",
                str(max(0.1, duration_ms / 2000)),
                "-i",
                str(composed),
                "-frames:v",
                "1",
                "-update",
                "1",
                str(composed.with_suffix(".png")),
            ],
            output,
        )
        clips.append(
            SceneClip(
                id=f"slide-{number}",
                scene_id=scene.id,
                start_ms=elapsed_ms,
                end_ms=elapsed_ms + duration_ms,
                source_uri=str(composed),
            )
        )
        progress(
            f"Slide {number}/{slide_count}: completed and verified {width} × {height}, "
            f"narration audio, {duration_ms / 1000:g} seconds"
        )
        elapsed_ms += duration_ms
        if slide_limit is not None and number >= slide_limit:
            return {"completed_slides": number}
    preview_duration_ms = elapsed_ms
    if not baseline_duration_ms <= preview_duration_ms <= baseline_duration_ms + extension_budget:
        raise ValueError("Presentation exceeded its shared 20-second extension budget")
    # The existing product renderer joins the already authored slide clips without re-framing.
    final_audio = output / "narration" / "complete.wav"
    concat = output / "narration" / "concat.txt"
    concat.write_text(
        "\n".join(f"file 'slide-{i:02d}-ready.wav'" for i in range(1, slide_count + 1)), "utf-8"
    )
    # Join original PCM directly; avoid decoding intermediate AAC slide audio.
    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-vn",
            "-c:a",
            "pcm_s16le",
            str(final_audio),
        ],
        output,
    )
    timeline = Timeline(
        project_id=project.id,
        demo_mode=project.demo_mode if is_promo else "product_demo",
        output_orientation=project.output_orientation if is_promo else None,
        duration_ms=preview_duration_ms,
        scene_clips=clips,
        audio_clips=[
            AudioClip(
                id="narration",
                scene_id="presentation-preview",
                start_ms=0,
                end_ms=preview_duration_ms,
                source_uri=str(final_audio),
            )
        ],
    )
    progress(f"Assemble: DemoDirector FFmpeg renderer, {slide_count} completed slides")
    exports = (
        export_service.artifact_directory if export_service else root / "artifacts" / "exports"
    )
    prefix = project.demo_mode if is_promo else "presentation"
    output_name = f"{prefix}-{slide_count}-slides-{project.id}-{uuid4().hex[:8]}.mp4"
    render_result = recorded_call(
        trace_recorder, "render", "Assemble completed slides", "FFmpeg renderer",
        partial(FFmpegRenderer(output, exports).render, timeline,
                RenderConfig(width=width, height=height, output_filename=output_name)),
    )
    if render_result.status != "succeeded":
        raise ValueError(render_result.error)
    final = Path(str(render_result.output_path))
    final_probe = media_probe(final)
    if abs(float(final_probe["format"]["duration"]) - preview_duration_ms / 1000) > 0.04:
        raise ValueError("The assembled video does not match the presentation duration")
    decoded_audio = output / "narration" / "verified-export.wav"
    run_ffmpeg(
        [
            "-i",
            str(final),
            "-vn",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(decoded_audio),
        ],
        output,
    )
    audio_quality = speech_metrics(decoded_audio)
    if audio_quality["peak"] >= 0.99:
        raise ValueError("Exported narration has clipping risk")
    if is_promo and audio_quality["max_internal_silence"] > 2:
        raise ValueError("Promo narration has an excessive gap")
    if audio_quality["max_internal_silence"] > 2:
        progress("Narration verified: quiet holds retained between continuous spoken paragraphs")
    if abs(audio_quality["duration"] - preview_duration_ms / 1000) > 0.05:
        raise ValueError("Exported narration duration does not match the presentation")
    (output / "audio-verification.json").write_text(json.dumps(audio_quality, indent=2), "utf-8")
    shutil.copy2(final, output / ("first-five-slides.mp4" if preview else "presentation-full.mp4"))
    timeline_path = output / "timeline.json"
    timeline_path.write_text(timeline.model_dump_json(indent=2), "utf-8")
    timelines = generation.timelines if generation else SQLiteTimelineRepository(db)
    if generation:
        timeline = generation.timeline_media_store.persist(timeline)
    current = timelines.current(project.id)
    if current is None:
        timelines.initialize(timeline)
    elif is_promo and current.current.timeline != timeline:
        if current.current.version != 1:
            raise ValueError("Create a new project instead of replacing an edited promo")
        timelines.commit(1, timeline, "Regenerated promo from saved sections", [])
    export_id = str(uuid4())
    export = VideoExport(
        id=export_id,
        project_id=project.id,
        status="succeeded",
        quality="1080p" if is_promo and project.output_orientation == "vertical" else "1440p",
        filename=final.name,
        width=width,
        height=height,
        duration_ms=preview_duration_ms,
        size_bytes=final.stat().st_size,
        thumbnail_path=render_result.thumbnail_path,
        download_url=f"/projects/{project.id}/exports/{export_id}/video",
        retryable=False,
        created_at=datetime.now(UTC),
    )
    if export_service:
        reference = export_service.artifact_store.persist(final, project.id, export_id)
        export_service.repository.save(StoredExport(export, reference, None))
    else:
        SQLiteExportRepository(db).save(StoredExport(export, str(final), None))
    storyboards = generation.storyboards if generation else SQLiteStoryboardRepository(db)
    storyboards.save(Storyboard(
        id=project.id, project_id=project.id, version=1, status="captured",
        total_duration_seconds=preview_duration_ms / 1000, scenes=scenes,
    ))
    projects.update(
        project.model_copy(
            update={
                "status": "published",
                "job_status": "succeeded",
                "updated_at": datetime.now(UTC),
            }
        )
    )
    cited_ids = {
        source_id
        for index in range(slide_count)
        for source_id in json.loads(
            (output / f"slide-{index + 1:02d}-script.json").read_text("utf-8")
        )["source_ids"]
    }
    cited_partner_sources = [
        {"id": source.id, "title": source.title, "url": str(source.url)}
        for source in partner_sources if source.id in cited_ids
    ]
    progress(
        f"Research evidence: {len(partner_sources)} retrieved sources; "
        f"{len(cited_partner_sources)} cited in slide scripts"
    )
    report: dict[str, object] = {
        "template_pack": renderer.pack["pack_id"],
        "research_evidence": {
            "accepted_source_count": len(partner_sources),
            "cited_partner_sources": cited_partner_sources,
        },
        "project_id": project.id,
        "export": export.model_dump(mode="json"),
        "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
        "providers": {
            "research": "Parallel Search direct",
            "direction": "Google ADK / Gemini",
            "narration": GeminiTTSSettings.from_environment().model_name,
        },
        "scope": (
            "First five slides of the two-minute presentation; "
            f"{preview_duration_ms / 1000:g}-second preview"
        )
        if preview
        else f"Full nine-slide presentation; {preview_duration_ms / 1000:g} seconds (120–140s)",
    }
    if is_promo:
        report["scope"] = f"{project.demo_mode}: {preview_duration_ms / 1000:g} seconds"
        report["sections"] = [t[0]["id"] for t in schedule]
    (output / "result.json").write_text(json.dumps(report, indent=2), "utf-8")
    progress(f"Finished: {slide_count} slides, {preview_duration_ms / 1000:g} seconds")
    return report
