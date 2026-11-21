# Probatum — Roadmap

Research fork of CAI. A red-team agent that reports only trace-verified findings, measured on
CAIBench. See `docs/PRD.md` for scope, `docs/adr/` for decisions, `docs/ROADMAP-HISTORY.md` for
finished work.

## Open items

- Phase 0.2 — Get forked CAI running end to end. Status: Blocked. Native Windows fails on
  `termios` (Unix-only), imported transitively even by `cli_headless.py` via
  `cai.repl.commands._parallel_monolith`; Docker-based Cybench needs Linux regardless. Target
  environment is WSL `kali-linux` (pending Felipe's confirmation).
- Phase 1.1 — Provenance gate core. Status: Not Started.
- Phase 2.1 — Reproducible Cybench before/after harness. Status: Not Started.
- Phase 3.1 — Measurement runs, both backends. Status: Not Started.
- Phase 4.1 — Preprint writeup. Status: Not Started.

## Phase 0 — Baseline and decisions (release 0.1.0)

- 0.1 ADR-0001 gate placement: new guardrail module. Status: Done. Detail:
  `docs/adr/0001-provenance-gate-placement.md`.
- 0.2 Install deps (`uv`), set `.env` with CVP-approved `ANTHROPIC_API_KEY`, confirm CAI CLI starts.
- 0.3 Install Ollama, pull `qwen2.5-coder:7b` to `D:` (`OLLAMA_MODELS` on `D:`), route via LiteLLM.
- 0.4 Rename repo and package identity to Probatum (ASCII), keep CAI attribution and licence intact.
- 0.5 Map and document the exact tool-call trace shape in `cai.sdk.agents`. Detail:
  `docs/research/`.
- Release gate 0.1.0: CAI runs on both backends; trace shape documented; ADR-0001 Accepted.

## Phase 1 — Trace-provenance gate (release 0.2.0)

- 1.1 Provenance gate core: accept a finding only if its proof token appears in real tool output
  after the exploit step; reject model-text-only claims. Log every verdict with trace evidence.
- 1.2 Wire the gate into the red-team / flag-discrimination path per ADR-0001.
- 1.3 Oracle cross-check against CAIBench `ctf.py` ground-truth flags: measure the gate's own
  precision and recall on accept/reject.
- Release gate 0.2.0: gate runs end to end on one Cybench challenge; fabricated flag rejected,
  trace-backed flag accepted, both logged; oracle cross-check reported.

## Phase 2 — Reproducible harness (release 0.3.0)

- 2.1 One-command Cybench-subset runner: checkpoints to disk, resumes on rerun with the same
  command, writes per-run solve / fabricated / provenance-verified rates.
- 2.2 On/off toggle holding model and challenges fixed, for a clean before/after.
- 2.3 Result schema and aggregation; no LLM in the scoring path.
- Release gate 0.3.0: a full before/after run reproduces from one command on both backends.

## Phase 3 — Measurement (release 0.4.0)

- 3.1 Frontier run (CVP API org) and local run (`qwen2.5-coder:7b`), gate on vs off, overnight,
  checkpointed.
- 3.2 Record deltas: fabricated finding rate, provenance-verified rate, solve rate, per backend.
- 3.3 Findings to `docs/research/`, committed and pushed before writeup.
- Release gate 0.4.0: a measured, reproduced delta exists on both backends with evidence cited.

## Phase 4 — Preprint (release 1.0.0)

- 4.1 Method and results writeup to preprint standard; CAI and CAIBench cited as baseline, the
  provenance literature as measurement method.
- 4.2 Submit to TechRxiv and engrXiv.
- Release gate 1.0.0: preprint submitted; repo README points to it; results reproducible from the
  harness.
