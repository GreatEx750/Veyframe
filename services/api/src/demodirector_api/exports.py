from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
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
    ) -> None:
        self.renderer = renderer
        self.repository = repository
        self.artifact_directory = artifact_directory.resolve()

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
                timeline,
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
                    file_path=str(path),
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
        try:
            path = self._safe_export_path(item.file_path)
        except ExportError:
            return None
        return item.export if path.is_file() and path.stat().st_size > 0 else None

    def latest_path(self, project_id: str) -> Path:
        item = self.repository.latest_successful(project_id)
        if item is None or item.file_path is None:
            raise ExportError("No completed video is available for this project.")
        path = self._safe_export_path(item.file_path)
        if not path.is_file() or path.stat().st_size == 0:
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
        path = self._safe_export_path(item.file_path)
        if not path.is_file():
            raise ExportError("Export file is unavailable.")
        return path

    def _safe_export_path(self, supplied: str) -> Path:
        path = Path(supplied).resolve()
        if path != self.artifact_directory and self.artifact_directory not in path.parents:
            raise ExportError("Export path is outside the approved artifact directory.")
        return path


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
