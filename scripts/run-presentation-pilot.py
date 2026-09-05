"""Run the first five authored slides through DemoDirector's local services."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import HttpUrl

ROOT = Path(__file__).resolve().parents[1]
for relative in ["packages/contracts/python", "services/api/src", "services/worker/src"]:
    sys.path.insert(0, str(ROOT / relative))

from demodirector_api.exports import SQLiteExportRepository, StoredExport  # noqa: E402
from demodirector_api.parallel_search import (  # noqa: E402
    ParallelSearchAdapter,
    ParallelSearchSettings,
    normalize_sources,
)
from demodirector_api.presentation_pilot import (  # noqa: E402
    PresentationPilotDirector,
    SlideScript,
    validate_slide,
)
from demodirector_api.repositories import (  # noqa: E402
    SQLiteProjectRepository,
    SQLiteResearchSourceRepository,
    SQLiteTimelineRepository,
)
from demodirector_contracts import (  # noqa: E402
    AudioClip,
    CaptureAction,
    CapturePlan,
    NarrationVoiceConfig,
    Project,
    RenderConfig,
    Scene,
    SceneCaptureResult,
    SceneClip,
    Timeline,
    VideoExport,
)
from demodirector_worker.narration import (  # noqa: E402
    GeminiTTSAdapter,
    GeminiTTSSettings,
    NarrationService,
)
from demodirector_worker.presentation_assets import (  # noqa: E402
    AuthoredSlideRenderer,
    capture_settings_for_template,
    media_probe,
    run_ffmpeg,
)
from demodirector_worker.renderer import FFmpegRenderer  # noqa: E402

OUTPUT = ROOT / "artifacts" / "wikipedia-presentation-five-slides"


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


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    renderer = AuthoredSlideRenderer(OUTPUT)
    db = ROOT / os.getenv("DEMO_DATABASE_PATH", "artifacts/demodirector.db")
    projects = SQLiteProjectRepository(db)
    state_path = OUTPUT / "project.json"
    if state_path.exists():
        project = Project.model_validate_json(state_path.read_text("utf-8"))
    else:
        now = datetime.now(UTC)
        project = Project.model_validate(
            {
                "id": str(uuid4()),
                "name": "Wikipedia — Presentation preview · first five slides",
                "website_url": "https://www.wikipedia.org/",
                "product_summary": "Search Solar System, navigate its contents, follow Earth.",
                "audience": "Curious readers",
                "tone": "Clear and inviting",
                "requested_duration_seconds": 120,
                "demo_mode": "presentation_demo",
                "cta": "Explore Wikipedia",
                "owner_user_id": "judge-demo",
                "created_at": now,
                "updated_at": now,
            }
        )
        projects.create(project)
        state_path.write_text(project.model_dump_json(indent=2), "utf-8")
    research_path = OUTPUT / "research.json"
    if not research_path.exists():
        print("Research: direct Parallel Search", flush=True)
        adapter = ParallelSearchAdapter(ParallelSearchSettings.from_environment())
        sources = normalize_sources(
            project.id,
            adapter.search(
                objective=(
                    "Official Wikipedia help on searching, navigating article contents "
                    "and related links."
                ),
                queries=["site:en.wikipedia.org Help searching Wikipedia table of contents links"],
                domain="wikipedia.org",
            ),
        )
        if not sources:
            raise ValueError(
                "Parallel returned no sources; cannot claim grounded script generation"
            )
        SQLiteResearchSourceRepository(db).replace_partner_sources(project.id, sources)
        research_path.write_text(
            json.dumps([s.model_dump(mode="json") for s in sources], indent=2), "utf-8"
        )
    research = json.loads(research_path.read_text("utf-8"))
    print(f"Research: {len(research)} saved Parallel sources", flush=True)
    director = PresentationPilotDirector(OUTPUT)
    speech = NarrationService(
        GeminiTTSAdapter(GeminiTTSSettings.from_environment()), OUTPUT / "narration"
    )
    clips = []
    recipe_order = ["title", "title", "search", "article", "related"]
    for index, (template, timing, recipe) in enumerate(
        zip(
            renderer.pack["templates"][:5],
            renderer.pack["schedule"][:5],
            recipe_order,
            strict=True,
        )
    ):
        number = index + 1
        duration_ms = timing["end_ms"] - timing["start_ms"]
        print(f"Slide {number}/5: {template['name']}", flush=True)
        script_path = OUTPUT / f"slide-{number:02d}-script.json"
        start_url, actions = RECIPES[recipe]
        context = {
            "sources": research,
            "capture_behavior": {
                "start_url": start_url,
                "actions": [a.description for a in actions],
            },
            "previous_scripts": [
                json.loads(p.read_text("utf-8"))
                for p in sorted(OUTPUT.glob("slide-*-script.json"))
                if p.name < script_path.name
            ],
        }
        if script_path.exists():
            draft = SlideScript.model_validate_json(script_path.read_text("utf-8"))
            try:
                validate_slide(draft, template, {s["id"] for s in research}, recipe)
            except ValueError as error:
                context["validation_feedback"] = str(error)
                draft = director.direct(context, template, recipe, duration_ms, index)
                script_path.write_text(draft.model_dump_json(indent=2), "utf-8")
        else:
            draft = director.direct(context, template, recipe, duration_ms, index)
            script_path.write_text(draft.model_dump_json(indent=2), "utf-8")
        validate_slide(draft, template, {s["id"] for s in research}, recipe)
        copy = {s.slot_id: s.text for s in draft.text}
        copy["counter"] = f"{number:02d} / 05"
        for attempt in range(3):
            try:
                renderer.copy_layer(template, copy, OUTPUT / f"slide-{number:02d}-copy-check.png")
                break
            except ValueError as error:
                if attempt == 2:
                    raise
                context["rewrite_feedback"] = str(error)
                draft = director.direct(context, template, recipe, duration_ms, index)
                script_path.write_text(draft.model_dump_json(indent=2), "utf-8")
                copy = {s.slot_id: s.text for s in draft.text}
        scene = Scene.model_validate(
            {
                "id": f"wikipedia-slide-{number}",
                "storyboard_id": project.id,
                "order": index,
                "title": copy.get("headline", copy.get("prompt", "Wikipedia")),
                "objective": f"Demonstrate {recipe}",
                "narration": draft.narration,
                "source_ids": draft.source_ids,
                "duration_seconds": duration_ms / 1000,
                "capture_plan": CapturePlan(
                    start_url=HttpUrl(start_url), actions=actions, timeout_seconds=60
                ),
            }
        )
        narration = OUTPUT / "narration" / f"slide-{number:02d}-ready.wav"
        voice_receipt = narration.with_suffix(".json")
        voice_key = hashlib.sha256(draft.narration.encode()).hexdigest()
        voice_changed = (
            not voice_receipt.exists()
            or json.loads(voice_receipt.read_text("utf-8"))["text_hash"] != voice_key
        )
        if not narration.exists() or voice_changed:
            print(f"Slide {number}: Gemini narration", flush=True)
            beats = draft.narration_beats or [draft.narration]
            windows = (
                [((duration_ms / 1000) - 4) / 2] * 2 + [4]
                if draft.narration_beats
                else [duration_ms / 1000]
            )
            prepared = []
            for beat_index, (beat, window) in enumerate(zip(beats, windows, strict=True)):
                beat_scene = scene.model_copy(
                    update={"id": f"{scene.id}-beat-{beat_index}", "narration": beat}
                )
                result = speech.generate([beat_scene], NarrationVoiceConfig())
                if result.status != "succeeded":
                    raise ValueError(result.error)
                audio = result.segments[0]
                trimmed = OUTPUT / "narration" / f"slide-{number:02d}-beat-{beat_index}-trim.wav"
                run_ffmpeg(
                    [
                        "-i",
                        audio.audio_path,
                        "-af",
                        "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB",
                        str(trimmed),
                    ],
                    OUTPUT,
                )
                actual = float(media_probe(trimmed)["format"]["duration"])
                speed = max(1.0, actual / (window - 0.15))
                if speed > 1.4:
                    raise ValueError(f"Narration too long for slide {number}: {speed:.2f}x")
                ready = trimmed.with_name(f"slide-{number:02d}-beat-{beat_index}-ready.wav")
                run_ffmpeg(
                    [
                        "-i",
                        str(trimmed),
                        "-af",
                        f"atempo={speed},loudnorm=I=-16:TP=-1.5:LRA=11,"
                        f"apad,atrim=duration={window}",
                        str(ready),
                    ],
                    OUTPUT,
                )
                prepared.append(f"file '{ready.name}'")
            beat_list = OUTPUT / "narration" / f"slide-{number:02d}-beats.txt"
            beat_list.write_text("\n".join(prepared), "utf-8")
            run_ffmpeg(
                [
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(beat_list),
                    "-c:a",
                    "pcm_s16le",
                    str(narration),
                ],
                OUTPUT,
            )
            voice_receipt.write_text(json.dumps({"text_hash": voice_key}), "utf-8")
        product = None
        if template["requires_product"]:
            capture_path = OUTPUT / f"slide-{number:02d}-capture.json"
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
            if product is None:
                print(f"Slide {number}: record real Wikipedia actions", flush=True)
                product, capture = renderer.capture(scene, duration_ms, template)
                capture_path.write_text(capture.model_dump_json(indent=2), "utf-8")
        composed = OUTPUT / f"slide-{number:02d}" / "composed.mp4"
        composition_receipt = OUTPUT / f"slide-{number:02d}-composition.json"
        composition_key = hashlib.sha256(
            json.dumps(
                {
                    "copy": copy,
                    "voice": voice_key,
                    "recipe": "authored-pilot-v2-native-aperture",
                    "product_hash": hashlib.sha256(product.read_bytes()).hexdigest()
                    if product
                    else None,
                    "aperture": template.get("product_aperture"),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        changed = (
            not composition_receipt.exists()
            or json.loads(composition_receipt.read_text("utf-8"))["hash"] != composition_key
        )
        if not composed.exists() or changed:
            print(f"Slide {number}: render fitted template with narration and captions", flush=True)
            composed = renderer.compose(
                template,
                copy,
                duration_ms,
                narration,
                draft.narration,
                product,
                index,
                draft.narration_beats,
            )
            composition_receipt.write_text(json.dumps({"hash": composition_key}), "utf-8")
        # Each completed slide is verified before the next slide begins.
        probe = media_probe(composed)
        video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
        if (video_stream["width"], video_stream["height"]) != (2560, 1440):
            raise ValueError("Slide resolution is not QHD")
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
            OUTPUT,
        )
        clips.append(
            SceneClip(
                id=f"slide-{number}",
                scene_id=scene.id,
                start_ms=timing["start_ms"],
                end_ms=timing["end_ms"],
                source_uri=str(composed),
            )
        )
        print(f"Slide {number}: verified QHD, audio, duration", flush=True)
    # The existing product renderer joins the already authored slide clips without re-framing.
    final_audio = OUTPUT / "narration" / "complete.wav"
    concat = OUTPUT / "narration" / "concat.txt"
    concat.write_text("\n".join(f"file 'slide-{i:02d}-ready.wav'" for i in range(1, 6)), "utf-8")
    # Preserve the full per-slide audio durations including trailing holds from composed MP4s.
    source_list = OUTPUT / "assembled-audio.txt"
    source_list.write_text(
        "\n".join(f"file 'slide-{i:02d}/composed.mp4'" for i in range(1, 6)), "utf-8"
    )
    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(source_list),
            "-vn",
            "-c:a",
            "pcm_s16le",
            str(final_audio),
        ],
        OUTPUT,
    )
    timeline = Timeline(
        project_id=project.id,
        duration_ms=53000,
        scene_clips=clips,
        audio_clips=[
            AudioClip(
                id="narration",
                scene_id="presentation-preview",
                start_ms=0,
                end_ms=53000,
                source_uri=str(final_audio),
            )
        ],
    )
    print("Assemble: DemoDirector FFmpeg renderer, five completed slides", flush=True)
    exports = ROOT / "artifacts" / "exports"
    output_name = f"wikipedia-presentation-five-slides-{project.id}-{uuid4().hex[:8]}.mp4"
    render_result = FFmpegRenderer(ROOT / "artifacts", exports).render(
        timeline, RenderConfig(width=2560, height=1440, output_filename=output_name)
    )
    if render_result.status != "succeeded":
        raise ValueError(render_result.error)
    final = Path(str(render_result.output_path))
    shutil.copy2(final, OUTPUT / "wikipedia-first-five-slides.mp4")
    timeline_path = OUTPUT / "timeline.json"
    timeline_path.write_text(timeline.model_dump_json(indent=2), "utf-8")
    timelines = SQLiteTimelineRepository(db)
    if timelines.current(project.id) is None:
        timelines.initialize(timeline)
    export_id = str(uuid4())
    export = VideoExport(
        id=export_id,
        project_id=project.id,
        status="succeeded",
        quality="1440p",
        filename=final.name,
        width=2560,
        height=1440,
        duration_ms=53000,
        size_bytes=final.stat().st_size,
        thumbnail_path=render_result.thumbnail_path,
        download_url=f"/projects/{project.id}/exports/{export_id}/video",
        retryable=False,
        created_at=datetime.now(UTC),
    )
    SQLiteExportRepository(db).save(StoredExport(export, str(final), None))
    projects.update(
        project.model_copy(
            update={
                "status": "published",
                "job_status": "succeeded",
                "updated_at": datetime.now(UTC),
            }
        )
    )
    report = {
        "project_id": project.id,
        "export": export.model_dump(mode="json"),
        "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
        "providers": {
            "research": "Parallel Search direct",
            "direction": "Google ADK / Gemini",
            "narration": GeminiTTSSettings.from_environment().model_name,
        },
        "scope": "First five slides of the two-minute presentation; 53-second preview",
    }
    (OUTPUT / "result.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
