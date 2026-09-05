import subprocess
from pathlib import Path

import pytest
from demodirector_contracts import (
    AudioClip,
    CaptionClip,
    RenderConfig,
    SceneClip,
    Timeline,
)
from demodirector_worker.longform import LongFormCompiler
from demodirector_worker.renderer import FFmpegRenderer, RendererError

from test_support.longform import longform_plan


class ProbeOnlyRenderer(FFmpegRenderer):
    def __init__(self, root: Path, diagnostics: str = "") -> None:
        super().__init__(root, root)
        self.diagnostics = diagnostics

    def _run(
        self,
        command: list[str],
        operation: str,
        *,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        del operation, capture_output
        return subprocess.CompletedProcess(command, 0, "", self.diagnostics)


def timeline() -> Timeline:
    return Timeline(
        project_id="project-1",
        duration_ms=180_000,
        long_form_plan_id="longform-plan-1",
        long_form_version="longform-v1",
        scene_clips=[SceneClip(
            id="scene-1", scene_id="product", start_ms=0, end_ms=180_000,
            source_uri="product.mp4",
        )],
        caption_clips=[CaptionClip(
            id="caption-1", scene_id="hook", start_ms=0, end_ms=1_000, text="See it work",
        )],
        audio_clips=[AudioClip(
            id="audio-1", scene_id="hook", start_ms=0, end_ms=4_000,
            source_uri="narration.wav",
        )],
    )


def test_longform_compiler_is_causal_and_deterministic() -> None:
    plan = longform_plan()
    compiled = LongFormCompiler().compile(plan)
    changed = plan.model_copy(update={
        "beats": [
            plan.beats[0].model_copy(update={"template_id": "hook"}),
            *plan.beats[1:],
        ]
    })
    assert compiled.deterministic_hash == LongFormCompiler().compile(plan).deterministic_hash
    assert compiled.deterministic_hash != LongFormCompiler().compile(changed).deterministic_hash


def test_longform_media_validation_requires_exact_qhd_timeline() -> None:
    report = LongFormCompiler().validate_timeline(
        longform_plan(), timeline(), RenderConfig(width=2560, height=1440, fps=30)
    )
    assert report.passed and report.product_presence_percent == 100


def test_longform_output_probe_requires_exact_playable_synchronized_media(
    tmp_path: Path,
) -> None:
    renderer = ProbeOnlyRenderer(tmp_path)
    probe = {
        "format": {"duration": "180.000"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 2560,
                "height": 1440,
                "avg_frame_rate": "30/1",
                "duration": "180.000",
            },
            {"codec_type": "audio", "codec_name": "aac", "duration": "180.000"},
        ],
    }
    renderer._validate_longform_output(tmp_path / "video.mp4", probe)

    with pytest.raises(RendererError, match="duration is not exactly"):
        renderer._validate_longform_output(
            tmp_path / "video.mp4",
            {**probe, "format": {"duration": "179.000"}},
        )
    with pytest.raises(RendererError, match="black interval"):
        ProbeOnlyRenderer(tmp_path, "black_duration:2.500")._validate_longform_output(
            tmp_path / "video.mp4",
            probe,
        )
