from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from demodirector_contracts import (
    BoundingBox,
    CaptureAction,
    CaptureActionResult,
    InteractionEvent,
    Scene,
    SceneCaptureResult,
    Viewport,
)
from playwright.sync_api import Browser, BrowserContext, Error, Locator, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


class CaptureExecutionError(RuntimeError):
    """Raised when a deterministic capture action cannot be executed safely."""


@dataclass(frozen=True, slots=True)
class CaptureSettings:
    viewport_width: int = 2560
    viewport_height: int = 1440
    allowed_upload_directory: Path | None = None
    authenticated_origins: tuple[str, ...] = ()


class PlaywrightCaptureWorker:
    def __init__(self, artifact_directory: Path, settings: CaptureSettings | None = None) -> None:
        self.artifact_directory = artifact_directory
        self.settings = settings or CaptureSettings()

    def capture_scene(
        self,
        scene: Scene,
        *,
        session_token: str | None = None,
    ) -> SceneCaptureResult:
        scene_directory = self.artifact_directory / scene.id
        video_directory = scene_directory / "video"
        scene_directory.mkdir(parents=True, exist_ok=True)
        video_directory.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        action_results: list[CaptureActionResult] = []
        interaction_events: list[InteractionEvent] = []
        logs: list[str] = []
        screenshots: list[str] = []
        raw_clip_path: str | None = None
        status: Literal["succeeded", "failed"]

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = self._new_context(
                browser,
                video_directory,
                start_url=str(scene.capture_plan.start_url),
                session_token=session_token,
            )
            page = context.new_page()
            video = page.video
            timeout_ms = scene.capture_plan.timeout_seconds * 1_000
            page.set_default_timeout(timeout_ms)
            try:
                page.goto(
                    str(scene.capture_plan.start_url),
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                for index, action in enumerate(scene.capture_plan.actions):
                    self._enforce_deadline(started, timeout_ms)
                    action_started = time.monotonic()
                    try:
                        if action.type in {"click", "fill", "select"}:
                            interaction_events.append(
                                self._record_interaction(page, action, started)
                            )
                        self._execute(page, action)
                        if action.type == "scroll":
                            interaction_events.append(
                                self._record_interaction(page, action, started)
                            )
                    except Exception:
                        action_results.append(
                            CaptureActionResult(
                                action_index=index,
                                action_type=action.type,
                                status="failed",
                                elapsed_ms=_elapsed_ms(action_started),
                                message=f"{action.description} failed",
                            )
                        )
                        raise
                    action_results.append(
                        CaptureActionResult(
                            action_index=index,
                            action_type=action.type,
                            status="succeeded",
                            elapsed_ms=_elapsed_ms(action_started),
                            message=f"{action.description} completed",
                        )
                    )
                    logs.append(f"Action {index + 1}: {action.description}")

                for assertion in scene.capture_plan.success_assertions:
                    self._enforce_deadline(started, timeout_ms)
                    self._execute(page, assertion)
                status = "succeeded"
                retryable = False
                error_message = None
            except (CaptureExecutionError, PlaywrightTimeoutError, Error) as error:
                failure_path = scene_directory / "failure.png"
                try:
                    page.screenshot(path=str(failure_path), full_page=False)
                    screenshots.append(str(failure_path))
                except Error:
                    logs.append("The browser closed before a failure screenshot could be saved.")
                status = "failed"
                retryable = True
                error_message = _clear_error(error)
                logs.append(error_message)
            finally:
                page.close()
                context.close()
                if video is not None:
                    raw_clip_path = str(video.path())
                browser.close()

        return SceneCaptureResult(
            scene_id=scene.id,
            status=status,
            retryable=retryable,
            duration_ms=_elapsed_ms(started),
            raw_clip_path=raw_clip_path,
            screenshot_paths=screenshots,
            action_results=action_results,
            interaction_events=interaction_events,
            logs=logs,
            error=error_message,
        )

    def _new_context(
        self,
        browser: Browser,
        video_directory: Path,
        *,
        start_url: str,
        session_token: str | None,
    ) -> BrowserContext:
        context = browser.new_context(
            viewport={
                "width": self.settings.viewport_width,
                "height": self.settings.viewport_height,
            },
            record_video_dir=str(video_directory),
            record_video_size={
                "width": self.settings.viewport_width,
                "height": self.settings.viewport_height,
            },
        )
        origin = _origin(start_url)
        allowed_origins = {_origin(item) for item in self.settings.authenticated_origins}
        if session_token and origin in allowed_origins:
            context.add_cookies(
                [
                    {
                        "name": "demodirector_session",
                        "value": session_token,
                        "url": origin,
                        "httpOnly": True,
                        "secure": origin.startswith("https://"),
                        "sameSite": "Lax",
                    }
                ]
            )
        return context

    def _execute(self, page: Page, action: CaptureAction) -> None:
        if action.type == "navigate":
            target = action.value if isinstance(action.value, str) else action.locator
            if not target:
                raise CaptureExecutionError("Navigate action requires a target URL.")
            page.goto(target, wait_until="domcontentloaded")
            return
        if action.type == "scroll":
            if action.locator:
                _locator(page, action).scroll_into_view_if_needed()
            else:
                delta = action.value if isinstance(action.value, (int, float)) else 500
                page.mouse.wheel(0, float(delta))
            return
        if action.type == "wait_for":
            if action.locator:
                _locator(page, action).wait_for(state="visible")
            else:
                milliseconds = action.value if isinstance(action.value, (int, float)) else 250
                page.wait_for_timeout(float(milliseconds))
            return

        locator = _locator(page, action)
        if action.type == "click":
            locator.click()
        elif action.type == "fill":
            if not isinstance(action.value, str):
                raise CaptureExecutionError("Fill action requires a text value.")
            locator.fill(action.value)
        elif action.type == "select":
            if not isinstance(action.value, str):
                raise CaptureExecutionError("Select action requires an option value.")
            locator.select_option(action.value)
        elif action.type == "assert_visible":
            locator.wait_for(state="visible")
        elif action.type == "upload":
            if not isinstance(action.value, str):
                raise CaptureExecutionError("Upload action requires a fixture path.")
            locator.set_input_files(str(self._safe_upload_path(action.value)))
        else:
            raise CaptureExecutionError(f"Unsupported capture action: {action.type}")

    def _safe_upload_path(self, supplied_path: str) -> Path:
        allowed = self.settings.allowed_upload_directory
        if allowed is None:
            raise CaptureExecutionError("Uploads are disabled for this capture job.")
        root = allowed.resolve()
        candidate = Path(supplied_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise CaptureExecutionError("Upload path is outside the approved fixture directory.")
        if not candidate.is_file():
            raise CaptureExecutionError("Approved upload fixture does not exist.")
        return candidate

    def _record_interaction(
        self,
        page: Page,
        action: CaptureAction,
        started: float,
    ) -> InteractionEvent:
        scroll = cast(
            dict[str, float],
            page.evaluate("() => ({ x: window.scrollX, y: window.scrollY })"),
        )
        viewport = Viewport(
            width=self.settings.viewport_width,
            height=self.settings.viewport_height,
            scroll_x=max(0, scroll["x"]),
            scroll_y=max(0, scroll["y"]),
        )
        box_model: BoundingBox | None = None
        center_x: float | None = None
        center_y: float | None = None
        if action.locator:
            box = _locator(page, action).bounding_box()
            if box is None:
                raise CaptureExecutionError(
                    f"The target for {action.description} is not visible in the viewport."
                )
            box_model = BoundingBox(
                x=max(0, box["x"]),
                y=max(0, box["y"]),
                width=box["width"],
                height=box["height"],
            )
            center_x = box_model.x + box_model.width / 2
            center_y = box_model.y + box_model.height / 2
        return InteractionEvent(
            timestamp_ms=_elapsed_ms(started),
            event_type=action.type,
            locator=action.locator,
            x=center_x,
            y=center_y,
            bounding_box=box_model,
            viewport=viewport,
        )

    @staticmethod
    def _enforce_deadline(started: float, timeout_ms: int) -> None:
        if _elapsed_ms(started) >= timeout_ms:
            raise CaptureExecutionError("Scene capture exceeded its timeout.")


def _locator(page: Page, action: CaptureAction) -> Locator:
    if not action.locator_strategy or not action.locator:
        raise CaptureExecutionError(f"{action.type} action requires a typed locator.")
    strategy = action.locator_strategy
    value = action.locator
    if strategy == "role":
        role, separator, name = value.partition(":")
        return page.get_by_role(
            cast(Any, role),
            name=name if separator else None,
            exact=True,
        )
    if strategy == "label":
        return page.get_by_label(value, exact=True)
    if strategy == "text":
        matches = page.get_by_text(value, exact=True)
        flexible_name: str | re.Pattern[str] = value
        if matches.count() == 0:
            tokens = value.split()
            if tokens:
                flexible_name = _token_pattern(value)
                matches = page.get_by_text(flexible_name)
        if matches.count() == 0:
            for role in ("button", "link", "textbox", "combobox"):
                accessible = page.get_by_role(
                    cast(Any, role),
                    name=flexible_name,
                    exact=isinstance(flexible_name, str),
                )
                if accessible.count():
                    matches = accessible
                    break
        if action.type == "click" and matches.count() > 1:
            for role in ("button", "link"):
                interactive = page.get_by_role(
                    cast(Any, role),
                    name=flexible_name,
                    exact=isinstance(flexible_name, str),
                )
                if interactive.count() == 1:
                    return interactive
        return matches.first if matches.count() > 1 else matches
    if strategy == "test_id":
        return page.get_by_test_id(value)
    if strategy == "placeholder":
        placeholder = page.get_by_placeholder(value, exact=True)
        if placeholder.count():
            return placeholder
        cleaned = _without_ui_metadata(value)
        for name in dict.fromkeys((value, cleaned)):
            labeled = page.get_by_label(name, exact=True)
            if labeled.count():
                return labeled
            for role in ("textbox", "combobox"):
                accessible = page.get_by_role(cast(Any, role), name=name, exact=True)
                if accessible.count():
                    return accessible
        for name in dict.fromkeys((value, cleaned)):
            pattern = _token_pattern(name)
            labeled = page.get_by_label(pattern)
            if labeled.count() == 1:
                return labeled
            for role in ("textbox", "combobox"):
                accessible = page.get_by_role(cast(Any, role), name=pattern)
                if accessible.count() == 1:
                    return accessible
        return placeholder
    if strategy == "alt_text":
        return page.get_by_alt_text(value, exact=True)
    if strategy == "css":
        return page.locator(value)
    if strategy == "xpath":
        return page.locator(f"xpath={value}")
    raise CaptureExecutionError(f"Unsupported locator strategy: {strategy}")


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1_000))


def _clear_error(error: Exception) -> str:
    if isinstance(error, PlaywrightTimeoutError):
        return "Timed out while waiting for a planned browser action or assertion."
    return str(error)


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _without_ui_metadata(value: str) -> str:
    cleaned = value.strip()
    suffix = re.compile(r"\s+(?:required|\d+\s*/\s*\d+)\s*$", re.IGNORECASE)
    while match := suffix.search(cleaned):
        cleaned = cleaned[: match.start()].rstrip()
    return cleaned


def _token_pattern(value: str) -> re.Pattern[str]:
    return re.compile(
        r"\s*".join(re.escape(token) for token in value.split()),
        re.IGNORECASE,
    )
