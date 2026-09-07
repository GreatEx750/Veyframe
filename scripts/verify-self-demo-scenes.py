"""Exercise reviewed self-demo scenes through the application recording engine."""

import argparse
from pathlib import Path
from urllib.parse import urlsplit

from demodirector_api.recording_workflows import load_reviewed_profile
from demodirector_contracts import Scene
from demodirector_worker.presentation_assets import AuthoredSlideRenderer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("slides", type=int, nargs="+")
    parser.add_argument("--run-name", default="")
    args = parser.parse_args()
    project_id = "3a0ab083-5be1-442e-a4c6-b0e594d5d4d0"
    url = "https://veyframe-web-5zo4cenn3q-uc.a.run.app/"
    reviewed = load_reviewed_profile(url, project_id, Path("artifacts"))
    assert reviewed
    profile = reviewed.recipes
    root = Path("artifacts/veyframe-self-demo") / f"outer-scene-checks-{reviewed.template_theme}"
    if args.run_name:
        assert args.run_name.isalnum()
        root = root / args.run_name
    renderer = AuthoredSlideRenderer(root, theme=reviewed.template_theme)
    prepare = renderer.prepare_page

    def traced_prepare(page, *steps, **options):
        def response_status(response):
            path = urlsplit(response.url).path
            if path == "/api/auth/session" or response.status >= 400:
                print(f"HTTP {response.status}: {path}", flush=True)
        page.on("response", response_status)
        page.on("framenavigated", lambda frame: print(
            f"Page: {urlsplit(frame.url).path}", flush=True
        ) if frame == page.main_frame else None)
        return prepare(page, *steps, **options)

    renderer.prepare_page = traced_prepare
    for number in args.slides:
        assert 2 <= number <= 8
        receipt = root / f"slide-{number}.json"
        if receipt.exists():
            print(f"Slide {number} already recorded; review its saved receipt", flush=True)
            continue
        recipe = profile[f"slide-{number}"]
        timing = renderer.pack["schedule"][number - 1]
        duration = timing["end_ms"] - timing["start_ms"]
        template = next(t for t in renderer.pack["templates"] if t["id"] == timing["template_id"])
        scene = Scene.model_validate({
            "id": f"self-demo-{number}", "storyboard_id": project_id, "order": number - 1,
            "title": "Self-demo capture verification", "objective": "Verify reviewed UI actions",
            "narration": "Diagnostic recording only", "duration_seconds": duration / 1000,
            "capture_plan": {"start_url": url, "timeout_seconds": 180,
                             "actions": recipe.actions},
        })
        print(f"Checking slide {number}", flush=True)
        path, result = renderer.capture(
            scene, duration, template, preparation=recipe.preparation,
            on_progress=lambda message: print(message, flush=True),
        )
        assert result.status == "succeeded" and result.interaction_events
        receipt.write_text(result.model_dump_json(indent=2), "utf-8")
        print(f"PASS slide {number}: {path}", flush=True)


if __name__ == "__main__":
    main()
