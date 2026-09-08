"""Observe hosted controls for the reviewed self-demo walkthrough, without generation."""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Private deployed web origin")
    base = parser.parse_args().base.rstrip("/")
    root = Path("artifacts/veyframe-self-demo/recording-ui")
    root.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1502, "height": 1022})
        page = context.new_page()
        page.goto(base, wait_until="networkidle", timeout=90000)
        page.get_by_role("button", name="Judge Demo Mode", exact=True).click()
        page.wait_for_url("**/projects", timeout=90000)
        for name, path in [
            ("projects", "/projects"), ("studio", "/studio"),
            ("jobs", "/jobs?job=b3ec9c6e-4c48-4493-a823-058d286dce74"),
        ]:
            page.goto(base + path, wait_until="networkidle", timeout=90000)
            root.joinpath(f"{name}.txt").write_text(page.locator("body").aria_snapshot(), "utf-8")
            page.screenshot(path=str(root / f"{name}.png"), full_page=True)
            print(f"Observed {name}", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
