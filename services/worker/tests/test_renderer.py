from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
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
from demodirector_contracts.attention import (
    AnimatedCallout,
    AttentionPlan,
    NormalizedRect,
    TargetObservation,
)
from demodirector_contracts.editorial import (
    EditorialScene,
    EditorialTemplatePlan,
    RenderSafeCrop,
)
from demodirector_contracts.motion import MotionCue, MotionDirectionPlan, MotionTokenSet
from demodirector_contracts.style import (
    StyleDirectionDecision,
    StyleDirectionPlan,
    VariantSceneDefaults,
    VisualVariantId,
)
from demodirector_worker.presentation import (
    PRESENTATION_PACK_ID,
    build_presentation_schedule,
    resolve_presentation_pack,
)
from demodirector_worker.renderer import (
    FFmpegRenderer,
    FFmpegSettings,
    RendererError,
    _escape_drawtext,
    _estimated_text_width,
    _layout_text_block,
    _video_duration_ms,
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


def create_moving_presentation_media(media: Path, settings: FFmpegSettings) -> Path:
    media.mkdir(exist_ok=True)
    video = media / "presentation-source.mp4"
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
            "color=c=0xFF00FF:s=320x180:r=12:d=120",
            "-f",
            "lavfi",
            "-i",
            "color=c=white:s=32x32:r=12:d=120",
            "-filter_complex",
            "[0:v][1:v]overlay=x='mod(t*48,288)':y=24:eval=frame:shortest=1[v]",
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    return video


def _sample_center_pixel(video: Path, timestamp: float, ffmpeg: str) -> tuple[int, int, int]:
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-ss",
            f"{timestamp:.3f}",
            "-frames:v",
            "1",
            "-vf",
            "scale=1:1,format=rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    assert len(completed.stdout) >= 3
    return (completed.stdout[0], completed.stdout[1], completed.stdout[2])


def _sample_pixel(
    video: Path,
    timestamp: float,
    x: int,
    y: int,
    ffmpeg: str,
) -> tuple[int, int, int]:
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            f"crop=1:1:{x}:{y},format=rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    assert len(completed.stdout) >= 3
    return (completed.stdout[0], completed.stdout[1], completed.stdout[2])


def _frame_red_pixel_count(video: Path, timestamp: float, ffmpeg: str) -> int:
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-ss",
            f"{timestamp:.3f}",
            "-frames:v",
            "1",
            "-vf",
            "format=rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    pixels = zip(
        completed.stdout[0::3],
        completed.stdout[1::3],
        completed.stdout[2::3],
        strict=True,
    )
    return sum(red > 180 and green < 100 and blue < 100 for red, green, blue in pixels)


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


def presentation_timeline(video: Path) -> Timeline:
    return Timeline(
        project_id="project-presentation",
        duration_ms=120_000,
        demo_mode="presentation_demo",
        presentation_pack_id="presentation-story@1",
        scene_clips=[
            SceneClip(
                id="scene-presentation",
                scene_id="scene-presentation",
                start_ms=0,
                end_ms=120_000,
                source_uri=str(video),
            )
        ],
        cursor_events=[
            InteractionEvent(
                timestamp_ms=8_000,
                event_type="click",
                x=640,
                y=360,
                viewport=Viewport(width=640, height=360),
            )
        ],
        presentation=VideoPresentationConfig(template="spotlight", zoom_enabled=False),
        cta_text="See the complete workflow",
    )


