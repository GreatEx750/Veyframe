from typing import Literal

from pydantic import Field

from demodirector_contracts.models import ContractModel, NonEmptyString, ResearchSource


class NarrationEvidence(ContractModel):
    id: NonEmptyString
    scene_id: NonEmptyString
    text: NonEmptyString
    status: Literal["source_quote", "source_linked", "user_assertion", "unverified"]
    source_ids: list[NonEmptyString]
    explanation: NonEmptyString


class StoryboardEvidence(ContractModel):
    project_id: NonEmptyString
    storyboard_version: int = Field(gt=0)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    claims: list[NarrationEvidence]
    sources: list[ResearchSource]
    unverified_count: int = Field(ge=0)
    approved: bool
    approval_required: bool = True
