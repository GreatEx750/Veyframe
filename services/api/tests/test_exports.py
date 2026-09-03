from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from demodirector_api.exports import (
    CloudExportArtifactStore,
    CloudTimelineMediaStore,
    ExportService,
    SQLiteExportRepository,
)
from demodirector_api.main import create_app
from demodirector_api.repositories import SQLiteProjectRepository
from demodirector_contracts import Project, RenderConfig, RenderResult, Timeline
from demodirector_worker import FFmpegRenderer, FFmpegSettings
from fastapi.testclient import TestClient


def media_binary(name: str) -> str:
    discovered = shutil.which(name)
    if discovered:
        return discovered
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        matches = sorted(root.glob(f"Gyan.FFmpeg*/*/bin/{name}.exe"))
        if matches:
            return str(matches[0])
    pytest.skip(f"{name} is required for the export integration test")


def timeline(video: Path, audio: Path) -> Timeline:
    return Timeline.model_validate(
        {
            "project_id": "project-1",
            "duration_ms": 2_000,
            "scene_clips": [
                {
                    "id": "scene-1",
                    "scene_id": "scene-1",
                    "start_ms": 0,
                    "end_ms": 2_000,
                    "source_uri": str(video),
                }
            ],
            "caption_clips": [],
            "zoom_clips": [],
            "audio_clips": [
                {
                    "id": "audio-1",
                    "scene_id": "scene-1",
                    "start_ms": 0,
                    "end_ms": 2_000,
                    "source_uri": str(audio),
                }
            ],
        }
    )


def create_media(root: Path, ffmpeg: str) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    video = root / "scene.mp4"
    audio = root / "audio.wav"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x172033:s=640x360:d=2:r=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            str(audio),
        ],
        check=True,
    )
    return video, audio


class FileRenderer:
    def __init__(self, output_directory: Path) -> None:
        self.output_directory = output_directory

    def render(self, timeline: Timeline, config: RenderConfig) -> RenderResult:
        self.output_directory.mkdir(parents=True, exist_ok=True)
        output = self.output_directory / config.output_filename
        output.write_bytes(b"small mp4 fixture")
        thumbnail = self.output_directory / "thumbnail.jpg"
        thumbnail.write_bytes(b"jpeg")
        return RenderResult(
            status="succeeded",
            output_path=str(output),
            thumbnail_path=str(thumbnail),
            duration_ms=timeline.duration_ms,
            width=config.width,
            height=config.height,
            has_video=True,
            has_audio=True,
        )


class FailingRenderer:
    def render(self, timeline: Timeline, config: RenderConfig) -> RenderResult:
        del timeline, config
        raise RuntimeError("temporary encoder failure")


class MemoryBlob:
    def __init__(self, objects: dict[str, bytes], name: str) -> None:
        self.objects = objects
        self.name = name

    def upload_from_filename(self, filename: str) -> None:
        self.objects[self.name] = Path(filename).read_bytes()

    def exists(self) -> bool:
        return self.name in self.objects

    def download_to_filename(self, filename: str) -> None:
        Path(filename).write_bytes(self.objects[self.name])


class MemoryBucket:
    name = "demo-bucket"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def blob(self, name: str) -> MemoryBlob:
        return MemoryBlob(self.objects, name)


def project() -> Project:
    now = datetime.now(UTC)
    return Project.model_validate(
        {
            "id": "project-1",
            "name": "Export demo",
            "website_url": "https://example.com",
            "product_summary": "Export fixture",
            "audience": "Product leaders",
            "tone": "Professional",
            "requested_duration_seconds": 20,
            "cta": "Try it",
            "created_at": now,
            "updated_at": now,
        }
    )


