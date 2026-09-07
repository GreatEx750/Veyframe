"""Verify the pre-generated alternate template assets remain complete and self-contained."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src" / "demodirector_worker" / "templates"


def test_google_phone_short_matches_approved_asymmetric_frame() -> None:
    from PIL import Image

    pack = json.loads((ROOT / "short-vertical-google-v1/manifest.json").read_text("utf-8"))
    template = pack["templates"][1]
    assert template["product_aperture"] == {
        "x": 56, "y": 500, "width": 968, "height": 902, "corner_radius": 32,
    }
    background = ROOT / "short-vertical-google-v1" / template["assets"]["background_png"]
    with Image.open(background) as frame:
        rgb = frame.convert("RGB")
        assert rgb.getpixel((100, 120)) == (26, 115, 232)
        assert rgb.getpixel((56, 86)) == (0, 0, 0)
        assert rgb.getpixel((600, 1600)) == (255, 102, 102)
        assert rgb.getpixel((420, 1450)) == (255, 255, 255)
        assert rgb.getpixel((800, 450)) == (0, 0, 0)


def test_google_short_product_masks_round_all_four_corners() -> None:
    from PIL import Image

    root = ROOT / "short-vertical-google-v1"
    pack = json.loads((root / "manifest.json").read_text("utf-8"))
    for template in pack["templates"]:
        assert template["visual_revision"] == "short-vertical-google-rounded-3"
        if not template["requires_product"]:
            continue
        with Image.open(root / template["assets"]["product_mask_png"]) as image:
            mask = image.convert("L")
            for corner in [(56, 500), (1023, 500), (56, 1401), (1023, 1401)]:
                assert mask.getpixel(corner) == 0
            assert mask.getpixel((540, 500)) == 255
            assert mask.getpixel((540, 950)) == 255
    default = json.loads((ROOT / "short-vertical-v1/manifest.json").read_text("utf-8"))
    assert default["templates"][1]["product_aperture"]["corner_radius"] == 0


def test_promo_theme_selection_preserves_default_and_rejects_unknown() -> None:
    from demodirector_worker.promo_assets import promo_root

    assert promo_root("short_demo", "vertical").name == "short-vertical-v1"
    assert promo_root("short_demo", "vertical", theme="google").name == "short-vertical-google-v1"
    with pytest.raises(ValueError):
        promo_root("short_demo", "vertical", theme="../unknown")


def test_alternate_promo_templates_are_allowed_by_typed_slide_script() -> None:
    from demodirector_api.presentation_pilot import SlideScript
    from pydantic import ValidationError

    fields = {
        "narration": "Explore Wikipedia", "capture_recipe": "title",
        "source_ids": ["source-1"],
        "text": [{"slot_id": "brand", "text": "Wikipedia"},
                 {"slot_id": "headline", "text": "Explore knowledge"}],
    }
    for mode in ["short", "spotlight"]:
        pack = json.loads((ROOT / f"{mode}-vertical-google-v1/manifest.json").read_text("utf-8"))
        for template in pack["templates"]:
            assert SlideScript.model_validate({**fields, "template_id": template["id"]})
    with pytest.raises(ValidationError):
        SlideScript.model_validate({**fields, "template_id": "untrusted-template"})


@pytest.mark.parametrize(
    ("folder", "pack_id", "mode", "duration_ms", "template_count"),
    [
        (
            "spotlight-landscape-google-v1",
            "spotlight-landscape-google@1",
            "spotlight_demo",
            30_000,
            3,
        ),
        (
            "spotlight-vertical-google-v1",
            "spotlight-vertical-google@1",
            "spotlight_demo",
            30_000,
            3,
        ),
        ("short-landscape-google-v1", "short-landscape-google@1", "short_demo", 45_000, 5),
        ("short-vertical-google-v1", "short-vertical-google@1", "short_demo", 45_000, 5),
        ("presentation-story-google-v1", "presentation-story-google@1", None, 120_000, 9),
    ],
)
def test_multicolor_template_pack_integrity(
    folder: str, pack_id: str, mode: str | None, duration_ms: int, template_count: int
) -> None:
    root = ROOT / folder
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    assert manifest["pack_id"] == pack_id
    assert manifest["theme"] == "google"
    if mode is not None:
        assert manifest["mode"] == mode
    assert len(manifest["templates"]) == template_count
    assert manifest["schedule"][0]["start_ms"] == 0
    assert manifest["schedule"][-1]["end_ms"] == duration_ms
    for relative, digest in manifest["integrity"]["files"].items():
        asset = (root / relative).resolve()
        assert asset.is_relative_to(root.resolve())
        assert hashlib.sha256(asset.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize(
    "folder",
    [
        "short-landscape-v1",
        "short-vertical-v1",
        "short-landscape-google-v1",
        "short-vertical-google-v1",
    ],
)
def test_short_templates_keep_the_brief_above_product_and_narration_below(folder: str) -> None:
    manifest = json.loads((ROOT / folder / "manifest.json").read_text("utf-8"))
    caption = manifest["caption_layout"]
    for template in manifest["templates"]:
        if not template["requires_product"]:
            continue
        slots = {slot["id"]: slot for slot in template["copy_slots"]}
        brief = slots["headline"]
        aperture = template["product_aperture"]
        assert brief["font_token"] == "body"
        assert brief["max_lines"] == 2
        assert brief["rect"]["y"] + brief["rect"]["height"] <= aperture["y"]
        assert aperture["y"] + aperture["height"] <= caption["y"]


def test_phone_short_captions_use_readable_theme_colors(tmp_path: Path) -> None:
    from demodirector_worker.presentation_assets import AuthoredSlideRenderer
    from PIL import Image

    renderer = AuthoredSlideRenderer(tmp_path, pack_root=ROOT / "short-vertical-google-v1")
    renderer.caption_images("Watch each step", tmp_path, 1.0)
    with Image.open(tmp_path / "caption-000.png") as frame:
        pixels = set(frame.convert("RGBA").getdata())
    assert (32, 33, 36, 255) in pixels
    assert (255, 255, 255, 255) in pixels
