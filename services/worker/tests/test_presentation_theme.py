from pathlib import Path

import pytest
from demodirector_worker.presentation_assets import AuthoredSlideRenderer, load_pack


def test_google_presentation_uses_saved_qhd_assets_and_same_scene_schedule(tmp_path: Path) -> None:
    renderer = AuthoredSlideRenderer(tmp_path, theme="google")
    assert renderer.pack["pack_id"] == "presentation-story-google@1"
    assert renderer.canvas["width"] == 2560
    assert renderer.canvas["height"] == 1440
    assert renderer.pack["schedule"] == load_pack()["schedule"]
    assert renderer.pack_root.name == "presentation-story-google-v1"


def test_unknown_presentation_theme_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="theme"):
        AuthoredSlideRenderer(tmp_path, theme="../invalid")
