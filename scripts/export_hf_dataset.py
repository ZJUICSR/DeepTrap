#!/usr/bin/env python3
"""Export bundled DeepTrap tasks as Hugging Face-compatible JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib_tasks import Task, TaskLoader


DEFAULT_TASKS_DIR = ROOT / "tasks"
DEFAULT_OUTPUT = ROOT / "data" / "tasks.jsonl"


def task_to_hf_row(task: Task) -> Dict[str, Any]:
    """Convert a DeepTrap task to one dataset row."""
    frontmatter = task.frontmatter or {}
    return {
        "task_id": task.task_id,
        "name": task.name,
        "risk": frontmatter.get("risk", ""),
        "category": task.category,
        "grading_type": task.grading_type,
        "timeout_seconds": task.timeout_seconds,
        "prompt": task.prompt,
        "expected_behavior": task.expected_behavior,
        "grading_criteria": task.grading_criteria,
        "workspace_files": task.workspace_files,
        "grading_weights": task.grading_weights,
        "has_automated_checks": task.automated_checks is not None,
        "has_llm_judge_rubric": task.llm_judge_rubric is not None,
    }


def export_tasks(tasks_dir: Path, output_path: Path) -> List[Dict[str, Any]]:
    """Load tasks and write them as newline-delimited JSON."""
    rows = [task_to_hf_row(task) for task in TaskLoader(tasks_dir).load_all_tasks()]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        for row in rows:
            output_file.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            output_file.write("\n")
    return rows


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export bundled DeepTrap tasks to data/tasks.jsonl for Hugging Face."
    )
    parser.add_argument(
        "--tasks-dir",
        type=Path,
        default=DEFAULT_TASKS_DIR,
        help="Directory containing task_*.md files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination JSONL file.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = export_tasks(args.tasks_dir, args.output)
    print(f"Wrote {len(rows)} tasks to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
