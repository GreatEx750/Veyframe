from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from demodirector_api.presentation_pilot import (
    SlideScript,
    validate_capture_narration,
    validate_slide,
)
from demodirector_api.presentation_pipeline import presentation_schedule
from demodirector_worker.presentation_assets import load_pack
from pydantic import ValidationError


def test_full_authored_schedule_is_exactly_two_minutes_and_all_templates_are_typed() -> None:
    pack = load_pack()
    schedule = presentation_schedule(pack, preview=False)
    assert len(schedule) == 9
    assert schedule[0][1]["start_ms"] == 0
    assert schedule[-1][1]["end_ms"] == 120_000
    assert sum(t[1]["end_ms"] - t[1]["start_ms"] for t in schedule) == 120_000
    for template, _, recipe in schedule:
        draft = SlideScript.model_validate(
            {
                "template_id": template["id"],
                "narration": "See the product in action.",
                "narration_beats": ["See the product in action."] * 3 if recipe != "title" else [],
                "text": [
                    {"slot_id": s["id"], "text": "Example"}
                    for s in template["copy_slots"]
                    if s["id"] != "caption"
                ],
                "source_ids": ["observed-page"],
                "capture_recipe": recipe,
            }
        )
        validate_slide(draft, template, {"observed-page"}, recipe)
    assert len(presentation_schedule(pack, preview=True)) == 5
    assert presentation_schedule(pack, preview=True)[-1][1]["end_ms"] == 61_000


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
        validate_slide(
            draft.model_copy(update={"narration": "Read peer-reviewed articles."}),
            template,
            {"source-1"},
            "title",
        )
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


def test_product_opening_rejects_placeholder_brand() -> None:
    template = load_pack()["templates"][1]
    draft = SlideScript.model_validate(
        {
            "template_id": template["id"],
            "narration": "Follow this related article link.",
            "narration_beats": ["Follow this related article link."] * 3,
            "text": [
                {"slot_id": s["id"], "text": "Untitled demo" if s["id"] == "brand" else "Test"}
                for s in template["copy_slots"]
                if s["id"] != "caption"
            ],
            "source_ids": ["source-1"],
            "capture_recipe": "related",
        }
    )
    with pytest.raises(ValueError, match="product name"):
        validate_slide(draft, template, {"source-1"}, "related")


def test_short_action_narration_is_valid_but_empty_beats_are_not() -> None:
    template = load_pack()["templates"][2]
    draft = SlideScript.model_validate(
        {
            "template_id": template["id"],
            "capture_recipe": "search",
            "source_ids": ["page"],
            "narration": "Type Solar System.",
            "narration_beats": [
                "Click the search field.",
                "Type Solar System.",
                "Search for Solar System.",
            ],
            "text": [
                {"slot_id": s["id"], "text": "Example"}
                for s in template["copy_slots"]
                if s["id"] != "caption"
            ],
        }
    )
    validate_slide(draft, template, {"page"}, "search")
    with pytest.raises(ValueError, match="nonempty"):
        validate_slide(
            draft.model_copy(update={"narration_beats": ["", "Open it", "Read it"]}),
            template,
            {"page"},
            "search",
        )


def test_article_narration_cannot_reuse_a_previous_earth_recipe() -> None:
    draft = SlideScript.model_validate(
        {
            "template_id": "focus-detail@2",
            "capture_recipe": "article",
            "source_ids": ["page"],
            "narration": "Explore Earth.",
            "narration_beats": ["Follow Earth.", "Read Natural history.", "Return to overview."],
            "text": [
                {"slot_id": "headline", "text": "Explore"},
                {"slot_id": "body", "text": "Read"},
            ],
        }
    )
    context = {"capture_behavior": {"start_url": "https://en.wikipedia.org/wiki/Solar_System"}}
    with pytest.raises(ValueError, match="does not match"):
        validate_capture_narration(draft, context)
    validate_capture_narration(
        draft.model_copy(
            update={
                "narration_beats": [
                    "Read Formation and evolution.",
                    "Open General characteristics.",
                    "Return to the overview.",
                ]
            }
        ),
        context,
    )


def test_director_preserves_full_paragraph_instead_of_short_action_summaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from demodirector_api import presentation_pilot as pilot

    template = load_pack()["templates"][2]
    paragraph = (
        "Click the search field to begin exploring a topic, type Solar System, "
        "then open the search result to read the article."
    )
    draft = SlideScript(
        template_id=template["id"], capture_recipe="search", source_ids=["page"],
        narration=paragraph,
        narration_beats=["Click search.", "Type Solar System.", "Open the result."],
        text=[pilot.SlideText(slot_id=s["id"], text="Example")
              for s in template["copy_slots"] if s["id"] != "caption"],
    )

    class Sessions:
        async def create_session(self, **kwargs: Any) -> None:
            pass

    class Runner:
        def __init__(self, **kwargs: Any) -> None:
            self.agent = kwargs["agent"]

        async def run_async(self, **kwargs: Any) -> AsyncIterator[Any]:
            self.agent.tools[0]()
            yield SimpleNamespace(
                is_final_response=lambda: True,
                content=SimpleNamespace(parts=[SimpleNamespace(text=(
                    json.dumps({"narration": paragraph})
                    if self.agent.name == "presentation_narration_rewriter"
                    else draft.model_dump_json()
                ))]),
            )

        async def close(self) -> None:
            pass

    monkeypatch.setattr(pilot, "Agent", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(pilot, "InMemorySessionService", Sessions)
    monkeypatch.setattr(pilot, "Runner", Runner)
    actual = pilot.PresentationPilotDirector(tmp_path).direct(
        {"sources": [{"id": "page"}]}, template, "search", 10_000, 2
    )
    assert actual.narration == paragraph
    assert actual.narration != " ".join(actual.narration_beats)

    rewritten = pilot.PresentationPilotDirector(tmp_path).rewrite_narration(
        {"sources": [{"id": "page"}], "capture_behavior": {"actions": ["Search"]},
         "narration_word_budget": len(paragraph.split()), "rewrite_feedback": "Expand."},
        draft.model_copy(update={"narration": "Search."}),
    )
    assert rewritten.narration == paragraph
    assert rewritten.narration_beats == draft.narration_beats
    assert list(tmp_path.glob("narration-rewrite-*.json"))
