"""Inspect existing cloud projects and editor controls; never submit generation."""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    base = "https://veyframe-web-5zo4cenn3q-uc.a.run.app"
    output = Path("artifacts/veyframe-self-demo/cloud-inspection")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        assert context.request.post(base + "/api/auth/judge-session").status == 200
        projects = context.request.get(base + "/api/projects").json()
        jobs = context.request.get(base + "/api/jobs").json()
        (output / "projects.json").write_text(json.dumps(projects, indent=2), "utf-8")
        (output / "jobs.json").write_text(json.dumps(jobs, indent=2), "utf-8")
        print(json.dumps([{"id": p["id"], "name": p.get("name"),
                           "mode": p.get("demo_mode")} for p in projects], indent=2))
        for route in ["quality-api/source-contributions", "generation/trace"]:
            response = context.request.get(
                base + "/api/projects/3f2f0ae4-d63e-44a2-ad0c-4edeb69fa9e9/" + route,
                timeout=90000,
            )
            print(f"CHECK {route}: HTTP {response.status}", flush=True)
            if response.status >= 400:
                print(response.text()[:600], flush=True)
        page = context.new_page()
        page.on("response", lambda response: print(
            f"HTTP {response.status} {response.url.split('?')[0]}", flush=True
        ) if response.status >= 400 else None)
        page.goto(base + "/projects/3f2f0ae4-d63e-44a2-ad0c-4edeb69fa9e9/editor",
                  wait_until="networkidle", timeout=90000)
        (output / "editor.txt").write_text(page.locator("body").aria_snapshot(), "utf-8")
        print(page.locator("body").aria_snapshot(), flush=True)
        page.get_by_role("button", name="Sources", exact=True).click()
        page.wait_for_load_state("networkidle")
        page.get_by_text("Loading saved evidence and runtime details", exact=False).wait_for(
            state="hidden", timeout=90000
        )
        (output / "sources.txt").write_text(page.locator("body").aria_snapshot(), "utf-8")
        print("SOURCES", flush=True)
        print(page.locator("body").aria_snapshot(), flush=True)
        browser.close()


if __name__ == "__main__":
    main()
