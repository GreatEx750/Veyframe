from typing import Literal, cast

import pytest
from demodirector_api.director_agent import create_director_workflow
from demodirector_api.google_ai import (
    DEFAULT_REASONING_MODEL,
    AIConfigurationError,
    FakeGoogleAIService,
    GoogleAIService,
    GoogleAISettings,
    ModelsAPI,
    RuntimeState,
    StructuredGenerationError,
)
from google.adk.agents import Agent
from google.genai import types
from pydantic import BaseModel, ConfigDict


class ProbeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    provider: Literal["google"]


class StubResponse:
    def __init__(self, parsed: object = None, text: str | None = None) -> None:
        self.parsed = parsed
        self.text = text


class StubModels:
    def __init__(self, response: StubResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: object,
    ) -> StubResponse:
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self.response


class StubClient:
    def __init__(self, response: StubResponse) -> None:
        self.stub_models = StubModels(response)

    @property
    def models(self) -> ModelsAPI:
        return self.stub_models


def settings() -> GoogleAISettings:
    return GoogleAISettings(
        model_name="configured-gemini",
        api_key="test-key",
        project=None,
        location="us-central1",
    )


def test_settings_use_environment_model_and_select_auth_mode() -> None:
    configured = GoogleAISettings.from_environment(
        {
            "GEMINI_REASONING_MODEL": "gemini-test",
            "GEMINI_API_KEY": " key-value ",
            "GOOGLE_CLOUD_PROJECT": "ignored-when-key-present",
            "GOOGLE_CLOUD_LOCATION": "europe-west1",
        }
    )

    assert configured.model_name == "gemini-test"
    assert configured.location == "europe-west1"
    assert configured.auth_mode == "api_key"
    assert configured.is_configured


def test_settings_have_cost_conscious_model_default() -> None:
    configured = GoogleAISettings.from_environment({})

    assert configured.model_name == DEFAULT_REASONING_MODEL
    assert configured.auth_mode == "unconfigured"
    assert not configured.is_configured


def test_unconfigured_google_service_fails_with_actionable_error() -> None:
    with pytest.raises(AIConfigurationError, match="GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT"):
        GoogleAIService(GoogleAISettings.from_environment({}))


def test_google_service_generates_and_validates_structured_response() -> None:
    client = StubClient(StubResponse(parsed={"ok": True, "provider": "google"}))
    service = GoogleAIService(settings(), client=client)

    result = service.generate_structured(
        prompt="Return a tiny runtime probe.",
        response_model=ProbeResponse,
    )

    assert result == ProbeResponse(ok=True, provider="google")
    assert service.state is RuntimeState.READY
    assert service.last_error is None
    assert client.stub_models.calls[0]["model"] == "configured-gemini"
    config = cast(types.GenerateContentConfig, client.stub_models.calls[0]["config"])
    assert config.max_output_tokens == 8_192


def test_invalid_google_output_fails_closed_and_records_error_state() -> None:
    service = GoogleAIService(
        settings(),
        client=StubClient(StubResponse(parsed={"ok": "not-a-boolean", "provider": "other"})),
    )

    with pytest.raises(StructuredGenerationError, match="ProbeResponse validation"):
        service.generate_structured(prompt="Probe.", response_model=ProbeResponse)

    assert service.state is RuntimeState.ERROR
    assert service.last_error is not None


def test_fake_adapter_is_deterministic_and_uses_the_same_validation_boundary() -> None:
    service = FakeGoogleAIService({"ok": True, "provider": "google"})

    first = service.generate_structured(prompt="First probe.", response_model=ProbeResponse)
    second = service.generate_structured(prompt="Second probe.", response_model=ProbeResponse)

    assert first == second
    assert service.prompts == ["First probe.", "Second probe."]
    assert service.state is RuntimeState.READY


def test_director_workflow_uses_the_configured_model() -> None:
    workflow = create_director_workflow("configured-gemini")
    agent = workflow.root_agent

    assert workflow.name == "demodirector"
    assert isinstance(agent, Agent)
    assert agent.name == "demodirector_director"
    assert "configured-gemini" in str(agent.model)
