"""Verify access to existing projects and media after the Cloud Run service rename."""

import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright


def main() -> None:
    output = Path("artifacts/cloud-veyframe")
    services = json.loads((output / "services.json").read_text("utf-8"))
    base = services["web"]["url"]
    previous = "https://demodirector-web-5zo4cenn3q-uc.a.run.app"
    summary = {"web_url": base, "checks": {}}
    checks = summary["checks"]
    with httpx.Client(timeout=120, follow_redirects=True) as old:
        old.post(previous + "/api/auth/judge-session", json={}).raise_for_status()
        existing = old.get(previous + "/api/projects")
        existing.raise_for_status()
        expected_ids = {item["id"] for item in existing.json()}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        auth = context.request.post(base + "/api/auth/judge-session", data={}, timeout=120000)
        assert auth.status == 200, f"Sign-in returned HTTP {auth.status}"
        checks["sign_in"] = "passed"
        session = context.request.get(base + "/api/auth/session")
        assert session.status == 200
        checks["session"] = "passed"
        projects = context.request.get(base + "/api/projects", timeout=120000)
        assert projects.status == 200
        actual_ids = {item["id"] for item in projects.json()}
        assert expected_ids.issubset(actual_ids), "Existing projects missing on the new origin"
        checks["existing_projects"] = {"preserved": len(expected_ids), "visible": len(actual_ids)}
        jobs = context.request.get(base + "/api/jobs")
        assert jobs.status == 200
        checks["job_status"] = "passed"
        page = context.new_page()
        page.goto(base + "/projects", wait_until="networkidle", timeout=120000)
        page.screenshot(path=str(output / "project-library.png"), full_page=True)
        samples = {
            "spotlight": Path("artifacts/cloud-new-key-smoke/spotlight/project.json"),
            "short": Path("artifacts/cloud-mode-smoke/short/project.json"),
            "presentation": Path("artifacts/cloud-new-key-smoke/presentation/project.json"),
        }
        for mode, record in samples.items():
            project_id = json.loads(record.read_text("utf-8"))["project_id"]
            assert project_id in actual_ids
            prefix = base + "/api/projects/" + project_id
            timeline = context.request.get(prefix + "/timeline", timeout=120000)
            assert timeline.status == 200, f"{mode} timeline HTTP {timeline.status}"
            media = context.request.get(prefix + "/exports/latest/video",
                                        headers={"Range": "bytes=0-1023"}, timeout=120000)
            assert media.status == 206, f"{mode} media HTTP {media.status}"
            checks[mode + "_saved_media"] = "passed"
            print(f"Verified {mode} project, timeline and media range delivery", flush=True)

        project_id = json.loads(samples["spotlight"].read_text("utf-8"))["project_id"]
        page.goto(base + f"/projects/{project_id}/editor", wait_until="domcontentloaded",
                  timeout=120000)
        page.wait_for_function("document.querySelector('video')?.readyState >= 2", timeout=120000)
        assert page.locator("video").count() == 1
        video = page.locator("video")
        video.evaluate("v => { v.muted = true; }")
        page.get_by_role("button", name="Play preview", exact=True).click()
        page.wait_for_function("document.querySelector('video').currentTime > 3", timeout=30000)
        page.get_by_role("button", name="Pause preview", exact=True).click()
        playback = video.evaluate(
            "v => ({width:v.videoWidth,height:v.videoHeight,time:v.currentTime,error:v.error})"
        )
        assert playback["error"] is None
        checks["browser_playback"] = playback
        page.screenshot(path=str(output / "saved-video-playback.png"), full_page=True)
        assert context.request.post(base + "/api/auth/logout", data={}).status == 200
        checks["logout"] = "passed"
        browser.close()

    with httpx.Client(timeout=120) as client:
        health = client.get(services["api"]["url"] + "/health")
        assert health.status_code == 200
        checks["api_health"] = "passed"
        private = client.get(services["worker"]["url"] + "/health")
        assert private.status_code in (401, 403)
        checks["worker_private"] = "passed"
    (output / "verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