def presentation_motion_plan() -> MotionDirectionPlan:
    editorial = EditorialTemplatePlan(
        id="presentation-editorial",
        project_id="project-presentation",
        job_id="job-presentation",
        run_id="run-presentation",
        motion_plan_id="motion-presentation",
        catalog_version="editorial-v1",
        design_version="motion-v1",
        duration_ms=120_000,
        scene_ids=["scene-presentation"],
        product_clip_refs=["scene:scene-presentation"],
        summary="Show a verified workflow.",
        scenes=[
            EditorialScene(
                id="editorial-presentation",
                scene_id="scene-presentation",
                section="product_walkthrough",
                template_id="framed_product",
                product_clip_ref="scene:scene-presentation",
                product_treatment="framed_product",
                start_ms=0,
                end_ms=120_000,
                eyebrow="Verified workflow",
                title="Show the working product",
                body=(
                    "Keep verified evidence visible while each project-specific point is "
                    "explained."
                ),
                crop=RenderSafeCrop(x=0, y=0, width=1, height=1),
            )
        ],
        created_at=datetime.now(UTC),
    )
    return MotionDirectionPlan(
        id="motion-presentation",
        project_id="project-presentation",
        job_id="job-presentation",
        run_id="run-presentation",
        request_fingerprint="a" * 64,
        design_tokens=MotionTokenSet(),
        duration_ms=120_000,
        scene_ids=["scene-presentation"],
        product_clip_refs=["scene:scene-presentation"],
        summary="Show a verified workflow.",
        cues=[
            MotionCue(
                id="cue-presentation",
                scene_id="scene-presentation",
                primitive="fade_slide",
                layer="transition",
                start_ms=0,
                end_ms=1_000,
                easing="standard",
                product_clip_ref="scene:scene-presentation",
            )
        ],
        editorial_plan=editorial,
        created_at=datetime.now(UTC),
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


def test_split_clips_continue_from_the_saved_source_offset(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
) -> None:
    media = tmp_path / "media"
    media.mkdir()
    source = media / "two-colors.mp4"
    subprocess.run(
        [
            ffmpeg_settings.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:d=1:r=12",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=1:r=12",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    timeline = Timeline(
        project_id="project-split",
        duration_ms=2_000,
        scene_clips=[
            SceneClip(
                id="split-first",
                scene_id="first",
                start_ms=0,
                end_ms=1_000,
                source_uri=str(source),
                source_start_ms=0,
            ),
            SceneClip(
                id="split-second",
                scene_id="second",
                start_ms=1_000,
                end_ms=2_000,
                source_uri=str(source),
                source_start_ms=1_000,
            ),
        ],
    )
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)

    graph = ";".join(
        renderer._video_filters(  # noqa: SLF001 - source continuity is under test
            timeline,
            timeline.scene_clips,
            RenderConfig(width=320, height=180, fps=12),
        )
    )
    assert "[0:v]trim=start=0.000:duration=1.000" in graph
    assert "[1:v]trim=start=1.000:duration=1.000" in graph

    result = renderer.render(
        timeline,
        RenderConfig(width=320, height=180, fps=12, output_filename="split.mp4"),
    )
    assert result.status == "succeeded"
    assert result.output_path is not None
    first_pixel = _sample_center_pixel(
        Path(result.output_path), 0.5, ffmpeg_settings.ffmpeg_path
    )
    second_pixel = _sample_center_pixel(
        Path(result.output_path), 1.5, ffmpeg_settings.ffmpeg_path
    )
    assert first_pixel[0] > 180 and first_pixel[2] < 80
    assert second_pixel[2] > 180 and second_pixel[0] < 80


def test_renderer_preflights_each_unique_scene_source_and_rejects_overrun(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "media"
    video, _ = create_media(media, ffmpeg_settings)
    timeline = Timeline(
        project_id="project-overrun",
        duration_ms=2_000,
        scene_clips=[
            SceneClip(
                id="first",
                scene_id="first",
                start_ms=0,
                end_ms=1_000,
                source_uri=str(video),
            ),
            SceneClip(
                id="second",
                scene_id="second",
                start_ms=1_000,
                end_ms=2_000,
                source_uri=str(video),
                source_start_ms=1_500,
            ),
        ],
    )
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)
    probed: list[Path] = []
    real_probe = renderer.probe

    def counting_probe(path: Path) -> dict[str, object]:
        probed.append(path)
        return real_probe(path)

    monkeypatch.setattr(renderer, "probe", counting_probe)

    with pytest.raises(
        RendererError,
        match=r"second.*source range ends at 2500 ms.*media duration is 2000 ms",
    ):
        renderer.render(
            timeline,
            RenderConfig(width=320, height=180, fps=12, output_filename="overrun.mp4"),
        )

    assert probed == [video.resolve()]
    assert not (tmp_path / "renders" / "overrun.mp4").exists()


@pytest.mark.parametrize(
    ("stream_metadata", "expected_ms"),
    [
        (
            {
                "codec_type": "video",
                "duration_ts": 3_600,
                "time_base": "1/30",
            },
            120_000,
        ),
        (
            {
                "codec_type": "video",
                "duration": "N/A",
                "duration_ts": "N/A",
                "time_base": "1/1000",
                "tags": {"DURATION": "00:02:00.000000000"},
            },
            120_000,
        ),
    ],
)
def test_video_duration_preflight_supports_stream_ticks_and_webm_tags(
    stream_metadata: dict[str, object],
    expected_ms: int,
) -> None:
    assert _video_duration_ms({"streams": [stream_metadata]}) == expected_ms


@pytest.mark.parametrize(
    "variant",
    ["editorial_story", "product_spotlight", "technical_proof"],
)
def test_renderer_consumes_validated_motion_and_style_plans(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
    variant: VisualVariantId,
) -> None:
    media = tmp_path / "media"
    video, audio = create_media(media, ffmpeg_settings)
    fixture = render_timeline(video, audio).model_copy(
        update={
            "motion_plan_id": "motion-plan-1",
            "motion_design_version": "motion-v1",
            "attention_plan_id": "attention-plan-1",
            "attention_design_version": "attention-v1",
            "style_plan_id": "style-plan-1",
            "style_design_version": "style-v1",
            "visual_variant": variant,
        }
    )
    editorial = EditorialTemplatePlan(
        id="editorial-plan-1",
        project_id=fixture.project_id,
        job_id="job-1",
        run_id="run-1",
        motion_plan_id="motion-plan-1",
        catalog_version="editorial-v1",
        design_version="motion-v1",
        duration_ms=fixture.duration_ms,
        scene_ids=["scene-1"],
        product_clip_refs=["scene:scene-1"],
        summary="Keep authentic footage visible.",
        scenes=[
            EditorialScene(
                id="editorial-scene-1",
                scene_id="scene-1",
                section="hook",
                template_id="hook",
                product_clip_ref="scene:scene-1",
                product_treatment="moving_background",
                start_ms=0,
                end_ms=fixture.duration_ms,
                title="Working product",
                crop=RenderSafeCrop(x=0, y=0, width=1, height=1),
            )
        ],
        created_at=datetime.now(UTC),
    )
    plan = MotionDirectionPlan(
        id="motion-plan-1",
        project_id=fixture.project_id,
        job_id="job-1",
        run_id="run-1",
        request_fingerprint="a" * 64,
        design_tokens=MotionTokenSet(),
        duration_ms=fixture.duration_ms,
        scene_ids=["scene-1"],
        product_clip_refs=["scene:scene-1"],
        summary="Show the product clearly.",
        cues=[
            MotionCue(
                id="cue-1",
                scene_id="scene-1",
                primitive="background_dim",
                layer="background",
                start_ms=200,
                end_ms=700,
                easing="standard",
                product_clip_ref="scene:scene-1",
            ),
            MotionCue(
                id="cue-2",
                scene_id="scene-1",
                primitive="stagger_text",
                layer="callout",
                start_ms=800,
                end_ms=1_500,
                easing="emphasized",
                text="Working product",
                product_clip_ref="scene:scene-1",
            ),
        ],
        editorial_plan=editorial,
        created_at=datetime.now(UTC),
    )
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)
    attention = AttentionPlan(
        id="attention-plan-1",
        project_id=fixture.project_id,
        job_id="job-1",
        parent_run_id=plan.run_id,
        duration_ms=fixture.duration_ms,
        targets=[
            TargetObservation(
                id="target-1",
                scene_id="scene-1",
                locator_fingerprint="a" * 64,
                timestamp_ms=1_000,
                rect=NormalizedRect(x=0.2, y=0.3, width=0.1, height=0.1),
                viewport=Viewport(width=640, height=360),
            )
        ],
        narration_statement_ids=[],
        summary="Guide attention.",
        callouts=[
            AnimatedCallout(
                id="callout-1",
                target_id="target-1",
                callout_type="label_connector",
                placement="top_left",
                start_ms=800,
                end_ms=1_500,
                text="Create project",
            )
        ],
        caption_emphasis=[],
        created_at=datetime.now(UTC),
    )
    style = StyleDirectionPlan(
        id="style-plan-1",
        project_id=fixture.project_id,
        job_id="job-1",
        parent_run_id=plan.run_id,
        audience="Product leaders",
        purpose="Show the working product",
        scene_ids=["scene-1"],
        allowed_evidence_refs=["storyboard:1"],
        recommendation_evidence_refs=["storyboard:1"],
        rationale="Show validated product evidence.",
        decision=StyleDirectionDecision(
            recommended_variant=variant,
            selected_variant=variant,
            outcome="recommended",
            decided_at=datetime.now(UTC),
        ),
        defaults=[
            VariantSceneDefaults(
                variant_id="editorial_story",
                product_scale="composed",
                callout_density="medium",
                motion_pace="deliberate",
            ),
            VariantSceneDefaults(
                variant_id="product_spotlight",
                product_scale="large",
                callout_density="low",
                motion_pace="calm",
            ),
            VariantSceneDefaults(
                variant_id="technical_proof",
                product_scale="evidence_focused",
                callout_density="medium",
                motion_pace="precise",
            ),
        ],
        created_at=datetime.now(UTC),
    )

    result = renderer.render(
        fixture,
        RenderConfig(width=640, height=360, fps=24, output_filename=f"{variant}.mp4"),
        plan,
        attention,
        style,
    )

    assert result.status == "succeeded"
    assert result.motion_composition_hash is not None
    assert len(result.motion_composition_hash) == 64
    graph = ";".join(
        renderer._video_filters(  # noqa: SLF001 - mode branching is under test
            fixture,
            fixture.scene_clips,
            RenderConfig(width=640, height=360, fps=24),
            plan,
            attention,
            style,
        )
    )
    assert "veditorial" not in graph
    assert "vattention" not in graph
    assert "vstyle" not in graph


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
    assert _escape_drawtext("It's 10:00, edit; share") == (r"It’s 10\:00\, edit\; share")


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


def test_product_demo_can_bypass_zoom_without_losing_real_click_feedback(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
) -> None:
    media = tmp_path / "media"
    video, audio = create_media(media, ffmpeg_settings)
    timeline = render_timeline(video, audio).model_copy(
        update={
            "presentation": VideoPresentationConfig(
                template="edge_to_edge",
                zoom_enabled=False,
            )
        }
    )
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)

    graph = ";".join(
        renderer._video_filters(  # noqa: SLF001 - graph order is the behavior under test
            timeline,
            timeline.scene_clips,
            RenderConfig(width=1920, height=1080, fps=30),
        )
    )

    assert "zoompan=" not in graph
    assert "vclick" in graph
    assert "0xFF5A5F" in graph
    assert "presentationcanvas" not in graph
    assert timeline.zoom_clips


