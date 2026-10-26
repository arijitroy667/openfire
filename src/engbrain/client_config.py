from __future__ import annotations

import json
import os
import shutil
import tomllib
from pathlib import Path
from typing import Any

import tomlkit

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


def _upsert_hook(
    hooks: dict[str, Any],
    *,
    event_name: str,
    matcher: str,
    hook: dict[str, Any],
) -> None:
    entries = hooks.setdefault(event_name, [])
    if not isinstance(entries, list):
        raise ValueError(f"Claude Code {event_name} hooks must be a JSON array")
    target = next(
        (entry for entry in entries if isinstance(entry, dict) and entry.get("matcher") == matcher),
        None,
    )
    if target is None:
        entries.append({"matcher": matcher, "hooks": [hook.copy()]})
        return
    configured = target.setdefault("hooks", [])
    if not isinstance(configured, list):
        raise ValueError(f"Claude Code {event_name} hook entry has an invalid hooks list")
    if not any(
        isinstance(item, dict)
        and item.get("type") == "command"
        and item.get("command") == hook["command"]
        and item.get("args") == hook["args"]
        for item in configured
    ):
        configured.append(hook.copy())


def _upsert_hooks(settings: dict[str, Any], command: str) -> None:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude Code hooks setting must be a JSON object")
    capture_hook = {
        "type": "command",
        "command": command,
        "args": ["hook", "event"],
        "async": True,
        "timeout": 10,
    }
    recall_hook = {
        "type": "command",
        "command": command,
        "args": ["hook", "event"],
        "timeout": 3,
    }
    for event_name in ("PostToolUse", "PostToolUseFailure"):
        _upsert_hook(
            hooks,
            event_name=event_name,
            matcher="Bash|PowerShell",
            hook=capture_hook,
        )
    _upsert_hook(
        hooks,
        event_name="PreToolUse",
        matcher="Edit|Write",
        hook=recall_hook,
    )


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


def _configure_json_mcp(project: Project, *, path: Path, server_key: str, client: str) -> Path:
    if shutil.which("engbrain") is None:
        raise ValueError(
            "The `engbrain` command is not on PATH. Install EngBrain with pipx or activate its environment before setup."
        )
    config = _read_json(path)
    servers = config.setdefault(server_key, {})
    if not isinstance(servers, dict):
        raise ValueError(f"{client} {server_key} setting must be a JSON object")
    entry = {
        "type": "stdio",
        "command": "engbrain",
        "args": ["mcp", "serve", "--root", "${workspaceFolder}"],
    }
    existing = servers.get("engbrain")
    if existing is not None and existing != entry and not _is_engbrain_entry(existing):
        raise ValueError(f"The {client} MCP server name 'engbrain' is already used by another command")
    servers["engbrain"] = entry
    _write_json(path, config)
    return path


def configure_cursor(project: Project) -> list[Path]:
    """Set up Cursor's project-level stdio MCP connection; no Cursor hooks are installed."""
    root = Path(project.repo_root)
    return [_configure_json_mcp(project, path=root / ".cursor" / "mcp.json", server_key="mcpServers", client="Cursor")]


def configure_vscode(project: Project) -> list[Path]:
    """Set up VS Code's workspace stdio MCP connection; no VS Code hooks are installed."""
    root = Path(project.repo_root)
    return [_configure_json_mcp(project, path=root / ".vscode" / "mcp.json", server_key="servers", client="VS Code")]


def configure_codex(project: Project) -> list[Path]:
    """Set up a project-trusted Codex MCP entry while preserving TOML formatting."""
    if shutil.which("engbrain") is None:
        raise ValueError(
            "The `engbrain` command is not on PATH. Install EngBrain with pipx or activate its environment before setup."
        )
    root = Path(project.repo_root)
    path = root / ".codex" / "config.toml"
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        document = tomlkit.parse(text) if text.strip() else tomlkit.document()
    except (OSError, tomlkit.exceptions.ParseError) as exc:
        raise ValueError(f"Cannot read Codex configuration {path}: {exc}") from exc
    servers = document.get("mcp_servers")
    if servers is None:
        servers = tomlkit.table()
        document["mcp_servers"] = servers
    if not isinstance(servers, tomlkit.items.Table):
        raise ValueError("Codex mcp_servers setting must be a TOML table")
    entry = servers.get("engbrain")
    if entry is not None and not _is_engbrain_entry(entry):
        raise ValueError("The Codex MCP server name 'engbrain' is already used by another command")
    if entry is None:
        entry = tomlkit.table()
        servers["engbrain"] = entry
    entry["command"] = "engbrain"
    entry["args"] = ["mcp", "serve", "--root", "."]
    entry["cwd"] = "."
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(tomlkit.dumps(document), encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        raise ValueError(f"Could not write Codex configuration {path}: {exc}") from exc
    return [path]


def configure_client(project: Project, client: str) -> list[Path]:
    """Configure a supported coding client for repository-scoped MCP access."""
    if client == "claude-code":
        return configure_claude_code(project)
    if client == "codex":
        return configure_codex(project)
    if client == "cursor":
        return configure_cursor(project)
    if client == "vscode":
        return configure_vscode(project)
    if client == "none":
        return []
    raise ValueError(f"Unsupported client: {client}")


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
    required = {
        "PostToolUse": "Bash|PowerShell",
        "PostToolUseFailure": "Bash|PowerShell",
        "PreToolUse": "Edit|Write",
    }
    for event_name, matcher in required.items():
        entries = hooks.get(event_name, []) if hooks_ok else []
        event_ok = any(
            isinstance(entry, dict)
            and entry.get("matcher") == matcher
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
    for event_name in ("PostToolUse", "PostToolUseFailure", "PreToolUse"):
        for entry in hooks.get(event_name, []):
            if not isinstance(entry, dict):
                continue
            for item in entry.get("hooks", []):
                if isinstance(item, dict) and "engbrain" in str(item.get("command", "")).casefold():
                    return True
    return False


def _json_mcp_status(path: Path, server_key: str) -> tuple[bool, bool]:
    config = _read_json(path)
    servers = config.get(server_key, {})
    entry = servers.get("engbrain") if isinstance(servers, dict) else None
    command = entry.get("command") if isinstance(entry, dict) else None
    configured = _is_engbrain_entry(entry)
    available = configured and isinstance(command, str) and shutil.which(command) is not None
    return bool(available), bool(configured)


def codex_status(project: Project) -> tuple[bool, bool]:
    path = Path(project.repo_root) / ".codex" / "config.toml"
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"Cannot read Codex configuration {path}: {exc}") from exc
    servers = config.get("mcp_servers", {})
    entry = servers.get("engbrain") if isinstance(servers, dict) else None
    command = entry.get("command") if isinstance(entry, dict) else None
    configured = _is_engbrain_entry(entry)
    available = configured and isinstance(command, str) and shutil.which(command) is not None
    return bool(available), bool(configured)


def client_statuses(project: Project) -> dict[str, tuple[bool, bool]]:
    """Return (available, configured) for each supported client's MCP entry."""
    root = Path(project.repo_root)
    claude_mcp, claude_hooks = claude_code_status(project)
    claude_present = claude_code_setup_present(project)
    return {
        "Claude Code MCP": (claude_mcp, claude_present),
        "Claude Code hooks": (claude_hooks, claude_present),
        "Codex MCP": codex_status(project),
        "Cursor MCP": _json_mcp_status(root / ".cursor" / "mcp.json", "mcpServers"),
        "VS Code MCP": _json_mcp_status(root / ".vscode" / "mcp.json", "servers"),
    }
