from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol
from urllib.parse import quote
from uuid import uuid4

from demodirector_contracts import RenderConfig, RenderResult, Timeline, VideoExport


class ExportError(RuntimeError):
    """Raised when export metadata or download authorization is invalid."""


class TimelineRenderer(Protocol):
    def render(self, timeline: Timeline, config: RenderConfig) -> RenderResult: ...


@dataclass(frozen=True, slots=True)
class StoredExport:
    export: VideoExport
    file_path: str | None
    token_hash: str | None


class ExportRepository(Protocol):
    def save(self, item: StoredExport) -> StoredExport: ...

    def get(self, project_id: str, export_id: str) -> StoredExport | None: ...

    def latest_successful(self, project_id: str) -> StoredExport | None: ...


class ExportArtifactStore(Protocol):
    def persist(self, path: Path, project_id: str, export_id: str) -> str: ...

    def resolve(self, reference: str) -> Path | None: ...


class TimelineMediaStore(Protocol):
    def persist(self, timeline: Timeline) -> Timeline: ...

    def materialize(self, timeline: Timeline) -> Timeline: ...


class LocalTimelineMediaStore:
    def persist(self, timeline: Timeline) -> Timeline:
        return timeline

    def materialize(self, timeline: Timeline) -> Timeline:
        return timeline


class LocalExportArtifactStore:
    def __init__(self, artifact_directory: Path) -> None:
        self.artifact_directory = artifact_directory.resolve()

    def persist(self, path: Path, project_id: str, export_id: str) -> str:
        del project_id, export_id
        approved = self._approved(path)
        return str(approved)

    def resolve(self, reference: str) -> Path | None:
        try:
            path = self._approved(Path(reference))
        except ExportError:
            return None
        return path if path.is_file() and path.stat().st_size > 0 else None

    def _approved(self, supplied: Path) -> Path:
        path = supplied.resolve()
        if path != self.artifact_directory and self.artifact_directory not in path.parents:
            raise ExportError("Export path is outside the approved artifact directory.")
        return path


class CloudBlob(Protocol):
    def upload_from_filename(self, filename: str) -> None: ...

    def exists(self) -> bool: ...

    def download_to_filename(self, filename: str) -> None: ...


class CloudBucket(Protocol):
    name: str

    def blob(self, name: str) -> CloudBlob: ...


class CloudExportArtifactStore:
    """Stores completed MP4s durably and restores a safe local streaming cache."""

    def __init__(self, bucket: CloudBucket, cache_directory: Path) -> None:
        self.bucket = bucket
        self.cache_directory = cache_directory.resolve()

    def persist(self, path: Path, project_id: str, export_id: str) -> str:
        object_name = (
            f"exports/{_safe_component(project_id)}/"
            f"{_safe_component(export_id)}/{path.name}"
        )
        self.bucket.blob(object_name).upload_from_filename(str(path))
        return f"gs://{self.bucket.name}/{object_name}"

    def resolve(self, reference: str) -> Path | None:
        prefix = f"gs://{self.bucket.name}/"
        if not reference.startswith(prefix):
            return None
        object_name = reference.removeprefix(prefix)
        object_path = PurePosixPath(object_name)
        if (
            not object_name.startswith("exports/")
            or object_path.is_absolute()
            or ".." in object_path.parts
        ):
            return None
        destination = (self.cache_directory / Path(*object_path.parts)).resolve()
        if self.cache_directory not in destination.parents:
            return None
        blob = self.bucket.blob(object_name)
        if not blob.exists():
            return None
        if not destination.is_file() or destination.stat().st_size == 0:
            destination.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(destination))
        return destination if destination.is_file() and destination.stat().st_size > 0 else None


