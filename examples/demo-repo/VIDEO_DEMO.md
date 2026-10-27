# EngBrain demo video

This recording shows the complete local loop: repeatable failures, a code
change, hook-shaped evidence capture, human review, recall from different
wording, and a staleness label that moves from `fresh` to `drifted` or `stale`.

There are two ways to record it:

- **Path A (recommended): deterministic offline replay.** Real commands are
  executed and their real exit codes and output are forwarded through the same
  JSON payloads Claude Code sends. No client is required, and the result is
  identical on every run.
- **Path B: live Claude Code hooks.** The most authentic demo, but it depends
  on Claude Code being installed and on the hook ordering described below.

Both paths use the same three seeded incidents and the same CLI review and
recall commands.

## Prepare before recording

Run these commands from the EngBrain repository root in PowerShell. Each run
uses a fresh temporary repository.

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

`doctor` should report the repository, database, SQLite FTS5, and database
integrity as OK. Client integrations are optional for Path A.

## Path A: deterministic offline replay

`scripts/offline_demo.py` runs each check twice to fail, applies the documented
fix, commits it, runs the check once to pass, and forwards those real outcomes
to `engbrain hook event` in Claude Code's payload shape. It creates the same
reviewable drafts that the hooks create. It never accepts a draft for you.

Capture all three incidents:

```powershell
python scripts/offline_demo.py capture all
```

Each incident prints its draft id. Review and accept them:

```powershell
engbrain review
$id = (engbrain review | Select-Object -First 1).Split(" ")[0]
engbrain review accept $id
engbrain episode show $id
```

Repeat the two `$id` lines for each draft, or accept them one at a time so the
recording shows the human review step clearly.

Then show recall from different wording:

```powershell
engbrain recall --query "workers cannot get a database connection" --query "pool capacity under concurrency" --path src/pool_config.py
engbrain recall --query "why is urllib3 pinned" --path src/version_policy.py
engbrain recall --query "debug mode turns on with an empty setting" --path src/runtime_flags.py
```

Finally, move a label:

```powershell
python scripts/offline_demo.py drift pool
python scripts/offline_demo.py drift dependency
```

`drift pool` adds one commit touching `src/pool_config.py` and prints the
episode before and after: `fresh` then `drifted` with the reason "1 commit(s)
touched anchored paths since capture". `drift dependency` bumps the pinned
`urllib3` to a new major version and prints `fresh` then `stale` with the reason
"changed major version: 1.26.18 to 2.0.0".

## Path B: live Claude Code hooks

Start Claude Code from the demo repository after `engbrain init --client
claude-code`. For each incident, keep the failing runs inside Claude Code so the
post-tool hooks capture them, then have the agent edit the file.

To make the accepted episode `fresh` rather than immediately `drifted`, commit
the fix before the passing run is captured:

1. Run the check twice inside Claude Code. Both runs fail.
2. Let the agent edit the source file.
3. Commit the fix: `git add -A; git commit -m "Fix ..."`.
4. Run the same check once more inside Claude Code. It passes and the draft is
   created against the fix commit.
5. Review and accept: `engbrain review`, then `engbrain review accept <id>`.

If the passing run happens before the commit, the episode is anchored to the
pre-fix commit and will show `drifted` as soon as you commit. That is honest
behaviour, not a bug; re-capture after committing if you want to start at
`fresh`.

## Suggested 3-minute recording

| Time | What to show | Action and narration |
| --- | --- | --- |
| 0:00–0:15 | Title and one-line pitch | "EngBrain remembers what agents tried, what failed, and what was verified, then flags memory that has gone stale." |
| 0:15–0:35 | `engbrain init` and `engbrain doctor` | Show the local database and passing checks. Keep private home-directory contents off screen. |
| 0:35–1:05 | Incident 1: connection pool | Run `python scripts/offline_demo.py capture pool`. Point out the two failed exit codes and the passing run. |
| 1:05–1:25 | Human review | Run `engbrain review` and `engbrain episode show <id>`. Show the commands, exit codes, diff summary, and `status=verified`. |
| 1:25–1:45 | Incident 2: dependency pin | Capture `dependency`. Show the `urllib3 (1.26.18)` dependency anchor in `episode show`. |
| 1:45–2:05 | Incident 3: environment variable | Capture `flag`. Show that an empty value was the trigger. |
| 2:05–2:30 | Recall with different wording | Run the three `engbrain recall` commands. Show that paraphrased queries plus a path still return the right episode. |
| 2:30–2:55 | Staleness moves | Run `drift pool`, then `drift dependency`. Show `fresh` to `drifted` and `fresh` to `stale` with reasons. |
| 2:55–3:15 | Benchmark table | Run `engbrain eval`, then show `eval/codex/results-20261026.md` (34/36 control vs 36/36 memory, 5 vs 7 median tool calls). |
| 3:15–3:30 | Limits | Say that the sample is small, the public-issue fixtures are simplified, and the Codex study does not measure Claude Code hooks. |

## Recording setup

- **Tool:** OBS Studio (free) or Windows Game Bar (`Win+G`). Capture the
  terminal window only, not the whole desktop.
- **Terminal:** Windows Terminal at 16–18 pt, a dark theme, and a clean prompt
  with the demo directory visible. Increase scrollback so earlier output stays
  on screen.
- **Resolution:** record at 1920×1080 or 1280×720, 30 fps.
- **Audio:** narrate the timeline above. If you do not want to narrate live,
  record the screen first and add a voice-over; the table is the script.
- **Editing:** cut waiting time, keep the command output readable, and add a
  caption for each of the five PRD demo steps.
- **Do not show:** your home directory, `.engbrain/engbrain.db` internals, API
  keys, or unrelated terminal history.

## What the demo proves, and what it does not

It proves the local loop works: real command outcomes create a draft, a person
accepts it, the accepted episode is retrievable from different wording, and its
label changes when the anchored code or dependency changes.

It does not prove that a specific edit caused a pass, that retrieval reduces
failed attempts in general, or that the 72-session Codex result generalises.
The fixtures are deliberately small, and the Codex study used MCP retrieval, not
Claude Code hooks.
