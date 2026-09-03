import pytest
from demodirector_api.health import HealthResponse
from demodirector_api.main import app
from fastapi.testclient import TestClient
from pydantic import ValidationError


def test_health_response_rejects_an_unknown_status() -> None:
    with pytest.raises(ValidationError):
        HealthResponse(status="degraded", service="api")  # type: ignore[arg-type]


def test_health_endpoint_reports_api_ready() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}
