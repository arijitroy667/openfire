from __future__ import annotations

import pytest
from pydantic import ValidationError

from engbrain.models import EpisodeDraft, EpisodeType
from engbrain.redaction import redact_text


def test_redacts_common_keys_bearer_and_connection_strings():
    text = "api_key=abc123 password=hidden Bearer tokenvalue postgres://user:pass@db.local/app"
    redacted = redact_text(text)
    assert "abc123" not in redacted
    assert "hidden" not in redacted
    assert "tokenvalue" not in redacted
    assert "pass@" not in redacted
    assert redacted.count("[REDACTED]") == 4


def test_redacts_private_key_block():
    text = "-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----"
    assert "not-a-real-key" not in redact_text(text)


def test_episode_requires_title_and_problem():
    with pytest.raises(ValidationError):
        EpisodeDraft(title="x", episode_type=EpisodeType.DEBUGGING, problem="")
