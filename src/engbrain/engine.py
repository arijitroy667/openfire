from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from engbrain.config import database_path
from engbrain.db import transaction
from engbrain.dependencies import dependency_snapshot, parse_dependency_anchor
from engbrain.models import (
    Episode,
    EpisodeDraft,
    EpisodeResult,
    EpisodeStatus,
    Project,
    ReviewState,
    utc_now,
)
from engbrain.redaction import redact_text
from engbrain.signatures import normalize_error_signature
from engbrain.staleness import current_commit


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    return value


def _has_successful_mechanical_evidence(evidence: dict[str, Any]) -> bool:
    """A passed command is observed evidence, not proof that a specific edit caused it."""
    exit_codes = evidence.get("exit_codes")
    if isinstance(exit_codes, list) and any(code == 0 for code in exit_codes):
        return True
    verification = evidence.get("verification")
    return isinstance(verification, dict) and verification.get("exit_code") == 0


def _save_episode(connection: sqlite3.Connection, episode: Episode) -> None:
    connection.execute(
        """INSERT INTO episodes(
            id,project_id,title,episode_type,problem,context,error_signature,attempts_json,
            solution_taken,rejected_alternatives_json,verification_text,evidence_kind,evidence_json,
            status,review_state,origin,verified_at_sha,supersedes_episode_id,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title, episode_type=excluded.episode_type, problem=excluded.problem,
            context=excluded.context, error_signature=excluded.error_signature,
            attempts_json=excluded.attempts_json, solution_taken=excluded.solution_taken,
            rejected_alternatives_json=excluded.rejected_alternatives_json,
            verification_text=excluded.verification_text, evidence_kind=excluded.evidence_kind,
            evidence_json=excluded.evidence_json, status=excluded.status,
            review_state=excluded.review_state, origin=excluded.origin,
            verified_at_sha=excluded.verified_at_sha,
            supersedes_episode_id=excluded.supersedes_episode_id, updated_at=excluded.updated_at""",
        (
            episode.id,
            episode.project_id,
            episode.title,
            episode.episode_type.value,
            episode.problem,
            episode.context,
            episode.error_signature,
            json.dumps([attempt.model_dump(mode="json") for attempt in episode.attempts]),
            episode.solution_taken,
            json.dumps(episode.rejected_alternatives),
            episode.verification_text,
            episode.evidence_kind.value,
            json.dumps(episode.evidence),
            episode.status.value,
            episode.review_state.value,
            episode.origin.value,
            episode.verified_at_sha,
            episode.supersedes_episode_id,
            episode.created_at.isoformat(),
            episode.updated_at.isoformat(),
        ),
    )
    connection.execute("DELETE FROM episodes_fts WHERE episode_id = ?", (episode.id,))
    if episode.review_state == ReviewState.ACCEPTED and episode.status != EpisodeStatus.SUPERSEDED:
        attempts = " ".join(
            f"{attempt.description} {attempt.outcome or ''} {attempt.command or ''}"
            for attempt in episode.attempts
        )
        connection.execute(
            """INSERT INTO episodes_fts(
                episode_id,title,problem,context,error_signature,attempts,solution,rejected_alternatives
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                episode.id,
                episode.title,
                episode.problem,
                episode.context,
                episode.error_signature or "",
                attempts,
                episode.solution_taken or "",
                " ".join(episode.rejected_alternatives),
            ),
        )


def _episode_from_row(row: sqlite3.Row) -> Episode:
    raw = dict(row)
    raw["attempts"] = json.loads(raw.pop("attempts_json"))
    raw["rejected_alternatives"] = json.loads(raw.pop("rejected_alternatives_json"))
    raw["evidence"] = json.loads(raw.pop("evidence_json"))
    raw["episode_type"] = raw.pop("episode_type")
    raw["created_at"] = raw["created_at"]
    raw["updated_at"] = raw["updated_at"]
    return Episode.model_validate(raw)


def _insert_anchors(
    connection: sqlite3.Connection,
    project: Project,
    episode: Episode,
    *,
    paths: list[str] | None = None,
    dependencies: list[str] | None = None,
    captured_commit: str | None = None,
) -> None:
    root = Path(project.repo_root).resolve()
    if captured_commit:
        connection.execute(
            "INSERT OR IGNORE INTO episode_anchors(id,episode_id,kind,value,version) VALUES(?,?,?,?,NULL)",
            (uuid4().hex, episode.id, "commit", captured_commit),
        )
    for value in paths or []:
        candidate = (root / value).resolve()
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"Path anchor must be inside the repository: {value}") from exc
        if not relative or relative == ".":
            raise ValueError("A path anchor must name a file inside the repository")
        connection.execute(
            "INSERT OR IGNORE INTO episode_anchors(id,episode_id,kind,value,version) VALUES(?,?,?,?,NULL)",
            (uuid4().hex, episode.id, "path", relative),
        )
    snapshot = dependency_snapshot(root)
    for value in dependencies or []:
        name, version = parse_dependency_anchor(value, snapshot)
        connection.execute(
            "INSERT OR IGNORE INTO episode_anchors(id,episode_id,kind,value,version) VALUES(?,?,?,?,?)",
            (uuid4().hex, episode.id, "dependency", name, version),
        )


def _query_episode(connection: sqlite3.Connection, project: Project, episode_id: str) -> Episode:
    row = connection.execute(
        "SELECT * FROM episodes WHERE id = ? AND project_id = ?",
        (episode_id, project.id),
    ).fetchone()
    if row is None:
        raise ValueError(f"Episode {episode_id!r} was not found in this project")
    return _episode_from_row(row)


def create_episode(
    project: Project,
    draft: EpisodeDraft,
    *,
    paths: list[str] | None = None,
    dependencies: list[str] | None = None,
) -> Episode:
    safe_data = _redact_value(draft.model_dump(mode="json"))
    safe_data["status"] = EpisodeStatus.UNVERIFIED.value
    if safe_data.get("error_signature"):
        safe_data["error_signature"] = normalize_error_signature(safe_data["error_signature"])
    captured_commit = current_commit(Path(project.repo_root))
    episode = Episode.model_validate({**safe_data, "project_id": project.id})
    with transaction(database_path(project)) as connection:
        _save_episode(connection, episode)
        _insert_anchors(connection, project, episode, paths=paths, dependencies=dependencies, captured_commit=captured_commit)
    return episode


def get_episode(project: Project, episode_id: str) -> Episode:
    with transaction(database_path(project)) as connection:
        return _query_episode(connection, project, episode_id)


def supersede_episode(project: Project, old_episode_id: str, new_episode_id: str) -> tuple[Episode, Episode]:
    """Mark an accepted old episode superseded by a different accepted episode."""
    if old_episode_id == new_episode_id:
        raise ValueError("An episode cannot supersede itself")
    with transaction(database_path(project)) as connection:
        old_episode = _query_episode(connection, project, old_episode_id)
        new_episode = _query_episode(connection, project, new_episode_id)
        if old_episode.review_state != ReviewState.ACCEPTED:
            raise ValueError("Only accepted episodes can be superseded")
        if new_episode.review_state != ReviewState.ACCEPTED:
            raise ValueError("The superseding episode must be accepted first")
        if old_episode.status == EpisodeStatus.SUPERSEDED:
            raise ValueError("The old episode is already superseded")
        if new_episode.status == EpisodeStatus.SUPERSEDED:
            raise ValueError("A superseded episode cannot supersede another episode")
        if new_episode.supersedes_episode_id is not None:
            raise ValueError("The new episode already supersedes another episode")
        updated_old = old_episode.model_copy(
            update={"status": EpisodeStatus.SUPERSEDED, "updated_at": utc_now()}
        )
        updated_new = new_episode.model_copy(
            update={"supersedes_episode_id": old_episode.id, "updated_at": utc_now()}
        )
        _save_episode(connection, updated_new)
        _save_episode(connection, updated_old)
        return updated_old, updated_new


def record_retrieval_feedback(project: Project, episode_id: str, *, helpful: bool) -> dict[str, Any]:
    """Attach or update a local helpfulness mark for the latest retrieval containing an episode."""
    with transaction(database_path(project)) as connection:
        _query_episode(connection, project, episode_id)
        retrieval_id: str | None = None
        rows = connection.execute(
            "SELECT id,returned_ids_json FROM retrievals WHERE project_id = ? ORDER BY created_at DESC LIMIT 500",
            (project.id,),
        ).fetchall()
        for row in rows:
            try:
                returned_ids = json.loads(row["returned_ids_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if episode_id in returned_ids:
                retrieval_id = row["id"]
                break
        if retrieval_id is None:
            raise ValueError("That episode was not returned by a recent search in this project")
        feedback_id = uuid4().hex
        created_at = utc_now().isoformat()
        connection.execute(
            """INSERT INTO retrieval_feedback(id,project_id,retrieval_id,episode_id,helpful,created_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(retrieval_id,episode_id)
               DO UPDATE SET helpful=excluded.helpful,created_at=excluded.created_at""",
            (feedback_id, project.id, retrieval_id, episode_id, int(helpful), created_at),
        )
        row = connection.execute(
            "SELECT id,retrieval_id,episode_id,helpful,created_at FROM retrieval_feedback "
            "WHERE project_id = ? AND retrieval_id = ? AND episode_id = ?",
            (project.id, retrieval_id, episode_id),
        ).fetchone()
        return {
            "id": row["id"],
            "retrieval_id": row["retrieval_id"],
            "episode_id": row["episode_id"],
            "helpful": bool(row["helpful"]),
            "created_at": row["created_at"],
        }


def list_episodes(
    project: Project,
    *,
    limit: int = 20,
    review_state: ReviewState | None = None,
    status: EpisodeStatus | None = None,
) -> list[Episode]:
    limit = max(1, min(limit, 100))
    clauses = ["project_id = ?"]
    parameters: list[Any] = [project.id]
    if review_state is not None:
        clauses.append("review_state = ?")
        parameters.append(review_state.value)
    if status is not None:
        clauses.append("status = ?")
        parameters.append(status.value)
    parameters.append(limit)
    query = f"SELECT * FROM episodes WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?"
    with transaction(database_path(project)) as connection:
        return [_episode_from_row(row) for row in connection.execute(query, parameters).fetchall()]


def review_draft(project: Project, episode_id: str, *, accept: bool) -> Episode:
    with transaction(database_path(project)) as connection:
        episode = _query_episode(connection, project, episode_id)
        if episode.review_state != ReviewState.DRAFT:
            raise ValueError("Only draft episodes can be accepted or rejected")
        new_state = ReviewState.ACCEPTED if accept else ReviewState.REJECTED
        status = EpisodeStatus.UNVERIFIED
        if accept and episode.evidence_kind.value == "mechanical" and _has_successful_mechanical_evidence(episode.evidence):
            status = EpisodeStatus.VERIFIED
        commit = connection.execute(
            "SELECT value FROM episode_anchors WHERE episode_id = ? AND kind = 'commit' ORDER BY rowid LIMIT 1",
            (episode.id,),
        ).fetchone()
        updated = episode.model_copy(
            update={
                "review_state": new_state,
                "status": status,
                "verified_at_sha": commit["value"] if status == EpisodeStatus.VERIFIED and commit else None,
                "updated_at": utc_now(),
            }
        )
        _save_episode(connection, updated)
        return updated


def edit_draft(project: Project, episode_id: str, changes: dict[str, Any]) -> Episode:
    allowed = {
        "title",
        "episode_type",
        "problem",
        "context",
        "attempts",
        "solution_taken",
        "rejected_alternatives",
        "verification_text",
    }
    changes = {key: value for key, value in changes.items() if key in allowed and value is not None}
    if not changes:
        raise ValueError("Provide at least one field to edit")
    changes = _redact_value(changes)
    with transaction(database_path(project)) as connection:
        episode = _query_episode(connection, project, episode_id)
        if episode.review_state != ReviewState.DRAFT:
            raise ValueError("Only draft episodes can be edited; create a new episode for accepted memory")
        existing = episode.model_dump(mode="json")
        merged = {**existing, **changes, "updated_at": datetime.now(timezone.utc).isoformat()}
        updated = Episode.model_validate(merged)
        _save_episode(connection, updated)
        return updated


def episode_anchors(project: Project, episode_id: str) -> list[dict[str, Any]]:
    with transaction(database_path(project)) as connection:
        _query_episode(connection, project, episode_id)
        rows = connection.execute(
            "SELECT id,episode_id,kind,value,version FROM episode_anchors WHERE episode_id = ? ORDER BY kind,value",
            (episode_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def save_anchor(project: Project, episode_id: str, kind: str, value: str, version: str | None = None) -> str:
    anchor_id = uuid4().hex
    with transaction(database_path(project)) as connection:
        _query_episode(connection, project, episode_id)
        connection.execute(
            "INSERT INTO episode_anchors(id,episode_id,kind,value,version) VALUES(?,?,?,?,?)",
            (anchor_id, episode_id, kind, value, version),
        )
    return anchor_id
