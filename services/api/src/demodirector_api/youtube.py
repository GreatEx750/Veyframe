"""Opt-in, single-process YouTube uploader; credentials never leave memory."""

from __future__ import annotations

import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"


class YouTubeError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class UploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    export_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w-]+$")
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    made_for_kids: bool = Field(strict=True)
    confirmed: Literal[True]

    @field_validator("title", "description")
    @classmethod
    def valid_text(cls, value: str) -> str:
        if "<" in value or ">" in value or len(value.encode("utf-8")) > 5000:
            raise ValueError("Text contains unsupported characters or is too long.")
        return value


class ConnectionStatus(BaseModel):
    enabled: bool
    configured: bool
    connected: bool = False
    channel_title: str | None = None
    message: str


class UploadStatus(BaseModel):
    id: str
    export_id: str
    status: Literal["queued", "uploading", "succeeded", "failed", "unknown"] = "queued"
    progress: int = 0
    message: str = "Waiting to upload privately."
    video_id: str | None = None


class TokenResponse(BaseModel):
    access_token: str = Field(min_length=1, max_length=8192)
    expires_in: int = Field(gt=0, le=86400)
    scope: str


class ChannelSnippet(BaseModel):
    title: str = Field(min_length=1, max_length=1000)


class Channel(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    snippet: ChannelSnippet


class ChannelResponse(BaseModel):
    items: list[Channel] = Field(min_length=1, max_length=50)


class VideoResponse(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")


@dataclass
class Connection:
    token: str
    expires: float
    channel: Channel


@dataclass
class Upload:
    session: str
    project_id: str
    payload: UploadInput
    path: Path
    connection: Connection
    result: UploadStatus


class LocalYouTube:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.transport = transport
        self.connections: dict[str, Connection] = {}
        self.states: dict[str, tuple[str, str, float]] = {}
        self.uploads: dict[str, Upload] = {}
        self.lock = threading.RLock()

    @property
    def origin(self) -> str | None:
        raw = os.getenv("YOUTUBE_PUBLIC_BASE_URL", "http://localhost:3000").strip()
        url = urlsplit(raw)
        local = url.scheme == "http" and url.hostname == "localhost" and url.port == 3000
        hosted = url.scheme == "https" and bool(url.hostname)
        if (
            not (local or hosted)
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            return None
        return f"{url.scheme}://{url.netloc}"

    @property
    def redirect_uri(self) -> str | None:
        return f"{self.origin}/api/youtube/callback" if self.origin else None

    def status(self, session: str) -> ConnectionStatus:
        hosted = bool(os.getenv("K_SERVICE"))
        local_enabled = (
            os.getenv("YOUTUBE_LOCAL_ENABLED") == "true"
            and not hosted
            and os.getenv("DEMO_METADATA_BACKEND", "sqlite") == "sqlite"
        )
        cloud_enabled = os.getenv("YOUTUBE_CLOUD_ENABLED") == "true" and hosted
        configured = bool(
            os.getenv("YOUTUBE_CLIENT_ID")
            and os.getenv("YOUTUBE_CLIENT_SECRET")
            and self.origin
        )
        enabled = (local_enabled or cloud_enabled) and self.origin is not None
        with self.lock:
            connection = self.connections.get(session)
            if connection and connection.expires <= time.monotonic():
                self.connections.pop(session, None)
                connection = None
        connected = enabled and configured and connection is not None
        message = "Connect your YouTube channel. Uploads are private."
        if not enabled or not configured:
            message = "YouTube setup is incomplete. Enable the integration and add Google OAuth credentials."
        elif connected:
            message = "Connected for this server session. A deployment or restart requires reconnection."
        return ConnectionStatus(
            enabled=enabled,
            configured=configured,
            connected=connected,
            channel_title=connection.channel.snippet.title if connected and connection else None,
            message=message,
        )

    def require_enabled(self, session: str) -> None:
        status = self.status(session)
        if not status.enabled or not status.configured:
            raise YouTubeError(status.message, 503)

    def connect(self, session: str, project_id: str) -> str:
        self.require_enabled(session)
        redirect_uri = self.redirect_uri
        if not redirect_uri:
            raise YouTubeError("YouTube's public application URL is invalid.", 503)
        with self.lock:
            if self.busy(session):
                raise YouTubeError("Wait for the current upload before changing channels.", 409)
            self.states = {
                key: value
                for key, value in self.states.items()
                if value[2] > time.monotonic() and value[0] != session
            }
            state = secrets.token_urlsafe(32)
            self.states[state] = (session, project_id, time.monotonic() + 600)
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": os.environ["YOUTUBE_CLIENT_ID"],
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "state": state,
                "access_type": "online",
                "prompt": "consent select_account",
            }
        )

    @staticmethod
    def check(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise YouTubeError(
                "Google authorization expired. Disconnect and reconnect YouTube.", 401
            )
        if response.status_code in (403, 429):
            raise YouTubeError(
                "YouTube rejected the request. Check API access, channel permissions and quota.",
                422,
            )
        if not response.is_success:
            raise YouTubeError(
                "YouTube could not complete the request. No automatic retry was made.", 502
            )

    def callback(self, session: str, state: str, code: str | None) -> str:
        self.require_enabled(session)
        redirect_uri = self.redirect_uri
        if not redirect_uri:
            raise YouTubeError("YouTube's public application URL is invalid.", 503)
        with self.lock:
            pending = self.states.get(state)
            if not pending or pending[0] != session or pending[2] < time.monotonic():
                raise YouTubeError(
                    "Connection expired or belongs to another session. Connect again."
                )
            del self.states[state]
        if not code:
            raise YouTubeError("YouTube connection was cancelled. No video was uploaded.")
        try:
            with httpx.Client(
                transport=self.transport, timeout=30, follow_redirects=False
            ) as client:
                response = client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": os.environ["YOUTUBE_CLIENT_ID"],
                        "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                        "code": code,
                    },
                )
                self.check(response)
                token = TokenResponse.model_validate(response.json())
                if not set(SCOPE.split()).issubset(token.scope.split()):
                    raise YouTubeError("Both YouTube upload and channel access must be granted.")
                response = client.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={"part": "snippet", "mine": "true"},
                    headers={"Authorization": f"Bearer {token.access_token}"},
                )
                self.check(response)
                channel = ChannelResponse.model_validate(response.json()).items[0]
            with self.lock:
                self.connections[session] = Connection(
                    token.access_token, time.monotonic() + token.expires_in - 30, channel
                )
            return pending[1]
        except (httpx.HTTPError, ValidationError, ValueError) as error:
            raise YouTubeError(
                "Could not connect a YouTube channel. Check consent and channel setup.", 502
            ) from error

    def busy(self, session: str) -> bool:
        return any(
            job.session == session and job.result.status in ("queued", "uploading")
            for job in self.uploads.values()
        )

    def disconnect(self, session: str) -> None:
        with self.lock:
            if self.busy(session):
                raise YouTubeError("Wait for the current upload before disconnecting.", 409)
            connection = self.connections.get(session)
        if connection:
            try:
                with httpx.Client(transport=self.transport, timeout=15) as client:
                    response = client.post(
                        "https://oauth2.googleapis.com/revoke", data={"token": connection.token}
                    )
                    if response.status_code not in (200, 400):
                        raise YouTubeError(
                            "Could not revoke Google access. Try disconnecting again.", 502
                        )
            except httpx.HTTPError as error:
                raise YouTubeError(
                    "Could not revoke Google access. Try disconnecting again.", 502
                ) from error
        with self.lock:
            self.connections.pop(session, None)
            self.states = {key: value for key, value in self.states.items() if value[0] != session}

    def start(
        self, session: str, project_id: str, payload: UploadInput, path: Path
    ) -> UploadStatus:
        self.require_enabled(session)
        with self.lock:
            for item in self.uploads.values():
                if (item.session, item.project_id, item.payload.export_id) == (
                    session,
                    project_id,
                    payload.export_id,
                ):
                    return item.result.model_copy()
            if not self.status(session).connected:
                raise YouTubeError("Connect YouTube before uploading.", 401)
            if self.busy(session):
                raise YouTubeError("One YouTube upload can run at a time.", 409)
            if len(self.uploads) >= 100:
                raise YouTubeError(
                    "Upload history is full. Restart after checking your uploads.", 409
                )
            if not path.is_file() or path.stat().st_size == 0:
                raise YouTubeError("The saved MP4 is unavailable.", 404)
            result = UploadStatus(id=str(uuid4()), export_id=payload.export_id)
            self.uploads[result.id] = Upload(
                session, project_id, payload, path, self.connections[session], result
            )
            return result.model_copy()

    def job(self, session: str, project_id: str, job_id: str) -> UploadStatus:
        with self.lock:
            item = self.uploads.get(job_id)
            if not item or (item.session, item.project_id) != (session, project_id):
                raise YouTubeError("Upload not found in this server session.", 404)
            return item.result.model_copy()

    def upload(self, job_id: str) -> None:
        with self.lock:
            job = self.uploads[job_id]
            if job.result.status != "queued":
                return
            job.result.status = "uploading"
            job.result.message = "Uploading privately to YouTube…"
        try:
            size = job.path.stat().st_size
            headers = {"Authorization": f"Bearer {job.connection.token}"}
            with httpx.Client(
                transport=self.transport, timeout=120, follow_redirects=False
            ) as client:
                response = client.post(
                    "https://www.googleapis.com/upload/youtube/v3/videos",
                    params={
                        "uploadType": "resumable",
                        "part": "snippet,status",
                        "notifySubscribers": "false",
                    },
                    headers={
                        **headers,
                        "X-Upload-Content-Type": "video/mp4",
                        "X-Upload-Content-Length": str(size),
                    },
                    json={
                        "snippet": {
                            "title": job.payload.title,
                            "description": job.payload.description,
                            "categoryId": "22",
                        },
                        "status": {
                            "privacyStatus": "private",
                            "selfDeclaredMadeForKids": job.payload.made_for_kids,
                        },
                    },
                )
                self.check(response)
                location = response.headers.get("Location", "")
                url = urlsplit(location)
                if (
                    url.scheme != "https"
                    or url.netloc != "www.googleapis.com"
                    or url.path != "/upload/youtube/v3/videos"
                    or url.fragment
                ):
                    raise YouTubeError("YouTube returned an invalid upload destination.", 502)
                offset = 0
                with job.path.open("rb") as stream:
                    while chunk := stream.read(8 * 1024 * 1024):
                        end = offset + len(chunk)
                        response = client.put(
                            location,
                            content=chunk,
                            headers={
                                **headers,
                                "Content-Type": "video/mp4",
                                "Content-Length": str(len(chunk)),
                                "Content-Range": f"bytes {offset}-{end - 1}/{size}",
                            },
                        )
                        if response.status_code == 308 and end < size:
                            received = re.fullmatch(
                                r"bytes=0-(\d+)", response.headers.get("Range", "")
                            )
                            if not received or int(received[1]) + 1 != end:
                                raise YouTubeError(
                                    "YouTube returned an unexpected upload offset.", 502
                                )
                        else:
                            self.check(response)
                            video = VideoResponse.model_validate(response.json())
                            with self.lock:
                                job.result.video_id = video.id
                                job.result.status = "succeeded"
                                job.result.progress = 100
                                job.result.message = (
                                    "Uploaded privately. YouTube may still be processing the video."
                                )
                            return
                        offset = end
                        with self.lock:
                            job.result.progress = min(99, int(offset / size * 100))
                raise YouTubeError("Upload ended without confirmation. Check YouTube Studio.", 502)
        except YouTubeError as error:
            with self.lock:
                job.result.status = "failed"
                job.result.message = str(error)
        except (httpx.HTTPError, OSError, ValidationError, ValueError):
            with self.lock:
                job.result.status = "unknown"
                job.result.message = (
                    "Upload could not be confirmed. Check YouTube Studio "
                    "before trying again to avoid duplicates."
                )
        finally:
            with self.lock:
                job.connection = Connection("", 0, job.connection.channel)
