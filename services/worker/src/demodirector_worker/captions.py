from __future__ import annotations

from collections.abc import Sequence

from demodirector_contracts import (
    CaptionClip,
    CaptionStyleConfig,
    CaptionTrack,
    NarrationSegment,
)


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
