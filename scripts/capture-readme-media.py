"""Capture real local UI for documentation without submitting a generation job."""

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/images"
BRIEF = (
    "Introduce Wikipedia to a first-time reader. Search for Solar System, explore "
    "the article's Formation and evolution and General characteristics sections, "
    "then follow the Earth link. Show visible mouse movement and clicks, smooth "
    "zooms, clear narration, and highlighted captions. End with Explore Wikipedia."
)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1600, "height": 1000}, reduced_motion="reduce",
        )
        page.goto("http://localhost:3000", wait_until="networkidle")
        page.locator("#benchmark").screenshot(path=str(OUTPUT / "benchmark.png"))
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(OUTPUT / "landing.png"))
        page.get_by_role("button", name="Judge Demo Mode", exact=True).click()
        page.wait_for_url("**/projects", timeout=90000)
        page.get_by_label("Search demos", exact=True).fill("Wikipedia")
        page.get_by_label("Filter by status", exact=True).select_option("published")
        page.wait_for_function("document.querySelector('video')?.readyState >= 2")
        page.wait_for_function("!document.querySelector('video')?.seeking")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUTPUT / "projects.png"))
        page.goto("http://localhost:3000/studio", wait_until="networkidle")
        page.get_by_label("Demo title", exact=False).fill("Wikipedia — presentation test")
        page.get_by_label("Website URL", exact=False).fill("https://www.wikipedia.org/")
        page.get_by_label("Describe your video", exact=False).fill(BRIEF)
        page.get_by_label("Target Audience", exact=True).select_option(label="Product leaders")
        page.get_by_label("Call to Action", exact=True).fill("Explore Wikipedia")
        page.get_by_role("radio", name="Presentation Demo", exact=True).check()
        page.get_by_label("Demo title", exact=False).scroll_into_view_if_needed()
        page.screenshot(path=str(OUTPUT / "studio.png"))
        page.goto(
            "http://localhost:3000/projects/dd910b44-0420-43c4-9e75-21f2aaadfb3e/editor",
            wait_until="networkidle",
        )
        page.wait_for_function("document.querySelector('video')?.readyState >= 2")
        page.locator("video").first.evaluate("v => {v.pause();v.currentTime=8;}")
        page.wait_for_function("!document.querySelector('video')?.seeking")
        page.screenshot(path=str(OUTPUT / "editor.png"))
        browser.close()
    print("Saved real UI screenshots; no generation job submitted.")


if __name__ == "__main__":
    main()
