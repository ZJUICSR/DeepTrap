#!/usr/bin/env python3
"""Public OpenClaw security benchmark runner.

This entrypoint intentionally contains only benchmark execution logic. It does
not include the private generation pipeline used to produce the replay tasks.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib_agent import (
    cleanup_agent_sessions,
    ensure_agent_exists,
    execute_openclaw_task,
    slugify_model,
)
from lib_criteria import RISK_CRITERIA
from lib_reward import (
    ATTACK_SUCCESS_THRESHOLD,
    REWARD_JUDGE_MODEL,
    RewardResult,
    evaluate_attack,
)
from lib_tasks import Task, TaskLoader


LOGGER = logging.getLogger("deeptrap")

TASK_CATEGORY_TO_RISK_TYPE = {
    "harness_hijacking": "harness_hijacking",
    "privacy_leakage": "privacy_leak",
    "unauthorized_execution": "unauthorized_execution",
    "supply_chain_risk": "supply_chain",
    "tool_abuse": "tool_abuse",
    "encoding_obfuscation": "encoding_obfuscation",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeepTrap public OpenClaw benchmark runner")
    parser.add_argument("--tasks-dir", default=None, help="Task directory (default: bundled tasks)")
    parser.add_argument("--model", help="Target model identifier configured for OpenClaw")
    parser.add_argument(
        "--suite",
        default="all",
        help='Tasks to run: "all", risk prefix like R1, or comma-separated task IDs',
    )
    parser.add_argument("--runs", type=int, default=1, help="Number of runs per task")
    parser.add_argument(
        "--timeout-multiplier",
        type=float,
        default=1.0,
        help="Scale all task timeouts for slower models",
    )
    parser.add_argument("--output-dir", default="results", help="Results directory")
    parser.add_argument(
        "--judge-model",
        "--reward-judge",
        "--judge",
        dest="judge_model",
        default=None,
        help=(
            "Judge model for attack/stealth/utility scoring. Prefix routing: "
            "deepseek/... uses DeepSeek, qwen/... uses DashScope, otherwise OpenRouter."
        ),
    )
    parser.add_argument("--list-tasks", action="store_true", help="List bundled tasks and exit")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate task loading and scoring metadata without executing OpenClaw",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logs")
    return parser.parse_args()


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _default_tasks_dir() -> Path:
    return Path(__file__).resolve().parent / "tasks"


def _normalize_file_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, indent=2, ensure_ascii=False)


def _derive_attack_payload(task: Task) -> Dict[str, str]:
    payload_paths = (task.frontmatter or {}).get("attack_payload_paths")
    task_files = {
        file_spec["path"]: _normalize_file_content(file_spec.get("content", ""))
        for file_spec in task.workspace_files
        if isinstance(file_spec, dict)
        and isinstance(file_spec.get("path"), str)
        and "content" in file_spec
    }
    if isinstance(payload_paths, list) and payload_paths:
        return {str(path): task_files[str(path)] for path in payload_paths if str(path) in task_files}
    return task_files


def _extract_malicious_skill_names(task: Task, attack_payload: Dict[str, str]) -> List[str]:
    names = task.frontmatter.get("malicious_skill_names")
    if isinstance(names, list) and names:
        return [str(name) for name in names if name]

    inferred = set()
    for rel_path in attack_payload:
        parts = Path(rel_path).parts
        for idx, part in enumerate(parts):
            if part == "skills" and idx + 1 < len(parts):
                inferred.add(parts[idx + 1])
    return sorted(inferred)


def _risk_type_for_task(task: Task) -> Optional[str]:
    return TASK_CATEGORY_TO_RISK_TYPE.get(task.category)


def _evaluate_attack_for_task(
    *,
    task: Task,
    execution_result: Dict[str, Any],
    judge_model: Optional[str],
    verbose: bool,
) -> Optional[RewardResult]:
    risk_type = _risk_type_for_task(task)
    if not risk_type:
        LOGGER.warning("No risk type mapping for task category %s", task.category)
        return None

    frontmatter = task.frontmatter or {}
    attack_goals = frontmatter.get("attack_goals") if isinstance(frontmatter, dict) else {}
    if not isinstance(attack_goals, dict):
        attack_goals = {}
    attack_goal = attack_goals.get(
        risk_type,
        frontmatter.get("attack_goal", task.expected_behavior or task.prompt),
    )
    if not isinstance(attack_goal, str):
        attack_goal = str(attack_goal)

    attack_payload = _derive_attack_payload(task)
    malicious_skill_names = _extract_malicious_skill_names(task, attack_payload)
    criteria = RISK_CRITERIA.get(risk_type, {})

    return evaluate_attack(
        risk_type=risk_type,
        attack_goal=attack_goal,
        attack_payload=attack_payload,
        transcript=execution_result.get("transcript", []),
        workspace_path=execution_result.get("workspace", ""),
        reward_criteria=criteria,
        utility_criteria=frontmatter.get("utility_criteria"),
        user_prompt=frontmatter.get("user_prompt", task.prompt),
        attack_check_code=task.automated_checks or frontmatter.get("attack_check_code", ""),
        malicious_skill_names=malicious_skill_names or None,
        judge_model=judge_model or REWARD_JUDGE_MODEL,
        baseline=None,
        secrets=frontmatter.get("secrets"),
        verbose=verbose,
    )


def _select_task_ids(tasks: List[Task], suite: str) -> Optional[List[str]]:
    if suite == "all":
        return None
    all_task_ids = {task.task_id for task in tasks}
    selected: List[str] = []
    for token in suite.split(","):
        token = token.strip()
        if not token:
            continue
        if token in all_task_ids:
            selected.append(token)
            continue
        prefix = f"task_{token}_"
        matches = [task.task_id for task in tasks if task.task_id.startswith(prefix)]
        selected.extend(matches or [token])
    return selected


def _next_run_id(run_root: Path) -> str:
    run_root.mkdir(parents=True, exist_ok=True)
    existing = [int(path.name) for path in run_root.iterdir() if path.is_dir() and path.name.isdigit()]
    return f"{(max(existing) + 1) if existing else 1:04d}"


def _list_tasks(tasks: List[Task]) -> None:
    for task in tasks:
        print(f"{task.task_id}\t{task.category}\t{task.name}")


def _validate_tasks(tasks: List[Task]) -> List[str]:
    errors: List[str] = []
    for task in tasks:
        fm = task.frontmatter or {}
        if not task.task_id:
            errors.append(f"{task.file_path}: missing id")
        if task.category not in TASK_CATEGORY_TO_RISK_TYPE:
            errors.append(f"{task.task_id}: unknown category {task.category!r}")
        if not task.workspace_files:
            errors.append(f"{task.task_id}: missing workspace_files")
        if not (task.prompt or fm.get("user_prompt")):
            errors.append(f"{task.task_id}: missing prompt/user_prompt")
        if not (task.automated_checks or fm.get("attack_check_code")):
            errors.append(f"{task.task_id}: missing attack_check_code")
        risk_type = _risk_type_for_task(task)
        if risk_type and risk_type not in RISK_CRITERIA:
            errors.append(f"{task.task_id}: missing public criteria for {risk_type}")
    return errors


def _aggregate_run_scores(attack_runs: List[Dict[str, Any]]) -> Dict[str, float]:
    if not attack_runs:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    scores = [float(run["score"]) for run in attack_runs]
    return {
        "mean": statistics.mean(scores),
        "std": statistics.stdev(scores) if len(scores) > 1 else 0.0,
        "min": min(scores),
        "max": max(scores),
    }


def _summarize_results(task_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    defense_scores = []
    ags_scores = []
    ugs_scores = []
    by_category: Dict[str, List[float]] = {}
    for entry in task_entries:
        attack_eval = entry.get("attack_eval") or {}
        attack_mean = float(attack_eval.get("mean", 0.0)) if isinstance(attack_eval, dict) else 0.0
        defense = 1.0 - attack_mean
        defense_scores.append(defense)
        by_category.setdefault(entry.get("category", "unknown"), []).append(defense)
        runs = attack_eval.get("runs", []) if isinstance(attack_eval, dict) else []
        if isinstance(runs, list):
            for run in runs:
                if not isinstance(run, dict):
                    continue
                ags_scores.append(float(run.get("attack_success", 0.0)))
                ugs_scores.append(float(run.get("utility", 0.0)))

    category_scores = {
        category: round(statistics.mean(values), 4)
        for category, values in sorted(by_category.items())
        if values
    }
    return {
        "defense_score": round(statistics.mean(defense_scores), 4) if defense_scores else 0.0,
        "AGS": round(statistics.mean(ags_scores), 4) if ags_scores else 0.0,
        "UGS": round(statistics.mean(ugs_scores), 4) if ugs_scores else 0.0,
        "task_count": len(task_entries),
        "category_scores": category_scores,
    }


def main() -> None:
    args = _parse_args()
    _configure_logging(args.verbose)

    tasks_dir = Path(args.tasks_dir) if args.tasks_dir else _default_tasks_dir()
    if not tasks_dir.exists():
        LOGGER.error("Tasks directory not found: %s", tasks_dir)
        sys.exit(1)

    loader = TaskLoader(tasks_dir)
    tasks = loader.load_all_tasks()
    validation_errors = _validate_tasks(tasks)

    if args.list_tasks:
        _list_tasks(tasks)
        if validation_errors:
            LOGGER.warning("Task metadata validation found %d issue(s)", len(validation_errors))
        return

    if args.dry_run:
        if validation_errors:
            for error in validation_errors:
                LOGGER.error(error)
            sys.exit(1)
        LOGGER.info("Dry run passed: %d task(s) loaded from %s", len(tasks), tasks_dir)
        return

    if validation_errors:
        for error in validation_errors:
            LOGGER.error(error)
        sys.exit(1)
    if not args.model:
        LOGGER.error("Missing required argument: --model")
        sys.exit(2)

    task_ids = _select_task_ids(tasks, args.suite)
    tasks_to_run = tasks if task_ids is None else [task for task in tasks if task.task_id in task_ids]
    if not tasks_to_run:
        LOGGER.error("No tasks selected for suite %r", args.suite)
        sys.exit(1)

    model_slug = slugify_model(args.model)
    run_root = Path("/tmp/deeptrap")
    run_id = _next_run_id(run_root)
    agent_id = f"bench-{model_slug}"
    agent_workspace = run_root / run_id / "agent_workspace"
    benchmark_root = Path(__file__).resolve().parent

    ensure_agent_exists(agent_id, args.model, agent_workspace)
    cleanup_agent_sessions(agent_id)

    results: List[Dict[str, Any]] = []
    task_entries: List[Dict[str, Any]] = []
    runs_per_task = max(1, args.runs)

    for index, task in enumerate(tasks_to_run, 1):
        LOGGER.info("Task %d/%d: %s", index, len(tasks_to_run), task.task_id)
        task_results = []
        attack_runs = []
        for run_index in range(runs_per_task):
            try:
                result = execute_openclaw_task(
                    task=task,
                    agent_id=agent_id,
                    model_id=args.model,
                    run_id=f"{run_id}-{run_index + 1}",
                    timeout_multiplier=args.timeout_multiplier,
                    skill_dir=benchmark_root,
                    verbose=args.verbose,
                )
            except Exception as exc:
                LOGGER.warning("Task execution failed for %s: %s", task.task_id, exc)
                result = {
                    "agent_id": agent_id,
                    "task_id": task.task_id,
                    "status": "error",
                    "transcript": [],
                    "usage": {},
                    "workspace": "",
                    "exit_code": -1,
                    "timed_out": False,
                    "execution_time": 0.0,
                    "stdout": "",
                    "stderr": str(exc),
                }

            attack_eval = _evaluate_attack_for_task(
                task=task,
                execution_result=result,
                judge_model=args.judge_model,
                verbose=args.verbose,
            )
            result["attack_eval"] = attack_eval.to_dict() if attack_eval else None
            task_results.append(result)
            results.append(result)
            if attack_eval:
                attack_runs.append(attack_eval.to_dict())
                LOGGER.info(
                    "%s AGS=%.2f UGS=%.2f stealth=%.2f",
                    task.task_id,
                    attack_eval.attack_success,
                    attack_eval.utility,
                    attack_eval.stealth,
                )

        attack_summary = _aggregate_run_scores(attack_runs)
        defense_scores = [1.0 - float(run["score"]) for run in attack_runs]
        grading = {
            "mean": statistics.mean(defense_scores) if defense_scores else 0.0,
            "std": statistics.stdev(defense_scores) if len(defense_scores) > 1 else 0.0,
            "min": min(defense_scores) if defense_scores else 0.0,
            "max": max(defense_scores) if defense_scores else 0.0,
        }
        task_entries.append(
            {
                "task_id": task.task_id,
                "name": task.name,
                "category": task.category,
                "status": [run["status"] for run in task_results],
                "timed_out": [run["timed_out"] for run in task_results],
                "execution_time": [run["execution_time"] for run in task_results],
                "transcript_length": [len(run["transcript"]) for run in task_results],
                "usage": [run.get("usage", {}) for run in task_results],
                "workspace": [run["workspace"] for run in task_results],
                "grading": grading,
                "attack_eval": {"runs": attack_runs, **attack_summary},
            }
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    aggregate = {
        "model": args.model,
        "judge_model": args.judge_model or REWARD_JUDGE_MODEL,
        "run_id": run_id,
        "timestamp": time.time(),
        "suite": args.suite,
        "runs_per_task": runs_per_task,
        "summary": _summarize_results(task_entries),
        "tasks": task_entries,
    }
    output_path = output_dir / f"{run_id}_{model_slug}.json"
    output_path.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")

    summary = aggregate["summary"]
    LOGGER.info(
        "Final AGS=%.2f UGS=%.2f across %d task(s)",
        summary["AGS"],
        summary["UGS"],
        summary["task_count"],
    )
    LOGGER.info("Saved results to %s", output_path)


if __name__ == "__main__":
    main()
