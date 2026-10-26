from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


@contextmanager
def transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(db_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with transaction(db_path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                repo_root TEXT NOT NULL UNIQUE,
                repo_fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                episode_type TEXT NOT NULL,
                problem TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '',
                error_signature TEXT,
                attempts_json TEXT NOT NULL DEFAULT '[]',
                solution_taken TEXT,
                rejected_alternatives_json TEXT NOT NULL DEFAULT '[]',
                verification_text TEXT,
                evidence_kind TEXT NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                review_state TEXT NOT NULL,
                origin TEXT NOT NULL,
                verified_at_sha TEXT,
                supersedes_episode_id TEXT REFERENCES episodes(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS episode_anchors (
                id TEXT PRIMARY KEY,
                episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                version TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL,
                command TEXT NOT NULL,
                normalized_command TEXT NOT NULL,
                exit_code INTEGER,
                output_tail TEXT NOT NULL DEFAULT '',
                cwd TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS retrievals (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                queries_json TEXT NOT NULL,
                returned_ids_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_project ON episodes(project_id);
            CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(project_id, status);
            CREATE INDEX IF NOT EXISTS idx_episodes_review ON episodes(project_id, review_state);
            CREATE INDEX IF NOT EXISTS idx_episodes_signature ON episodes(project_id, error_signature);
            CREATE INDEX IF NOT EXISTS idx_anchors_episode ON episode_anchors(episode_id);
            CREATE INDEX IF NOT EXISTS idx_anchors_value ON episode_anchors(kind, value);
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(project_id, session_id, created_at);
            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                episode_id UNINDEXED,
                title,
                problem,
                context,
                error_signature,
                attempts,
                solution,
                rejected_alternatives,
                tokenize='porter'
            );
            """
        )
        connection.execute("DELETE FROM schema_meta")
        connection.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))


def fts5_available(db_path: Path) -> bool:
    try:
        with transaction(db_path) as connection:
            connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.engbrain_fts_check USING fts5(value)")
            connection.execute("DROP TABLE temp.engbrain_fts_check")
        return True
    except sqlite3.OperationalError:
        return False


def database_integrity(db_path: Path) -> str:
    with transaction(db_path) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"
