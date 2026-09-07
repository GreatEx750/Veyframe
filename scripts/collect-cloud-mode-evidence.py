"""Read cloud-saved generation receipts for QA; never export session credentials."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import httpx


def decode(value):
    if "mapValue" in value:
        return {key: decode(item) for key, item in value["mapValue"].get("fields", {}).items()}
    if "arrayValue" in value:
        return [decode(item) for item in value["arrayValue"].get("values", [])]
    if "integerValue" in value:
        return int(value["integerValue"])
    return next(iter(value.values()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["spotlight", "short", "presentation"])
    parser.add_argument("--artifacts-root", type=Path, default=Path("artifacts/cloud-mode-smoke"))
    parser.add_argument("--frames", action="store_true")
    args = parser.parse_args()
    root = args.artifacts_root / args.mode
    project_id = json.loads((root / "project.json").read_text(encoding="utf-8"))["project_id"]
    executable = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    assert executable, "Google Cloud CLI unavailable"
    token = subprocess.run([executable, "auth", "print-access-token"], check=True, capture_output=True, text=True).stdout.strip()
    headers = {"Authorization": "Bearer " + token, "x-goog-user-project": "demodirector-507722"}
    with httpx.Client(headers=headers, timeout=90) as client:
        record = client.get("https://firestore.googleapis.com/v1/projects/demodirector-507722/databases/demodirector/documents/workflow_records/" + quote(f"presentation-full:{project_id}:checkpoint", safe=""))
        record.raise_for_status()
        state = decode(record.json()["fields"]["payload"])
        receipts = root / "receipts"
        receipts.mkdir(exist_ok=True)
        captures = []
        count = 0
        for name, entry in state["files"].items():
            wanted = name.endswith(".json") or (args.frames and (
                name.endswith("/composed.png") or name.endswith("/last-frame.png")
            ))
            if not wanted or ":" in name or ".." in Path(name).parts:
                continue
            destination = receipts / name
            if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == entry["sha256"]:
                continue
            blob_name = f"presentation-cache/{project_id}/full/{entry['sha256']}"
            blob = client.get("https://storage.googleapis.com/storage/v1/b/demodirector-507722-artifacts/o/" + quote(blob_name, safe=""), params={"alt":"media"})
            blob.raise_for_status()
            assert hashlib.sha256(blob.content).hexdigest() == entry["sha256"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(blob.content)
            count += 1
            if name.endswith("-capture.json"):
                capture = blob.json()
                captures.append({"file":name,"interactions":len(capture["interaction_events"]),"duration_ms":capture["duration_ms"],"status":capture["status"]})
        print(json.dumps({"saved_step":state["step"],"receipt_count":count,"captures":captures}, indent=2))


if __name__ == "__main__":
    main()
