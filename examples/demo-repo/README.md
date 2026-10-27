# Seeded incident demo

This tiny project reproduces the three incidents from the PRD demo. Each one has
a check that fails, a one-line fix, and an anchor that the staleness engine can
watch.

| Incident | Check | Failing state | Fix |
| --- | --- | --- | --- |
| Connection pool exhaustion | `python scripts/check_pool.py` | `MAX_CONNECTIONS = 1` | Raise it to `4` in `src/pool_config.py` |
| Dependency pin mismatch | `python scripts/check_dependency.py` | `SUPPORTED_URLLIB3 = "1.22.0"` but `requirements.txt` pins `1.26.18` | Align the runtime bound in `src/version_policy.py` |
| Empty environment-variable value | `python scripts/check_runtime_flag.py` | `debug_enabled("")` returns true | Return `bool(value)` in `src/runtime_flags.py` |

For the timed screen-recording plan and both recording paths, see
[VIDEO_DEMO.md](VIDEO_DEMO.md).

## Quick start

```powershell
$EngBrainRoot = (Get-Location).Path
uv sync --extra dev
$env:PATH = "$EngBrainRoot\.venv\Scripts;$env:PATH"

$DemoRoot = Join-Path $env:TEMP ("engbrain-demo-" + [guid]::NewGuid().ToString("N"))
Copy-Item -Recurse -LiteralPath (Join-Path $EngBrainRoot "examples\demo-repo") -Destination $DemoRoot
Set-Location $DemoRoot
git init
git add .
git -c user.name="Demo" -c user.email="demo@example.invalid" commit -m "demo fixture"
engbrain init
engbrain doctor
```

## Capture and review

Without a coding client, replay the hook contract deterministically:

```powershell
python scripts/offline_demo.py capture all
engbrain review
```

Accept a draft after inspecting it:

```powershell
engbrain review accept <id>
engbrain episode show <id>
```

Then demonstrate retrieval and staleness:

```powershell
engbrain recall --query "workers cannot get a database connection" --path src/pool_config.py
python scripts/offline_demo.py drift pool
python scripts/offline_demo.py drift dependency
```

With Claude Code, run the checks inside the agent instead so its hooks capture
them. The full sequence, including the ordering that keeps an accepted episode
`fresh`, is in [VIDEO_DEMO.md](VIDEO_DEMO.md).

## What is captured

The hook path stores the command, exit code, a redacted 2 KB output tail, the
changed-file diff summary, and the commit at the passing run. The draft is
searchable only after a person accepts it. A fail-then-pass sequence is
mechanical evidence that the outcome changed; it does not prove which edit
caused the pass. Hooks never store a full terminal transcript.
