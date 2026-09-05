from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from demodirector_contracts import (
    AudioClip,
    CaptionClip,
    InteractionEvent,
    RenderConfig,
    RenderResult,
    SceneClip,
    Timeline,
    Viewport,
    ZoomClip,
)
from demodirector_contracts.attention import AttentionPlan
from demodirector_contracts.longform import AudioMixPlan, LongFormVideoPlan
from demodirector_contracts.motion import MotionDirectionPlan
from demodirector_contracts.style import StyleDirectionPlan, VisualVariantId

from demodirector_worker.attention import AttentionCompiler
from demodirector_worker.editorial import EditorialCompositionCompiler
from demodirector_worker.longform import LongFormCompiler
from demodirector_worker.motion import MotionCompositionCompiler
from demodirector_worker.presentation import (
    PRESENTATION_PACK_ID,
    CopyLayout,
    build_presentation_schedule,
    resolve_palette_color,
    resolve_presentation_pack,
)
from demodirector_worker.style import StyleCompiler

VIDEO_EXTENSIONS = {".mkv", ".mov", ".mp4", ".webm"}
AUDIO_EXTENSIONS = {".aac", ".m4a", ".mp3", ".ogg", ".wav"}


class RendererError(RuntimeError):
    """Raised when a typed timeline cannot be rendered safely."""


@dataclass(frozen=True, slots=True)
class FFmpegSettings:
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    font_path: str | None = None
    timeout_seconds: int = 900


@dataclass(frozen=True, slots=True)
class _TextBlockLayout:
    """Measured, deterministic copy layout for a trusted authored slot."""

    lines: tuple[str, ...]
    font_size: int
    line_height: int

    @property
    def height(self) -> int:
        return self.line_height * len(self.lines)


