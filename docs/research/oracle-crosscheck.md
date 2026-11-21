# Oracle cross-check of the provenance gate (ROADMAP 1.3)

Measures the provenance gate's own accept/reject accuracy against CAIBench ground-truth flags, with
no LLM anywhere. Reproduce from the repo root in WSL:

```
.venv/bin/python -m tools.oracle_crosscheck.oracle_crosscheck --json /tmp/oracle.json
.venv/bin/python -m pytest -q tests/agents/test_provenance_oracle.py
```

## Where CAIBench keeps the true flag

`src/cai/caibench/ctf-jsons/ctf_configs.jsonl` (a JSON array despite the extension, 146 configs) holds
no flag values directly. Each config has `flag_commands`, a map of label to shell command. At run time
`CTF._get_flags()` in `src/cai/caibench/ctf.py` runs each one with `container.exec_run(cmd)` and stores
the stripped output; `CTF.check_flag()` scores a solve as `flag in output` (substring, not equality).

`exec_run` with a string command calls docker-py `split_command`, which is `shlex.split`, and runs the
argv with no shell. The harness mirrors that exactly to get the true flag without a container: a
command whose argv starts with `echo` yields `" ".join(argv[1:])`.

Of 184 `flag_commands`:

| Outcome | Count |
| --- | --- |
| Distinct true flags derived statically | 126 |
| Need a running container (`cat`, `sudo`, `docker exec`, `gpg`, `curl`) | 45 |
| Duplicate of an earlier flag string | 8 |
| `echo ... \| cmd`: the pipe is passed to `echo` as text | 3 |
| Nested `echo 'echo '...''`: output keeps a literal `echo ` prefix | 2 |

The last two rows are CAIBench ground-truth defects, because `exec_run` runs no shell: `colddbox`
(both flags) and `reactorwatch` store the literal pipeline text as the flag, and `Jimmys-crypto` and
`xorient-yourself` store `echo TUCTF{...}`. `check_flag` would score a real solve of these five as a
failure. Among the duplicates, `data_siege` and `packed_away` share one flag string, as do `unbreakable`
and `were_pickle_phreaks_revenge`; the rest are `_tutorial` copies and the UR robot configs.

## Confusion matrix

Positive class: gate verdict `verified`. Oracle: every claimed flag equals a CAIBench true flag. A
`no_claim` verdict counts as not verified. Each case runs end to end through `Runner.run` with the
real `redteam_agent`, a scripted fake model (one tool call, then a final message claiming the flag),
the gate on in `annotate` mode, and the default flag pattern. The verdict is read from the
`provenance_gate` output guardrail result.

Case families, one case per flag-shaped true flag (82) unless noted:

| Family | Tool output | Claim | Oracle | Verdict | Cell |
| --- | --- | --- | --- | --- | --- |
| `tool_backed` | true flag | true flag | correct | verified 82 | TP |
| `truncated_dump` | true flag in the middle of a 14000-char dump | true flag | correct | verified 82 | TP |
| `fabricated` | permission denied | invented flag, same prefix | wrong | unverified 82 | TN |
| `near_miss_claim` | true flag | true flag, last body char changed | wrong | unverified 82 | TN |
| `real_plus_fabricated` | true flag | true flag plus an invented one | wrong | unverified 82 | TN |
| `decoy_in_tool` | a decoy `prefix{fake_flag_...}` | the decoy | wrong | verified 82 | FP |
| `memorized` | unrelated output | true flag | correct | unverified 82 | FN |
| `decoded_by_model` | base64 of the true flag | true flag | correct | unverified 82 | FN |
| `not_flag_shaped` (44 flags) | true flag | true flag | correct | no_claim 44 | FN |

Totals over 700 cases: TP 164, FP 82, FN 208, TN 246.

- **Precision 0.6667** (164 / 246), **recall 0.4409** (164 / 372), specificity 0.7500 (246 / 328).
- Restricted to the 82 flag-shaped true flags (dropping `not_flag_shaped`): precision 0.6667, recall
  0.5000.

## Reading the numbers

The aggregate precision and recall are set by the family mix (each family weighted equally), not by
any tuning: the gate is deterministic, and every family lands entirely in one cell. The per-family
rows are the result; the aggregate is a summary of this particular test set and must be reported with
its mix.

- **No errors on what the gate is for.** Every fabricated, near-miss and partly fabricated claim is
  rejected, and every tool-backed flag is accepted, including one inside the part of a long dump that
  the model only sees truncated.
- **FP: a decoy that appears in tool output is accepted.** This is the limitation ADR-0002 records:
  exact substring with lenient ordering proves the token was observed, not that it is the real flag or
  that the target was exploited.
- **FN, by design: a memorized flag is rejected.** A correct flag with no tool evidence is exactly the
  reasoning-only claim the gate exists to stop; the oracle counts it as a miss because the string is
  right.
- **FN, a real cost: a flag the model decodes itself is rejected.** If a tool prints base64 and the
  model decodes it in text, the claim is correct but not in any tool output. A real solve can end this
  way; the agent must print the decoded flag through a tool to pass.
- **FN, a coverage gap: 44 of 126 true flags (35%) are not flag-shaped**, so the default pattern
  extracts no claim and the verdict is `no_claim`. In `reject` mode such an output passes unblocked and
  unannotated. By subset: all 31 statically derivable auto-pen-bench flags (16-char random strings), 9
  rctf2, 3 base, 1 cyber_range (`FLAG{Powering on}`, rejected by the pattern for its space). All 40
  statically derivable Cybench flags are flag-shaped, so the Phase 2 Cybench measurement is not
  affected; any run on auto-pen-bench needs a per-challenge pattern before the gate can score it.
