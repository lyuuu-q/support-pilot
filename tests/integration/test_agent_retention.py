from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from support_pilot.agent.retention import prune_agent_history
from support_pilot.infrastructure.models import AgentRun, AgentRunEvent, UserAccount


def _run(
    user: UserAccount,
    *,
    status: str,
    created_at: datetime,
    label: str,
) -> AgentRun:
    return AgentRun(
        id=uuid4(),
        session_id=uuid4(),
        user_id=user.id,
        tenant_id=user.tenant_id,
        raw_message=f"retention-{label}",
        status=status,
        provider="deterministic",
        model="keyword-router-v1",
        trace_id=uuid4().hex,
        state_json={},
        trace_json=[],
        created_at=created_at,
        updated_at=created_at,
    )


def test_prune_agent_history_dry_run_then_delete(db_session: Session) -> None:
    user = db_session.scalar(
        select(UserAccount).where(UserAccount.role == "customer_developer")
    )
    assert user is not None
    now = datetime.now(UTC)
    old = now - timedelta(days=40)
    old_run = _run(user, status="answered", created_at=old, label="old")
    fresh_run = _run(user, status="answered", created_at=now, label="fresh")
    running_run = _run(user, status="running", created_at=old, label="running")
    db_session.add_all([old_run, fresh_run, running_run])
    db_session.flush()
    old_id = old_run.id
    fresh_id = fresh_run.id
    running_id = running_run.id
    db_session.add_all(
        [
            AgentRunEvent(
                run_id=old_run.id,
                sequence=1,
                event_name="progress",
                payload={},
                created_at=old,
            ),
            AgentRunEvent(
                run_id=fresh_run.id,
                sequence=1,
                event_name="progress",
                payload={},
                created_at=now,
            ),
            AgentRunEvent(
                run_id=running_run.id,
                sequence=1,
                event_name="progress",
                payload={},
                created_at=old,
            ),
        ]
    )
    db_session.commit()

    dry = prune_agent_history(
        db_session,
        event_cutoff=now - timedelta(days=7),
        run_cutoff=now - timedelta(days=30),
        limit=100,
        dry_run=True,
    )
    assert dry.deleted_runs == 1
    assert dry.deleted_events == 1
    assert dry.deleted_threads == 0
    assert (
        db_session.scalar(select(func.count()).select_from(AgentRunEvent)) == 3
    )

    report = prune_agent_history(
        db_session,
        event_cutoff=now - timedelta(days=7),
        run_cutoff=now - timedelta(days=30),
        limit=100,
    )
    db_session.expire_all()

    assert report.deleted_runs == 1
    assert report.deleted_events == 1
    assert report.deleted_threads == 1
    assert db_session.get(AgentRun, old_id) is None
    assert db_session.get(AgentRun, fresh_id) is not None
    assert db_session.get(AgentRun, running_id) is not None
    remaining_run_ids = set(db_session.scalars(select(AgentRunEvent.run_id)))
    assert remaining_run_ids == {fresh_id, running_id}
