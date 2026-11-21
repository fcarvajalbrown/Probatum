# Probatum — Product Requirements

## Vision

A red-team AI agent that reports only what it can prove. Probatum is a research fork of the archived
Cybersecurity AI (CAI) framework. It adds a trace-provenance gate to the offensive agent loop: a
finding is accepted only when its proof (a flag, a shell, exfiltrated data) appears in real tool
output *after* the exploit step, never in model-generated text alone. The measured contribution is
the change in real-versus-fabricated finding rates on a published benchmark, with a reproducible
harness that lets anyone re-run the comparison.

## Problem

Autonomous offensive-security agents fabricate. Published 2026 evidence:

- Trace-level provenance analysis finds only 62–87% of recovered flags are backed by a verified
  exploit trace; the rest are shortcuts or pure model text (arXiv:2608.26237).
- ReproBench reports 45.3% of runs fall back to *simulating* a vulnerability, with only 5.3% of
  CVE–model pairs reproducing a real one (arXiv:2609.34450).
- A controlled scaffold ablation recorded one agent emitting 93 fabricated flags and zero real
  solves.

Existing work addresses this on the evaluation side (benchmarks that detect cheating after the
fact). No open agent integrates provenance checking into its own decision loop and reports a
reproducible before/after on a standard benchmark. That gap is Probatum's scope.

## Scope

### In scope

- A trace-provenance gate wired into the CAI red-team / flag-discrimination path.
- A reproducible CAIBench (Cybench subset) before/after harness measuring: solve rate, fabricated
  finding rate, and provenance-verified finding rate, per run.
- Two backends through LiteLLM: one CVP-approved Anthropic API model (headline) and one local model
  (`qwen2.5-coder:7b` Q4 via Ollama, weights on `D:`) as the on-premise data point.
- A preprint-grade writeup of the method and results, targeting TechRxiv and engrXiv.

### Out of scope

- Blue-team / defensive agents (CAI's `blue_teamer`, DFIR, memory-analysis paths stay untouched).
- New exploit capabilities or new attack tooling beyond what CAI already ships.
- Any commercial or production use. CAI's core (`src/cai/`) is research-use, non-commercial only;
  `src/cai/agents/` is MIT (derived from openai/openai-agents-python). Probatum stays inside the
  research-use licence and cites CAI and CAIBench as the baseline it builds on, not as its own work.
- Command-and-control infrastructure, mass data exfiltration, and ransomware — prohibited and
  excluded regardless of CVP status.

## Architecture

- **Base:** CAI v1.1.5 final source tree, forked at `fcarvajalbrown/cai`.
- **Agent loop:** `cai.sdk.agents` (MIT) carries tool-call results; the provenance trace is read
  here.
- **Gate placement:** to be fixed in ADR-0001 (SDK-level interceptor vs `flag_discriminator`
  wrapper vs new guardrail module). Pending Felipe's decision — not yet chosen.
- **Fabrication surface:** `src/cai/agents/flag_discriminator.py` declares a flag from model output;
  `src/cai/agents/reporter.py` synthesizes findings and already withholds tools to avoid replaying
  chat instructions.
- **Ground truth:** CAIBench `ctf.py` exposes per-challenge flags for an oracle cross-check of the
  gate's own accuracy (does the trace-provenance verdict match the benchmark's ground-truth flag).

## Success criteria

- The gate runs end to end on at least one Cybench challenge: a fabricated flag is rejected, a
  trace-backed flag is accepted, and both decisions are logged with the trace evidence.
- The harness reproduces a full Cybench-subset before/after run from one command, checkpointing to
  disk and resuming on rerun.
- A measured delta exists on both backends: fabricated finding rate falls with the gate on, with the
  provenance-verified rate reported alongside solve rate.
- The results and method are written up to preprint standard (TechRxiv + engrXiv), with CAI and
  CAIBench cited as baseline and the provenance literature cited as the measurement method.

## Research goal

The reproducible before/after on fabrication rate is the preprint's spine. The novelty claimed is
narrow and honest: agent-side integration of a provenance gate plus a reproducible benchmark
comparison, not the invention of exploit verification. A frontier-versus-on-premise contrast
strengthens the result and connects to CAI's own on-premise-models thesis.
