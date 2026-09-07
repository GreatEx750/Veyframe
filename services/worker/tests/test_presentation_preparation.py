import subprocess
from pathlib import Path

import pytest
from demodirector_contracts import CaptureAction, Scene
from demodirector_worker.presentation_assets import AuthoredSlideRenderer


def test_preparation_runs_before_visible_recording(tmp_path: Path) -> None:
    page = tmp_path / "app.html"
    page.write_text(
        """<body style="background:white"><button
        onclick="document.body.style.background='green';this.remove()">Load app</button>
        <h1>Ready product</h1><button>Explore</button></body>""",
        "utf-8",
    )
    # HttpUrl is used in the public contract, so serve the fixture over loopback.
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        scene = Scene.model_validate({
            "id": "prepared", "storyboard_id": "test", "order": 0,
            "title": "Prepared app", "objective": "Show the loaded product",
            "narration": "Ready product", "duration_seconds": 2,
            "capture_plan": {"start_url": f"http://127.0.0.1:{server.server_port}/app.html",
                             "timeout_seconds": 10, "actions": [{
                                 "type": "click", "locator_strategy": "role",
                                 "locator": "button:Explore", "description": "Explore product",
                             }]},
        })
        renderer = AuthoredSlideRenderer(tmp_path / "render")
        template = {"requires_product": True,
                    "canvas": {"width": 640, "height": 360},
                    "product_aperture": {"x": 0, "y": 0, "width": 640, "height": 360}}
        preparation = [CaptureAction(type="click", locator_strategy="role",
                                     locator="button:Load app", description="Prepare product")]
        video, receipt = renderer.capture(scene, 2000, template, preparation=preparation)
        assert video.is_file()
        assert len(receipt.interaction_events) == 1
        assert receipt.interaction_events[0].locator == "button:Explore"
        assert receipt.duration_ms == 2000
        assert any("Prepare product" in line for line in receipt.logs)
        pixel = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(video), "-frames:v", "1",
             "-vf", "crop=2:2:500:300,scale=1:1", "-pix_fmt", "rgb24",
             "-f", "rawvideo", "-"], capture_output=True, check=True, timeout=30,
        ).stdout
        assert len(pixel) == 3 and pixel[1] > pixel[0] * 2 and pixel[1] > pixel[2] * 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_preparation_rejects_excessive_timeout_before_browser_launch(tmp_path: Path) -> None:
    renderer = AuthoredSlideRenderer(tmp_path)
    with pytest.raises(ValueError, match="preparation timeout"):
        renderer.prepare_page(None, [], timeout_seconds=1000)  # type: ignore[arg-type]
