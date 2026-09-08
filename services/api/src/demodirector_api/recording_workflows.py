"""Reviewed walkthroughs for explicitly owner-authorized recording destinations.

These are deterministic capture profiles, not AI-discovered navigation. Direction,
copy, research and narration still run through the regular generation pipeline.
"""

import os
import re
from pathlib import Path
from typing import Literal

from demodirector_contracts import CaptureAction
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RecordingRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preparation: list[CaptureAction] = Field(default_factory=list, max_length=30)
    actions: list[CaptureAction] = Field(default_factory=list, max_length=30)
    direction_note: str = Field(default="", max_length=1500)


class ReviewedRecordingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    website_url: HttpUrl
    template_theme: Literal["default", "google"] = "default"
    recipes: dict[str, RecordingRecipe] = Field(max_length=13)


def load_reviewed_workflow(
    url: str, project_id: str, artifact_root: Path
) -> dict[str, RecordingRecipe] | None:
    profile = load_reviewed_profile(url, project_id, artifact_root)
    return profile.recipes if profile else approved_workflow(url)


def load_reviewed_profile(
    url: str, project_id: str, artifact_root: Path
) -> ReviewedRecordingProfile | None:
    """Read an operator-authored profile; model output never writes these files."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", project_id):
        raise ValueError("Invalid recording profile project identifier")
    folder = (artifact_root / "recording-workflows").resolve()
    path = (folder / f"{project_id}.json").resolve()
    if path.parent != folder:
        raise ValueError("Recording profile escaped its directory")
    if not path.exists():
        return None
    if path.stat().st_size > 100_000:
        raise ValueError("Recording profile is too large")
    profile = ReviewedRecordingProfile.model_validate_json(path.read_text("utf-8"))
    if str(profile.website_url).rstrip("/") != url.rstrip("/"):
        raise ValueError("Reviewed recording destination does not match the project")
    if not {"title", "search", "article", "related"}.issubset(profile.recipes):
        raise ValueError("Recording profile is missing required recipes")
    for name, recipe in profile.recipes.items():
        if name not in {"title", "search", "article", "related"} and not re.fullmatch(
            r"slide-[1-9]", name
        ):
            raise ValueError("Unknown recording recipe")
        for action in [*recipe.preparation, *recipe.actions]:
            if action.type not in {
                "click", "fill", "select", "wait_for", "assert_visible", "scroll"
            }:
                raise ValueError("Unsupported reviewed recording action")
    return profile


def _step(kind: str, target: str, description: str, value: str | None = None) -> CaptureAction:
    return CaptureAction.model_validate({
        "type": kind, "locator_strategy": "css", "locator": target,
        "description": description, "value": value,
    })


def approved_workflow(url: str) -> dict[str, RecordingRecipe] | None:
    approved_origin = os.getenv("ROAMSTEAD_DEMO_ORIGIN", "").rstrip("/")
    if not approved_origin or url.rstrip("/") != approved_origin:
        return None
    profile = [
        _step("click", 'button:has-text("Explore with demo access")', "Open the demo profile"),
        _step("wait_for", 'select[aria-label="Choose city"]:enabled', "Wait for the profile"),
    ]
    workspace = [
        *profile,
        _step("click", 'button:has-text("Show my matches")', "Load matching properties"),
        _step("wait_for", 'article button:has-text("View property") >> nth=0',
              "Wait for property cards"),
        _step("wait_for", '[aria-label^="Google Map"] '
              'gmp-advanced-marker[aria-label$="fit"]'
              ' >> nth=0', "Wait for property markers on the loaded map"),
        _step("scroll", "article >> nth=0", "Bring the property photos into view"),
    ]
    return {
        "title": RecordingRecipe(),
        "search": RecordingRecipe(preparation=profile, actions=[
            _step("click", 'select[aria-label="Choose city"]', "Review the destination city"),
            _step("click", 'button:has-text("Rent")', "Choose the rental housing plan"),
            _step("click", 'button:has-text("Buy")', "Compare the purchase housing plan"),
        ]),
        "article": RecordingRecipe(preparation=workspace, actions=[
            _step("click", 'article button:has-text("View property") >> nth=1',
                  "Open a matched home and review its photos and profile-fit explanation"),
            _step("scroll", 'h3:has-text("Why it fits your profile")',
                  "Inspect the reasons this home matches the household"),
            _step("click", 'button[aria-label="Close property"]',
                  "Return to the property shortlist"),
        ]),
        "related": RecordingRecipe(preparation=workspace, actions=[
            _step("click", 'button:has-text("Satellite")', "Explore the satellite map"),
            _step("click", 'button:has-text("Normal")',
                  "Return to the street map with home markers"),
            _step("click", 'article button:has-text("View property") >> nth=1',
                  "Inspect a matching home from the property shortlist"),
        ]),
    }
