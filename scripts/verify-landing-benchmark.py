"""Read-only local browser checks for the public timing comparison."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    output = Path("artifacts/landing-benchmark")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1080}, reduced_motion="reduce")
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://localhost:3000/#benchmark", wait_until="networkidle")
        benchmark = page.locator("#benchmark")
        benchmark.scroll_into_view_if_needed()
        assert page.get_by_role("heading", name="Video production benchmark").is_visible()
        assert page.get_by_role("button", name="Presentation details").count() == 1
        assert page.get_by_text("1h 27m 52s less", exact=True).is_visible()
        assert page.get_by_text("27m 38s less", exact=True).is_visible()
        assert page.get_by_text("33m 19s less", exact=True).is_visible()
        benchmark.screenshot(path=str(output / "desktop.png"))
        page.get_by_role("button", name="Presentation details").click()
        assert page.get_by_role("region", name="Presentation methodology").is_visible()
        benchmark.screenshot(path=str(output / "details.png"))
        assert benchmark.get_by_role("spinbutton").count() == 0
        assert benchmark.get_by_role("button", name="Reset estimates").count() == 0
        for minutes in (60, 120, 35, 45):
            assert benchmark.get_by_role("cell", name=f"{minutes} min", exact=True).is_visible()
        assert benchmark.get_by_role("combobox").count() == 0
        assert benchmark.get_by_text("6 Sep 2026", exact=False).count() == 0
        for label in ("Product Demo", "Presentation", "Spotlight", "Short"):
            assert benchmark.get_by_role("button", name=f"{label} details").is_visible()
        page.get_by_role("button", name="Product Demo details").click()
        assert page.get_by_role("region", name="Product Demo methodology").is_visible()
        assert benchmark.get_by_role(
            "cell", name="Not measured No matched timing record", exact=True,
        ).is_visible()
        page.get_by_role("button", name="Product Demo details").click()
        response = page.request.get("http://localhost:3000/benchmarks/generation-2026-09-06.json")
        assert response.ok and len(response.json()["runs"]) == 4
        assert response.json()["runs"][0]["startedAt"] is None
        assert response.json()["runs"][0]["outputSeconds"] == 90
        assert response.json()["runs"][0]["manualMinutes"] == 60
        assert benchmark.get_by_text("90-second video", exact=True).is_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        benchmark.scroll_into_view_if_needed()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        table_region = page.get_by_role("region", name="Scrollable benchmark comparison")
        assert table_region.evaluate("e => e.scrollWidth > e.clientWidth")
        page.screenshot(path=str(output / "mobile.png"))
        table_region.focus()
        page.keyboard.press("End")
        page.get_by_text("33m 19s less", exact=True).scroll_into_view_if_needed()
        assert page.get_by_text("33m 19s less", exact=True).is_visible()
        assert benchmark.get_by_role("spinbutton").count() == 0
        assert not errors, errors
        browser.close()
    result = {
        "desktop": "passed", "mobile_no_page_overflow": "passed", "scrollable_table": "passed",
        "fixed_estimates": "passed", "no_edit_or_reset_controls": "passed",
        "all_four_formats": "passed", "no_date_or_filter_toolbar": "passed",
        "unmeasured_product_timing": "passed",
        "details": "passed", "public_timing_data": "passed", "browser_errors": errors,
    }
    (output / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
