from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from demodirector_contracts import (
    CaptionClip,
    CaptionStyleConfig,
    CaptionTrack,
    NarrationSegment,
)


@dataclass(frozen=True)
class WordHighlight:
    words: tuple[str, ...]
    word_index: int
    start_ms: int
    end_ms: int


def highlight_frame_window(state: WordHighlight, fps: int = 30) -> tuple[int, int]:
    """Quantize shared absolute boundaries, never independently rounded durations."""
    return ((state.start_ms * fps + 500) // 1000, (state.end_ms * fps + 500) // 1000)


def word_highlights(text: str, start_ms: int, end_ms: int) -> list[WordHighlight]:
    """Estimated word timing within an existing phrase, not speech alignment."""
    words = tuple(text.split())
    if not words or end_ms <= start_ms:
        return []
    duration = end_ms - start_ms
    return [
        WordHighlight(
            words,
            index,
            start_ms + duration * index // len(words),
            start_ms + duration * (index + 1) // len(words),
        )
        for index in range(len(words))
        if duration * (index + 1) // len(words) > duration * index // len(words)
    ]


class CaptionService:
    def __init__(self, max_words_per_caption: int = 7) -> None:
        if max_words_per_caption <= 0:
            raise ValueError("max_words_per_caption must be positive")
        self.max_words_per_caption = max_words_per_caption

    def generate(
        self,
        narration_segments: Sequence[NarrationSegment],
        style: CaptionStyleConfig,
    ) -> list[CaptionTrack]:
        return [self.generate_track(segment, style) for segment in narration_segments]

    def generate_track(
        self,
        segment: NarrationSegment,
        style: CaptionStyleConfig,
    ) -> CaptionTrack:
        if not style.enabled:
            return CaptionTrack(
                scene_id=segment.scene_id,
                duration_ms=segment.duration_ms,
                style=style,
                clips=[],
            )
        words = segment.text.split()
        chunks = [
            words[index : index + self.max_words_per_caption]
            for index in range(0, len(words), self.max_words_per_caption)
        ]
        if len(chunks) > segment.duration_ms:
            chunks = [words]
        clips: list[CaptionClip] = []
        chunk_count = len(chunks)
        for index, chunk in enumerate(chunks):
            start_ms = index * segment.duration_ms // chunk_count
            end_ms = (index + 1) * segment.duration_ms // chunk_count
            clips.append(
                CaptionClip(
                    id=f"caption-{segment.scene_id}-{index + 1}",
                    scene_id=segment.scene_id,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=" ".join(chunk),
                )
            )
        return CaptionTrack(
            scene_id=segment.scene_id,
            duration_ms=segment.duration_ms,
            style=style,
            clips=clips,
        )
