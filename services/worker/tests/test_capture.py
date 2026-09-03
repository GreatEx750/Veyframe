from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from demodirector_contracts import CaptureAction, CapturePlan, Scene
from demodirector_worker.capture import CaptureSettings, PlaywrightCaptureWorker
from pydantic import HttpUrl


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args


@contextmanager
def fixture_server(directory: Path) -> Iterator[str]:
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(QuietHandler, directory=str(directory)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/index.html"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@contextmanager
def protected_fixture_server() -> Iterator[tuple[str, list[str]]]:
    received_cookies: list[str] = []

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self) -> None:
            cookie = self.headers.get("Cookie", "")
            received_cookies.append(cookie)
            content = (
                "<!doctype html><h1>Private workspace</h1>"
                if "demodirector_session=smoke-token" in cookie
                else "<!doctype html><h1>Log in</h1>"
            )
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", received_cookies
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def write_fixture(directory: Path) -> None:
    directory.mkdir()
    (directory / "index.html").write_text(
        """<!doctype html><title>Capture fixture</title>
<label for="email">Work email</label><input id="email" type="email">
<button aria-label="Save demo" onclick="document.querySelector('#saved').hidden=false">Save</button>
<p id="saved" hidden>Saved successfully</p>
<button onclick="document.querySelector('#opened').hidden=false">Insights</button>
<h1>Insights</h1><p id="opened" hidden>Insights opened</p>""",
        encoding="utf-8",
    )


def scene_for(url: str, *, bad_locator: bool = False) -> Scene:
    return Scene(
        id="scene-capture",
        storyboard_id="storyboard-1",
        order=0,
        title="Save a demo",
        objective="Show the save interaction",
        narration="Save the prepared demo.",
        source_ids=["source-1"],
        capture_plan=CapturePlan(
            start_url=HttpUrl(url),
            actions=[
                CaptureAction(
                    type="fill",
                    locator_strategy="label",
                    locator="Missing email" if bad_locator else "Work email",
                    value="private@example.com",
                    description="Enter the work email",
                ),
                CaptureAction(
                    type="click",
                    locator_strategy="role",
                    locator="button:Save demo",
                    description="Save the demo",
                ),
            ],
            success_assertions=[
                CaptureAction(
                    type="assert_visible",
                    locator_strategy="text",
                    locator="Saved successfully",
                    description="Confirm the save result",
                )
            ],
            timeout_seconds=2,
        ),
        expected_evidence=["The saved confirmation is visible"],
        duration_seconds=3,
    )


def test_fixture_scene_records_webm_and_safe_action_results(tmp_path: Path) -> None:
    site = tmp_path / "site"
    write_fixture(site)
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")

    with fixture_server(site) as url:
        result = worker.capture_scene(scene_for(url))

    assert result.status == "succeeded"
    assert result.retryable is False
    assert result.raw_clip_path is not None
    assert Path(result.raw_clip_path).is_file()
    assert Path(result.raw_clip_path).suffix == ".webm"
    assert [item.status for item in result.action_results] == ["succeeded", "succeeded"]
    assert [event.event_type for event in result.interaction_events] == ["fill", "click"]
    click = result.interaction_events[1]
    assert click.bounding_box is not None
    assert click.bounding_box.x + click.bounding_box.width <= click.viewport.width
    assert click.bounding_box.y + click.bounding_box.height <= click.viewport.height
    assert click.timestamp_ms <= result.duration_ms
    assert click.x is not None and click.y is not None
    assert result.model_validate_json(result.model_dump_json()) == result
    assert "private@example.com" not in result.model_dump_json()


def test_bad_locator_is_retryable_and_saves_failure_screenshot(tmp_path: Path) -> None:
    site = tmp_path / "site"
    write_fixture(site)
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")

    with fixture_server(site) as url:
        result = worker.capture_scene(scene_for(url, bad_locator=True))

    assert result.status == "failed"
    assert result.retryable is True
    assert result.error == "Timed out while waiting for a planned browser action or assertion."
    assert result.duration_ms < 5_000
    assert result.action_results[0].status == "failed"
    assert len(result.screenshot_paths) == 1
    assert Path(result.screenshot_paths[0]).is_file()


