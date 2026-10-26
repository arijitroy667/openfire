from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import sqlite3

from engbrain.config import database_path
from engbrain.db import transaction
from engbrain.dependencies import dependency_snapshot, normalize_name
from engbrain.engine import _insert_anchors, _save_episode
from engbrain.models import (
    Attempt,
    Episode,
    EpisodeOrigin,
    EpisodeStatus,
    EpisodeType,
    EvidenceKind,
    Project,
    ReviewState,
)
from engbrain.signatures import normalize_error_signature
from engbrain.staleness import current_commit

_EXIT_CODE = re.compile(r"^\s*Exit code\s+(-?\d+)", re.I)


def normalize_command(command: str, repo_root: Path) -> str:
    text = command.strip()
    root = str(repo_root.resolve())
    text = re.sub(re.escape(root), "<repo>", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def exit_code_from_failure(error: str) -> int | None:
    match = _EXIT_CODE.match(error)
    return int(match.group(1)) if match else None


def _tail_2kb(value: str) -> str:
    encoded = value.encode("utf-8", errors="replace")[-2048:]
    return encoded.decode("utf-8", errors="ignore")


def _sensitive_path(value: str) -> bool:
    normalized = value.replace("\\", "/").casefold()
    name = normalized.rsplit("/", 1)[-1]
    if name == ".env" or (name.startswith(".env.") and name not in {".env.example", ".env.sample", ".env.template"}):
        return True
    if name.startswith(("secret", "credential")) or name in {"id_rsa", "id_ed25519"}:
        return True
    return name.endswith((".pem", ".key", ".p12", ".pfx"))


def _git_text(root: Path, arguments: list[str], *, timeout: float = 3.0) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def _changed_paths(root: Path, base_sha: str | None) -> list[str]:
    changed: list[str] = []
    if base_sha:
        changed.extend(_git_text(root, ["diff", "--name-only", "--no-renames", base_sha]).splitlines())
    changed.extend(_git_text(root, ["ls-files", "--others", "--exclude-standard"]).splitlines())
    if not base_sha:
        for line in _git_text(root, ["status", "--porcelain", "--untracked-files=all"]).splitlines():
            if len(line) >= 4:
                changed.append(line[3:])
    safe_paths = []
    for value in dict.fromkeys(item.replace("\\", "/").strip() for item in changed if item.strip()):
        if value.startswith(".engbrain/"):
            continue
        if not _sensitive_path(value):
            safe_paths.append(value)
        if len(safe_paths) == 50:
            break
    return safe_paths


def _diff_summary(root: Path, base_sha: str | None, paths: list[str]) -> str:
    if not base_sha or not paths:
        return "No safe changed file paths were available"
    numstat = _git_text(root, ["diff", "--numstat", base_sha, "--", *paths])
    entries = []
    for line in numstat.splitlines():
        columns = line.split("\t", 2)
        if len(columns) == 3:
            entries.append(f"{columns[2]} (+{columns[0]}/-{columns[1]})")
    if not entries:
        return f"{len(paths)} changed or untracked file(s): " + ", ".join(paths[:10])
    return f"{len(paths)} changed file(s): " + "; ".join(entries[:10])


def _relevant_dependencies(root: Path, text: str) -> list[str]:
    snapshot = dependency_snapshot(root)
    if not snapshot:
        return []
    haystack = normalize_name(text)
    selected = []
    for name in snapshot:
        if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", haystack):
            selected.append(name)
        if len(selected) >= 20:
            break
    return selected


def _episode_from_success(
    connection: sqlite3.Connection,
    project: Project,
    event_id: str,
) -> Episode | None:
    current = connection.execute(
        "SELECT * FROM events WHERE id = ? AND project_id = ?",
        (event_id, project.id),
    ).fetchone()
    if current is None or current["exit_code"] != 0:
        return None
    rows = connection.execute(
        """SELECT * FROM events WHERE project_id = ? AND session_id = ? AND normalized_command = ?
           AND created_at <= ? ORDER BY created_at,id""",
        (project.id, current["session_id"], current["normalized_command"], current["created_at"]),
    ).fetchall()
    current_index = next((index for index, row in enumerate(rows) if row["id"] == event_id), None)
    if current_index is None:
        return None
    prior_rows = rows[:current_index]
    last_success = max(
        (index for index, row in enumerate(prior_rows) if row["exit_code"] == 0),
        default=-1,
    )
    failures = [row for row in prior_rows[last_success + 1 :] if row["exit_code"] not in (None, 0)]
    if len(failures) < 2:
        return None
    first_failure = failures[0]
    detector_id = uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()
    inserted = connection.execute(
        """INSERT OR IGNORE INTO detected_sequences(
            id,project_id,session_id,normalized_command,first_failure_event_id,success_event_id,created_at
        ) VALUES(?,?,?,?,?,?,?)""",
        (
            detector_id,
            project.id,
            current["session_id"],
            current["normalized_command"],
            first_failure["id"],
            event_id,
            created_at,
        ),
    )
    if inserted.rowcount == 0:
        return None

    command = current["command"]
    title_command = re.sub(r"\s+", " ", command).strip()
    attempts = [
        Attempt(
            description=f"Command returned exit code {row['exit_code']}",
            outcome="Failed run observed; raw output remains only in the expiring local event buffer.",
            command=row["command"],
            exit_code=row["exit_code"],
        )
        for row in failures[-20:]
    ]
    attempts.append(
        Attempt(
            description="The same normalized command later returned exit code 0",
            outcome="Passing run observed; this does not prove which edit caused the pass.",
            command=current["command"],
            exit_code=0,
        )
    )
    error_text = "\n".join(row["output_tail"] for row in failures[-3:])
    error_signature = normalize_error_signature(error_text)[:1000] or None
    root = Path(project.repo_root)
    paths = _changed_paths(root, first_failure["commit_sha"])
    evidence = {
        "commands": [row["command"] for row in failures[-20:]] + [current["command"]],
        "exit_codes": [row["exit_code"] for row in failures[-20:]] + [0],
        "diff_summary": _diff_summary(root, first_failure["commit_sha"], paths)[:1500],
        "capture_key": f"{current['session_id']}:{current['normalized_command']}:{first_failure['id']}:{event_id}",
    }
    dependency_text = "\n".join([command, error_text])
    draft = Episode(
        project_id=project.id,
        title=f"Repeated command failure: {title_command[:140]}",
        episode_type=EpisodeType.DEBUGGING,
        problem=f"The command failed repeatedly and later passed: {command[:2000]}",
        context="Captured from Claude Code command-hook events. Event output tails are redacted and remain local.",
        error_signature=error_signature,
        attempts=attempts,
        solution_taken=None,
        verification_text=(
            "The same normalized command later exited successfully. This is mechanical run evidence; "
            "it does not prove a particular edit caused the pass."
        ),
        evidence_kind=EvidenceKind.MECHANICAL,
        evidence=evidence,
        status=EpisodeStatus.UNVERIFIED,
        review_state=ReviewState.DRAFT,
        origin=EpisodeOrigin.HOOK,
    )
    _save_episode(connection, draft)
    _insert_anchors(
        connection,
        project,
        draft,
        paths=paths,
        dependencies=_relevant_dependencies(root, dependency_text),
        captured_commit=current["commit_sha"],
    )
    connection.execute(
        "UPDATE detected_sequences SET episode_id = ? WHERE id = ?",
        (draft.id, detector_id),
    )
    return draft


def record_command_event(
    project: Project,
    *,
    session_id: str,
    command: str,
    normalized_command: str,
    exit_code: int | None,
    output_tail: str,
    cwd: str,
) -> Episode | None:
    root = Path(project.repo_root)
    commit_sha = current_commit(root)
    now = datetime.now(timezone.utc)
    event_id = uuid4().hex
    with transaction(database_path(project)) as connection:
        cutoff = datetime.fromtimestamp(now.timestamp() - 7 * 24 * 60 * 60, timezone.utc).isoformat()
        connection.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))
        connection.execute(
            """INSERT INTO events(
                id,project_id,session_id,command,normalized_command,exit_code,output_tail,cwd,commit_sha,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                event_id,
                project.id,
                session_id,
                command,
                normalized_command,
                exit_code,
                output_tail,
                cwd,
                commit_sha,
                now.isoformat(),
            ),
        )
        return _episode_from_success(connection, project, event_id) if exit_code == 0 else None
