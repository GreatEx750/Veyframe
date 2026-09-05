from __future__ import annotations

import binascii
import hashlib
import json
import struct
import zlib
from functools import lru_cache
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any, cast

PACK_DIRECTORY = "presentation-story-v2"
PACK_ID = "presentation-story@2"
CANVAS_SIZE = (2560, 1440)
PREVIEW_SIZE = (1280, 720)
PACK_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "demodirector_worker"
    / "templates"
    / PACK_DIRECTORY
)

EXPECTED_SCHEDULE = [
    (0, 3_000, "hook-question@2"),
    (3_000, 13_000, "brand-promise@2"),
    (13_000, 28_000, "context-split@2"),
    (28_000, 45_000, "workflow-rail@2"),
    (45_000, 61_000, "prompt-over-product@2"),
    (61_000, 78_000, "focus-detail@2"),
    (78_000, 98_000, "human-review@2"),
    (98_000, 115_000, "trust-cards@2"),
    (115_000, 120_000, "brand-outro@2"),
]

BASE_ASSET_KEYS = {
    "source_svg",
    "background_png",
    "foreground_png",
    "preview_png",
}


@lru_cache(maxsize=1)
def _manifest() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((PACK_PATH / "manifest.json").read_text(encoding="utf-8")),
    )


def _template_by_id() -> dict[str, dict[str, Any]]:
    templates = _manifest()["templates"]
    return {template["id"]: template for template in templates}


def _assert_safe_relative_path(value: str) -> PurePosixPath:
    assert isinstance(value, str) and value
    assert "\\" not in value, f"asset path must use forward slashes: {value}"
    path = PurePosixPath(value)
    assert not path.is_absolute(), f"asset path must be relative: {value}"
    assert all(part not in {"", ".", ".."} for part in path.parts), (
        f"asset path must remain inside the pack: {value}"
    )

    resolved = (PACK_PATH / Path(*path.parts)).resolve()
    resolved.relative_to(PACK_PATH.resolve())
    return path


