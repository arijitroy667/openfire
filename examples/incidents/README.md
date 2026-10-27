# Seeded incidents

The PRD's demo needs three deterministic incidents. All three live in
[`examples/demo-repo`](../demo-repo/README.md), where each has a failing check,
a one-line fix, and a matching capture path:

| Incident | Failing check | Anchored file | Fix | Staleness demo |
| --- | --- | --- | --- | --- |
| Connection pool exhaustion | `python scripts/check_pool.py` | `src/pool_config.py` | Raise `MAX_CONNECTIONS` to 4 | Touch the file again: fresh to drifted |
| Dependency pin mismatch | `python scripts/check_dependency.py` | `src/version_policy.py`, `urllib3==1.26.18` | Align the runtime bound with the pin | Bump `urllib3` to `2.0.0`: fresh to stale |
| Empty environment-variable value | `python scripts/check_runtime_flag.py` | `src/runtime_flags.py` | Return `bool(value)` instead of `value is not None` | Touch the file again: fresh to drifted |

`scripts/offline_demo.py` replays the Claude Code hook contract for these
incidents so the capture loop is reproducible without a specific client.

The larger benchmark corpus is separate:

- `eval/codex/` holds the 12 target incidents and 30 distractors used by the
  72-session Codex study.
- `eval/retrieval/` holds the frozen retrieval challenge.
- `eval/upstream/` holds the bounded full-upstream follow-up.

The three demo incidents are deliberately tiny. They demonstrate the product
loop; they are not benchmark evidence.
