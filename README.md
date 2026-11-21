<div align="center">

# Probatum

**A red-team AI agent that reports only what it can prove.**

[![Status](https://img.shields.io/badge/status-early%20research-orange?style=flat-square)](ROADMAP.md)
[![Based on CAI](https://img.shields.io/badge/based%20on-CAI%20v1.1.5-blue?style=flat-square)](https://github.com/aliasrobotics/cai)
[![License](https://img.shields.io/badge/license-research--use-blue?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue?style=flat-square)](pyproject.toml)

</div>

---

In August 2026, Alias Robotics archived [Cybersecurity AI (CAI)](https://github.com/aliasrobotics/cai),
its offensive-security agent framework. The research stood; the code stopped. Probatum is a research
fork that keeps it running, and adds the one thing the archive never got: an agent that will not
report a finding it cannot prove.

## The problem

Autonomous offensive-security agents fabricate. The 2026 evidence is specific:

- Of the flags agents recover, only 62 to 87 percent are backed by a verified exploit trace. The
  rest are shortcuts or plain model text ([arXiv:2608.26237](https://arxiv.org/abs/2608.26237)).
- In 45.3 percent of runs, the agent falls back to *simulating* a vulnerability. Only 5.3 percent of
  CVE and model pairs reproduce a real one ([arXiv:2609.34450](https://arxiv.org/abs/2609.34450)).
- One controlled study clocked a single agent emitting 93 fabricated flags and zero real solves.

Benchmarks are starting to catch this after the run. No open agent stops it inside the loop.

## What Probatum adds

A trace-provenance gate. A finding counts only when its proof shows up in real tool output after the
exploit step: a flag, a shell, data pulled out. A claim that lives only in the model's own text is
rejected, and logged with the trace that failed it.

The gate sits in CAI's existing guardrail layer, so turning it on and off is the before-and-after
control for measurement.

## How it is measured

| Backend | Role |
|:--|:--|
| A frontier model via API | Headline before-and-after on fabrication rate |
| Local `qwen2.5-coder:7b` via Ollama | On-premise data point and offline fallback |

Both run the [CAIBench](https://arxiv.org/abs/2510.24317) Cybench subset and report, per run, three
numbers: solve rate, fabricated-finding rate, and provenance-verified rate. One command reproduces
the whole thing.

## Status

Early research. The scope, the design, and the first decision are set. The gate and the harness are
being built. See **[ROADMAP.md](ROADMAP.md)** for the phases and **[docs/PRD.md](docs/PRD.md)** for
the full plan. No results are claimed yet.

## Relationship to CAI

Probatum builds on CAI v1.1.5 and exists because of it. CAI's core (`src/cai/`) is licensed by Alias
Robotics for non-commercial research use; the agent layer (`src/cai/agents/`) is MIT, derived from
[openai/openai-agents-python](https://github.com/openai/openai-agents-python). Probatum stays inside
that research-use license, cites CAI and CAIBench as the baseline it builds on, and claims no part of
that work as its own. See [LICENSE](LICENSE).

> This is unmaintained-lineage offensive tooling, for authorized testing only. Run it in isolated
> environments, against systems you have explicit permission to test.
