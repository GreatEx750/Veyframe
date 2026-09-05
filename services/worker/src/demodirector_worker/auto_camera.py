from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from demodirector_contracts import BoundingBox, InteractionEvent, ZoomClip
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field


class AutoCameraError(RuntimeError):
    """Raised when a focus-selection response cannot produce a safe camera plan."""


@dataclass(frozen=True, slots=True)
class AutoCameraSettings:
    min_scale: float = 1.2
    max_scale: float = 2.2
    edge_padding_px: float = 32
    focus_duration_ms: int = 1_200
    lead_in_ms: int = 200
    merge_gap_ms: int = 300
    minimum_motion_interval_ms: int = 900

    def __post_init__(self) -> None:
        if self.min_scale < 1 or self.max_scale > 4 or self.min_scale > self.max_scale:
            raise ValueError("camera scale bounds must stay within the ZoomClip contract")
        if self.edge_padding_px < 0:
            raise ValueError("edge padding may not be negative")
        if min(
            self.focus_duration_ms,
            self.merge_gap_ms,
            self.minimum_motion_interval_ms,
        ) <= 0:
            raise ValueError("camera timing settings must be positive")
        if self.lead_in_ms < 0:
            raise ValueError("camera lead-in may not be negative")


@dataclass(frozen=True, slots=True)
class FocusCandidate:
    event_index: int
    clip: ZoomClip


class FocusSelector(Protocol):
    def select(self, candidates: Sequence[FocusCandidate]) -> list[int]: ...


class DeterministicFocusSelector:
    def select(self, candidates: Sequence[FocusCandidate]) -> list[int]:
        return list(range(len(candidates)))


class FocusSelectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_candidate_indexes: list[int] = Field(default_factory=list)


class GeminiFocusSelector:
    """Gemini may select candidates only; it never controls camera geometry."""

    def __init__(self, api_key: str, model_name: str = "gemini-3.5-flash-lite") -> None:
        self.model_name = model_name
        self._client = genai.Client(api_key=api_key)

    def select(self, candidates: Sequence[FocusCandidate]) -> list[int]:
        payload = [
            {
                "candidate_index": index,
                "event_index": candidate.event_index,
                "start_ms": candidate.clip.start_ms,
                "end_ms": candidate.clip.end_ms,
                "scale": candidate.clip.scale,
                "target_rect": candidate.clip.target_rect.model_dump(),
            }
            for index, candidate in enumerate(candidates)
        ]
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=(
                "Select the smallest ordered set of semantic UI focus candidates needed for a "
                "clear product demo. Return candidate indexes only. Candidates: "
                f"{json.dumps(payload, separators=(',', ':'))}"
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FocusSelectionResponse,
                temperature=0,
                max_output_tokens=128,
            ),
        )
        if not isinstance(response.parsed, FocusSelectionResponse):
            raise AutoCameraError("Gemini returned an invalid focus selection.")
        return response.parsed.selected_candidate_indexes


