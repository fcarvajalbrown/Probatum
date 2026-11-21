<div align="center">

# Probatum

**A red-team AI agent that reports only what it can prove.**

[![Status](https://img.shields.io/badge/status-early%20research-orange?style=flat-square)](ROADMAP.md)
[![Based on CAI](https://img.shields.io/badge/based%20on-CAI%20v1.1.5-blue?style=flat-square)](https://github.com/aliasrobotics/cai)
[![License](https://img.shields.io/badge/license-research--use-blue?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue?style=flat-square)](pyproject.toml)

</div>

---

Probatum is a research fork of [Cybersecurity AI (CAI)](https://github.com/aliasrobotics/cai), the
offensive-security agent framework archived by Alias Robotics in August 2026. It keeps CAI running
and adds one thing the archive never got: an agent that refuses to report a finding it cannot prove.

## The problem

Autonomous offensive-security agents fabricate. Published 2026 evidence:

- Only 62 to 87 percent of flags recovered by agents are backed by a verified exploit trace; the
  rest are shortcuts or plain model text ([arXiv:2608.26237](https://arxiv.org/abs/2608.26237)).
- 45.3 percent of agent runs fall back to *simulating* a vulnerability, and only 5.3 percent of
  CVE and model pairs reproduce a real one ([arXiv:2609.34450](https://arxiv.org/abs/2609.34450)).
- A controlled scaffold study recorded one agent emitting 93 fabricated flags and zero real solves.

Benchmarks are starting to catch this after the fact. No open agent stops it inside its own loop.

## What Probatum adds

A **trace-provenance gate**. A finding is accepted only when its proof, a flag, a shell, or
exfiltrated data, appears in real tool output after the exploit step. A claim backed only by
model-generated text is rejected and logged with the trace evidence that failed it.

The gate lives in CAI's existing guardrail layer, so switching it on and off is the before-and-after
control for measurement.

## How it is measured

| Backend | Role |
|:--|:--|
| A frontier model via API | Headline before-and-after on fabrication rate |
| Local `qwen2.5-coder:7b` via Ollama | On-premise data point and offline fallback |

Both run the [CAIBench](https://arxiv.org/abs/2510.24317) Cybench subset, reporting solve rate,
fabricated-finding rate, and provenance-verified rate per run, from a single reproducible command.

## Status

Early research. The scope, design, and first decision are set; the gate and harness are in build.
See **[ROADMAP.md](ROADMAP.md)** for phases and **[docs/PRD.md](docs/PRD.md)** for the full plan.

## Relationship to CAI

Probatum builds directly on CAI v1.1.5 and exists because of it. CAI's core (`src/cai/`) is
licensed by Alias Robotics for non-commercial research use; the agent layer (`src/cai/agents/`) is
MIT, derived from [openai/openai-agents-python](https://github.com/openai/openai-agents-python).
Probatum stays inside that research-use license, cites CAI and CAIBench as the baseline it builds on,
and claims no part of that work as its own. See [LICENSE](LICENSE).

> This is unmaintained-lineage offensive tooling for authorized testing only. Run it in isolated
> environments, against systems you are explicitly permitted to test.
