"""Run each reviewed Roamstead scene through the application's actual slide recorder."""

import json
import os
from pathlib import Path

from demodirector_api.recording_workflows import approved_workflow
from demodirector_contracts import Scene
from demodirector_worker.presentation_assets import AuthoredSlideRenderer


def main() -> None:
    url = os.getenv("ROAMSTEAD_DEMO_URL", "").rstrip("/") + "/"
    if url == "/":
        raise RuntimeError("ROAMSTEAD_DEMO_URL is required")
    workflow = approved_workflow(url)
    assert workflow
    output = Path("artifacts/veyframe-self-demo/roamstead-recordings")
    renderer = AuthoredSlideRenderer(output)
    for name, index in [("related", 1), ("search", 2), ("article", 3)]:
        receipt = output / f"{name}.json"
        if receipt.exists():
            print(f"Already verified {name}", flush=True)
            continue
        recipe = workflow[name]
        scene = Scene.model_validate({
            "id": name, "storyboard_id": "roamstead-verification", "order": index,
            "title": f"Roamstead {name}", "objective": "Verify the real product walkthrough",
            "narration": "Inspect the product", "duration_seconds": 10,
            "capture_plan": {"start_url": url, "timeout_seconds": 180,
                             "actions": [a.model_dump() for a in recipe.actions]},
        })
        print(f"Preparing and recording {name}", flush=True)
        path, result = renderer.capture(
            scene, 10000, renderer.pack["templates"][index], preparation=recipe.preparation,
            on_progress=lambda message: print(message, flush=True),
        )
        assert result.status == "succeeded" and result.interaction_events
        receipt.write_text(result.model_dump_json(indent=2), "utf-8")
        print(json.dumps({"scene": name, "video": str(path),
                          "interactions": len(result.interaction_events)}), flush=True)


if __name__ == "__main__":
    main()
