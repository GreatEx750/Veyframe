from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from demodirector_contracts import EditOperation, Timeline
from demodirector_contracts.quality import OptimizationProposal, OptimizationRun, VideoReview

from demodirector_api.records import RecordConflict, RecordStore
from demodirector_api.repositories import TimelineRepository
from demodirector_api.timeline_edits import TimelineEditService
from demodirector_api.video_reviews import ReviewConflict, VideoReviewService


def propose_repairs(review: VideoReview, timeline: Timeline) -> OptimizationProposal:
    """Conservative deterministic repairs; no model-authored executable instructions."""
    assert review.result is not None
    operations: list[EditOperation] = []
    selected: list[str] = []
    unsupported: list[str] = []
    used: set[str] = set()
    rank = {"high": 0, "medium": 1, "low": 2}
    for finding in sorted(
        review.result.findings, key=lambda f: (rank[f.severity], f.start_ms, f.id)
    ):
        if len(operations) >= 3:
            unsupported.append(finding.id)
            continue
        if finding.repair_category == "camera":
            zoom = next(
                (
                    z
                    for z in timeline.zoom_clips
                    if z.id not in used
                    and z.start_ms < finding.end_ms
                    and z.end_ms > finding.start_ms
                ),
                None,
            )
            if zoom is not None:
                operations.append(
                    EditOperation(
                        operation_type="delete_zoom",
                        target_id=zoom.id,
                        rationale=f"Remove movement at the cited defect: {finding.observation}",
                    )
                )
                selected.append(finding.id)
                used.add(zoom.id)
                continue
        if finding.repair_category == "caption":
            caption = next(
                (
                    c
                    for c in timeline.caption_clips
                    if c.id not in used
                    and c.start_ms < finding.end_ms
                    and c.end_ms > finding.start_ms
                    and len(c.text) > 45
                    and "\n" not in c.text
                ),
                None,
            )
            if caption is not None:
                words = caption.text.split(" ")
                midpoint = len(words) // 2
                wrapped = " ".join(words[:midpoint]) + "\n" + " ".join(words[midpoint:])
                operations.append(
                    EditOperation(
                        operation_type="update_caption",
                        target_id=caption.id,
                        arguments={"text": wrapped},
                        rationale="Wrap the caption into two lines without changing its words.",
                    )
                )
                selected.append(finding.id)
                used.add(caption.id)
                continue
        unsupported.append(finding.id)
    return OptimizationProposal(
        operations=operations,
        finding_ids=selected,
        unsupported_findings=unsupported,
        explanation="Highest severity first, then playback time. Up to three low-cost camera "
        "or caption repairs; no new footage, narration, CTA, or duration changes. "
        "Improvement is unproven until the new render is reviewed.",
    )


