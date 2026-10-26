from __future__ import annotations

import json
import tomllib

from engbrain.client_config import (
    claude_code_status,
    configure_claude_code,
    configure_codex,
    configure_cursor,
    configure_vscode,
    codex_status,
)


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


def test_cursor_and_vscode_mcp_configs_preserve_existing_servers(git_project, monkeypatch):
    root, project = git_project
    monkeypatch.setattr("engbrain.client_config.shutil.which", lambda command: "C:/tools/engbrain.exe")
    cursor = root / ".cursor" / "mcp.json"
    cursor.parent.mkdir()
    cursor.write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}), encoding="utf-8")
    vscode = root / ".vscode" / "mcp.json"
    vscode.parent.mkdir()
    vscode.write_text(json.dumps({"servers": {"other": {"type": "stdio", "command": "other"}}}), encoding="utf-8")

    configure_cursor(project)
    configure_cursor(project)
    configure_vscode(project)
    configure_vscode(project)

    cursor_config = json.loads(cursor.read_text(encoding="utf-8"))
    vscode_config = json.loads(vscode.read_text(encoding="utf-8"))
    assert "other" in cursor_config["mcpServers"]
    assert cursor_config["mcpServers"]["engbrain"]["args"][-1] == "${workspaceFolder}"
    assert "other" in vscode_config["servers"]
    assert vscode_config["servers"]["engbrain"]["type"] == "stdio"


def test_codex_project_config_preserves_tables_and_is_idempotent(git_project, monkeypatch):
    root, project = git_project
    monkeypatch.setattr("engbrain.client_config.shutil.which", lambda command: "C:/tools/engbrain.exe")
    config = root / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text('# Keep this comment.\nmodel = "existing-model"\n\n[features]\nfoo = true\n', encoding="utf-8")

    configure_codex(project)
    configure_codex(project)

    content = config.read_text(encoding="utf-8")
    parsed = tomllib.loads(content)
    assert "# Keep this comment." in content
    assert parsed["model"] == "existing-model"
    assert parsed["features"]["foo"] is True
    assert parsed["mcp_servers"]["engbrain"]["command"] == "engbrain"
    assert parsed["mcp_servers"]["engbrain"]["args"] == ["mcp", "serve", "--root", "."]
    assert parsed["mcp_servers"]["engbrain"]["cwd"] == "."
    assert codex_status(project) == (True, True)
