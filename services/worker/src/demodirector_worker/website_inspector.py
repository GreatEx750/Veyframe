from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urljoin, urlsplit

from demodirector_contracts import InspectedElement, InspectedPage, WebsiteInspection
from playwright.sync_api import Browser, Locator, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

ElementKind = Literal["button", "link", "input", "select", "textarea"]


@dataclass(frozen=True, slots=True)
class InspectorSettings:
    max_pages: int = 3
    max_depth: int = 1
    timeout_ms: int = 10_000
    viewport_width: int = 1280
    viewport_height: int = 720

    def __post_init__(self) -> None:
        if self.max_pages <= 0:
            raise ValueError("max_pages must be positive")
        if self.max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")


class WebsiteInspector(Protocol):
    def inspect(self, *, project_id: str, website_url: str) -> WebsiteInspection: ...


class PlaywrightWebsiteInspector:
    def __init__(self, artifact_directory: Path, settings: InspectorSettings | None = None) -> None:
        self.artifact_directory = artifact_directory
        self.settings = settings or InspectorSettings()

    def inspect(self, *, project_id: str, website_url: str) -> WebsiteInspection:
        project_directory = self.artifact_directory / project_id
        project_directory.mkdir(parents=True, exist_ok=True)
        pages: list[InspectedPage] = []
        warnings: list[str] = []
        origin = _origin(website_url)
        queue: deque[tuple[str, int]] = deque([(website_url, 0)])
        visited: set[str] = set()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                while queue and len(pages) < self.settings.max_pages:
                    url, depth = queue.popleft()
                    normalized_url = _without_fragment(url)
                    if normalized_url in visited:
                        continue
                    visited.add(normalized_url)
                    page = self._new_page(browser)
                    try:
                        inspected, links = self._inspect_page(
                            page,
                            normalized_url,
                            project_directory / f"page-{len(pages) + 1}.png",
                        )
                    except PlaywrightTimeoutError:
                        warnings.append(f"Timed out while inspecting {normalized_url}")
                        page.close()
                        continue
                    pages.append(inspected)
                    page.close()
                    if depth < self.settings.max_depth:
                        for link in links:
                            if _origin(link) == origin and _without_fragment(link) not in visited:
                                queue.append((link, depth + 1))
            finally:
                browser.close()

        return WebsiteInspection(
            project_id=project_id,
            pages=pages,
            max_pages=self.settings.max_pages,
            max_depth=self.settings.max_depth,
            warning="; ".join(warnings) or None,
        )

    def _new_page(self, browser: Browser) -> Page:
        return browser.new_page(
            viewport={
                "width": self.settings.viewport_width,
                "height": self.settings.viewport_height,
            }
        )

    def _inspect_page(
        self,
        page: Page,
        url: str,
        screenshot_path: Path,
    ) -> tuple[InspectedPage, list[str]]:
        page.goto(url, wait_until="domcontentloaded", timeout=self.settings.timeout_ms)
        page.screenshot(path=str(screenshot_path), full_page=False)
        headings = _visible_texts(page.locator("h1, h2, h3"))
        elements = _visible_elements(page)
        viewport = page.evaluate(
            "() => ({scrollX: Math.max(0, window.scrollX), scrollY: Math.max(0, window.scrollY)})"
        )
        inspected = InspectedPage.model_validate(
            {
                "title": page.title(),
                "url": page.url,
                "headings": headings,
                "elements": [element.model_dump() for element in elements],
                "screenshot_path": str(screenshot_path),
                "viewport": {
                    "width": self.settings.viewport_width,
                    "height": self.settings.viewport_height,
                    "scroll_x": viewport["scrollX"],
                    "scroll_y": viewport["scrollY"],
                    "device_scale_factor": 1,
                },
            }
        )
        links = [element.href for element in elements if element.kind == "link" and element.href]
        return inspected, [urljoin(page.url, link) for link in links]


def _visible_texts(locator: Locator, limit: int = 100) -> list[str]:
    texts: list[str] = []
    for index in range(min(locator.count(), limit)):
        item = locator.nth(index)
        if item.is_visible():
            text = _clean(item.inner_text())
            if text:
                texts.append(text)
    return texts


def _visible_elements(page: Page, limit: int = 200) -> list[InspectedElement]:
    locator = page.locator("button, [role='button'], a[href], input, select, textarea")
    elements: list[InspectedElement] = []
    for index in range(min(locator.count(), limit)):
        item = locator.nth(index)
        if not item.is_visible():
            continue
        tag = item.evaluate("element => element.tagName.toLowerCase()")
        kind = _element_kind(tag, item.get_attribute("role"))
        label = _element_label(page, item)
        text = _clean(item.inner_text()) if tag not in {"input", "textarea"} else ""
        accessible_name = _clean(
            item.get_attribute("aria-label")
            or label
            or text
            or item.get_attribute("placeholder")
            or item.get_attribute("title")
            or ""
        )
        elements.append(
            InspectedElement(
                kind=kind,
                tag=tag,
                text=text,
                accessible_name=accessible_name,
                href=item.get_attribute("href") if kind == "link" else None,
                input_type=item.get_attribute("type") if kind == "input" else None,
                label=label or None,
            )
        )
    return elements


def _element_kind(tag: str, role: str | None) -> ElementKind:
    if tag == "a":
        return "link"
    if tag == "input":
        return "input"
    if tag == "select":
        return "select"
    if tag == "textarea":
        return "textarea"
    if tag == "button" or role == "button":
        return "button"
    raise ValueError(f"unsupported inspected element tag: {tag}")


def _element_label(page: Page, item: Locator) -> str:
    element_id = item.get_attribute("id")
    if element_id:
        labels = page.locator("label")
        for index in range(labels.count()):
            label = labels.nth(index)
            if label.get_attribute("for") == element_id:
                return _clean(label.inner_text())
    parent_label = item.locator("xpath=ancestor::label[1]")
    if parent_label.count():
        return _clean(parent_label.first.inner_text())
    return ""


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _without_fragment(url: str) -> str:
    parsed = urlsplit(url)
    return parsed._replace(fragment="").geturl()


def _clean(value: str) -> str:
    return " ".join(value.split())
