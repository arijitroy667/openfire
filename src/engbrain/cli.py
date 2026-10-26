from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Literal

import typer

from engbrain import __version__
from engbrain.config import database_path, initialize_project, load_project
from engbrain.db import database_integrity, fts5_available
from engbrain.client_config import claude_code_setup_present, claude_code_status, configure_claude_code
from engbrain.engine import (
    create_episode,
    edit_draft,
    episode_anchors,
    get_episode,
    list_episodes,
    record_retrieval_feedback,
    review_draft,
    supersede_episode,
)
from engbrain.models import Attempt, EpisodeDraft, EpisodeStatus, EpisodeType, ReviewState
from engbrain.staleness import compute_staleness
from engbrain.retrieval import search_memory

app = typer.Typer(
    help="Local-first episodic engineering memory for coding agents.",
    invoke_without_command=True,
)
episode_app = typer.Typer(help="Create and inspect engineering episodes.")
review_app = typer.Typer(help="Review hook-captured and agent-proposed episode drafts.", invoke_without_command=True)
mcp_app = typer.Typer(help="Run the local EngBrain MCP server.")
hook_app = typer.Typer(help="Internal adapters invoked by supported agent hooks.")
app.add_typer(episode_app, name="episode")
app.add_typer(review_app, name="review")
app.add_typer(mcp_app, name="mcp")
app.add_typer(hook_app, name="hook")


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show the installed version."),
) -> None:
    if version:
        typer.echo(f"EngBrain {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def init(
    name: str | None = typer.Option(None, "--name", help="Name for this repository's memory."),
    client: Literal["none", "claude-code"] = typer.Option(
        "none", "--client", help="Optionally register the MCP server and capture hooks."
    ),
) -> None:
    """Initialize a local EngBrain database in the current Git repository."""
    try:
        project = initialize_project(project_name=name)
        if client == "claude-code":
            config_paths = configure_claude_code(project)
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        _fail(str(exc))
    typer.echo(f"Initialized EngBrain for {project.name}")
    typer.echo(f"Repository: {project.repo_root}")
    typer.echo(f"Database: {database_path(project)}")
    if client == "claude-code":
        for path in config_paths:
            typer.echo(f"Claude Code configuration: {path}")


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
        mcp_registered, hooks_registered = claude_code_status(project)
        setup_present = claude_code_setup_present(project)
        if mcp_registered and hooks_registered:
            checks.append(("Claude Code MCP", True, "registered"))
            checks.append(("Claude Code hooks", True, "capture and pre-edit recall registered"))
        elif setup_present:
            checks.append(("Claude Code MCP", mcp_registered, "registered and available" if mcp_registered else "missing or command is not on PATH"))
            checks.append(("Claude Code hooks", hooks_registered, "registered and available" if hooks_registered else "missing or command is not on PATH"))
        else:
            typer.echo("SKIP  Claude Code MCP/hooks: optional; enable with `engbrain init --client claude-code`")
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
        typer.echo(f"Episodes: {episodes} | drafts awaiting review: {drafts}")
        typer.echo(f"Database: {db_path}")
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))


@app.command("eval")
def evaluate_retrieval(
    dataset: Path | None = typer.Option(
        None, "--dataset", help="JSON corpus file; defaults to the bundled synthetic corpus."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the complete metrics as JSON."),
) -> None:
    """Measure Recall@5, MRR, Precision@5, and p95 retrieval latency locally."""
    try:
        from engbrain.evaluation import run_retrieval_evaluation

        result = run_retrieval_evaluation(dataset)
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        _fail(str(exc))
    if json_output:
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
        return
    typer.echo(f"Corpus: {result['dataset']} ({result['corpus_kind']})")
    typer.echo(
        f"Episodes: {result['target_episodes']} targets, {result['distractor_episodes']} distractors; "
        f"queries: {result['query_count']}"
    )
    for query_type, metrics in result["retrieval_metrics"].items():
        typer.echo(
            f"{query_type}: n={metrics['n']} Recall@5={metrics['recall_at_5']:.3f} "
            f"MRR={metrics['mrr']:.3f} Precision@5={metrics['precision_at_5']:.3f}"
        )
    typer.echo(f"Search latency p95: {result['latency_ms']['p95']:.3f} ms")
    if result["notice"]:
        typer.echo(f"Note: {result['notice']}")


@app.command()
def recall(
    queries: list[str] = typer.Option(..., "--query", help="Search phrasing; repeat up to five times."),
    paths: list[str] | None = typer.Option(None, "--path", help="Repository-relative path; repeat as needed."),
    episode_type: EpisodeType | None = typer.Option(None, "--type", help="Filter by episode category."),
    limit: int = typer.Option(5, min=1, max=5, help="Maximum results (hard limit: 5)."),
) -> None:
    """Search accepted episodes with several phrasings and optional file anchors."""
    try:
        results = search_memory(load_project(), queries, paths=paths, episode_type=episode_type, limit=limit)
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))
    if not results:
        typer.echo("No matching accepted episodes.")
        return
    for index, result in enumerate(results, start=1):
        episode = result.episode
        typer.echo(f"{index}. {episode.title} [{episode.id}]")
        typer.echo(
            f"   status={episode.status.value} evidence={episode.evidence_kind.value} "
            f"staleness={result.staleness.value} match={result.match_reason}"
        )
        typer.echo(f"   {episode.problem[:300]}")
        for reason in result.staleness_reasons:
            typer.echo(f"   - {reason}")