def test_1440p_export_is_ffprobe_valid(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    ffmpeg = media_binary("ffmpeg")
    ffprobe = media_binary("ffprobe")
    video, audio = create_media(artifact_root / "media", ffmpeg)
    export_root = artifact_root / "exports"
    service = ExportService(
        FFmpegRenderer(
            artifact_root,
            export_root,
            FFmpegSettings(ffmpeg_path=ffmpeg, ffprobe_path=ffprobe, timeout_seconds=60),
        ),
        SQLiteExportRepository(tmp_path / "exports.db"),
        export_root,
    )

    result = service.create("project-1", timeline(video, audio), "1440p")

    assert result.status == "succeeded"
    assert (result.width, result.height) == (2560, 1440)
    assert result.duration_ms == pytest.approx(2_000, abs=150)
    assert result.download_url is not None


def test_download_route_requires_project_scoped_token(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    export_root = artifact_root / "exports"
    service = ExportService(
        FileRenderer(export_root),
        SQLiteExportRepository(tmp_path / "exports.db"),
        export_root,
    )
    projects = SQLiteProjectRepository(tmp_path / "projects.db")
    projects.create(project())
    app = create_app(repository=projects)
    app.state.export_service = service
    client = TestClient(app)
    fixture_timeline = Timeline(
        project_id="project-1",
        duration_ms=1_000,
        scene_clips=[],
    )

    response = client.post(
        "/projects/project-1/exports",
        json={"timeline": fixture_timeline.model_dump(mode="json"), "quality": "1080p"},
    )

    assert response.status_code == 200
    export = response.json()
    token = parse_qs(urlparse(export["download_url"]).query)["token"][0]
    download = client.get(
        f"/projects/project-1/exports/{export['id']}/download",
        params={"token": token},
    )
    forbidden = client.get(
        f"/projects/project-1/exports/{export['id']}/download",
        params={"token": "wrong-token-that-is-long-enough"},
    )
    assert download.status_code == 200
    assert download.headers["content-type"] == "video/mp4"
    assert forbidden.status_code == 403
    latest = client.get("/projects/project-1/exports/latest")
    latest_video = client.get("/projects/project-1/exports/latest/video")
    assert latest.status_code == 200
    assert latest.json()["id"] == export["id"]
    assert latest_video.status_code == 200
    assert latest_video.headers["content-type"] == "video/mp4"
    assert latest_video.content == b"small mp4 fixture"


def test_export_failure_is_persisted_as_retryable(tmp_path: Path) -> None:
    service = ExportService(
        FailingRenderer(),
        SQLiteExportRepository(tmp_path / "exports.db"),
        tmp_path / "exports",
    )
    fixture_timeline = Timeline(
        project_id="project-1",
        duration_ms=1_000,
        scene_clips=[],
    )

    result = service.create("project-1", fixture_timeline, "720p")

    assert result.status == "failed"
    assert result.retryable is True
    assert service.get("project-1", result.id) == result


def test_latest_export_keeps_the_most_recent_success_when_a_retry_fails(
    tmp_path: Path,
) -> None:
    repository = SQLiteExportRepository(tmp_path / "exports.db")
    export_root = tmp_path / "exports"
    successful_service = ExportService(FileRenderer(export_root), repository, export_root)
    successful = successful_service.create(
        "project-1",
        Timeline(project_id="project-1", duration_ms=1_000, scene_clips=[]),
        "1080p",
    )
    failed_service = ExportService(FailingRenderer(), repository, export_root)
    failed_service.create(
        "project-1",
        Timeline(project_id="project-1", duration_ms=1_000, scene_clips=[]),
        "1080p",
    )

    assert successful_service.latest("project-1") == successful
    assert successful_service.latest_path("project-1").read_bytes() == b"small mp4 fixture"


def test_cloud_artifact_store_restores_export_after_local_file_is_removed(tmp_path: Path) -> None:
    repository = SQLiteExportRepository(tmp_path / "exports.db")
    bucket = MemoryBucket()
    first_root = tmp_path / "first" / "exports"
    service = ExportService(
        FileRenderer(first_root),
        repository,
        first_root,
        artifact_store=CloudExportArtifactStore(bucket, tmp_path / "first-cache"),
    )
    result = service.create(
        "project-1",
        Timeline(project_id="project-1", duration_ms=1_000, scene_clips=[]),
        "1080p",
    )
    assert result.status == "succeeded"
    shutil.rmtree(tmp_path / "first")

    restored_service = ExportService(
        FileRenderer(tmp_path / "unused"),
        repository,
        tmp_path / "unused",
        artifact_store=CloudExportArtifactStore(bucket, tmp_path / "restored-cache"),
    )

    assert restored_service.latest("project-1") == result
    assert restored_service.latest_path("project-1").read_bytes() == b"small mp4 fixture"


def test_cloud_timeline_media_survives_local_capture_cleanup(tmp_path: Path) -> None:
    source_root = tmp_path / "artifacts"
    video = source_root / "captures" / "recording.webm"
    audio = source_root / "narration" / "voice.wav"
    video.parent.mkdir(parents=True)
    audio.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    source_timeline = Timeline.model_validate(
        {
            "project_id": "project-1",
            "duration_ms": 1_000,
            "scene_clips": [
                {
                    "id": "scene-clip-1",
                    "scene_id": "scene-1",
                    "start_ms": 0,
                    "end_ms": 1_000,
                    "source_uri": str(video),
                }
            ],
            "audio_clips": [
                {
                    "id": "audio-clip-1",
                    "scene_id": "scene-1",
                    "start_ms": 0,
                    "end_ms": 1_000,
                    "source_uri": str(audio),
                }
            ],
        }
    )
    bucket = MemoryBucket()
    store = CloudTimelineMediaStore(bucket, source_root, tmp_path / "cache")

    persisted = store.persist(source_timeline)
    shutil.rmtree(source_root)
    restored = store.materialize(persisted)

    assert persisted.scene_clips[0].source_uri.startswith("gs://demo-bucket/timeline-media/")
    assert Path(restored.scene_clips[0].source_uri).read_bytes() == b"video"
    assert Path(restored.audio_clips[0].source_uri).read_bytes() == b"audio"
