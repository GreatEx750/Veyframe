"""Verify the format showcase through Veyframe's authored-slide recorder."""

from pathlib import Path

from demodirector_api.presentation_pipeline import action
from demodirector_contracts import Scene
from demodirector_worker.presentation_assets import AuthoredSlideRenderer


def main() -> None:
    output = Path("artifacts/veyframe-self-demo/format-recording-v2")
    renderer = AuthoredSlideRenderer(output)
    receipt = output / "capture.json"
    if receipt.exists():
        print("Format recording already saved; inspect it before replacing.", flush=True)
        return
    steps = [
        action("assert_visible", "dialog video", "Watch the saved Spotlight example"),
        action("click", 'button[aria-label="Close example"]', "Close the Spotlight example"),
        action("click", '[role="tab"]:has-text("Shorts")', "Select the social Short format"),
        action("click", 'button:has-text("A little time. A whole product story.")',
               "Play the previously generated vertical Short example"),
        action("assert_visible", "dialog video", "Watch the Short's recorded product footage"),
    ]
    scene = Scene.model_validate({
        "id": "format-showcase", "storyboard_id": "veyframe-self-demo", "order": 6,
        "title": "Formats for the marketing workflow", "objective": "Show saved examples",
        "narration": "Choose a feature spotlight or a vertical social short.",
        "duration_seconds": 20,
        "capture_plan": {"start_url": "https://veyframe-web-5zo4cenn3q-uc.a.run.app/",
                         "timeout_seconds": 180, "actions": steps},
    })
    video, result = renderer.capture(
        scene, 20_000, renderer.pack["templates"][6],
        preparation=[action("click", '[role="tab"]:has-text("Spotlights")',
                            "Prepare the Spotlight format preview"),
                     action("click", 'button:has-text("One feature. A moment in the spotlight.")',
                            "Open the saved Spotlight example")],
        on_progress=lambda message: print(message, flush=True),
    )
    assert result.status == "succeeded" and len(result.interaction_events) == 3
    receipt.write_text(result.model_dump_json(indent=2), "utf-8")
    print(f"PASS: three visible interactions; {video}", flush=True)


if __name__ == "__main__":
    main()
