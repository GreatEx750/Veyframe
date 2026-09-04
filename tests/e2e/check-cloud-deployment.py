from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test a deployed DemoDirector web origin.")
    parser.add_argument("web_url")
    args = parser.parse_args()
    origin = args.web_url.rstrip("/")

    summary: dict[str, object] = {}
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        root = client.get(origin)
        root.raise_for_status()
        summary["root_status"] = root.status_code

        video = client.get(f"{origin}/judge-demo.mp4")
        video.raise_for_status()
        with tempfile.TemporaryDirectory(prefix="demodirector-cloud-smoke-") as directory:
            video_path = Path(directory) / "judge-demo.mp4"
            video_path.write_bytes(video.content)
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        summary["demo_video_bytes"] = len(video.content)
        summary["demo_video_seconds"] = round(float(probe.stdout.strip()), 3)

        login = client.post(f"{origin}/api/auth/judge-session", json={})
        login.raise_for_status()
        login_payload = login.json()
        summary["judge_login_status"] = login.status_code
        summary["judge_landing_path"] = login_payload["landing_path"]

        session = client.get(f"{origin}/api/auth/session")
        session.raise_for_status()
        session_payload = session.json()
        user = session_payload.get("user", session_payload.get("session", {}).get("user", {}))
        summary["session_role"] = user.get("role")

        projects = client.get(f"{origin}/api/projects")
        projects.raise_for_status()
        project_payload = projects.json()
        project = project_payload[0]
        project_id = project["id"]
        summary["project_count"] = len(project_payload)
        summary["project_id"] = project_id

        storyboard = client.get(f"{origin}/projects/{project_id}/storyboard")
        storyboard.raise_for_status()
        editor = client.get(f"{origin}/projects/{project_id}/editor")
        editor.raise_for_status()
        summary["storyboard_status"] = storyboard.status_code
        summary["editor_status"] = editor.status_code

        provenance = client.get(f"{origin}/api/runtime/provenance")
        provenance.raise_for_status()
        summary["provenance_status"] = provenance.status_code

        forbidden = client.post(f"{origin}/api/projects/{project_id}/generate", json={})
        if forbidden.status_code != 403:
            raise AssertionError(
                f"Judge mutation should be read-only, got {forbidden.status_code}: "
                f"{forbidden.text[:200]}"
            )
        summary["judge_generate_status"] = forbidden.status_code

        logout = client.post(f"{origin}/api/auth/logout", json={})
        logout.raise_for_status()
        summary["logout_status"] = logout.status_code

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
