from __future__ import annotations

import ast
import inspect
import json
import logging

import pytest

from cai.agents.provenance import ProvenanceContext, ProvenanceHooks, ToolEvent, judge
from cai.sdk.agents import Agent, OutputGuardrailTripwireTriggered, RunContextWrapper, Runner
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


def run_ctf(tool_output: str, claim: str):
    from cai.agents.guardrails import provenance_guardrail

    model = FakeModel()
    agent = Agent(
        name="redteam",
        model=model,
        tools=[get_function_tool("generic_linux_command", tool_output)],
        output_guardrails=[provenance_guardrail],
    )
    model.add_multiple_turn_outputs(
        [[get_function_tool_call("generic_linux_command", "")], [get_text_message(claim)]]
    )
    ledger = ProvenanceContext()
    return ledger, Runner.run(agent, input="solve", context=ledger, hooks=ProvenanceHooks())


@pytest.mark.asyncio
async def test_gate_trips_on_flag_that_appears_only_in_model_text(caplog, monkeypatch):
    monkeypatch.delenv("CAI_PROVENANCE_MODE", raising=False)
    ledger, run = run_ctf("total 0\nindex.html\n", "Solved. The flag is HTB{made_up_by_the_model}")
    with caplog.at_level(logging.INFO, logger="cai.provenance"):
        with pytest.raises(OutputGuardrailTripwireTriggered) as raised:
            await run
    info = raised.value.guardrail_result.output.output_info
    assert info["verdict"] == "unverified"
    assert info["action"] == "blocked"
    assert info["missing"] == ["HTB{made_up_by_the_model}"]
    assert info["ledger"] == [
        {"order_index": 0, "tool_name": "generic_linux_command", "result": "total 0\nindex.html\n"}
    ]
    record = next(r for r in caplog.records if r.name == "cai.provenance")
    assert record.levelno == logging.WARNING
    logged = json.loads(record.getMessage().split("provenance verdict: ", 1)[1])
    assert logged["verdict"] == "unverified"
    assert logged["ledger"] == info["ledger"]


@pytest.mark.asyncio
async def test_gate_passes_flag_present_in_tool_result(caplog, monkeypatch):
    monkeypatch.delenv("CAI_PROVENANCE_MODE", raising=False)
    ledger, run = run_ctf(LONG_DUMP, "Solved. The flag is HTB{inside_the_truncated_middle}")
    with caplog.at_level(logging.INFO, logger="cai.provenance"):
        result = await run
    info = result.output_guardrail_results[0].output.output_info
    assert result.final_output == "Solved. The flag is HTB{inside_the_truncated_middle}"
    assert info["verdict"] == "verified"
    assert info["matched"] == {"HTB{inside_the_truncated_middle}": [0]}
    record = next(r for r in caplog.records if r.name == "cai.provenance")
    assert record.levelno == logging.INFO
    assert '"verdict": "verified"' in record.getMessage()


@pytest.mark.asyncio
async def test_annotate_mode_keeps_unverified_finding(monkeypatch):
    monkeypatch.setenv("CAI_PROVENANCE_MODE", "annotate")
    ledger, run = run_ctf("nothing", "flag{invented}")
    result = await run
    info = result.output_guardrail_results[0].output.output_info
    assert result.final_output == "flag{invented}"
    assert info["verdict"] == "unverified"
    assert info["action"] == "allowed"
    assert not result.output_guardrail_results[0].output.tripwire_triggered


@pytest.mark.asyncio
async def test_output_without_flag_claim_passes(monkeypatch):
    monkeypatch.delenv("CAI_PROVENANCE_MODE", raising=False)
    ledger, run = run_ctf("nothing", "No flag found yet, port 80 is open.")
    result = await run
    assert result.output_guardrail_results[0].output.output_info["verdict"] == "no_claim"


def test_every_claimed_flag_must_be_backed():
    ledger = ProvenanceContext()
    ledger.record("cat", "HTB{real}")
    verdict = judge("HTB{real} and HTB{fake}", ledger, mode="reject")
    assert verdict.verdict == "unverified"
    assert verdict.missing == ["HTB{fake}"]
    assert verdict.tripwire


def test_missing_ledger_fails_closed():
    verdict = judge("HTB{anything}", None, mode="reject")
    assert verdict.verdict == "unverified"
    assert verdict.tripwire


def test_invalid_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("CAI_PROVENANCE_MODE", "maybe")
    with pytest.raises(ValueError):
        judge("HTB{x}", ProvenanceContext())


def test_match_path_contains_no_llm():
    import cai.agents.provenance as provenance
    from cai.agents.guardrails import provenance_guardrail

    tree = ast.parse(inspect.getsource(provenance))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported.isdisjoint({"openai", "litellm", "anthropic", "ollama"})
    assert "Runner" not in inspect.getsource(provenance)
    gate_names = set(provenance_guardrail.guardrail_function.__code__.co_names)
    assert gate_names <= {"judge", "ledger_of", "log_verdict", "GuardrailFunctionOutput", "as_info", "tripwire"}


@pytest.mark.parametrize(
    "guardrails, gate, expected_output",
    [
        ("false", "false", []),
        ("false", "true", ["provenance_gate"]),
        ("true", "false", ["command_execution_guard"]),
        ("true", "true", ["command_execution_guard", "provenance_gate"]),
    ],
)
def test_toggle_controls_provenance_gate_independently(monkeypatch, guardrails, gate, expected_output):
    from cai.agents.guardrails import get_security_guardrails

    monkeypatch.setenv("CAI_GUARDRAILS", guardrails)
    monkeypatch.setenv("CAI_PROVENANCE_GATE", gate)
    _, output_guardrails = get_security_guardrails()
    assert [g.get_name() for g in output_guardrails] == expected_output
