"""Continuous slide speech with bounded timing and measurable audio quality."""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path

from demodirector_worker.presentation_assets import run_ffmpeg

NARRATION_VERSION = "continuous-slide-v2-flexible"


class NarrationTimingError(ValueError):
    pass


def speech_metrics(path: Path) -> dict[str, float]:
    with wave.open(str(path), "rb") as audio:
        if audio.getsampwidth() != 2 or audio.getnchannels() != 1:
            raise ValueError("Narration must be mono 16-bit PCM")
        rate = audio.getframerate()
        samples = array.array("h", audio.readframes(audio.getnframes()))
    frame = max(1, rate // 100)
    levels = [
        math.sqrt(sum(float(v) ** 2 for v in samples[i:i + frame]) / frame) / 32768
        for i in range(0, len(samples) - frame + 1, frame)
    ]
    active = [i for i, value in enumerate(levels) if value > 10 ** (-45 / 20)]
    if not active:
        raise ValueError("Narration contains no audible speech")
    first, last = active[0], active[-1]
    longest = current = 0
    for value in levels[first:last + 1]:
        current = current + 1 if value <= 10 ** (-45 / 20) else 0
        longest = max(longest, current)
    return {
        "duration": len(samples) / rate,
        "start": max(0, first * .01 - .06),
        "end": min(len(samples) / rate, (last + 1) * .01 + .10),
        "max_internal_silence": longest * .01,
        "active_rms": math.sqrt(sum(levels[i] ** 2 for i in active) / len(active)),
        "peak": max(abs(v) for v in samples) / 32768,
    }


def prepare_narration(
    source: Path, destination: Path, duration: float, *, max_duration: float | None = None,
    min_duration: float | None = None,
    allow_silent_hold: bool = False,
) -> dict[str, float]:
    if not math.isfinite(duration) or duration <= .25:
        raise ValueError("Invalid narration duration")
    if max_duration is not None and (
        not math.isfinite(max_duration) or max_duration < duration
    ):
        raise ValueError("Invalid narration extension budget")
    if min_duration is not None and (
        not math.isfinite(min_duration) or not .25 < min_duration <= duration
    ):
        raise ValueError("Invalid narration shortening budget")
    metrics = speech_metrics(source)
    spoken = metrics["end"] - metrics["start"]
    if max_duration is not None:
        # Tenth-second boundaries are exact three-frame intervals at 30 fps.
        duration = min(max_duration, max(min_duration or duration,
                                        math.ceil((spoken + .25) * 10) / 10))
    target = duration - .25
    speed = max(1.0 if allow_silent_hold else .9, min(1.1, spoken / target))
    fitted = spoken / speed
    if fitted > duration - .1 or (not allow_silent_hold and duration - fitted > 1.25):
        raise NarrationTimingError(
            f"Speech lasts {spoken:.2f}s for a {duration:.2f}s slide. "
            f"Rewrite to approximately {target:.2f}s at the same natural pace; "
            f"use about {target / spoken:.2f} times the current word count."
        )
    if not allow_silent_hold and metrics["max_internal_silence"] / speed > 1.25:
        raise NarrationTimingError("Speech has a pause longer than 1.25s; use flowing sentences.")
    # One constant gain for the paragraph avoids short-phrase loudness pumping.
    gain = min(10 ** (-20 / 20) / metrics["active_rms"],
               10 ** (-1.5 / 20) / metrics["peak"])
    run_ffmpeg([
        "-i", str(source), "-af",
        f"atrim=start={metrics['start']}:end={metrics['end']},asetpts=PTS-STARTPTS,"
        f"atempo={speed:.8f},volume={gain:.8f},"
        f"afade=t=in:d=0.01,afade=t=out:st={max(0, fitted - .03):.6f}:d=0.03,"
        f"apad,atrim=duration={duration}",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(destination),
    ], destination.parent)
    return {
        **metrics, "speed": speed, "speech_duration": fitted,
        "slide_duration": duration, "gain": gain,
        "silent_hold_seconds": max(0, duration - fitted),
    }
