from pathlib import Path

from demodirector_api.main import create_app
from demodirector_api.repositories import SQLiteProjectRepository
from fastapi.testclient import TestClient


def project_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Launch demo",
        "website_url": "https://example.com/product",
        "product_summary": "A product for focused teams",
        "audience": "Product leaders",
        "tone": "Professional",
        "requested_duration_seconds": 90,
        "cta": "Start a trial",
        "brand_kit_id": "default-brand",
    }
    payload.update(overrides)
    return payload


def client_for(database_path: Path) -> TestClient:
    repository = SQLiteProjectRepository(database_path)
    return TestClient(create_app(repository))


def test_create_read_and_patch_project(tmp_path: Path) -> None:
    client = client_for(tmp_path / "projects.db")

    create_response = client.post("/projects", json=project_payload())

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["id"]
    assert created["status"] == "draft"
    assert created["job_status"] == "idle"

    get_response = client.get(f"/projects/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == created

    patch_response = client.patch(
        f"/projects/{created['id']}",
        json={"audience": "Sales engineers", "cta": "Book a demo"},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["audience"] == "Sales engineers"
    assert patched["cta"] == "Book a demo"
    assert patched["product_summary"] == created["product_summary"]
    assert patched["updated_at"] >= created["updated_at"]


def test_create_rejects_invalid_url(tmp_path: Path) -> None:
    response = client_for(tmp_path / "projects.db").post(
        "/projects",
        json=project_payload(website_url="not-a-public-url"),
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "website_url"


def test_patch_rejects_empty_body(tmp_path: Path) -> None:
    client = client_for(tmp_path / "projects.db")
    created = client.post("/projects", json=project_payload()).json()

    response = client.patch(f"/projects/{created['id']}", json={})

    assert response.status_code == 422


def test_missing_project_returns_not_found(tmp_path: Path) -> None:
    client = client_for(tmp_path / "projects.db")

    assert client.get("/projects/missing").status_code == 404
    assert client.patch("/projects/missing", json={"cta": "Try it"}).status_code == 404
    assert client.delete("/projects/missing").status_code == 404


def test_delete_project_removes_it_from_the_library(tmp_path: Path) -> None:
    client = client_for(tmp_path / "projects.db")
    kept = client.post("/projects", json=project_payload(name="Keep me")).json()
    deleted = client.post("/projects", json=project_payload(name="Delete me")).json()

    response = client.delete(f"/projects/{deleted['id']}")

    assert response.status_code == 204
    assert client.get(f"/projects/{deleted['id']}").status_code == 404
    assert [item["id"] for item in client.get("/projects").json()] == [kept["id"]]


def test_list_projects_returns_library_items(tmp_path: Path) -> None:
    client = client_for(tmp_path / "projects.db")
    first = client.post("/projects", json=project_payload(name="First demo")).json()
    second = client.post("/projects", json=project_payload(name="Second demo")).json()

    response = client.get("/projects")

    assert response.status_code == 200
    assert {project["id"] for project in response.json()} == {first["id"], second["id"]}
