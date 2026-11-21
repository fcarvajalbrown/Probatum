from __future__ import annotations

from cai.agents.provenance import ProvenanceContext, ToolEvent


def test_record_assigns_order_and_keeps_result_untruncated():
    ledger = ProvenanceContext()
    long_result = "x" * 20000 + "HTB{deep_in_the_dump}"
    first = ledger.record("generic_linux_command", "ls output")
    second = ledger.record("generic_linux_command", long_result)
    assert first == ToolEvent(0, "generic_linux_command", "ls output")
    assert second.order_index == 1
    assert ledger.tool_events[1].result == long_result
    assert ledger.contains("HTB{deep_in_the_dump}")
    assert not ledger.contains("HTB{never_seen}")


def test_record_stringifies_non_string_results():
    ledger = ProvenanceContext()
    ledger.record("tool", 42)
    assert ledger.tool_events[0].result == "42"
