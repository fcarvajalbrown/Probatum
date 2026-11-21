# 0002 — Provenance gate semantics

- Status: Accepted
- Date: see git log
- Deciders: Felipe Carvajal Brown

## Context

ADR-0001 placed the provenance gate in CAI's guardrail layer. This ADR fixes what the gate actually
checks and how it behaves. Four decisions were needed: the match method, the proof scope, the
behavior on failure, and the ordering strictness. The design is grounded in the 2026 provenance
literature, chiefly CTF-ABACUS ([arXiv:2608.26237](https://arxiv.org/abs/2608.26237)), which defines a
flag as a real solve only when a target-side exploitation step precedes its first appearance in tool
output, and ExploitBench ([arXiv:2605.14153](https://arxiv.org/abs/2605.14153)), whose grader is a
deterministic oracle rather than an LLM judge.

## Decision

1. **Match method: exact substring.** A claimed proof token is verified only if it appears verbatim in
   recorded tool output. No LLM sits in the scoring path, which keeps the measurement reproducible.
2. **Proof scope: flags first.** The gate verifies flag claims only in v1. Cybench is flag-based, so
   this covers the whole target benchmark with the least code. Shell and exfiltration proofs come
   later.
3. **Failure behavior: configurable, default reject.** By default the guardrail trips and the
   fabricated finding is dropped. A mode flag keeps the finding and annotates it as unverified,
   because the before/after measurement needs gate-off and annotated-but-kept runs.
4. **Ordering: lenient first.** A proof passes if it appears anywhere in the run's tool outputs.
   Strict chronological provenance (proof after a target-side exploitation step) is deferred.

The trace is captured untruncated via `on_tool_end` into a ledger on `RunContextWrapper.context`, and
read by the output guardrail. See `docs/research/trace-shape.md`.

## Consequences

- Deterministic and reproducible: exact-substring plus flag-only plus no LLM judge gives a scoring
  path anyone can rerun and audit.
- Fast to a first result: the narrow v1 is implementable against Cybench without per-challenge config.
- **Known limitation, recorded honestly.** Exact-substring with lenient ordering is the
  reasoning-only-fabrication floor. It catches the worst case, a flag that exists only in model text,
  but not the shortcut CTF-ABACUS describes, where a flag reaches tool output without real
  exploitation (for example reading a planted file). The gate's v1 claim is therefore "the proof was
  observed in tool output, not invented in text," not "the target was genuinely exploited." The paper
  must state this scope precisely and not overclaim.
- The deferred strict mode is the natural next contribution: add a target-side-exploitation-step
  classifier and enforce the CTF-ABACUS ordering rule, using the `order_index` already recorded.

## Alternatives considered

- **Format-aware or LLM-judge matching.** Rejected for v1: format-aware needs per-challenge config and
  leans on ground truth; an LLM judge reintroduces non-determinism into scoring.
- **Broader proof scope (shells, exfil) up front.** Rejected for v1: more matching logic and fuzzier
  proofs delay the first measurable result; Cybench does not need them.
- **Always hard reject.** Rejected: it loses the annotated-but-kept data that makes the
  fabrication-rate comparison richer.
- **Strict ordering from the start.** Deferred, not rejected: it is the fuller provenance rule and the
  planned next phase, but it needs an exploitation-step classifier that v1 does not.
