from __future__ import annotations

from collections.abc import Sequence

import pytest
from demodirector_contracts import BoundingBox, InteractionEvent, Viewport, ZoomClip
from demodirector_worker.auto_camera import (
    AutoCameraError,
    AutoCameraService,
    AutoCameraSettings,
    FocusCandidate,
)


def interaction(
    timestamp_ms: int,
    *,
    x: float = 500,
    y: float = 300,
) -> InteractionEvent:
    box = BoundingBox(x=x, y=y, width=120, height=60)
    return InteractionEvent(
        timestamp_ms=timestamp_ms,
        event_type="click",
        locator="button:Save demo",
        x=x + 60,
        y=y + 30,
        bounding_box=box,
        viewport=Viewport(width=1280, height=720),
    )


def test_click_target_produces_centered_safe_zoom() -> None:
    settings = AutoCameraSettings(min_scale=1.25, max_scale=2.0, edge_padding_px=20)
    clip = AutoCameraService(settings=settings).generate([interaction(1_000)], 5_000)[0]

    assert clip.start_ms == 800
    assert clip.end_ms == 2_000
    assert clip.scale == 2.0
    assert 1.25 <= clip.scale <= 2.0
    assert clip.target_rect.x + clip.target_rect.width / 2 == pytest.approx(560)
    assert clip.target_rect.y + clip.target_rect.height / 2 == pytest.approx(330)
    assert clip.focus_x == pytest.approx(560)
    assert clip.focus_y == pytest.approx(330)
    assert clip.source_viewport == Viewport(width=1280, height=720)
    assert clip.model_validate_json(clip.model_dump_json()) == clip


def test_adjacent_focus_moves_are_merged_and_timing_is_non_negative() -> None:
    clips = AutoCameraService().generate(
        [interaction(50), interaction(400, x=520, y=310)],
        3_000,
    )

    assert len(clips) == 1
    assert clips[0].start_ms == 0
    assert clips[0].end_ms == 1_400


def test_manual_zoom_overrides_overlapping_generated_zoom() -> None:
    manual = ZoomClip(
        id="zoom-manual-1",
        start_ms=700,
        end_ms=2_100,
        scale=1.4,
        target_rect=BoundingBox(x=100, y=100, width=500, height=300),
        easing="ease_out",
        source="manual",
    )

    clips = AutoCameraService().generate([interaction(1_000)], 5_000, manual_clips=[manual])

    assert clips == [manual]


class BadSelector:
    def select(self, candidates: Sequence[FocusCandidate]) -> list[int]:
        return [len(candidates)]


def test_invalid_model_selection_fails_closed() -> None:
    with pytest.raises(AutoCameraError, match="unknown candidate"):
        AutoCameraService(selector=BadSelector()).generate([interaction(1_000)], 5_000)


def test_invalid_camera_bounds_are_rejected() -> None:
    with pytest.raises(ValueError, match="scale bounds"):
        AutoCameraSettings(min_scale=0.8, max_scale=4.5)
