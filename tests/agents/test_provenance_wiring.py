from __future__ import annotations

import io
import json
import logging

import pytest
from rich.console import Console

from cai.agents.provenance import (
    CompositeRunHooks,
    ProvenanceContext,
    ProvenanceHooks,
    provenance_run_kwargs,
)
from cai.sdk.agents import OutputGuardrailTripwireTriggered, RunHooks, Runner
from tests.core.test_responses import get_function_tool, get_function_tool_call, get_text_message
from tests.fake_model import FakeModel

REAL_FLAG = "HTB{tool_backed_flag}"
FAKE_FLAG = "HTB{model_only_flag}"
LONG_DUMP = "A" * 7000 + REAL_FLAG + "B" * 7000


class HistoryFakeModel(FakeModel):
    def __init__(self) -> None:
        super().__init__()
        self.model = "fake-model"
        self.message_history: list[dict] = []

    def add_to_message_history(self, message: dict) -> None:
        self.message_history.append(message)


class RecordingHooks(RunHooks):
    def __init__(self) -> None:
        self.tool_results: list[str] = []

    async def on_tool_end(self, context, agent, tool, result) -> None:
        self.tool_results.append(result)


def redteam_with_fake_model(tool_output: str, claim: str):
    from cai.agents.red_teamer import redteam_agent

    model = HistoryFakeModel()
    model.add_multiple_turn_outputs(
        [
            [get_function_tool_call("generic_linux_command", "")],
            [get_text_message(f"Found the flag: {claim}")],
        ]
    )
    return redteam_agent.clone(
        model=model,
        tools=[get_function_tool("generic_linux_command", tool_output)],
    )


def verdicts(caplog) -> list[dict]:
    prefix = "provenance verdict: "
    return [
        json.loads(record.getMessage()[len(prefix):])
        for record in caplog.records
        if record.name == "cai.provenance" and record.getMessage().startswith(prefix)
    ]


def test_run_kwargs_add_nothing_when_gate_off(monkeypatch):
    monkeypatch.setenv("CAI_PROVENANCE_GATE", "false")
    existing = RecordingHooks()
    assert provenance_run_kwargs() == {}
    assert provenance_run_kwargs(existing) == {"hooks": existing}


def test_run_kwargs_give_each_run_a_fresh_ledger(monkeypatch):
    monkeypatch.setenv("CAI_PROVENANCE_GATE", "true")
    first, second = provenance_run_kwargs(), provenance_run_kwargs()
    assert isinstance(first["hooks"], ProvenanceHooks)
    assert isinstance(first["context"], ProvenanceContext)
    assert first["context"] is not second["context"]


def test_run_kwargs_keep_hooks_that_already_record(monkeypatch):
    monkeypatch.setenv("CAI_PROVENANCE_GATE", "true")
    existing = ProvenanceHooks()
    assert provenance_run_kwargs(existing)["hooks"] is existing


@pytest.mark.asyncio
async def test_run_kwargs_merge_with_existing_hooks(monkeypatch):
    monkeypatch.setenv("CAI_PROVENANCE_GATE", "true")
    existing = RecordingHooks()
    kwargs = provenance_run_kwargs(existing)
    assert isinstance(kwargs["hooks"], CompositeRunHooks)
    model = FakeModel()
    model.add_multiple_turn_outputs([[get_function_tool_call("ls", "")], [get_text_message("done")]])
    from cai.sdk.agents import Agent

    agent = Agent(name="test", model=model, tools=[get_function_tool("ls", "flag.txt")])
    await Runner.run(agent, input="go", **kwargs)
    assert existing.tool_results == ["flag.txt"]
    assert kwargs["context"].contains("flag.txt")


@pytest.mark.asyncio
async def test_redteam_agent_reads_toggle_at_run_time_not_import(monkeypatch):
    monkeypatch.setenv("CAI_PROVENANCE_GATE", "false")
    agent = redteam_with_fake_model("nothing here", FAKE_FLAG)
    result = await Runner.run(agent, input="solve", **provenance_run_kwargs())
    assert FAKE_FLAG in result.final_output

    monkeypatch.setenv("CAI_PROVENANCE_GATE", "true")
    agent = redteam_with_fake_model("nothing here", FAKE_FLAG)
    with pytest.raises(OutputGuardrailTripwireTriggered):
        await Runner.run(agent, input="solve", **provenance_run_kwargs())


@pytest.mark.asyncio
async def test_streamed_run_records_untruncated_tool_result(monkeypatch):
    monkeypatch.setenv("CAI_PROVENANCE_GATE", "true")
    agent = redteam_with_fake_model(LONG_DUMP, REAL_FLAG)
    kwargs = provenance_run_kwargs()
    result = Runner.run_streamed(agent, input="solve", **kwargs)
    async for _ in result.stream_events():
        pass
    assert kwargs["context"].tool_events[0].result == LONG_DUMP
    assert REAL_FLAG in result.final_output


@pytest.mark.parametrize("runner_name", ["_run_non_streamed", "_run_streamed"])
@pytest.mark.parametrize(
    "tool_output, claim, expected_verdict, blocked",
    [
        ("uid=0(root)\n/root/flag.txt", FAKE_FLAG, "unverified", True),
        (LONG_DUMP, REAL_FLAG, "verified", False),
    ],
    ids=["fabricated_flag", "tool_backed_flag"],
)
def test_cli_redteam_run_gates_flags(
    monkeypatch, caplog, runner_name, tool_output, claim, expected_verdict, blocked
):
    import cai.cli_headless as cli

    monkeypatch.setenv("CAI_PROVENANCE_GATE", "true")
    monkeypatch.setenv("CAI_PROVENANCE_MODE", "reject")
    warnings: list[OutputGuardrailTripwireTriggered] = []
    monkeypatch.setattr(cli, "_print_guardrail_warning", warnings.append)
    caplog.set_level(logging.INFO, logger="cai.provenance")
    agent = redteam_with_fake_model(tool_output, claim)

    getattr(cli, runner_name)(agent, "solve", Console(file=io.StringIO()), False, None)

    gate_verdicts = [v for v in verdicts(caplog) if v["verdict"] != "no_claim"]
    assert [v["verdict"] for v in gate_verdicts] == [expected_verdict]
    assert gate_verdicts[0]["claimed"] == [claim]
    assert gate_verdicts[0]["action"] == ("blocked" if blocked else "allowed")
    assert len(warnings) == (1 if blocked else 0)
    if blocked:
        assert warnings[0].guardrail_result.guardrail.get_name() == "provenance_gate"
