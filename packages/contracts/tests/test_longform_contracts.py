from datetime import UTC, datetime

import pytest
from demodirector_contracts.longform import (
    ChapterCheckpoint,
    LongFormVideoPlan,
)
from pydantic import ValidationError

from test_support.longform import longform_plan


def test_longform_plan_enforces_proof_first_180_second_profile() -> None:
    plan = longform_plan()
    assert plan.duration_ms == 180_000
    assert plan.narration_word_count() == 400
    assert len(plan.beats) == 24
    assert plan.sections[3].start_ms == 20_000


def test_longform_plan_rejects_late_create_action() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 30000"):
        LongFormVideoPlan.model_validate(
            {**longform_plan().model_dump(mode="json"), "create_action_ms": 31_000}
        )


def test_chapter_checkpoint_requires_artifact_for_captured_state() -> None:
    with pytest.raises(ValidationError, match="validated artifact"):
        ChapterCheckpoint(
            id="checkpoint-1",
            project_id="project-1",
            plan_id="longform-plan-1",
            chapter_id="chapter-1",
            status="captured",
            attempt=1,
            created_at=datetime.now(UTC),
        )
