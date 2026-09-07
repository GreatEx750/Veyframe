from pathlib import Path

import pytest
from demodirector_api.streaming_file import StreamingFileResponse
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize("range_header", [None, "bytes=0-", "bytes=100-399"])
def test_large_video_streams_without_fixed_length_and_preserves_ranges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, range_header: str | None
) -> None:
    monkeypatch.setattr(StreamingFileResponse, "stream_threshold", 256)
    payload = bytes(range(256)) * 8
    path = tmp_path / "video.mp4"
    path.write_bytes(payload)
    app = FastAPI()

    @app.get("/video")
    def video() -> StreamingFileResponse:
        return StreamingFileResponse(path, media_type="video/mp4")

    with TestClient(app) as client:
        response = client.get("/video", headers={"Range": range_header} if range_header else {})
        assert response.status_code == (206 if range_header else 200)
        assert "content-length" not in response.headers
        assert response.headers["accept-ranges"] == "bytes"
        expected = payload[100:400] if range_header == "bytes=100-399" else payload
        assert response.content == expected
        if range_header:
            assert response.headers["content-range"].endswith("/2048")
        small = client.get("/video", headers={"Range": "bytes=0-9"})
        assert small.headers["content-length"] == "10"
        assert small.content == payload[:10]
        invalid = client.get("/video", headers={"Range": "bytes=99999-"})
        assert invalid.status_code == 416