class CloudTimelineMediaStore:
    """Moves capture and narration inputs to object storage for later re-exports."""

    def __init__(self, bucket: CloudBucket, source_root: Path, cache_directory: Path) -> None:
        self.bucket = bucket
        self.source_root = source_root.resolve()
        self.cache_directory = cache_directory.resolve()

    def persist(self, timeline: Timeline) -> Timeline:
        project_id = _safe_component(timeline.project_id)

        def upload(reference: str) -> str:
            if reference.startswith(f"gs://{self.bucket.name}/timeline-media/"):
                return reference
            source = Path(reference).resolve()
            if self.source_root not in source.parents or not source.is_file():
                raise ExportError("Timeline media is outside the approved artifact directory.")
            fingerprint = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:16]
            filename = _safe_filename(source.name)
            object_name = f"timeline-media/{project_id}/{fingerprint}/{filename}"
            self.bucket.blob(object_name).upload_from_filename(str(source))
            return f"gs://{self.bucket.name}/{object_name}"

        return timeline.model_copy(
            update={
                "scene_clips": [
                    clip.model_copy(update={"source_uri": upload(clip.source_uri)})
                    for clip in timeline.scene_clips
                ],
                "audio_clips": [
                    clip.model_copy(update={"source_uri": upload(clip.source_uri)})
                    for clip in timeline.audio_clips
                ],
            }
        )

    def materialize(self, timeline: Timeline) -> Timeline:
        def download(reference: str) -> str:
            prefix = f"gs://{self.bucket.name}/"
            if not reference.startswith(prefix):
                return reference
            object_name = reference.removeprefix(prefix)
            object_path = PurePosixPath(object_name)
            if (
                not object_name.startswith("timeline-media/")
                or object_path.is_absolute()
                or ".." in object_path.parts
            ):
                raise ExportError("Timeline media reference is not approved.")
            destination = (self.cache_directory / Path(*object_path.parts)).resolve()
            if self.cache_directory not in destination.parents:
                raise ExportError("Timeline media cache path is not approved.")
            blob = self.bucket.blob(object_name)
            if not blob.exists():
                raise ExportError("Timeline media is unavailable in object storage.")
            if not destination.is_file() or destination.stat().st_size == 0:
                destination.parent.mkdir(parents=True, exist_ok=True)
                blob.download_to_filename(str(destination))
            return str(destination)

        return timeline.model_copy(
            update={
                "scene_clips": [
                    clip.model_copy(update={"source_uri": download(clip.source_uri)})
                    for clip in timeline.scene_clips
                ],
                "audio_clips": [
                    clip.model_copy(update={"source_uri": download(clip.source_uri)})
                    for clip in timeline.audio_clips
                ],
            }
        )


class SQLiteExportRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS video_exports (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    file_path TEXT,
                    token_hash TEXT
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def save(self, item: StoredExport) -> StoredExport:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO video_exports (
                    id, project_id, payload, file_path, token_hash
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item.export.id,
                    item.export.project_id,
                    item.export.model_dump_json(),
                    item.file_path,
                    item.token_hash,
                ),
            )
        return item

    def get(self, project_id: str, export_id: str) -> StoredExport | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload, file_path, token_hash
                FROM video_exports WHERE id = ? AND project_id = ?
                """,
                (export_id, project_id),
            ).fetchone()
        if row is None:
            return None
        return StoredExport(
            export=VideoExport.model_validate_json(row[0]),
            file_path=row[1],
            token_hash=row[2],
        )

    def latest_successful(self, project_id: str) -> StoredExport | None:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload, file_path, token_hash
                FROM video_exports WHERE project_id = ? ORDER BY rowid DESC
                """,
                (project_id,),
            ).fetchall()
        for row in rows:
            video_export = VideoExport.model_validate_json(row[0])
            if video_export.status == "succeeded":
                return StoredExport(
                    export=video_export,
                    file_path=row[1],
                    token_hash=row[2],
                )
        return None


