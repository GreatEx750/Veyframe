from pathlib import Path
from typing import Any

import pytest
from demodirector_api.activity_cards import ActivityCardDirector, ActivityPanel, validate_panel
from pydantic import ValidationError


def panel_data() -> dict[str, Any]:
    return {
        "heading": "WIKIPEDIA ACTIVITY",
        "cards": [{"label": f"FEATURE {i}", "detail": "Explore article sections",
                   "status": "RECORDED", "source_ids": ["page"],
                   "action_refs": ["article:0"]} for i in range(4)],
    }


def context() -> dict[str, Any]:
    return {"sources": [{"id": "page", "title": "Wikipedia",
                         "snippet": "Explore article sections using the table of contents"}],
            "workflow": [{"ref": "article:0"}], "recorded_action_refs": ["article:0"]}


def test_four_evidence_grounded_cards_map_to_thirteen_slots() -> None:
    panel = ActivityPanel.model_validate(panel_data())
    validate_panel(panel, context())
    assert len(panel.slot_copy()) == 13
    data = panel_data()
    data["cards"].pop()
    with pytest.raises(ValidationError):
        ActivityPanel.model_validate(data)


@pytest.mark.parametrize("mutation", ["source", "action", "recorded", "backend", "duplicate"])
def test_rejects_unsupported_claims(mutation: str) -> None:
    data, evidence = panel_data(), context()
    if mutation == "source":
        data["cards"][0]["source_ids"] = ["unknown"]
    elif mutation == "action":
        data["cards"][0]["action_refs"] = ["unknown"]
    elif mutation == "recorded":
        evidence["recorded_action_refs"] = []
    elif mutation == "backend":
        data["cards"][0]["detail"] = "Gemini ADK coordinates Wikipedia"
    else:
        data["cards"][0]["label"] = data["cards"][1]["label"]
    with pytest.raises(ValueError):
        validate_panel(ActivityPanel.model_validate(data), evidence)


def test_generation_is_cached_only_for_matching_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    async def generate(self: Any, evidence: Any, feedback: str) -> Any:
        calls.append(evidence)
        return ActivityPanel.model_validate(panel_data()), {"evidence_reads": 1}

    monkeypatch.setattr(ActivityCardDirector, "_generate", generate)
    director = ActivityCardDirector(tmp_path)
    director.generate(context())
    director.generate(context())
    assert len(calls) == 1
    changed = context()
    changed["sources"][0]["snippet"] += " Updated evidence."
    director.generate(changed)
    assert len(calls) == 2


def test_rejected_generation_never_falls_back_to_static_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def generate(self: Any, evidence: Any, feedback: str) -> Any:
        calls.append(feedback)
        raise ValueError("Evidence review rejected the cards: action was not recorded")

    monkeypatch.setattr(ActivityCardDirector, "_generate", generate)
    with pytest.raises(ValueError, match="action was not recorded"):
        ActivityCardDirector(tmp_path).generate(context())
    assert len(calls) == 3
    assert "action was not recorded" in calls[1]
    assert not (tmp_path / "slide-06-activity-adk.json").exists()
