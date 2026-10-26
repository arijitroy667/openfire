from __future__ import annotations

import pytest

from engbrain.engine import create_episode, get_episode, review_draft
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
