from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.auth.service import decode_access_token
from support_pilot.config import Settings, get_settings
from support_pilot.domain.errors import AuthenticationError, CsrfError
from support_pilot.infrastructure.models import AuthSession, UserAccount

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


@dataclass(frozen=True)
class IssuedSession:
    """Refresh session material returned exactly once, at login or rotation."""

    session_id: UUID
    refresh_token: str
    csrf_token: str


def generate_secret() -> str:
    return token_urlsafe(48)


def hash_secret(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _require_secret(secret: str | None, *, name: str) -> str:
    if not secret:
        raise AuthenticationError(f"{name} is missing")
    return secret


def start_session(
    session: Session,
    user: UserAccount,
    *,
    settings: Settings | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> tuple[AuthSession, IssuedSession]:
    resolved = settings or get_settings()
    issued_at = now or datetime.now(UTC)
    refresh_token = generate_secret()
    csrf_token = generate_secret()
    row = AuthSession(
        user_id=user.id,
        token_hash=hash_secret(refresh_token),
        csrf_hash=hash_secret(csrf_token),
        status="active",
        issued_at=issued_at,
        expires_at=issued_at + timedelta(days=resolved.auth_refresh_token_days),
        user_agent=(user_agent or "")[:200] or None,
    )
    session.add(row)
    session.flush()
    return row, IssuedSession(
        session_id=row.id, refresh_token=refresh_token, csrf_token=csrf_token
    )


def lookup_session(session: Session, refresh_token: str | None) -> AuthSession | None:
    if not refresh_token:
        return None
    return session.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_secret(refresh_token))
    )


def find_active_session(
    session: Session,
    refresh_token: str | None,
    *,
    now: datetime | None = None,
) -> AuthSession:
    _require_secret(refresh_token, name="refresh token")
    row = lookup_session(session, refresh_token)
    moment = now or datetime.now(UTC)
    if row is None or row.status != "active" or _as_aware(row.expires_at) <= moment:
        raise AuthenticationError("refresh session is not active")
    return row


def rotate_session(
    session: Session,
    refresh_token: str | None,
    *,
    settings: Settings | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> tuple[AuthSession, IssuedSession]:
    """Rotate a refresh token: the presented token is revoked and replaced."""

    resolved = settings or get_settings()
    moment = now or datetime.now(UTC)
    previous = find_active_session(session, refresh_token, now=moment)
    previous.status = "revoked"
    previous.revoked_at = moment
    new_token = generate_secret()
    new_csrf = generate_secret()
    row = AuthSession(
        user_id=previous.user_id,
        token_hash=hash_secret(new_token),
        csrf_hash=hash_secret(new_csrf),
        status="active",
        issued_at=moment,
        expires_at=moment + timedelta(days=resolved.auth_refresh_token_days),
        rotated_from=previous.id,
        user_agent=((user_agent or previous.user_agent or "")[:200]) or None,
    )
    session.add(row)
    session.flush()
    return row, IssuedSession(session_id=row.id, refresh_token=new_token, csrf_token=new_csrf)


def revoke_session(
    session: Session,
    *,
    refresh_token: str | None = None,
    session_id: UUID | None = None,
    now: datetime | None = None,
) -> AuthSession | None:
    moment = now or datetime.now(UTC)
    row: AuthSession | None = None
    if session_id is not None:
        row = session.get(AuthSession, session_id)
    elif refresh_token:
        row = session.scalar(
            select(AuthSession).where(AuthSession.token_hash == hash_secret(refresh_token))
        )
    if row is None or row.status != "active":
        return None
    row.status = "revoked"
    row.revoked_at = moment
    session.flush()
    return row


def session_id_from_access_token(
    token: str | None, *, settings: Settings | None = None
) -> UUID | None:
    """Best-effort read of the ``sid`` claim; authentication already happened elsewhere."""

    if not token:
        return None
    try:
        payload = decode_access_token(token, settings=settings)
    except AuthenticationError:
        return None
    raw_session_id = payload.get("sid")
    if not isinstance(raw_session_id, str):
        return None
    try:
        return UUID(raw_session_id)
    except ValueError:
        return None


def list_active_sessions(
    session: Session,
    *,
    user_id: UUID,
    now: datetime | None = None,
) -> list[AuthSession]:
    moment = now or datetime.now(UTC)
    return list(
        session.scalars(
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.status == "active",
                AuthSession.expires_at > moment,
            )
            .order_by(AuthSession.issued_at.desc())
        )
    )


def revoke_user_session(
    session: Session,
    *,
    session_id: UUID,
    user_id: UUID,
    now: datetime | None = None,
) -> AuthSession | None:
    """Revoke one session, but only when it belongs to the caller."""

    moment = now or datetime.now(UTC)
    row = session.get(AuthSession, session_id)
    if row is None or row.user_id != user_id or row.status != "active":
        return None
    row.status = "revoked"
    row.revoked_at = moment
    session.flush()
    return row


def revoke_all_user_sessions(
    session: Session,
    *,
    user_id: UUID,
    now: datetime | None = None,
) -> int:
    moment = now or datetime.now(UTC)
    rows = list(
        session.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.status == "active",
            )
        )
    )
    for row in rows:
        row.status = "revoked"
        row.revoked_at = moment
    session.flush()
    return len(rows)


def verify_csrf(
    session_row: AuthSession,
    *,
    header_value: str | None,
    cookie_value: str | None,
    method: str,
) -> None:
    """Double-submit check plus session binding for cookie-authenticated writes."""

    if method.upper() in SAFE_METHODS:
        return
    if not header_value or not cookie_value or not compare_digest(header_value, cookie_value):
        raise CsrfError("X-CSRF-Token header must match the CSRF cookie")
    if not compare_digest(session_row.csrf_hash, hash_secret(header_value)):
        raise CsrfError("CSRF token does not belong to the current session")


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
