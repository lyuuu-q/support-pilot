from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import SecretStr
from sqlalchemy.orm import Session

from support_pilot.auth.contracts import TokenResponse
from support_pilot.config import Settings, get_settings
from support_pilot.domain.enums import UserStatus
from support_pilot.domain.errors import AuthenticationError, DomainError
from support_pilot.infrastructure.models import AuditEvent, AuthSession, UserAccount
from support_pilot.infrastructure.repositories import SupportRepository

ALGORITHM = "HS256"
PASSWORD_HASH = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$MtzpBsirEtF1rPaNlWyDaA$"
    "RSQrj2WRF9eCu6/kcx2N74yMiu1W2v1xGUeRRPYj6b8"
)


class AuthenticationConfigurationError(DomainError):
    """Raised when JWT signing is not configured."""

    status_code = 503
    code = "authentication_unavailable"


def authenticate_user(session: Session, *, email: str, password: str) -> UserAccount:
    normalized_email = email.strip().casefold()
    user = SupportRepository(session).get_user_by_email(normalized_email)
    candidate_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    valid_password = PASSWORD_HASH.verify(password, candidate_hash)
    if user is None or not valid_password or user.status != UserStatus.ACTIVE.value:
        record_auth_event(
            session,
            actor_id=f"email_hash:{sha256(normalized_email.encode()).hexdigest()[:16]}",
            outcome="denied",
            reason_code="invalid_credentials",
        )
        raise AuthenticationError("invalid email or password")
    record_auth_event(
        session,
        actor_id=str(user.id),
        outcome="success",
        reason_code="password_verified",
        tenant_id=user.tenant_id,
    )
    return user


def issue_access_token(
    user: UserAccount,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    session_id: UUID | None = None,
) -> TokenResponse:
    resolved = settings or get_settings()
    secret = _require_secret(resolved.jwt_secret)
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=resolved.jwt_access_token_minutes)
    payload = {
        "sub": str(user.id),
        "tid": str(user.tenant_id) if user.tenant_id is not None else None,
        "role": user.role,
        "iss": resolved.jwt_issuer,
        "aud": resolved.jwt_audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
        "jti": uuid4().hex,
    }
    if session_id is not None:
        payload["sid"] = str(session_id)
    return TokenResponse(
        access_token=jwt.encode(payload, secret, algorithm=ALGORITHM),
        expires_in=resolved.jwt_access_token_minutes * 60,
    )


def decode_access_token(token: str, *, settings: Settings | None = None) -> dict[str, object]:
    resolved = settings or get_settings()
    secret = _require_secret(resolved.jwt_secret)
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            audience=resolved.jwt_audience,
            issuer=resolved.jwt_issuer,
            options={"require": ["sub", "role", "iss", "aud", "iat", "nbf", "exp", "jti"]},
        )
    except InvalidTokenError as error:
        raise AuthenticationError("invalid or expired access token") from error
    return dict(payload)


def authenticate_token(
    session: Session,
    token: str,
    *,
    settings: Settings | None = None,
    require_session: bool = False,
) -> UserAccount:
    user, _session = _resolve_token_identity(
        session, token, settings=settings, require_session=require_session
    )
    return user


def authenticate_cookie_token(
    session: Session,
    token: str,
    *,
    settings: Settings | None = None,
) -> tuple[UserAccount, AuthSession]:
    """Authenticate an access token that must be bound to an active browser session."""
    user, auth_session = _resolve_token_identity(
        session, token, settings=settings, require_session=True
    )
    if auth_session is None:  # pragma: no cover - require_session always resolves a row
        raise AuthenticationError("access token is not bound to a session")
    return user, auth_session


def _resolve_token_identity(
    session: Session,
    token: str,
    *,
    settings: Settings | None = None,
    require_session: bool = False,
) -> tuple[UserAccount, AuthSession | None]:
    payload = decode_access_token(token, settings=settings)
    try:
        user_id = UUID(str(payload["sub"]))
    except (KeyError, TypeError, ValueError):
        raise AuthenticationError("invalid or expired access token") from None
    auth_session = _require_active_session(session, payload) if require_session else None
    user = SupportRepository(session).get_user(user_id)
    expected_tenant = str(user.tenant_id) if user is not None and user.tenant_id else None
    if (
        user is None
        or user.status != UserStatus.ACTIVE.value
        or payload.get("role") != user.role
        or payload.get("tid") != expected_tenant
    ):
        raise AuthenticationError("token identity is no longer active")
    return user, auth_session


def _require_active_session(session: Session, payload: dict[str, object]) -> AuthSession:
    raw_session_id = payload.get("sid")
    if not isinstance(raw_session_id, str):
        raise AuthenticationError("access token is not bound to a session")
    try:
        session_id = UUID(raw_session_id)
    except ValueError:
        raise AuthenticationError("access token session id is invalid") from None
    auth_session = session.get(AuthSession, session_id)
    expires_at = auth_session.expires_at if auth_session is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        auth_session is None
        or auth_session.status != "active"
        or expires_at is None
        or expires_at <= datetime.now(UTC)
    ):
        raise AuthenticationError("session is no longer active")
    return auth_session


def _require_secret(secret: SecretStr | None) -> str:
    value = secret.get_secret_value() if secret is not None else ""
    if len(value) < 32:
        raise AuthenticationConfigurationError(
            "SUPPORT_PILOT_JWT_SECRET must contain at least 32 characters"
        )
    return value


def record_auth_event(
    session: Session,
    *,
    actor_id: str,
    outcome: str,
    reason_code: str,
    tenant_id: UUID | None = None,
    action: str = "auth.authenticate",
    resource_id: str = "access_token",
) -> None:
    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_type="user" if outcome == "success" else "system",
            actor_id=actor_id,
            action=action,
            resource_type="session",
            resource_id=resource_id,
            outcome=outcome,
            reason_code=reason_code,
            metadata_redacted={},
            trace_id=uuid4().hex,
        )
    )
    session.commit()
