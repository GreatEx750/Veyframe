"""Verify the saved pilot's real media and authenticated local playback."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "wikipedia-presentation-five-slides"


def main() -> None:
    result = json.loads((OUTPUT / "result.json").read_text("utf-8"))
    media = OUTPUT / "wikipedia-first-five-slides.mp4"
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(media),
            ]
        )
    )
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert (video["width"], video["height"], video["codec_name"]) == (2560, 1440, "h264")
    assert video["r_frame_rate"] == "30/1"
    assert audio["codec_name"] == "aac"
    assert abs(float(probe["format"]["duration"]) - 53) < 0.05
    clicks = 0
    for index in range(1, 6):
        receipt = json.loads((OUTPUT / f"slide-{index:02d}-adk.json").read_text("utf-8"))
        assert receipt["evidence_reads"] > 0
        if index > 2:
            capture = json.loads((OUTPUT / f"slide-{index:02d}-capture.json").read_text("utf-8"))
            events = [e for e in capture["interaction_events"] if e["event_type"] == "click"]
            assert events and all(e["x"] is not None and e["y"] is not None for e in events)
            clicks += len(events)
    for stamp in [1, 4, 7, 13, 19, 23, 30, 36, 40, 45, 52]:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(stamp),
                "-i",
                str(media),
                "-frames:v",
                "1",
                str(OUTPUT / f"review-{stamp:02d}.png"),
            ],
            check=True,
            timeout=30,
        )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1600, "height": 1100})
        auth = context.request.post("http://localhost:3000/api/auth/judge-session")
        assert auth.status == 200, f"Local sign-in: {auth.status}"
        projects = context.request.get("http://localhost:3000/api/projects")
        assert projects.status == 200
        assert result["project_id"] in projects.text(), "Pilot missing from project library"
        base = f"http://localhost:3000/api/projects/{result['project_id']}/exports/latest"
        latest = context.request.get(base)
        assert latest.status == 200
        assert latest.json()["id"] == result["export"]["id"]
        ranged = context.request.get(base + "/video", headers={"Range": "bytes=0-1023"})
        assert ranged.status == 206 and len(ranged.body()) == 1024
        page = context.new_page()
        page.goto("http://localhost:3000/projects", wait_until="networkidle")
        page.get_by_text(
            "Wikipedia — Presentation preview · first five slides", exact=True
        ).wait_for()
        page.screenshot(path=str(OUTPUT / "project-library.png"), full_page=True)
        page.goto(
            f"http://localhost:3000/projects/{result['project_id']}/editor",
            wait_until="networkidle",
        )
        page.wait_for_function("document.querySelector('video')?.readyState >= 2")
        assert page.locator("video").count() == 1
        page.locator("video").evaluate("video => { video.muted = true; }")
        page.get_by_label("Timeline playhead", exact=True).fill("7000")
        page.get_by_role("button", name="Play preview", exact=True).click()
        page.wait_for_function("document.querySelector('video').currentTime > 8", timeout=20000)
        page.get_by_role("button", name="Pause preview", exact=True).click()
        playback = page.locator("video").evaluate("""video => ({
            time: video.currentTime, width: video.videoWidth,
            height: video.videoHeight, duration: video.duration, error: video.error
        })""")
        assert playback["time"] > 8 and playback["error"] is None
        assert (playback["width"], playback["height"]) == (2560, 1440)
        page.screenshot(path=str(OUTPUT / "editor-playback.png"), full_page=True)
        browser.close()
    report = {
        "media": "53s / 2560x1440 / 30fps / H.264 + AAC",
        "adk_slides": 5,
        "recorded_clicks": clicks,
        "library": "passed",
        "range_playback": "passed",
        "browser_playback": playback,
        "export_id": result["export"]["id"],
    }
    (OUTPUT / "verification.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
