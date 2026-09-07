"""Independent Spotlight/Short template packs; presentation defaults remain unchanged."""

import hashlib
import json
from pathlib import Path
from typing import Any

PROMO_MODES = {"spotlight_demo", "short_demo"}


def promo_root(mode: str, orientation: str, *, theme: str = "default") -> Path:
    if mode not in PROMO_MODES or orientation not in {"landscape", "vertical"}:
        raise ValueError("Unknown promo mode or orientation")
    if theme not in {"default", "google"}:
        raise ValueError("Unknown promo theme")
    suffix = "-google" if theme == "google" else ""
    folder = f"{mode.removesuffix('_demo')}-{orientation}{suffix}-v1"
    return Path(__file__).parent / "templates" / folder


def load_promo_pack(root: Path) -> dict[str, Any]:
    pack: dict[str, Any] = json.loads((root / "manifest.json").read_text("utf-8"))
    if pack.get("family") != "promo" or pack.get("mode") not in PROMO_MODES:
        raise ValueError("Unknown promo template pack")
    for relative, digest in pack["integrity"]["files"].items():
        asset = (root / relative).resolve()
        if root.resolve() not in asset.parents:
            raise ValueError("Asset escaped promo pack")
        if hashlib.sha256(asset.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Promo asset integrity failed: {relative}")
    return pack


def promo_schedule(pack: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any], str]]:
    templates = {t["id"]: t for t in pack["templates"]}
    expected = 30_000 if pack["mode"] == "spotlight_demo" else 45_000
    result = []
    previous = 0
    for timing in pack["schedule"]:
        template = templates[timing["template_id"]]
        if timing["start_ms"] != previous or timing["end_ms"] <= previous:
            raise ValueError("Promo schedule must be contiguous")
        if template["requires_product"] != (timing["recipe"] != "title"):
            raise ValueError("Promo footage does not match recipe")
        result.append((template, timing, timing["recipe"]))
        previous = timing["end_ms"]
    if previous != expected:
        raise ValueError("Promo schedule has the wrong duration")
    return result
