"""Exercise hosted Studio and inspect saved authored-demo jobs without exposing credentials."""

import argparse
import json
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "retry", "rebuild", "status", "verify"])
    parser.add_argument("mode", choices=["spotlight", "short", "presentation"])
    parser.add_argument("--base", default="https://demodirector-web-5zo4cenn3q-uc.a.run.app")
    parser.add_argument("--artifacts-root", type=Path, default=Path("artifacts/cloud-mode-smoke"))
    parser.add_argument("--title-suffix", default="verification")
    parser.add_argument("--title")
    parser.add_argument("--url", default="https://www.wikipedia.org/")
    parser.add_argument("--brief")
    parser.add_argument("--call-to-action", default="Explore Wikipedia")
    args = parser.parse_args()
    root = args.artifacts_root / args.mode
    root.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1600, "height": 1100})
        auth = context.request.post(args.base + "/api/auth/judge-session", timeout=60000)
        assert auth.status == 200, f"Judge login HTTP {auth.status}"
        page = context.new_page()
        page.set_default_timeout(30000)
        if args.action == "start":
            assert not (root / "project.json").exists(), "Existing smoke project; inspect before rerunning"
            page.goto(args.base + "/studio", wait_until="domcontentloaded", timeout=60000)
            page.get_by_label("Demo title", exact=False).fill(
                args.title or f"Wikipedia — Cloud {args.mode.title()} {args.title_suffix}"
            )
            page.get_by_label("Website URL", exact=False).fill(args.url)
            page.get_by_label("Describe your video", exact=False).fill(
                args.brief or
                "Show how Wikipedia helps people explore knowledge. Search for Solar System, "
                "read its overview, use the table of contents and follow the Earth article. "
                "Show actual browser interactions with visible pointer movement and clicks, "
                "clear narration, captions, and smooth zoom. End by inviting viewers to explore Wikipedia."
            )
            page.get_by_label("Target Audience", exact=True).select_option(label="Product leaders")
            page.get_by_label("Call to Action", exact=True).fill(args.call_to_action)
            label = "Presentation Demo" if args.mode == "presentation" else args.mode.title()
            page.get_by_role("radio", name=label, exact=True).check()
            page.screenshot(path=str(root / "studio.png"), full_page=True)
            page.get_by_role("button", name="Create demo", exact=True).click()
            page.wait_for_url("**/jobs?job=*", timeout=90000)
            job_id = page.url.split("?job=")[1]
            jobs = context.request.get(args.base + "/api/jobs").json()["jobs"]
            job = next(item["job"] for item in jobs if item["job"]["id"] == job_id)
            (root / "project.json").write_text(json.dumps({"project_id": job["project_id"], "job_id": job_id}), encoding="utf-8")
            page.screenshot(path=str(root / "queued.png"), full_page=True)
        saved = json.loads((root / "project.json").read_text(encoding="utf-8"))
        if args.action in {"retry", "rebuild"}:
            page.goto(args.base + "/jobs?job=" + saved["job_id"], wait_until="domcontentloaded", timeout=60000)
            with page.expect_response(lambda response: response.url.endswith("/generation/presentation") and response.request.method == "POST", timeout=60000) as retried:
                button = "Approve retry" if args.action == "retry" else "Rebuild from saved slides"
                page.get_by_role("button", name=button, exact=True).click()
            assert retried.value.status == 202, f"Retry HTTP {retried.value.status}"
            page.screenshot(path=str(root / "retry.png"), full_page=True)
        prefix = args.base + "/api/projects/" + saved["project_id"]
        response = context.request.get(prefix + "/generation/presentation", timeout=60000)
        assert response.status == 200, f"Job status HTTP {response.status}"
        job = response.json()
        (root / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
        print(json.dumps(job, indent=2), flush=True)
        detail_response = context.request.get(args.base + "/api/jobs", timeout=60000)
        assert detail_response.status == 200
        detail = next(item for item in detail_response.json()["jobs"] if item["job"]["id"] == saved["job_id"])
        (root / "details.json").write_text(json.dumps(detail, indent=2), encoding="utf-8")
        print(json.dumps({key: detail.get(key) for key in ["health", "last_heartbeat_at", "elapsed_seconds"]}), flush=True)
        if args.action == "verify":
            assert job["status"] == "succeeded", "Job has not succeeded"
            page.goto(args.base + "/projects/" + saved["project_id"] + "/editor", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_function("document.querySelector('video')?.readyState >= 2", timeout=90000)
            assert page.locator("video").count() == 1
            video = page.locator("video")
            video.evaluate("v => { v.muted = true; }")
            page.get_by_role("button", name="Play preview", exact=True).click()
            page.wait_for_function("document.querySelector('video').currentTime > 2", timeout=30000)
            page.get_by_role("button", name="Pause preview", exact=True).click()
            playback = video.evaluate("v => ({width:v.videoWidth,height:v.videoHeight,duration:v.duration,time:v.currentTime,error:v.error})")
            assert playback["width"] == 2560 and playback["height"] == 1440
            assert playback["error"] is None
            expected = {"spotlight": (30, 30.2), "short": (45, 45.2), "presentation": (120, 140.2)}[args.mode]
            assert expected[0] <= playback["duration"] <= expected[1], playback
            for second in [2, playback["duration"] / 2, playback["duration"] - 2]:
                video.evaluate("(v, t) => new Promise(resolve => { v.addEventListener('seeked', resolve, {once:true}); v.currentTime=t; })", second)
                page.screenshot(path=str(root / f"playback-{int(second)}.png"), full_page=True)
            timeline_response = context.request.get(prefix + "/timeline")
            assert timeline_response.status == 200
            timeline = timeline_response.json()["current"]["timeline"]
            clips = timeline["scene_clips"]
            assert len(clips) == {"spotlight":3, "short":5, "presentation":9}[args.mode]
            assert clips[0]["start_ms"] == 0
            assert clips[-1]["end_ms"] == timeline["duration_ms"]
            for index, clip in enumerate(clips):
                second = (clip["start_ms"] + clip["end_ms"]) / 2000
                video.evaluate("(v, t) => new Promise(resolve => { v.addEventListener('seeked', resolve, {once:true}); v.currentTime=t; })", second)
                page.screenshot(path=str(root / f"section-{index + 1:02d}.png"), full_page=True)
            export = context.request.get(prefix + "/exports/latest").json()
            assert export["id"] == job["export_id"]
            assert context.request.get(prefix + "/exports/latest/video", headers={"Range":"bytes=0-1023"}).status == 206
            assert saved["project_id"] in context.request.get(args.base + "/api/projects").text()
            media = context.request.get(prefix + "/exports/latest/video", timeout=120000)
            assert media.status == 200
            output = root / "cloud-export.mp4"
            output.write_bytes(media.body())
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)], check=True, capture_output=True, text=True, timeout=30)
            metadata = json.loads(probe.stdout)
            assert any(stream["codec_type"] == "audio" for stream in metadata["streams"])
            decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"], check=True, capture_output=True, text=True, timeout=180)
            assert not decoded.stderr.strip(), decoded.stderr
            (root / "verification.json").write_text(json.dumps({"playback":playback,"export":export,"project":saved,"media":metadata,"section_count":len(clips),"full_decode":"passed"}, indent=2), encoding="utf-8")
            print("PASS: Studio submission, saved job, export, library, range delivery, playback, dimensions and duration", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
