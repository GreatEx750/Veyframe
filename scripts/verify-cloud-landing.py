"""Verify the deployed landing page and existing judge library without generating jobs."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Private deployed web origin")
    base = parser.parse_args().base.rstrip("/")
    output = Path("artifacts/veyframe-self-demo/deployment")
    output.mkdir(parents=True, exist_ok=True)
    checks = {}
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1080})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base, wait_until="networkidle", timeout=90000)
        assert page.get_by_role("tab").first.inner_text() == "Presentations"
        assert page.get_by_role("button", name="Judge Demo Mode").is_visible()
        page.wait_for_function("document.querySelector('video')?.currentTime > .5")
        page.get_by_role("button", name="Pause preview", exact=True).click()
        checks["public_presentation_first"] = "passed"
        page.screenshot(path=str(output / "landing.png"), full_page=True)
        page.get_by_role("tab", name="Shorts", exact=True).click()
        page.wait_for_function("document.querySelector('video')?.readyState >= 2")
        assert "rounded-3" in page.locator("video").get_attribute("src")
        assert "rounded" in page.locator("video").get_attribute("poster")
        page.get_by_role("button", name="A little time", exact=False).click()
        page.wait_for_function("document.querySelector('dialog video')?.currentTime > .5")
        media = page.locator("dialog video").evaluate(
            "v => ({width:v.videoWidth,height:v.videoHeight,duration:v.duration,error:v.error})"
        )
        assert media["width"] == 720 and media["height"] == 1280
        assert 45 <= media["duration"] <= 45.1 and media["error"] is None
        checks["rounded_short"] = media
        page.keyboard.press("Escape")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(output / "landing-mobile.png"), full_page=True)
        page.get_by_role("button", name="Judge Demo Mode", exact=True).click()
        page.wait_for_url("**/projects", timeout=90000)
        projects = context.request.get(base + "/api/projects", timeout=90000)
        assert projects.status == 200
        ids = {item["id"] for item in projects.json()}
        expected = {"208f7496-2c97-4f69-956a-0e00989a7c59",
                    "3f2f0ae4-d63e-44a2-ad0c-4edeb69fa9e9",
                    "3d42a559-1577-4ab1-aaf0-c27d270412fb"}
        assert expected.issubset(ids)
        for project_id in expected:
            response = context.request.get(
                base + f"/api/projects/{project_id}/exports/latest/video",
                headers={"Range": "bytes=0-1023"}, timeout=90000,
            )
            assert response.status == 206
        checks["judge_library_existing_media"] = {"projects": len(ids), "media_checked": 3}
        page.set_viewport_size({"width": 1440, "height": 1080})
        page.get_by_role("link", name="Studio", exact=True).click()
        page.wait_for_url("**/studio")
        assert page.get_by_label("Demo title", exact=False).is_visible()
        checks["studio_route"] = "passed"
        assert not errors, errors
        checks["browser_errors"] = errors
        browser.close()
    (output / "verification.json").write_text(json.dumps(checks, indent=2), "utf-8")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
