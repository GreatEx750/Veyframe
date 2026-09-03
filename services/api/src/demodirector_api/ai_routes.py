from typing import Literal

from demodirector_worker.narration import GeminiTTSSettings
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from demodirector_api.google_ai import StructuredAIService


class AIRuntimeHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "unavailable"]
    provider: Literal["google"]
    model: str
    tts_model: str
    agent: str
    detail: str | None = None


router = APIRouter(prefix="/ai", tags=["ai-runtime"])


@router.get("/health", response_model=AIRuntimeHealth)
def ai_health(request: Request) -> AIRuntimeHealth:
    service: StructuredAIService = request.app.state.ai_service
    is_ready = service.state.value != "unavailable"
    return AIRuntimeHealth(
        status="ready" if is_ready else "unavailable",
        provider="google",
        model=service.model_name,
        tts_model=GeminiTTSSettings.from_environment().model_name,
        agent=request.app.state.director_workflow.root_agent.name,
        detail=None if is_ready else service.last_error,
    )
