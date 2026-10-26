# Codex agent evaluation

This harness compares Codex on the same isolated bug-fix fixtures in two conditions:

- **Control:** no EngBrain MCP server or seeded memory is available.
- **Memory:** a repository-local EngBrain MCP server exposes 12 accepted target episodes and 30 distractors.

The 72-session evaluation has been run. See [results and limitations](results-20261026.md) for aggregate metrics, MCP retrieval usage, and the independent verification outcomes.

The corpus contains 12 targets and runs each target three times in each condition: 72 independent Codex sessions. Run order alternates by repetition. The four development fixtures are the only split that may be used for tuning; the eight test fixtures should remain held out until the experiment is finalized.

## Corpus provenance and limits

Five fixtures are simplified, dependency-free behavioral reproductions based on closed public GitHub issues:

- [Requests #6071](https://github.com/psf/requests/issues/6071)
- [Requests #4673](https://github.com/psf/requests/issues/4673)
- [pytest #12659](https://github.com/pytest-dev/pytest/issues/12659)
- [Click #1884](https://github.com/pallets/click/issues/1884)
- [Click #3059](https://github.com/pallets/click/issues/3059)

They do not check out or reproduce the full upstream repositories. Seven additional cases are synthetic local incidents. This is a small exploratory benchmark with one Codex model and three repetitions per condition, not a general efficacy claim or a direct replication of a Claude Code experiment.

All tests should fail before repair. Each task repository contains only its fixture source and verifier. The final verifier runs in a fresh directory with the original, immutable test file and the agent's candidate source file. Test modifications are recorded and invalidate the agent's transcript pass metric. The agent is limited to 30 tool calls and 15 minutes by default.

## Requirements

- Linux or WSL2 with Python 3.11+, Git, and Codex CLI authenticated in a shared `CODEX_HOME`.
- The EngBrain source tree available at this repository's `src/`.
- The project runtime dependencies installed for the Python interpreter used by this script.
- An enabled Codex account quota. The script does not reset limits or use API keys.

Example from WSL at the repository root:

```bash
export CODEX_HOME=/mnt/c/Users/ariji/.codex
uv run --python 3.11 python eval/codex/run.py --preflight-only
uv run --python 3.11 python eval/codex/run.py --runs-dir eval/codex/runs/full-20261026
```

Use `--limit 2` for a paired feasibility pilot, `--case requests-6071` to restrict the corpus, or `--runs-dir` to resume a partially completed run. The default model is `gpt-6-luna` at low reasoning effort; both conditions receive exactly the same model and effort. Override these only before starting the experiment and record the settings in any report.

Raw JSONL transcripts, task workspaces, per-run results, and summaries are written beneath the selected runs directory. They are local evaluation artifacts and are excluded from Git. Do not publish transcripts without reviewing them for sensitive content.

## Metrics

- **Success:** final independent verifier passes with original tests.
- **Tool calls to pass:** Codex tool events through the first successful in-session verifier, capped at 30. A trial without one is assigned 30.
- **Repeat failed verifications:** failing verifier calls after the initial baseline failure. This is a command-transcript proxy for repeated failed attempts, not semantic classification of every action.
- **Test integrity:** whether the agent changed an immutable test file in its workspace.

The runner reports development, held-out test, and combined splits separately. It saves per-trial records and raw transcripts locally for audit.
