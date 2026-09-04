from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

import httpx
from demodirector_contracts import (
    JudgeSandbox,
    JudgeSession,
    LoginRequest,
    LoginResult,
    SessionState,
    SessionSummary,
    SignupRequest,
    SignupResult,
    UserIdentity,
    UserProfile,
)

AuthErrorCode = Literal[
    "authentication_required",
    "invalid_credentials",
    "verification_required",
    "account_unavailable",
    "session_expired",
    "session_revoked",
    "rate_limited",
]


class AuthenticationError(RuntimeError):
    def __init__(self, code: AuthErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    user_id: str
    email: str
    email_verified: bool
    id_token: str | None = None


class IdentityProvider(Protocol):
    def signup(self, email: str, password: str) -> ProviderIdentity: ...

    def send_verification(self, identity: ProviderIdentity) -> None: ...

    def login(self, email: str, password: str) -> ProviderIdentity: ...


class UnavailableIdentityProvider:
    def signup(self, email: str, password: str) -> ProviderIdentity:
        del email, password
        raise AuthenticationError(
            "account_unavailable",
            "Account service is temporarily unavailable.",
        )

    def send_verification(self, identity: ProviderIdentity) -> None:
        del identity

    def login(self, email: str, password: str) -> ProviderIdentity:
        del email, password
        raise AuthenticationError(
            "account_unavailable",
            "Account service is temporarily unavailable.",
        )


class GoogleIdentityPlatformProvider:
    """Small official Identity Toolkit REST boundary used for managed credentials."""

    def __init__(self, api_key: str, timeout_seconds: float = 10) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://identitytoolkit.googleapis.com/v1"

    def signup(self, email: str, password: str) -> ProviderIdentity:
        try:
            response = httpx.post(
                f"{self.base_url}/accounts:signUp",
                params={"key": self.api_key},
                json={"email": email, "password": password, "returnSecureToken": True},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise AuthenticationError(
                "account_unavailable",
                "Account service is temporarily unavailable.",
            ) from error
        if response.status_code >= 400:
            raise AuthenticationError(
                "account_unavailable",
                "An account could not be created with those details.",
            )
        payload = response.json()
        user_id = payload.get("localId")
        id_token = payload.get("idToken")
        returned_email = payload.get("email")
        if not isinstance(user_id, str) or not isinstance(id_token, str) or not isinstance(
            returned_email, str
        ):
            raise AuthenticationError(
                "account_unavailable",
                "Account service returned an invalid response.",
            )
        return ProviderIdentity(
            user_id=user_id,
            email=returned_email.strip().lower(),
            email_verified=False,
            id_token=id_token,
        )

    def send_verification(self, identity: ProviderIdentity) -> None:
        if identity.id_token is None:
            raise AuthenticationError(
                "account_unavailable",
                "Verification could not be started.",
            )
        try:
            response = httpx.post(
                f"{self.base_url}/accounts:sendOobCode",
                params={"key": self.api_key},
                json={"requestType": "VERIFY_EMAIL", "idToken": identity.id_token},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise AuthenticationError(
                "account_unavailable",
                "Verification could not be started.",
            ) from error
        if response.status_code >= 400:
            raise AuthenticationError(
                "account_unavailable",
                "Verification could not be started.",
            )

    def login(self, email: str, password: str) -> ProviderIdentity:
        try:
            response = httpx.post(
                f"{self.base_url}/accounts:signInWithPassword",
                params={"key": self.api_key},
                json={"email": email, "password": password, "returnSecureToken": True},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise AuthenticationError(
                "account_unavailable",
                "Account service is temporarily unavailable.",
            ) from error
        if response.status_code >= 400:
            raise AuthenticationError("invalid_credentials", "Email or password is incorrect.")
        payload = response.json()
        user_id = payload.get("localId")
        id_token = payload.get("idToken")
        returned_email = payload.get("email")
        if not isinstance(user_id, str) or not isinstance(id_token, str) or not isinstance(
            returned_email, str
        ):
            raise AuthenticationError(
                "account_unavailable",
                "Account service returned an invalid response.",
            )
        verified = self._email_is_verified(id_token)
        return ProviderIdentity(
            user_id=user_id,
            email=returned_email.strip().lower(),
            email_verified=verified,
            id_token=id_token,
        )

    def _email_is_verified(self, id_token: str) -> bool:
        try:
            response = httpx.post(
                f"{self.base_url}/accounts:lookup",
                params={"key": self.api_key},
                json={"idToken": id_token},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise AuthenticationError(
                "account_unavailable",
                "Account service is temporarily unavailable.",
            ) from error
        if response.status_code >= 400:
            raise AuthenticationError("invalid_credentials", "Email or password is incorrect.")
        users = response.json().get("users", [])
        return bool(users and users[0].get("emailVerified") is True)


class FakeIdentityProvider:
    """Provider-free deterministic adapter for tests."""

    def __init__(self, *, verified: bool = True) -> None:
        self.verified = verified
        self.users: dict[str, tuple[ProviderIdentity, str]] = {}
        self.verification_requests: list[str] = []

    def signup(self, email: str, password: str) -> ProviderIdentity:
        normalized = email.strip().lower()
        if normalized in self.users:
            raise AuthenticationError(
                "account_unavailable",
                "An account could not be created with those details.",
            )
        identity = ProviderIdentity(
            user_id=f"user-{len(self.users) + 1}",
            email=normalized,
            email_verified=self.verified,
            id_token="fake-provider-token",
        )
        self.users[normalized] = (identity, _fake_password_hash(password))
        return identity

    def send_verification(self, identity: ProviderIdentity) -> None:
        self.verification_requests.append(identity.email)

    def login(self, email: str, password: str) -> ProviderIdentity:
        stored = self.users.get(email.strip().lower())
        if stored is None or not secrets.compare_digest(
            stored[1], _fake_password_hash(password)
        ):
            raise AuthenticationError("invalid_credentials", "Email or password is incorrect.")
        return stored[0]


@dataclass(frozen=True, slots=True)
class StoredSession:
    summary: SessionSummary
    token_hash: str
    revoked_at: datetime | None = None


class AuthRepository(Protocol):
    def save_profile(self, profile: UserProfile) -> UserProfile: ...

    def save_session(self, session: StoredSession) -> StoredSession: ...

    def get_session(self, token_hash: str) -> StoredSession | None: ...

    def revoke_session(self, session_id: str, revoked_at: datetime) -> bool: ...

    def expired_judge_user_ids(self, now: datetime) -> list[str]: ...


class SQLiteAuthRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    session_id TEXT PRIMARY KEY,
                    token_hash TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL,
                    revoked_at TEXT
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def save_profile(self, profile: UserProfile) -> UserProfile:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO user_profiles (user_id, payload) VALUES (?, ?)",
                (profile.user_id, profile.model_dump_json()),
            )
        return profile

    def save_session(self, session: StoredSession) -> StoredSession:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_sessions (session_id, token_hash, payload, revoked_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session.summary.session_id,
                    session.token_hash,
                    session.summary.model_dump_json(),
                    None if session.revoked_at is None else session.revoked_at.isoformat(),
                ),
            )
        return session

    def get_session(self, token_hash: str) -> StoredSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload, token_hash, revoked_at FROM auth_sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return StoredSession(
            summary=SessionSummary.model_validate_json(row[0]),
            token_hash=str(row[1]),
            revoked_at=None if row[2] is None else datetime.fromisoformat(str(row[2])),
        )

    def revoke_session(self, session_id: str, revoked_at: datetime) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_sessions SET revoked_at = ?
                WHERE session_id = ? AND revoked_at IS NULL
                """,
                (revoked_at.isoformat(), session_id),
            )
        return cursor.rowcount == 1

    def expired_judge_user_ids(self, now: datetime) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM auth_sessions").fetchall()
        expired: list[str] = []
        for row in rows:
            summary = SessionSummary.model_validate_json(row[0])
            if summary.user.role == "judge_demo" and summary.expires_at <= now:
                expired.append(summary.user.user_id)
        return sorted(set(expired))


class FirestoreAuthRepository:
    def __init__(self, client: Any) -> None:
        self.profiles = client.collection("user_profiles")
        self.sessions = client.collection("auth_sessions")

    def save_profile(self, profile: UserProfile) -> UserProfile:
        self.profiles.document(profile.user_id).set(profile.model_dump(mode="json"))
        return profile

    def save_session(self, session: StoredSession) -> StoredSession:
        self.sessions.document(session.summary.session_id).set(
            {
                "summary": session.summary.model_dump(mode="json"),
                "token_hash": session.token_hash,
                "revoked_at": session.revoked_at,
            }
        )
        return session

    def get_session(self, token_hash: str) -> StoredSession | None:
        for snapshot in self.sessions.stream():
            payload = snapshot.to_dict() or {}
            if payload.get("token_hash") != token_hash:
                continue
            revoked_at = payload.get("revoked_at")
            return StoredSession(
                summary=SessionSummary.model_validate(payload["summary"]),
                token_hash=token_hash,
                revoked_at=revoked_at,
            )
        return None

    def revoke_session(self, session_id: str, revoked_at: datetime) -> bool:
        reference = self.sessions.document(session_id)
        snapshot = reference.get()
        if not snapshot.exists:
            return False
        payload = snapshot.to_dict() or {}
        if payload.get("revoked_at") is not None:
            return False
        reference.update({"revoked_at": revoked_at})
        return True

    def expired_judge_user_ids(self, now: datetime) -> list[str]:
        expired: list[str] = []
        for snapshot in self.sessions.stream():
            payload = snapshot.to_dict() or {}
            summary = SessionSummary.model_validate(payload.get("summary"))
            if summary.user.role == "judge_demo" and summary.expires_at <= now:
                expired.append(summary.user.user_id)
        return sorted(set(expired))


@dataclass(frozen=True, slots=True)
class AuthSettings:
    required: bool = False
    require_verified_email: bool = False
    session_ttl_seconds: int = 43_200
    identity_platform_api_key: str | None = None
    judge_demo_enabled: bool = True
    judge_session_ttl_seconds: int = 3_600

    @classmethod
    def from_environment(cls) -> AuthSettings:
        return cls(
            required=os.getenv("DEMO_AUTH_REQUIRED", "false").lower() == "true",
            require_verified_email=os.getenv(
                "DEMO_AUTH_REQUIRE_VERIFIED_EMAIL", "false"
            ).lower()
            == "true",
            session_ttl_seconds=int(os.getenv("DEMO_SESSION_TTL_SECONDS", "43200")),
            identity_platform_api_key=os.getenv("IDENTITY_PLATFORM_API_KEY"),
            judge_demo_enabled=os.getenv("DEMO_JUDGE_ENABLED", "true").lower() == "true",
            judge_session_ttl_seconds=int(os.getenv("DEMO_JUDGE_SESSION_TTL_SECONDS", "3600")),
        )


class AuthService:
    def __init__(
        self,
        provider: IdentityProvider,
        repository: AuthRepository,
        settings: AuthSettings,
    ) -> None:
        self.provider = provider
        self.repository = repository
        self.settings = settings
        self._login_attempts: dict[str, list[float]] = {}
        self._judge_attempts: list[float] = []

    def signup(self, request: SignupRequest) -> SignupResult:
        identity = self.provider.signup(request.email.strip().lower(), request.password)
        now = datetime.now(UTC)
        self.repository.save_profile(
            UserProfile(
                user_id=identity.user_id,
                email=identity.email,
                role="customer",
                created_at=now,
                updated_at=now,
            )
        )
        if self.settings.require_verified_email and not identity.email_verified:
            self.provider.send_verification(identity)
            return SignupResult(
                status="verification_required",
                message="Check your email to verify the account before signing in.",
            )
        token, summary = self.issue_session(
            UserIdentity(
                user_id=identity.user_id,
                email=identity.email,
                role="customer",
                email_verified=identity.email_verified,
            )
        )
        return SignupResult(
            status="signed_in",
            session=summary,
            session_token=token,
            message="Account created.",
        )

    def login(self, request: LoginRequest) -> LoginResult:
        key = hashlib.sha256(request.email.strip().lower().encode("utf-8")).hexdigest()
        now = time.monotonic()
        attempts = [attempt for attempt in self._login_attempts.get(key, []) if now - attempt < 60]
        if len(attempts) >= 5:
            raise AuthenticationError("rate_limited", "Try again in a moment.")
        attempts.append(now)
        self._login_attempts[key] = attempts
        identity = self.provider.login(request.email.strip().lower(), request.password)
        if self.settings.require_verified_email and not identity.email_verified:
            raise AuthenticationError(
                "verification_required",
                "Verify your email before signing in.",
            )
        self._login_attempts.pop(key, None)
        token, summary = self.issue_session(
            UserIdentity(
                user_id=identity.user_id,
                email=identity.email,
                role="customer",
                email_verified=identity.email_verified,
            )
        )
        return LoginResult(
            session=summary,
            session_token=token,
            landing_path="/projects",
        )

    def session_state(self, token: str | None) -> SessionState:
        if token is None:
            return SessionState(status="absent")
        try:
            return SessionState(status="active", session=self.authenticate(token))
        except AuthenticationError as error:
            if error.code == "session_expired":
                return SessionState(status="expired")
            if error.code == "session_revoked":
                return SessionState(status="revoked")
            return SessionState(status="absent")

    def issue_judge_session(self) -> JudgeSession:
        if not self.settings.judge_demo_enabled:
            raise AuthenticationError("account_unavailable", "Judge demo is not available.")
        now_monotonic = time.monotonic()
        self._judge_attempts = [
            attempt for attempt in self._judge_attempts if now_monotonic - attempt < 60
        ]
        if len(self._judge_attempts) >= 10:
            raise AuthenticationError("rate_limited", "Try the judge demo again in a moment.")
        self._judge_attempts.append(now_monotonic)
        user_id = f"judge-{uuid4()}"
        token, summary = self.issue_session(
            UserIdentity(
                user_id=user_id,
                email="judge-session@demodirector.local",
                role="judge_demo",
                email_verified=True,
            ),
            ttl_seconds=self.settings.judge_session_ttl_seconds,
        )
        project_id = f"judge-demo-{summary.session_id}"
        return JudgeSession(
            session=summary,
            session_token=token,
            sandbox=JudgeSandbox(
                sandbox_id=summary.session_id,
                project_id=project_id,
                owner_user_id=user_id,
                fixture_version="northstar-20s-v1",
                created_at=summary.created_at,
                expires_at=summary.expires_at,
            ),
            capabilities=[
                "view_project",
                "explore_editor",
                "preview_fixture",
                "reset_sandbox",
                "create_project",
                "generate_demo",
                "edit_timeline",
                "export_video",
            ],
            landing_path="/projects",
        )

    def expired_judge_user_ids(self) -> list[str]:
        return self.repository.expired_judge_user_ids(datetime.now(UTC))

    def issue_session(
        self,
        identity: UserIdentity,
        *,
        ttl_seconds: int | None = None,
    ) -> tuple[str, SessionSummary]:
        now = datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        summary = SessionSummary(
            session_id=str(uuid4()),
            user=identity,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds or self.settings.session_ttl_seconds),
        )
        self.repository.save_session(StoredSession(summary, _token_hash(token)))
        return token, summary

    def authenticate(self, token: str) -> SessionSummary:
        stored = self.repository.get_session(_token_hash(token))
        if stored is None:
            raise AuthenticationError("authentication_required", "Authentication is required.")
        if stored.revoked_at is not None:
            raise AuthenticationError("session_revoked", "The session is no longer active.")
        if stored.summary.expires_at <= datetime.now(UTC):
            raise AuthenticationError("session_expired", "The session has expired.")
        return stored.summary

    def revoke(self, token: str) -> bool:
        stored = self.repository.get_session(_token_hash(token))
        if stored is None:
            return False
        return self.repository.revoke_session(stored.summary.session_id, datetime.now(UTC))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fake_password_hash(password: str) -> str:
    return hashlib.sha256(f"demodirector-test-only:{password}".encode()).hexdigest()
