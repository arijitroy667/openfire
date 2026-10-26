from __future__ import annotations

import sqlite3

from engbrain.config import database_path, load_project
from engbrain.db import SCHEMA_VERSION, transaction


def test_opening_an_existing_project_applies_additive_schema_migrations(git_project):
    root, project = git_project
    with transaction(database_path(project)) as connection:
        connection.execute("DROP TABLE retrieval_feedback")
        connection.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION - 1,))

    loaded = load_project(root)

    assert loaded.id == project.id
    with sqlite3.connect(database_path(project)) as connection:
        version = connection.execute("SELECT MAX(version) FROM schema_meta").fetchone()[0]
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'retrieval_feedback'"
        ).fetchone()
    assert version == SCHEMA_VERSION
    assert table is not None
