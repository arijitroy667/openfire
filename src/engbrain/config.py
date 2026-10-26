from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from engbrain.db import initialize_database, transaction
from engbrain.models import Project

APP_DIR = ".engbrain"
DB_NAME = "engbrain.db"


def git_root(start: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(result.stdout.strip()).resolve()


def repository_fingerprint(root: Path) -> str:
    common_dir = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-common-dir"],
        check=False,
        capture_output=True,
        text=True,
        timeout=3,
    )
    basis = str(root).casefold()
    if common_dir.returncode == 0:
        basis = f"{basis}\n{common_dir.stdout.strip()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def normalize_root(root: Path) -> str:
    return str(root.resolve()).casefold()


def ensure_local_database_ignored(root: Path) -> None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", "info/exclude"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"Could not locate Git's local exclude file: {exc}") from exc
    exclude_path = Path(result.stdout.strip())
    if not exclude_path.is_absolute():
        exclude_path = (root / exclude_path).resolve()
    try:
        existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
        lines = {line.strip() for line in existing.splitlines()}
        if "/.engbrain/" not in lines and ".engbrain/" not in lines:
            exclude_path.parent.mkdir(parents=True, exist_ok=True)
            prefix = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
            exclude_path.write_text(existing + prefix + "# EngBrain local memory\n/.engbrain/\n", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not protect local EngBrain data from Git: {exc}") from exc


def initialize_project(start: Path | None = None, *, project_name: str | None = None) -> Project:
    start = (start or Path.cwd()).resolve()
    root = git_root(start)
    if root is None:
        raise ValueError(f"No Git repository found from {start}")
    app_dir = root / APP_DIR
    db_path = app_dir / DB_NAME
    initialize_database(db_path)
    ensure_local_database_ignored(root)
    fingerprint = repository_fingerprint(root)
    normalized = normalize_root(root)
    with transaction(db_path) as connection:
        row = connection.execute(
            "SELECT id, name, repo_root, repo_fingerprint, created_at FROM projects WHERE repo_root = ?",
            (normalized,),
        ).fetchone()
        if row is None:
            project_id = uuid4().hex
            created_at = datetime.now(timezone.utc).isoformat()
            name = project_name or root.name
            connection.execute(
                "INSERT INTO projects(id,name,repo_root,repo_fingerprint,created_at) VALUES(?,?,?,?,?)",
                (project_id, name, normalized, fingerprint, created_at),
            )
            return Project(
                id=project_id,
                name=name,
                repo_root=str(root),
                repo_fingerprint=fingerprint,
                created_at=created_at,
            )
        return Project(
            id=row["id"],
            name=row["name"],
            repo_root=str(root),
            repo_fingerprint=row["repo_fingerprint"],
            created_at=row["created_at"],
        )


def load_project(start: Path | None = None) -> Project:
    start = (start or Path.cwd()).resolve()
    root = git_root(start)
    if root is None:
        raise ValueError(f"No Git repository found from {start}")
    db_path = root / APP_DIR / DB_NAME
    if not db_path.exists():
        raise ValueError("EngBrain is not initialized here. Run `engbrain init` first.")
    with transaction(db_path) as connection:
        row = connection.execute(
            "SELECT id, name, repo_root, repo_fingerprint, created_at FROM projects WHERE repo_root = ?",
            (normalize_root(root),),
        ).fetchone()
    if row is None:
        raise ValueError("This repository has no EngBrain project record. Run `engbrain init` first.")
    return Project(
        id=row["id"],
        name=row["name"],
        repo_root=str(root),
        repo_fingerprint=row["repo_fingerprint"],
        created_at=row["created_at"],
    )


def database_path(project: Project) -> Path:
    return Path(project.repo_root) / APP_DIR / DB_NAME


def config_snapshot(project: Project) -> str:
    return json.dumps(project.model_dump(mode="json"), indent=2)
