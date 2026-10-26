from __future__ import annotations

import re


_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)
_HEX = re.compile(r"\b0x[0-9a-f]+\b|\b[0-9a-f]{8,}\b", re.I)
_WINDOWS_PATH = re.compile(r"\b[A-Za-z]:[\\/](?:[^\s<>\"|?*]+[\\/])*[^\s<>\"|?*]*")
_UNIX_PATH = re.compile(r"(?<![:\w])/(?:[^\s/:]+/)+[^\s:]*")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)*\b")
_WHITESPACE = re.compile(r"\s+")


def normalize_error_signature(value: str) -> str:
    """Normalize volatile paths and identifiers while preserving error wording."""
    text = value.strip().casefold()
    text = _UUID.sub(" <uuid> ", text)
    text = _WINDOWS_PATH.sub(" <path> ", text)
    text = _UNIX_PATH.sub(" <path> ", text)
    text = _HEX.sub(" <hex> ", text)
    text = _NUMBER.sub(" <n> ", text)
    return _WHITESPACE.sub(" ", text).strip()


def fts_query(value: str) -> str:
    """Build a safe OR query from literal word tokens, without exposing FTS syntax."""
    tokens = re.findall(r"[^\W_]+(?:[_-][^\W_]+)*", value, flags=re.UNICODE)
    unique = list(dict.fromkeys(token for token in tokens if token))
    return " OR ".join('"' + token.replace('"', '""') + '"' for token in unique)
