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


def test_silent_hold_keeps_short_speech_at_natural_speed(tmp_path: Path) -> None:
    source = pcm(tmp_path / "short.wav", [(3, True)])
    ready = tmp_path / "ready.wav"
    receipt = prepare_narration(source, ready, 10, max_duration=15, allow_silent_hold=True)
    assert receipt["speed"] == 1
    assert receipt["speech_duration"] == 3
    assert receipt["slide_duration"] == 10
    assert receipt["silent_hold_seconds"] == 7
    assert speech_metrics(ready)["duration"] == pytest.approx(10, abs=.01)


def test_long_internal_gap_is_rejected(tmp_path: Path) -> None:
    source = pcm(tmp_path / "gap.wav", [(2, True), (2, False), (2, True)])
    with pytest.raises(NarrationTimingError, match="pause"):
        prepare_narration(source, tmp_path / "ready.wav", 6.25)


def test_long_speech_extends_slide_without_forcing_fast_narration(tmp_path: Path) -> None:
    source = pcm(tmp_path / "long.wav", [(11.5, True)])
    ready = tmp_path / "ready.wav"
    receipt = prepare_narration(source, ready, 10, max_duration=15)
    assert 11.5 < receipt["slide_duration"] <= 12
    assert receipt["speed"] == pytest.approx(1, abs=.02)
    assert speech_metrics(ready)["duration"] == pytest.approx(receipt["slide_duration"], abs=.01)


def test_modestly_short_speech_shortens_slide_without_regeneration(tmp_path: Path) -> None:
    source = pcm(tmp_path / "short.wav", [(15, True)])
    receipt = prepare_narration(source, tmp_path / "ready.wav", 17,
                                min_duration=15, max_duration=22)
    assert receipt["slide_duration"] == 15.3
    assert receipt["speed"] == pytest.approx(1, abs=.02)
    with pytest.raises(NarrationTimingError):
        prepare_narration(pcm(tmp_path / "tiny.wav", [(7, True)]),
                          tmp_path / "tiny-ready.wav", 17, min_duration=15, max_duration=22)


def test_extra_time_does_not_accept_excessive_pauses_or_overflow(tmp_path: Path) -> None:
    gap = pcm(tmp_path / "gap.wav", [(4, True), (2, False), (4, True)])
    with pytest.raises(NarrationTimingError, match="pause"):
        prepare_narration(gap, tmp_path / "ready.wav", 10, max_duration=15)
    long = pcm(tmp_path / "long.wav", [(18, True)])
    with pytest.raises(NarrationTimingError, match="Rewrite"):
        prepare_narration(long, tmp_path / "ready.wav", 10, max_duration=15)


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
