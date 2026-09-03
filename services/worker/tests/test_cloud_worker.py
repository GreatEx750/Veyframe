from __future__ import annotations

from pathlib import Path

import pytest
from demodirector_contracts import CapturePlan, Scene, SceneCaptureResult
from demodirector_worker.app import create_worker_app
from demodirector_worker.cloud_storage import CloudStorageArtifactStore
from fastapi.testclient import TestClient
from pydantic import HttpUrl


class Blob:
    def __init__(self, name: str) -> None:
        self.name = name
        self.filename = ""

    def upload_from_filename(self, filename: str) -> None:
        self.filename = filename


class Bucket:
    name = "fixture-bucket"

    def __init__(self) -> None:
        self.created: list[Blob] = []

    def blob(self, name: str) -> Blob:
        blob = Blob(name)
        self.created.append(blob)
        return blob


class StorageClient:
    def __init__(self) -> None:
        self.fixture_bucket = Bucket()

    def bucket(self, name: str) -> Bucket:
        assert name == "fixture-bucket"
        return self.fixture_bucket


def test_storage_upload_is_project_scoped_and_rejects_path_traversal(tmp_path: Path) -> None:
    path = tmp_path / "clip.webm"
    path.write_bytes(b"video")
    client = StorageClient()
    store = CloudStorageArtifactStore(client, "fixture-bucket")

    uri = store.upload_capture("project-1", "scene-1", path)

    assert uri == "gs://fixture-bucket/captures/project-1/scene-1/clip.webm"
    assert client.fixture_bucket.created[0].filename == str(path)
    with pytest.raises(ValueError):
        store.upload_capture("../other", "scene-1", path)


def scene() -> Scene:
    return Scene(
        id="scene-1",
        storyboard_id="storyboard-1",
        order=0,
        title="Dashboard",
        objective="Show dashboard",
        narration="Review the dashboard.",
        capture_plan=CapturePlan(
            start_url=HttpUrl("https://example.com"),
            actions=[],
            success_assertions=[],
            timeout_seconds=30,
        ),
        duration_seconds=5,
    )


class Runner:
    def __init__(self, clip: Path) -> None:
        self.clip = clip

    def capture_scene(self, scene: Scene) -> SceneCaptureResult:
        return SceneCaptureResult(
            scene_id=scene.id,
            status="succeeded",
            retryable=False,
            duration_ms=100,
            raw_clip_path=str(self.clip),
            logs=["captured"],
        )


class Store:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str]] = []

    def upload_capture(self, project_id: str, scene_id: str, path: str | Path) -> str:
        self.uploads.append((project_id, scene_id, str(path)))
        return f"gs://fixture/{project_id}/{scene_id}/{Path(path).name}"


def test_private_worker_boundary_captures_and_uploads_artifact(tmp_path: Path) -> None:
    clip = tmp_path / "clip.webm"
    clip.write_bytes(b"video")
    store = Store()
    client = TestClient(create_worker_app(Runner(clip), store))

    response = client.post(
        "/tasks/capture", json={"project_id": "project-1", "scene": scene().model_dump(mode="json")}
    )

    assert response.status_code == 200
    assert response.json()["artifact_uris"] == ["gs://fixture/project-1/scene-1/clip.webm"]
    assert store.uploads == [("project-1", "scene-1", str(clip))]
