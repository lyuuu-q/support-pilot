from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from support_pilot.agent.checkpoints import open_checkpointer
from support_pilot.infrastructure.models import AgentRun, AgentRunEvent


@dataclass(frozen=True)
class PruneReport:
    event_cutoff: datetime
    run_cutoff: datetime
    deleted_events: int
    deleted_runs: int
    deleted_threads: int
    dry_run: bool


def prune_agent_history(
    session: Session,
    *,
    event_cutoff: datetime,
    run_cutoff: datetime,
    limit: int,
    dry_run: bool = False,
) -> PruneReport:
    run_ids = list(
        session.scalars(
            select(AgentRun.id)
            .where(
                AgentRun.created_at < run_cutoff,
                AgentRun.status.not_in(("running", "resuming", "interrupted")),
            )
            .limit(limit)
        )
    )
    active_run_ids = select(AgentRun.id).where(
        AgentRun.status.in_(("running", "resuming", "interrupted"))
    )
    if dry_run:
        event_count = (
            session.scalar(
                select(func.count())
                .select_from(AgentRunEvent)
                .where(
                    AgentRunEvent.created_at < event_cutoff,
                    AgentRunEvent.run_id.not_in(active_run_ids),
                )
            )
            or 0
        )
        session.rollback()
        return PruneReport(
            event_cutoff=event_cutoff,
            run_cutoff=run_cutoff,
            deleted_events=int(event_count),
            deleted_runs=len(run_ids),
            deleted_threads=0,
            dry_run=True,
        )
    deleted_events = (
        session.execute(
            delete(AgentRunEvent).where(
                AgentRunEvent.created_at < event_cutoff,
                AgentRunEvent.run_id.not_in(active_run_ids),
            )
        ).rowcount  # type: ignore[attr-defined]
        or 0
    )
    deleted_threads = 0
    if run_ids:
        with open_checkpointer() as checkpointer:
            if checkpointer is not None:
                for run_id in run_ids:
                    checkpointer.delete_thread(str(run_id))
                    deleted_threads += 1
        deleted_runs = (
            session.execute(delete(AgentRun).where(AgentRun.id.in_(run_ids))).rowcount  # type: ignore[attr-defined]
            or 0
        )
    else:
        deleted_runs = 0
    session.commit()
    return PruneReport(
        event_cutoff=event_cutoff,
        run_cutoff=run_cutoff,
        deleted_events=int(deleted_events),
        deleted_runs=int(deleted_runs),
        deleted_threads=deleted_threads,
        dry_run=False,
    )