class ExportService:
    def __init__(
        self,
        renderer: TimelineRenderer,
        repository: ExportRepository,
        artifact_directory: Path,
        artifact_store: ExportArtifactStore | None = None,
        timeline_media_store: TimelineMediaStore | None = None,
    ) -> None:
        self.renderer = renderer
        self.repository = repository
        self.artifact_directory = artifact_directory.resolve()
        self.artifact_store = artifact_store or LocalExportArtifactStore(self.artifact_directory)
        self.timeline_media_store = timeline_media_store or LocalTimelineMediaStore()

    def create(
        self,
        project_id: str,
        timeline: Timeline,
        quality: Literal["1080p", "720p"],
    ) -> VideoExport:
        if timeline.project_id != project_id:
            raise ExportError("Export timeline does not belong to the requested project.")
        if quality not in {"1080p", "720p"}:
            raise ExportError("Export quality must be 1080p or 720p.")
        export_id = str(uuid4())
        filename = f"demodirector-{project_id}-{export_id}.mp4"
        width, height = (1920, 1080) if quality == "1080p" else (1280, 720)
        try:
            rendered = self.renderer.render(
                self.timeline_media_store.materialize(timeline),
                RenderConfig(
                    width=width,
                    height=height,
                    fps=30,
                    output_filename=filename,
                ),
            )
            if rendered.status != "succeeded" or rendered.output_path is None:
                raise ExportError(rendered.error or "Renderer did not produce an export file.")
            path = self._safe_export_path(rendered.output_path)
            if not path.is_file() or path.stat().st_size == 0:
                raise ExportError("Renderer output is missing or empty.")
            artifact_reference = self.artifact_store.persist(path, project_id, export_id)
            token = secrets.token_urlsafe(24)
            export = VideoExport(
                id=export_id,
                project_id=project_id,
                status="succeeded",
                quality=quality,
                filename=filename,
                width=rendered.width,
                height=rendered.height,
                duration_ms=rendered.duration_ms,
                size_bytes=path.stat().st_size,
                thumbnail_path=rendered.thumbnail_path,
                download_url=(
                    f"/projects/{quote(project_id)}/exports/{quote(export_id)}/download"
                    f"?token={quote(token)}"
                ),
                retryable=False,
                created_at=datetime.now(UTC),
            )
            self.repository.save(
                StoredExport(
                    export=export,
                    file_path=artifact_reference,
                    token_hash=_token_hash(token),
                )
            )
            return export
        except Exception as error:
            failed = VideoExport(
                id=export_id,
                project_id=project_id,
                status="failed",
                quality=quality,
                filename=filename,
                width=width,
                height=height,
                duration_ms=timeline.duration_ms,
                size_bytes=0,
                retryable=True,
                error=f"Export failed: {error}",
                created_at=datetime.now(UTC),
            )
            self.repository.save(StoredExport(failed, None, None))
            return failed

    def get(self, project_id: str, export_id: str) -> VideoExport | None:
        item = self.repository.get(project_id, export_id)
        return None if item is None else item.export

    def latest(self, project_id: str) -> VideoExport | None:
        item = self.repository.latest_successful(project_id)
        if item is None or item.file_path is None:
            return None
        path = self.artifact_store.resolve(item.file_path)
        return item.export if path is not None else None

    def latest_path(self, project_id: str) -> Path:
        item = self.repository.latest_successful(project_id)
        if item is None or item.file_path is None:
            raise ExportError("No completed video is available for this project.")
        path = self.artifact_store.resolve(item.file_path)
        if path is None:
            raise ExportError("The completed video file is unavailable.")
        return path

    def authorize_download(self, project_id: str, export_id: str, token: str) -> Path:
        item = self.repository.get(project_id, export_id)
        if item is None or item.export.status != "succeeded":
            raise ExportError("Export was not found.")
        if item.token_hash is None or not hmac.compare_digest(item.token_hash, _token_hash(token)):
            raise PermissionError("Export download token is invalid.")
        if item.file_path is None:
            raise ExportError("Export file is unavailable.")
        path = self.artifact_store.resolve(item.file_path)
        if path is None:
            raise ExportError("Export file is unavailable.")
        return path

    def _safe_export_path(self, supplied: str) -> Path:
        path = Path(supplied).resolve()
        if path != self.artifact_directory and self.artifact_directory not in path.parents:
            raise ExportError("Export path is outside the approved artifact directory.")
        return path


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _safe_component(value: str) -> str:
    if not value or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for character in value
    ):
        raise ExportError("Cloud artifact identifier contains unsupported characters.")
    return value


def _safe_filename(value: str) -> str:
    if Path(value).name != value or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
        for character in value
    ):
        raise ExportError("Cloud artifact filename contains unsupported characters.")
    return value
