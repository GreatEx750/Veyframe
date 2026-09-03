from __future__ import annotations

import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from demodirector_api.auth import (
    AuthService,
    AuthSettings,
    SQLiteAuthRepository,
    UnavailableIdentityProvider,
)
from demodirector_contracts import (
    AudioClip,
    CaptionStyleConfig,
    CapturePlan,
    NarrationVoiceConfig,
    RenderConfig,
    Scene,
    SceneClip,
    Timeline,
    UserIdentity,
    UserProfile,
)
from demodirector_worker import (
    CaptionService,
    FFmpegRenderer,
    FFmpegSettings,
    GeminiTTSAdapter,
    GeminiTTSSettings,
    NarrationService,
)
from playwright.sync_api import Page, sync_playwright
from pydantic import HttpUrl

BASE_URL = "http://localhost:3000"
DEMO_DURATION_SECONDS = 20


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
    raise RuntimeError(f"{name} is required to generate the local demo video")


def hold_until(page: Page, started: float, target_seconds: float) -> None:
    remaining_ms = round((target_seconds - (time.monotonic() - started)) * 1_000)
    if remaining_ms > 0:
        page.wait_for_timeout(remaining_ms)


def issue_local_customer_session(database_path: Path, run_id: str) -> str:
    repository = SQLiteAuthRepository(database_path)
    auth = AuthService(
        UnavailableIdentityProvider(),
        repository,
        AuthSettings(required=True, session_ttl_seconds=3_600),
    )
    identity = UserIdentity(
        user_id=f"local-demo-{run_id}",
        email=f"local-demo-{run_id}@demodirector.local",
        role="customer",
        email_verified=True,
    )
    now = datetime.now(UTC)
    repository.save_profile(
        UserProfile(
            user_id=identity.user_id,
            email=identity.email,
            role=identity.role,
            created_at=now,
            updated_at=now,
        )
    )
    token, _summary = auth.issue_session(identity)
    return token


def capture_product_flow(artifact_root: Path, session_token: str) -> Path:
    video_directory = artifact_root / "capture"
    video_directory.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=str(video_directory),
            record_video_size={"width": 1280, "height": 720},
        )
        context.add_cookies(
            [
                {
                    "name": "demodirector_session",
                    "value": session_token,
                    "url": BASE_URL,
                    "httpOnly": True,
                    "sameSite": "Lax",
                }
            ]
        )
        page = context.new_page()
        recording = page.video
        started = time.monotonic()

        page.goto(f"{BASE_URL}/projects", wait_until="domcontentloaded")
        page.get_by_role("heading", name="Projects", exact=True).wait_for()
        hold_until(page, started, 2.5)

        page.get_by_role("link", name="+ New demo", exact=True).click()
        page.get_by_role("heading", name="Create product demo", exact=True).wait_for()
        hold_until(page, started, 5.0)

        page.get_by_label("Website URL", exact=False).fill(BASE_URL)
        page.get_by_label("Describe your video", exact=False).fill(
            "Create a concise product tour that introduces DemoDirector, shows the "
            "natural-language video brief and editing controls, and ends in the project "
            "library ready for the next cut."
        )
        hold_until(page, started, 9.0)

        page.get_by_label("Target Audience", exact=True).select_option(label="Product leaders")
        page.get_by_label("Length", exact=True).select_option("60")
        page.get_by_label("Call to Action", exact=True).fill("Create your first product demo")
        hold_until(page, started, 12.0)

        page.get_by_role("button", name="Generate Storyboard", exact=True).click()
        page.get_by_role("status").filter(has_text="Project saved").wait_for(timeout=10_000)
        hold_until(page, started, 16.0)

        navigation = page.get_by_role("navigation", name="Primary navigation")
        navigation.get_by_role("link", name="Projects", exact=True).click()
        page.get_by_role("heading", name="Projects", exact=True).wait_for()
        page.get_by_role("heading", name="Untitled demo", exact=True).wait_for()
        hold_until(page, started, 21.0)

        context.close()
        if recording is None:
            browser.close()
            raise RuntimeError("Browser recording was not available")
        raw_video = Path(recording.path()).resolve()
        browser.close()
    if not raw_video.is_file():
        raise RuntimeError("Browser recording was not written")
    return raw_video


