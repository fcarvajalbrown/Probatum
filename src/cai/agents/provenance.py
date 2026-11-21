from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple


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
