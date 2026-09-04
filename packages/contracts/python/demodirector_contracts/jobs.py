from datetime import datetime
from typing import Literal

from pydantic import Field

from demodirector_contracts.models import ContractModel, NonEmptyString

GenerationStage = Literal[
    "inspection",
    "research",
    "understanding",
    "storyboard",
    "capture",
    "narration",
    "render",
    "done",
]


class GenerationJob(ContractModel):
    id: NonEmptyString
    project_id: NonEmptyString
    status: Literal[
        "queued", "running", "awaiting_approval", "awaiting_retry", "failed", "succeeded"
    ]
    stage: GenerationStage
    completed_stages: list[GenerationStage] = Field(default_factory=list)
    attempts: int = Field(default=0, ge=0, le=3)
    version: int = Field(gt=0)
    created_at: datetime
    updated_at: datetime
    lease_until: datetime | None = None
    message: NonEmptyString
    export_id: str | None = None
    timeline_version: int | None = None
