from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.auth.session_retention import prune_auth_sessions
from support_pilot.infrastructure.models import AuthSession

DEMO_PASSWORD = "SupportPilotDemo!2026"


def _session_rows(session: Session) -> list[AuthSession]:
    return list(session.scalars(select(AuthSession).order_by(AuthSession.issued_at)))


def _backdate(session: Session, row: AuthSession, *, days_ago: int) -> None:
    row.expires_at = datetime.now(UTC) - timedelta(days=days_ago)
    session.commit()


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "beta.developer@example.com", "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200


def test_dry_run_reports_without_deleting(client: TestClient, db_session: Session) -> None:
    _login(client)
    _login(client)
    rows = _session_rows(db_session)
    assert len(rows) == 2
    _backdate(db_session, rows[0], days_ago=90)

    report = prune_auth_sessions(
        db_session,
        cutoff=datetime.now(UTC) - timedelta(days=30),
        limit=50,
        dry_run=True,
    )

    assert report.dry_run is True
    assert report.deleted_sessions == 1
    assert report.active_sessions == 1
    assert len(_session_rows(db_session)) == 2


def test_prune_deletes_only_sessions_expired_before_cutoff(
    client: TestClient,
    db_session: Session,
) -> None:
    for _ in range(3):
        _login(client)
    rows = _session_rows(db_session)
    assert len(rows) == 3
    _backdate(db_session, rows[0], days_ago=120)
    _backdate(db_session, rows[1], days_ago=45)
    # rows[2] stays live; a revoked-but-live session must never be pruned either
    rows[1].status = "revoked"
    rows[1].revoked_at = datetime.now(UTC)
    db_session.commit()

    report = prune_auth_sessions(
        db_session,
        cutoff=datetime.now(UTC) - timedelta(days=30),
        limit=50,
    )

    assert report.dry_run is False
    assert report.deleted_sessions == 2
    remaining = _session_rows(db_session)
    assert len(remaining) == 1
    assert remaining[0].id == rows[2].id
    assert report.active_sessions == 1


def test_prune_respects_the_batch_limit(client: TestClient, db_session: Session) -> None:
    for _ in range(3):
        _login(client)
    rows = _session_rows(db_session)
    for row in rows:
        _backdate(db_session, row, days_ago=60)

    report = prune_auth_sessions(
        db_session,
        cutoff=datetime.now(UTC) - timedelta(days=30),
        limit=2,
    )

    assert report.deleted_sessions == 2
    assert len(_session_rows(db_session)) == 1
