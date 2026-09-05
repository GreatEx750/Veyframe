from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from demodirector_contracts import Project, Storyboard
from demodirector_contracts.evidence import (
    ContributionScene,
    ContributionSource,
    NarrationEvidence,
    SourceContribution,
    SourceContributionMap,
    StoryboardEvidence,
)

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


def statement_id(scene_id: str, sentence: str) -> str:
    digest = hashlib.sha256(normalized(sentence).encode()).hexdigest()[:12]
    return f"{scene_id}-statement-{digest}"


def safe_excerpt(text: str) -> str:
    return " ".join(text.split())[:500]


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
            for sentence in re.split(r"(?<=[.!?])\s+", scene.narration.strip()):
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
                            "id": statement_id(scene.id, sentence),
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

    def contribution_map(self, project_id: str) -> SourceContributionMap:
        project = self.projects.get(project_id)
        board = self.boards.get_latest(project_id)
        if project is None or board is None:
            raise KeyError("Storyboard not found")
        evidence = self.dashboard(project_id)
        approval = self.records.get(f"storyboard-approval-{project_id}")
        status: Literal["ready", "stale", "approval_required"] = (
            "ready"
            if evidence.approved
            else "stale"
            if approval is not None
            else "approval_required"
        )
        saved_sources = sorted(self.sources.list_for_project(project_id), key=lambda item: item.id)
        sources = [
            ContributionSource(
                id=f"brief:{project_id}",
                project_id=project_id,
                title="Project brief",
                domain="Creator input",
                origin="project_brief",
                retrieval_state="saved",
                retrieved_at=project.updated_at,
                excerpt=safe_excerpt(
                    f"{project.product_summary} Audience: {project.audience}. CTA: {project.cta}"
                ),
            ),
            *[
                ContributionSource(
                    id=source.id,
                    project_id=source.project_id,
                    title=source.title,
                    url=source.url,
                    domain=urlsplit(str(source.url)).hostname or "Saved source",
                    origin=(
                        "website_inspection"
                        if source.source_type == "website"
                        else "parallel_search"
                        if source.source_type == "partner_search"
                        else "project_brief"
                    ),
                    retrieval_state="saved",
                    retrieved_at=source.retrieved_at,
                    excerpt=safe_excerpt(source.snippet),
                )
                for source in saved_sources
            ],
        ]
        scenes = [
            ContributionScene(id=scene.id, title=scene.title, order=scene.order)
            for scene in sorted(board.scenes, key=lambda item: item.order)
        ]
        partial_evidence = not any(
            source.source_type == "website" for source in saved_sources
        ) or not any(source.source_type == "partner_search" for source in saved_sources)
        if status != "ready":
            return SourceContributionMap(
                project_id=project_id,
                storyboard_version=board.version,
                fingerprint=evidence.fingerprint,
                status=status,
                partial_evidence=partial_evidence,
                sources=sources,
                scenes=scenes,
                narration_statements=[],
                contributions=[],
            )

        contributions = [
            SourceContribution(
                id=f"brief:{project_id}:brief_context",
                project_id=project_id,
                source_id=f"brief:{project_id}",
                kind="brief_context",
                scene_ids=[scene.id for scene in scenes],
                usage_state="used" if scenes else "unused",
                label="Used to frame the approved storyboard",
            )
        ]
        board_scene_by_id = {scene.id: scene for scene in board.scenes}
        for source in saved_sources:
            linked_scene_ids = [
                scene.id
                for scene in sorted(board.scenes, key=lambda item: item.order)
                if source.id in scene.source_ids
            ]
            if source.source_type == "website":
                contributions.append(
                    SourceContribution(
                        id=f"{source.id}:website_structure",
                        project_id=project_id,
                        source_id=source.id,
                        kind="website_structure",
                        scene_ids=linked_scene_ids,
                        usage_state="used" if linked_scene_ids else "unused",
                        label=(
                            "Used to plan page structure and capture steps"
                            if linked_scene_ids
                            else "Inspected page — not used in the final capture plan"
                        ),
                    )
                )
            else:
                contributions.append(
                    SourceContribution(
                        id=f"{source.id}:research_context",
                        project_id=project_id,
                        source_id=source.id,
                        kind="research_context",
                        scene_ids=linked_scene_ids,
                        usage_state="used" if linked_scene_ids else "unused",
                        label=(
                            "Research context used in approved scenes"
                            if linked_scene_ids
                            else "Research context — not used in the final script"
                        ),
                    )
                )
            supported = [
                statement
                for statement in evidence.claims
                if statement.status in {"source_quote", "source_linked"}
                and source.id in statement.source_ids
            ]
            if supported:
                statement_scene_ids = list(
                    dict.fromkeys(
                        statement.scene_id
                        for statement in supported
                        if statement.scene_id in board_scene_by_id
                    )
                )
                contributions.append(
                    SourceContribution(
                        id=f"{source.id}:factual_narration",
                        project_id=project_id,
                        source_id=source.id,
                        kind="factual_narration",
                        scene_ids=statement_scene_ids,
                        narration_statement_ids=[statement.id for statement in supported],
                        usage_state="used",
                        label="Attributed in approved narration",
                    )
                )
        return SourceContributionMap(
            project_id=project_id,
            storyboard_version=board.version,
            fingerprint=evidence.fingerprint,
            status="ready",
            partial_evidence=partial_evidence,
            sources=sources,
            scenes=scenes,
            narration_statements=evidence.claims,
            contributions=contributions,
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
