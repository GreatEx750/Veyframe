from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from demodirector_contracts import BriefCoverageReport, Storyboard, Timeline

from demodirector_api.google_ai import StructuredAIService


class BriefCoverageValidationError(ValueError):
    """Raised when a QA report cites requirements or evidence outside its inputs."""


class BriefCoverageService:
    def __init__(self, ai_service: StructuredAIService) -> None:
        self.ai_service = ai_service

    def analyze(
        self,
        project_id: str,
        brief: str,
        storyboard: Storyboard,
        timeline: Timeline,
        capture_evidence: Mapping[str, Sequence[str]],
    ) -> BriefCoverageReport:
        if not brief.strip():
            raise ValueError("original brief must not be empty")
        report = self.ai_service.generate_structured(
            prompt=build_coverage_prompt(brief, storyboard, timeline, capture_evidence),
            response_model=BriefCoverageReport,
        )
        validate_coverage_report(
            report,
            project_id,
            brief,
            storyboard,
            timeline,
            capture_evidence,
        )
        return report


def build_coverage_prompt(
    brief: str,
    storyboard: Storyboard,
    timeline: Timeline,
    capture_evidence: Mapping[str, Sequence[str]],
) -> str:
    evidence_catalog = build_evidence_catalog(storyboard, timeline, capture_evidence)
    context = {
        "project_id": storyboard.project_id,
        "brief": brief,
        "storyboard": [
            {
                "id": scene.id,
                "title": scene.title,
                "objective": scene.objective,
                "narration": scene.narration,
                "expected_evidence": scene.expected_evidence,
            }
            for scene in storyboard.scenes
        ],
        "timeline": {
            "duration_ms": timeline.duration_ms,
            "scene_clip_ids": [clip.id for clip in timeline.scene_clips],
            "caption_clip_ids": [clip.id for clip in timeline.caption_clips],
            "zoom_clip_ids": [clip.id for clip in timeline.zoom_clips],
            "audio_clip_ids": [clip.id for clip in timeline.audio_clips],
            "narration_override_scene_ids": list(timeline.narration_overrides),
            "cta_text": timeline.cta_text,
        },
        "evidence_catalog": evidence_catalog,
    }
    return (
        "You are DemoDirector's Demo QA Agent. Extract distinct typed requirements from the "
        "original brief, then compare them with the storyboard, narration, capture evidence, "
        "and final timeline metadata. Mark each requirement covered, partial, or missing. A "
        "covered item must cite only exact scene IDs and evidence reference IDs from the provided "
        "catalog. Missing items need a specific suggested repair and no invented evidence. Use "
        "generic product language such as Brief Coverage and Demo QA; never discuss contests, "
        "judges, or scoring. Return one BriefCoverageReport only. Context: "
        f"{json.dumps(context, separators=(',', ':'))}"
    )


def build_evidence_catalog(
    storyboard: Storyboard,
    timeline: Timeline,
    capture_evidence: Mapping[str, Sequence[str]],
) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for scene in storyboard.scenes:
        catalog[f"scene:{scene.id}"] = f"Storyboard scene: {scene.title}"
        catalog[f"scene:{scene.id}:narration"] = scene.narration
        for index, evidence in enumerate(scene.expected_evidence):
            catalog[f"scene:{scene.id}:expected:{index}"] = evidence
        for index, evidence in enumerate(capture_evidence.get(scene.id, ())):
            catalog[f"capture:{scene.id}:{index}"] = evidence
    for scene_clip in timeline.scene_clips:
        catalog[f"timeline:scene:{scene_clip.id}"] = f"Scene clip for {scene_clip.scene_id}"
    for caption_clip in timeline.caption_clips:
        catalog[f"timeline:caption:{caption_clip.id}"] = caption_clip.text
    for zoom_clip in timeline.zoom_clips:
        catalog[f"timeline:zoom:{zoom_clip.id}"] = (
            f"Zoom from {zoom_clip.start_ms} to {zoom_clip.end_ms}"
        )
    for audio_clip in timeline.audio_clips:
        catalog[f"timeline:audio:{audio_clip.id}"] = (
            f"Narration audio for {audio_clip.scene_id}"
        )
    return catalog


def validate_coverage_report(
    report: BriefCoverageReport,
    project_id: str,
    brief: str,
    storyboard: Storyboard,
    timeline: Timeline,
    capture_evidence: Mapping[str, Sequence[str]],
) -> None:
    if report.project_id != project_id:
        raise BriefCoverageValidationError(
            "QA report project does not match the requested project."
        )
    if storyboard.project_id != project_id or timeline.project_id != project_id:
        raise BriefCoverageValidationError("QA inputs must belong to the requested project.")
    normalized_brief = " ".join(brief.lower().split())
    requirements = {requirement.id: requirement for requirement in report.requirements}
    checks = {check.requirement_id: check for check in report.checks}
    known_scenes = {scene.id for scene in storyboard.scenes}
    evidence_catalog = build_evidence_catalog(storyboard, timeline, capture_evidence)
    for requirement in report.requirements:
        excerpt = " ".join(requirement.source_excerpt.lower().split())
        if excerpt not in normalized_brief:
            raise BriefCoverageValidationError(
                f"Requirement {requirement.id} is not grounded in the original brief."
            )
        check = checks[requirement.id]
        if check.requirement != requirement.text:
            raise BriefCoverageValidationError(
                f"QA check text does not match requirement {requirement.id}."
            )
        if set(check.scene_ids) - known_scenes:
            raise BriefCoverageValidationError(
                f"QA check {requirement.id} cites an unknown scene."
            )
        if set(check.evidence) - set(evidence_catalog):
            raise BriefCoverageValidationError(
                f"QA check {requirement.id} cites unknown evidence."
            )
    if set(checks) != set(requirements):
        raise BriefCoverageValidationError("QA report must check every brief requirement once.")
