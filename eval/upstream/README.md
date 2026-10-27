# Full upstream Codex evaluation

This follow-up evaluates two public Click issues against pinned, full upstream source trees rather than the simplified fixtures used in the 72-session study. Each selected test was taken from the upstream fix commit and overlaid onto its parent (pre-fix) revision. Control runs have no EngBrain server. Memory runs use the repository-local EngBrain MCP server and the same accepted episodes and distractors as the earlier Codex study.

## Run

Requires Python 3.11+, `pytest`, Git, Codex CLI authenticated to an available model, and the EngBrain dependencies installed in the Python interpreter used by Codex. Network access is needed once to fetch the pinned upstream commits.

```powershell
uv run --extra dev python eval/upstream/run.py --preflight-only
uv run --extra dev python eval/upstream/run.py --runs-dir $env:TEMP/engbrain-upstream-eval
```

Default design: two issue tasks, two Codex models (`gpt-6-luna`, `gpt-5.6-terra`), two conditions, and two repetitions (16 sessions). Use `--limit` for a pilot or resume the same `--runs-dir` to skip completed sessions. Raw transcripts and workspaces are written to the selected run directory; review them before sharing because agent output can contain repository text.

The evaluator checks that the upstream regression tests fail at baseline, commits the pristine source snapshot, overlays only the upstream test files, records test hashes, and independently verifies the candidate implementation in a fresh copy with the original tests. It records a human adjudication sheet for repeated failed approaches; labels must be filled after transcript review and are not inferred from tool counts.

This is still exploratory: two issues from one upstream project are not a broad estimate of product efficacy. The design broadens repository scale and model coverage relative to the prior study but does not yet cover multiple projects or human labels across a large incident set.
