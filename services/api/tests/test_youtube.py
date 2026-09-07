from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from demodirector_api.youtube import LocalYouTube, UploadInput, YouTubeError
from pydantic import ValidationError


def gateway(monkeypatch: pytest.MonkeyPatch, handler: object) -> LocalYouTube:
    monkeypatch.setenv("YOUTUBE_LOCAL_ENABLED", "true")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "test-client")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "test-secret")
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("DEMO_METADATA_BACKEND", "sqlite")
    monkeypatch.setenv("YOUTUBE_PUBLIC_BASE_URL", "http://localhost:3000")
    return LocalYouTube(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def authorize(service: LocalYouTube, session: str = "session") -> None:
    url = service.connect(session, "project-1")
    state = parse_qs(urlsplit(url).query)["state"][0]
    assert service.callback(session, state, "code") == "project-1"


def provider(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/token":
        return httpx.Response(
            200,
            json={
                "access_token": "private-token",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
            },
        )
    if request.url.path.endswith("/channels"):
        return httpx.Response(
            200, json={"items": [{"id": "channel-1", "snippet": {"title": "Test channel"}}]}
        )
    if request.method == "POST" and request.url.path.endswith("/videos"):
        assert b'"privacyStatus":"private"' in request.content
        return httpx.Response(
            200,
            headers={
                "Location": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test"
            },
        )
    if request.method == "PUT":
        assert request.content == b"test-video"
        return httpx.Response(201, json={"id": "abcdefghijk"})
    if request.url.path == "/revoke":
        return httpx.Response(200)
    raise AssertionError(request.url)


def test_oauth_state_is_single_use_session_bound_and_tokens_are_not_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = gateway(monkeypatch, provider)
    url = service.connect("session", "project-1")
    assert "private-token" not in url and "test-secret" not in url
    state = parse_qs(urlsplit(url).query)["state"][0]
    with pytest.raises(YouTubeError):
        service.callback("other-session", state, "code")
    assert service.callback("session", state, "code") == "project-1"
    with pytest.raises(YouTubeError):
        service.callback("session", state, "code")
    assert service.status("session").channel_title == "Test channel"
    assert "private-token" not in service.status("session").model_dump_json()
    assert not service.status("other-session").connected
    service.disconnect("session")
    assert not service.status("session").connected


def test_upload_private_with_explicit_audience_and_duplicate_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = gateway(monkeypatch, provider)
    authorize(service)
    media = tmp_path / "video.mp4"
    media.write_bytes(b"test-video")
    payload = UploadInput(
        export_id="export-1",
        title="My video",
        description="A demo",
        made_for_kids=False,
        confirmed=True,
    )
    job = service.start("session", "project-1", payload, media)
    assert service.start("session", "project-1", payload, media).id == job.id
    service.upload(job.id)
    result = service.job("session", "project-1", job.id)
    assert result.status == "succeeded" and result.video_id == "abcdefghijk"
    assert result.progress == 100
    with pytest.raises(YouTubeError):
        service.job("other-session", "project-1", job.id)
    assert service.start("session", "project-1", payload, media).id == job.id


def test_rejects_untrusted_upload_location(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def malicious(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/videos"):
            return httpx.Response(200, headers={"Location": "https://example.com/steal"})
        return provider(request)

    service = gateway(monkeypatch, malicious)
    authorize(service)
    media = tmp_path / "video.mp4"
    media.write_bytes(b"test-video")
    job = service.start(
        "session",
        "project-1",
        UploadInput(export_id="e", title="Video", made_for_kids=False, confirmed=True),
        media,
    )
    service.upload(job.id)
    assert service.job("session", "project-1", job.id).status == "failed"


def test_local_gate_and_input_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    service = gateway(monkeypatch, provider)
    monkeypatch.setenv("K_SERVICE", "cloud-service")
    assert not service.status("session").enabled
    with pytest.raises(YouTubeError):
        service.connect("session", "project-1")
    with pytest.raises(ValidationError):
        UploadInput(export_id="e", title="   ", made_for_kids=False, confirmed=True)
    with pytest.raises(ValidationError):
        UploadInput.model_validate({"export_id": "e", "title": "Video", "confirmed": True})
    with pytest.raises(ValidationError):
        UploadInput.model_validate(
            {"export_id": "e", "title": "Video", "made_for_kids": False, "confirmed": False}
        )


def test_explicit_cloud_configuration_uses_https_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    service = gateway(monkeypatch, provider)
    monkeypatch.setenv("K_SERVICE", "cloud-service")
    monkeypatch.setenv("YOUTUBE_CLOUD_ENABLED", "true")
    monkeypatch.setenv("YOUTUBE_PUBLIC_BASE_URL", "https://veyframe.example")
    status = service.status("session")
    assert status.enabled and status.configured
    url = service.connect("session", "project-1")
    assert parse_qs(urlsplit(url).query)["redirect_uri"] == [
        "https://veyframe.example/api/youtube/callback"
    ]


@pytest.mark.parametrize(
    "base_url",
    ["http://veyframe.example", "https://veyframe.example/path", "https://user@veyframe.example"],
)
def test_rejects_unsafe_public_base_url(
    monkeypatch: pytest.MonkeyPatch, base_url: str
) -> None:
    service = gateway(monkeypatch, provider)
    monkeypatch.setenv("YOUTUBE_PUBLIC_BASE_URL", base_url)
    assert not service.status("session").enabled
    with pytest.raises(YouTubeError):
        service.connect("session", "project-1")


def test_expired_and_cancelled_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    service = gateway(monkeypatch, provider)
    state = parse_qs(urlsplit(service.connect("session", "project-1")).query)["state"][0]
    service.states[state] = ("session", "project-1", 0)
    with pytest.raises(YouTubeError):
        service.callback("session", state, "code")
    state = parse_qs(urlsplit(service.connect("session", "project-1")).query)["state"][0]
    with pytest.raises(YouTubeError, match="cancelled"):
        service.callback("session", state, None)
    assert not service.status("session").connected


def test_network_failure_does_not_retry_or_expose_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def interrupted(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            raise httpx.ReadTimeout("private-token and secret URL")
        return provider(request)

    service = gateway(monkeypatch, interrupted)
    authorize(service)
    media = tmp_path / "video.mp4"
    media.write_bytes(b"test-video")
    job = service.start(
        "session",
        "project-1",
        UploadInput(export_id="e", title="Video", made_for_kids=False, confirmed=True),
        media,
    )
    service.upload(job.id)
    result = service.job("session", "project-1", job.id)
    assert result.status == "unknown"
    assert "private-token" not in result.model_dump_json()
    assert service.uploads[job.id].connection.token == ""


def test_chunked_upload_progress_and_single_active_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = 0

    def chunks(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.method == "PUT":
            calls += 1
            if calls == 1:
                assert len(request.content) == 8 * 1024 * 1024
                return httpx.Response(308, headers={"Range": "bytes=0-8388607"})
            assert request.headers["Content-Range"] == "bytes 8388608-8388608/8388609"
            return httpx.Response(201, json={"id": "abcdefghijk"})
        return provider(request)

    service = gateway(monkeypatch, chunks)
    authorize(service)
    media = tmp_path / "large.mp4"
    media.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
    payload = UploadInput(export_id="e", title="Video", made_for_kids=False, confirmed=True)
    job = service.start("session", "project-1", payload, media)
    with pytest.raises(YouTubeError, match="One YouTube upload"):
        service.start("session", "project-1", payload.model_copy(update={"export_id": "e2"}), media)
    with pytest.raises(YouTubeError):
        service.disconnect("session")
    service.upload(job.id)
    assert calls == 2 and service.job("session", "project-1", job.id).progress == 100
