from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from engbrain.config import database_path
from engbrain.db import transaction
from engbrain.engine import _episode_from_row
from engbrain.models import EpisodeAnchor, EpisodeResult, EpisodeType, Project
from engbrain.redaction import redact_text
from engbrain.signatures import fts_query, normalize_error_signature
from engbrain.staleness import StalenessCache, compute_staleness

RRF_K = 60
MAX_RESULTS = 5


def _normalize_path(root: Path, value: str) -> str:
    candidate_input = Path(value)
    candidate = candidate_input.resolve() if candidate_input.is_absolute() else (root / candidate_input).resolve()
    try:
        relative = candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Search path must be inside this repository: {value}") from exc
    return relative.as_posix()


def _fts_rank_list(
    connection: sqlite3.Connection,
    project: Project,
    query: str,
    *,
    episode_type: EpisodeType | None,
    candidate_limit: int,
) -> list[str]:
    match = fts_query(query)
    if not match:
        return []
    type_clause = " AND e.episode_type = ?" if episode_type else ""
    parameters: list[Any] = [match, project.id]
    if episode_type:
        parameters.append(episode_type.value)
    parameters.append(candidate_limit)
    try:
        rows = connection.execute(
            """SELECT f.episode_id
               FROM episodes_fts AS f JOIN episodes AS e ON e.id = f.episode_id
               WHERE episodes_fts MATCH ? AND e.project_id = ? AND e.review_state = 'accepted'
                 AND e.status != 'superseded'""" + type_clause +
            " ORDER BY bm25(episodes_fts,0,3,2,1,4,1,1,1) LIMIT ?",
            parameters,
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "syntax error" in str(exc).lower() or "malformed" in str(exc).lower():
            return []
        raise
    return [row[0] for row in rows]


def _exact_signature_rank_list(
    connection: sqlite3.Connection,
    project: Project,
    queries: list[str],
    episode_type: EpisodeType | None,
) -> list[str]:
    signatures = list(dict.fromkeys(normalize_error_signature(query) for query in queries))
    signatures = [signature for signature in signatures if signature]
    if not signatures:
        return []
    placeholders = ",".join("?" for _ in signatures)
    type_clause = " AND episode_type = ?" if episode_type else ""
    parameters: list[Any] = [project.id, *signatures]
    if episode_type:
        parameters.append(episode_type.value)
    rows = connection.execute(
        "SELECT id FROM episodes WHERE project_id = ? AND review_state = 'accepted' "
        "AND status != 'superseded' AND error_signature IN (" + placeholders + ")" + type_clause,
        parameters,
    ).fetchall()
    return [row[0] for row in rows]


def _path_anchor_rank_list(
    connection: sqlite3.Connection,
    project: Project,
    paths: list[str],
    episode_type: EpisodeType | None,
) -> list[str]:
    if not paths:
        return []
    placeholders = ",".join("?" for _ in paths)
    type_clause = " AND e.episode_type = ?" if episode_type else ""
    parameters: list[Any] = [project.id, *paths]
    if episode_type:
        parameters.append(episode_type.value)
    rows = connection.execute(
        """SELECT DISTINCT a.episode_id FROM episode_anchors AS a
           JOIN episodes AS e ON e.id = a.episode_id
           WHERE e.project_id = ? AND e.review_state = 'accepted' AND e.status != 'superseded'
             AND a.kind = 'path' AND a.value IN (""" + placeholders + ")" + type_clause,
        parameters,
    ).fetchall()
    return [row[0] for row in rows]


def _rrf(scores: dict[str, float], matches: dict[str, set[str]], rank_list: list[str], source: str) -> None:
    for rank, episode_id in enumerate(rank_list, start=1):
        scores[episode_id] = scores.get(episode_id, 0.0) + 1.0 / (RRF_K + rank)
        matches.setdefault(episode_id, set()).add(source)


def search_memory(
    project: Project,
    queries: list[str],
    *,
    paths: list[str] | None = None,
    episode_type: EpisodeType | None = None,
    limit: int = MAX_RESULTS,
) -> list[EpisodeResult]:
    if not 1 <= len(queries) <= 5:
        raise ValueError("Provide between one and five search queries")
    if any(not query.strip() for query in queries):
        raise ValueError("Search queries cannot be empty")
    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"Search limit must be between 1 and {MAX_RESULTS}")
    root = Path(project.repo_root)
    normalized_paths = list(dict.fromkeys(_normalize_path(root, value) for value in (paths or [])))
    safe_queries = [redact_text(query.strip()) for query in queries]
    scores: dict[str, float] = {}
    match_sources: dict[str, set[str]] = {}
    candidate_limit = 100
    with transaction(database_path(project)) as connection:
        for query in safe_queries:
            _rrf(
                scores,
                match_sources,
                _fts_rank_list(connection, project, query, episode_type=episode_type, candidate_limit=candidate_limit),
                "full_text",
            )
        _rrf(
            scores,
            match_sources,
            _exact_signature_rank_list(connection, project, safe_queries, episode_type),
            "error_signature",
        )
        _rrf(
            scores,
            match_sources,
            _path_anchor_rank_list(connection, project, normalized_paths, episode_type),
            "path_anchor",
        )

        candidate_ids = sorted(scores, key=scores.get, reverse=True)[:25]
        if not candidate_ids:
            connection.execute(
                "INSERT INTO retrievals(id,project_id,queries_json,returned_ids_json,created_at) VALUES(?,?,?,?,?)",
                (
                    uuid4().hex,
                    project.id,
                    json.dumps([redact_text(query) for query in safe_queries]),
                    "[]",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return []
        placeholders = ",".join("?" for _ in candidate_ids)
        rows = connection.execute(
            f"SELECT * FROM episodes WHERE project_id = ? AND review_state = 'accepted' AND id IN ({placeholders})",
            [project.id, *candidate_ids],
        ).fetchall()
        episodes = {row["id"]: _episode_from_row(row) for row in rows}
        anchor_rows = connection.execute(
            f"""SELECT a.* FROM episode_anchors AS a JOIN episodes AS e ON e.id = a.episode_id
                WHERE e.project_id = ? AND a.episode_id IN ({placeholders}) ORDER BY a.kind,a.value""",
            [project.id, *candidate_ids],
        ).fetchall()
        anchors_by_episode: dict[str, list[EpisodeAnchor]] = {}
        for row in anchor_rows:
            anchor = EpisodeAnchor.model_validate(dict(row))
            anchors_by_episode.setdefault(anchor.episode_id, []).append(anchor)

        results: list[tuple[float, EpisodeResult]] = []
        staleness_cache = StalenessCache(Path(project.repo_root))
        for episode_id in candidate_ids:
            episode = episodes.get(episode_id)
            if episode is None:
                continue
            result = compute_staleness(
                project,
                episode,
                cache=staleness_cache,
                anchors=anchors_by_episode.get(episode_id, []),
            )
            adjusted = scores[episode_id]
            source_set = match_sources.get(episode_id, set())
            if "error_signature" in source_set:
                adjusted += 0.002
            if "path_anchor" in source_set:
                adjusted += 0.001
            if episode.status.value == "unverified":
                adjusted -= 0.0005
            if episode.status.value == "superseded":
                adjusted -= 0.002
            if result.staleness.value == "stale":
                adjusted -= 0.0015
            elif result.staleness.value == "drifted":
                adjusted -= 0.0005
            elif result.staleness.value == "unknown":
                adjusted -= 0.0002
            result.match_reason = ", ".join(sorted(source_set)) or "full_text"
            results.append((adjusted, result))
        results.sort(key=lambda item: item[0], reverse=True)
        top_results = [result for _, result in results[:limit]]
        connection.execute(
            "INSERT INTO retrievals(id,project_id,queries_json,returned_ids_json,created_at) VALUES(?,?,?,?,?)",
            (
                uuid4().hex,
                project.id,
                json.dumps([redact_text(query) for query in safe_queries]),
                json.dumps([result.episode.id for result in top_results]),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return top_results
