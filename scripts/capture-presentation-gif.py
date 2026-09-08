"""Capture a short silent Presentation Demo excerpt for documentation."""

from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "apps/web/public/examples/roamstead-presentation-120s.mp4"
OUTPUT = ROOT / "docs/images/presentation-demo.gif"


def main() -> None:
    frames: list[Image.Image] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 640, "height": 360}, device_scale_factor=1)
        page.goto(VIDEO.as_uri(), wait_until="load")
        page.locator("video").evaluate(
            "video => { video.muted = true; "
            "video.removeAttribute('controls'); video.currentTime = 10; }"
        )
        page.wait_for_timeout(500)
        for index in range(20):
            timestamp = 10 + index / 4
            page.locator("video").evaluate(
                "(video, time) => { video.currentTime = time; }", timestamp
            )
            page.wait_for_timeout(35)
            path = ROOT / "artifacts" / "presentation-gif-frame.png"
            page.screenshot(path=str(path), animations="disabled")
            frames.append(Image.open(path).convert("RGB"))
        browser.close()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUTPUT, save_all=True, append_images=frames[1:], duration=250, loop=0, optimize=True
    )
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
