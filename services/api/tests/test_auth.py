from pathlib import Path
from typing import Any, cast

from demodirector_api.auth import (
    AuthService,
    AuthSettings,
    FakeIdentityProvider,
    SQLiteAuthRepository,
)
from demodirector_api.main import create_app
from demodirector_api.repositories import SQLiteProjectRepository
from fastapi.testclient import TestClient


def project_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "website_url": "https://example.com/product",
        "product_summary": "A product for focused teams",
        "audience": "Product leaders",
        "tone": "Professional",
        "requested_duration_seconds": 60,
        "cta": "Start a trial",
    }


def auth_client(
    database_path: Path,
    *,
    verified: bool = True,
    require_verified: bool = False,
    judge_enabled: bool = True,
    judge_ttl_seconds: int = 3_600,
) -> tuple[TestClient, FakeIdentityProvider]:
    provider = FakeIdentityProvider(verified=verified)
    auth = AuthService(
        provider,
        SQLiteAuthRepository(database_path),
        AuthSettings(
            required=True,
            require_verified_email=require_verified,
            judge_demo_enabled=judge_enabled,
            judge_session_ttl_seconds=judge_ttl_seconds,
        ),
    )
    return TestClient(
        create_app(SQLiteProjectRepository(database_path), auth_service=auth)
    ), provider


