from __future__ import annotations

import pytest

from engbrain.engine import create_episode, get_episode, review_draft, supersede_episode
from engbrain.models import (
    Attempt,
    EpisodeDraft,
    EpisodeOrigin,
    EpisodeType,
    EvidenceKind,
    ReviewState,
)
from engbrain.retrieval import search_memory
from engbrain.signatures import normalize_error_signature


def make_episode(project, *, title, problem, state=ReviewState.ACCEPTED, **kwargs):
    return create_episode(
        project,
        EpisodeDraft(
            title=title,
            episode_type=EpisodeType.DEBUGGING,
            problem=problem,
            review_state=state,
            **kwargs,
        ),
    )


def test_manual_episode_is_accepted_but_unverified(git_project):
    _, project = git_project
    episode = make_episode(project, title="Pool timeout", problem="Connections run out under load.")
    assert episode.review_state == ReviewState.ACCEPTED
    assert episode.status.value == "unverified"
    assert get_episode(project, episode.id).title == episode.title


def test_draft_is_excluded_until_human_acceptance(git_project):
    _, project = git_project
    draft = make_episode(
        project,
        title="Observed failure",
        problem="A command failed before a later pass.",
        state=ReviewState.DRAFT,
        origin=EpisodeOrigin.HOOK,
        evidence_kind=EvidenceKind.MECHANICAL,
        evidence={"exit_codes": [1, 1, 0]},
    )
    assert search_memory(project, ["command failed later pass"]) == []
    accepted = review_draft(project, draft.id, accept=True)
    assert accepted.status.value == "verified"
    assert search_memory(project, ["command failed later pass"])[0].episode.id == draft.id


def test_agent_assertions_never_become_verified(git_project):
    _, project = git_project
    draft = make_episode(
        project,
        title="Agent proposal",
        problem="A cache entry may be stale.",
        state=ReviewState.DRAFT,
        origin=EpisodeOrigin.AGENT,
        evidence_kind=EvidenceKind.ASSERTED,
        evidence={"assertion": "It appears to work."},
    )
    accepted = review_draft(project, draft.id, accept=True)
    assert accepted.status.value == "unverified"


def test_rejected_draft_stays_out_of_search(git_project):
    _, project = git_project
    draft = make_episode(project, title="Bad proposal", problem="A rare migration error.", state=ReviewState.DRAFT)
    rejected = review_draft(project, draft.id, accept=False)
    assert rejected.review_state == ReviewState.REJECTED
    assert search_memory(project, ["rare migration error"]) == []


def test_supersession_removes_old_episode_from_search_and_keeps_link(git_project):
    _, project = git_project
    old = make_episode(project, title="Old connection limit", problem="The pool accepted too few requests.")
    new = make_episode(project, title="New connection limit", problem="The pool capacity was raised safely.")

    updated_old, updated_new = supersede_episode(project, old.id, new.id)

    assert updated_old.status.value == "superseded"
    assert updated_new.supersedes_episode_id == old.id
    assert get_episode(project, old.id).status.value == "superseded"
    assert get_episode(project, new.id).supersedes_episode_id == old.id
    assert [item.episode.id for item in search_memory(project, ["pool capacity connection limit"])] == [new.id]


def test_supersession_requires_distinct_accepted_episodes(git_project):
    _, project = git_project
    accepted = make_episode(project, title="Accepted memory", problem="An accepted pool workaround.")
    draft = make_episode(
        project,
        title="Draft replacement",
        problem="A proposed pool workaround.",
        state=ReviewState.DRAFT,
    )
    with pytest.raises(ValueError, match="accepted first"):
        supersede_episode(project, accepted.id, draft.id)
    with pytest.raises(ValueError, match="cannot supersede itself"):
        supersede_episode(project, accepted.id, accepted.id)


def test_retrieval_fuses_queries_and_path_anchors(git_project):
    root, project = git_project
    pool_file = root / "src" / "pool.py"
    pool_file.write_text("MAX_CONNECTIONS = 4\n", encoding="utf-8")
    target = create_episode(
        project,
        EpisodeDraft(
            title="Connection pool exhaustion",
            episode_type=EpisodeType.DEBUGGING,
            problem="SQLAlchemy callers timed out after every pooled connection was checked out.",
            attempts=[Attempt(description="Increasing the request timeout did not help.")],
        ),
        paths=["src/pool.py"],
    )
    make_episode(project, title="Retry delay", problem="Backoff prevents a request storm after 503 responses.")
    results = search_memory(
        project,
        ["SQLAlchemy pool timeout", "database clients have no free connections"],
        paths=["src/pool.py"],
    )
    assert results[0].episode.id == target.id
    assert "path_anchor" in results[0].match_reason
    assert len(results) <= 5


def test_error_signature_normalizes_paths_numbers_and_hex():
    first = normalize_error_signature(r"FileNotFoundError: C:\service\db.py line 123 0xabc123")
    second = normalize_error_signature(r"FileNotFoundError: D:\work\db.py line 999 0xdef456")
    assert first == second


def test_search_rejects_bad_query_count_and_paths_outside_project(git_project):
    _, project = git_project
    with pytest.raises(ValueError, match="between one and five"):
        search_memory(project, [])
    with pytest.raises(ValueError, match="inside this repository"):
        search_memory(project, ["anything"], paths=["../outside.txt"])