def test_presentation_demo_uses_one_fixed_pack_without_the_recording_frame_overlay(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
) -> None:
    media = tmp_path / "media"
    video, _ = create_media(media, ffmpeg_settings)
    timeline = presentation_timeline(video)
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)

    graph = ";".join(
        renderer._video_filters(  # noqa: SLF001 - graph composition is under test
            timeline,
            timeline.scene_clips,
            RenderConfig(width=1920, height=1080, fps=30),
            presentation_motion_plan(),
        )
    )

    assert "presentationcanvas" in graph
    assert "pt_product_split" in graph
    assert "pt_guided_workflow" in graph
    assert "pt_brand_outro" in graph
    assert "gradients=" not in graph
    assert "presentationcrop" not in graph
    assert "gte(t,5.000)*lt(t,115.000)" in graph
    for entry in build_presentation_schedule(120_000):
        half_open = (
            f"gte(t,{entry.start_ms / 1_000:.3f})*"
            f"lt(t,{entry.end_ms / 1_000:.3f})"
        )
        inclusive = (
            f"between(t,{entry.start_ms / 1_000:.3f},"
            f"{entry.end_ms / 1_000:.3f})"
        )
        assert half_open in graph
        assert inclusive not in graph
    assert "force_original_aspect_ratio=increase" in graph
    assert "force_original_aspect_ratio=decrease" in graph
    assert "gblur=sigma=18" in graph
    assert "overlay=x=(1018-w)/2:y=(756-h)/2" in graph
    assert "pad=1018:756" not in graph
    assert "pt_product_split_split_reveal_copy" in graph
    assert "pt_guided_workflow_prompt_sequence_copy" in graph
    assert "pt_template_populate_focus_reveal_copy" in graph
    assert "pt_review_gate_review_reveal_copy" in graph
    assert "pt_constraints_three_up_stagger_cards_copy" in graph
    assert "color=c=0x173D34" in graph
    assert "color=0x98E3CD@1.0" in graph
    assert "Keep verified evidence visible" in graph


