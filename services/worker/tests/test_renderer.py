from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from demodirector_contracts import (
    AudioClip,
    BoundingBox,
    CaptionClip,
    InteractionEvent,
    RenderConfig,
    SceneClip,
    Timeline,
    VideoPresentationConfig,
    Viewport,
    ZoomClip,
)
from demodirector_worker.renderer import (
    FFmpegRenderer,
    FFmpegSettings,
    RendererError,
    _escape_drawtext,
)
from pydantic import ValidationError


def media_binary(name: str) -> str:
    discovered = shutil.which(name)
    if discovered:
        return discovered
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        matches = sorted(root.glob(f"Gyan.FFmpeg*/*/bin/{name}.exe"))
        if matches:
            return str(matches[0])
    pytest.skip(f"{name} is required for the renderer integration test")


@pytest.fixture
def ffmpeg_settings() -> FFmpegSettings:
    return FFmpegSettings(
        ffmpeg_path=media_binary("ffmpeg"),
        ffprobe_path=media_binary("ffprobe"),
        font_path="C:/Windows/Fonts/arial.ttf",
        timeout_seconds=30,
    )


def create_media(media: Path, settings: FFmpegSettings) -> tuple[Path, Path]:
    media.mkdir()
    video = media / "scene.mp4"
    audio = media / "narration.wav"
    subprocess.run(
        [
            settings.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x172033:s=640x360:d=2:r=24",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    subprocess.run(
        [
            settings.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            str(audio),
        ],
        check=True,
    )
    return video, audio


def render_timeline(video: Path, audio: Path) -> Timeline:
    return Timeline(
        project_id="project-render",
        duration_ms=2_000,
        scene_clips=[
            SceneClip(
                id="scene-clip-1",
                scene_id="scene-1",
                start_ms=0,
                end_ms=2_000,
                source_uri=str(video),
            )
        ],
        caption_clips=[
            CaptionClip(
                id="caption-1",
                scene_id="scene-1",
                start_ms=200,
                end_ms=1_700,
                text="Create, edit; and share the demo",
            )
        ],
        zoom_clips=[
            ZoomClip(
                id="zoom-1",
                start_ms=500,
                end_ms=1_400,
                scale=1.35,
                target_rect=BoundingBox(x=200, y=100, width=160, height=80),
                focus_x=280,
                focus_y=140,
                source_viewport=Viewport(width=640, height=360),
                easing="ease_in_out",
                source="auto",
            ),
            ZoomClip(
                id="zoom-2",
                start_ms=1_500,
                end_ms=1_900,
                scale=1.2,
                target_rect=BoundingBox(x=40, y=50, width=80, height=80),
                focus_x=80,
                focus_y=90,
                source_viewport=Viewport(width=640, height=360),
                easing="ease_in_out",
                source="auto",
            ),
        ],
        cursor_events=[
            InteractionEvent(
                timestamp_ms=200,
                event_type="click",
                x=80,
                y=90,
                viewport=Viewport(width=640, height=360),
            ),
            InteractionEvent(
                timestamp_ms=1_000,
                event_type="click",
                x=280,
                y=140,
                viewport=Viewport(width=640, height=360),
            ),
        ],
        audio_clips=[
            AudioClip(
                id="audio-1",
                scene_id="scene-1",
                start_ms=0,
                end_ms=2_000,
                source_uri=str(audio),
            )
        ],
        presentation=VideoPresentationConfig(template="spotlight"),
    )


def test_ffmpeg_renderer_outputs_probed_mp4_audio_and_thumbnail(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
) -> None:
    media = tmp_path / "media"
    video, audio = create_media(media, ffmpeg_settings)
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)

    result = renderer.render(
        render_timeline(video, audio),
        RenderConfig(width=640, height=360, fps=24),
    )

    assert result.status == "succeeded"
    assert result.has_video is True
    assert result.has_audio is True
    assert result.width == 640
    assert result.height == 360
    assert result.duration_ms == pytest.approx(2_000, abs=150)
    assert result.output_path is not None and Path(result.output_path).is_file()
    assert result.thumbnail_path is not None and Path(result.thumbnail_path).is_file()
    assert result.model_validate_json(result.model_dump_json()) == result


def test_renderer_rejects_paths_outside_project_media(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
) -> None:
    media = tmp_path / "media"
    video, audio = create_media(media, ffmpeg_settings)
    outside = tmp_path / "outside.mp4"
    video.replace(outside)
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)

    with pytest.raises(RendererError, match="outside"):
        renderer.render(render_timeline(outside, audio), RenderConfig(width=640, height=360))


def test_renderer_rejects_unsupported_media_type(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
) -> None:
    media = tmp_path / "media"
    video, audio = create_media(media, ffmpeg_settings)
    unsupported = media / "scene.exe"
    unsupported.write_bytes(video.read_bytes())
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)

    with pytest.raises(RendererError, match="Unsupported media type"):
        renderer.render(render_timeline(unsupported, audio), RenderConfig(width=640, height=360))


def test_render_config_rejects_unsupported_fields_and_unsafe_filename() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        RenderConfig.model_validate({"operation": "shell", "output_filename": "preview.mp4"})
    with pytest.raises(ValidationError, match="String should match pattern"):
        RenderConfig(output_filename="../preview.mp4")


def test_drawtext_escaping_is_deterministic() -> None:
    assert _escape_drawtext("It's 10:00, edit; share") == (
        r"It’s 10\:00\, edit\; share"
    )


def test_video_filters_draw_a_moving_cursor_before_coordinate_aware_zoom(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
) -> None:
    media = tmp_path / "media"
    video, audio = create_media(media, ffmpeg_settings)
    timeline = render_timeline(video, audio)
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)

    graph = ";".join(
        renderer._video_filters(  # noqa: SLF001 - filter graph is the behavior under test
            timeline,
            timeline.scene_clips,
            RenderConfig(width=1920, height=1080, fps=30),
        )
    )

    assert "drawtext=" in graph
    assert "text='●'" in graph
    assert graph.index("drawtext=") < graph.index("zoompan=")
    assert "840.000-iw/(2*zoom)" in graph
    assert "(on-15.000)" in graph
    assert "3-2*" in graph
    assert "1.350" in graph
    assert "1.200" in graph
    assert "between(on,45.000,57.000)" in graph
    assert "gradients=" in graph
    assert "force_original_aspect_ratio=increase" in graph
    assert "crop=1708:960,format=rgba[presentationcrop]" in graph
    assert "geq=lum='if(" in graph
    assert "gblur=sigma=0.7[presentationmask]" in graph
    assert "alphamerge[presentationframe]" in graph
    assert "drawbox=" not in graph
    assert "pad=1708:960" not in graph
    assert "if(between(on,15.000,42.000),1.350" not in graph
