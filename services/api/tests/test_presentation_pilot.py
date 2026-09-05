from __future__ import annotations

import pytest
from demodirector_api.presentation_pilot import SlideScript, validate_slide
from demodirector_worker.presentation_assets import load_pack
from pydantic import ValidationError


def test_slide_direction_rejects_executable_fields_and_unknown_recipes() -> None:
    with pytest.raises(ValidationError):
        SlideScript.model_validate(
            {
                "template_id": "hook-question@2",
                "narration": "A question?",
                "text": [
                    {"slot_id": "headline", "text": "Question"},
                    {"slot_id": "chapter", "text": "Opening"},
                ],
                "source_ids": ["source-1"],
                "capture_recipe": "javascript",
                "code": "document.body.remove()",
            }
        )


def test_slide_direction_requires_exact_slots_and_grounded_sources() -> None:
    template = load_pack()["templates"][0]
    draft = SlideScript.model_validate(
        {
            "template_id": template["id"],
            "narration": "Where does curiosity lead?",
            "text": [
                {"slot_id": s["id"], "text": "Test"}
                for s in template["copy_slots"]
                if s["id"] != "caption"
            ],
            "source_ids": ["source-1"],
            "capture_recipe": "title",
        }
    )
    validate_slide(draft, template, {"source-1"}, "title")
    with pytest.raises(ValueError, match="not formally peer-reviewed"):
        validate_slide(draft.model_copy(update={"narration": "Read peer-reviewed articles."}),
                       template, {"source-1"}, "title")
    with pytest.raises(ValueError, match="unknown research"):
        validate_slide(draft, template, {"source-2"}, "title")
    with pytest.raises(ValueError, match="each declared slot"):
        validate_slide(
            draft.model_copy(update={"text": draft.text[:-1]}), template, {"source-1"}, "title"
        )
    with pytest.raises(ValueError, match="assigned template or capture recipe"):
        validate_slide(draft, template, {"source-1"}, "search")


def test_slide_direction_rejects_copy_overflow() -> None:
    template = load_pack()["templates"][0]
    draft = SlideScript.model_validate(
        {
            "template_id": template["id"],
            "narration": "Explore Wikipedia.",
            "text": [
                {"slot_id": s["id"], "text": "x" * (s["max_characters"] + 1)}
                for s in template["copy_slots"]
                if s["id"] != "caption"
            ],
            "source_ids": ["source-1"],
            "capture_recipe": "title",
        }
    )
    with pytest.raises(ValueError, match="exceeds the limit"):
        validate_slide(draft, template, {"source-1"}, "title")
