from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from demodirector_api.auth import (
    AuthService,
    AuthSettings,
    FakeIdentityProvider,
    SQLiteAuthRepository,
)
from demodirector_api.exports import LocalExportArtifactStore, StoredExport
from demodirector_api.main import create_app
from demodirector_api.repositories import SQLiteProjectRepository
from demodirector_api.youtube import LocalYouTube
from demodirector_contracts import VideoExport
from fastapi.testclient import TestClient


def test_youtube_requires_session_same_origin_and_owned_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "data.db"))
    monkeypatch.setenv("DEMO_METADATA_BACKEND", "sqlite")
    auth = AuthService(
        FakeIdentityProvider(verified=True),
        SQLiteAuthRepository(tmp_path / "auth.db"),
        AuthSettings(required=False, require_verified_email=False),
    )
    app = create_app(SQLiteProjectRepository(tmp_path / "projects.db"), auth_service=auth)
    with TestClient(app) as client:
        assert client.get("/youtube/status").status_code == 401
        signup = client.post(
            "/auth/signup",
            json={"email": "youtube@example.com", "password": "correct-horse-battery-staple"},
        )
        assert signup.status_code == 201
        headers = {"Authorization": f"Bearer {signup.json()['session_token']}"}
        assert client.get("/youtube/status", headers=headers).status_code == 200
        assert (
            client.post(
                "/youtube/connect", headers=headers, json={"project_id": "foreign"}
            ).status_code
            == 403
        )


def test_saved_export_upload_route_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("DEMO_METADATA_BACKEND", "sqlite")
    monkeypatch.setenv("YOUTUBE_LOCAL_ENABLED", "true")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "test-client")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "test-secret")
    monkeypatch.delenv("K_SERVICE", raising=False)
    from test_youtube import provider

    auth = AuthService(
        FakeIdentityProvider(verified=True),
        SQLiteAuthRepository(tmp_path / "auth.db"),
        AuthSettings(required=True, require_verified_email=False),
    )
    app = create_app(SQLiteProjectRepository(tmp_path / "projects.db"), auth_service=auth)
    app.state.youtube = LocalYouTube(transport=httpx.MockTransport(provider))
    app.state.export_service.artifact_store = LocalExportArtifactStore(tmp_path)
    with TestClient(app) as client:
        result = client.post(
            "/auth/signup",
            json={"email": "uploader@example.com", "password": "correct-horse-battery-staple"},
        )
        headers = {
            "Authorization": f"Bearer {result.json()['session_token']}",
            "Origin": "http://localhost:3000",
        }
        project = client.post(
            "/projects",
            headers=headers,
            json={
                "name": "Upload test",
                "website_url": "https://example.com",
                "product_summary": "A workflow",
                "audience": "Teams",
                "tone": "Professional",
                "requested_duration_seconds": 90,
                "cta": "Try it",
            },
        ).json()
        project_id = project["id"]
        url = client.post(
            "/youtube/connect", headers=headers, json={"project_id": project_id}
        ).json()["url"]
        state = parse_qs(urlsplit(url).query)["state"][0]
        assert (
            client.post(
                "/youtube/callback", headers=headers, json={"state": state, "code": "test-code"}
            ).status_code
            == 200
        )
        payload = {
            "export_id": "saved-export",
            "title": "My video",
            "made_for_kids": False,
            "confirmed": True,
        }
        endpoint = f"/youtube/projects/{project_id}/uploads"
        assert client.post(endpoint, headers=headers, json=payload).status_code == 404
        media = tmp_path / "saved.mp4"
        media.write_bytes(b"test-video")
        export = VideoExport(
            id="saved-export",
            project_id=project_id,
            status="succeeded",
            quality="1440p",
            filename="saved.mp4",
            width=2560,
            height=1440,
            duration_ms=90_000,
            size_bytes=10,
            retryable=False,
            download_url="/saved/download",
            created_at=datetime.now(UTC),
        )
        app.state.export_service.repository.save(StoredExport(export, str(media), None))
        started = client.post(endpoint, headers=headers, json=payload)
        assert started.status_code == 200
        job = client.get(endpoint + "/" + started.json()["id"], headers=headers).json()
        assert job["status"] == "succeeded" and job["video_id"] == "abcdefghijk"
        assert client.post(endpoint, headers=headers, json=payload).json()["id"] == job["id"]
        headers["Origin"] = "http://localhost:3000"
        assert (
            client.post(
                "/youtube/connect", headers=headers, json={"project_id": "foreign"}
            ).status_code
            == 404
        )
        assert (
            client.get("/youtube/projects/foreign/uploads/job", headers=headers).status_code == 404
        )
        assert (
            client.post(
                "/youtube/projects/foreign/uploads",
                headers=headers,
                json={
                    "export_id": "e",
                    "title": "Video",
                    "made_for_kids": False,
                    "confirmed": True,
                },
            ).status_code
            == 404
        )
