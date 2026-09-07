"""Check owner-authorized demo access from the actual cloud capture worker."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/contracts/python"))
from demodirector_contracts import Scene  # noqa: E402


def main() -> None:
    output = ROOT / "artifacts/veyframe-self-demo/roamstead-preflight"
    output.mkdir(parents=True, exist_ok=True)
    if (output / "result.json").exists():
        print((output / "result.json").read_text("utf-8"))
        return
    gcloud = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    if not gcloud:
        raise RuntimeError("Google Cloud CLI is required")
    token = subprocess.run(
        [gcloud, "auth", "print-identity-token"], capture_output=True, text=True, check=True,
    ).stdout.strip()
    scene = Scene.model_validate({
        "id": "roamstead-profile-preflight-20260906", "storyboard_id": "roamstead-preflight",
        "order": 0, "title": "Roamstead demo profile access check",
        "objective": "Verify demo access and an enabled profile before generating footage",
        "narration": "Cloud recording access check", "duration_seconds": 75,
        "capture_plan": {
            "start_url": "https://roamstead-web-tn7ddsxnmq-uc.a.run.app/",
            "timeout_seconds": 150,
            "actions": [
                {"type": "click", "locator_strategy": "role",
                 "locator": "button:Explore with demo access", "description": "Open demo profile"},
                {"type": "wait_for", "value": 60000,
                 "description": "Allow the demo profile to initialize"},
            ],
            "success_assertions": [{
                "type": "assert_visible", "locator_strategy": "css",
                "locator": 'select[aria-label="Choose city"]:enabled',
                "description": "Confirm the destination selector is ready",
            }],
        },
    })
    response = httpx.post(
        "https://veyframe-worker-5zo4cenn3q-uc.a.run.app/tasks/capture",
        headers={"Authorization": "Bearer " + token},
        json={"project_id": "veyframe-self-demo-preflight", "scene": scene.model_dump(mode="json")},
        timeout=180,
    )
    response.raise_for_status()
    result = response.json()
    (output / "result.json").write_text(json.dumps(result, indent=2), "utf-8")
    print(json.dumps(result, indent=2), flush=True)
    for index, uri in enumerate(result["artifact_uris"]):
        if uri.startswith("gs://") and uri.endswith((".png", ".webm", ".mp4")):
            destination = output / f"capture-{index}{Path(uri).suffix}"
            subprocess.run([gcloud, "storage", "cp", uri, str(destination)], check=True)


if __name__ == "__main__":
    main()
