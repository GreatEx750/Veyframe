"""Check Google pages in the authenticated cloud recording worker, without bypasses."""

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
    output = ROOT / "artifacts/veyframe-self-demo/google-preflight"
    output.mkdir(parents=True, exist_ok=True)
    verdict = output / "verdict.json"
    if verdict.exists():
        print(verdict.read_text("utf-8"))
        return
    gcloud = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    if not gcloud:
        raise RuntimeError("Google Cloud CLI is required")
    token = subprocess.run(
        [gcloud, "auth", "print-identity-token"], capture_output=True, text=True, check=True,
    ).stdout.strip()
    worker = "https://veyframe-worker-5zo4cenn3q-uc.a.run.app"
    for name, url in [("home", "https://www.google.com/"),
                      ("ai-mode", "https://www.google.com/ai")]:
        scene = Scene.model_validate({
            "id": f"google-{name}-preflight-20260906", "storyboard_id": "google-preflight",
            "order": 0, "title": f"Google {name} access check",
            "objective": "Inspect the actual page delivered to the cloud recorder",
            "narration": "Cloud recording access check", "duration_seconds": 6,
            "capture_plan": {"start_url": url, "timeout_seconds": 30,
                             "actions": [{"type": "wait_for", "value": 5000,
                                          "description": "Allow the page to settle"}],
                             "success_assertions": []},
        })
        response = httpx.post(
            worker + "/tasks/capture", headers={"Authorization": "Bearer " + token},
            json={
                "project_id": "veyframe-self-demo-preflight",
                "scene": scene.model_dump(mode="json"),
            },
            timeout=90,
        )
        response.raise_for_status()
        result = response.json()
        (output / f"{name}.json").write_text(json.dumps(result, indent=2), "utf-8")
        print(json.dumps({"page": name, **result}), flush=True)
        for index, uri in enumerate(result["artifact_uris"]):
            if not uri.startswith("gs://") or not uri.endswith((".png", ".webm", ".mp4")):
                continue
            destination = output / f"{name}-{index}{Path(uri).suffix}"
            subprocess.run([gcloud, "storage", "cp", uri, str(destination)], check=True)


if __name__ == "__main__":
    main()
