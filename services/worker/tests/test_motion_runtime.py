from datetime import UTC, datetime

from demodirector_contracts import RenderConfig
from demodirector_contracts.motion import MotionCue, MotionDirectionPlan, MotionTokenSet
from demodirector_worker.motion import MotionCompositionCompiler, motion_state


def plan() -> MotionDirectionPlan:
    primitives = [
        "fade_slide",
        "scale_settle",
        "stagger_text",
        "highlight_reveal",
        "browser_frame_move",
        "background_dim",
    ]
    layers = ["transition", "product", "captions", "callout", "background", "mask"]
    cues = [
        MotionCue(
            id=f"cue-{index}",
            scene_id="scene-1",
            primitive=primitive,  # type: ignore[arg-type]
            layer=layers[index],  # type: ignore[arg-type]
            start_ms=1000,
            end_ms=1600,
            easing="standard",
            text="Visible text" if primitive in {"stagger_text", "highlight_reveal"} else None,
            product_clip_ref="scene:scene-1",
        )
        for index, primitive in enumerate(primitives)
    ]
    return MotionDirectionPlan(
        id="motion-plan-1",
        project_id="project-1",
        job_id="job-1",
        run_id="motion-run-1",
        request_fingerprint="b" * 64,
        design_tokens=MotionTokenSet(),
        duration_ms=20_000,
        scene_ids=["scene-1"],
        product_clip_refs=["scene:scene-1"],
        summary="Keep the product visible.",
        cues=cues,
        created_at=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
    )


def test_compiler_is_deterministic_and_resolution_independent() -> None:
    compiler = MotionCompositionCompiler()
    first = compiler.compile(plan(), RenderConfig(width=1920, height=1080))
    again = compiler.compile(plan(), RenderConfig(width=1920, height=1080))
    qhd = compiler.compile(plan(), RenderConfig(width=2560, height=1440))

    assert first == again
    assert first.deterministic_hash == again.deterministic_hash
    assert first.deterministic_hash != qhd.deterministic_hash
    assert [cue.layer_index for cue in first.cues] == [6, 1, 5, 4, 0, 2]
    assert all(cue.start_frame == 30 and cue.end_frame == 48 for cue in first.cues)


def test_every_primitive_has_bounded_entrance_settled_and_exit_state() -> None:
    tokens = MotionTokenSet()
    for cue in plan().cues:
        before = motion_state(cue, 999, tokens)
        entrance = motion_state(cue, 1000, tokens)
        settled = motion_state(cue, 1300, tokens)
        exit_state = motion_state(cue, 1600, tokens)
        assert before.active is False and exit_state.active is False
        assert entrance.active is True and entrance.progress == 0
        assert settled.active is True and 0 < settled.progress < 1
        assert 0 <= settled.opacity <= 1
        assert 0.96 <= settled.scale <= 1
        assert 0 <= settled.dim_opacity <= 0.42
