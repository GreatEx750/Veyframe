import pytest
from demodirector_api.recording_workflows import ReviewedRecordingProfile, approved_workflow


def test_owned_roamstead_has_explicit_readiness_and_three_walkthroughs() -> None:
    workflow = approved_workflow("https://roamstead-web-tn7ddsxnmq-uc.a.run.app/")
    assert workflow is not None
    assert set(workflow) == {"title", "search", "article", "related"}
    assert any("fit" in (a.locator or "") for a in workflow["article"].preparation)
    assert all(a.type != "navigate" for r in workflow.values() for a in r.preparation)
    assert all(any(a.type == "click" for a in workflow[key].actions)
               for key in ["search", "article", "related"])


def test_workflows_do_not_match_lookalike_or_unapproved_hosts() -> None:
    assert approved_workflow("https://example.com/") is None
    assert approved_workflow("https://roamstead-web-tn7ddsxnmq-uc.a.run.app.evil.test/") is None
    assert approved_workflow("http://roamstead-web-tn7ddsxnmq-uc.a.run.app/") is None


def test_reviewed_profile_theme_is_explicit_and_validated() -> None:
    data = {"website_url": "https://example.com/", "recipes": {}}
    assert ReviewedRecordingProfile.model_validate(data).template_theme == "default"
    assert ReviewedRecordingProfile.model_validate(
        {**data, "template_theme": "google"}
    ).template_theme == "google"
    with pytest.raises(ValueError):
        ReviewedRecordingProfile.model_validate({**data, "template_theme": "../other"})
