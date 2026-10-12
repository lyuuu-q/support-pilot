import argparse
import json
from datetime import UTC, datetime, timedelta

from support_pilot.agent.retention import prune_agent_history
from support_pilot.config import get_settings
from support_pilot.infrastructure.database import get_session_factory


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Prune old agent runs, events and checkpoints")
    parser.add_argument(
        "--runs-older-than-days",
        type=int,
        default=settings.agent_run_retention_days,
    )
    parser.add_argument(
        "--events-older-than-days",
        type=int,
        default=settings.agent_run_event_retention_days,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=settings.agent_run_prune_batch_size,
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    now = datetime.now(UTC)
    event_cutoff = now - timedelta(days=max(args.events_older_than_days, 1))
    run_cutoff = now - timedelta(days=max(args.runs_older_than_days, 1))
    with get_session_factory()() as session:
        report = prune_agent_history(
            session,
            event_cutoff=event_cutoff,
            run_cutoff=run_cutoff,
            limit=max(args.limit, 1),
            dry_run=args.dry_run,
        )
    print(
        json.dumps(
            {
                "event_cutoff": report.event_cutoff.isoformat(),
                "run_cutoff": report.run_cutoff.isoformat(),
                "deleted_events": report.deleted_events,
                "deleted_runs": report.deleted_runs,
                "deleted_threads": report.deleted_threads,
                "dry_run": report.dry_run,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
