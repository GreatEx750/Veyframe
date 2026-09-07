"""Create the first-five-slide Wikipedia preview using the real local Studio."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT = Path("artifacts/presentation-ui-smoke").resolve()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1600, "height": 1100})
        assert context.request.post("http://localhost:3000/api/auth/judge-session").status == 200
        page = context.new_page()
        if "--resume" in sys.argv:
            project_id = json.loads((OUTPUT / "project.json").read_text("utf-8"))["project_id"]
            page.goto(f"http://localhost:3000/projects/{project_id}/generation?preview=first-five",
                      wait_until="networkidle")
            page.get_by_role("button", name="Approve retry", exact=True).click()
        else:
            page.goto("http://localhost:3000/studio", wait_until="networkidle")
            page.get_by_label("Website URL", exact=False).fill("https://www.wikipedia.org/")
            page.get_by_label("Demo title", exact=False).fill("Wikipedia exploration — five slides")
            page.get_by_label("Describe your video", exact=False).fill(
                "Create a Wikipedia presentation. Show searching for Solar System, navigating its "
                "table of contents, and following the Earth article. Keep each slide focused on "
                "the recorded interaction, with clear narration and visible mouse clicks."
            )
            page.get_by_label("Target Audience", exact=True).select_option(label="Product leaders")
            page.get_by_label("Call to Action", exact=True).fill("Explore Wikipedia")
            page.get_by_role("radio", name="Presentation Demo", exact=True).check()
            page.get_by_role("checkbox", name="Preview first five slides (about 1 minute)").check()
            page.screenshot(path=str(OUTPUT / "studio-before-generation.png"), full_page=True)
            page.get_by_role("button", name="Create demo", exact=True).first.click()
            page.wait_for_url("**/jobs?job=*", timeout=60000)
            job_id = page.url.split("?job=")[1]
            jobs = context.request.get("http://localhost:3000/api/jobs").json()["jobs"]
            project_id = next(item["job"]["project_id"] for item in jobs if item["job"]["id"] == job_id)
            (OUTPUT / "project.json").write_text(json.dumps({"project_id": project_id}), "utf-8")
        print(f"Created through Studio: {project_id}", flush=True)
        url = f"http://localhost:3000/api/projects/{project_id}/generation/presentation-preview"
        previous = ""
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            response = context.request.get(url)
            assert response.status == 200
            job = response.json()
            if job["message"] != previous:
                print(job["message"], flush=True)
                previous = job["message"]
            if job["status"] in {"succeeded", "failed"}:
                break
            page.wait_for_timeout(5000)
        assert job["status"] == "succeeded", "Presentation job did not succeed"
        page.get_by_role("link", name="Play finished demo", exact=True).wait_for(timeout=15000)
        page.screenshot(path=str(OUTPUT / "completed-progress.png"), full_page=True)
        page.get_by_role("link", name="Play finished demo", exact=True).click()
        page.wait_for_function("document.querySelector('video')?.readyState >= 2", timeout=60000)
        assert page.locator("video").count() == 1
        page.locator("video").evaluate("video => { video.muted = true; }")
        page.get_by_label("Timeline playhead", exact=True).fill("39000")
        page.get_by_role("button", name="Play preview", exact=True).click()
        page.wait_for_function("document.querySelector('video').currentTime > 40", timeout=20000)
        page.get_by_role("button", name="Pause preview", exact=True).click()
        playback = page.locator("video").evaluate(
            "v => ({width:v.videoWidth,height:v.videoHeight,duration:v.duration,time:v.currentTime,error:v.error})"
        )
        assert playback["width"] == 2560 and playback["height"] == 1440
        assert playback["duration"] == 61 and playback["error"] is None
        page.screenshot(path=str(OUTPUT / "editor-playback.png"), full_page=True)
        exports = f"http://localhost:3000/api/projects/{project_id}/exports/latest"
        export = context.request.get(exports).json()
        assert export["id"] == job["export_id"]
        assert (
            context.request.get(exports + "/video", headers={"Range": "bytes=0-1023"}).status == 206
        )
        assert project_id in context.request.get("http://localhost:3000/api/projects").text()
        (OUTPUT / "result.json").write_text(
            json.dumps(
                {"project_id": project_id, "job": job, "export": export, "playback": playback},
                indent=2,
            ),
            "utf-8",
        )
        print(
            "PASS: Studio launch, saved progress, export, library, range delivery and playback",
            flush=True,
        )
        browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Smoke stopped: {type(error).__name__}", flush=True)
        raise SystemExit(1) from None
