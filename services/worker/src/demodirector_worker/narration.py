from __future__ import annotations

import math
import os
import struct
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from demodirector_contracts import (
    NarrationJobResult,
    NarrationSegment,
    NarrationVoiceConfig,
    Scene,
)
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

load_dotenv()

DEFAULT_TTS_MODEL = "gemini-3.1-flash-tts-preview"
FALLBACK_TTS_MODEL = "gemini-2.5-flash-preview-tts"
SAMPLE_RATE = 24_000
SAMPLE_WIDTH = 2
NARRATION_QUOTA_MESSAGE = (
    "Google speech rate or quota limit reached. "
    "Wait for the configured project's limit to reset before approving a retry; "
    "completed slides are preserved."
)


class NarrationQuotaError(RuntimeError):
    """Speech generation is waiting for provider capacity."""


class AudioGenerationError(RuntimeError):
    """Raised when a narration provider does not return usable PCM audio."""


@dataclass(frozen=True, slots=True)
class GeminiTTSSettings:
    model_name: str
    api_key: str | None

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> GeminiTTSSettings:
        values = os.environ if environment is None else environment
        return cls(
            model_name=values.get("GEMINI_TTS_MODEL", "").strip() or DEFAULT_TTS_MODEL,
            api_key=values.get("GEMINI_API_KEY", "").strip() or None,
        )


class TTSAdapter(Protocol):
    def synthesize(self, text: str, voice: NarrationVoiceConfig) -> bytes: ...


class GeminiTTSAdapter:
    def __init__(self, settings: GeminiTTSSettings,
                 *, on_progress: Callable[[str], None] | None = None) -> None:
        if settings.api_key is None:
            raise AudioGenerationError("GEMINI_API_KEY is required for live narration.")
        self.model_name = settings.model_name
        self.on_progress = on_progress or (lambda _: None)
        self._client = genai.Client(api_key=settings.api_key, http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1)))

    def synthesize(self, text: str, voice: NarrationVoiceConfig) -> bytes:
        try:
            return self._synthesize(text, voice)
        except APIError as error:
            if error.code != 429 or self.model_name != DEFAULT_TTS_MODEL:
                raise
            self.model_name = FALLBACK_TTS_MODEL
            self.on_progress(
                "Gemini 3.1 Flash TTS rate limited; using Gemini 2.5 Flash TTS fallback."
            )
            return self._synthesize(text, voice)

    def _synthesize(self, text: str, voice: NarrationVoiceConfig) -> bytes:
        self.on_progress(f"Speech generation: {self.model_name}")
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=(
                f"Read in {voice.language_code} at a {voice.pace} pace. "
                f"Speak only this narration: {text}"
            ),
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    language_code=voice.language_code,
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice.voice_name
                        )
                    ),
                ),
            ),
        )
        candidates = response.candidates or []
        content = candidates[0].content if candidates else None
        parts = content.parts if content is not None else []
        inline_data = parts[0].inline_data if parts else None
        data = inline_data.data if inline_data is not None else None
        if not data:
            raise AudioGenerationError("Gemini TTS returned empty audio data.")
        return data


class FixtureTTSAdapter:
    """Small deterministic audio adapter used by CI without provider calls."""

    def synthesize(self, text: str, voice: NarrationVoiceConfig) -> bytes:
        del voice
        duration_seconds = max(0.2, min(1.0, len(text.split()) * 0.08))
        frame_count = round(SAMPLE_RATE * duration_seconds)
        return b"".join(
            struct.pack("<h", round(600 * math.sin(2 * math.pi * 220 * i / SAMPLE_RATE)))
            for i in range(frame_count)
        )


class NarrationService:
    def __init__(self, adapter: TTSAdapter, artifact_directory: Path) -> None:
        self.adapter = adapter
        self.artifact_directory = artifact_directory

    def generate(
        self,
        scenes: Sequence[Scene],
        voice: NarrationVoiceConfig,
        *,
        capture_clip_paths: Sequence[str] = (),
    ) -> NarrationJobResult:
        self.artifact_directory.mkdir(parents=True, exist_ok=True)
        segments: list[NarrationSegment] = []
        preserved = list(capture_clip_paths)
        try:
            for order, scene in enumerate(sorted(scenes, key=lambda item: item.order)):
                pcm = self.adapter.synthesize(scene.narration, voice)
                output = self.artifact_directory / f"{order:03d}-{scene.id}.wav"
                _write_pcm_wav(output, pcm)
                duration_ms = max(1, round(len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH) * 1_000))
                segments.append(
                    NarrationSegment(
                        scene_id=scene.id,
                        order=order,
                        text=scene.narration,
                        audio_path=str(output),
                        duration_ms=duration_ms,
                    )
                )
        except Exception as error:
            return NarrationJobResult(
                status="failed",
                retryable=True,
                voice_config=voice,
                segments=segments,
                preserved_capture_paths=preserved,
                error=(NARRATION_QUOTA_MESSAGE
                       if isinstance(error, APIError) and error.code == 429
                       else f"Narration generation failed: {error}"),
            )
        return NarrationJobResult(
            status="succeeded",
            retryable=False,
            voice_config=voice,
            segments=segments,
            preserved_capture_paths=preserved,
        )


def _write_pcm_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(SAMPLE_WIDTH)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(pcm)
