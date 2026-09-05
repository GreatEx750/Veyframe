from demodirector_contracts import BoundingBox, RenderConfig, Viewport, ZoomClip
from demodirector_worker.attention import AttentionCompiler
from test_attention_contracts import attention_plan


def test_attention_compiler_maps_anchor_through_camera_and_avoids_captions() -> None:
    zoom = ZoomClip(
        id="zoom-1",
        start_ms=500,
        end_ms=2_500,
        scale=1.5,
        target_rect=BoundingBox(x=200, y=100, width=100, height=100),
        focus_x=250,
        focus_y=150,
        source_viewport=Viewport(width=1280, height=720),
        easing="ease_in_out",
        source="auto",
    )
    compiled = AttentionCompiler().compile(
        attention_plan(), RenderConfig(width=1920, height=1080, fps=30), [zoom]
    )
    assert compiled.callouts[0].placement == "top_right"
    assert compiled.callouts[0].anchor_x >= 0
    assert compiled.collisions[0].overlaps_caption is False
    assert len(compiled.deterministic_hash) == 64
