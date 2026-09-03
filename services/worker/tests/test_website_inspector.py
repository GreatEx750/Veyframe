from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from demodirector_worker.website_inspector import InspectorSettings, PlaywrightWebsiteInspector


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args


@contextmanager
def fixture_server(directory: Path, delay_seconds: float = 0) -> Iterator[str]:
    class Handler(QuietHandler):
        def do_GET(self) -> None:
            if delay_seconds:
                time.sleep(delay_seconds)
            super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/index.html"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def write_fixture_site(directory: Path) -> None:
    directory.mkdir()
    (directory / "index.html").write_text(
        """<!doctype html>
<html><head><title>Fixture Product</title></head>
<body>
  <h1>Build calmer workflows</h1>
  <button aria-label="Start demo">Start</button>
  <label for="email">Work email</label>
  <input id="email" type="email" value="sensitive@example.com" />
  <a href="/docs.html">Documentation</a>
</body></html>""",
        encoding="utf-8",
    )
    (directory / "docs.html").write_text(
        "<!doctype html><title>Docs</title><h1>Documentation</h1><p>Official help.</p>",
        encoding="utf-8",
    )


def test_fixture_site_produces_stable_inventory_and_screenshot(tmp_path: Path) -> None:
    site = tmp_path / "site"
    write_fixture_site(site)
    inspector = PlaywrightWebsiteInspector(
        tmp_path / "artifacts",
        InspectorSettings(max_pages=2, max_depth=1, timeout_ms=5_000),
    )

    with fixture_server(site) as url:
        inspection = inspector.inspect(project_id="project-1", website_url=url)

    assert [page.title for page in inspection.pages] == ["Fixture Product", "Docs"]
    assert inspection.pages[0].headings == ["Build calmer workflows"]
    assert [element.kind for element in inspection.pages[0].elements] == [
        "button",
        "input",
        "link",
    ]
    assert inspection.pages[0].elements[1].label == "Work email"
    assert Path(inspection.pages[0].screenshot_path).is_file()
    assert "sensitive@example.com" not in inspection.model_dump_json()


def test_inspector_timeout_is_reported_without_crashing(tmp_path: Path) -> None:
    site = tmp_path / "site"
    write_fixture_site(site)
    inspector = PlaywrightWebsiteInspector(
        tmp_path / "artifacts",
        InspectorSettings(max_pages=1, max_depth=0, timeout_ms=50),
    )

    with fixture_server(site, delay_seconds=0.2) as url:
        inspection = inspector.inspect(project_id="project-timeout", website_url=url)

    assert inspection.pages == []
    assert inspection.warning is not None
    assert "Timed out" in inspection.warning
