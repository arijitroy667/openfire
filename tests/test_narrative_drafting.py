from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from engbrain.cli import app
from engbrain.config import load_project
from engbrain.engine import list_episodes
from engbrain.models import ReviewState
from engbrain.narrative import EpisodeNarrative, draft_episode_narrative
from engbrain.retrieval import search_memory


class FakeResponses:
    def __init__(self, parsed):
        self.parsed = parsed
        self.call = None

    def parse(self, **kwargs):
        self.call = kwargs
        return SimpleNamespace(output_parsed=self.parsed)


class FakeClient:
    def __init__(self, parsed):
        self.responses = FakeResponses(parsed)


def narrative():
    return EpisodeNarrative(
        title="Pool check failed under four workers",
        problem="Four workers exhaust the one-connection pool.",
        context="The test repository runs four concurrent workers.",
        attempts=["Increasing the request timeout did not help."],
        solution_taken="Raise the pool size to four.",
        rejected_alternatives=["Increasing the timeout"],
        verification_text="The pool check passed after the change.",
    )


def test_openai_adapter_uses_schema_redacted_input_and_no_server_storage():
    client = FakeClient(narrative())

    result = draft_episode_narrative(
        "Pool starved workers. api_key=sk-abcdefghijklmnopqrstuvwxyz123456 and timeout increase failed.",
        model="configured-model",
        client=client,
    )

    assert result.title == "Pool check failed under four workers"
    assert client.responses.call["model"] == "configured-model"
    assert client.responses.call["text_format"] is EpisodeNarrative
    assert client.responses.call["store"] is False
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in client.responses.call["input"]
    assert "[REDACTED]" in client.responses.call["input"]
    assert "Do not infer a root cause" in client.responses.call["instructions"]


def test_openai_adapter_rejects_empty_notes_and_incomplete_responses():
    client = FakeClient(None)
    with pytest.raises(ValueError, match="incident notes"):
        draft_episode_narrative("  ", client=client)

    with pytest.raises(RuntimeError, match="no complete narrative"):
        draft_episode_narrative("Observed a failure.", client=client)


def test_cli_saves_narrative_as_draft_until_human_review(git_project, monkeypatch):
    root, project = git_project
    monkeypatch.chdir(root)
    import engbrain.narrative as narrative_module

    monkeypatch.setattr(narrative_module, "draft_episode_narrative", lambda notes, model=None: narrative())
    result = CliRunner().invoke(
        app,
        ["episode", "draft", "--notes", "Workers failed; a timeout retry did not help.", "--path", "src/example.py"],
    )

    assert result.exit_code == 0, result.output
    assert "Created LLM-assisted review draft" in result.stdout
    episodes = list_episodes(project, review_state=ReviewState.DRAFT)
    assert len(episodes) == 1
    assert episodes[0].origin.value == "manual"
    assert episodes[0].status.value == "unverified"
    assert search_memory(project, ["pool check failed under four workers"]) == []
