from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from cai.sdk.agents import Agent, RunContextWrapper, RunHooks
from cai.sdk.agents.tool import Tool

logger = logging.getLogger("cai.provenance")


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
