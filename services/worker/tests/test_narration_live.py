from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest
from demodirector_contracts import NarrationVoiceConfig
from demodirector_worker.narration import GeminiTTSAdapter, GeminiTTSSettings, _write_pcm_wav

pytestmark = pytest.mark.live


def test_live_gemini_tts_produces_short_audio(tmp_path: Path) -> None:
    if os.getenv("GEMINI_TTS_LIVE_SMOKE_TEST") != "1":
        pytest.skip("Set GEMINI_TTS_LIVE_SMOKE_TEST=1 to run the paid Gemini TTS smoke test.")
    settings = GeminiTTSSettings.from_environment()
    if settings.api_key is None:
        pytest.skip("Gemini credentials are not configured.")

    pcm = GeminiTTSAdapter(settings).synthesize("Hello.", NarrationVoiceConfig())
    output = tmp_path / "live-smoke.wav"
    _write_pcm_wav(output, pcm)

    with wave.open(str(output), "rb") as audio:
        assert audio.getnframes() > 0
