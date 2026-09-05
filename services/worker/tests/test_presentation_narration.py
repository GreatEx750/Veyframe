import math
import shutil
import struct
import wave
from pathlib import Path

import pytest
from demodirector_worker.presentation_narration import (
    NarrationTimingError,
    prepare_narration,
    speech_metrics,
)


def pcm(path: Path, parts: list[tuple[float, bool]]) -> Path:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        for duration, audible in parts:
            audio.writeframes(b"".join(
                struct.pack("<h", round(5000 * math.sin(2 * math.pi * 220 * i / 24000))
                            if audible else 0)
                for i in range(round(duration * 24000))
            ))
    return path


def test_short_narration_is_rejected_instead_of_padding_seconds(tmp_path: Path) -> None:
    source = pcm(tmp_path / "short.wav", [(2, True)])
    with pytest.raises(NarrationTimingError, match="Rewrite"):
        prepare_narration(source, tmp_path / "ready.wav", 8)
    assert not (tmp_path / "ready.wav").exists()


def test_long_internal_gap_is_rejected(tmp_path: Path) -> None:
    source = pcm(tmp_path / "gap.wav", [(2, True), (2, False), (2, True)])
    with pytest.raises(NarrationTimingError, match="pause"):
        prepare_narration(source, tmp_path / "ready.wav", 6.25)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg required")
def test_continuous_audio_has_exact_duration_and_no_long_gap(tmp_path: Path) -> None:
    source = pcm(tmp_path / "speech.wav", [(.3, False), (2.7, True), (.5, False)])
    ready = tmp_path / "ready.wav"
    receipt = prepare_narration(source, ready, 3)
    measured = speech_metrics(ready)
    assert measured["duration"] == pytest.approx(3, abs=1/48000)
    assert measured["max_internal_silence"] < .1
    assert measured["peak"] < .9
    assert .9 <= receipt["speed"] <= 1.1
    with wave.open(str(ready)) as audio:
        assert audio.getframerate() == 48000
