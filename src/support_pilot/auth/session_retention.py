from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from support_pilot.infrastructure.models import AuthSession
from support_pilot.telemetry import get_tracer, record_session_prune


@dataclass(frozen=True)
class SessionPruneReport:
    cutoff: datetime
    deleted_sessions: int
    active_sessions: int
    dry_run: bool


def prune_auth_sessions(
    session: Session,
    *,
    cutoff: datetime,
    limit: int,
    dry_run: bool = False,
    now: datetime | None = None,
) -> SessionPruneReport:
    """Delete sessions that expired before the cutoff, never live ones.

    A session row is removable only when ``expires_at < cutoff``, and the cutoff is
    already ``now - retention_days``. Live sessions therefore can never be selected,
    regardless of status.
    """

    span = get_tracer().start_span("auth.sessions.prune")
    moment = now or datetime.now(UTC)
    session_ids = list(
        session.scalars(select(AuthSession.id).where(AuthSession.expires_at < cutoff).limit(limit))
    )
    active_sessions = (
        session.scalar(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.status == "active",
                AuthSession.expires_at > moment,
            )
        )
        or 0
    )
    if dry_run:
        session.rollback()
        span.set_attribute("auth.sessions.dry_run", True)
        record_session_prune(deleted_sessions=len(session_ids), dry_run=True)
        span.end()
        return SessionPruneReport(
            cutoff=cutoff,
            deleted_sessions=len(session_ids),
            active_sessions=int(active_sessions),
            dry_run=True,
        )
    deleted_sessions = 0
    if session_ids:
        deleted_sessions = (
            session.execute(delete(AuthSession).where(AuthSession.id.in_(session_ids))).rowcount  # type: ignore[attr-defined]
            or 0
        )
    session.commit()
    span.set_attribute("auth.sessions.dry_run", False)
    record_session_prune(deleted_sessions=int(deleted_sessions), dry_run=False)
    span.end()
    return SessionPruneReport(
        cutoff=cutoff,
        deleted_sessions=int(deleted_sessions),
        active_sessions=int(active_sessions),
        dry_run=False,
    )
