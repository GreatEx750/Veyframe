"""Render the authored QHD pack from validated copy and actual browser recordings."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from demodirector_contracts import RenderConfig, Scene, SceneCaptureResult, ZoomClip
from playwright.sync_api import sync_playwright

from demodirector_worker.captions import highlight_frame_window, word_highlights
from demodirector_worker.capture import CaptureSettings, PlaywrightCaptureWorker, _locator

PACK_ROOT = Path(__file__).parent / "templates" / "presentation-story-v2"

# This pointer implementation is fixed application code, never supplied by a model.
POINTER_SCRIPT = """() => {
  function mount() {
    const cursor = document.createElement('div');
    cursor.setAttribute('aria-hidden', 'true');
    cursor.style.cssText = 'position:fixed;left:50%;top:50%;width:40px;height:52px;'
      + 'z-index:2147483647;pointer-events:none;filter:drop-shadow(0 2px 2px #0008)';
    cursor.innerHTML = '<svg viewBox="0 0 40 52"><path d="M3 2L3 39L13 31L22 49'
      + 'L30 45L21 28L35 28Z" fill="white" stroke="#102B25" stroke-width="3"/></svg>';
    document.documentElement.appendChild(cursor);
    document.addEventListener('mousemove', e => {
      cursor.style.left = Math.min(innerWidth-40,e.clientX) + 'px';
      cursor.style.top = Math.min(innerHeight-52,e.clientY) + 'px';
    });
    document.addEventListener('mousedown', e => {
      const ring = document.createElement('div');
      ring.style.cssText = 'position:fixed;width:62px;height:62px;border:5px solid #ff6559;'
        + 'border-radius:50%;z-index:2147483646;pointer-events:none;'
        + 'left:'+(e.clientX-31)+'px;top:'+(e.clientY-31)+'px';
      document.documentElement.appendChild(ring);
      ring.animate([{transform:'scale(.5)',opacity:1},{transform:'scale(1.8)',opacity:0}],
        {duration:650,easing:'ease-out'}).onfinish = () => ring.remove();
    });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',mount);
  else mount();
} """


def load_pack() -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads((PACK_ROOT / "manifest.json").read_text("utf-8"))
    if manifest["pack_id"] != "presentation-story@2":
        raise ValueError("Unknown authored presentation pack")
    for relative, digest in manifest["integrity"]["files"].items():
        asset = (PACK_ROOT / relative).resolve()
        if PACK_ROOT.resolve() not in asset.parents:
            raise ValueError("Asset escaped the authored pack")
        if hashlib.sha256(asset.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Authored asset integrity failed: {relative}")
    return manifest


def run_ffmpeg(arguments: list[str], cwd: Path) -> None:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])


def capture_settings_for_template(template: dict[str, Any]) -> CaptureSettings:
    """Use the authored product window as the browser and recording pixel grid."""
    if not template.get("requires_product"):
        raise ValueError("Only product templates have a recording viewport")
    aperture = template.get("product_aperture", {})
    for position, dimension, limit in [("x", "width", 2560), ("y", "height", 1440)]:
        offset, size = aperture.get(position), aperture.get(dimension)
        if (
            type(offset) is not int
            or type(size) is not int
            or offset < 0
            or size < 2
            or size % 2
            or offset + size > limit
        ):
            raise ValueError("Invalid authored product aperture for browser recording")
    return CaptureSettings(viewport_width=aperture["width"], viewport_height=aperture["height"])


def media_probe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)  # type: ignore[no-any-return]


class AuthoredSlideRenderer:
    def __init__(self, output: Path) -> None:
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.pack = load_pack()

    def capture(
        self,
        scene: Scene,
        duration_ms: int,
        template: dict[str, Any],
        *,
        session_token: str | None = None,
    ) -> tuple[Path, SceneCaptureResult]:
        """Record one scene, moving through observed targets with the standard executor."""
        settings = capture_settings_for_template(template)
        worker = PlaywrightCaptureWorker(self.output / "capture", settings)
        destination = (
            self.output
            / "capture"
            / (f"{scene.id}-{settings.viewport_width}x{settings.viewport_height}")
        )
        destination.mkdir(parents=True, exist_ok=True)
        events = []
        logs = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = worker._new_context(
                browser,
                destination,
                start_url=str(scene.capture_plan.start_url),
                session_token=session_token,
            )
            context.add_init_script(f"({POINTER_SCRIPT})();")
            page = context.new_page()
            video = page.video
            started = time.monotonic()
            page.set_default_timeout(15_000)
            try:
                page.goto(
                    str(scene.capture_plan.start_url), wait_until="networkidle", timeout=30_000
                )
                page.wait_for_timeout(400)
                offset_ms = round((time.monotonic() - started) * 1000)
                visible_start = time.monotonic()
                page.mouse.move(settings.viewport_width / 2, settings.viewport_height / 2)
                count = len(scene.capture_plan.actions)
                for index, action in enumerate(scene.capture_plan.actions):
                    target_time = 1 + index * ((duration_ms / 1000 - 4) / max(1, count - 1))
                    remaining = target_time - (time.monotonic() - visible_start)
                    if remaining > 0:
                        page.wait_for_timeout(remaining * 1000)
                    if action.locator:
                        target = _locator(page, action)
                        target.scroll_into_view_if_needed()
                        box = target.bounding_box()
                        if box is None:
                            raise ValueError("Capture target is not visible")
                        page.mouse.move(
                            box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=35
                        )
                        page.wait_for_timeout(250)
                    if action.type in {"click", "fill", "select"}:
                        events.append(worker._record_interaction(page, action, visible_start))
                    if action.type == "fill":
                        target = _locator(page, action)
                        target.click()
                        target.press_sequentially(str(action.value), delay=95)
                    else:
                        worker._execute(page, action)
                    logs.append(action.description)
                for assertion in scene.capture_plan.success_assertions:
                    worker._execute(page, assertion)
                remaining = duration_ms / 1000 + 0.7 - (time.monotonic() - visible_start)
                if remaining > 0:
                    page.wait_for_timeout(remaining * 1000)
                page.screenshot(path=str(destination / "last-frame.png"))
            except Exception:
                page.screenshot(path=str(destination / "failure.png"))
                raise
            finally:
                context.close()
                browser.close()
            if video is None:
                raise ValueError("Capture produced no video")
            raw = Path(video.path())
        trimmed = destination / "recording.mp4"
        run_ffmpeg(
            [
                "-ss",
                str(offset_ms / 1000),
                "-i",
                str(raw),
                "-t",
                str(duration_ms / 1000),
                "-an",
                "-vf",
                "fps=30",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                str(trimmed),
            ],
            self.output,
        )
        metadata = media_probe(trimmed)
        stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
        if (stream["width"], stream["height"]) != (
            settings.viewport_width,
            settings.viewport_height,
        ):
            raise ValueError("Recording dimensions do not match the authored product aperture")
        measured = float(metadata["format"]["duration"])
        if measured < duration_ms / 1000 - 0.04:
            raise ValueError("The captured recording is shorter than its slide")
        capture = SceneCaptureResult(
            scene_id=scene.id,
            status="succeeded",
            retryable=False,
            duration_ms=duration_ms,
            raw_clip_path=str(trimmed),
            interaction_events=[event for event in events if event.timestamp_ms < duration_ms],
            logs=logs,
        )
        if not any(event.event_type == "click" for event in capture.interaction_events):
            raise ValueError("Product slide has no recorded click")
        return trimmed, capture

    def copy_layer(self, template: dict[str, Any], copy: dict[str, str], output: Path) -> None:
        font = base64.b64encode(
            (PACK_ROOT / "shared/inter-latin-variable.woff2").read_bytes()
        ).decode()
        light = template["id"] in {"brand-promise@2", "brand-outro@2"}
        body_dark = template["id"] in {
            "context-split@2",
            "human-review@2",
            "trust-cards@2",
        }
        pieces = []
        for slot in template["copy_slots"]:
            key = slot["id"]
            if key == "caption":
                continue
            if key not in copy or len(copy[key]) > slot["max_characters"]:
                raise ValueError(f"Invalid copy for {key}")
            token = self.pack["typography"]["tokens"][slot["font_token"]]
            rect = slot["rect"]
            color = "#F3EDE1"
            if light or (body_dark and key not in {"chapter", "counter"}) or key == "prompt":
                color = "#0A211C"
            if template["id"] == "workflow-rail@2" and key == "result":
                color = "#0A211C"
            if key.startswith("activity_") and key.endswith("_label"):
                color = "#0A211C"
            elif key == "activity_heading" or key.endswith("_status"):
                color = "#9DE8D2"
            style = (
                f"left:{rect['x']}px;top:{rect['y']}px;width:{rect['width']}px;"
                f"height:{rect['height']}px;font-size:{token['size']}px;"
                f"line-height:{token['line_height']}px;font-weight:{token['weight']};"
                f"letter-spacing:{token['tracking']}px;text-align:{slot['align']};color:{color}"
            )
            pieces.append(
                f'<div data-slot="{key}" data-lines="{slot["max_lines"]}" '
                f'style="{style}"><span>{html.escape(copy[key])}</span></div>'
            )
        document = (
            '<!doctype html><meta charset="utf-8"><style>'
            f"@font-face{{font-family:Inter;src:url(data:font/woff2;base64,{font}) format('woff2');"
            "font-weight:100 900;}body{margin:0;background:transparent;}"
            "div{position:absolute;font-family:Inter;overflow:hidden;box-sizing:border-box;}"
            "</style>" + "".join(pieces)
        )
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 2560, "height": 1440})
            page.set_content(document)
            page.evaluate("document.fonts.ready")
            measurements = page.evaluate("""() =>
              [...document.querySelectorAll('[data-slot]')].map(el => {
                const initial = parseFloat(el.style.fontSize);
                const ratio = parseFloat(el.style.lineHeight) / initial;
                const span = el.firstElementChild;
                let size = initial;
                while(size >= initial * .72) {
                    el.style.fontSize = size + 'px'; el.style.lineHeight = size*ratio + 'px';
                    const lines = Math.round(span.getBoundingClientRect().height / (size*ratio));
                    if(el.scrollHeight <= el.clientHeight && el.scrollWidth <= el.clientWidth
                       && lines <= Number(el.dataset.lines))
                        return {slot:el.dataset.slot,size,lines,fits:true,
                                color:getComputedStyle(el).color};
                    size -= 1;
                }
                return {slot:el.dataset.slot,size,fits:false};
            })""")
            if any(not item["fits"] for item in measurements):
                browser.close()
                raise ValueError(f"Copy requires rewriting: {measurements}")
            page.screenshot(path=str(output), omit_background=True)
            browser.close()
        output.with_suffix(".json").write_text(json.dumps(measurements, indent=2), "utf-8")

    def compose(
        self,
        template: dict[str, Any],
        copy: dict[str, str],
        duration_ms: int,
        narration: Path,
        narration_text: str,
        product: Path | None,
        index: int,
        narration_beats: list[str] | None = None,
        *,
        zoom_clips: list[ZoomClip] | None = None,
        narration_duration: float | None = None,
    ) -> Path:
        directory = self.output / f"slide-{index + 1:02d}"
        directory.mkdir(exist_ok=True)
        self.copy_layer(template, copy, directory / "copy.png")
        background = PACK_ROOT / template["assets"]["background_png"]
        foreground = PACK_ROOT / template["assets"]["foreground_png"]
        duration = duration_ms / 1000
        caption_list = self.caption_images(
            narration_text, directory, narration_duration or duration, narration_beats
        )
        caption_video = directory / "captions.mov"
        run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(caption_list),
                "-vf",
                "fps=30",
                "-t",
                str(duration),
                "-c:v",
                "qtrle",
                "-threads",
                "2",
                str(caption_video),
            ],
            self.output,
        )
        inputs = [
            "-threads",
            "1",
            "-framerate",
            "30",
            "-loop",
            "1",
            "-i",
            str(background),
            "-threads",
            "1",
            "-framerate",
            "30",
            "-loop",
            "1",
            "-i",
            str(foreground),
            "-threads",
            "1",
            "-framerate",
            "30",
            "-loop",
            "1",
            "-i",
            str(directory / "copy.png"),
            "-threads",
            "1",
            "-i",
            str(narration),
            "-threads",
            "1",
            "-i",
            str(caption_video),
        ]
        filters = []
        if template["requires_product"]:
            if product is None:
                raise ValueError("A product slide requires its recorded product video")
            inputs += [
                "-threads",
                "1",
                "-i",
                str(product),
                "-threads",
                "1",
                "-framerate",
                "30",
                "-loop",
                "1",
                "-i",
                str(PACK_ROOT / template["assets"]["product_mask_png"]),
            ]
            a = template["product_aperture"]
            w, h, x, y = (a[k] for k in ["width", "height", "x", "y"])
            capture_settings_for_template(template)
            source = next(s for s in media_probe(product)["streams"] if s["codec_type"] == "video")
            if (source["width"], source["height"]) != (w, h):
                raise ValueError("Re-record this slide at its authored product aperture dimensions")
            product_label = "5:v"
            if zoom_clips:
                from demodirector_worker.renderer import FFmpegRenderer

                filters.append(
                    FFmpegRenderer(self.output, self.output)._zoom_filter(
                        zoom_clips, RenderConfig(width=w, height=h), product_label, "focused"
                    )
                )
                product_label = "focused"
            filters += [
                f"[{product_label}]setpts=PTS-STARTPTS,setsar=1,"
                f"pad=2560:1440:{x}:{y}:color=black[placed]",
                "[placed][6:v]alphamerge[masked]",
                "[0:v][masked]overlay=0:0:shortest=1[base]",
            ]
        else:
            filters += ["[0:v]null[base]"]
        filters += [
            "[base][1:v]overlay=0:0[frame]",
            "[2:v]format=rgba,fade=t=in:st=0:d=0.35:alpha=1[copy]",
            "[frame][copy]overlay=0:0[written]",
            "[written][4:v]overlay=500:1252:eof_action=repeat,format=yuv420p[v]",
            f"[3:a]apad,atrim=duration={duration},asetpts=PTS-STARTPTS[a]",
        ]
        output = directory / "composed.mp4"
        # Bound static inputs as well as the output so framesync cannot read an
        # endless image stream while waiting for a finite browser recording.
        for position in reversed(range(len(inputs))):
            if inputs[position] == "-loop":
                inputs[position:position] = ["-t", str(duration)]
        run_ffmpeg(
            [
                *inputs,
                "-filter_complex_threads",
                "1",
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-t",
                str(duration),
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-threads",
                "2",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(output),
            ],
            self.output,
        )
        return output

    def caption_images(
        self, text: str, directory: Path, duration: float, beats: list[str] | None = None
    ) -> Path:
        windows = [(duration - 4) / 2, (duration - 4) / 2, 4] if beats else [duration]
        chunks = []
        elapsed_ms = 0
        for beat, window in zip(beats or [text], windows, strict=True):
            words = beat.split()
            for offset in range(0, len(words), 7):
                chunk = words[offset : offset + 7]
                chunk_ms = round(window * 1000 * len(chunk) / len(words))
                chunks.extend(word_highlights(" ".join(chunk), elapsed_ms, elapsed_ms + chunk_ms))
                elapsed_ms += chunk_ms
        font = base64.b64encode(
            (PACK_ROOT / "shared/inter-latin-variable.woff2").read_bytes()
        ).decode()
        entries = []
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1560, "height": 104})
            page.set_content(
                '<!doctype html><meta charset="utf-8"><style>'
                f"@font-face{{font-family:Inter;src:url(data:font/woff2;base64,{font});}}"
                "body{margin:0;height:104px;display:flex;align-items:center;justify-content:center;"
                "font:44px/56px Inter;color:#F3EDE1;background:transparent;}"
                "span{display:inline-block;padding:4px 6px;border-radius:8px;vertical-align:top;}"
                ".active{background:#9DE8D2;color:#0A211C;}"
                "p{margin:0;white-space:nowrap}</style><p></p>"
            )
            page.evaluate("async () => { await document.fonts.load('44px Inter'); }")
            phrase: tuple[str, ...] = ()
            for index, state in enumerate(chunks):
                start_frame, end_frame = highlight_frame_window(state)
                if end_frame <= start_frame:
                    continue
                if state.words != phrase:
                    phrase = state.words
                    markup = " ".join(f"<span>{html.escape(word)}</span>" for word in phrase)
                    page.locator("p").evaluate(
                        "(element, markup) => element.innerHTML = markup", markup
                    )
                # Only paint changes within a phrase: no font reload or text reflow.
                page.locator("p").evaluate(
                    "(element, active) => Array.from(element.children).forEach((word, index) => "
                    "word.classList.toggle('active', index === active))",
                    state.word_index,
                )
                name = f"caption-{index:03d}.png"
                page.screenshot(path=str(directory / name), omit_background=True)
                entries += [
                    f"file '{name}'",
                    "option framerate 30",
                    f"duration {(end_frame - start_frame) / 30:.9f}",
                ]
            browser.close()
        if not entries:
            raise ValueError("Captions require at least one visible word.")
        entries.extend([entries[-3], "option framerate 30"])
        caption_list = directory / "captions.txt"
        caption_list.write_text("\n".join(entries) + "\n", "utf-8")
        return caption_list
