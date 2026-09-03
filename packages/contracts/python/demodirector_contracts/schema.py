from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from demodirector_contracts.models import (
    AuthError,
    BriefCoverageReport,
    CaptureAction,
    CapturePlan,
    DemoGenerationResult,
    EditOperation,
    InteractionEvent,
    LoginRequest,
    LoginResult,
    LogoutResult,
    MissingRequirementRepairProposal,
    MissingRequirementRepairResult,
    Project,
    QACheck,
    ReauthenticationRequired,
    ResearchSource,
    Scene,
    SessionState,
    SessionSummary,
    SignupRequest,
    SignupResult,
    Storyboard,
    Timeline,
    UserIdentity,
    UserProfile,
    VideoExport,
    ZoomClip,
)

CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    Project,
    UserIdentity,
    UserProfile,
    SessionSummary,
    SessionState,
    LoginRequest,
    LoginResult,
    LogoutResult,
    ReauthenticationRequired,
    SignupRequest,
    SignupResult,
    AuthError,
    ResearchSource,
    Storyboard,
    Scene,
    CapturePlan,
    CaptureAction,
    InteractionEvent,
    Timeline,
    ZoomClip,
    EditOperation,
    QACheck,
    BriefCoverageReport,
    MissingRequirementRepairProposal,
    MissingRequirementRepairResult,
    VideoExport,
    DemoGenerationResult,
)


def build_contract_schema() -> dict[str, Any]:
    model_schemas, definitions = models_json_schema(
        [(model, "validation") for model in CONTRACT_MODELS],
        title="DemoDirector shared contracts",
    )
    references = [model_schemas[(model, "validation")] for model in CONTRACT_MODELS]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **definitions,
        "oneOf": references,
        "x-contracts": [model.__name__ for model in CONTRACT_MODELS],
    }


def write_contract_schema(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(build_contract_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
