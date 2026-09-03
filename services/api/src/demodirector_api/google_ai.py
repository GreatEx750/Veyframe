from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeVar, cast

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

load_dotenv()

DEFAULT_REASONING_MODEL = "gemini-3.5-flash-lite"
MAX_STRUCTURED_OUTPUT_TOKENS = 8_192

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class RuntimeState(StrEnum):
    READY = "ready"
    GENERATING = "generating"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class AIConfigurationError(RuntimeError):
    """Raised when the approved Google runtime is not configured."""


class StructuredGenerationError(RuntimeError):
    """Raised when a model response cannot be validated against its contract."""


@dataclass(frozen=True, slots=True)
class GoogleAISettings:
    model_name: str
    api_key: str | None
    project: str | None
    location: str

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> GoogleAISettings:
        values = os.environ if environment is None else environment
        return cls(
            model_name=_value(values, "GEMINI_REASONING_MODEL") or DEFAULT_REASONING_MODEL,
            api_key=_value(values, "GEMINI_API_KEY"),
            project=_value(values, "GOOGLE_CLOUD_PROJECT"),
            location=_value(values, "GOOGLE_CLOUD_LOCATION") or "us-central1",
        )

    @property
    def is_configured(self) -> bool:
        return self.api_key is not None or self.project is not None

    @property
    def auth_mode(self) -> str:
        if self.api_key is not None:
            return "api_key"
        if self.project is not None:
            return "vertex_ai"
        return "unconfigured"


def _value(environment: Mapping[str, str], name: str) -> str | None:
    value = environment.get(name, "").strip()
    return value or None


class GenerationResponse(Protocol):
    parsed: object
    text: str | None


class ModelsAPI(Protocol):
    def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: object,
    ) -> GenerationResponse: ...


class GenAIClient(Protocol):
    @property
    def models(self) -> ModelsAPI: ...


class StructuredAIService(Protocol):
    provider: str
    model_name: str
    state: RuntimeState
    last_error: str | None

    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel: ...


class GoogleAIService:
    provider = "google"

    def __init__(
        self,
        settings: GoogleAISettings,
        client: GenAIClient | None = None,
    ) -> None:
        if not settings.is_configured and client is None:
            raise AIConfigurationError(
                "Configure GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT before using Gemini."
            )
        self.model_name = settings.model_name
        self.state = RuntimeState.READY
        self.last_error: str | None = None
        self._client = client or self._create_client(settings)

    @staticmethod
    def _create_client(settings: GoogleAISettings) -> GenAIClient:
        if settings.api_key is not None:
            return cast(GenAIClient, genai.Client(api_key=settings.api_key))
        return cast(
            GenAIClient,
            genai.Client(
                vertexai=True,
                project=settings.project,
                location=settings.location,
            ),
        )

    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        self.state = RuntimeState.GENERATING
        self.last_error = None
        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=response_model.model_json_schema(),
                    max_output_tokens=MAX_STRUCTURED_OUTPUT_TOKENS,
                ),
            )
            result = validate_structured_response(response, response_model)
        except Exception as error:
            self.state = RuntimeState.ERROR
            if isinstance(error, StructuredGenerationError):
                self.last_error = str(error)
                raise
            self.last_error = "Google generation failed before a valid response was returned."
            raise StructuredGenerationError(self.last_error) from error

        self.state = RuntimeState.READY
        return result


class FakeGoogleAIService:
    provider = "google"

    def __init__(
        self,
        payload: object,
        model_name: str = "fake-gemini",
    ) -> None:
        self.model_name = model_name
        self.state = RuntimeState.READY
        self.last_error: str | None = None
        self.payload = payload
        self.prompts: list[str] = []

    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        self.state = RuntimeState.GENERATING
        self.prompts.append(prompt)
        try:
            result = response_model.model_validate(self.payload)
        except ValidationError as error:
            self.state = RuntimeState.ERROR
            self.last_error = _validation_message(response_model, error)
            raise StructuredGenerationError(self.last_error) from error
        self.state = RuntimeState.READY
        self.last_error = None
        return result


class UnavailableGoogleAIService:
    provider = "google"
    state = RuntimeState.UNAVAILABLE

    def __init__(self, model_name: str, detail: str) -> None:
        self.model_name = model_name
        self.last_error: str | None = detail

    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        del prompt, response_model
        raise AIConfigurationError(self.last_error or "The Google AI runtime is unavailable.")


def validate_structured_response[ResponseModel: BaseModel](
    response: GenerationResponse,
    response_model: type[ResponseModel],
) -> ResponseModel:
    candidate = response.parsed
    try:
        if candidate is not None:
            return response_model.model_validate(candidate)
        if response.text:
            return response_model.model_validate_json(response.text)
    except (ValidationError, ValueError, TypeError) as error:
        raise StructuredGenerationError(_validation_message(response_model, error)) from error

    raise StructuredGenerationError(
        f"Gemini returned no structured content for {response_model.__name__}."
    )


def _validation_message(response_model: type[BaseModel], error: Exception) -> str:
    return f"Gemini output failed {response_model.__name__} validation: {error}"
