from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from cai.sdk.agents import Agent, RunContextWrapper, RunHooks
from cai.sdk.agents.tool import Tool

logger = logging.getLogger("cai.provenance")

DEFAULT_FLAG_PATTERN = r"\b[A-Za-z0-9_]{2,40}\{[^{}\s]{1,400}\}"
REJECT = "reject"
ANNOTATE = "annotate"


class ToolEvent(NamedTuple):
    order_index: int
    tool_name: str
    result: str


@dataclass
class ProvenanceContext:
    tool_events: list[ToolEvent] = field(default_factory=list)

    def record(self, tool_name: str, result: object) -> ToolEvent:
        event = ToolEvent(len(self.tool_events), tool_name, str(result))
        self.tool_events.append(event)
        return event

    def contains(self, token: str) -> bool:
        return any(token in event.result for event in self.tool_events)


def ledger_of(wrapper: RunContextWrapper[Any], create: bool = False) -> ProvenanceContext | None:
    if isinstance(wrapper.context, ProvenanceContext):
        return wrapper.context
    if wrapper.context is None and create:
        wrapper.context = ProvenanceContext()
        return wrapper.context
    return None


class ProvenanceHooks(RunHooks[Any]):
    async def on_tool_end(
        self,
        context: RunContextWrapper[Any],
        agent: Agent[Any],
        tool: Tool,
        result: Any,
    ) -> None:
        ledger = ledger_of(context, create=True)
        if ledger is None:
            logger.warning(
                "provenance ledger unavailable: run context is %s, not ProvenanceContext",
                type(context.context).__name__,
            )
            return
        ledger.record(tool.name, result)


class CompositeRunHooks(RunHooks[Any]):
    def __init__(self, *hooks: RunHooks[Any]) -> None:
        self.hooks = hooks

    async def on_agent_start(self, context: RunContextWrapper[Any], agent: Agent[Any]) -> None:
        for hook in self.hooks:
            await hook.on_agent_start(context, agent)

    async def on_agent_end(
        self, context: RunContextWrapper[Any], agent: Agent[Any], output: Any
    ) -> None:
        for hook in self.hooks:
            await hook.on_agent_end(context, agent, output)

    async def on_handoff(
        self, context: RunContextWrapper[Any], from_agent: Agent[Any], to_agent: Agent[Any]
    ) -> None:
        for hook in self.hooks:
            await hook.on_handoff(context, from_agent, to_agent)

    async def on_tool_start(
        self, context: RunContextWrapper[Any], agent: Agent[Any], tool: Tool
    ) -> None:
        for hook in self.hooks:
            await hook.on_tool_start(context, agent, tool)

    async def on_tool_end(
        self, context: RunContextWrapper[Any], agent: Agent[Any], tool: Tool, result: Any
    ) -> None:
        for hook in self.hooks:
            await hook.on_tool_end(context, agent, tool, result)


def gate_enabled() -> bool:
    return os.getenv("CAI_PROVENANCE_GATE", "false").strip().lower() in ("true", "1", "yes", "on")


def has_provenance_hooks(hooks: RunHooks[Any] | None) -> bool:
    if isinstance(hooks, ProvenanceHooks):
        return True
    if isinstance(hooks, CompositeRunHooks):
        return any(has_provenance_hooks(hook) for hook in hooks.hooks)
    return False


def provenance_run_kwargs(hooks: RunHooks[Any] | None = None) -> dict[str, Any]:
    if not gate_enabled():
        return {"hooks": hooks} if hooks is not None else {}
    if hooks is None:
        merged: RunHooks[Any] = ProvenanceHooks()
    elif has_provenance_hooks(hooks):
        merged = hooks
    else:
        merged = CompositeRunHooks(hooks, ProvenanceHooks())
    return {"hooks": merged, "context": ProvenanceContext()}


@dataclass
class ProvenanceVerdict:
    verdict: str
    mode: str
    claimed: list[str]
    missing: list[str]
    matched: dict[str, list[int]]
    ledger: list[dict[str, Any]] | None

    @property
    def tripwire(self) -> bool:
        return self.verdict == "unverified" and self.mode == REJECT

    def as_info(self) -> dict[str, Any]:
        return {
            "guardrail": "provenance_gate",
            "verdict": self.verdict,
            "mode": self.mode,
            "action": "blocked" if self.tripwire else "allowed",
            "claimed": self.claimed,
            "missing": self.missing,
            "matched": self.matched,
            "ledger": self.ledger,
        }


def flag_pattern() -> re.Pattern[str]:
    return re.compile(os.getenv("CAI_PROVENANCE_FLAG_PATTERN", DEFAULT_FLAG_PATTERN))


def gate_mode() -> str:
    mode = os.getenv("CAI_PROVENANCE_MODE", REJECT).strip().lower()
    if mode not in (REJECT, ANNOTATE):
        raise ValueError(f"CAI_PROVENANCE_MODE must be {REJECT!r} or {ANNOTATE!r}, got {mode!r}")
    return mode


def output_text(output: Any) -> str:
    if hasattr(output, "model_dump_json"):
        return output.model_dump_json()
    return str(output)


def extract_flags(text: str, pattern: re.Pattern[str] | None = None) -> list[str]:
    found = (pattern or flag_pattern()).findall(text)
    return list(dict.fromkeys(found))


def judge(output: Any, ledger: ProvenanceContext | None, mode: str | None = None) -> ProvenanceVerdict:
    mode = mode or gate_mode()
    claimed = extract_flags(output_text(output))
    events = ledger.tool_events if ledger is not None else []
    matched = {
        flag: [event.order_index for event in events if flag in event.result] for flag in claimed
    }
    missing = [flag for flag, indices in matched.items() if not indices]
    if not claimed:
        verdict = "no_claim"
    elif missing:
        verdict = "unverified"
    else:
        verdict = "verified"
    snapshot = [event._asdict() for event in events] if ledger is not None else None
    return ProvenanceVerdict(
        verdict=verdict,
        mode=mode,
        claimed=claimed,
        missing=missing,
        matched={flag: indices for flag, indices in matched.items() if indices},
        ledger=snapshot if verdict == "unverified" else None,
    )


def log_verdict(result: ProvenanceVerdict) -> None:
    if result.verdict == "no_claim":
        logger.debug("provenance verdict: %s", json.dumps(result.as_info()))
    elif result.verdict == "verified":
        logger.info("provenance verdict: %s", json.dumps(result.as_info()))
    else:
        logger.warning("provenance verdict: %s", json.dumps(result.as_info()))
