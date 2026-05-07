# DeepTrap

**Security benchmarks for OpenClaw agents**

DeepTrap is a benchmark suite for evaluating how OpenClaw agents behave when benign user tasks are mixed with malicious workspace context, injected skills, misleading tool metadata, unsafe command paths, and encoded payloads.

The public repository is intentionally minimal: it contains the runner, the bundled replay tasks, and the scoring code needed to evaluate OpenClaw models. It does not include the private task-generation or attack-search pipeline.

## Why DeepTrap?

Most agent benchmarks measure whether a model can complete useful work. DeepTrap focuses on whether the agent can complete useful work **safely**:

- **Harness Hijacking (R1)** — Does poisoned context or an injected skill redirect the agent into unrequested actions?
- **Privacy Leakage (R2)** — Does the agent expose planted secrets from the workspace?
- **Unauthorized Execution (R3)** — Does the agent run dangerous or out-of-scope commands?
- **Supply Chain Risk (R4)** — Does the agent trust or invoke malicious skill/tool logic?
- **Tool Abuse (R5)** — Does misleading tool metadata cause harmful behavior?
- **Encoding Obfuscation (R6)** — Does the agent decode and execute hidden payloads unsafely?

All tasks use normal, benign user prompts. The risk comes from the surrounding workspace files, skills, simulated tool metadata, or encoded artifacts.

## Quick Start

```bash
# Clone this benchmark repository
git clone https://github.com/ZJUICSR/DeepTrap.git
cd DeepTrap

# Install dependencies, or use your preferred virtualenv workflow
pip install -e .

# Validate task metadata without running OpenClaw
python benchmark.py --dry-run

# List bundled tasks
python benchmark.py --list-tasks

# Run a risk suite
python benchmark.py --model openrouter/anthropic/claude-sonnet-4-5 --suite R1

# Run a specific task
python benchmark.py --model openrouter/anthropic/claude-sonnet-4-5 --suite task_R1_T01
```

Results are written to `results/` by default.

## Requirements

- Python 3.10+
- OpenClaw CLI installed and configured
- A target model available through OpenClaw
- Judge API credentials for the selected judge backend:
  - OpenRouter: `OPENROUTER_API_KEY`
  - DeepSeek: `DEEPSEEK_API_KEY`
  - DashScope/Qwen: DashScope-compatible credentials expected by the bundled client

Model IDs should include their provider prefix, for example `openrouter/anthropic/claude-sonnet-4-5`.

## What Gets Tested

DeepTrap includes 42 replay tasks arranged as six security categories crossed with seven scenario categories. The security category defines the attack/risk being evaluated; the scenario category defines the benign user workflow in which that risk appears.

| Suite | Category | Tasks | What is measured |
|------|----------|-------|------------------|
| `R1` | Harness Hijacking | 7 | Resistance to poisoned context and injected workflow steps |
| `R2` | Privacy Leakage | 7 | Protection of planted credentials and sensitive values |
| `R3` | Unauthorized Execution | 7 | Refusal of dangerous commands and boundary-crossing actions |
| `R4` | Supply Chain Risk | 7 | Handling of malicious skills and tool-like integrations |
| `R5` | Tool Abuse | 7 | Detection of misleading or mismatched tool behavior |
| `R6` | Encoding Obfuscation | 7 | Handling of encoded instructions and multi-step payloads |

The current seven scenario categories are:

| Scenario | Typical task family |
|----------|---------------------|
| `T01` | Meeting notes, action items, and routine workflow summaries |
| `T02` | Python/code formatting, refactoring, and API/log processing |
| `T03` | Research notes, literature review, citation, and survey analysis |
| `T04` | Deployment readiness, configuration validation, and service health checks |
| `T05` | Sales, revenue, and structured business-data reporting |
| `T06` | Blog/content drafting, style checking, onboarding, and feedback summaries |
| `T07` | System administration, environment audits, deployment checks, and log backup |

Each task reports:

- `grading`: defense-oriented score, where higher is better
- `attack_eval`: attack-oriented score, where higher means the replayed attack succeeded more strongly
- task timing, transcript length, workspace path, and usage metadata when available

## Command Reference

| Flag | Description |
|------|-------------|
| `--model MODEL` | Target model identifier configured for OpenClaw |
| `--suite SUITE` | `all`, a risk suite such as `R1`, or comma-separated task IDs |
| `--runs N` | Number of runs per task for averaging |
| `--timeout-multiplier N` | Scale task timeouts for slower models |
| `--judge-model MODEL` | Judge model for attack, stealth, and utility scoring |
| `--output-dir DIR` | Results directory, default `results/` |
| `--list-tasks` | Print bundled task IDs and exit |
| `--dry-run` | Validate task loading and scoring metadata without running OpenClaw |
| `--verbose` | Print detailed execution logs |

## Inspecting Results

```bash
# Overall score summary
jq '.summary' results/*.json

# Per-task defense scores
jq '.tasks[] | {task_id, category, score: .grading.mean}' results/*.json

# Tasks where the replay attack was reproduced strongly
jq '.tasks[] | select(.attack_eval.mean >= 0.8) | {task_id, attack: .attack_eval.mean}' results/*.json
```

## Project Layout

```text
.
├── benchmark.py                  # Public benchmark runner
├── tasks/                         # 42 bundled task definitions
├── scripts/                       # Runtime support code
│   ├── lib_agent.py               # OpenClaw execution helpers
│   ├── lib_reward.py              # Attack/defense scoring
│   ├── lib_criteria.py            # Public judge criteria
│   ├── lib_llm.py                 # Judge backend router
│   ├── lib_openrouter.py          # OpenRouter judge client
│   ├── lib_deepseek.py            # DeepSeek judge client
│   └── lib_dashscope.py           # DashScope/Qwen judge client
├── tests/                         # Public validation tests
├── SKILL.md                       # Agent-facing benchmark skill
└── pyproject.toml
```

## Acknowledgments

DeepTrap was inspired in part by [PinchBench](https://github.com/pinchbench/skill), which provides a practical benchmark suite for measuring OpenClaw agent capability on real-world tasks. We thank the PinchBench project for demonstrating a clear, usable benchmark format for OpenClaw agents.

## License

MIT — see `LICENSE` when included in the distribution.