@pytest.mark.parametrize(("width", "height"), [(320, 180), (1920, 1080)])
def test_presentation_title_blocks_fit_every_authored_copy_slot(
    width: int,
    height: int,
) -> None:
    pack = resolve_presentation_pack(PRESENTATION_PACK_ID)
    safe_x = round(width * 0.05)
    project_specific_title = (
        "Show a validated customer workflow with project-specific evidence and outcomes"
    )

    for template in pack.templates:
        title = project_specific_title[: template.max_title_chars]
        if template.requires_product:
            panel_width = max(2, round(width * template.copy_layout.panel_width))
            panel_height = max(2, round(height * template.copy_layout.panel_height))
            max_width = max(2, panel_width - 24)
            max_height = max(5, panel_height - 12)
            preferred = max(7, round(height * 0.038))
        else:
            max_width = width - safe_x * 2
            max_height = round(height * 0.56)
            preferred = max(8, round(height * 0.068))

        layout = _layout_text_block(
            title,
            preferred=preferred,
            max_width=max_width,
            max_height=max_height,
            max_lines=3,
        )

        assert layout.height <= max_height, template.id
        assert all(
            _estimated_text_width(line, layout.font_size) <= max_width
            for line in layout.lines
        ), template.id


def test_low_resolution_presentation_graph_clamps_every_copy_line_to_safe_area(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
) -> None:
    media = tmp_path / "media"
    video, _ = create_media(media, ffmpeg_settings)
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)

    graph = ";".join(
        renderer._video_filters(  # noqa: SLF001 - graph safety is under test
            presentation_timeline(video),
            presentation_timeline(video).scene_clips,
            RenderConfig(width=320, height=180, fps=12),
            presentation_motion_plan(),
        )
    )

    horizontal_safe_expression = "x='max(16,min(304-text_w,("
    assert graph.count(horizontal_safe_expression) >= 13
    assert "fontsize=10:x='12'" not in graph