def test_text_click_prefers_a_unique_interactive_control_over_matching_heading(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site"
    write_fixture(site)
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")
    scene = scene_for("https://example.com").model_copy(
        update={
            "capture_plan": CapturePlan(
                start_url=HttpUrl("https://example.com"),
                actions=[
                    CaptureAction(
                        type="click",
                        locator_strategy="text",
                        locator="Insights",
                        description="Open insights",
                    )
                ],
                success_assertions=[
                    CaptureAction(
                        type="assert_visible",
                        locator_strategy="text",
                        locator="Insights opened",
                        description="Confirm insights opened",
                    )
                ],
                timeout_seconds=2,
            )
        }
    )

    with fixture_server(site) as url:
        plan = scene.capture_plan.model_copy(update={"start_url": HttpUrl(url)})
        result = worker.capture_scene(scene.model_copy(update={"capture_plan": plan}))

    assert result.status == "succeeded"
    assert result.interaction_events[0].bounding_box is not None


def test_upload_path_must_be_inside_explicit_fixture_directory(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    fixture = allowed / "fixture.txt"
    fixture.write_text("fixture", encoding="utf-8")
    worker = PlaywrightCaptureWorker(
        tmp_path / "artifacts",
        CaptureSettings(allowed_upload_directory=allowed),
    )

    assert worker._safe_upload_path(str(fixture)) == fixture

    outside = tmp_path / "outside.txt"
    outside.write_text("not approved", encoding="utf-8")
    try:
        worker._safe_upload_path(str(outside))
    except RuntimeError as error:
        assert "outside" in str(error)
    else:
        raise AssertionError("an out-of-scope upload fixture was accepted")


def test_capture_action_contract_rejects_javascript_evaluation() -> None:
    try:
        CaptureAction.model_validate(
            {
                "type": "evaluate",
                "value": "document.body.innerHTML",
                "description": "Run model-provided JavaScript",
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("the deterministic action allowlist accepted JavaScript")


def test_capture_forwards_session_only_to_an_allowlisted_origin(tmp_path: Path) -> None:
    with protected_fixture_server() as (url, received_cookies):
        worker = PlaywrightCaptureWorker(
            tmp_path / "artifacts",
            CaptureSettings(authenticated_origins=(url.rstrip("/"),)),
        )
        scene = scene_for(url).model_copy(
            update={
                "capture_plan": CapturePlan(
                    start_url=HttpUrl(url),
                    actions=[],
                    success_assertions=[
                        CaptureAction(
                            type="assert_visible",
                            locator_strategy="text",
                            locator="Private workspace",
                            description="Confirm the authenticated workspace",
                        )
                    ],
                    timeout_seconds=2,
                )
            }
        )
        result = worker.capture_scene(scene, session_token="smoke-token")

    assert result.status == "succeeded"
    assert any("demodirector_session=smoke-token" in value for value in received_cookies)


def test_capture_does_not_forward_session_to_an_untrusted_origin(tmp_path: Path) -> None:
    with protected_fixture_server() as (url, received_cookies):
        worker = PlaywrightCaptureWorker(
            tmp_path / "artifacts",
            CaptureSettings(authenticated_origins=("https://trusted.example",)),
        )
        scene = scene_for(url).model_copy(
            update={
                "capture_plan": CapturePlan(
                    start_url=HttpUrl(url),
                    actions=[],
                    success_assertions=[
                        CaptureAction(
                            type="assert_visible",
                            locator_strategy="text",
                            locator="Log in",
                            description="Confirm the public login page",
                        )
                    ],
                    timeout_seconds=2,
                )
            }
        )
        result = worker.capture_scene(scene, session_token="smoke-token")

    assert result.status == "succeeded"
    assert all("smoke-token" not in value for value in received_cookies)
