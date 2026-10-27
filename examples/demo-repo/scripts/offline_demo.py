"""Deterministic offline replay of the Claude Code hook contract.

Claude Code is EngBrain's supported hook client. When Claude Code is not
available - on a machine without it, in CI, or for a repeatable screen
recording - this script still exercises the real capture path:

* it runs each fixture's check command twice so it genuinely fails,
* applies the documented one-line fix,
* commits the fix and then runs the check once so it genuinely passes,
* forwards the same JSON payloads Claude Code sends to ``engbrain hook event``.

Every command is executed and its real exit code and output are forwarded, so
the drafts it produces carry real mechanical evidence. The script never invents
an outcome. It does not accept drafts; a person still reviews them with
``engbrain review``.

Usage (from an initialized copy of this demo repository):

    python scripts/offline_demo.py capture pool
    python scripts/offline_demo.py capture all
    python scripts/offline_demo.py drift pool

The commit helpers use ``-c user.name``/``-c user.email`` so the demo works on
a machine with no global Git identity configured.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / ".engbrain" / "engbrain.db"

INCIDENTS: dict[str, dict[str, str]] = {
    "pool": {
        "label": "connection pool exhaustion",
        "command": "python scripts/check_pool.py",
        "script": "scripts/check_pool.py",
        "fix_path": "src/pool_config.py",
        "broken": "MAX_CONNECTIONS = 1\n",
        "fixed": "MAX_CONNECTIONS = 4\n",
        "commit_message": "Fix connection pool capacity",
        "drift_note": "# Capacity raised after the incident (staleness demo).\n",
    },
    "dependency": {
        "label": "dependency pin mismatch",
        "command": "python scripts/check_dependency.py",
        "script": "scripts/check_dependency.py",
        "fix_path": "src/version_policy.py",
        "broken": 'SUPPORTED_URLLIB3 = "1.22.0"\n',
        "fixed": 'SUPPORTED_URLLIB3 = "1.26.18"\n',
        "commit_message": "Align the urllib3 runtime bound with the pin",
        "drift_requirements": "urllib3==2.0.0\n",
    },
    "flag": {
        "label": "empty environment-variable value",
        "command": "python scripts/check_runtime_flag.py",
        "script": "scripts/check_runtime_flag.py",
        "fix_path": "src/runtime_flags.py",
        "broken": "def debug_enabled(value):\n    return value is not None\n",
        "fixed": "def debug_enabled(value):\n    return bool(value)\n",
        "commit_message": "Treat an empty flag value as disabled",
        "drift_note": "# Empty-value handling corrected (staleness demo).\n",
    },
}


def _engbrain():
    try:
        from engbrain.config import load_project
        from engbrain.engine import episode_anchors, list_episodes
        from engbrain.models import ReviewState
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            "EngBrain is not importable in this interpreter. Activate the "
            "environment where EngBrain is installed (for example the project "
            "`.venv`) and run this script again."
        ) from exc
    return load_project, episode_anchors, list_episodes, ReviewState


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def _commit_all(message: str) -> None:
    _git("add", "--all")
    # A line-ending-only difference can make `git status` dirty while `git add`
    # stages nothing. Treat an empty index diff as "already committed".
    if _git("diff", "--cached", "--quiet").returncode == 0:
        return
    result = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "-c",
            "user.name=EngBrain Demo",
            "-c",
            "user.email=demo@example.invalid",
            "commit",
            "-m",
            message,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
        raise SystemExit(f"Could not commit the demo state:\n{detail}")


def _run_check(command: str) -> tuple[int, str]:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, shell=True)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return result.returncode, output


def _send(payload: dict[str, object]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "engbrain", "hook", "event"],
        cwd=ROOT,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"`engbrain hook event` failed:\n{result.stderr.strip()}")


def _failure_payload(command: str, session: str, exit_code: int, output: str) -> dict[str, object]:
    return {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(ROOT),
        "session_id": session,
        "error": f"Exit code {exit_code}\n{output.rstrip()}",
    }


def _success_payload(command: str, session: str, output: str) -> dict[str, object]:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(ROOT),
        "session_id": session,
        "tool_response": {"stdout": output, "stderr": ""},
    }


def _newest_draft_id():
    load_project, _, list_episodes, ReviewState = _engbrain()
    project = load_project(ROOT)
    drafts = list_episodes(project, limit=1, review_state=ReviewState.DRAFT)
    return drafts[0].id if drafts else None


def capture(name: str) -> None:
    incident = INCIDENTS[name]
    fix_path = ROOT / incident["fix_path"]

    # Reset to the failing baseline and commit it, so the captured failure has a
    # stable commit anchor and the change is a clean diff.
    fix_path.write_text(incident["broken"], encoding="utf-8")
    _commit_all(f"Demo baseline: {incident['label']}")

    session = uuid.uuid4().hex
    print(f"Incident: {incident['label']}")
    print(f"Command:  {incident['command']}")

    for attempt in range(1, 3):
        code, output = _run_check(incident["command"])
        if code == 0:
            raise SystemExit("The baseline check unexpectedly passed; aborting.")
        _send(_failure_payload(incident["command"], session, code, output))
        print(f"  failure {attempt}: exit code {code} forwarded to `engbrain hook event`")
        time.sleep(0.02)

    fix_path.write_text(incident["fixed"], encoding="utf-8")
    _commit_all(incident["commit_message"])

    code, output = _run_check(incident["command"])
    if code != 0:
        raise SystemExit("The check still fails after applying the fix; aborting.")
    _send(_success_payload(incident["command"], session, output))
    print(f"  passing run: exit code 0 forwarded to `engbrain hook event`")

    draft_id = _newest_draft_id()
    if draft_id is None:
        raise SystemExit("No draft was detected. Is EngBrain initialized here (`engbrain init`)?")
    print(f"  draft created: {draft_id}")
    print("Review it with `engbrain review`, then `engbrain review accept <id>`.")


def drift(name: str) -> None:
    incident = INCIDENTS[name]
    load_project, episode_anchors, list_episodes, ReviewState = _engbrain()
    project = load_project(ROOT)

    wanted_path = incident["fix_path"]
    wanted_dependency = "urllib3" if name == "dependency" else None
    episode = None
    for candidate in list_episodes(project, limit=100, review_state=ReviewState.ACCEPTED):
        anchors = episode_anchors(project, candidate.id)
        if any(a["kind"] == "path" and a["value"] == wanted_path for a in anchors):
            episode = candidate
            break
        if wanted_dependency and any(
            a["kind"] == "dependency" and a["value"] == wanted_dependency for a in anchors
        ):
            episode = candidate
            break
    if episode is None:
        raise SystemExit(f"Accept the '{incident['label']}' episode before demonstrating drift.")

    def show(heading: str) -> None:
        print(f"\n=== {heading} ===", flush=True)
        subprocess.run(
            [sys.executable, "-m", "engbrain", "episode", "show", episode.id],
            cwd=ROOT,
            check=False,
        )

    show("Staleness before the change")
    if "drift_requirements" in incident:
        (ROOT / "requirements.txt").write_text(incident["drift_requirements"], encoding="utf-8")
        _commit_all("Bump urllib3 to an unsupported major version")
    else:
        path = ROOT / incident["fix_path"]
        path.write_text(path.read_text(encoding="utf-8") + incident["drift_note"], encoding="utf-8")
        _commit_all("Touch an anchored file after the incident")
    show("Staleness after the change")


def main() -> int:
    if not DB_PATH.is_file():
        raise SystemExit("EngBrain is not initialized here. Run `engbrain init` in this folder first.")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    capture_parser = sub.add_parser("capture", help="Reproduce an incident and create a review draft.")
    capture_parser.add_argument("incident", choices=[*INCIDENTS, "all"])
    drift_parser = sub.add_parser("drift", help="Change an anchored file to move a label to drifted or stale.")
    drift_parser.add_argument("incident", choices=list(INCIDENTS))
    args = parser.parse_args()

    if args.action == "capture":
        names = INCIDENTS if args.incident == "all" else [args.incident]
        for name in names:
            capture(name)
            print()
        return 0
    drift(args.incident)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())