def test_fixed_presentation_pack_renders_a_complete_two_minute_mp4(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
) -> None:
    media = tmp_path / "media"
    video = create_moving_presentation_media(media, ffmpeg_settings)
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)

    result = renderer.render(
        presentation_timeline(video),
        RenderConfig(
            width=320,
            height=180,
            fps=12,
            output_filename="presentation-demo.mp4",
        ),
        presentation_motion_plan(),
    )

    assert result.status == "succeeded"
    assert result.duration_ms == pytest.approx(120_000, abs=150)
    assert result.width == 320
    assert result.height == 180
    assert result.output_path is not None and Path(result.output_path).is_file()
    output = Path(result.output_path)

    # The authored aperture contains the full 16:9 foreground. The blurred copy fills
    # the remaining aperture instead of black bars, and the real source keeps moving.
    letterbox_fill = _sample_pixel(output, 9.000, 210, 24, ffmpeg_settings.ffmpeg_path)
    moving_square_at_nine = _sample_pixel(
        output, 9.000, 214, 52, ffmpeg_settings.ffmpeg_path
    )
    same_point_at_ten = _sample_pixel(
        output, 10.000, 214, 52, ffmpeg_settings.ffmpeg_path
    )
    assert max(letterbox_fill) > 40
    assert min(moving_square_at_nine) > 190
    assert min(same_point_at_ten) < 160

    # The captured click is at the source viewport's bottom-right edge. It must remain
    # visible after containment inside the authored product aperture.
    assert _frame_red_pixel_count(output, 8.200, ffmpeg_settings.ffmpeg_path) > 8


def test_renderer_does_not_invent_a_click_from_an_auto_zoom(
    tmp_path: Path,
    ffmpeg_settings: FFmpegSettings,
) -> None:
    media = tmp_path / "media"
    video, audio = create_media(media, ffmpeg_settings)
    timeline = render_timeline(video, audio).model_copy(update={"cursor_events": []})
    renderer = FFmpegRenderer(media, tmp_path / "renders", ffmpeg_settings)

    graph = ";".join(
        renderer._video_filters(  # noqa: SLF001 - graph composition is under test
            timeline,
            timeline.scene_clips,
            RenderConfig(width=1920, height=1080, fps=30),
        )
    )

    assert "vclick" not in graph
    assert "text='â—'" not in graph
    assert "zoompan=" in graph
