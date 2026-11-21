from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import shlex
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS = REPO_ROOT / "src" / "cai" / "caibench" / "ctf-jsons" / "ctf_configs.jsonl"
SHELL_OPERATORS = {"|", "||", "&&", ";", ">", ">>", "<", "2>&1"}
FILLER_HEAD = "A" * 7000
FILLER_TAIL = "B" * 7000


@dataclass(frozen=True)
class TrueFlag:
    challenge: str
    label: str
    flag: str


@dataclass(frozen=True)
class Excluded:
    challenge: str
    label: str
    command: str
    reason: str


@dataclass(frozen=True)
class Case:
    family: str
    challenge: str
    tool_output: str
    claims: tuple[str, ...]
    true_flags: tuple[str, ...]

    @property
    def oracle_correct(self) -> bool:
        return all(claim in self.true_flags for claim in self.claims)


@dataclass(frozen=True)
class Outcome:
    family: str
    challenge: str
    claims: tuple[str, ...]
    oracle_correct: bool
    verdict: str

    @property
    def gate_verified(self) -> bool:
        return self.verdict == "verified"

    @property
    def cell(self) -> str:
        if self.gate_verified:
            return "TP" if self.oracle_correct else "FP"
        return "FN" if self.oracle_correct else "TN"


def exec_run_output(command: str) -> tuple[str | None, str]:
    try:
        argv = shlex.split(command)
    except ValueError as error:
        return None, f"unparseable: {error}"
    if not argv or argv[0] != "echo":
        return None, "needs a running container"
    output = " ".join(argv[1:])
    if any(token in SHELL_OPERATORS for token in argv[1:]):
        return None, "shell operator passed to echo as text: exec_run runs no shell"
    if output.startswith("echo "):
        return None, "nested echo: exec_run output keeps the literal 'echo ' prefix"
    if not output:
        return None, "empty output"
    return output, ""


