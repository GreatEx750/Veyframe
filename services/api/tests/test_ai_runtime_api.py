from pathlib import Path

from demodirector_api.google_ai import FakeGoogleAIService, GoogleAISettings
from demodirector_api.main import create_app
from demodirector_api.repositories import SQLiteProjectRepository
from fastapi.testclient import TestClient


def test_ai_health_reports_injected_google_runtime_without_calling_a_model(
    tmp_path: Path,
) -> None:
    service = FakeGoogleAIService({"unused": True}, model_name="gemini-test")
    settings = GoogleAISettings(
        model_name="gemini-test",
        api_key="test-key",
        project=None,
        location="us-central1",
    )
    app = create_app(
        repository=SQLiteProjectRepository(tmp_path / "projects.db"),
        ai_service=service,
        ai_settings=settings,
    )

    response = TestClient(app).get("/ai/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "provider": "google",
        "model": "gemini-test",
        "tts_model": "gemini-3.1-flash-tts-preview",
        "agent": "demodirector_director",
        "detail": None,
    }
    assert service.prompts == []


def test_ai_health_reports_missing_configuration_without_exposing_secrets(
    tmp_path: Path,
) -> None:
    app = create_app(
        repository=SQLiteProjectRepository(tmp_path / "projects.db"),
        ai_settings=GoogleAISettings.from_environment({}),
    )

    response = TestClient(app).get("/ai/health")

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["provider"] == "google"
    assert "GEMINI_API_KEY" in response.json()["detail"]
