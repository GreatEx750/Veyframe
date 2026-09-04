from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from demodirector_contracts import (
    JudgeDemoHealth,
    JudgeSession,
    LoginRequest,
    LoginResult,
    LogoutResult,
    Project,
    SessionState,
    SessionSummary,
    SignupRequest,
    SignupResult,
    UserIdentity,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from demodirector_api.auth import AuthenticationError, AuthService
from demodirector_api.repositories import ProjectRepository


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service  # type: ignore[no-any-return]


Auth = Annotated[AuthService, Depends(get_auth_service)]


def get_projects(request: Request) -> ProjectRepository:
    return request.app.state.project_repository  # type: ignore[no-any-return]


Projects = Annotated[ProjectRepository, Depends(get_projects)]


def bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def current_session(
    auth: Auth,
    authorization: Annotated[str | None, Header()] = None,
) -> SessionSummary:
    token = bearer_token(authorization)
    if token is None:
        if not auth.settings.required:
            return SessionSummary.model_validate(
                {
                    "session_id": "system-session",
                    "user": {
                        "user_id": "system",
                        "email": "system@demodirector.local",
                        "role": "system",
                        "email_verified": True,
                    },
                    "created_at": "2026-01-01T00:00:00Z",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required", "message": "Authentication is required."},
        )
    try:
        return auth.authenticate(token)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": error.code, "message": str(error)},
        ) from error


CurrentSession = Annotated[SessionSummary, Depends(current_session)]


def current_identity(session: CurrentSession) -> UserIdentity:
    return session.user


CurrentIdentity = Annotated[UserIdentity, Depends(current_identity)]

router = APIRouter(prefix="/auth", tags=["authentication"])
judge_router = APIRouter(prefix="/judge", tags=["judge-demo"])


@router.post("/signup", response_model=SignupResult, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, auth: Auth) -> SignupResult:
    try:
        return auth.signup(payload)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": error.code, "message": str(error)},
        ) from error


@router.post("/login", response_model=LoginResult)
def login(payload: LoginRequest, auth: Auth) -> LoginResult:
    try:
        return auth.login(payload)
    except AuthenticationError as error:
        error_status = {
            "invalid_credentials": status.HTTP_401_UNAUTHORIZED,
            "verification_required": status.HTTP_403_FORBIDDEN,
            "rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
        }.get(error.code, status.HTTP_503_SERVICE_UNAVAILABLE)
        raise HTTPException(
            status_code=error_status,
            detail={"code": error.code, "message": str(error)},
        ) from error


@router.get("/session", response_model=SessionState)
def session(
    auth: Auth,
    authorization: Annotated[str | None, Header()] = None,
) -> SessionState:
    return auth.session_state(bearer_token(authorization))


@router.post("/logout", response_model=LogoutResult)
def logout(
    auth: Auth,
    authorization: Annotated[str | None, Header()] = None,
) -> LogoutResult:
    token = bearer_token(authorization)
    if token is None:
        return LogoutResult(
            status="already_absent",
            reason="absent",
            message="You are logged out.",
        )
    state = auth.session_state(token)
    revoked = auth.revoke(token)
    if revoked:
        return LogoutResult(
            status="logged_out",
            reason="user_requested",
            message="You are logged out.",
        )
    reason: Literal["absent", "expired", "revoked"]
    if state.status == "expired":
        reason = "expired"
    elif state.status == "revoked":
        reason = "revoked"
    else:
        reason = "absent"
    return LogoutResult(
        status="already_absent",
        reason=reason,
        message="You are logged out.",
    )


def judge_fixture_project(session: JudgeSession) -> Project:
    return Project.model_validate(
        {
            "id": session.sandbox.project_id,
            "name": "Northstar AI — Judge Demo",
            "website_url": "https://example.com/northstar",
            "product_summary": (
                "A pre-generated product demo showing insights, goals, team collaboration, "
                "recommendations, narration, captions, camera direction, and export."
            ),
            "audience": "Hackathon judges",
            "tone": "Professional",
            "requested_duration_seconds": 20,
            "cta": "Explore the complete DemoDirector workflow",
            "brand_kit_id": "northstar-fixture",
            "status": "published",
            "job_status": "succeeded",
            "owner_user_id": session.session.user.user_id,
            "created_at": session.session.created_at,
            "updated_at": session.session.created_at,
        }
    )


@router.post("/judge-session", response_model=JudgeSession)
def create_judge_session(auth: Auth, projects: Projects) -> JudgeSession:
    try:
        session = auth.issue_judge_session()
        if projects.get(session.sandbox.project_id) is None:
            projects.create(judge_fixture_project(session))
        return session
    except AuthenticationError as error:
        error_status = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if error.code == "rate_limited"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        raise HTTPException(
            status_code=error_status,
            detail={"code": error.code, "message": str(error)},
        ) from error


@judge_router.get("/status", response_model=JudgeDemoHealth)
def judge_status(active: CurrentSession, auth: Auth, projects: Projects) -> JudgeDemoHealth:
    if active.user.role != "judge_demo":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Judge demo not found")
    ready = bool(projects.list(active.user.user_id))
    return JudgeDemoHealth(
        enabled=auth.settings.judge_demo_enabled,
        ready=ready,
        fixture_version="northstar-20s-v1",
        message="Judge sandbox is ready." if ready else "Judge sandbox is unavailable.",
    )


def _reset_session(active: SessionSummary, project_id: str) -> JudgeSession:
    return JudgeSession.model_validate(
        {
            "session": active,
            "session_token": "server-only-placeholder",
            "sandbox": {
                "sandbox_id": active.session_id,
                "project_id": project_id,
                "owner_user_id": active.user.user_id,
                "fixture_version": "northstar-20s-v1",
                "created_at": active.created_at,
                "expires_at": active.expires_at,
            },
            "capabilities": ["reset_sandbox"],
            "landing_path": "/projects",
        }
    )


@judge_router.post("/reset", response_model=Project)
def reset_judge_sandbox(active: CurrentSession, projects: Projects) -> Project:
    if active.user.role != "judge_demo":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Judge demo not found")
    project_id = "judge-demo-northstar"
    existing = projects.get(project_id)
    replacement = judge_fixture_project(_reset_session(active, project_id))
    if existing:
        replacement = Project.model_validate(
            {
                **replacement.model_dump(),
                "created_at": existing.created_at,
                "updated_at": datetime.now(UTC),
            }
        )
        projects.update(replacement)
    else:
        projects.create(replacement)
    return replacement