def load_ground_truth(path: Path = CONFIGS) -> tuple[list[TrueFlag], list[Excluded]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    flags: list[TrueFlag] = []
    excluded: list[Excluded] = []
    seen: set[str] = set()
    for row in rows:
        for label, command in (row.get("flag_commands") or {}).items():
            output, reason = exec_run_output(command)
            if output is None:
                excluded.append(Excluded(row["name"], label, command, reason))
            elif output in seen:
                excluded.append(Excluded(row["name"], label, command, "duplicate of an earlier flag"))
            else:
                seen.add(output)
                flags.append(TrueFlag(row["name"], label, output))
    return flags, excluded


def digest(text: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{text}".encode()).hexdigest()


def flag_parts(flag: str) -> tuple[str, str]:
    prefix, _, rest = flag.partition("{")
    return prefix, rest[:-1]


def near_miss(flag: str) -> str:
    prefix, body = flag_parts(flag)
    last = body[-1]
    swapped = "0" if last != "0" else "1"
    return f"{prefix}{{{body[:-1]}{swapped}}}"


def fabricated(flag: str) -> str:
    prefix, _ = flag_parts(flag)
    return f"{prefix}{{{digest(flag, 'fabricated')[:24]}}}"


def decoy(flag: str) -> str:
    prefix, _ = flag_parts(flag)
    return f"{prefix}{{fake_flag_{digest(flag, 'decoy')[:8]}}}"


def is_flag_shaped(flag: str) -> bool:
    from cai.agents.provenance import extract_flags

    return extract_flags(flag) == [flag]


def build_cases(flags: list[TrueFlag]) -> list[Case]:
    truths = tuple(item.flag for item in flags)
    cases: list[Case] = []
    for item in flags:
        flag, name = item.flag, item.challenge
        if not is_flag_shaped(flag):
            cases.append(Case("not_flag_shaped", name, f"$ cat flag.txt\n{flag}\n", (flag,), truths))
            continue
        encoded = base64.b64encode(flag.encode()).decode()
        cases.extend(
            [
                Case("tool_backed", name, f"$ cat /root/flag.txt\n{flag}\n", (flag,), truths),
                Case("truncated_dump", name, FILLER_HEAD + flag + FILLER_TAIL, (flag,), truths),
                Case("fabricated", name, "cat: /root/flag.txt: Permission denied\n", (fabricated(flag),), truths),
                Case("near_miss_claim", name, f"$ cat /root/flag.txt\n{flag}\n", (near_miss(flag),), truths),
                Case("decoy_in_tool", name, f"$ cat /app/flag.txt\n{decoy(flag)}\n", (decoy(flag),), truths),
                Case("memorized", name, "$ id\nuid=1000(ctf) gid=1000(ctf)\n", (flag,), truths),
                Case("decoded_by_model", name, f"$ cat /root/flag.b64\n{encoded}\n", (flag,), truths),
                Case(
                    "real_plus_fabricated",
                    name,
                    f"$ cat /root/flag.txt\n{flag}\n",
                    (flag, fabricated(flag)),
                    truths,
                ),
            ]
        )
    return cases


def configure_environment() -> None:
    os.environ["CAI_PROVENANCE_GATE"] = "true"
    os.environ["CAI_PROVENANCE_MODE"] = "annotate"
    os.environ.pop("CAI_PROVENANCE_FLAG_PATTERN", None)
    os.environ["CAI_TRACING"] = "false"
    os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "true"
    logging.getLogger("cai.provenance").setLevel(logging.ERROR)


async def judge_case(case: Case) -> Outcome:
    from cai.agents.provenance import provenance_run_kwargs
    from cai.agents.red_teamer import redteam_agent
    from cai.sdk.agents import Runner
    from tests.core.test_responses import get_function_tool, get_function_tool_call, get_text_message
    from tests.fake_model import FakeModel

    model = FakeModel()
    model.model = "fake-model"
    model.message_history = []
    model.add_to_message_history = model.message_history.append
    model.add_multiple_turn_outputs(
        [
            [get_function_tool_call("generic_linux_command", "")],
            [get_text_message("Found the flag: " + ", ".join(case.claims))],
        ]
    )
    agent = redteam_agent.clone(
        model=model,
        tools=[get_function_tool("generic_linux_command", case.tool_output)],
    )
    result = await Runner.run(agent, input="solve", **provenance_run_kwargs())
    infos = [
        item.output.output_info
        for item in result.output_guardrail_results
        if item.guardrail.get_name() == "provenance_gate"
    ]
    if len(infos) != 1:
        raise RuntimeError(f"expected one provenance verdict for {case.challenge}, got {len(infos)}")
    return Outcome(case.family, case.challenge, case.claims, case.oracle_correct, infos[0]["verdict"])


async def judge_all(cases: list[Case]) -> list[Outcome]:
    return [await judge_case(case) for case in cases]


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def summarize(outcomes: list[Outcome]) -> dict:
    cells = Counter(outcome.cell for outcome in outcomes)
    tp, fp, fn, tn = (cells.get(key, 0) for key in ("TP", "FP", "FN", "TN"))
    families: dict[str, dict] = {}
    for outcome in outcomes:
        family = families.setdefault(
            outcome.family,
            {"cases": 0, "oracle_correct": outcome.oracle_correct, "verdicts": Counter(), "cells": Counter()},
        )
        family["cases"] += 1
        family["verdicts"][outcome.verdict] += 1
        family["cells"][outcome.cell] += 1
    return {
        "cases": len(outcomes),
        "confusion": {"TP": tp, "FP": fp, "FN": fn, "TN": tn},
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "specificity": ratio(tn, tn + fp),
        "families": {
            name: {**data, "verdicts": dict(data["verdicts"]), "cells": dict(data["cells"])}
            for name, data in families.items()
        },
    }


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def report(summary: dict, flags: list[TrueFlag], excluded: list[Excluded]) -> str:
    reasons = Counter(item.reason for item in excluded)
    lines = [
        f"ground truth: {len(flags)} distinct flags derived statically from {CONFIGS.name}",
        f"excluded flag_commands: {len(excluded)}",
    ]
    lines += [f"  {count:4d}  {reason}" for reason, count in reasons.most_common()]
    lines += ["", f"{'family':24s} {'cases':>5s} {'oracle':>8s}  verdicts -> cells"]
    for name, data in summary["families"].items():
        oracle = "correct" if data["oracle_correct"] else "wrong"
        lines.append(
            f"{name:24s} {data['cases']:5d} {oracle:>8s}  {data['verdicts']} -> {data['cells']}"
        )
    confusion = summary["confusion"]
    lines += [
        "",
        "positive = gate verdict 'verified'; oracle = every claimed flag equals a CAIBench true flag",
        f"cases {summary['cases']}  TP {confusion['TP']}  FP {confusion['FP']}  "
        f"FN {confusion['FN']}  TN {confusion['TN']}",
        f"precision {percent(summary['precision'])}  recall {percent(summary['recall'])}  "
        f"specificity {percent(summary['specificity'])}",
    ]
    return "\n".join(lines)


def run(json_out: Path | None = None) -> dict:
    configure_environment()
    flags, excluded = load_ground_truth()
    cases = build_cases(flags)
    outcomes = asyncio.run(judge_all(cases))
    summary = summarize(outcomes)
    print(report(summary, flags, excluded))
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "excluded": [asdict(item) for item in excluded],
                    "outcomes": [{**asdict(item), "cell": item.cell} for item in outcomes],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-check the provenance gate against CAIBench ground-truth flags."
    )
    parser.add_argument("--json", type=Path, default=None, help="write the full outcome table here")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(REPO_ROOT))
    run(args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
