from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from demodirector_contracts.models import ContractModel, NonEmptyString, ResearchSource


class NarrationEvidence(ContractModel):
    id: NonEmptyString
    scene_id: NonEmptyString
    text: NonEmptyString
    status: Literal["source_quote", "source_linked", "user_assertion", "unverified"]
    source_ids: list[NonEmptyString]
    explanation: NonEmptyString


class ContributionSource(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    title: NonEmptyString
    url: HttpUrl | None = None
    domain: NonEmptyString
    origin: Literal["project_brief", "website_inspection", "parallel_search"]
    retrieval_state: Literal["saved", "partial"]
    retrieved_at: datetime | None = None
    excerpt: str = Field(min_length=1, max_length=500)


class ContributionScene(ContractModel):
    id: NonEmptyString
    title: NonEmptyString
    order: int = Field(ge=0)


class SourceContribution(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    source_id: NonEmptyString
    kind: Literal[
        "brief_context", "website_structure", "research_context", "factual_narration"
    ]
    scene_ids: list[NonEmptyString] = Field(default_factory=list)
    narration_statement_ids: list[NonEmptyString] = Field(default_factory=list)
    usage_state: Literal["used", "unused"]
    label: NonEmptyString


class SourceContributionMap(ContractModel):
    project_id: NonEmptyString
    storyboard_version: int = Field(gt=0)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["ready", "stale", "approval_required"]
    partial_evidence: bool
    sources: list[ContributionSource]
    scenes: list[ContributionScene]
    narration_statements: list[NarrationEvidence]
    contributions: list[SourceContribution]

    @model_validator(mode="after")
    def references_are_project_owned_and_supported(self) -> "SourceContributionMap":
        source_by_id = {source.id: source for source in self.sources}
        scene_ids = {scene.id for scene in self.scenes}
        statement_by_id = {statement.id: statement for statement in self.narration_statements}
        if len(source_by_id) != len(self.sources) or len(scene_ids) != len(self.scenes):
            raise ValueError("Contribution source and scene IDs must be unique")
        if len(statement_by_id) != len(self.narration_statements):
            raise ValueError("Narration statement IDs must be unique")
        if any(source.project_id != self.project_id for source in self.sources):
            raise ValueError("Contribution sources must belong to the project")
        if self.status != "ready" and (self.contributions or self.narration_statements):
            raise ValueError("Unapproved contribution maps must not retain usage references")
        for statement in self.narration_statements:
            if (
                statement.scene_id not in scene_ids
                or set(statement.source_ids) - source_by_id.keys()
            ):
                raise ValueError("Narration statements must reference known project evidence")
        contribution_ids: set[str] = set()
        for contribution in self.contributions:
            if contribution.id in contribution_ids:
                raise ValueError("Contribution IDs must be unique")
            contribution_ids.add(contribution.id)
            if contribution.project_id != self.project_id:
                raise ValueError("Contributions must belong to the project")
            if contribution.source_id not in source_by_id:
                raise ValueError("Contributions must reference known project evidence")
            if set(contribution.scene_ids) - scene_ids:
                raise ValueError("Contributions must reference known storyboard scenes")
            if set(contribution.narration_statement_ids) - statement_by_id.keys():
                raise ValueError("Contributions must reference known narration statements")
            has_usage = bool(contribution.scene_ids or contribution.narration_statement_ids)
            if (contribution.usage_state == "used") != has_usage:
                raise ValueError("Contribution usage state must match its references")
            if contribution.kind == "website_structure" and contribution.narration_statement_ids:
                raise ValueError("Website structure is a capture input, not a factual claim")
            if contribution.kind == "factual_narration":
                if not contribution.narration_statement_ids:
                    raise ValueError("Factual narration contributions require statements")
                for statement_id in contribution.narration_statement_ids:
                    statement = statement_by_id[statement_id]
                    if (
                        statement.status not in {"source_quote", "source_linked"}
                        or contribution.source_id not in statement.source_ids
                        or statement.scene_id not in contribution.scene_ids
                    ):
                        raise ValueError("Factual narration must be supported by saved evidence")
        return self


class StoryboardEvidence(ContractModel):
    project_id: NonEmptyString
    storyboard_version: int = Field(gt=0)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    claims: list[NarrationEvidence]
    sources: list[ResearchSource]
    unverified_count: int = Field(ge=0)
    approved: bool
    approval_required: bool = True
