"""Best-effort local redaction for common secret formats."""

from __future__ import annotations

import re


_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I | re.S),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})\b"),
    re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|passwd|secret)\b\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(://[^:/\s]+:)([^@/\s]+)(@)"),
    re.compile(r"(?i)(\b(?:token|secret|password)\b[^\r\n]{0,40}?\b)[A-Za-z0-9_+/=-]{32,}"),
)


def redact_text(value: str) -> str:
    """Replace likely credentials; callers must still treat this as best-effort."""
    text = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(r"\1[REDACTED]\3", text)
        elif pattern.groups >= 1:
            text = pattern.sub(r"\1[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text
