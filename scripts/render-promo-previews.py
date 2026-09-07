"""Render portrait template specimens with the same Inter font used by video exports."""

import base64
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    pack = Path(sys.argv[1]).resolve()
    font = base64.b64encode((pack / "shared/inter-latin-variable.woff2").read_bytes()).decode()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 432, "height": 768})
        for source in sorted((pack / "slides").glob("*/source.svg")):
            artwork = source.read_text("utf-8").replace(
                'font-family="sans-serif"', 'font-family="Inter"'
            )
            page.set_content(
                '<!doctype html><meta charset="utf-8"><style>'
                f"@font-face{{font-family:Inter;src:url(data:font/woff2;base64,{font});}}"
                "body{margin:0}svg{display:block;width:432px;height:768px}</style>" + artwork
            )
            page.evaluate("async () => { await document.fonts.ready; }")
            page.screenshot(path=str(source.with_name("preview.png")))
        browser.close()


if __name__ == "__main__":
    main()