def _asset_references(manifest: dict[str, Any]) -> set[str]:
    references: set[str] = set()
    for template in manifest["templates"]:
        folder = _assert_safe_relative_path(template["folder"])
        assets = template["assets"]
        assert isinstance(assets, dict) and assets
        for value in assets.values():
            path = _assert_safe_relative_path(value)
            assert path.is_relative_to(folder), (
                f"template asset {value} must live below {template['folder']}"
            )
            references.add(value)
    return references


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    assert data.startswith(b"\x89PNG\r\n\x1a\n"), "invalid PNG signature"
    chunks: list[tuple[bytes, bytes]] = []
    offset = 8
    while offset < len(data):
        assert offset + 12 <= len(data), "truncated PNG chunk"
        length = struct.unpack_from(">I", data, offset)[0]
        chunk_type = data[offset + 4 : offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        assert payload_end + 4 <= len(data), "truncated PNG payload"
        payload = data[payload_start:payload_end]
        expected_crc = struct.unpack_from(">I", data, payload_end)[0]
        actual_crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
        assert actual_crc == expected_crc, f"invalid {chunk_type!r} chunk CRC"
        chunks.append((chunk_type, payload))
        offset = payload_end + 4
        if chunk_type == b"IEND":
            break
    assert chunks and chunks[-1][0] == b"IEND", "PNG is missing IEND"
    assert offset == len(data), "unexpected data after PNG IEND"
    return chunks


def _png_ihdr(path: Path) -> tuple[int, int, int, int, int]:
    chunks = _png_chunks(path.read_bytes())
    assert chunks[0][0] == b"IHDR" and len(chunks[0][1]) == 13
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    assert compression == 0
    assert filtering == 0
    return width, height, bit_depth, color_type, interlace


def _paeth(left: int, above: int, upper_left: int) -> int:
    prediction = left + above - upper_left
    distance_left = abs(prediction - left)
    distance_above = abs(prediction - above)
    distance_upper_left = abs(prediction - upper_left)
    if distance_left <= distance_above and distance_left <= distance_upper_left:
        return left
    if distance_above <= distance_upper_left:
        return above
    return upper_left


def _grayscale_mask_statistics(path: Path) -> tuple[int, tuple[int, int, int, int]]:
    chunks = _png_chunks(path.read_bytes())
    width, height, bit_depth, color_type, interlace = _png_ihdr(path)
    assert (bit_depth, color_type, interlace) == (8, 0, 0), (
        "product masks must be non-interlaced 8-bit grayscale PNGs"
    )
    compressed = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    decoded = zlib.decompress(compressed)
    row_size = width
    assert len(decoded) == height * (row_size + 1)

    previous = bytearray(row_size)
    cursor = 0
    nonzero = 0
    min_x, min_y = width, height
    max_x = max_y = -1
    for y in range(height):
        filter_type = decoded[cursor]
        cursor += 1
        encoded = decoded[cursor : cursor + row_size]
        cursor += row_size
        reconstructed = bytearray(row_size)
        for x, value in enumerate(encoded):
            left = reconstructed[x - 1] if x else 0
            above = previous[x]
            upper_left = previous[x - 1] if x else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                raise AssertionError(f"unsupported PNG row filter: {filter_type}")
            pixel = (value + predictor) & 0xFF
            reconstructed[x] = pixel
            if pixel:
                nonzero += 1
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
        previous = reconstructed

    assert nonzero > 0, "product mask cannot be empty"
    return nonzero, (min_x, min_y, max_x, max_y)


def test_manifest_identity_canvas_and_schedule_are_fixed() -> None:
    manifest = _manifest()
    assert manifest["schema_version"] == 1
    assert manifest["pack_id"] == PACK_ID
    assert isinstance(manifest["display_name"], str) and manifest["display_name"].strip()
    assert isinstance(manifest["status"], str) and manifest["status"].strip()
    assert (manifest["canvas"]["width"], manifest["canvas"]["height"]) == CANVAS_SIZE
    assert manifest["canvas"]["color_space"] == "sRGB"
    assert (
        manifest["preview_canvas"]["width"],
        manifest["preview_canvas"]["height"],
    ) == PREVIEW_SIZE

    safe_area = manifest["canvas"]["safe_area"]
    assert all(isinstance(safe_area[key], int) for key in ("x", "y", "width", "height"))
    assert safe_area["x"] >= 0 and safe_area["y"] >= 0
    assert safe_area["width"] > 0 and safe_area["height"] > 0
    assert safe_area["x"] + safe_area["width"] <= CANVAS_SIZE[0]
    assert safe_area["y"] + safe_area["height"] <= CANVAS_SIZE[1]

    schedule = manifest["schedule"]
    assert [
        (entry["start_ms"], entry["end_ms"], entry["template_id"]) for entry in schedule
    ] == EXPECTED_SCHEDULE
    assert all(
        left["end_ms"] == right["start_ms"]
        for left, right in zip(schedule, schedule[1:], strict=False)
    )
    assert schedule[0]["start_ms"] == 0
    assert schedule[-1]["end_ms"] == 120_000


def test_template_ids_roles_and_product_window_are_strict() -> None:
    manifest = _manifest()
    templates = manifest["templates"]
    ids = [template["id"] for template in templates]
    assert len(ids) == len(set(ids)) == len(EXPECTED_SCHEDULE)
    assert ids == [template_id for _, _, template_id in EXPECTED_SCHEDULE]

    by_id = _template_by_id()
    transition_presets = manifest["transition_presets"]
    assert isinstance(transition_presets, dict) and transition_presets

    for entry in manifest["schedule"]:
        template = by_id[entry["template_id"]]
        if entry["end_ms"] <= 3_000:
            expected_role = "intro"
        elif entry["start_ms"] >= 115_000:
            expected_role = "outro"
        else:
            assert entry["start_ms"] >= 3_000
            assert entry["end_ms"] <= 115_000
            expected_role = "product"
        assert template["role"] == expected_role
        assert template["requires_product"] is (expected_role == "product")
        assert entry["transition_preset"] in transition_presets
        assert template["motion_preset"] in transition_presets

        assets = template["assets"]
        assert set(assets) >= BASE_ASSET_KEYS
        if expected_role == "product":
            assert "product_mask_png" in assets
            aperture = template["product_aperture"]
            assert aperture["fit"] == "contain_over_blur"
            assert all(
                isinstance(aperture[key], int)
                for key in ("x", "y", "width", "height", "corner_radius")
            )
            assert aperture["x"] > 0 and aperture["y"] > 0
            assert aperture["width"] > 0 and aperture["height"] > 0
            assert aperture["corner_radius"] >= 0
            assert aperture["x"] + aperture["width"] < CANVAS_SIZE[0]
            assert aperture["y"] + aperture["height"] < CANVAS_SIZE[1]
        else:
            assert "product_mask_png" not in assets
            assert "product_aperture" not in template


def test_assets_are_in_pack_complete_and_match_declared_hashes() -> None:
    manifest = _manifest()
    references = _asset_references(manifest)
    integrity = manifest["integrity"]
    assert integrity["algorithm"] == "sha256"
    hashes = integrity["files"]
    assert isinstance(hashes, dict) and references <= set(hashes)

    for relative_path, declared_hash in hashes.items():
        path = _assert_safe_relative_path(relative_path)
        absolute_path = PACK_PATH / Path(*path.parts)
        assert absolute_path.is_file(), f"missing declared asset: {relative_path}"
        assert isinstance(declared_hash, str) and len(declared_hash) == 64
        int(declared_hash, 16)
        assert hashlib.sha256(absolute_path.read_bytes()).hexdigest() == declared_hash.lower()

    for relative_path in references:
        asset_path = PACK_PATH / Path(*PurePosixPath(relative_path).parts)
        assert asset_path.is_file(), f"missing template asset: {relative_path}"


def test_png_assets_have_their_declared_dimensions_and_color_types() -> None:
    for template in _manifest()["templates"]:
        assets = template["assets"]
        for asset_key in ("background_png", "foreground_png"):
            png = PACK_PATH / Path(*PurePosixPath(assets[asset_key]).parts)
            width, height, bit_depth, color_type, interlace = _png_ihdr(png)
            assert (width, height) == CANVAS_SIZE
            assert bit_depth == 8 and interlace == 0
            if asset_key == "background_png":
                assert color_type in {2, 6}, "background must be RGB or RGBA"
            else:
                assert color_type == 6, "foreground must preserve RGBA transparency"

        preview = PACK_PATH / Path(*PurePosixPath(assets["preview_png"]).parts)
        width, height, bit_depth, color_type, interlace = _png_ihdr(preview)
        assert (width, height) == PREVIEW_SIZE
        assert bit_depth == 8 and color_type in {2, 6} and interlace == 0

        if template["requires_product"]:
            mask = PACK_PATH / Path(*PurePosixPath(assets["product_mask_png"]).parts)
            assert _png_ihdr(mask) == (*CANVAS_SIZE, 8, 0, 0)


def test_product_masks_are_bounded_and_leave_a_large_product_aperture() -> None:
    canvas_width, canvas_height = CANVAS_SIZE
    canvas_pixels = canvas_width * canvas_height
    product_templates = [
        template for template in _manifest()["templates"] if template["role"] == "product"
    ]
    assert product_templates

    for template in product_templates:
        mask_path = PACK_PATH / Path(*PurePosixPath(template["assets"]["product_mask_png"]).parts)
        nonzero, (min_x, min_y, max_x, max_y) = _grayscale_mask_statistics(mask_path)
        aperture = template["product_aperture"]
        aperture_right = aperture["x"] + aperture["width"] - 1
        aperture_bottom = aperture["y"] + aperture["height"] - 1

        assert min_x > 0 and min_y > 0
        assert max_x < canvas_width - 1 and max_y < canvas_height - 1
        assert aperture["x"] <= min_x <= max_x <= aperture_right
        assert aperture["y"] <= min_y <= max_y <= aperture_bottom
        assert max_x - min_x + 1 >= aperture["width"] * 0.9
        assert max_y - min_y + 1 >= aperture["height"] * 0.9
        assert nonzero >= canvas_pixels * 0.15
        assert nonzero >= aperture["width"] * aperture["height"] * 0.72


def test_all_pack_assets_are_readable_as_python_package_resources() -> None:
    package_root = resources.files("demodirector_worker")
    pack_resource = package_root.joinpath("templates", PACK_DIRECTORY)
    manifest_resource = pack_resource.joinpath("manifest.json")
    assert manifest_resource.is_file()
    resource_manifest = json.loads(manifest_resource.read_text(encoding="utf-8"))
    assert resource_manifest["pack_id"] == PACK_ID

    expected_resources = _asset_references(resource_manifest) | set(
        resource_manifest["integrity"]["files"]
    )
    for relative_path in expected_resources:
        resource = pack_resource.joinpath(*PurePosixPath(relative_path).parts)
        assert resource.is_file(), f"missing package resource: {relative_path}"
        assert resource.read_bytes(), f"empty package resource: {relative_path}"


def test_product_windows_have_no_decorative_recording_badge() -> None:
    from PIL import Image

    for template in _manifest()["templates"]:
        if not template["requires_product"]:
            continue
        x, y = (template["product_aperture"][key] for key in ("x", "y"))
        with Image.open(PACK_PATH / template["assets"]["foreground_png"]) as foreground:
            # The top-left product area should match the adjacent undecorated area,
            # including any intentional full-window dimming layer.
            reference = foreground.getpixel((x + 240, y + 48))
            assert foreground.getpixel((x + 54, y + 48)) == reference
            assert foreground.getpixel((x + 120, y + 48)) == reference


def test_second_slide_shows_product_for_ten_seconds_with_copy_above_footage() -> None:
    template = _manifest()["templates"][1]
    timing = _manifest()["schedule"][1]
    assert template["requires_product"] is True
    assert timing["end_ms"] - timing["start_ms"] == 10_000
    aperture = template["product_aperture"]
    assert (aperture["width"], aperture["height"]) == (2304, 816)
    for slot in template["copy_slots"]:
        if slot["id"] != "caption":
            assert slot["rect"]["y"] + slot["rect"]["height"] <= aperture["y"]
