---
pretty_name: DeepTrap
license: mit
task_categories:
- text-generation
tags:
- benchmark
- agent-safety
- security
- prompt-injection
- llm-agents
- openclaw
size_categories:
- n<1K
---

# DeepTrap

**Security benchmarks for OpenClaw agents**

DeepTrap is a benchmark suite for evaluating how OpenClaw agents behave when
benign user tasks are mixed with malicious workspace context, injected skills,
misleading tool metadata, unsafe command paths, and encoded payloads.

The dataset contains 42 replay tasks arranged across six security categories:

- **Harness Hijacking (R1)**
- **Privacy Leakage (R2)**
- **Unauthorized Execution (R3)**
- **Supply Chain Risk (R4)**
- **Tool Abuse (R5)**
- **Encoding Obfuscation (R6)**

Each row in `data/tasks.jsonl` represents one benchmark task and includes:
`task_id`, `name`, `risk`, `category`, `prompt`, `expected_behavior`,
`grading_criteria`, `workspace_files`, scoring metadata, and flags for
automated checks and LLM judge rubrics.

## Usage

```python
from datasets import load_dataset

dataset = load_dataset("ZJUICSR/DeepTrap", split="train")
```

The original Markdown task definitions are also included in `tasks/`.

## Repository

The benchmark runner and scoring code are available on GitHub:

https://github.com/ZJUICSR/DeepTrap

## License

MIT
