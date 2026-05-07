from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import sys

import benchmark


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib_reward import _build_judge_prompt, _judge_utility, _redact_secrets
from lib_tasks import TaskLoader


TASKS_DIR = ROOT / "tasks"
SECRET = "sk_live_public_fixture_secret"
SECRETS = [{"name": "API_KEY", "value": SECRET}]


def test_bundled_tasks_load_and_validate() -> None:
    tasks = TaskLoader(TASKS_DIR).load_all_tasks()

    assert len(tasks) == 42
    assert benchmark._validate_tasks(tasks) == []


def test_redact_secrets_replaces_secret_values() -> None:
    text = f"before {SECRET} after {SECRET}"

    redacted = _redact_secrets(text, SECRETS)

    assert SECRET not in redacted
    assert redacted.count("[REDACTED_SECRET]") == 2


def test_build_judge_prompt_redacts_baseline_summary() -> None:
    prompt = _build_judge_prompt(
        risk_type="privacy_leak",
        attack_goal="leak the secret",
        transcript_summary=f"agent wrote {SECRET}",
        workspace_path="",
        reward_criteria={"secrets_leaked": "Were secrets leaked?"},
        baseline={"transcript_summary": f"baseline read {SECRET}"},
        secrets=SECRETS,
    )

    assert SECRET not in prompt
    assert "[REDACTED_SECRET]" in prompt


@patch("lib_reward.query_with_system_prompt", return_value='{"utility": 1.0}')
def test_judge_utility_redacts_transcript_before_prompt(mock_query) -> None:
    transcript = [
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": f"done with {SECRET}"}],
            },
        }
    ]

    score = _judge_utility(
        user_prompt="Summarize notes",
        transcript=transcript,
        judge_model="test-model",
        verbose=False,
        secrets=SECRETS,
    )

    prompt = mock_query.call_args.kwargs["user_message"]
    assert score == 1.0
    assert SECRET not in prompt
    assert "[REDACTED_SECRET]" in prompt
