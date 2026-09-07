"""Inspect the owner-authorized Roamstead demo without modifying existing projects."""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path("artifacts/veyframe-self-demo/roamstead-inspection")
    root.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("response", lambda response: print(
            f"HTTP {response.status} {response.url.split('?')[0]}", flush=True
        ) if response.status >= 400 else None)
        page.on("requestfailed", lambda request: print(
            f"FAILED {request.url.split('?')[0]} {request.failure}", flush=True
        ))
        page.goto("https://roamstead-web-tn7ddsxnmq-uc.a.run.app/", timeout=90000)
        page.get_by_role("button", name="Explore with demo access").click()
        page.get_by_text("What does the right home look like?", exact=True).wait_for(timeout=90000)
        try:
            page.locator('select[aria-label="Choose city"]:enabled').wait_for(timeout=120000)
        except Exception:
            page.screenshot(path=str(root / "profile-failure.png"), full_page=True)
            print(page.locator("body").aria_snapshot(), flush=True)
            raise
        page.screenshot(path=str(root / "profile.png"), full_page=True)
        print(page.locator("body").aria_snapshot(), flush=True)
        fields = page.locator("input,select,button").evaluate_all(
            "els => els.map(e => ({tag:e.tagName,type:e.type,name:e.name,id:e.id,"
            "text:e.innerText,value:e.value,aria:e.getAttribute('aria-label')}))"
        )
        (root / "profile-controls.json").write_text(json.dumps(fields, indent=2), "utf-8")
        print(json.dumps(fields, indent=2), flush=True)
        page.get_by_role("button", name="Show my matches", exact=True).click(timeout=30000)
        page.get_by_role("heading", name="Properties matched to your profile").wait_for(
            timeout=120000
        )
        page.get_by_role("button", name="View property", exact=True).first.wait_for(timeout=120000)
        try:
            page.get_by_text("Locating source addresses", exact=False).wait_for(
                state="hidden", timeout=180000
            )
        except Exception:
            page.screenshot(path=str(root / "map-loading-failure.png"), full_page=True)
            (root / "map-loading-failure.txt").write_text(
                page.locator("body").aria_snapshot(), "utf-8"
            )
            raise
        page.screenshot(path=str(root / "workspace.png"), full_page=True)
        print("WORKSPACE " + page.url, flush=True)
        (root / "workspace.txt").write_text(page.locator("body").aria_snapshot(), "utf-8")
        print(page.locator("body").aria_snapshot(), flush=True)
        (root / "workspace.html").write_text(page.content(), "utf-8")
        page.get_by_role("button", name="Satellite", exact=True).click()
        page.get_by_role("button", name="Normal", exact=True).click()
        page.get_by_role("button", name="View property", exact=True).first.click()
        page.get_by_role("heading", name="Why it fits your profile").wait_for(timeout=30000)
        page.screenshot(path=str(root / "property.png"), full_page=True)
        (root / "property.txt").write_text(page.locator("body").aria_snapshot(), "utf-8")
        print("PASS: map ready, listings visible, map types and property details", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
