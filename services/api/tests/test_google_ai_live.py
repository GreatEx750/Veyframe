import os
from typing import Literal

import pytest
from demodirector_api.google_ai import GoogleAIService, GoogleAISettings
from pydantic import BaseModel, ConfigDict

pytestmark = pytest.mark.live


class LiveProbeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]
    provider: Literal["google"]


def test_live_gemini_structured_response() -> None:
    if os.getenv("GEMINI_LIVE_SMOKE_TEST") != "1":
        pytest.skip("Set GEMINI_LIVE_SMOKE_TEST=1 to run the paid Gemini smoke test.")
    settings = GoogleAISettings.from_environment()
    if not settings.is_configured:
        pytest.skip("Gemini credentials are not configured.")

    response = GoogleAIService(settings).generate_structured(
        prompt="Return ok=true and provider=google for a minimal runtime health probe.",
        response_model=LiveProbeResponse,
    )

    assert response == LiveProbeResponse(ok=True, provider="google")
