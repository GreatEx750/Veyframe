from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from demodirector_contracts import (
    AudioClip,
    BoundingBox,
    CaptionClip,
    RenderConfig,
    SceneClip,
    Timeline,
    VideoPresentationConfig,
    ZoomClip,
)
from demodirector_worker import FFmpegRenderer, FFmpegSettings


def media_binary(name: str) -> str:
    discovered = shutil.which(name)
    if discovered:
        return discovered
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        package_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        matches = sorted(package_root.glob(f"Gyan.FFmpeg*/*/bin/{name}.exe"))
        if matches:
            return str(matches[0])
    raise RuntimeError(f"{name} is required for the 20-second render smoke test")


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def create_scene(ffmpeg: str, output: Path, color: str, frequency: int) -> tuple[Path, Path]:
    video = output.with_suffix(".mp4")
    audio = output.with_suffix(".wav")
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=1280x720:d=10:r=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ]
    )
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration=10",
            str(audio),
        ]
    )
    return video, audio


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a 20-second DemoDirector smoke video")
    parser.add_argument(
        "--presentation",
        choices=("edge_to_edge", "soft_frame", "spotlight"),
        default="edge_to_edge",
    )
    args = parser.parse_args()
    presentation: Literal["edge_to_edge", "soft_frame", "spotlight"] = args.presentation
    root = Path(__file__).resolve().parents[1]
    smoke_root = root / "artifacts" / "smoke-20s"
    media = smoke_root / "media"
    renders = smoke_root / "renders"
    media.mkdir(parents=True, exist_ok=True)
    renders.mkdir(parents=True, exist_ok=True)

    ffmpeg = media_binary("ffmpeg")
    ffprobe = media_binary("ffprobe")
    scene_one, audio_one = create_scene(ffmpeg, media / "scene-one", "0x172033", 440)
    scene_two, audio_two = create_scene(ffmpeg, media / "scene-two", "0x263A5B", 554)
    timeline = Timeline(
        project_id="smoke-20s",
        duration_ms=20_000,
        scene_clips=[
            SceneClip(
                id="scene-clip-one",
                scene_id="scene-one",
                start_ms=0,
                end_ms=10_000,
                source_uri=str(scene_one),
            ),
            SceneClip(
                id="scene-clip-two",
                scene_id="scene-two",
                start_ms=10_000,
                end_ms=20_000,
                source_uri=str(scene_two),
            ),
        ],
        caption_clips=[
            CaptionClip(
                id="caption-one",
                scene_id="scene-one",
                start_ms=1_000,
                end_ms=8_500,
                text="DemoDirector 20-second render test",
            ),
            CaptionClip(
                id="caption-two",
                scene_id="scene-two",
                start_ms=11_000,
                end_ms=18_500,
                text="Scenes, captions, audio, zoom, and thumbnail verified",
            ),
        ],
        zoom_clips=[
            ZoomClip(
                id="zoom-two",
                start_ms=12_000,
                end_ms=16_000,
                scale=1.25,
                target_rect=BoundingBox(x=430, y=220, width=420, height=250),
                easing="ease_in_out",
                source="manual",
            )
        ],
        audio_clips=[
            AudioClip(
                id="audio-one",
                scene_id="scene-one",
                start_ms=0,
                end_ms=10_000,
                source_uri=str(audio_one),
            ),
            AudioClip(
                id="audio-two",
                scene_id="scene-two",
                start_ms=10_000,
                end_ms=20_000,
                source_uri=str(audio_two),
            ),
        ],
        presentation=VideoPresentationConfig(template=presentation),
    )
    renderer = FFmpegRenderer(
        media,
        renders,
        FFmpegSettings(
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
            timeout_seconds=180,
        ),
    )
    result = renderer.render(
        timeline,
        RenderConfig(
            width=1280,
            height=720,
            fps=30,
            output_filename=f"demodirector-smoke-20s-{presentation}.mp4",
        ),
    )
    if result.duration_ms < 19_850 or result.duration_ms > 20_150:
        raise RuntimeError(f"Unexpected rendered duration: {result.duration_ms} ms")
    if not result.has_video or not result.has_audio:
        raise RuntimeError("Rendered smoke video must contain video and audio streams")
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()
