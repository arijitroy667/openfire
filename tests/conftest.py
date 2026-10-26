from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engbrain.config import initialize_project


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit_all(root: Path, message: str = "fixture") -> None:
    git(root, "add", "--all")
    git(root, "commit", "-m", message)


@pytest.fixture
def git_project(tmp_path: Path):
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "EngBrain Tests")
    git(root, "config", "user.email", "engbrain-tests@example.invalid")
    (root / "src").mkdir()
    (root / "src" / "example.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "README.md").write_text("test repository\n", encoding="utf-8")
    commit_all(root, "initial fixture")
    project = initialize_project(root, project_name="Test repository")
    return root, project