def build_timeline(artifact_root: Path, raw_video: Path, run_id: str) -> Timeline:
    narration_text = (
        "Start with your product website, describe the video you want, and set the "
        "audience and tone. "
        "DemoDirector saves the project and keeps every demo organized for editing."
    )
    scene = Scene(
        id=f"scene-{run_id}",
        storyboard_id=f"storyboard-{run_id}",
        order=0,
        title="Create a DemoDirector project",
        objective="Show the live local project creation workflow",
        narration=narration_text,
        source_ids=["local-app"],
        capture_plan=CapturePlan(
            start_url=HttpUrl(BASE_URL),
            actions=[],
            success_assertions=[],
            timeout_seconds=30,
        ),
        expected_evidence=["The new project appears in the project library"],
        duration_seconds=DEMO_DURATION_SECONDS,
    )
    narration = NarrationService(
        GeminiTTSAdapter(GeminiTTSSettings.from_environment()),
        artifact_root / "narration",
    ).generate([scene], NarrationVoiceConfig(), capture_clip_paths=[str(raw_video)])
    if narration.status != "succeeded" or not narration.segments:
        raise RuntimeError(narration.error or "Gemini narration did not complete")
    segment = narration.segments[0]
    audio_duration = min(segment.duration_ms, DEMO_DURATION_SECONDS * 1_000)
    caption_track = CaptionService().generate_track(
        segment.model_copy(update={"duration_ms": audio_duration}),
        CaptionStyleConfig(enabled=True),
    )
    return Timeline(
        project_id=f"local-demo-{run_id}",
        duration_ms=DEMO_DURATION_SECONDS * 1_000,
        scene_clips=[
            SceneClip(
                id=f"scene-clip-{run_id}",
                scene_id=scene.id,
                start_ms=0,
                end_ms=DEMO_DURATION_SECONDS * 1_000,
                source_uri=str(raw_video),
            )
        ],
        caption_clips=caption_track.clips,
        zoom_clips=[],
        audio_clips=[
            AudioClip(
                id=f"audio-{run_id}",
                scene_id=scene.id,
                start_ms=0,
                end_ms=audio_duration,
                source_uri=segment.audio_path,
            )
        ],
    )


def main() -> None:
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    artifact_root = (Path("artifacts") / f"localhost-demo-{run_id}").resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    database_path = Path(os.getenv("DEMO_DATABASE_PATH", "artifacts/demodirector.db"))
    session_token = issue_local_customer_session(database_path, run_id)
    raw_video = capture_product_flow(artifact_root, session_token)
    timeline = build_timeline(artifact_root, raw_video, run_id)
    renderer = FFmpegRenderer(
        artifact_root,
        artifact_root / "output",
        FFmpegSettings(
            ffmpeg_path=media_binary("ffmpeg"),
            ffprobe_path=media_binary("ffprobe"),
            timeout_seconds=120,
        ),
    )
    result = renderer.render(
        timeline,
        RenderConfig(
            width=1280,
            height=720,
            output_filename="demodirector-localhost-demo-20s.mp4",
        ),
    )
    if result.status != "succeeded" or result.output_path is None:
        raise RuntimeError(result.error or "Demo render failed")
    print(f"output={result.output_path}")
    print(f"thumbnail={result.thumbnail_path}")
    print(f"duration_ms={result.duration_ms}")
    print(f"resolution={result.width}x{result.height}")
    print(f"has_audio={result.has_audio}")
    print(f"bytes={Path(result.output_path).stat().st_size}")


if __name__ == "__main__":
    main()
