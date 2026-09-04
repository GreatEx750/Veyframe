from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime

from demodirector_contracts import Project, Storyboard
from demodirector_contracts.evidence import NarrationEvidence, StoryboardEvidence

from demodirector_api.generation_jobs import ApprovalNeeded
from demodirector_api.records import RecordStore
from demodirector_api.repositories import (
    ProductUnderstandingRepository,
    ProjectRepository,
    ResearchSourceRepository,
    StoryboardRepository,
)


def normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


class EvidenceService:
    def __init__(
        self,
        projects: ProjectRepository,
        sources: ResearchSourceRepository,
        boards: StoryboardRepository,
        understandings: ProductUnderstandingRepository,
        records: RecordStore,
    ) -> None:
        self.projects, self.sources, self.boards = projects, sources, boards
        self.understandings, self.records = understandings, records

    def dashboard(self, project_id: str) -> StoryboardEvidence:
        project = self.projects.get(project_id)
        board = self.boards.get_latest(project_id)
        if project is None or board is None:
            raise KeyError("Storyboard not found")
        sources = self.sources.list_for_project(project_id)
        understanding = self.understandings.get(project_id)
        known = {source.id: source for source in sources}
        if any(source.project_id != project_id for source in sources):
            raise ValueError("Foreign project evidence was rejected")
        if any(set(scene.source_ids) - known.keys() for scene in board.scenes):
            raise ValueError("Storyboard cites missing evidence; fix the source references first")
        inputs = {
            "website_url": str(project.website_url),
            "product_summary": project.product_summary,
            "audience": project.audience,
            "tone": project.tone,
            "duration": project.requested_duration_seconds,
            "cta": project.cta,
        }
        snapshot = {
            "board": board.model_dump(mode="json"),
            "brief": inputs,
            "sources": [s.model_dump(mode="json") for s in sorted(sources, key=lambda s: s.id)],
            "understanding": understanding.model_dump(mode="json") if understanding else None,
        }
        fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
        claims: list[NarrationEvidence] = []
        for scene in sorted(board.scenes, key=lambda scene: scene.order):
            for index, sentence in enumerate(re.split(r"(?<=[.!?])\s+", scene.narration.strip())):
                if not sentence.strip():
                    continue
                text = normalized(sentence)
                linked = list(scene.source_ids)
                quotes = [
                    sid
                    for sid in linked
                    if text
                    and text in normalized(known[sid].snippet)
                    and known[sid].source_type != "user"
                ]
                from_brief = bool(text) and any(
                    text in normalized(value) for value in (project.product_summary, project.cta)
                )
                matches = (
                    []
                    if understanding is None
                    else [
                        claim
                        for claim in understanding.claims
                        if normalized(claim.text) == text
                        and claim.source_ids
                        and not (set(claim.source_ids) - known.keys())
                    ]
                )
                if quotes:
                    status = "source_quote"
                    refs = quotes
                    explanation = "Text appears in a saved excerpt; judge source accuracy yourself."
                elif from_brief:
                    status = "user_assertion"
                    refs = []
                    explanation = (
                        "Stated in your supplied brief or CTA, not independently verified."
                    )
                elif matches:
                    status = "source_linked"
                    refs = list(dict.fromkeys(sid for claim in matches for sid in claim.source_ids))
                    explanation = "AI-attributed sources, not independently verified facts."
                else:
                    status = "unverified"
                    refs = linked
                    explanation = "No exact support found. Check this statement before approving."
                claims.append(
                    NarrationEvidence.model_validate(
                        {
                            "id": f"{scene.id}-claim-{index + 1}",
                            "scene_id": scene.id,
                            "text": sentence,
                            "status": status,
                            "source_ids": refs,
                            "explanation": explanation,
                        }
                    )
                )
        approval = self.records.get(f"storyboard-approval-{project_id}")
        return StoryboardEvidence(
            project_id=project_id,
            storyboard_version=board.version,
            fingerprint=fingerprint,
            claims=claims,
            sources=sources,
            unverified_count=sum(
                claim.status in {"unverified", "source_linked"} for claim in claims
            ),
            approved=approval is not None and approval[1]["fingerprint"] == fingerprint,
        )

    def approve(
        self, project_id: str, version: int, fingerprint: str, acknowledge_unverified: bool
    ) -> StoryboardEvidence:
        dashboard = self.dashboard(project_id)
        if dashboard.storyboard_version != version or dashboard.fingerprint != fingerprint:
            raise ValueError("Storyboard or evidence changed. Reload before approving.")
        if dashboard.unverified_count and not acknowledge_unverified:
            raise ValueError("Review and explicitly acknowledge the unverified statements first.")
        project = self.projects.get(project_id)
        assert project is not None
        board = self.boards.get_latest(project_id)
        if board is None or board.version != version:
            raise ValueError("Storyboard changed before approval was saved.")
        key = f"storyboard-approval-{project_id}"
        previous = self.records.get(key)
        self.records.put(
            key,
            previous[0] if previous else 0,
            {
                "project_id": project_id,
                "fingerprint": fingerprint,
                "storyboard_version": version,
                "owner_user_id": project.owner_user_id,
                "created_at": datetime.now(UTC).isoformat(),
                "acknowledged_unverified": acknowledge_unverified,
                "approved_storyboard": board.model_dump(mode="json"),
                "approved_project": project.model_dump(mode="json"),
            },
        )
        return self.dashboard(project_id)

    def approved_board(self, project_id: str) -> Storyboard:
        return self.approved_inputs(project_id)[0]

    def approved_inputs(self, project_id: str) -> tuple[Storyboard, Project]:
        try:
            evidence = self.dashboard(project_id)
            saved = self.records.get(f"storyboard-approval-{project_id}")
            board = (
                None
                if saved is None
                else Storyboard.model_validate(saved[1]["approved_storyboard"])
            )
            if (
                not evidence.approved
                or saved is None
                or saved[1]["fingerprint"] != evidence.fingerprint
                or board is None
                or board.version != evidence.storyboard_version
            ):
                raise ApprovalNeeded("Storyboard needs approval")
            return board, Project.model_validate(saved[1]["approved_project"])
        except (KeyError, ValueError) as error:
            raise ApprovalNeeded("Review storyboard evidence before capture") from error
