# Tool-call trace shape in `cai.sdk.agents`

Reference for the provenance gate (ADR-0001, ADR-0002). It records where real tool output lives in
the agent run, how to capture it untruncated, and where the gate reads it. Grounded in the SDK source
as of CAI v1.1.5.

## Where tool output lives

A run produces a list of `RunItem` (`src/cai/sdk/agents/items.py`). The relevant types:

- `MessageOutputItem` wraps `ResponseOutputMessage`: model-generated text. A proof token that appears
  only here is a fabricated or reasoning-only claim.
- `ToolCallItem` wraps the tool call the model requested.
- `ToolCallOutputItem` wraps the tool result. Its `.output` field holds what the tool actually
  returned. This is the ground truth the gate checks against.

`RunResult` (`result.py`) exposes the full list as `new_items: list[RunItem]`, alongside
`output_guardrail_results` and `final_output`. So the trace is reachable post-run.

## Truncation caveat

What the model reads back is truncated; `ToolCallOutputItem.output` is not. For function tools,
`_run_impl.py:888-893` builds `ToolCallOutputItem(output=result, raw_item=tool_call_output_item(call,
truncate_output(result)))`: `.output` keeps the full result, while `raw_item["output"]`, the copy sent
to the model, goes through `truncate_output(max_length=10000)` (`_run_impl.py:206`). Past 10000 chars
that keeps the first 5000 and the last 5000 and drops the middle. Verified by
`tests/agents/test_provenance_gate.py`, which runs a tool returning a flag in the middle of a 14000-char
dump: the flag survives in the ledger and is absent from `raw_item["output"]`.

The gate still cannot use `new_items`, because the output guardrail does not receive them (see below),
so it reads the ledger. The match source must never be `raw_item["output"]`.

## Capture point: `on_tool_end`

`RunHooks.on_tool_end` and `AgentHooks.on_tool_end` (`lifecycle.py:46`, `:97`) are called after each
tool runs, with the full, untruncated result:

```
async def on_tool_end(self, context: RunContextWrapper[TContext], agent: Agent[TContext],
                      tool: Tool, result: str) -> None
```

`_run_impl.py:738` invokes it as `hooks.on_tool_end(context_wrapper, agent, func_tool, result)`, where
`result` is the tool return before `truncate_output` is applied. This is the correct place to record
provenance: it sees every tool, the untruncated output, and the run context.

## Ledger home: `RunContextWrapper.context`

`RunContextWrapper` (`run_context.py:12`) wraps the `context` object passed to `Runner.run()`. It is
the per-run carrier available to both hooks and guardrails. The provenance ledger lives here:

- A context dataclass holds `tool_events: list[ToolEvent]`, each `ToolEvent` being
  `(order_index, tool_name, result)`.
- The `on_tool_end` hook appends one `ToolEvent` per call, in execution order.

## Gate read point: output guardrail

`OutputGuardrail.run(context, agent, agent_output)` (`guardrail.py:159`) receives only the final
`agent_output` and the `context` wrapper, not the item list. That is why the ledger must live in the
context: the gate reads `context.context.tool_events`, extracts the claimed proof token from
`agent_output`, and checks membership.

Flow:

1. `on_tool_end` records each untruncated tool result into `context.context.tool_events`.
2. The provenance guardrail (an `@output_guardrail` added via `get_security_guardrails`, per ADR-0001)
   runs on the agent's final output.
3. It extracts the claimed proof (a flag string, per ADR-0002 scope) and tests exact-substring
   membership against the concatenated `tool_events` results.
4. Absent from every tool result means the proof exists only in model text. The guardrail trips
   (configurable, default reject, per ADR-0002), logging the claim and the failing ledger snapshot.

## Ordering, deferred

`order_index` on each `ToolEvent` is recorded now but unused by the v1 lenient rule (proof present in
any tool output). It is the hook for the strict CTF-ABACUS rule (ADR-0002): a proof is a real solve
only if a target-side exploitation step precedes its first appearance. That needs a classifier for
"exploitation step" and is a later phase.
