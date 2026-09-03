from __future__ import annotations

from pathlib import Path, PurePosixPath

from google.cloud.storage import Client  # type: ignore[import-untyped]


class CloudStorageArtifactStore:
    def __init__(self, client: Client, bucket_name: str) -> None:
        self.bucket = client.bucket(bucket_name)

    def upload_capture(self, project_id: str, scene_id: str, path: str | Path) -> str:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        safe_project = _safe_segment(project_id)
        safe_scene = _safe_segment(scene_id)
        object_name = str(PurePosixPath("captures", safe_project, safe_scene, source.name))
        self.bucket.blob(object_name).upload_from_filename(str(source))
        return f"gs://{self.bucket.name}/{object_name}"


def _safe_segment(value: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("artifact path segments must be non-empty identifiers")
    return value
