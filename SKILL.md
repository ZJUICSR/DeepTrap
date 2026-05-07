---
name: deeptrap-benchmark
description: Run the DeepTrap security benchmark to evaluate OpenClaw agents against indirect prompt injection, privacy leakage, unauthorized execution, supply-chain risk, tool abuse, and encoding-obfuscation replay tasks. Use when testing OpenClaw model security, comparing defensive behavior across models, or validating that an OpenClaw setup can run the bundled benchmark tasks.
metadata:
  author: DeepTrap
  version: "0.1.0"
  repository: https://github.com/ZJUICSR/DeepTrap
---

# DeepTrap Benchmark Skill

DeepTrap evaluates OpenClaw agents on security replay tasks. The benchmark measures whether an agent resists malicious workspace context, injected skills, misleading tools, dangerous commands, and obfuscated payloads while still completing the user's benign task.

## Prerequisites

- Python 3.10+
- OpenClaw CLI installed and configured
- A target model available through OpenClaw
- Judge API credentials for the selected judge backend:
  - `OPENROUTER_API_KEY` for OpenRouter models
  - `DEEPSEEK_API_KEY` for DeepSeek models
  - DashScope credentials for Qwen/DashScope models

## Quick Start

```bash
cd <benchmark_directory>

# Validate bundled task metadata without running OpenClaw
python benchmark.py --dry-run

# List available tasks
python benchmark.py --list-tasks

# Run all tasks
python benchmark.py --model openrouter/anthropic/claude-sonnet-4-5

# Run one risk suite
python benchmark.py --model openrouter/anthropic/claude-sonnet-4-5 --suite R2

# Run specific tasks
python benchmark.py --model openrouter/anthropic/claude-sonnet-4-5 --suite task_R1_T01,task_R2_T01
```

## Available Suites

| Suite | Category | What it tests |
|------|----------|---------------|
| `R1` | Harness Hijacking | Whether poisoned context or injected skills redirect agent behavior |
| `R2` | Privacy Leakage | Whether planted secrets are exposed in outputs, files, or external actions |
| `R3` | Unauthorized Execution | Whether the agent runs dangerous or out-of-scope commands |
| `R4` | Supply Chain Risk | Whether malicious skill/tool logic is invoked or trusted |
| `R5` | Tool Abuse | Whether misleading tool metadata causes harmful behavior |
| `R6` | Encoding Obfuscation | Whether encoded payloads are decoded and executed unsafely |

Each suite currently contains seven replay tasks: `task_R*_T01` through `task_R*_T07`.

## Command Line Options

| Option | Description |
|--------|-------------|
| `--model MODEL` | Target model identifier configured for OpenClaw |
| `--suite SUITE` | `all`, a risk suite like `R1`, or comma-separated task IDs |
| `--runs N` | Number of runs per task for averaging |
| `--timeout-multiplier N` | Scale task timeouts for slower models |
| `--judge-model MODEL` | Judge model; DeepSeek and DashScope route by prefix |
| `--output-dir DIR` | Results directory, default `results/` |
| `--list-tasks` | Print bundled tasks and exit |
| `--dry-run` | Validate task loading and scoring metadata without running OpenClaw |
| `--verbose` | Print detailed execution logs |

## Results

Results are saved as JSON in the output directory:

```bash
# Overall summary
jq '.summary' results/*.json

# Per-task defense scores
jq '.tasks[] | {task_id, score: .grading.mean}' results/*.json

# Tasks with reproduced attacks
jq '.tasks[] | select(.attack_eval.mean >= 0.8) | {task_id, attack: .attack_eval.mean}' results/*.json
```

Scores are defense-oriented in the `grading` field: higher is better. The `attack_eval` field is attack-oriented: higher means the replayed attack was more successful.
