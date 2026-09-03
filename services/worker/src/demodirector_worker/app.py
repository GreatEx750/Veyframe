from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from demodirector_contracts import Scene, SceneCaptureResult
from fastapi import FastAPI, HTTPException
from google.cloud.storage import Client  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from demodirector_worker.capture import PlaywrightCaptureWorker
from demodirector_worker.cloud_storage import CloudStorageArtifactStore


class CaptureRunner(Protocol):
    def capture_scene(self, scene: Scene) -> SceneCaptureResult: ...


class ArtifactStore(Protocol):
    def upload_capture(self, project_id: str, scene_id: str, path: str | Path) -> str: ...


class CaptureTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    scene: Scene


class CaptureTaskResponse(BaseModel):
    status: str
    scene_id: str
    artifact_uris: list[str]
    error: str | None = None


def create_worker_app(
    runner: CaptureRunner | None = None,
    store: ArtifactStore | None = None,
) -> FastAPI:
    application = FastAPI(title="DemoDirector Capture Worker", version="0.1.0")
    resolved_runner = runner or PlaywrightCaptureWorker(Path("/tmp/demodirector/captures"))
    bucket = os.getenv("DEMO_ARTIFACT_BUCKET")
    resolved_store = store
    if resolved_store is None and bucket:
        resolved_store = CloudStorageArtifactStore(Client(), bucket)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "worker"}

    @application.post("/tasks/capture", response_model=CaptureTaskResponse)
    def capture(payload: CaptureTaskRequest) -> CaptureTaskResponse:
        if resolved_store is None:
            raise HTTPException(status_code=503, detail="Artifact bucket is not configured.")
        result = resolved_runner.capture_scene(payload.scene)
        paths = ([result.raw_clip_path] if result.raw_clip_path else []) + result.screenshot_paths
        artifact_uris = [
            resolved_store.upload_capture(payload.project_id, payload.scene.id, path)
            for path in paths
        ]
        return CaptureTaskResponse(
            status=result.status,
            scene_id=result.scene_id,
            artifact_uris=artifact_uris,
            error=result.error,
        )

    return application


app = create_worker_app()
