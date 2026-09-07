"""Observe unsolicited seeks in hosted preview playback without modifying the player."""

import argparse
import json

from playwright.sync_api import sync_playwright


parser = argparse.ArgumentParser()
parser.add_argument("--base", default="https://demodirector-web-5zo4cenn3q-uc.a.run.app")
parser.add_argument("--project-id", default="208f7496-2c97-4f69-956a-0e00989a7c59")
parser.add_argument("--assert-smooth", action="store_true")
args = parser.parse_args()

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context()
    base = args.base
    auth = context.request.post(base + "/api/auth/judge-session")
    assert auth.status == 200
    page = context.new_page()
    page.goto(base + "/projects/" + args.project_id + "/editor")
    page.wait_for_function("document.querySelector('video')?.readyState >= 2")
    video = page.locator("video")
    video.evaluate("""v => {
        v.muted = true;
        window.playbackProbe = {
            seeking: 0, seeked: 0, timeupdate: 0, waiting: 0,
            started: performance.now(), start: v.currentTime
        };
        for (const name of ['seeking', 'seeked', 'timeupdate', 'waiting']) {
            v.addEventListener(name, () => window.playbackProbe[name]++);
        }
    }""")
    page.get_by_role("button", name="Play preview", exact=True).click()
    page.wait_for_timeout(10000)
    result = video.evaluate("""v => ({
        ...window.playbackProbe,
        wallSeconds: (performance.now() - window.playbackProbe.started) / 1000,
        videoSeconds: v.currentTime - window.playbackProbe.start,
        playbackRate: v.playbackRate
    })""")
    print(json.dumps(result), flush=True)
    if args.assert_smooth:
        assert result["seeking"] == 0, "Normal playback must never seek"
        assert result["playbackRate"] == 1
        assert result["videoSeconds"] >= result["wallSeconds"] * .9, "Playback fell behind real time"
        assert result["waiting"] == 0, "Playback was interrupted"
        page.get_by_role("button", name="Pause preview", exact=True).click()
        paused_time = video.evaluate("v => v.currentTime")
        page.wait_for_timeout(400)
        assert abs(video.evaluate("v => v.currentTime") - paused_time) < .1
        slider = page.get_by_label("Timeline playhead", exact=True)
        slider.focus()
        slider.press("Home")
        page.wait_for_function("document.querySelector('video').currentTime < .1 && !document.querySelector('video').seeking")
        page.get_by_role("button", name="Play preview", exact=True).click()
        page.wait_for_function("document.querySelector('video').currentTime > 1")
        page.get_by_role("button", name="Pause preview", exact=True).click()
        assert video.evaluate("() => window.playbackProbe.seeking") == 1, "Only the deliberate seek should occur"
        print("PASS: uninterrupted real-time playback, pause, deliberate seek and resume", flush=True)
    browser.close()
