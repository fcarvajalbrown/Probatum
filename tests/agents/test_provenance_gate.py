from __future__ import annotations

import pytest

from cai.agents.provenance import ProvenanceContext, ProvenanceHooks, ToolEvent
from cai.sdk.agents import Agent, RunContextWrapper, Runner
from tests.core.test_responses import get_function_tool, get_function_tool_call, get_text_message
from tests.fake_model import FakeModel

LONG_DUMP = "A" * 7000 + "HTB{inside_the_truncated_middle}" + "B" * 7000


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


@pytest.mark.asyncio
async def test_hook_records_untruncated_tool_output_during_a_run():
    model = FakeModel()
    agent = Agent(name="test", model=model, tools=[get_function_tool("dump", LONG_DUMP)])
    model.add_multiple_turn_outputs(
        [[get_function_tool_call("dump", "")], [get_text_message("done")]]
    )
    ledger = ProvenanceContext()
    result = await Runner.run(agent, input="go", context=ledger, hooks=ProvenanceHooks())
    assert result.final_output == "done"
    assert ledger.tool_events == [ToolEvent(0, "dump", LONG_DUMP)]
    sent_to_model = [
        item.raw_item["output"] for item in result.new_items if item.type == "tool_call_output_item"
    ]
    assert "HTB{inside_the_truncated_middle}" not in sent_to_model[0]
    assert ledger.contains("HTB{inside_the_truncated_middle}")


@pytest.mark.asyncio
async def test_hook_installs_ledger_when_run_has_no_context():
    wrapper = RunContextWrapper(context=None)
    tool = get_function_tool("ls", "flag.txt")
    await ProvenanceHooks().on_tool_end(wrapper, Agent(name="test"), tool, "flag.txt")
    assert wrapper.context.tool_events == [ToolEvent(0, "ls", "flag.txt")]


@pytest.mark.asyncio
async def test_hook_leaves_foreign_context_untouched():
    wrapper = RunContextWrapper(context={"other": "state"})
    tool = get_function_tool("ls", "flag.txt")
    await ProvenanceHooks().on_tool_end(wrapper, Agent(name="test"), tool, "flag.txt")
    assert wrapper.context == {"other": "state"}