def signup(client: TestClient, email: str) -> dict[str, Any]:
    response = client.post(
        "/auth/signup",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def bearer(result: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {result['session_token']}"}


def test_signup_creates_private_session_and_owned_project(tmp_path: Path) -> None:
    database = tmp_path / "auth.db"
    client, _ = auth_client(database)

    signed_up = signup(client, "owner@example.com")
    response = client.post(
        "/projects",
        json=project_payload("Private launch"),
        headers=bearer(signed_up),
    )

    assert signed_up["status"] == "signed_in"
    assert response.status_code == 201
    assert response.json()["owner_user_id"] == signed_up["session"]["user"]["user_id"]
    assert client.get("/auth/session", headers=bearer(signed_up)).status_code == 200
    assert client.get("/projects").status_code == 401
    assert b"correct-horse-battery-staple" not in database.read_bytes()


def test_project_ownership_is_enforced_without_revealing_foreign_ids(tmp_path: Path) -> None:
    client, _ = auth_client(tmp_path / "ownership.db")
    first = signup(client, "first@example.com")
    second = signup(client, "second@example.com")
    created = client.post(
        "/projects",
        json=project_payload("First project"),
        headers=bearer(first),
    ).json()

    assert client.get("/projects", headers=bearer(first)).json() == [created]
    assert client.get("/projects", headers=bearer(second)).json() == []
    assert client.get(f"/projects/{created['id']}", headers=bearer(second)).status_code == 404
    assert (
        client.patch(
            f"/projects/{created['id']}",
            json={"cta": "Steal it"},
            headers=bearer(second),
        ).status_code
        == 404
    )


def test_hosted_verification_policy_does_not_issue_session(tmp_path: Path) -> None:
    client, provider = auth_client(
        tmp_path / "verification.db",
        verified=False,
        require_verified=True,
    )

    result = signup(client, "verify@example.com")

    assert result["status"] == "verification_required"
    assert result["session"] is None
    assert result["session_token"] is None
    assert provider.verification_requests == ["verify@example.com"]


def test_signup_errors_do_not_enumerate_existing_accounts(tmp_path: Path) -> None:
    client, _ = auth_client(tmp_path / "duplicates.db")
    signup(client, "same@example.com")

    response = client.post(
        "/auth/signup",
        json={"email": "same@example.com", "password": "another-secure-password"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["message"] == (
        "An account could not be created with those details."
    )


def test_returning_user_login_rotates_session_and_restores_owned_projects(
    tmp_path: Path,
) -> None:
    client, _ = auth_client(tmp_path / "login.db")
    signed_up = signup(client, "returning@example.com")
    created = client.post(
        "/projects",
        json=project_payload("Remember me"),
        headers=bearer(signed_up),
    ).json()

    response = client.post(
        "/auth/login",
        json={
            "email": "returning@example.com",
            "password": "correct-horse-battery-staple",
            "return_to": f"/projects/{created['id']}/editor",
        },
    )

    assert response.status_code == 200
    logged_in = response.json()
    assert logged_in["session_token"] != signed_up["session_token"]
    assert logged_in["session"]["session_id"] != signed_up["session"]["session_id"]
    assert logged_in["landing_path"] == "/projects"
    assert client.get("/auth/session", headers=bearer(logged_in)).json()["status"] == "active"
    assert client.get("/projects", headers=bearer(logged_in)).json() == [created]


def test_login_has_generic_errors_verification_gate_and_safe_return_paths(
    tmp_path: Path,
) -> None:
    client, _ = auth_client(
        tmp_path / "login-errors.db",
        verified=False,
        require_verified=True,
    )
    signup(client, "pending@example.com")

    invalid = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "wrong", "return_to": "/projects"},
    )
    pending = client.post(
        "/auth/login",
        json={
            "email": "pending@example.com",
            "password": "correct-horse-battery-staple",
            "return_to": "/projects",
        },
    )
    external = client.post(
        "/auth/login",
        json={
            "email": "pending@example.com",
            "password": "correct-horse-battery-staple",
            "return_to": "https://evil.example",
        },
    )

    assert invalid.status_code == 401
    assert invalid.json()["detail"]["message"] == "Email or password is incorrect."
    assert pending.status_code == 403
    assert pending.json()["detail"]["code"] == "verification_required"
    assert external.status_code == 422


def test_login_rate_limit_is_bounded(tmp_path: Path) -> None:
    client, _ = auth_client(tmp_path / "rate-limit.db")

    responses = [
        client.post(
            "/auth/login",
            json={"email": "missing@example.com", "password": "wrong", "return_to": "/projects"},
        )
        for _ in range(6)
    ]

    assert [response.status_code for response in responses[:5]] == [401] * 5
    assert responses[5].status_code == 429


def test_logout_revokes_session_and_is_idempotent(tmp_path: Path) -> None:
    client, _ = auth_client(tmp_path / "logout.db")
    signed_up = signup(client, "logout@example.com")
    headers = bearer(signed_up)
    assert client.get("/auth/session", headers=headers).json()["status"] == "active"

    first = client.post("/auth/logout", headers=headers)
    after = client.get("/auth/session", headers=headers)
    second = client.post("/auth/logout", headers=headers)
    absent = client.post("/auth/logout")

    assert first.json()["status"] == "logged_out"
    assert first.json()["reason"] == "user_requested"
    assert after.json() == {"status": "revoked", "session": None}
    assert second.json()["status"] == "already_absent"
    assert second.json()["reason"] == "revoked"
    assert absent.json()["reason"] == "absent"


def test_revoked_session_cannot_access_private_or_sensitive_routes(tmp_path: Path) -> None:
    client, _ = auth_client(tmp_path / "revoked.db")
    signed_up = signup(client, "revoke@example.com")
    headers = bearer(signed_up)
    project = client.post(
        "/projects",
        headers=headers,
        json=project_payload("Revoked project"),
    ).json()
    client.post("/auth/logout", headers=headers)

    assert client.get("/projects", headers=headers).status_code == 401
    assert client.get(f"/projects/{project['id']}", headers=headers).status_code == 401
    assert (
        client.get(
            f"/projects/{project['id']}/exports/export-id/download?token={'x' * 24}",
            headers=headers,
        ).status_code
        == 401
    )


def test_judge_sessions_share_one_persistent_workspace_and_allow_owned_project_writes(
    tmp_path: Path,
) -> None:
    client, _ = auth_client(tmp_path / "judge.db")

    first = client.post("/auth/judge-session")
    second = client.post("/auth/judge-session")

    assert first.status_code == 200
    assert second.status_code == 200
    first_session = first.json()
    second_session = second.json()
    assert first_session["session"]["user"]["role"] == "judge_demo"
    assert first_session["landing_path"] == "/projects"
    assert first_session["sandbox"]["project_id"] == second_session["sandbox"]["project_id"]
    assert (
        first_session["session"]["user"]["user_id"]
        == second_session["session"]["user"]["user_id"]
        == "judge-demo"
    )
    assert first_session["session_token"] != second_session["session_token"]
    first_headers = bearer(first_session)
    second_headers = bearer(second_session)
    first_projects = client.get("/projects", headers=first_headers).json()
    second_projects = client.get("/projects", headers=second_headers).json()
    assert [project["id"] for project in first_projects] == [
        first_session["sandbox"]["project_id"]
    ]
    assert second_projects == first_projects
    created = client.post(
        "/projects",
        headers=first_headers,
        json=project_payload("Judge-created project"),
    )
    assert created.status_code == 201
    assert created.json()["owner_user_id"] == first_session["session"]["user"]["user_id"]
    updated = client.patch(
        f"/projects/{created.json()['id']}",
        headers=first_headers,
        json={"cta": "Explore the result"},
    )
    assert updated.status_code == 200
    assert updated.json()["cta"] == "Explore the result"
    shared = client.patch(
        f"/projects/{created.json()['id']}",
        headers=second_headers,
        json={"cta": "Visible in the shared judge workspace"},
    )
    assert shared.status_code == 200
    deleted = client.delete(
        f"/projects/{first_session['sandbox']['project_id']}",
        headers=first_headers,
    )
    assert deleted.status_code == 204
    assert [project["id"] for project in client.get("/projects", headers=first_headers).json()] == [
        created.json()["id"]
    ]


def test_judge_status_and_reset_use_pre_generated_fixture(tmp_path: Path) -> None:
    client, _ = auth_client(tmp_path / "judge-reset.db")
    session = client.post("/auth/judge-session").json()
    headers = bearer(session)

    status_response = client.get("/judge/status", headers=headers)
    reset_response = client.post("/judge/reset", headers=headers)

    assert status_response.json() == {
        "enabled": True,
        "ready": True,
        "fixture_version": "northstar-20s-v1",
        "message": "Judge sandbox is ready.",
    }
    assert reset_response.status_code == 200
    assert reset_response.json()["name"] == "Northstar AI — Judge Demo"
    assert reset_response.json()["requested_duration_seconds"] == 20
    assert reset_response.json()["status"] == "published"


def test_judge_demo_has_global_disable_switch(tmp_path: Path) -> None:
    client, _ = auth_client(tmp_path / "judge-disabled.db", judge_enabled=False)

    response = client.post("/auth/judge-session")

    assert response.status_code == 503
    assert response.json()["detail"]["message"] == "Judge demo is not available."
