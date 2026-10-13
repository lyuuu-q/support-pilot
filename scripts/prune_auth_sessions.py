import argparse
import json
from datetime import UTC, datetime, timedelta

from support_pilot.auth.session_retention import prune_auth_sessions
from support_pilot.config import get_settings
from support_pilot.infrastructure.database import get_session_factory


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Prune expired browser auth sessions")
    parser.add_argument(
        "--sessions-older-than-days",
        type=int,
        default=settings.auth_session_retention_days,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=settings.auth_session_prune_batch_size,
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cutoff = datetime.now(UTC) - timedelta(days=max(args.sessions_older_than_days, 1))
    with get_session_factory()() as session:
        report = prune_auth_sessions(
            session,
            cutoff=cutoff,
            limit=max(args.limit, 1),
            dry_run=args.dry_run,
        )
    print(
        json.dumps(
            {
                "cutoff": report.cutoff.isoformat(),
                "deleted_sessions": report.deleted_sessions,
                "active_sessions": report.active_sessions,
                "dry_run": report.dry_run,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