class FFmpegRenderer:
    def __init__(
        self,
        media_directory: Path,
        artifact_directory: Path,
        settings: FFmpegSettings | None = None,
    ) -> None:
        self.media_directory = media_directory.resolve()
        self.artifact_directory = artifact_directory.resolve()
        self.settings = settings or FFmpegSettings()

    def render(
        self,
        timeline: Timeline,
        config: RenderConfig,
        motion_plan: MotionDirectionPlan | None = None,
        attention_plan: AttentionPlan | None = None,
        style_plan: StyleDirectionPlan | None = None,
        longform_plan: LongFormVideoPlan | None = None,
    ) -> RenderResult:
        self._validate_binaries()
        composition = None
        if motion_plan is not None:
            if motion_plan.project_id != timeline.project_id:
                raise RendererError("Motion plan does not belong to this timeline.")
            if motion_plan.duration_ms != timeline.duration_ms:
                raise RendererError("Motion plan duration does not match this timeline.")
            composition = MotionCompositionCompiler().compile(motion_plan, config)
            if motion_plan.editorial_plan is None:
                raise RendererError("Validated editorial template direction is missing.")
            EditorialCompositionCompiler().compile(motion_plan.editorial_plan, config)
        if attention_plan is not None:
            if attention_plan.project_id != timeline.project_id:
                raise RendererError("Attention plan does not belong to this timeline.")
            AttentionCompiler().compile(
                attention_plan,
                config,
                timeline.zoom_clips if timeline.presentation.zoom_enabled else [],
            )
        if style_plan is not None:
            if style_plan.project_id != timeline.project_id:
                raise RendererError("Style plan does not belong to this timeline.")
            if timeline.visual_variant != style_plan.decision.selected_variant:
                raise RendererError("Style selection does not match this timeline.")
            StyleCompiler().compile(style_plan, config)
        longform_composition = None
        if longform_plan is not None:
            if longform_plan.project_id != timeline.project_id:
                raise RendererError("Long-form plan does not belong to this timeline.")
            report = LongFormCompiler().validate_timeline(longform_plan, timeline, config)
            if not report.passed:
                raise RendererError(
                    "Long-form media validation failed: " + "; ".join(report.issues)
                )
            longform_composition = LongFormCompiler().compile(longform_plan)
        scenes = sorted(timeline.scene_clips, key=lambda clip: clip.start_ms)
        self._validate_scene_layout(scenes, timeline.duration_ms)
        scene_paths = [self._safe_media_path(clip.source_uri, VIDEO_EXTENSIONS) for clip in scenes]
        self._validate_scene_source_ranges(scenes, scene_paths)
        audio_paths = [
            self._safe_media_path(clip.source_uri, AUDIO_EXTENSIONS)
            for clip in timeline.audio_clips
        ]
        self.artifact_directory.mkdir(parents=True, exist_ok=True)
        output_path = self.artifact_directory / config.output_filename
        thumbnail_path = output_path.with_name(f"{output_path.stem}-thumbnail.jpg")
        command = self._render_command(
            timeline,
            config,
            scenes,
            scene_paths,
            audio_paths,
            output_path,
            motion_plan,
            attention_plan,
            style_plan,
            longform_plan,
        )
        self._run(command, "FFmpeg render")
        self._run(
            [
                self.settings.ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{min(0.5, timeline.duration_ms / 2_000):.3f}",
                "-i",
                str(output_path),
                "-frames:v",
                "1",
                str(thumbnail_path),
            ],
            "FFmpeg thumbnail",
        )
        probe = self.probe(output_path)
        duration_ms = round(float(probe["format"]["duration"]) * 1_000)
        streams = cast(list[dict[str, Any]], probe["streams"])
        video_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "video"),
            None,
        )
        if video_stream is None:
            raise RendererError("ffprobe found no video stream in the rendered MP4.")
        if longform_plan is not None:
            self._validate_longform_output(output_path, probe)
            contact_sheet_path = output_path.with_name(
                f"{output_path.stem}-contact-sheet.jpg"
            )
            self._run(
                [
                    self.settings.ffmpeg_path,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(output_path),
                    "-vf",
                    "fps=1/15,scale=320:-1,tile=4x3",
                    "-frames:v",
                    "1",
                    str(contact_sheet_path),
                ],
                "FFmpeg long-form contact sheet",
            )
        return RenderResult(
            status="succeeded",
            output_path=str(output_path),
            thumbnail_path=str(thumbnail_path),
            duration_ms=duration_ms,
            width=int(video_stream["width"]),
            height=int(video_stream["height"]),
            has_video=True,
            has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
            motion_composition_hash=(
                composition.deterministic_hash if composition is not None else None
            ),
            long_form_composition_hash=(
                longform_composition.deterministic_hash
                if longform_composition is not None
                else None
            ),
        )

    def probe(self, path: Path) -> dict[str, Any]:
        completed = self._run(
            [
                self.settings.ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                (
                    "stream=codec_type,codec_name,width,height,avg_frame_rate,"
                    "duration,start_time,duration_ts,time_base:stream_tags=DURATION:"
                    "format=duration"
                ),
                "-of",
                "json",
                str(path),
            ],
            "ffprobe validation",
            capture_output=True,
        )
        try:
            return cast(dict[str, Any], json.loads(completed.stdout))
        except (json.JSONDecodeError, TypeError) as error:
            raise RendererError("ffprobe returned invalid media metadata.") from error

    def _validate_longform_output(
        self,
        path: Path,
        probe: dict[str, Any],
    ) -> None:
        streams = cast(list[dict[str, Any]], probe.get("streams", []))
        video = next(
            (stream for stream in streams if stream.get("codec_type") == "video"),
            None,
        )
        audio = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"),
            None,
        )
        metadata = cast(dict[str, Any], probe.get("format", {}))
        duration = float(metadata.get("duration", 0))
        issues: list[str] = []
        if abs(duration - 180) > 0.05:
            issues.append("duration is not exactly 180 seconds")
        if video is None or (int(video.get("width", 0)), int(video.get("height", 0))) != (
            2560,
            1440,
        ):
            issues.append("video dimensions are not 2560x1440")
        if video is None or video.get("codec_name") != "h264":
            issues.append("video codec is not H.264")
        if video is None or abs(
            _frame_rate(str(video.get("avg_frame_rate", "0/1"))) - 30
        ) > 0.01:
            issues.append("frame rate is not 30 fps")
        if audio is None or audio.get("codec_name") != "aac":
            issues.append("audio codec is not AAC")
        video_duration = _stream_duration(video, duration)
        audio_duration = _stream_duration(audio, 0)
        if audio is not None and abs(video_duration - audio_duration) > 0.25:
            issues.append("audio and video are not synchronized")
        if issues:
            raise RendererError("Long-form output validation failed: " + "; ".join(issues))

        diagnostics = self._run(
            [
                self.settings.ffmpeg_path,
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-vf",
                "blackdetect=d=2:pix_th=0.10,freezedetect=n=-60dB:d=10",
                "-af",
                "silencedetect=noise=-50dB:d=8",
                "-f",
                "null",
                "-",
            ],
            "FFmpeg long-form quality scan",
            capture_output=True,
        ).stderr
        if re.search(r"black_duration:(?:[2-9]|\d{2,})(?:\.\d+)?", diagnostics):
            raise RendererError("Long-form output contains an unexplained black interval.")
        if "freeze_duration:" in diagnostics:
            raise RendererError("Long-form output contains a frozen interval over 10 seconds.")
        if re.search(r"silence_duration:(?:[89]|\d{2,})(?:\.\d+)?", diagnostics):
            raise RendererError("Long-form output contains an extended silent interval.")

    def _render_command(
        self,
        timeline: Timeline,
        config: RenderConfig,
        scenes: Sequence[SceneClip],
        scene_paths: Sequence[Path],
        audio_paths: Sequence[Path],
        output_path: Path,
        motion_plan: MotionDirectionPlan | None = None,
        attention_plan: AttentionPlan | None = None,
        style_plan: StyleDirectionPlan | None = None,
        longform_plan: LongFormVideoPlan | None = None,
    ) -> list[str]:
        command = [self.settings.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y"]
        for path in scene_paths:
            command.extend(["-i", str(path)])
        for path in audio_paths:
            command.extend(["-i", str(path)])
        filters = self._video_filters(
            timeline,
            scenes,
            config,
            motion_plan,
            attention_plan,
            style_plan,
            longform_plan,
        )
        audio_label = self._audio_filters(
            timeline.audio_clips,
            len(scene_paths),
            timeline.duration_ms,
            filters,
            longform_plan.audio_mix if longform_plan is not None else None,
        )
        command.extend(["-filter_complex", ";".join(filters), "-map", "[vout]"])
        if audio_label is not None:
            command.extend(["-map", f"[{audio_label}]", "-c:a", "aac", "-b:a", "128k"])
        command.extend(
            [
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(config.fps),
                "-t",
                f"{timeline.duration_ms / 1_000:.3f}",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        return command

    def _video_filters(
        self,
        timeline: Timeline,
        scenes: Sequence[SceneClip],
        config: RenderConfig,
        motion_plan: MotionDirectionPlan | None = None,
        attention_plan: AttentionPlan | None = None,
        style_plan: StyleDirectionPlan | None = None,
        longform_plan: LongFormVideoPlan | None = None,
    ) -> list[str]:
        filters: list[str] = []
        labels: list[str] = []
        for index, scene in enumerate(scenes):
            duration = (scene.end_ms - scene.start_ms) / 1_000
            source_start = scene.source_start_ms / 1_000
            label = f"scene{index}"
            filters.append(
                f"[{index}:v]trim=start={source_start:.3f}:duration={duration:.3f},"
                "setpts=PTS-STARTPTS,"
                f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
                f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2:black,"
                f"fps={config.fps},setsar=1[{label}]"
            )
            labels.append(f"[{label}]")
        if len(labels) == 1:
            filters.append(f"{labels[0]}null[vbase]")
        else:
            filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[vbase]")
        current = "vbase"
        cursor_events = _renderable_cursor_events(timeline, config)
        if cursor_events:
            filters.append(self._cursor_filter(cursor_events, config, current, "vcursor"))
            current = "vcursor"
            for index, event in enumerate(
                item for item in cursor_events if item.event_type == "click"
            ):
                next_label = f"vclick{index}"
                filters.append(
                    self._click_filter(event, config, current, next_label)
                )
                current = next_label
        if timeline.presentation.zoom_enabled and timeline.zoom_clips:
            filters.append(self._zoom_filter(timeline.zoom_clips, config, current, "vzoom"))
            current = "vzoom"
        legacy_directed_composition = longform_plan is not None
        if legacy_directed_composition and style_plan is not None:
            style_filters, current = self._style_filters(style_plan, motion_plan, config, current)
            filters.extend(style_filters)
        if legacy_directed_composition and longform_plan is not None:
            targets = {
                target.id: target
                for target in (attention_plan.targets if attention_plan is not None else [])
            }
            for index, beat in enumerate(longform_plan.beats):
                output = f"vlongform{index}"
                filters.append(
                    self._longform_beat_filter(
                        beat,
                        config,
                        current,
                        output,
                        targets.get(beat.target_id) if beat.target_id is not None else None,
                    )
                )
                current = output
            for index, interval in enumerate(longform_plan.condensed_intervals):
                output = f"vcondensed{index}"
                filters.append(
                    self._condensed_interval_filter(interval, config, current, output)
                )
                current = output
        if (
            legacy_directed_composition
            and motion_plan is not None
            and motion_plan.editorial_plan is not None
        ):
            for index, editorial_scene in enumerate(motion_plan.editorial_plan.scenes):
                next_label = f"veditorial{index}"
                filters.extend(
                    self._editorial_scene_filters(
                        editorial_scene, config, current, next_label, index
                    )
                )
                current = next_label
        if legacy_directed_composition and motion_plan is not None:
            for index, cue in enumerate(
                sorted(
                    motion_plan.cues,
                    key=lambda item: (
                        motion_plan.design_tokens.layer_order.index(item.layer),
                        item.start_ms,
                        item.id,
                    ),
                )
            ):
                next_label = f"vmotion{index}"
                filters.append(
                    self._motion_cue_filter(
                        cue,
                        motion_plan,
                        config,
                        current,
                        next_label,
                    )
                )
                current = next_label
        if (
            (legacy_directed_composition or timeline.demo_mode == "presentation_demo")
            and attention_plan is not None
        ):
            compiled_attention = AttentionCompiler().compile(
                attention_plan,
                config,
                timeline.zoom_clips if timeline.presentation.zoom_enabled else [],
            )
            callout_by_id = {item.id: item for item in attention_plan.callouts}
            for index, compiled in enumerate(compiled_attention.callouts):
                next_label = f"vattention{index}"
                filters.append(
                    self._attention_filter(
                        callout_by_id[compiled.id], compiled, config, current, next_label
                    )
                )
                current = next_label
        if timeline.demo_mode == "presentation_demo":
            filters.extend(
                self._presentation_demo_filters(
                    timeline,
                    config,
                    current,
                    "vpresentationdemo",
                    motion_plan,
                )
            )
            current = "vpresentationdemo"

        captions = sorted(timeline.caption_clips, key=lambda clip: clip.start_ms)
        for index, caption in enumerate(captions):
            next_label = f"vcaption{index}"
            filters.append(self._caption_filter(caption, current, next_label))
            current = next_label
        if (
            timeline.demo_mode == "product_demo"
            and timeline.presentation.template != "edge_to_edge"
        ):
            filters.extend(
                self._presentation_filters(
                    timeline.presentation.template,
                    timeline.duration_ms,
                    config,
                    current,
                    "vpresentation",
                )
            )
            current = "vpresentation"
        filters.append(f"[{current}]null[vout]")
        return filters

    @staticmethod
    def _longform_beat_filter(
        beat: Any,
        config: RenderConfig,
        input_label: str,
        output_label: str,
        target: Any | None = None,
    ) -> str:
        enable = f"between(t,{beat.start_ms / 1_000:.3f},{beat.end_ms / 1_000:.3f})"
        margin = round(config.width * 0.04)
        if beat.template_id == "framed_product":
            base = (
                f"[{input_label}]drawbox=x={margin}:y={margin}:w=iw-{margin * 2}:"
                f"h=ih-{margin * 2}:color=0x86E1A8@0.58:t=3:"
                f"enable='{enable}'"
            )
        else:
            layouts = {
                "hook": (0, 0.78, 1.0, 0.22, "111214", 0.72),
                "feature_callout": (0.04, 0.04, 0.28, 0.22, "F2C66D", 0.24),
                "split_explanation": (0, 0, 0.38, 1.0, "111214", 0.28),
                "proof_safety": (0.04, 0.72, 0.42, 0.18, "86E1A8", 0.24),
                "closing": (0, 0.80, 1.0, 0.20, "111214", 0.76),
            }
            x, y, width, height, color, opacity = layouts[beat.template_id]
            base = (
                f"[{input_label}]drawbox=x={round(config.width * x)}:"
                f"y={round(config.height * y)}:w={round(config.width * width)}:"
                f"h={round(config.height * height)}:color=0x{color}@{opacity:.2f}:"
                f"t=fill:enable='{enable}'"
            )
        if target is not None:
            center_x = round((target.rect.x + target.rect.width / 2) * config.width)
            center_y = round((target.rect.y + target.rect.height / 2) * config.height)
            radius = max(10, round(config.height * 0.012))
            base += (
                f",drawbox=x={center_x - radius}:y={center_y - radius}:"
                f"w={radius * 2}:h={radius * 2}:color=0xFF5A5F@0.90:t=3:"
                f"enable='{enable}'"
            )
        return f"{base}[{output_label}]"

    def _style_filters(
        self,
        plan: StyleDirectionPlan,
        motion_plan: MotionDirectionPlan | None,
        config: RenderConfig,
        input_label: str,
    ) -> tuple[list[str], str]:
        overrides = {item.scene_id: item.variant_id for item in plan.overrides}
        scene_ranges = (
            [
                (scene.scene_id, scene.start_ms, scene.end_ms)
                for scene in motion_plan.editorial_plan.scenes
            ]
            if motion_plan is not None and motion_plan.editorial_plan is not None
            else [
                (scene_id, 0, motion_plan.duration_ms if motion_plan else 1)
                for scene_id in plan.scene_ids
            ]
        )
        filters: list[str] = []
        current = input_label
        for index, (scene_id, start_ms, end_ms) in enumerate(scene_ranges):
            variant = overrides.get(scene_id, plan.decision.selected_variant)
            output = f"vstyle{index}"
            filters.append(
                self._style_variant_filter(
                    variant,
                    len(plan.recommendation_evidence_refs),
                    start_ms,
                    end_ms,
                    config,
                    current,
                    output,
                )
            )
            current = output
        return filters, current

    def _condensed_interval_filter(
        self,
        interval: Any,
        config: RenderConfig,
        input_label: str,
        output_label: str,
    ) -> str:
        font = _escape_filter_path(self._font_path())
        text = _escape_drawtext(
            f"{interval.label} · actual {interval.actual_elapsed_ms / 1_000:.1f}s"
        )
        enable = (
            f"between(t,{interval.start_ms / 1_000:.3f},"
            f"{interval.end_ms / 1_000:.3f})"
        )
        margin = round(config.width * 0.035)
        return (
            f"[{input_label}]drawtext=fontfile='{font}':text='{text}':expansion=none:"
            f"fontcolor=white:fontsize={max(20, round(config.height * 0.024))}:"
            "box=1:boxcolor=0x111214@0.84:boxborderw=10:"
            f"x=w-text_w-{margin}:y={margin}:enable='{enable}'[{output_label}]"
        )

    def _style_variant_filter(
        self,
        variant: VisualVariantId,
        evidence_count: int,
        start_ms: int,
        end_ms: int,
        config: RenderConfig,
        input_label: str,
        output_label: str,
    ) -> str:
        enable = f"between(t,{start_ms / 1_000:.3f},{end_ms / 1_000:.3f})"
        margin = round(config.width * 0.025)
        if variant == "editorial_story":
            return (
                f"[{input_label}]drawbox=x={margin}:y={margin}:w=3:h=ih-{margin * 2}:"
                f"color=0xF2F0EA@0.72:t=fill:enable='{enable}'[{output_label}]"
            )
        if variant == "product_spotlight":
            return (
                f"[{input_label}]drawbox=x={margin}:y={margin}:w=iw-{margin * 2}:"
                f"h=ih-{margin * 2}:color=white@0.32:t=2:enable='{enable}'[{output_label}]"
            )
        font = _escape_filter_path(self._font_path())
        text = _escape_drawtext(f"{evidence_count} linked project inputs")
        return (
            f"[{input_label}]drawtext=fontfile='{font}':text='{text}':expansion=none:"
            f"fontcolor=0xF5F6F7:fontsize={max(18, round(config.height * 0.024))}:"
            "box=1:boxcolor=0x111214@0.82:boxborderw=10:"
            f"x={margin}:y={margin}:enable='{enable}'[{output_label}]"
        )

    def _attention_filter(
        self,
        callout: Any,
        compiled: Any,
        config: RenderConfig,
        input_label: str,
        output_label: str,
    ) -> str:
        start = callout.start_ms / 1_000
        end = callout.end_ms / 1_000
        enable = f"between(t,{start:.3f},{end:.3f})"
        text = _escape_drawtext(callout.text)
        font = _escape_filter_path(self._font_path())
        left = compiled.placement.endswith("left")
        top = compiled.placement.startswith("top")
        x = round(config.width * (0.05 if left else 0.62))
        y = round(config.height * (0.08 if top else 0.72))
        return (
            f"[{input_label}]drawtext=fontfile='{font}':text='{text}':expansion=none:"
            f"fontcolor=0x111214:fontsize={max(22, round(config.height * 0.032))}:"
            "box=1:boxcolor=0x86E1A8@0.95:boxborderw=14:"
            f"x={x}:y={y}:enable='{enable}'[{output_label}]"
        )

    def _editorial_scene_filters(
        self,
        scene: Any,
        config: RenderConfig,
        input_label: str,
        output_label: str,
        index: int,
    ) -> list[str]:
        start = scene.start_ms / 1_000
        end = scene.end_ms / 1_000
        enable = f"between(t,{start:.3f},{end:.3f})"
        safe_x = round(config.width * 0.05)
        safe_y = round(config.height * 0.05)
        text = _escape_drawtext(scene.title)
        font = _escape_filter_path(self._font_path())
        panel_ratio = 0.38 if scene.template_id == "split_explanation" else 0.5
        panel_width = round(config.width * panel_ratio)
        filters: list[str] = []
        current = input_label
        if scene.template_id == "framed_product":
            filters.append(
                f"[{current}]drawbox=x={safe_x}:y={safe_y}:w=iw-{safe_x * 2}:"
                f"h=ih-{safe_y * 2}:color=white@0.35:t=2:enable='{enable}'"
                f"[veditorialbox{index}]"
            )
            current = f"veditorialbox{index}"
        else:
            if scene.template_id in {"hook", "closing"}:
                box_y = round(config.height * 0.62)
                box_height = config.height - box_y
            elif scene.template_id == "proof_safety":
                box_y = round(config.height * 0.7)
                box_height = config.height - box_y
            else:
                box_y = safe_y
                box_height = round(config.height * 0.28)
            filters.append(
                f"[{current}]drawbox=x={safe_x}:y={box_y}:w={panel_width}:h={box_height}:"
                f"color=0x111214@0.78:t=fill:enable='{enable}'[veditorialbox{index}]"
            )
            current = f"veditorialbox{index}"
        title_y = (
            round(config.height * 0.69)
            if scene.template_id in {"hook", "closing", "proof_safety"}
            else safe_y + round(config.height * 0.07)
        )
        filters.append(
            f"[{current}]drawtext=fontfile='{font}':text='{text}':expansion=none:"
            f"fontcolor=0xF5F6F7:fontsize={max(24, round(config.height * 0.043))}:"
            f"x={safe_x + 24}:y={title_y}:enable='{enable}'[{output_label}]"
        )
        return filters

    def _motion_cue_filter(
        self,
        cue: Any,
        plan: MotionDirectionPlan,
        config: RenderConfig,
        input_label: str,
        output_label: str,
    ) -> str:
        """Compile one validated cue into an authored FFmpeg filter; no model expression is used."""
        start = cue.start_ms / 1_000
        end = cue.end_ms / 1_000
        enable = f"between(t,{start:.3f},{end:.3f})"
        accent = plan.design_tokens.accent.removeprefix("#")
        safe_x = round(config.width * 0.055)
        safe_y = round(config.height * 0.07)
        if cue.primitive == "background_dim":
            return (
                f"[{input_label}]drawbox=x=0:y=0:w=iw:h=ih:color=black@0.28:t=fill:"
                f"enable='{enable}'[{output_label}]"
            )
        if cue.primitive in {"highlight_reveal", "scale_settle"}:
            ratio = 0.009 if cue.primitive == "highlight_reveal" else 0.004
            height = max(6, round(config.height * ratio))
            return (
                f"[{input_label}]drawbox=x={safe_x}:y={safe_y}:"
                f"w=iw-{safe_x * 2}:h={height}:color=0x{accent}@0.92:t=fill:"
                f"enable='{enable}'[{output_label}]"
            )
        if cue.primitive == "browser_frame_move":
            inset = max(8, round(config.width * 0.018))
            return (
                f"[{input_label}]drawbox=x={inset}:y={inset}:w=iw-{inset * 2}:"
                f"h=ih-{inset * 2}:color=0x{accent}@0.58:t=2:"
                f"enable='{enable}'[{output_label}]"
            )
        text = _escape_drawtext(cue.text or plan.summary)
        font = _escape_filter_path(self._font_path())
        font_size = (
            plan.design_tokens.title_size
            if cue.primitive == "stagger_text"
            else plan.design_tokens.body_size
        )
        y = safe_y if cue.layer != "captions" else config.height - safe_y - font_size * 2
        return (
            f"[{input_label}]drawtext=fontfile='{font}':text='{text}':expansion=none:"
            f"fontcolor=0x{plan.design_tokens.text.removeprefix('#')}:fontsize={font_size}:"
            "box=1:boxcolor=black@0.58:boxborderw=14:"
            f"x={safe_x}:y={y}:enable='{enable}'[{output_label}]"
        )

    def _presentation_demo_filters(
        self,
        timeline: Timeline,
        config: RenderConfig,
        input_label: str,
        output_label: str,
        motion_plan: MotionDirectionPlan | None,
    ) -> list[str]:
        """Populate the shipped presentation pack; runtime never creates layout geometry."""
        if timeline.presentation_pack_id != PRESENTATION_PACK_ID:
            raise RendererError("Presentation Demo references an unsupported template pack.")
        try:
            pack = resolve_presentation_pack(timeline.presentation_pack_id)
            schedule = build_presentation_schedule(timeline.duration_ms)
        except ValueError as error:
            raise RendererError(str(error)) from error

        templates = {template.id: template for template in pack.templates}
        product_templates = tuple(
            template for template in pack.templates if template.requires_product
        )
        duration = timeline.duration_ms / 1_000
        filters: list[str] = []
        split_labels = [
            label
            for index in range(len(product_templates))
            for label in (f"ptsource{index}bg", f"ptsource{index}fg")
        ]
        filters.append(
            f"[{input_label}]split={len(split_labels)}"
            + "".join(f"[{label}]" for label in split_labels)
        )
        filters.append(
            f"color=c=0x{resolve_palette_color(product_templates[0].palette.canvas)}:"
            f"s={config.width}x{config.height}:r={config.fps}:"
            f"d={duration:.3f}[presentationcanvas]"
        )
        current = "presentationcanvas"
        corner_radius = max(8, round(config.width * 0.008))

        for index, template in enumerate(product_templates):
            aperture = template.aperture
            width = max(2, round(config.width * aperture.w) // 2 * 2)
            height = max(2, round(config.height * aperture.h) // 2 * 2)
            x = round(config.width * aperture.x)
            y = round(config.height * aperture.y)
            slug = template.id.split("@", maxsplit=1)[0].replace("-", "_")
            background_label = f"pt_{slug}_background"
            foreground_label = f"pt_{slug}_foreground"
            contained_label = f"pt_{slug}_contained"
            mask_label = f"pt_{slug}_mask"
            frame_label = f"pt_{slug}_frame"
            next_label = f"pt_{slug}_{index}"
            active_intervals = [
                entry for entry in schedule if entry.template_id == template.id
            ]
            enable = "+".join(
                _half_open_time_window(entry.start_ms, entry.end_ms)
                for entry in active_intervals
            )
            rounded_mask = (
                f"if(gt(abs(X-W/2),W/2-{corner_radius})*"
                f"gt(abs(Y-H/2),H/2-{corner_radius}),"
                f"if(lte(hypot(abs(X-W/2)-(W/2-{corner_radius}),"
                f"abs(Y-H/2)-(H/2-{corner_radius})),{corner_radius}),255,0),255)"
            )
            filters.extend(
                [
                    f"[ptsource{index}bg]scale={width}:{height}:"
                    "force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},setsar=1,gblur=sigma=18:steps=2,"
                    f"format=rgba[{background_label}]",
                    f"[ptsource{index}fg]scale={width}:{height}:"
                    "force_original_aspect_ratio=decrease,setsar=1,"
                    f"format=rgba[{foreground_label}]",
                    f"[{background_label}][{foreground_label}]overlay="
                    f"x=({width}-w)/2:y=({height}-h)/2:eof_action=repeat:"
                    f"shortest=0:format=auto[{contained_label}]",
                    f"color=c=white:s={width}x{height}:r={config.fps}:d={duration:.3f},"
                    f"format=gray,geq=lum='{rounded_mask}',gblur=sigma=0.7[{mask_label}]",
                    f"[{contained_label}][{mask_label}]alphamerge[{frame_label}]",
                    f"[{current}][{frame_label}]overlay=x={x}:y={y}:eof_action=repeat:"
                    f"shortest=0:format=auto:enable='{enable}'[{next_label}]",
                ]
            )
            current = next_label

        safe_x = round(config.width * 0.05)
        safe_y = round(config.height * 0.055)
        product_accent = resolve_palette_color(product_templates[0].palette.accent)
        filters.append(
            f"[{current}]drawbox=x={safe_x}:y={safe_y}:w=iw-{safe_x * 2}:h=2:"
            f"color=0x{product_accent}@0.88:t=fill:"
            f"enable='{_half_open_time_window(5_000, 115_000)}'[ptproductrule]"
        )
        current = "ptproductrule"

        editorial_scenes = (
            list(motion_plan.editorial_plan.scenes)
            if motion_plan is not None and motion_plan.editorial_plan is not None
            else []
        )
        fallback_summary = (
            motion_plan.summary if motion_plan is not None else "Show the product in action"
        )
        product_copy_index = 0
        font = _escape_filter_path(self._font_path())
        for index, entry in enumerate(schedule):
            template = templates[entry.template_id]
            slug = entry.template_id.split("@", maxsplit=1)[0].replace("-", "_")
            enable = _half_open_time_window(entry.start_ms, entry.end_ms)
            if entry.role == "intro":
                source = editorial_scenes[0] if editorial_scenes else None
            elif entry.role == "outro":
                source = editorial_scenes[-1] if editorial_scenes else None
            else:
                source = (
                    editorial_scenes[product_copy_index % len(editorial_scenes)]
                    if editorial_scenes
                    else None
                )
                product_copy_index += 1
            if entry.template_id == "hook-question@1":
                title = source.title if source is not None else "What should viewers see first?"
            elif entry.template_id == "brand-reveal@1":
                title = fallback_summary
            elif entry.template_id == "brand-outro@1":
                title = timeline.cta_text or "See the complete workflow"
            else:
                title = source.title if source is not None else fallback_summary
            title = _truncate_slot(title, template.max_title_chars)
            body = (
                _truncate_slot(source.body, template.max_body_chars)
                if source is not None and source.body
                else None
            )
            transition_slug = template.transition.name.replace("-", "_")
            next_label = f"pt_{slug}_{transition_slug}_copy_{index}"
            start = entry.start_ms / 1_000
            transition_seconds = template.transition.duration_ms / 1_000
            progress = (
                "1"
                if transition_seconds == 0
                else f"max(0,min(1,(t-{start:.3f})/{transition_seconds:.3f}))"
            )
            palette_canvas = resolve_palette_color(template.palette.canvas)
            palette_ink = resolve_palette_color(template.palette.ink)
            palette_surface = resolve_palette_color(template.palette.surface)
            palette_accent = resolve_palette_color(template.palette.accent)
            palette_outline = resolve_palette_color(template.palette.outline)

            if entry.template_id in {"brand-reveal@1", "brand-outro@1"}:
                title_layout = _layout_text_block(
                    title,
                    preferred=max(8, round(config.height * 0.068)),
                    max_width=config.width - safe_x * 2,
                    max_height=round(config.height * 0.56),
                    max_lines=3,
                )
                centered_title_x = _safe_text_x_expression(
                    _copy_x_position(template.copy_layout, config),
                    left=safe_x,
                    right=config.width - safe_x,
                )
                centered_title_y = (
                    round(config.height * template.copy_layout.y)
                    - title_layout.height // 2
                )
                filter_chain = (
                    f"[{current}]drawbox=x=0:y=0:w=iw:h=ih:"
                    f"color=0x{palette_canvas}@1.0:t=fill:"
                    f"enable='{enable}'"
                )
                for line_index, line in enumerate(title_layout.lines):
                    escaped_line = _escape_drawtext(line)
                    line_y = centered_title_y + line_index * title_layout.line_height
                    filter_chain += (
                        f",drawtext=fontfile='{font}':text='{escaped_line}':"
                        f"expansion=none:fontcolor=0x{palette_ink}:"
                        f"fontsize={title_layout.font_size}:x='{centered_title_x}':"
                        f"y={line_y}:enable='{enable}'"
                    )
                filters.append(f"{filter_chain}[{next_label}]")
            elif entry.template_id == "hook-question@1":
                title_layout = _layout_text_block(
                    title,
                    preferred=max(8, round(config.height * 0.062)),
                    max_width=config.width - safe_x * 2,
                    max_height=round(config.height * 0.56),
                    max_lines=3,
                )
                hook_title_y = _animated_position(
                    round(config.height * template.copy_layout.y),
                    round(config.height * template.transition.copy_offset_y),
                    progress,
                )
                hook_title_x = _safe_text_x_expression(
                    _copy_x_position(template.copy_layout, config),
                    left=safe_x,
                    right=config.width - safe_x,
                )
                filter_chain = f"[{current}]null"
                for line_index, line in enumerate(title_layout.lines):
                    escaped_line = _escape_drawtext(line)
                    line_y_offset = (
                        line_index * title_layout.line_height - title_layout.height // 2
                    )
                    filter_chain += (
                        f",drawtext=fontfile='{font}':text='{escaped_line}':"
                        f"expansion=none:fontcolor=0x{palette_ink}:"
                        f"fontsize={title_layout.font_size}:x='{hook_title_x}':"
                        f"y='({hook_title_y})+{line_y_offset}':enable='{enable}'"
                    )
                filter_chain += (
                    f",drawbox=x={safe_x}:y=h-{safe_y}:"
                    f"w=iw-{safe_x * 2}:h=2:color=0x{palette_accent}@0.82:"
                    f"t=fill:enable='{enable}'"
                )
                filters.append(f"{filter_chain}[{next_label}]")
            else:
                aperture = template.aperture
                product_x = round(config.width * aperture.x)
                product_y = round(config.height * aperture.y)
                product_w = max(2, round(config.width * aperture.w) // 2 * 2)
                product_h = max(2, round(config.height * aperture.h) // 2 * 2)
                copy_layout = template.copy_layout
                title_x = round(config.width * copy_layout.x)
                title_y = round(config.height * copy_layout.y)
                panel_w = max(2, round(config.width * copy_layout.panel_width))
                panel_h = max(2, round(config.height * copy_layout.panel_height))
                frame_x = _animated_position(
                    product_x,
                    round(config.width * template.transition.product_offset_x),
                    progress,
                )
                frame_y = _animated_position(
                    product_y,
                    round(config.height * template.transition.product_offset_y),
                    progress,
                )
                animated_title_x = _animated_position(
                    title_x,
                    round(config.width * template.transition.copy_offset_x),
                    progress,
                )
                animated_title_y = _animated_position(
                    title_y,
                    round(config.height * template.transition.copy_offset_y),
                    progress,
                )
                copy_width = max(2, panel_w - 24)
                content_height = max(5, panel_h - 12)
                title_layout = _layout_text_block(
                    title,
                    preferred=max(7, round(config.height * 0.038)),
                    max_width=copy_width,
                    max_height=content_height,
                    max_lines=3,
                )
                safe_title_x = _safe_text_x_expression(
                    animated_title_x,
                    left=safe_x,
                    right=config.width - safe_x,
                )
                filter_chain = (
                    f"[{current}]drawbox=x='{frame_x}':y='{frame_y}':w={product_w}:"
                    f"h={product_h}:color=0x{palette_outline}@0.78:t=2:enable='{enable}',"
                    f"drawbox=x='({animated_title_x})-12':y='({animated_title_y})-18':"
                    f"w={panel_w}:h={panel_h}:color=0x{palette_surface}@0.10:t=fill:"
                    f"enable='{enable}'"
                )
                for line_index, line in enumerate(title_layout.lines):
                    escaped_line = _escape_drawtext(line)
                    title_y_offset = line_index * title_layout.line_height
                    filter_chain += (
                        f",drawtext=fontfile='{font}':text='{escaped_line}':"
                        f"expansion=none:fontcolor=0x{palette_ink}:"
                        f"fontsize={title_layout.font_size}:x='{safe_title_x}':"
                        f"y='({animated_title_y})+{title_y_offset}':enable='{enable}'"
                    )
                if body:
                    body_gap = max(2, round(config.height * 0.008))
                    body_height = content_height - title_layout.height - body_gap
                    if body_height >= 5:
                        body_layout = _layout_text_block(
                            body,
                            preferred=max(5, round(config.height * 0.021)),
                            max_width=copy_width,
                            max_height=body_height,
                            max_lines=3,
                        )
                        for line_index, line in enumerate(body_layout.lines):
                            escaped_line = _escape_drawtext(line)
                            body_y_offset = (
                                title_layout.height
                                + body_gap
                                + line_index * body_layout.line_height
                            )
                            filter_chain += (
                                f",drawtext=fontfile='{font}':text='{escaped_line}':"
                                f"expansion=none:fontcolor=0x{palette_ink}@0.82:"
                                f"fontsize={body_layout.font_size}:x='{safe_title_x}':"
                                f"y='({animated_title_y})+{body_y_offset}':"
                                f"enable='{enable}'"
                            )
                filters.append(f"{filter_chain}[{next_label}]")
            current = next_label

        filters.append(f"[{current}]null[{output_label}]")
        return filters

    @staticmethod
    def _presentation_filters(
        template: str,
        duration_ms: int,
        config: RenderConfig,
        input_label: str,
        output_label: str,
    ) -> list[str]:
        if template == "soft_frame":
            top_color = "0x3a3b3f"
            bottom_color = "0x141518"
            inset = 0.06
        elif template == "spotlight":
            top_color = "0x94d6aa"
            bottom_color = "0x06391f"
            inset = 0.055
        else:
            raise RendererError(f"Unsupported presentation template: {template}")

        inner_width = max(2, round(config.width * (1 - inset * 2)) // 2 * 2)
        inner_height = max(2, round(config.height * (1 - inset * 2)) // 2 * 2)
        offset_x = (config.width - inner_width) // 2
        offset_y = (config.height - inner_height) // 2
        corner_radius = max(6, round(config.width * 0.008))
        duration = duration_ms / 1_000
        rounded_mask = (
            f"if(gt(abs(X-W/2),W/2-{corner_radius})*"
            f"gt(abs(Y-H/2),H/2-{corner_radius}),"
            f"if(lte(hypot(abs(X-W/2)-(W/2-{corner_radius}),"
            f"abs(Y-H/2)-(H/2-{corner_radius})),{corner_radius}),255,0),255)"
        )
        return [
            f"gradients=s={config.width}x{config.height}:r={config.fps}:"
            f"c0={top_color}:c1={bottom_color}:x0=0:y0=0:x1=0:y1={config.height}:"
            f"d={duration:.3f}:speed=0[presentationbg]",
            f"color=c=white:s={inner_width}x{inner_height}:r={config.fps}:"
            f"d={duration:.3f},format=gray,geq=lum='{rounded_mask}',"
            "gblur=sigma=0.7[presentationmask]",
            f"[{input_label}]scale={inner_width}:{inner_height}:"
            "force_original_aspect_ratio=increase,"
            f"crop={inner_width}:{inner_height},format=rgba[presentationcrop]",
            "[presentationcrop][presentationmask]alphamerge[presentationframe]",
            f"[presentationbg][presentationframe]overlay=x={offset_x}:y={offset_y}:"
            f"shortest=1:format=auto[{output_label}]",
        ]

    def _cursor_filter(
        self,
        events: Sequence[InteractionEvent],
        config: RenderConfig,
        input_label: str,
        output_label: str,
    ) -> str:
        marker_size = 28
        marker_margin = marker_size / 2 + 3
        points: list[tuple[float, float, float]] = []
        for event in events:
            x, y = _map_viewport_point(
                cast(float, event.x),
                cast(float, event.y),
                event.viewport,
                config,
            )
            x, y = _clamp_render_point(x, y, config, marker_margin)
            points.append((event.timestamp_ms / 1_000, x, y))
        x_expression = _motion_expression([(time, x) for time, x, _ in points])
        y_expression = _motion_expression([(time, y) for time, _, y in points])
        font = _escape_filter_path(self._font_path())
        return (
            f"[{input_label}]drawtext=fontfile='{font}':text='●':expansion=none:"
            f"fontcolor=white:borderw=2:bordercolor=black@0.92:fontsize={marker_size}:"
            f"x='{x_expression}-{marker_size / 2:.1f}':"
            f"y='{y_expression}-{marker_size / 2:.1f}'[{output_label}]"
        )

    def _click_filter(
        self,
        event: InteractionEvent,
        config: RenderConfig,
        input_label: str,
        output_label: str,
    ) -> str:
        if event.x is None or event.y is None:
            raise RendererError("A click indicator requires captured coordinates.")
        x, y = _map_viewport_point(event.x, event.y, event.viewport, config)
        start = event.timestamp_ms / 1_000
        end = start + 0.42
        font = _escape_filter_path(self._font_path())
        size = max(34, round(config.height * 0.045))
        x, y = _clamp_render_point(x, y, config, size / 2 + 5)
        return (
            f"[{input_label}]drawtext=fontfile='{font}':text='O':expansion=none:"
            f"fontcolor=0xFF5A5F@0.12:borderw=4:bordercolor=0xFF5A5F@0.96:"
            f"fontsize={size}:x={x:.3f}-text_w/2:y={y:.3f}-text_h/2:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{output_label}]"
        )

    def _zoom_filter(
        self,
        zooms: Sequence[ZoomClip],
        config: RenderConfig,
        input_label: str,
        output_label: str,
    ) -> str:
        zoom_expression = "1"
        x_expression = "0"
        y_expression = "0"
        for zoom in reversed(sorted(zooms, key=lambda clip: clip.start_ms)):
            start_frame = zoom.start_ms * config.fps / 1_000
            end_frame = zoom.end_ms * config.fps / 1_000
            active = f"between(on,{start_frame:.3f},{end_frame:.3f})"
            transition_frames = min(
                config.fps * 0.35,
                (end_frame - start_frame) / 3,
            )
            zoom_in_end = start_frame + transition_frames
            zoom_out_start = end_frame - transition_frames
            zoom_in_progress = f"max(0,min(1,(on-{start_frame:.3f})/{transition_frames:.3f}))"
            zoom_out_progress = f"max(0,min(1,(on-{zoom_out_start:.3f})/{transition_frames:.3f}))"
            eased_in = _easing_expression(zoom_in_progress, zoom.easing)
            eased_out = _easing_expression(zoom_out_progress, zoom.easing)
            scale_delta = zoom.scale - 1
            active_zoom = (
                f"if(lt(on,{zoom_in_end:.3f}),"
                f"1+{scale_delta:.3f}*({eased_in}),"
                f"if(lt(on,{zoom_out_start:.3f}),{zoom.scale:.3f},"
                f"{zoom.scale:.3f}-{scale_delta:.3f}*({eased_out})))"
            )
            source_viewport = zoom.source_viewport
            if source_viewport is None and zoom.source == "auto":
                source_viewport = Viewport(width=1280, height=720)
            if source_viewport is None:
                source_viewport = Viewport(width=config.width, height=config.height)
            focus_x = (
                zoom.focus_x
                if zoom.focus_x is not None
                else zoom.target_rect.x + zoom.target_rect.width / 2
            )
            focus_y = (
                zoom.focus_y
                if zoom.focus_y is not None
                else zoom.target_rect.y + zoom.target_rect.height / 2
            )
            center_x, center_y = _map_viewport_point(
                focus_x,
                focus_y,
                source_viewport,
                config,
            )
            zoom_expression = f"if({active},{active_zoom},{zoom_expression})"
            x_expression = (
                f"if({active},max(0,min(iw-iw/zoom,{center_x:.3f}-iw/(2*zoom))),{x_expression})"
            )
            y_expression = (
                f"if({active},max(0,min(ih-ih/zoom,{center_y:.3f}-ih/(2*zoom))),{y_expression})"
            )
        return (
            f"[{input_label}]zoompan=z='{zoom_expression}':x='{x_expression}':"
            f"y='{y_expression}':d=1:s={config.width}x{config.height}:fps={config.fps}"
            f"[{output_label}]"
        )

    def _caption_filter(
        self,
        caption: CaptionClip,
        input_label: str,
        output_label: str,
    ) -> str:
        start = caption.start_ms / 1_000
        end = caption.end_ms / 1_000
        text = _escape_drawtext(caption.text)
        font = _escape_filter_path(self._font_path())
        return (
            f"[{input_label}]drawtext=fontfile='{font}':text='{text}':"
            "expansion=none:fontcolor=white:"
            "fontsize=32:box=1:boxcolor=black@0.65:boxborderw=12:"
            f"x=(w-text_w)/2:y=h-text_h-48:enable='between(t,{start:.3f},{end:.3f})'"
            f"[{output_label}]"
        )

    def _font_path(self) -> Path:
        candidates = [
            Path(self.settings.font_path) if self.settings.font_path else None,
            Path("C:/Windows/Fonts/InterVariable.ttf"),
            Path("C:/Windows/Fonts/Inter-Regular.ttf"),
            Path("/usr/share/fonts/truetype/inter-vf/Inter.var.ttf"),
            Path("/usr/share/fonts/truetype/inter/Inter.var.ttf"),
            Path("/usr/share/fonts/truetype/inter/Inter-Regular.ttf"),
            Path("/usr/share/fonts/opentype/inter/Inter-Regular.otf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        for candidate in candidates:
            if candidate is not None and candidate.is_file():
                return candidate.resolve()
        raise RendererError("A TrueType font is required to render captions.")

    @staticmethod
    def _audio_filters(
        clips: Sequence[AudioClip],
        input_offset: int,
        duration_ms: int,
        filters: list[str],
        mix: AudioMixPlan | None = None,
    ) -> str | None:
        if not clips:
            return None
        labels: list[str] = []
        for index, clip in enumerate(clips):
            duration = (clip.end_ms - clip.start_ms) / 1_000
            delay = clip.start_ms
            label = f"audio{index}"
            filters.append(
                f"[{input_offset + index}:a]atrim=duration={duration:.3f},"
                f"asetpts=PTS-STARTPTS,adelay={delay}|{delay}[{label}]"
            )
            labels.append(f"[{label}]")
        duration = duration_ms / 1_000
        output_label = "amixed" if mix is not None else "aout"
        if len(labels) == 1:
            filters.append(
                f"{labels[0]}apad=whole_dur={duration:.3f},"
                f"atrim=duration={duration:.3f}[{output_label}]"
            )
        else:
            filters.append(
                f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,"
                f"apad=whole_dur={duration:.3f},"
                f"atrim=duration={duration:.3f}[{output_label}]"
            )
        if mix is not None:
            filters.append(
                f"[amixed]loudnorm=I={mix.narration_lufs:.1f}:TP=-1.5:LRA=11[aout]"
            )
        return "aout"

    def _safe_media_path(self, supplied: str, extensions: set[str]) -> Path:
        candidate = Path(supplied)
        if not candidate.is_absolute():
            candidate = self.media_directory / candidate
        resolved = candidate.resolve()
        if resolved != self.media_directory and self.media_directory not in resolved.parents:
            raise RendererError("Media path is outside the approved project directory.")
        if resolved.suffix.lower() not in extensions:
            raise RendererError(f"Unsupported media type: {resolved.suffix or '(none)'}")
        if not resolved.is_file():
            raise RendererError("Timeline media file does not exist.")
        return resolved

    @staticmethod
    def _validate_scene_layout(scenes: Sequence[SceneClip], duration_ms: int) -> None:
        if not scenes:
            raise RendererError("Timeline must contain at least one scene clip.")
        expected_start = 0
        for scene in scenes:
            if scene.start_ms != expected_start:
                raise RendererError("Scene clips must be contiguous and non-overlapping.")
            expected_start = scene.end_ms
        if expected_start != duration_ms:
            raise RendererError("Scene clips must cover the full timeline duration.")

    def _validate_scene_source_ranges(
        self,
        scenes: Sequence[SceneClip],
        paths: Sequence[Path],
    ) -> None:
        metadata_by_path: dict[Path, tuple[float, float]] = {}
        for scene, path in zip(scenes, paths, strict=True):
            metadata = metadata_by_path.get(path)
            if metadata is None:
                probe = self.probe(path)
                duration_ms = _video_duration_ms(probe)
                tolerance_ms = _video_duration_tolerance_ms(probe)
                metadata = (duration_ms, tolerance_ms)
                metadata_by_path[path] = metadata
            duration_ms, tolerance_ms = metadata
            requested_end_ms = scene.source_start_ms + scene.end_ms - scene.start_ms
            if requested_end_ms > duration_ms + tolerance_ms:
                raise RendererError(
                    f"Scene clip {scene.id} source range ends at {requested_end_ms} ms, "
                    f"but media duration is {round(duration_ms)} ms."
                )

    def _validate_binaries(self) -> None:
        for name, executable in (
            ("FFmpeg", self.settings.ffmpeg_path),
            ("ffprobe", self.settings.ffprobe_path),
        ):
            if Path(executable).is_file() or shutil.which(executable):
                continue
            raise RendererError(f"{name} executable is unavailable.")

    def _run(
        self,
        command: list[str],
        operation: str,
        *,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.settings.timeout_seconds,
        )
        if completed.returncode != 0:
            message = (
                completed.stderr.strip().splitlines()[-1] if completed.stderr else "unknown error"
            )
            raise RendererError(f"{operation} failed: {message}")
        if not capture_output:
            completed.stdout = ""
        return completed


def _escape_drawtext(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace("'", "’")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace(";", r"\;")
    )


def _truncate_slot(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(1, limit - 1)].rstrip() + "…"


_TEXT_WIDTH_FACTOR = 0.72


def _estimated_text_width(text: str, font_size: int) -> int:
    """Conservatively estimate Inter/Arial width for deterministic safe fitting."""

    return math.ceil(len(text) * font_size * _TEXT_WIDTH_FACTOR)


def _layout_text_block(
    text: str,
    *,
    preferred: int,
    max_width: int,
    max_height: int,
    max_lines: int,
) -> _TextBlockLayout:
    """Fit and wrap a text block within fixed pixel bounds at any resolution."""

    compact = " ".join(text.split())
    if not compact:
        compact = " "
    width = max(1, max_width)
    height = max(1, max_height)
    line_limit = max(1, max_lines)
    preferred_size = max(4, preferred)

    for font_size in range(preferred_size, 3, -1):
        characters_per_line = max(
            1,
            math.floor(width / font_size / _TEXT_WIDTH_FACTOR),
        )
        lines = tuple(
            textwrap.wrap(
                compact,
                width=characters_per_line,
                break_long_words=True,
                break_on_hyphens=False,
            )
        )
        line_height = max(font_size, math.ceil(font_size * 1.18))
        if (
            len(lines) <= line_limit
            and line_height * len(lines) <= height
            and all(_estimated_text_width(line, font_size) <= width for line in lines)
        ):
            return _TextBlockLayout(lines, font_size, line_height)

    font_size = 4
    line_height = max(font_size, math.ceil(font_size * 1.18))
    available_lines = max(1, min(line_limit, height // line_height))
    characters_per_line = max(
        1,
        math.floor(width / font_size / _TEXT_WIDTH_FACTOR),
    )
    lines = tuple(
        _wrap_copy_lines(compact, characters_per_line, max_lines=available_lines)
    )
    return _TextBlockLayout(lines, font_size, line_height)


def _wrap_copy_lines(text: str, max_characters: int, *, max_lines: int) -> list[str]:
    return textwrap.wrap(
        " ".join(text.split()),
        width=max_characters,
        max_lines=max_lines,
        placeholder="…",
    )


def _animated_position(base: int, offset: int, progress: str) -> str:
    if offset == 0:
        return str(base)
    return f"{base}+{offset}*(1-({progress}))"


def _half_open_time_window(start_ms: int, end_ms: int) -> str:
    return (
        f"gte(t,{start_ms / 1_000:.3f})*"
        f"lt(t,{end_ms / 1_000:.3f})"
    )


def _copy_x_position(layout: CopyLayout, config: RenderConfig) -> str:
    base = round(config.width * layout.x)
    if layout.alignment == "center":
        return f"{base}-text_w/2"
    return str(base)


def _safe_text_x_expression(preferred: str, *, left: int, right: int) -> str:
    """Clamp drawtext to an authored horizontal safe area."""

    return f"max({left},min({right}-text_w,({preferred})))"


def _escape_filter_path(path: Path) -> str:
    return path.as_posix().replace(":", r"\:").replace("'", r"\'")


def _renderable_cursor_events(
    timeline: Timeline,
    config: RenderConfig,
) -> list[InteractionEvent]:
    recorded = sorted(
        (event for event in timeline.cursor_events if event.x is not None and event.y is not None),
        key=lambda event: event.timestamp_ms,
    )
    del config
    return recorded


def _map_viewport_point(
    x: float,
    y: float,
    viewport: Viewport,
    config: RenderConfig,
) -> tuple[float, float]:
    scale = min(config.width / viewport.width, config.height / viewport.height)
    offset_x = (config.width - viewport.width * scale) / 2
    offset_y = (config.height - viewport.height * scale) / 2
    return offset_x + x * scale, offset_y + y * scale


def _clamp_render_point(
    x: float,
    y: float,
    config: RenderConfig,
    margin: float,
) -> tuple[float, float]:
    return (
        max(margin, min(config.width - margin, x)),
        max(margin, min(config.height - margin, y)),
    )


def _frame_rate(value: str) -> float:
    numerator, separator, denominator = value.partition("/")
    if not separator:
        return float(value)
    divisor = float(denominator)
    return float(numerator) / divisor if divisor else 0


def _video_duration_ms(probe: dict[str, Any]) -> float:
    streams = cast(list[dict[str, Any]], probe.get("streams", []))
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    if video is None:
        raise RendererError("Scene media does not contain a video stream.")

    duration_ts = _positive_float(video.get("duration_ts"))
    time_base = _time_base_seconds(video.get("time_base"))
    if duration_ts is not None and time_base is not None:
        return duration_ts * time_base * 1_000

    tags = video.get("tags")
    if isinstance(tags, dict):
        tagged_duration = _clock_duration_seconds(tags.get("DURATION"))
        if tagged_duration is not None:
            return tagged_duration * 1_000

    stream_duration = _positive_float(video.get("duration"))
    if stream_duration is not None:
        return stream_duration * 1_000

    metadata = probe.get("format")
    if isinstance(metadata, dict):
        format_duration = _positive_float(metadata.get("duration"))
        if format_duration is not None:
            return format_duration * 1_000
    raise RendererError("ffprobe could not determine scene media duration.")


def _video_duration_tolerance_ms(probe: dict[str, Any]) -> float:
    streams = cast(list[dict[str, Any]], probe.get("streams", []))
    video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    if video is None:
        return 2.0
    try:
        fps = _frame_rate(str(video.get("avg_frame_rate", "0/1")))
    except ValueError:
        fps = 0
    return min(100.0, max(2.0, 1_000 / fps + 1.0)) if fps > 0 else 2.0


def _positive_float(value: object) -> float | None:
    try:
        number = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _time_base_seconds(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    numerator, separator, denominator = value.partition("/")
    if not separator:
        return _positive_float(value)
    top = _positive_float(numerator)
    bottom = _positive_float(denominator)
    if top is None or bottom is None:
        return None
    return top / bottom


def _clock_duration_seconds(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) != 3:
        return _positive_float(value)
    try:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
    except ValueError:
        return None
    duration = hours * 3_600 + minutes * 60 + seconds
    return duration if math.isfinite(duration) and duration > 0 else None


def _stream_duration(stream: dict[str, Any] | None, fallback: float) -> float:
    if stream is None:
        return fallback
    try:
        return float(stream.get("duration", fallback))
    except (TypeError, ValueError):
        return fallback


def _motion_expression(points: Sequence[tuple[float, float]]) -> str:
    if not points:
        raise RendererError("A cursor motion expression requires at least one point.")
    expression = f"{points[-1][1]:.3f}"
    pairs = zip(points, points[1:], strict=False)
    for (start, start_value), (end, end_value) in reversed(list(pairs)):
        travel_start = max(start, end - 0.35)
        duration = max(0.001, end - travel_start)
        delta = end_value - start_value
        movement = (
            f"if(lt(t,{travel_start:.3f}),{start_value:.3f},"
            f"{start_value:.3f}+({delta:.3f})*"
            f"max(0,min(1,(t-{travel_start:.3f})/{duration:.3f})))"
        )
        expression = f"if(lt(t,{end:.3f}),{movement},{expression})"
    return expression


def _easing_expression(progress: str, easing: str) -> str:
    if easing == "linear":
        return progress
    if easing == "ease_in":
        return f"({progress})*({progress})"
    if easing == "ease_out":
        return f"1-(1-({progress}))*(1-({progress}))"
    return f"({progress})*({progress})*(3-2*({progress}))"