@app.command("feedback")
def retrieval_feedback(
    episode_id: str,
    rating: Literal["helpful", "not-helpful"],
) -> None:
    """Store a local helpfulness mark for an episode returned by a recent recall."""
    try:
        result = record_retrieval_feedback(
            load_project(),
            episode_id,
            helpful=rating == "helpful",
        )
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))
    label = "helpful" if result["helpful"] else "not helpful"
    typer.echo(f"Recorded {label} feedback for {episode_id}.")


@mcp_app.command("serve")
def mcp_serve(
    repo_root: Path | None = typer.Option(None, "--root", help="Git repository to scope this server to."),
) -> None:
    """Serve search_episodes, get_episode, and propose_episode over stdio."""
    try:
        project = load_project(repo_root)
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))
    from engbrain.mcp_server import run_server

    run_server(Path(project.repo_root))


@hook_app.command("event")
def hook_event() -> None:
    """Read a Claude Code hook JSON payload from stdin and handle supported events."""
    from engbrain.hooks import handle_stdin

    try:
        response = handle_stdin()
        if isinstance(response, dict):
            typer.echo(json.dumps(response, ensure_ascii=False))
    except Exception:
        # Capture is best-effort and must not interrupt the developer's agent session.
        return


def _display_episode(episode) -> None:
    typer.echo(f"{episode.title} [{episode.id}]")
    typer.echo(f"Type: {episode.episode_type.value} | status: {episode.status.value} | review: {episode.review_state.value}")
    typer.echo(f"Evidence: {episode.evidence_kind.value} | origin: {episode.origin.value}")
    typer.echo(f"Problem: {episode.problem}")
    if episode.context:
        typer.echo(f"Context: {episode.context}")
    if episode.attempts:
        typer.echo("Attempts:")
        for index, attempt in enumerate(episode.attempts, start=1):
            details = attempt.description
            if attempt.outcome:
                details += f" - {attempt.outcome}"
            if attempt.command:
                details += f" (command: {attempt.command}; exit: {attempt.exit_code})"
            typer.echo(f"  {index}. {details}")
    if episode.solution_taken:
        typer.echo(f"Solution: {episode.solution_taken}")
    if episode.supersedes_episode_id:
        typer.echo(f"Supersedes episode: {episode.supersedes_episode_id}")
    if episode.rejected_alternatives:
        typer.echo("Rejected alternatives: " + "; ".join(episode.rejected_alternatives))
    if episode.verification_text:
        typer.echo(f"Verification: {episode.verification_text}")
    if episode.evidence:
        typer.echo("Evidence: " + str(episode.evidence))
    anchors = episode_anchors(load_project(), episode.id)
    if anchors:
        typer.echo("Anchors:")
        for anchor in anchors:
            version = f" ({anchor['version']})" if anchor["version"] else ""
            typer.echo(f"  - {anchor['kind']}: {anchor['value']}{version}")


