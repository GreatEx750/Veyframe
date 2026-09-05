from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from demodirector_contracts import CaptureAction, CapturePlan, Scene
from demodirector_worker.capture import CaptureSettings, PlaywrightCaptureWorker
from pydantic import HttpUrl


def media_binary(name: str) -> str:
    discovered = shutil.which(name)
    if discovered:
        return discovered
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        matches = sorted(
            (Path(local_app_data) / "Microsoft" / "WinGet" / "Packages").glob(
                f"Gyan.FFmpeg*/*/bin/{name}.exe"
            )
        )
        if matches:
            return str(matches[0])
    pytest.skip(f"{name} is required for the capture resolution test")


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
<label for="brief">Describe your video</label>
<textarea id="brief" placeholder="Tell us about the workflow"></textarea>
<label for="site">Website URL <span>Required</span></label>
<input id="site" placeholder="https://yourproduct.com" type="url">
<button aria-label="Save demo" onclick="document.querySelector('#saved').hidden=false">Save</button>
<p id="saved" hidden>Saved successfully</p>
<button onclick="document.querySelector('#opened').hidden=false">Insights</button>
<h1>Insights</h1><p id="opened" hidden>Insights opened</p>
<p><span>Website URL</span><span>Required</span></p>""",
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


def test_default_capture_settings_match_qhd_monitor_resolution() -> None:
    settings = CaptureSettings()

    assert (settings.viewport_width, settings.viewport_height) == (2560, 1440)


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
    probe = subprocess.run(
        [
            media_binary("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            result.raw_clip_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert (stream["width"], stream["height"]) == (2560, 1440)


def test_offscreen_interaction_is_recorded_inside_the_viewport(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        """<!doctype html><title>Offscreen target fixture</title>
<div style="height: 2400px"></div>
<button>Related article</button>""",
        encoding="utf-8",
    )
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")
    scene = scene_for("https://example.com").model_copy(
        update={
            "capture_plan": CapturePlan(
                start_url=HttpUrl("https://example.com"),
                actions=[
                    CaptureAction(
                        type="click",
                        locator_strategy="role",
                        locator="button:Related article",
                        description="Open the related article",
                    )
                ],
                success_assertions=[],
                timeout_seconds=2,
            )
        }
    )

    with fixture_server(site) as url:
        plan = scene.capture_plan.model_copy(update={"start_url": HttpUrl(url)})
        result = worker.capture_scene(scene.model_copy(update={"capture_plan": plan}))

    assert result.status == "succeeded"
    event = result.interaction_events[0]
    assert event.bounding_box is not None
    assert 0 <= event.bounding_box.y < event.viewport.height
    assert event.bounding_box.y + event.bounding_box.height <= event.viewport.height


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


def test_text_locator_matches_escaped_tokens_across_adjacent_elements(tmp_path: Path) -> None:
    site = tmp_path / "site"
    write_fixture(site)
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")
    scene = scene_for("https://example.com").model_copy(
        update={
            "capture_plan": CapturePlan(
                start_url=HttpUrl("https://example.com"),
                actions=[],
                success_assertions=[
                    CaptureAction(
                        type="assert_visible",
                        locator_strategy="text",
                        locator="Website URL Required",
                        description="Confirm the required website URL field",
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


def test_text_locator_falls_back_to_an_exact_accessible_name(tmp_path: Path) -> None:
    site = tmp_path / "site"
    write_fixture(site)
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")
    scene = scene_for("https://example.com").model_copy(
        update={
            "capture_plan": CapturePlan(
                start_url=HttpUrl("https://example.com"),
                actions=[],
                success_assertions=[
                    CaptureAction(
                        type="assert_visible",
                        locator_strategy="text",
                        locator="Save demo",
                        description="Confirm the save control",
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


def test_text_wait_uses_first_match_when_hydration_adds_duplicates(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        """<!doctype html><title>Hydration fixture</title>
<script>
setTimeout(() => {
  document.body.insertAdjacentHTML('beforeend', '<p>Devpost</p><p>Devpost for Teams</p>');
}, 100);
</script>""",
        encoding="utf-8",
    )
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")
    scene = scene_for("https://example.com").model_copy(
        update={
            "capture_plan": CapturePlan(
                start_url=HttpUrl("https://example.com"),
                actions=[
                    CaptureAction(
                        type="wait_for",
                        locator_strategy="text",
                        locator="Devpost",
                        description="Wait for hydrated page content",
                    )
                ],
                success_assertions=[],
                timeout_seconds=2,
            )
        }
    )

    with fixture_server(site) as url:
        plan = scene.capture_plan.model_copy(update={"start_url": HttpUrl(url)})
        result = worker.capture_scene(scene.model_copy(update={"capture_plan": plan}))

    assert result.status == "succeeded"


def test_text_wait_prefers_a_visible_partial_match_over_a_hidden_exact_match(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        """<!doctype html><title>Visible text fixture</title>
<span hidden>Wikipedia</span>
<p>From Wikipedia, the free encyclopedia</p>""",
        encoding="utf-8",
    )
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")
    scene = scene_for("https://example.com").model_copy(
        update={
            "capture_plan": CapturePlan(
                start_url=HttpUrl("https://example.com"),
                actions=[
                    CaptureAction(
                        type="wait_for",
                        locator_strategy="text",
                        locator="Wikipedia",
                        description="Wait for visible Wikipedia content",
                    )
                ],
                success_assertions=[],
                timeout_seconds=2,
            )
        }
    )

    with fixture_server(site) as url:
        plan = scene.capture_plan.model_copy(update={"start_url": HttpUrl(url)})
        result = worker.capture_scene(scene.model_copy(update={"capture_plan": plan}))

    assert result.status == "succeeded"


def test_placeholder_locator_falls_back_to_a_label_without_counter_metadata(
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
                        type="fill",
                        locator_strategy="placeholder",
                        locator="Describe your video 0/500",
                        value="Show the product workflow",
                        description="Enter the video brief",
                    )
                ],
                success_assertions=[],
                timeout_seconds=2,
            )
        }
    )

    with fixture_server(site) as url:
        plan = scene.capture_plan.model_copy(update={"start_url": HttpUrl(url)})
        result = worker.capture_scene(scene.model_copy(update={"capture_plan": plan}))

    assert result.status == "succeeded"


def test_placeholder_locator_matches_tokens_within_an_accessible_label(
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
                        type="fill",
                        locator_strategy="placeholder",
                        locator="Website URL",
                        value="https://example.com",
                        description="Enter the website URL",
                    )
                ],
                success_assertions=[],
                timeout_seconds=2,
            )
        }
    )

    with fixture_server(site) as url:
        plan = scene.capture_plan.model_copy(update={"start_url": HttpUrl(url)})
        result = worker.capture_scene(scene.model_copy(update={"capture_plan": plan}))

    assert result.status == "succeeded"


def test_placeholder_assertion_uses_a_visible_match_when_page_has_duplicates(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        """<!doctype html><title>Duplicate search fixture</title>
<input type="search" placeholder="Search Wikipedia">
<input type="search" placeholder="Search Wikipedia">""",
        encoding="utf-8",
    )
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")
    scene = scene_for("https://example.com").model_copy(
        update={
            "capture_plan": CapturePlan(
                start_url=HttpUrl("https://example.com"),
                actions=[],
                success_assertions=[
                    CaptureAction(
                        type="assert_visible",
                        locator_strategy="placeholder",
                        locator="Search Wikipedia",
                        description="Assert a search field remains visible",
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


def test_placeholder_fill_uses_a_visible_match_when_page_has_duplicates(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        """<!doctype html><title>Duplicate search fixture</title>
<input type="search" placeholder="Search Wikipedia">
<input type="search" placeholder="Search Wikipedia">""",
        encoding="utf-8",
    )
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")
    scene = scene_for("https://example.com").model_copy(
        update={
            "capture_plan": CapturePlan(
                start_url=HttpUrl("https://example.com"),
                actions=[
                    CaptureAction(
                        type="fill",
                        locator_strategy="placeholder",
                        locator="Search Wikipedia",
                        value="Artificial intelligence",
                        description="Enter the article topic",
                    )
                ],
                success_assertions=[],
                timeout_seconds=2,
            )
        }
    )

    with fixture_server(site) as url:
        plan = scene.capture_plan.model_copy(update={"start_url": HttpUrl(url)})
        result = worker.capture_scene(scene.model_copy(update={"capture_plan": plan}))

    assert result.status == "succeeded"


def test_semantic_search_locators_fall_back_to_unique_native_controls(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        """<!doctype html><title>Search fixture</title>
<form><input id="searchInput" name="search" type="search">
<button type="submit">Search</button></form>
<button type="button">Language</button>""",
        encoding="utf-8",
    )
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")
    scene = scene_for("https://example.com").model_copy(
        update={
            "capture_plan": CapturePlan(
                start_url=HttpUrl("https://example.com"),
                actions=[
                    CaptureAction(
                        type="fill",
                        locator_strategy="placeholder",
                        locator="Search Wikipedia",
                        value="Google Gemini",
                        description="Enter the search query",
                    ),
                    CaptureAction(
                        type="click",
                        locator_strategy="role",
                        locator="Search",
                        description="Submit the search",
                    ),
                ],
                success_assertions=[],
                timeout_seconds=2,
            )
        }
    )

    with fixture_server(site) as url:
        plan = scene.capture_plan.model_copy(update={"start_url": HttpUrl(url)})
        result = worker.capture_scene(scene.model_copy(update={"capture_plan": plan}))

    assert result.status == "succeeded"
    assert [event.locator for event in result.interaction_events] == [
        "Search Wikipedia",
        "Search",
    ]


def test_unnamed_button_role_uses_the_unique_native_submit_control(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        """<!doctype html><title>Submit fixture</title>
<form><input name="search"><button type="submit">Search</button></form>
<button type="button">Language</button>""",
        encoding="utf-8",
    )
    worker = PlaywrightCaptureWorker(tmp_path / "artifacts")
    scene = scene_for("https://example.com").model_copy(
        update={
            "capture_plan": CapturePlan(
                start_url=HttpUrl("https://example.com"),
                actions=[
                    CaptureAction(
                        type="click",
                        locator_strategy="role",
                        locator="button",
                        description="Submit the search",
                    )
                ],
                success_assertions=[
                    CaptureAction(
                        type="assert_visible",
                        locator_strategy="role",
                        locator="button",
                        description="Ensure a button remains visible",
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
    assert result.interaction_events[0].locator == "button"


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
