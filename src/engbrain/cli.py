from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import typer

from engbrain import __version__
from engbrain.config import database_path, initialize_project, load_project
from engbrain.db import database_integrity, fts5_available

app = typer.Typer(help="Local-first episodic engineering memory for coding agents.")


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Show the installed version."),
) -> None:
    if version:
        typer.echo(f"EngBrain {__version__}")
        raise typer.Exit()


@app.command()
def init(
    name: str | None = typer.Option(None, "--name", help="Name for this repository's memory."),
) -> None:
    """Initialize a local EngBrain database in the current Git repository."""
    try:
        project = initialize_project(project_name=name)
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        _fail(str(exc))
    typer.echo(f"Initialized EngBrain for {project.name}")
    typer.echo(f"Repository: {project.repo_root}")
    typer.echo(f"Database: {database_path(project)}")


@app.command()
def doctor() -> None:
    """Check the local runtime, Git repository, database, and FTS5 support."""
    checks: list[tuple[str, bool, str]] = []
    try:
        project = load_project()
        db_path = database_path(project)
        checks.append(("Git repository", True, project.repo_root))
        checks.append(("EngBrain database", db_path.is_file(), str(db_path)))
        checks.append(("SQLite FTS5", fts5_available(db_path), "required for episode search"))
        integrity = database_integrity(db_path)
        checks.append(("Database integrity", integrity == "ok", integrity))
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        checks.append(("Project", False, str(exc)))
    for label, ok, details in checks:
        typer.echo(f"{'OK' if ok else 'FAIL'}  {label}: {details}")
    if any(not ok for _, ok, _ in checks):
        raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Show the active project's memory counts."""
    try:
        project = load_project()
        db_path = database_path(project)
        with sqlite3.connect(db_path) as connection:
            episodes = connection.execute(
                "SELECT COUNT(*) FROM episodes WHERE project_id = ?", (project.id,)
            ).fetchone()[0]
            drafts = connection.execute(
                "SELECT COUNT(*) FROM episodes WHERE project_id = ? AND review_state = 'draft'",
                (project.id,),
            ).fetchone()[0]
        typer.echo(f"Project: {project.name} ({project.id})")
        typer.echo(f"Episodes: {episodes} · drafts awaiting review: {drafts}")
        typer.echo(f"Database: {db_path}")
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))


if __name__ == "__main__":
    app()
