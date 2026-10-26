"""Optional, redacted LLM assistance for preparing reviewable episode drafts."""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field

from engbrain.redaction import redact_text

MAX_NOTES_LENGTH = 12_000


class EpisodeNarrative(BaseModel):
    """Structured narrative fields suggested from user-provided notes."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200)
    problem: str = Field(min_length=1, max_length=10_000)
    context: str = Field(default="", max_length=10_000)
    attempts: list[str] = Field(default_factory=list, max_length=50)
    solution_taken: str | None = Field(default=None, max_length=10_000)
    rejected_alternatives: list[str] = Field(default_factory=list, max_length=50)
    verification_text: str | None = Field(default=None, max_length=5_000)


class NarrativeDraftError(RuntimeError):
    """Safe, user-facing error for optional provider setup or generation failures."""


def draft_episode_narrative(
    notes: str,
    *,
    model: str | None = None,
    client=None,
) -> EpisodeNarrative:
    """Turn notes into a proposed narrative; never save or accept the episode here.

    Only redacted user-provided notes are sent to the configured OpenAI API. The
    optional SDK is imported lazily, so the offline core has no extra dependency.
    """
    if not notes.strip():
        raise ValueError("Provide incident notes to draft from")
    safe_notes = redact_text(notes.strip()[:MAX_NOTES_LENGTH])

    if client is None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise NarrativeDraftError(
                "Install the optional LLM extra with `uv sync --extra llm`, then set OPENAI_API_KEY."
            ) from exc
        try:
            client = OpenAI()
        except Exception as exc:
            raise NarrativeDraftError(
                "Could not configure the OpenAI client. Check OPENAI_API_KEY and the optional LLM setup."
            ) from exc

    selected_model = model or os.environ.get("ENGBRAIN_OPENAI_MODEL", "gpt-6-astra")
    instructions = (
        "Prepare a concise engineering incident memory from the supplied notes. "
        "Use only facts present in the notes. Do not infer a root cause, solution, "
        "failed attempt, or verification that is not supported by them. Leave unknown "
        "optional fields null and unknown lists empty. Do not add commands or advice."
    )
    try:
        response = client.responses.parse(
            model=selected_model,
            instructions=instructions,
            input=safe_notes,
            text_format=EpisodeNarrative,
            store=False,
        )
    except Exception as exc:
        raise NarrativeDraftError(
            f"Narrative generation failed ({type(exc).__name__}); no episode was created."
        ) from exc

    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        raise NarrativeDraftError(
            "The model returned no complete narrative; no episode was created."
        )
    try:
        return EpisodeNarrative.model_validate(parsed)
    except Exception as exc:
        raise NarrativeDraftError(
            "The model response did not match the episode schema; no episode was created."
        ) from exc
