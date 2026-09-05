from datetime import UTC, datetime
from typing import Literal, cast

from demodirector_contracts import Viewport
from demodirector_contracts.longform import (
    SECTION_PROFILE,
    CaptureChapter,
    LongFormVideoPlan,
    NarrativeSection,
    VisualBeat,
)


def longform_plan() -> LongFormVideoPlan:
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    source = "source:parallel-1"
    clip = "scene:product"
    sections: list[NarrativeSection] = []
    cursor = 0
    narration_counts = (10, 14, 22, 170, 78, 56, 42, 8)
    for order, (section_id, duration) in enumerate(SECTION_PROFILE):
        sections.append(
            NarrativeSection(
                id=section_id,
                order=order,
                start_ms=cursor,
                end_ms=cursor + duration,
                narration=" ".join(["product"] * narration_counts[order]),
                source_refs=[source],
                product_clip_ref=clip,
            )
        )
        cursor += duration
    beats: list[VisualBeat] = []
    for section in sections:
        spacing = max(1, (section.end_ms - section.start_ms) // 4)
        for position in range(3):
            start = section.start_ms + position * spacing
            purpose = cast(
                Literal["hook", "problem", "promise", "walkthrough", "closing"],
                {
                    "hook": "hook",
                    "problem": "problem",
                    "promise": "promise",
                    "closing": "closing",
                }.get(section.id, "walkthrough"),
            )
            beats.append(
                VisualBeat(
                    id=f"beat-{len(beats) + 1}",
                    section_id=section.id,
                    start_ms=start,
                    end_ms=min(section.end_ms, start + max(250, spacing)),
                    purpose=purpose,
                    template_id="framed_product",
                    product_clip_ref=clip,
                    source_refs=[source],
                )
            )
    indexes = [
        index for index, beat in enumerate(beats)
        if beat.section_id == "product_walkthrough"
    ]
    replacements = [
        beats[indexes[0]].model_copy(
            update={"purpose": "product_operation", "start_ms": 20_000, "end_ms": 24_000}
        ),
        beats[indexes[1]].model_copy(
            update={"purpose": "create_action", "start_ms": 25_000, "end_ms": 29_000}
        ),
        beats[indexes[2]].model_copy(
            update={"purpose": "finished_glimpse", "start_ms": 40_000, "end_ms": 44_000}
        ),
    ]
    for index, replacement in zip(indexes, replacements, strict=True):
        beats[index] = replacement
    chapters = []
    for index in range(0, 8, 2):
        pair = sections[index : index + 2]
        chapters.append(
            CaptureChapter(
                id=f"chapter-{index // 2 + 1}",
                project_id="project-1",
                order=index // 2,
                section_ids=[item.id for item in pair],
                start_ms=pair[0].start_ms,
                end_ms=pair[-1].end_ms,
                viewport=Viewport(width=2560, height=1440),
                account_ref="account:owner",
                project_state_ref="storyboard:1",
                cursor_continuity_key="cursor:project-1",
            )
        )
    return LongFormVideoPlan(
        id="longform-plan-1",
        project_id="project-1",
        job_id="job-1",
        adk_run_id="longform-run-1",
        parent_motion_run_id="motion-run-1",
        visual_variant="technical_proof",
        research_status="complete",
        evidence_refs=[source, "storyboard:1"],
        parallel_source_refs=[source],
        product_clip_refs=[clip],
        target_ids=[],
        sections=sections,
        beats=beats,
        chapters=chapters,
        first_product_operation_ms=20_000,
        create_action_ms=25_000,
        finished_glimpse_ms=40_000,
        product_presence_percent=100,
        created_at=now,
    )
