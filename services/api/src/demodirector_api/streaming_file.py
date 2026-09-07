"""Preserve range semantics while streaming large media through hosted proxies."""

from starlette.responses import FileResponse
from starlette.types import Message, Receive, Scope, Send


class StreamingFileResponse(FileResponse):
    # Fixed-length HTTP/1 responses have a 32 MiB limit on Cloud Run.
    stream_threshold = 8 * 1024 * 1024

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def stream_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                length = next((int(value) for key, value in headers
                               if key.lower() == b"content-length"), 0)
                if length > self.stream_threshold:
                    message = {**message, "headers": [
                        (key, value) for key, value in headers
                        if key.lower() != b"content-length"
                    ]}
            await send(message)

        await super().__call__(scope, receive, stream_headers)
