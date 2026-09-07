"""Check the public homepage, real video examples, mobile layout and Studio access."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    output = Path("artifacts/landing-verification")
    output.mkdir(parents=True, exist_ok=True)
    base = "http://localhost:3000"
    results = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1080})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base, wait_until="networkidle")
        assert page.url == base + "/"
        assert page.get_by_role("tab").first.inner_text() == "Presentations"
        first_tab = page.get_by_role("tab", name="Presentations")
        assert first_tab.get_attribute("aria-selected") == "true"
        assert page.get_by_role("button", name="Judge Demo Mode").is_visible()
        assert page.get_by_role("heading", level=1).inner_text().startswith("Turn what you do")
        page.wait_for_function("document.querySelector('video').currentTime > 1")
        page.get_by_role("button", name="Pause preview", exact=True).click()
        page.screenshot(path=str(output / "desktop.png"), full_page=True)
        results["public_homepage"] = "passed"

        for label in ["Presentations", "Spotlights", "Shorts", "Product demos"]:
            page.get_by_role("tab", name=label, exact=True).click()
            page.wait_for_function("document.querySelector('video').readyState >= 2")
            video = page.locator("video").first
            assert video.evaluate("v => v.videoWidth") == (720 if label == "Shorts" else 1280)
            assert video.evaluate("v => v.videoHeight") == (1280 if label == "Shorts" else 720)
            assert video.evaluate("v => v.paused")
        results["four_previews_and_pause_persistence"] = "passed"
        page.get_by_role("button", name="Play preview", exact=True).click()
        page.wait_for_function(
            "document.querySelector('[role=tab][aria-selected=true]')?.textContent "
            "=== 'Spotlights'",
            timeout=15000,
        )
        page.get_by_role("button", name="Pause preview", exact=True).click()
        page.get_by_role("tab", name="Product demos", exact=True).click()
        results["automatic_format_rotation"] = "passed"
        page.get_by_role("button", name="See a product story", exact=False).click()
        modal = page.get_by_role("dialog")
        assert modal.is_visible()
        page.wait_for_function("document.querySelector('dialog video')?.currentTime > 1")
        assert page.locator("dialog video").evaluate("v => !v.muted")
        page.keyboard.press("Escape")
        assert not modal.is_visible()
        page.locator("dialog video").wait_for(state="detached")
        results["narrated_example_dialog"] = "passed"

        page.get_by_role("tab", name="Shorts", exact=True).click()
        page.screenshot(path=str(output / "short-desktop.png"), full_page=True)
        page.get_by_role("button", name="A little time", exact=False).click()
        page.wait_for_function("document.querySelector('dialog video')?.currentTime > 1")
        short = page.locator("dialog video")
        assert short.evaluate("v => v.videoHeight / v.videoWidth") == 16 / 9
        assert 45 <= short.evaluate("v => v.duration") <= 45.2
        assert short.evaluate("v => !v.muted && !v.error")
        page.keyboard.press("Escape")
        results["new_portrait_short_playback"] = "passed"

        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        results["mobile_overflow"] = "passed"
        page.get_by_role("link", name="Get started", exact=True).click()
        page.wait_for_url("**/signup")
        page.goto(base)
        page.get_by_role("link", name="Log in", exact=True).click()
        page.wait_for_url("**/login")
        results["account_links"] = "passed"

        reduced = browser.new_context(reduced_motion="reduce")
        still = reduced.new_page()
        still.goto(base, wait_until="networkidle")
        assert still.locator("video").evaluate("v => v.paused && v.currentTime === 0")
        still.get_by_role("button", name="Play preview", exact=True).click()
        still.wait_for_function("document.querySelector('video').currentTime > .5")
        results["reduced_motion_with_manual_play"] = "passed"
        reduced.close()

        page.goto(base, wait_until="networkidle")
        page.get_by_role("button", name="Judge Demo Mode", exact=True).click()
        page.wait_for_url("**/projects", timeout=120000)
        results["judge_demo_button"] = "passed"
        page.get_by_text("Wikipedia — Blue and coral Short", exact=True).wait_for()
        results["new_short_in_judge_library"] = "passed"
        page.get_by_role("link", name="Studio", exact=True).click()
        page.wait_for_url("**/studio")
        assert page.get_by_label("Demo title", exact=False).is_visible()
        assert page.get_by_role("button", name="Create demo", exact=True).is_visible()
        results["authenticated_studio_navigation"] = "passed"
        assert not errors, errors
        results["browser_errors"] = errors
        browser.close()
    (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
