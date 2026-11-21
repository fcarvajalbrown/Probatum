# Probatum — Roadmap

Research fork of CAI. A red-team agent that reports only trace-verified findings, measured on
CAIBench. See `docs/PRD.md` for scope, `docs/adr/` for decisions, `docs/ROADMAP-HISTORY.md` for
finished work.

## Open items

- Phase 0.3 — Install Ollama, pull `qwen2.5-coder:7b`, route via LiteLLM. Status: Not Started.
- Phase 1.3 — Oracle cross-check of the gate against CAIBench ground-truth flags. Status: Not Started.
- Phase 2.1 — Reproducible Cybench before/after harness. Status: Not Started.
- Phase 3.1 — Measurement runs, both backends. Status: Not Started.
- Phase 4.1 — Preprint writeup. Status: Not Started.

## Phase 0 — Baseline and decisions (release 0.1.0)

- 0.1 ADR-0001 gate placement: new guardrail module. Status: Done. Detail:
  `docs/adr/0001-provenance-gate-placement.md`.
- 0.2 Environment and deps. Status: Done. Runs in WSL `kali-linux` (native Windows dead-ends on
  `termios`); Python pinned to 3.12 (3.14 breaks pinned C-extensions); unused `pynput`/`evdev`
  dropped. Clean `uv sync` and `import cai` verified. Open: set `ANTHROPIC_API_KEY` in the kali
  `.env` (Windows copy had an encoding issue); kali has no git push auth, so commits go from the
  Windows checkout.
- 0.3 Install Ollama, pull `qwen2.5-coder:7b` (weights on the WSL ext4 home, 830 GB free; not `D:`,
  20 GB), route via LiteLLM. Status: Not Started.
- 0.4 Repo renamed to Probatum; README, description, 7 topics, default branch set. Status: Done.
  Open: package identity in `pyproject.toml` still `cai-framework`.
- 0.5 Map and document the exact tool-call trace shape in `cai.sdk.agents`. Status: Done. Capture via
  `on_tool_end` (untruncated) into a ledger on `RunContextWrapper.context`; guardrail reads it. Detail:
  `docs/research/trace-shape.md`.
- 0.6 Provenance gate semantics decided (ADR-0002): exact-substring match, flags first, configurable
  default reject, lenient ordering. Status: Done. Detail:
  `docs/adr/0002-provenance-gate-semantics.md`.
- Release gate 0.1.0: CAI runs on both backends; trace shape documented; ADR-0001 Accepted. Open:
  local Ollama backend (0.3) not yet installed.

## Phase 1 — Trace-provenance gate (release 0.2.0)

- 1.1 Provenance gate core: accept a finding only if its proof token appears in real tool output;
  reject model-text-only claims; log every verdict with trace evidence. Status: Done.
  `src/cai/agents/provenance.py` holds the `ProvenanceContext` ledger, the `ProvenanceHooks.on_tool_end`
  capture and the deterministic `judge`; `provenance_guardrail` lives in `src/cai/agents/guardrails.py`.
  Toggles: `CAI_PROVENANCE_GATE` (default off, independent of `CAI_GUARDRAILS`), `CAI_PROVENANCE_MODE`
  (`reject` default, `annotate` keeps the output), `CAI_PROVENANCE_FLAG_PATTERN` (default
  `\b[A-Za-z0-9_]{2,40}\{[^{}\s]{1,400}\}`). Every claimed flag must be backed; a run without a ledger
  fails closed. Verdicts log to the `cai.provenance` logger (warning with ledger snapshot on unverified,
  info on verified). Done check: `tests/agents/test_provenance_gate.py`, 17 tests, end to end through
  `Runner.run`, including a static check that the match path imports no LLM client. Finding: only
  `raw_item["output"]` (what the model reads back) is truncated, not `ToolCallOutputItem.output`; see
  `docs/research/trace-shape.md`. Open for 1.2: agents call `get_security_guardrails()` at import, so the
  env vars must be set before import, and no run path yet passes `ProvenanceHooks()` and a
  `ProvenanceContext` to `Runner.run`, which is why the gate defaults off.
- 1.2 Wire the gate into the red-team run path per ADR-0001. Status: Done. `provenance_run_kwargs()` in
  `src/cai/agents/provenance.py` returns `hooks` and a fresh `ProvenanceContext` per run when
  `CAI_PROVENANCE_GATE` is on, merging existing hooks through `CompositeRunHooks`. It is passed at every
  `Runner.run` / `run_streamed` in `src/cai/cli_headless.py` (streamed, non-streamed, both parallel paths)
  and in `src/cai/parallel_worker.py`. `get_security_guardrails()` now always attaches the provenance
  guardrail, which reads the toggle at run time (verdict `disabled` when off), so import order no longer
  matters. The streamed path records the untruncated result through the same `on_tool_end` (see
  `docs/research/trace-shape.md`). Done check: `tests/agents/test_provenance_wiring.py`, 10 tests, runs the
  real `redteam_agent` with a fake model through `cli_headless._run_non_streamed` and `_run_streamed`: a
  model-only flag is rejected, and a tool-backed flag in the truncated middle of a 14000-char dump is
  accepted. Reverting the CLI wiring fails 3 of the 4 CLI cases. Findings: (a) the streamed CLI swallowed
  `OutputGuardrailTripwireTriggered` in a broad `except Exception` and logged it as a streaming error; it
  now re-raises to the guardrail warning. (b) In streamed mode the final message is printed before the
  output guardrail runs, so a rejected flag still shows on screen; Phase 2 must score from the verdict and
  tripwire, never from console text. (c) The ledger lives for one `Runner.run`: in the interactive REPL each
  turn is a new run, so a flag a tool printed in an earlier turn and claimed in a later one is rejected.
  One-shot benchmark runs are unaffected. (d) Not wired, so they fail closed with the gate on: TUI
  (`src/cai/tui/`), API (`src/cai/api/`), the REPL monoliths, `approach_contest`. (e) `src/cai/caibench/`
  only manages CTF containers; benchmark agent runs go through `cli_headless`. Pre-existing failures,
  unchanged by this work: `tests/agents/test_agent_inference.py` (live API, 401) and 4 tests in
  `tests/cli/test_cli_streaming.py`.
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