@episode_app.command("create")
def episode_create(
    title: str | None = typer.Option(None, "--title", help="Short incident title."),
    problem: str | None = typer.Option(None, "--problem", help="Observed problem and symptoms."),
    episode_type: EpisodeType = typer.Option(EpisodeType.DEBUGGING, "--type", help="Episode category."),
    context: str = typer.Option("", "--context", help="Relevant environment or repository context."),
    attempts: list[str] | None = typer.Option(None, "--attempt", help="Attempt text; repeat for multiple attempts."),
    paths: list[str] | None = typer.Option(None, "--path", help="Repository-relative file anchor; repeat as needed."),
    dependencies: list[str] | None = typer.Option(
        None, "--dependency", help="Dependency anchor name or name==version; repeat as needed."
    ),
    solution: str | None = typer.Option(None, "--solution", help="What ultimately worked, if known."),
    verification: str | None = typer.Option(None, "--verification", help="How the result was checked."),
) -> None:
    """Create a human-authored episode without requiring an LLM."""
    try:
        if title is None:
            title = typer.prompt("Title")
        if problem is None:
            problem = typer.prompt("Problem")
        if not attempts and sys.stdin.isatty():
            entered = typer.prompt("Attempt (leave blank to finish)", default="")
            attempts = []
            while entered:
                attempts.append(entered)
                entered = typer.prompt("Another attempt (leave blank to finish)", default="")
        draft = EpisodeDraft(
            title=title,
            episode_type=episode_type,
            problem=problem,
            context=context,
            attempts=[Attempt(description=item) for item in (attempts or [])],
            solution_taken=solution,
            verification_text=verification,
            review_state=ReviewState.ACCEPTED,
        )
        episode = create_episode(load_project(), draft, paths=paths, dependencies=dependencies)
        typer.echo(f"Created {episode.status.value} episode {episode.id}: {episode.title}")
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        _fail(str(exc))


@episode_app.command("list")
def episode_list(
    limit: int = typer.Option(20, min=1, max=100, help="Maximum episodes to show."),
    review_state: ReviewState | None = typer.Option(None, "--review-state", help="Filter by review state."),
    episode_status: EpisodeStatus | None = typer.Option(None, "--status", help="Filter by episode status."),
) -> None:
    """List this repository's episodes."""
    try:
        episodes = list_episodes(load_project(), limit=limit, review_state=review_state, status=episode_status)
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))
    if not episodes:
        typer.echo("No episodes found.")
        return
    for episode in episodes:
        typer.echo(
            f"{episode.id}  {episode.status.value:<10} {episode.review_state.value:<8} "
            f"{episode.episode_type.value:<22} {episode.title}"
        )


@episode_app.command("show")
def episode_show(episode_id: str) -> None:
    """Show an episode's content, evidence, provenance, and anchors."""
    try:
        project = load_project()
        episode = get_episode(project, episode_id)
        _display_episode(episode)
        result = compute_staleness(project, episode)
        typer.echo(f"Staleness: {result.staleness.value}")
        for reason in result.staleness_reasons:
            typer.echo(f"  - {reason}")
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))


@episode_app.command("supersede")
def episode_supersede(
    old_episode_id: str,
    new_episode_id: str = typer.Option(..., "--with", help="Accepted episode that replaces the old one."),
) -> None:
    """Mark an accepted episode as superseded by another accepted episode."""
    try:
        old_episode, new_episode = supersede_episode(load_project(), old_episode_id, new_episode_id)
        typer.echo(f"Superseded {old_episode.id} with {new_episode.id}.")
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))


@review_app.callback()
def review_queue(ctx: typer.Context) -> None:
    """List drafts when called without a review action."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        drafts = list_episodes(load_project(), limit=100, review_state=ReviewState.DRAFT)
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))
    if not drafts:
        typer.echo("No drafts are waiting for review.")
        return
    for episode in drafts:
        typer.echo(f"{episode.id}  {episode.origin.value:<6} {episode.title}")


@review_app.command("accept")
def review_accept(episode_id: str) -> None:
    """Accept a draft; mechanical passing evidence is labeled verified."""
    try:
        episode = review_draft(load_project(), episode_id, accept=True)
        typer.echo(f"Accepted {episode.id} as {episode.status.value}.")
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))


@review_app.command("reject")
def review_reject(episode_id: str) -> None:
    """Reject a draft while keeping its review record locally."""
    try:
        episode = review_draft(load_project(), episode_id, accept=False)
        typer.echo(f"Rejected {episode.id}.")
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))


@review_app.command("edit")
def review_edit(
    episode_id: str,
    title: str | None = typer.Option(None, "--title"),
    problem: str | None = typer.Option(None, "--problem"),
    context: str | None = typer.Option(None, "--context"),
    solution: str | None = typer.Option(None, "--solution"),
    verification: str | None = typer.Option(None, "--verification"),
) -> None:
    """Edit a draft before accepting it."""
    try:
        episode = edit_draft(
            load_project(),
            episode_id,
            {
                "title": title,
                "problem": problem,
                "context": context,
                "solution_taken": solution,
                "verification_text": verification,
            },
        )
        typer.echo(f"Updated draft {episode.id}: {episode.title}")
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(str(exc))


if __name__ == "__main__":
    app()
