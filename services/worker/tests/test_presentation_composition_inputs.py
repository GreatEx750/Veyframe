import json
from pathlib import Path
from unittest.mock import patch

from demodirector_contracts import BoundingBox, Viewport, ZoomClip
from demodirector_worker.presentation_assets import AuthoredSlideRenderer


def test_unobstructed_product_has_only_header_copy(tmp_path: Path) -> None:
    renderer = AuthoredSlideRenderer(tmp_path)
    template = renderer.pack["templates"][7]
    renderer.copy_layer(template, {
        slot["id"]: "Example" for slot in template["copy_slots"] if slot["id"] != "caption"
    }, tmp_path / "copy.png")
    measurements = json.loads((tmp_path / "copy.json").read_text("utf-8"))
    assert {item["slot"] for item in measurements} == {"chapter", "counter"}
    assert all(item["fits"] for item in measurements)


def test_composition_bounds_static_inputs_and_resets_recording_clock(tmp_path: Path) -> None:
    renderer = AuthoredSlideRenderer(tmp_path)
    template = renderer.pack["templates"][1]
    aperture = template["product_aperture"]
    probe = {
        "streams": [
            {"codec_type": "video", "width": aperture["width"], "height": aperture["height"]}
        ]
    }
    with (
        patch.object(renderer, "copy_layer"),
        patch.object(renderer, "caption_images", return_value=tmp_path / "captions.txt"),
        patch("demodirector_worker.presentation_assets.media_probe", return_value=probe),
        patch("demodirector_worker.presentation_assets.run_ffmpeg") as ffmpeg,
    ):
        renderer.compose(
            template,
            {},
            10_000,
            tmp_path / "voice.wav",
            "Open the dashboard.",
            tmp_path / "recording.mp4",
            0,
        )
    arguments = ffmpeg.call_args.args[0]
    loops = [index for index, value in enumerate(arguments) if value == "-loop"]
    assert len(loops) == 4
    for index in loops:
        assert arguments[index - 2 : index] == ["-t", "10.0"]
    filters = arguments[arguments.index("-filter_complex") + 1]
    assert "[5:v]setpts=PTS-STARTPTS" in filters


def test_zoom_is_applied_only_inside_product_aperture(tmp_path: Path) -> None:
    renderer = AuthoredSlideRenderer(tmp_path)
    template = renderer.pack["templates"][4]
    aperture = template["product_aperture"]
    zoom = ZoomClip(
        id="click-focus",
        start_ms=1000,
        end_ms=3500,
        scale=1.5,
        target_rect=BoundingBox(x=200, y=100, width=100, height=40),
        easing="ease_in_out",
        source="auto",
        source_viewport=Viewport(width=aperture["width"], height=aperture["height"]),
    )
    with (
        patch.object(renderer, "copy_layer"),
        patch.object(renderer, "caption_images", return_value=tmp_path / "captions.txt"),
        patch(
            "demodirector_worker.presentation_assets.media_probe",
            return_value={
                "streams": [
                    {
                        "codec_type": "video",
                        "width": aperture["width"],
                        "height": aperture["height"],
                    }
                ],
            },
        ),
        patch("demodirector_worker.presentation_assets.run_ffmpeg") as ffmpeg,
    ):
        renderer.compose(
            template,
            {},
            10000,
            tmp_path / "voice.wav",
            "Open the page.",
            tmp_path / "recording.mp4",
            4,
            zoom_clips=[zoom],
        )
    arguments = ffmpeg.call_args.args[0]
    filters = arguments[arguments.index("-filter_complex") + 1]
    assert "[5:v]zoompan" in filters
    assert "[focused]setpts" in filters
    assert f"s={aperture['width']}x{aperture['height']}" in filters
