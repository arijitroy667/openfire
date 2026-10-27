# Full upstream Codex evaluation — bounded v1 results

## Scope and protocol

This run tested the pinned full Click source tree for issue [#2952](https://github.com/pallets/click/issues/2952). The pre-fix base is `5c1239b0116b66492cdd0848144ab3c78a04495a`; the upstream regression tests were overlaid from fix commit `9caedb9206103dfb5465e1916bc2f13b9c10c0e4`. The focused baseline selected 37 cases and failed 15, with 22 passing.

Four Codex sessions completed: models `gpt-6-luna` and `gpt-5.6-terra`, each with and without the EngBrain MCP server. Each session started from a separate full upstream checkout. The same accepted memory corpus was seeded in both memory workspaces. Candidate code was copied into a fresh pre-fix checkout for independent verification; all four sessions preserved the regression test file byte-for-byte.

The user-approved reset credit was not available when this follow-up started (`availableCount: 0`). Codex usage reached 97% during the study, so the run stopped before agent sessions for the second prepared issue. A broad first pilot was excluded because its transcript-capture code failed on Windows console encoding. The balanced runs below use the corrected harness and the focused 37-case selection.

## Results

| Model | Condition | Independent pass | Tool calls | Post-baseline failed test runs | Human label |
| --- | --- | ---: | ---: | ---: | --- |
| `gpt-6-luna` | Control | No | 21 | 6 | Repeated same-method edits after failures; final three whitespace cases still failed |
| `gpt-6-luna` | EngBrain available | Yes | 16 | 1 | One partial fix, then corrected the remaining blank-value handling |
| `gpt-5.6-terra` | Control | Yes | 10 | 1 | Staged fix; corrected two remaining whitespace cases after the first test run |
| `gpt-5.6-terra` | EngBrain available | Yes | 10 | 1 | Same staged fix pattern; no MCP lookup was made |

Control passed 1/2 sessions and memory-available passed 2/2. The only changed outcome was one matched `gpt-6-luna` pair. Median calls were 15.5 for control and 13 for memory-available, based on two sessions per condition. This sample is too small to support an effectiveness claim.

The `gpt-6-luna` control transcript made six failing post-baseline test runs. After the first partial patch left two failures, the agent made five more edits in `Option.resolve_envvar_value`; the final runs continued to fail on three empty or whitespace-only environment values. Its final explanation attributed those values to `CliRunner` behavior, which did not resolve the failures. The other three agents had one intermediate failing run each, then passed independent verification. I label those as ordinary staged corrections, not repeated use of the same failed approach.

EngBrain was actually queried in one of the two memory-available sessions. That search retrieved the Click #3059 usage-synopsis episode, which was unrelated to boolean envvar handling and reported stale anchors; the agent inspected it, then solved this issue from the current upstream tests and code. `gpt-5.6-terra` did not call MCP. This measures memory availability and natural use, not forced retrieval.

## Limits and next step

This is one issue in one upstream project, one run per model-condition cell, and only two models. The second prepared Click issue (#3059) had a verified baseline (two failures, two passes), but its agent run was interrupted before producing a result when Codex quota reached 97%. The broader multi-project, repeated-run evaluation remains open until quota resets or a reset credit becomes available. Do not cite these data as proof that EngBrain improves coding outcomes.

The reproducible setup and runner are in this directory. Default settings define a 16-session study; this bounded run used `--repetitions 1` and stopped after four completed sessions. The raw transcripts and working trees remain in the local temp directory selected by `--runs-dir` and were not committed.
