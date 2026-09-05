from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from demodirector_worker.presentation import (
    INTRO_END_MS,
    OUTRO_START_MS,
    PRESENTATION_DURATION_MS,
    PRESENTATION_PACK_ID,
    PRESENTATION_RENDER_RECIPE_VERSION,
    PRESENTATION_TEMPLATE_IDS,
    Aperture,
    build_presentation_schedule,
    resolve_palette_color,
    resolve_presentation_pack,
)


def test_pack_has_exact_versioned_id_template_order_and_product_roles() -> None:
    pack = resolve_presentation_pack(PRESENTATION_PACK_ID)

    assert pack.id == "presentation-story@1"
    assert pack.render_recipe_version == PRESENTATION_RENDER_RECIPE_VERSION
    assert (pack.aspect_width, pack.aspect_height) == (16, 9)
    assert tuple(template.id for template in pack.templates) == (
        "hook-question@1",
        "brand-reveal@1",
        "product-split@1",
        "guided-workflow@1",
        "template-populate@1",
        "review-gate@1",
        "constraints-three-up@1",
        "brand-outro@1",
    )
    assert tuple(template.id for template in pack.templates) == PRESENTATION_TEMPLATE_IDS
    assert [template.role for template in pack.templates] == [
        "intro",
        "intro",
        "product",
        "product",
        "product",
        "product",
        "product",
        "outro",
    ]
    assert [template.requires_product for template in pack.templates] == [
        False,
        False,
        True,
        True,
        True,
        True,
        True,
        False,
    ]


def test_pack_is_immutable_and_unknown_ids_are_rejected() -> None:
    pack = resolve_presentation_pack(PRESENTATION_PACK_ID)

    with pytest.raises(FrozenInstanceError):
        pack.id = "replacement@1"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        pack.templates[2].copy_layout.x = 0.2  # type: ignore[misc]
    with pytest.raises(ValueError, match="unknown presentation pack id"):
        resolve_presentation_pack("presentation-story@2")


def test_120_second_schedule_has_fixed_boundaries_and_full_middle_coverage() -> None:
    schedule = build_presentation_schedule(PRESENTATION_DURATION_MS)
    middle = schedule[2:-1]
    product_ids = PRESENTATION_TEMPLATE_IDS[2:-1]

    assert [(entry.template_id, entry.start_ms, entry.end_ms) for entry in schedule[:2]] == [
        ("hook-question@1", 0, 3_000),
        ("brand-reveal@1", 3_000, INTRO_END_MS),
    ]
    assert schedule[-1].template_id == "brand-outro@1"
    assert (schedule[-1].start_ms, schedule[-1].end_ms) == (
        OUTRO_START_MS,
        PRESENTATION_DURATION_MS,
    )
    assert middle[0].start_ms == INTRO_END_MS
    assert middle[-1].end_ms == OUTRO_START_MS
    assert all(
        left.end_ms == right.start_ms
        for left, right in zip(schedule, schedule[1:], strict=False)
    )
    assert sum(entry.duration_ms for entry in middle) == OUTRO_START_MS - INTRO_END_MS
    assert all(entry.role == "product" and entry.requires_product for entry in middle)
    assert tuple(entry.template_id for entry in middle) == tuple(
        product_ids[index % len(product_ids)] for index in range(len(middle))
    )


@pytest.mark.parametrize("duration_ms", [19_999, 20_000, 119_999, 120_001, 120_000.0])
def test_schedule_rejects_every_other_duration(duration_ms: object) -> None:
    with pytest.raises(ValueError, match="exactly 120000 ms"):
        build_presentation_schedule(duration_ms)  # type: ignore[arg-type]


def test_schedule_is_deterministic() -> None:
    first = build_presentation_schedule(PRESENTATION_DURATION_MS)
    second = build_presentation_schedule(PRESENTATION_DURATION_MS)

    assert first == second
    assert first is not second


def test_every_template_has_fixed_normalized_in_bounds_geometry() -> None:
    expected = {
        "hook-question@1": Aperture(x=0.05, y=0.08, w=0.90, h=0.84),
        "brand-reveal@1": Aperture(x=0.05, y=0.08, w=0.90, h=0.84),
        "product-split@1": Aperture(x=0.42, y=0.11, w=0.53, h=0.70),
        "guided-workflow@1": Aperture(x=0.40, y=0.11, w=0.55, h=0.70),
        "template-populate@1": Aperture(x=0.05, y=0.25, w=0.90, h=0.56),
        "review-gate@1": Aperture(x=0.35, y=0.11, w=0.60, h=0.67),
        "constraints-three-up@1": Aperture(x=0.05, y=0.13, w=0.90, h=0.68),
        "brand-outro@1": Aperture(x=0.05, y=0.08, w=0.90, h=0.84),
    }

    pack = resolve_presentation_pack(PRESENTATION_PACK_ID)
    assert {template.id: template.aperture for template in pack.templates} == expected
    for template in pack.templates:
        aperture = template.aperture
        assert 0 <= aperture.x < 1
        assert 0 <= aperture.y < 1
        assert 0 < aperture.w <= 1
        assert 0 < aperture.h <= 1
        assert aperture.x + aperture.w <= 1
        assert aperture.y + aperture.h <= 1


def test_pack_owns_copy_motion_and_palette_recipes_used_by_the_renderer() -> None:
    pack = resolve_presentation_pack(PRESENTATION_PACK_ID)
    product_templates = [template for template in pack.templates if template.requires_product]

    assert [template.transition.name for template in pack.templates] == [
        "stagger-tags",
        "palette-cut",
        "split-reveal",
        "prompt-sequence",
        "focus-reveal",
        "review-reveal",
        "stagger-cards",
        "brand-hold",
    ]
    assert all(template.copy_layout.panel_width > 0 for template in product_templates)
    assert all(template.copy_layout.panel_height > 0 for template in product_templates)
    assert len({
        (
            template.transition.product_offset_x,
            template.transition.product_offset_y,
            template.transition.copy_offset_x,
            template.transition.copy_offset_y,
        )
        for template in product_templates
    }) == len(product_templates)
    assert resolve_palette_color(pack.templates[0].palette.canvas) == "173D34"
    assert resolve_palette_color(pack.templates[-1].palette.canvas) == "98E3CD"
