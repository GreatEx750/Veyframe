import json
from pathlib import Path

import pytest
from demodirector_api.recording_workflows import load_reviewed_workflow


def test_operator_profile_is_scoped_to_project_and_exact_destination(tmp_path: Path) -> None:
    folder = tmp_path / "recording-workflows"
    folder.mkdir()
    payload = {"website_url": "https://example.com/", "recipes": {
        name: {"actions": []} for name in ["title", "search", "article", "related"]
    }}
    (folder / "project-1.json").write_text(json.dumps(payload), "utf-8")
    assert load_reviewed_workflow("https://example.com/", "project-1", tmp_path)
    assert load_reviewed_workflow("https://example.com/", "project-2", tmp_path) is None
    with pytest.raises(ValueError, match="destination"):
        load_reviewed_workflow("https://another.test/", "project-1", tmp_path)
    with pytest.raises(ValueError, match="identifier"):
        load_reviewed_workflow("https://example.com/", "../project-1", tmp_path)


def test_profile_does_not_accept_executable_code(tmp_path: Path) -> None:
    folder = tmp_path / "recording-workflows"
    folder.mkdir()
    (folder / "project-1.json").write_text(json.dumps({
        "website_url": "https://example.com/", "recipes": {
            "title": {"actions": [{"type": "javascript", "value": "alert(1)"}]}
        },
    }), "utf-8")
    with pytest.raises(ValueError):
        load_reviewed_workflow("https://example.com/", "project-1", tmp_path)
