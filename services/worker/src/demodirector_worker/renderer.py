from __future__ import annotations

import json
import shutil
import subprocess
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

VIDEO_EXTENSIONS = {".mkv", ".mov", ".mp4", ".webm"}
AUDIO_EXTENSIONS = {".aac", ".m4a", ".mp3", ".ogg", ".wav"}


class RendererError(RuntimeError):
    """Raised when a typed timeline cannot be rendered safely."""


@dataclass(frozen=True, slots=True)
class FFmpegSettings:
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    font_path: str | None = None
    timeout_seconds: int = 120


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

    def render(self, timeline: Timeline, config: RenderConfig) -> RenderResult:
        self._validate_binaries()
        scenes = sorted(timeline.scene_clips, key=lambda clip: clip.start_ms)
        self._validate_scene_layout(scenes, timeline.duration_ms)
        scene_paths = [self._safe_media_path(clip.source_uri, VIDEO_EXTENSIONS) for clip in scenes]
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
        return RenderResult(
            status="succeeded",
            output_path=str(output_path),
            thumbnail_path=str(thumbnail_path),
            duration_ms=duration_ms,
            width=int(video_stream["width"]),
            height=int(video_stream["height"]),
            has_video=True,
            has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
        )

    def probe(self, path: Path) -> dict[str, Any]:
        completed = self._run(
            [
                self.settings.ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,width,height:format=duration",
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

    def _render_command(
        self,
        timeline: Timeline,
        config: RenderConfig,
        scenes: Sequence[SceneClip],
        scene_paths: Sequence[Path],
        audio_paths: Sequence[Path],
        output_path: Path,
    ) -> list[str]:
        command = [self.settings.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y"]
        for path in scene_paths:
            command.extend(["-i", str(path)])
        for path in audio_paths:
            command.extend(["-i", str(path)])
        filters = self._video_filters(timeline, scenes, config)
        audio_label = self._audio_filters(
            timeline.audio_clips,
            len(scene_paths),
            timeline.duration_ms,
            filters,
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
    ) -> list[str]:
        filters: list[str] = []
        labels: list[str] = []
        for index, scene in enumerate(scenes):
            duration = (scene.end_ms - scene.start_ms) / 1_000
            label = f"scene{index}"
            filters.append(
                f"[{index}:v]trim=duration={duration:.3f},setpts=PTS-STARTPTS,"
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
        if timeline.zoom_clips:
            filters.append(self._zoom_filter(timeline.zoom_clips, config, current, "vzoom"))
            current = "vzoom"
        captions = sorted(timeline.caption_clips, key=lambda clip: clip.start_ms)
        for index, caption in enumerate(captions):
            next_label = f"vcaption{index}"
            filters.append(self._caption_filter(caption, current, next_label))
            current = next_label
        if timeline.presentation.template != "edge_to_edge":
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
        points = [
            (
                event.timestamp_ms / 1_000,
                *_map_viewport_point(
                    cast(float, event.x),
                    cast(float, event.y),
                    event.viewport,
                    config,
                ),
            )
            for event in events
        ]
        x_expression = _motion_expression([(time, x) for time, x, _ in points])
        y_expression = _motion_expression([(time, y) for time, _, y in points])
        font = _escape_filter_path(self._font_path())
        return (
            f"[{input_label}]drawtext=fontfile='{font}':text='●':expansion=none:"
            "fontcolor=white:borderw=2:bordercolor=black@0.92:fontsize=28:"
            f"x='{x_expression}-14':y='{y_expression}-14'[{output_label}]"
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
            zoom_in_progress = (
                f"max(0,min(1,(on-{start_frame:.3f})/{transition_frames:.3f}))"
            )
            zoom_out_progress = (
                f"max(0,min(1,(on-{zoom_out_start:.3f})/{transition_frames:.3f}))"
            )
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
                f"if({active},max(0,min(iw-iw/zoom,{center_x:.3f}-iw/(2*zoom))),"
                f"{x_expression})"
            )
            y_expression = (
                f"if({active},max(0,min(ih-ih/zoom,{center_y:.3f}-ih/(2*zoom))),"
                f"{y_expression})"
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
        if len(labels) == 1:
            filters.append(f"{labels[0]}apad=whole_dur={duration:.3f},atrim=duration={duration:.3f}[aout]")
        else:
            filters.append(
                f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,"
                f"apad=whole_dur={duration:.3f},atrim=duration={duration:.3f}[aout]"
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
                completed.stderr.strip().splitlines()[-1]
                if completed.stderr
                else "unknown error"
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
    if recorded:
        return recorded
    synthetic: list[InteractionEvent] = []
    for zoom in sorted(timeline.zoom_clips, key=lambda clip: clip.start_ms):
        if zoom.source != "auto":
            continue
        viewport = zoom.source_viewport or Viewport(width=1280, height=720)
        synthetic.append(
            InteractionEvent(
                timestamp_ms=(zoom.start_ms + zoom.end_ms) // 2,
                event_type="click",
                x=(
                    zoom.focus_x
                    if zoom.focus_x is not None
                    else zoom.target_rect.x + zoom.target_rect.width / 2
                ),
                y=(
                    zoom.focus_y
                    if zoom.focus_y is not None
                    else zoom.target_rect.y + zoom.target_rect.height / 2
                ),
                viewport=viewport,
            )
        )
    del config
    return synthetic


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
