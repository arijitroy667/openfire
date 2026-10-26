from __future__ import annotations

import asyncio
from pathlib import Path

from mcp import Client

from engbrain.config import database_path
from engbrain.db import transaction
from engbrain.engine import get_episode, review_draft
from engbrain.hooks import handle_hook_payload
from engbrain.mcp_server import create_server
from engbrain.retrieval import search_memory


def _payload(root: Path, event_name: str, error: str = ""):
    payload = {
        "hook_event_name": event_name,
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/test_pool.py"},
        "cwd": str(root),
        "session_id": "test-session",
    }
    if event_name == "PostToolUseFailure":
        payload["error"] = error
    else:
        payload["tool_response"] = {"stdout": "1 passed", "stderr": ""}
    return payload


def test_fail_twice_then_pass_creates_redacted_review_draft(git_project):
    root, project = git_project
    assert handle_hook_payload(_payload(root, "PostToolUseFailure", "Exit code 1\npassword=FAKE_SECRET_A")) is None
    assert handle_hook_payload(_payload(root, "PostToolUseFailure", "Exit code 1\npassword=FAKE_SECRET_B")) is None
    episode_id = handle_hook_payload(_payload(root, "PostToolUse"))
    assert episode_id
    episode = get_episode(project, episode_id)
    assert episode.review_state.value == "draft"
    assert episode.evidence["exit_codes"] == [1, 1, 0]
    assert "FAKE_SECRET" not in str(episode.evidence)
    with transaction(database_path(project)) as connection:
        tails = [row[0] for row in connection.execute("SELECT output_tail FROM events")]
    assert all("FAKE_SECRET" not in tail for tail in tails)
    assert all("[REDACTED]" in tail for tail in tails[:2])
    assert search_memory(project, ["pool test command"]) == []
    assert review_draft(project, episode_id, accept=True).status.value == "verified"


def test_sensitive_commands_are_not_captured(git_project):
    root, project = git_project
    payload = _payload(root, "PostToolUse", "")
    payload["tool_input"]["command"] = "Get-Content .env.production"
    assert handle_hook_payload(payload) is None
    with transaction(database_path(project)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_mcp_exposes_search_get_propose_with_review_gate(git_project):
    root, project = git_project

    async def exercise():
        async with Client(create_server(root)) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {"search_episodes", "get_episode", "propose_episode"}
            proposal = await client.call_tool(
                "propose_episode",
                {
                    "title": "MCP proposal",
                    "episode_type": "debugging",
                    "problem": "A project-scoped sample problem is proposed.",
                    "evidence_text": "Agent assertion only.",
                },
            )
            episode_id = proposal.structured_content["id"]
            before = await client.call_tool("search_episodes", {"queries": ["project scoped sample problem"]})
            assert before.structured_content["count"] == 0
            review_draft(project, episode_id, accept=True)
            after = await client.call_tool("search_episodes", {"queries": ["project scoped sample problem"]})
            assert after.structured_content["count"] == 1
            assert after.structured_content["results"][0]["untrusted"] is True
            detail = await client.call_tool("get_episode", {"episode_id": episode_id})
            assert detail.structured_content["untrusted"] is True
            assert detail.structured_content["episode"]["status"] == "unverified"

    asyncio.run(exercise())
