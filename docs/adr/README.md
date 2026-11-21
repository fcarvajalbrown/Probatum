# Architecture Decision Records

MADR-lite. One file per significant decision, numbered `0001-kebab-case-title.md`. Once Accepted, an
ADR is immutable; a change of course gets a new ADR that supersedes the old one.

| # | Title | Status |
|:--|:--|:--|
| 0001 | Provenance gate placement | Pending (needs Felipe's decision before the ADR is written) |

## Pending ADR-0001 — Provenance gate placement

The trace-provenance gate must read tool-call results and veto unverified findings. Where it lives
is an open architectural decision with real trade-offs, to be settled with Felipe before any ADR is
written:

- SDK-level interceptor in `cai.sdk.agents` — sees every tool call, most general, highest blast
  radius into forked SDK code.
- Wrapper around `src/cai/agents/flag_discriminator.py` — smallest change, narrow to the
  flag-claim path, may miss non-flag findings.
- New guardrail module alongside `src/cai/agents/guardrails.py` — fits CAI's existing guardrail
  pattern, needs the trace surfaced to the guardrail layer.
