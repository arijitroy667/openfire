from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from engbrain.config import load_project
from engbrain.detector import _tail_2kb, exit_code_from_failure, normalize_command, record_command_event
from engbrain.redaction import redact_text

_SENSITIVE_ENV_DUMP = re.compile(
    r"(?i)(?:\b(?:env|printenv)\b|\b(?:Get-ChildItem|gci|dir|ls)\s+Env:)"
)
_ENV_FILE = re.compile(r"(?i)\.env(?:\.[A-Za-z0-9_-]+)?(?![A-Za-z0-9_-])")
_ALLOWED_ENV_FILES = {".env.example", ".env.sample", ".env.template"}


def _extract_output(payload: dict[str, Any]) -> str:
    if payload.get("hook_event_name") == "PostToolUseFailure":
        value = payload.get("error", "")
    else:
        value = payload.get("tool_response", "")
        if isinstance(value, dict):
            value = "\n".join(
                item for item in (value.get("stdout", ""), value.get("stderr", "")) if isinstance(item, str)
            )
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _excluded(command: str) -> bool:
    if _SENSITIVE_ENV_DUMP.search(command):
        return True
    if any(match.group(0).casefold() not in _ALLOWED_ENV_FILES for match in _ENV_FILE.finditer(command)):
        return True
    custom = os.environ.get("ENGBRAIN_EXCLUDE_COMMANDS", "")
    return any(item.strip().casefold() in command.casefold() for item in custom.split(",") if item.strip())


def handle_hook_payload(payload: dict[str, Any]) -> str | None:
    """Record a supported Claude Code command event; return a new draft ID if detected."""
    event_name = payload.get("hook_event_name")
    if event_name not in {"PostToolUse", "PostToolUseFailure"}:
        return None
    if payload.get("tool_name") not in {"Bash", "PowerShell"}:
        return None
    if payload.get("is_interrupt") is True:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw_command = tool_input.get("command")
    if not isinstance(raw_command, str) or not raw_command.strip():
        return None
    command = redact_text(raw_command.strip())[:2000]
    if _excluded(command):
        return None
    cwd_value = payload.get("cwd")
    if not isinstance(cwd_value, str) or not cwd_value:
        return None
    try:
        cwd = Path(cwd_value).resolve()
        project = load_project(cwd)
    except (OSError, ValueError):
        return None
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    if event_name == "PostToolUse":
        exit_code = 0
    else:
        error = _extract_output(payload)
        exit_code = exit_code_from_failure(error)
    output = redact_text(_extract_output(payload))
    output_tail = _tail_2kb(output)
    normalized = normalize_command(command, Path(project.repo_root))
    episode = record_command_event(
        project,
        session_id=session_id[:200],
        command=command,
        normalized_command=normalized[:2000],
        exit_code=exit_code,
        output_tail=output_tail,
        cwd=str(cwd),
    )
    return episode.id if episode else None


def handle_stdin() -> str | None:
    try:
        raw = sys.stdin.read(1_000_000)
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    return handle_hook_payload(payload) if isinstance(payload, dict) else None