class OptimizationService:
    def __init__(
        self, reviews: VideoReviewService, timelines: TimelineRepository, records: RecordStore
    ) -> None:
        self.reviews = reviews
        self.timelines = timelines
        self.records = records

    def get(self, project_id: str, run_id: str) -> OptimizationRun:
        record = self.records.get(f"optimization-{run_id}")
        if record is None or record[1]["project_id"] != project_id:
            raise KeyError("Optimization not found")
        return OptimizationRun.model_validate(record[1])

    def propose(self, project_id: str, review_id: str) -> OptimizationRun:
        review = self.reviews.get(project_id, review_id)
        if review.status != "succeeded" or review.overall_score is None:
            raise ReviewConflict("Optimization needs a successful persisted review.")
        history = self.timelines.current(project_id)
        lineage = self.records.get(f"export-{review.export_id}")
        if (
            history is None
            or lineage is None
            or history.current.version != review.timeline_version
            or history.current.timeline.model_dump(mode="json") != lineage[1]["timeline"]
        ):
            raise ReviewConflict(
                "The reviewed timeline is stale; export and review the current version."
            )
        proposal = propose_repairs(review, history.current.timeline)
        run = OptimizationRun(
            id=str(uuid4()),
            project_id=project_id,
            review_id=review.id,
            before_export_id=review.export_id,
            before_version=review.timeline_version,
            before_score=review.overall_score,
            proposal=proposal,
            status="proposed",
            stop_reason="awaiting_approval" if proposal.operations else "unsupported",
            created_at=datetime.now(UTC),
            message="Review each operation before applying. "
            "One repair cycle and one follow-up AI review are allowed.",
        )
        self.records.put(f"optimization-{run.id}", 0, run.model_dump(mode="json"))
        return run

    def cancel(self, project_id: str, run_id: str) -> OptimizationRun:
        run = self.get(project_id, run_id)
        if run.status != "proposed":
            raise ReviewConflict("Only an unapplied proposal can be cancelled.")
        return self._save(
            run.model_copy(
                update={
                    "status": "cancelled",
                    "stop_reason": "cancelled",
                    "message": "No edits were applied.",
                }
            ),
            1,
        )

    def apply(
        self, project_id: str, run_id: str, expected_version: int, approved: bool
    ) -> OptimizationRun:
        run = self.get(project_id, run_id)
        if run.status != "proposed":
            return run
        if not approved:
            raise ReviewConflict("Explicit approval is required for the edits and one AI review.")
        if expected_version != run.before_version:
            raise ReviewConflict("The approved timeline version does not match the proposal.")
        if not run.proposal.operations:
            raise ReviewConflict(
                "No supported automatic repair; use the editor for these findings."
            )
        history = self.timelines.current(project_id)
        if history is None or history.current.version != expected_version:
            raise ReviewConflict("Timeline changed; request a fresh proposal.")
        self._save(run.model_copy(update={"status": "running"}), 1)
        try:
            # Keep the old video preferred until the creator explicitly chooses another export.
            preference = self.records.get(f"preferred-{project_id}")
            self.records.put(
                f"preferred-{project_id}",
                preference[0] if preference else 0,
                {"export_id": run.before_export_id},
            )
            updated = TimelineEditService(self.timelines).apply(
                history.current.timeline,
                expected_version,
                run.proposal.operations,
                f"Approved optimization {run.id}",
            )
        except Exception:
            return self._save(
                run.model_copy(
                    update={
                        "status": "failed",
                        "stop_reason": "apply_failed",
                        "message": "Edit transaction failed; no partial operations were applied.",
                    }
                ),
                2,
            )
        run = run.model_copy(update={"after_version": updated.current.version, "cycles": 1})
        self._save(run.model_copy(update={"status": "running"}), 2)
        video = self.reviews.exports.create(project_id, updated.current.timeline, "1440p")
        run = run.model_copy(update={"after_export_id": video.id})
        if video.status != "succeeded":
            return self._save(
                run.model_copy(
                    update={
                        "status": "failed",
                        "stop_reason": "render_failed",
                        "message": "Render failed; edits saved. Original video unchanged.",
                    }
                ),
                3,
            )
        try:
            after = self.reviews.create(project_id, video.id)
            if after.status != "succeeded" or after.overall_score is None:
                raise ReviewConflict("Follow-up review failed")
        except Exception:
            return self._save(
                run.model_copy(
                    update={
                        "status": "failed",
                        "stop_reason": "review_failed",
                        "model_calls": 1,
                        "message": "Video rendered; review failed. No improvement is claimed.",
                    }
                ),
                3,
            )
        delta = round(after.overall_score - run.before_score, 2)
        return self._save(
            run.model_copy(
                update={
                    "status": "succeeded",
                    "after_review_id": after.id,
                    "after_score": after.overall_score,
                    "score_delta": delta,
                    "model_calls": after.model_calls,
                    "stop_reason": "target_reached"
                    if after.overall_score >= 90 and delta >= 3
                    else "improved"
                    if delta >= 3
                    else "no_improvement",
                    "message": "One-cycle limit reached. The original stays preferred. "
                    "Scores are model assessments, not an independent guarantee of improvement.",
                }
            ),
            3,
        )

    def _save(self, run: OptimizationRun, expected: int) -> OptimizationRun:
        try:
            self.records.put(f"optimization-{run.id}", expected, run.model_dump(mode="json"))
        except RecordConflict as error:
            raise ReviewConflict(str(error)) from error
        return run
