from __future__ import annotations

import copy

import pytest
from demodirector_worker.presentation_assets import capture_settings_for_template, load_pack


@pytest.mark.parametrize("index", [2, 3, 4, 5, 6, 7])
def test_recording_dimensions_match_each_product_window(index: int) -> None:
    template = load_pack()["templates"][index]
    settings = capture_settings_for_template(template)
    aperture = template["product_aperture"]
    assert (settings.viewport_width, settings.viewport_height) == (
        aperture["width"],
        aperture["height"],
    )


@pytest.mark.parametrize("width", [0, -2, 2303, 3000, "2304", True])
def test_invalid_recording_geometry_is_rejected(width: object) -> None:
    template = copy.deepcopy(load_pack()["templates"][4])
    template["product_aperture"]["width"] = width
    with pytest.raises(ValueError, match="aperture"):
        capture_settings_for_template(template)


def test_title_cards_do_not_create_browser_recordings() -> None:
    with pytest.raises(ValueError, match="product"):
        capture_settings_for_template(load_pack()["templates"][0])
