from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 2560, "height": 1440})
    for url in [
        "https://en.wikipedia.org/wiki/Solar_System",
        "https://en.wikipedia.org/wiki/Earth",
    ]:
        page.goto(url, wait_until="domcontentloaded")
        print(
            json.dumps(
                {
                    "url": page.url,
                    "title": page.title(),
                    "contents": [
                        {"text": item.inner_text(), "href": item.get_attribute("href")}
                        for item in page.locator("#vector-toc a").all()[:14]
                    ],
                    "earth_links": page.locator('#mw-content-text a[title="Earth"]').count(),
                }
            ),
            flush=True,
        )
    browser.close()