class AutoCameraService:
    def __init__(
        self,
        selector: FocusSelector | None = None,
        settings: AutoCameraSettings | None = None,
    ) -> None:
        self.selector = selector or DeterministicFocusSelector()
        self.settings = settings or AutoCameraSettings()

    def generate(
        self,
        events: Sequence[InteractionEvent],
        duration_ms: int,
        *,
        manual_clips: Sequence[ZoomClip] = (),
    ) -> list[ZoomClip]:
        if duration_ms <= 0:
            raise ValueError("camera timeline duration must be positive")
        if any(clip.end_ms > duration_ms for clip in manual_clips):
            raise ValueError("manual zooms must fit within the camera timeline")
        candidates = self._candidates(events, duration_ms)
        selected_indexes = self.selector.select(candidates)
        if len(selected_indexes) != len(set(selected_indexes)):
            raise AutoCameraError("Focus selection may not repeat candidate indexes.")
        if any(index < 0 or index >= len(candidates) for index in selected_indexes):
            raise AutoCameraError("Focus selection referenced an unknown candidate index.")
        selected = [candidates[index].clip for index in selected_indexes]
        stabilized = self._stabilize(selected)
        auto_clips = [
            clip
            for clip in stabilized
            if not any(_overlaps(clip, manual) for manual in manual_clips)
        ]
        return sorted([*auto_clips, *manual_clips], key=lambda clip: (clip.start_ms, clip.id))

    def _candidates(
        self,
        events: Sequence[InteractionEvent],
        duration_ms: int,
    ) -> list[FocusCandidate]:
        candidates: list[FocusCandidate] = []
        for event_index, event in enumerate(events):
            if event.event_type not in {"click", "fill", "select"} or event.bounding_box is None:
                continue
            box = event.bounding_box
            if box.x >= event.viewport.width or box.y >= event.viewport.height:
                continue
            start_ms = max(0, event.timestamp_ms - self.settings.lead_in_ms)
            if start_ms >= duration_ms:
                continue
            end_ms = min(duration_ms, start_ms + self.settings.focus_duration_ms)
            if end_ms <= start_ms:
                continue
            target = _padded_target(event, self.settings.edge_padding_px)
            scale = _safe_scale(event, target, self.settings)
            candidates.append(
                FocusCandidate(
                    event_index=event_index,
                    clip=ZoomClip(
                        id=f"zoom-auto-{event_index + 1}",
                        start_ms=start_ms,
                        end_ms=end_ms,
                        scale=scale,
                        target_rect=target,
                        focus_x=event.x,
                        focus_y=event.y,
                        source_viewport=event.viewport,
                        easing="ease_in_out",
                        source="auto",
                    ),
                )
            )
        return candidates

    def _stabilize(self, clips: Sequence[ZoomClip]) -> list[ZoomClip]:
        ordered = sorted(clips, key=lambda clip: (clip.start_ms, clip.id))
        stable: list[ZoomClip] = []
        for clip in ordered:
            if not stable:
                stable.append(clip)
                continue
            previous = stable[-1]
            gap = clip.start_ms - previous.end_ms
            start_gap = clip.start_ms - previous.start_ms
            if gap <= self.settings.merge_gap_ms:
                stable[-1] = _merge_clips(previous, clip, self.settings)
            elif start_gap < self.settings.minimum_motion_interval_ms:
                continue
            else:
                stable.append(clip)
        return stable


def _padded_target(event: InteractionEvent, padding: float) -> BoundingBox:
    box = cast(BoundingBox, event.bounding_box)
    left = max(0, box.x - padding)
    top = max(0, box.y - padding)
    right = min(float(event.viewport.width), box.x + box.width + padding)
    bottom = min(float(event.viewport.height), box.y + box.height + padding)
    return BoundingBox(x=left, y=top, width=right - left, height=bottom - top)


def _safe_scale(
    event: InteractionEvent,
    target: BoundingBox,
    settings: AutoCameraSettings,
) -> float:
    fit_scale = min(event.viewport.width / target.width, event.viewport.height / target.height)
    return round(max(settings.min_scale, min(settings.max_scale, fit_scale * 0.7)), 3)


def _merge_clips(
    first: ZoomClip,
    second: ZoomClip,
    settings: AutoCameraSettings,
) -> ZoomClip:
    left = min(first.target_rect.x, second.target_rect.x)
    top = min(first.target_rect.y, second.target_rect.y)
    right = max(
        first.target_rect.x + first.target_rect.width,
        second.target_rect.x + second.target_rect.width,
    )
    bottom = max(
        first.target_rect.y + first.target_rect.height,
        second.target_rect.y + second.target_rect.height,
    )
    return ZoomClip(
        id=first.id,
        start_ms=min(first.start_ms, second.start_ms),
        end_ms=max(first.end_ms, second.end_ms),
        scale=max(settings.min_scale, min(settings.max_scale, min(first.scale, second.scale))),
        target_rect=BoundingBox(x=left, y=top, width=right - left, height=bottom - top),
        focus_x=second.focus_x if second.focus_x is not None else first.focus_x,
        focus_y=second.focus_y if second.focus_y is not None else first.focus_y,
        source_viewport=(
            first.source_viewport
            if first.source_viewport == second.source_viewport
            else first.source_viewport or second.source_viewport
        ),
        easing="ease_in_out",
        source="auto",
    )


def _overlaps(first: ZoomClip, second: ZoomClip) -> bool:
    return first.start_ms < second.end_ms and second.start_ms < first.end_ms
