from __future__ import annotations

import json

from engbrain.client_config import claude_code_status, configure_claude_code


def test_claude_code_setup_preserves_config_and_is_idempotent(git_project, monkeypatch):
    root, project = git_project
    monkeypatch.setattr("engbrain.client_config.shutil.which", lambda command: "C:/tools/engbrain.exe")
    (root / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "other", "args": []}}}),
        encoding="utf-8",
    )
    local = root / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    local.write_text(json.dumps({"permissions": {"allow": ["Read"]}}), encoding="utf-8")
    configure_claude_code(project)
    configure_claude_code(project)
    mcp_config = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    hooks_config = json.loads(local.read_text(encoding="utf-8"))
    assert "other" in mcp_config["mcpServers"]
    assert "${CLAUDE_PROJECT_DIR:-.}" in mcp_config["mcpServers"]["engbrain"]["args"]
    assert hooks_config["permissions"]["allow"] == ["Read"]
    assert claude_code_status(project) == (True, True)
    for event in ("PostToolUse", "PostToolUseFailure"):
        configured = hooks_config["hooks"][event]
        matching = [entry for entry in configured if entry.get("matcher") == "Bash|PowerShell"]
        assert len(matching) == 1
        assert matching[0]["hooks"][0]["async"] is True
    pre_tool = hooks_config["hooks"]["PreToolUse"]
    matching = [entry for entry in pre_tool if entry.get("matcher") == "Edit|Write"]
    assert len(matching) == 1
    assert matching[0]["hooks"][0]["timeout"] == 3
    assert "async" not in matching[0]["hooks"][0]
