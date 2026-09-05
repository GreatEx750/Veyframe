from datetime import UTC, datetime

from demodirector_contracts import RenderConfig
from demodirector_contracts.editorial import (
    EditorialScene,
    EditorialTemplateId,
    EditorialTemplatePlan,
)
from demodirector_worker.editorial import EditorialCompositionCompiler


def scene(template_id: EditorialTemplateId = "hook") -> EditorialScene:
    return EditorialScene(
        id="editorial-scene-1",
        scene_id="scene-1",
        section="hook",
        template_id=template_id,
        product_clip_ref="scene:scene-1",
        product_treatment="moving_background",
        start_ms=0,
        end_ms=10_000,
        title="Show the product from the first frame",
        crop={"x": 0, "y": 0, "width": 1, "height": 1},  # type: ignore[arg-type]
    )


def plan(scenes: list[EditorialScene] | None = None) -> EditorialTemplatePlan:
    return EditorialTemplatePlan(
        id="editorial-plan-1",
        project_id="project-1",
        job_id="job-1",
        run_id="run-1",
        motion_plan_id="motion-plan-1",
        catalog_version="editorial-v1",
        design_version="motion-v1",
        duration_ms=10_000,
        scene_ids=["scene-1"],
        product_clip_refs=["scene:scene-1"],
        summary="Product-present hook.",
        scenes=scenes or [scene()],
        created_at=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
    )


def test_all_six_templates_compile_deterministically_with_visible_product() -> None:
    templates: list[EditorialTemplateId] = [
        "hook",
        "framed_product",
        "feature_callout",
        "split_explanation",
        "proof_safety",
        "closing",
    ]
    compiler = EditorialCompositionCompiler()
    hashes: set[str] = set()
    for template in templates:
        composition = compiler.compile(
            plan(scenes=[scene(template_id=template)]),
            RenderConfig(width=2560, height=1440, fps=30),
        )
        assert composition.product_presence.percentage == 100
        assert composition.scenes[0].template_id == template
        hashes.add(composition.deterministic_hash)
    assert len(hashes) == len(templates)


def test_template_geometry_scales_equivalently() -> None:
    compiler = EditorialCompositionCompiler()
    hd = compiler.compile(plan(), RenderConfig(width=1920, height=1080))
    qhd = compiler.compile(plan(), RenderConfig(width=2560, height=1440))
    assert hd.scenes[0].safe_margin_x / hd.width == qhd.scenes[0].safe_margin_x / qhd.width
    assert hd.scenes[0].safe_margin_y / hd.height == qhd.scenes[0].safe_margin_y / qhd.height
