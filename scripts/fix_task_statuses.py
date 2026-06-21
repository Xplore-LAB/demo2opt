import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.task_manager import TaskManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair stale processing tasks in task_progress.")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=1.0,
        help="Mark processing tasks older than this threshold as failed.",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        default=[],
        help="Repair a specific task id regardless of age. Can be used multiple times.",
    )
    parser.add_argument(
        "--reason",
        default="Task recovered by repair script: stale processing task.",
        help="Failure reason to write into repaired tasks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the tasks that would be repaired without writing changes.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    manager = TaskManager()
    repaired_tasks = manager.repair_stale_processing_tasks(
        max_age_hours=args.max_age_hours,
        reason=args.reason,
        task_ids=args.task_id,
        dry_run=args.dry_run,
    )

    if not repaired_tasks:
        print("No stale processing tasks matched the repair criteria.")
        return 0

    action = "Would repair" if args.dry_run else "Repaired"
    print(f"{action} {len(repaired_tasks)} task(s):")
    for task in repaired_tasks:
        print(f"- {task.task_id} | {task.start_time} | {task.current_step}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
