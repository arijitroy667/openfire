from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from engbrain.models import Project


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read client configuration {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Client configuration must contain a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _mcp_entry() -> dict[str, Any]:
    return {
        "type": "stdio",
        "command": "engbrain",
        "args": ["mcp", "serve", "--root", "${CLAUDE_PROJECT_DIR:-.}"],
    }


def _is_engbrain_entry(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    command = str(value.get("command", "")).casefold()
    args = " ".join(str(item) for item in value.get("args", [])).casefold()
    return "engbrain" in command or "engbrain" in args


def _upsert_hooks(settings: dict[str, Any], command: str) -> None:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude Code hooks setting must be a JSON object")
    hook = {
        "type": "command",
        "command": command,
        "args": ["hook", "event"],
        "async": True,
        "timeout": 10,
    }
    for event_name in ("PostToolUse", "PostToolUseFailure"):
        entries = hooks.setdefault(event_name, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude Code {event_name} hooks must be a JSON array")
        target = next(
            (entry for entry in entries if isinstance(entry, dict) and entry.get("matcher") == "Bash|PowerShell"),
            None,
        )
        if target is None:
            entries.append({"matcher": "Bash|PowerShell", "hooks": [hook.copy()]})
            continue
        configured = target.setdefault("hooks", [])
        if not isinstance(configured, list):
            raise ValueError(f"Claude Code {event_name} hook entry has an invalid hooks list")
        if not any(
            isinstance(item, dict)
            and item.get("type") == "command"
            and item.get("command") == command
            and item.get("args") == hook["args"]
            for item in configured
        ):
            configured.append(hook.copy())


def configure_claude_code(project: Project) -> list[Path]:
    """Register a local stdio server and asynchronous shell hooks without clobbering settings."""
    root = Path(project.repo_root)
    if shutil.which("engbrain") is None:
        raise ValueError(
            "The `engbrain` command is not on PATH. Install EngBrain with pipx or activate its environment before setup."
        )
    mcp_path = root / ".mcp.json"
    mcp_config = _read_json(mcp_path)
    servers = mcp_config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("Claude Code mcpServers setting must be a JSON object")
    entry = _mcp_entry()
    existing = servers.get("engbrain")
    if existing is not None and existing != entry and not _is_engbrain_entry(existing):
        raise ValueError("The Claude Code MCP server name 'engbrain' is already used by another command")
    servers["engbrain"] = entry
    _write_json(mcp_path, mcp_config)

    settings_path = root / ".claude" / "settings.local.json"
    settings = _read_json(settings_path)
    _upsert_hooks(settings, entry["command"])
    _write_json(settings_path, settings)
    return [mcp_path, settings_path]


def claude_code_status(project: Project) -> tuple[bool, bool]:
    root = Path(project.repo_root)
    mcp_config = _read_json(root / ".mcp.json")
    servers = mcp_config.get("mcpServers", {})
    entry = servers.get("engbrain") if isinstance(servers, dict) else None
    command = entry.get("command") if isinstance(entry, dict) else None
    mcp_ok = _is_engbrain_entry(entry) and isinstance(command, str) and shutil.which(command) is not None
    settings = _read_json(root / ".claude" / "settings.local.json")
    hooks = settings.get("hooks", {})
    hooks_ok = isinstance(hooks, dict)
    for event_name in ("PostToolUse", "PostToolUseFailure"):
        entries = hooks.get(event_name, []) if hooks_ok else []
        event_ok = any(
            isinstance(entry, dict)
            and entry.get("matcher") == "Bash|PowerShell"
            and any(
                isinstance(item, dict)
                and item.get("type") == "command"
                and isinstance(item.get("command"), str)
                and Path(item["command"]).name.casefold().startswith("engbrain")
                and shutil.which(item["command"]) is not None
                and item.get("args") == ["hook", "event"]
                for item in entry.get("hooks", [])
            )
            for entry in entries
        )
        hooks_ok = hooks_ok and event_ok
    return mcp_ok, hooks_ok


def claude_code_setup_present(project: Project) -> bool:
    root = Path(project.repo_root)
    mcp_config = _read_json(root / ".mcp.json")
    servers = mcp_config.get("mcpServers", {})
    if isinstance(servers, dict) and "engbrain" in servers:
        return True
    settings = _read_json(root / ".claude" / "settings.local.json")
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return False
    for event_name in ("PostToolUse", "PostToolUseFailure"):
        for entry in hooks.get(event_name, []):
            if not isinstance(entry, dict):
                continue
            for item in entry.get("hooks", []):
                if isinstance(item, dict) and "engbrain" in str(item.get("command", "")).casefold():
                    return True
    return False
