from __future__ import annotations

from engbrain.engine import create_episode
from engbrain.models import EpisodeDraft, EpisodeType
from engbrain.staleness import compute_staleness


def anchored_episode(project, **kwargs):
    return create_episode(
        project,
        EpisodeDraft(
            title="Anchored incident",
            episode_type=EpisodeType.DEBUGGING,
            problem="A failure happened in the example source file.",
        ),
        **kwargs,
    )


def test_unchanged_path_is_fresh(git_project):
    _, project = git_project
    episode = anchored_episode(project, paths=["src/example.py"])
    assert compute_staleness(project, episode).staleness.value == "fresh"


def test_uncommitted_path_edit_is_drifted(git_project):
    root, project = git_project
    episode = anchored_episode(project, paths=["src/example.py"])
    (root / "src" / "example.py").write_text("VALUE = 2\n", encoding="utf-8")
    result = compute_staleness(project, episode)
    assert result.staleness.value == "drifted"
    assert any("uncommitted changes" in reason for reason in result.staleness_reasons)


def test_deleted_path_is_stale(git_project):
    root, project = git_project
    episode = anchored_episode(project, paths=["src/example.py"])
    (root / "src" / "example.py").unlink()
    result = compute_staleness(project, episode)
    assert result.staleness.value == "stale"
    assert any("deleted or renamed" in reason for reason in result.staleness_reasons)


def test_twenty_path_commits_are_stale(git_project):
    root, project = git_project
    episode = anchored_episode(project, paths=["src/example.py"])
    for index in range(20):
        (root / "src" / "example.py").write_text(f"VALUE = {index + 2}\n", encoding="utf-8")
        from tests.conftest import commit_all

        commit_all(root, f"update example {index}")
    result = compute_staleness(project, episode)
    assert result.staleness.value == "stale"
    assert any("20 commits touched" in reason for reason in result.staleness_reasons)


def test_dependency_minor_change_drifts_and_major_change_stales(git_project):
    root, project = git_project
    (root / "requirements.txt").write_text("requests==1.2.3\n", encoding="utf-8")
    from tests.conftest import commit_all

    commit_all(root, "pin requests")
    episode = anchored_episode(project, dependencies=["requests"])
    (root / "requirements.txt").write_text("requests==1.3.0\n", encoding="utf-8")
    assert compute_staleness(project, episode).staleness.value == "drifted"
    (root / "requirements.txt").write_text("requests==2.0.0\n", encoding="utf-8")
    assert compute_staleness(project, episode).staleness.value == "stale"


def test_missing_anchor_history_and_no_anchors_are_unknown(git_project):
    _, project = git_project
    no_anchors = anchored_episode(project)
    assert compute_staleness(project, no_anchors).staleness.value == "unknown"
    anchored = anchored_episode(project, paths=["src/example.py"])
    from engbrain.config import database_path
    from engbrain.db import transaction

    with transaction(database_path(project)) as connection:
        connection.execute(
            "UPDATE episode_anchors SET value = ? WHERE episode_id = ? AND kind = 'commit'",
            ("0" * 40, anchored.id),
        )
    result = compute_staleness(project, anchored)
    assert result.staleness.value == "unknown"
    assert any("not an ancestor" in reason for reason in result.staleness_reasons)
