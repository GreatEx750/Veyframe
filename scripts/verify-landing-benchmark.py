"""Verify and capture the successful-attempt benchmark without generating videos."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main() -> None:
    output = Path("artifacts/landing-benchmark")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1100})
        page.goto("http://localhost:3000/#benchmark", wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        section = page.locator("#benchmark")
        for label in ["8m 55s", "2m 22s", "3m 31s", "1h 46m 5s less", "36m 29s less"]:
            assert label in section.inner_text(), label
        assert section.get_by_text("Resumed attempt · cached work").is_visible()
        section.screenshot(path="docs/images/benchmark.png")
        section.screenshot(path=str(output / "desktop.png"))
        page.get_by_role("button", name="Short details").click()
        assert page.get_by_role("region", name="Short methodology").is_visible()
        section.screenshot(path=str(output / "details.png"))
        page.get_by_role("button", name="Short details").click()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        section.scroll_into_view_if_needed()
        page.screenshot(path=str(output / "mobile.png"))
        response = page.request.get("http://localhost:3000/benchmarks/generation-2026-09-06.json")
        assert response.ok
        assert response.json()["runs"][3]["startedAt"] == "2026-09-06T16:11:05.299951Z"
        browser.close()
    (output / "verification.json").write_text(json.dumps({
        "successful_attempts_only": True, "resumed_label": True,
        "desktop": "passed", "mobile_overflow": False,
        "shared_readme_devpost_image": "docs/images/benchmark.png",
    }, indent=2), encoding="utf-8")
    print("Benchmark values, desktop/mobile layout and documentation image verified.")


if __name__ == "__main__":
    main()
