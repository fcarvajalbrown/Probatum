# 0001 — Provenance gate placement

- Status: Accepted
- Date: see git log
- Deciders: Felipe Carvajal Brown

## Context

Probatum's contribution is a trace-provenance gate: the red-team agent must not report a finding
whose proof (flag, shell, exfiltrated data) failed to appear in real tool output after the exploit
step. The gate has to read tool-call results, compare a claimed proof token against them, and veto
claims backed only by model-generated text. It must toggle cleanly on and off so the CAIBench
before/after holds the model and challenges fixed while varying only the gate.

CAI already ships a guardrail layer. `src/cai/agents/guardrails.py` defines `@input_guardrail` and
`@output_guardrail` functions returning `GuardrailFunctionOutput` with a tripwire, and the red-team
agent wires them in through `get_security_guardrails`. Three placements were considered: a new
guardrail module, a wrapper around `flag_discriminator.py`, and an interceptor in the forked
`cai.sdk.agents` SDK.

## Decision

Implement the gate as a provenance guardrail in CAI's existing guardrail layer, alongside
`src/cai/agents/guardrails.py`, surfaced to the red-team agent through `get_security_guardrails`. It
runs as an output guardrail: it inspects the agent's claimed finding against the run's tool-call
trace and trips when the proof token is absent from real tool output. Enabling or disabling the
guardrail in `get_security_guardrails` is the on/off toggle for the before/after measurement.

## Consequences

- Idiomatic: reuses CAI's guardrail pattern and the wiring the red-team agent already has, so the
  change is small and localized.
- Clean toggle: including or excluding the guardrail is the before/after switch, with no change to
  model, prompts, or challenges.
- Known risk: an output guardrail does not natively receive the full tool-call trace. Surfacing the
  trace to the guardrail (via the run context) is required work and is tracked as roadmap item 0.5
  (map the trace shape in `cai.sdk.agents`) before 1.1.
- Narrower than an SDK interceptor: findings that never pass through the guarded agent's output are
  not covered. Acceptable for the Cybench scope, where findings surface as agent-reported flags.

## Alternatives considered

- **Wrapper around `flag_discriminator.py`.** Smallest change, but guards only the flag-claim path
  and would miss non-flag findings (shells, exfil). Rejected as too narrow for a general gate.
- **Interceptor in `cai.sdk.agents`.** Most general, catches every finding type centrally, but
  highest blast radius into forked SDK code and hardest to keep in sync with upstream. Rejected as
  disproportionate to the Cybench scope; revisit only if non-agent-reported findings must be gated.
