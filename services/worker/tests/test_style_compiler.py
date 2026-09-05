from demodirector_contracts import RenderConfig
from demodirector_worker.style import StyleCompiler
from test_style_contracts import style_plan


def test_style_compiler_is_deterministic_and_resolution_aware() -> None:
    plan = style_plan()
    compiler = StyleCompiler()
    full_hd = compiler.compile(plan, RenderConfig(width=1920, height=1080, fps=30))
    qhd = compiler.compile(plan, RenderConfig(width=2560, height=1440, fps=30))
    assert full_hd.safe_margin_x == 96 and qhd.safe_margin_x == 128
    assert full_hd.deterministic_hash != qhd.deterministic_hash


def test_style_switch_changes_composition_without_changing_scene_data() -> None:
    plan = style_plan()
    switched = plan.model_copy(
        update={
            "decision": plan.decision.model_copy(
                update={"selected_variant": "technical_proof", "outcome": "overridden"}
            )
        }
    )
    assert plan.scene_ids == switched.scene_ids
    assert plan.recommendation_evidence_refs == switched.recommendation_evidence_refs
    config = RenderConfig(width=1920, height=1080, fps=30)
    assert (
        StyleCompiler().compile(plan, config).deterministic_hash
        != StyleCompiler().compile(switched, config).deterministic_hash
    )
