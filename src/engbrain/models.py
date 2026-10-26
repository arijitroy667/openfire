from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EpisodeType(StrEnum):
    DEBUGGING = "debugging"
    ARCHITECTURE_DECISION = "architecture_decision"
    DEPENDENCY = "dependency"
    DEPLOYMENT = "deployment"
    OPERATIONAL_GOTCHA = "operational_gotcha"


class EvidenceKind(StrEnum):
    MECHANICAL = "mechanical"
    ASSERTED = "asserted"
    NONE = "none"


class EpisodeStatus(StrEnum):
    UNRESOLVED = "unresolved"
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    SUPERSEDED = "superseded"


class ReviewState(StrEnum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EpisodeOrigin(StrEnum):
    HOOK = "hook"
    MANUAL = "manual"
    AGENT = "agent"


class AnchorKind(StrEnum):
    PATH = "path"
    DEPENDENCY = "dependency"
    COMMIT = "commit"


class StalenessLevel(StrEnum):
    FRESH = "fresh"
    DRIFTED = "drifted"
    STALE = "stale"
    UNKNOWN = "unknown"


class Attempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=2000)
    outcome: str | None = Field(default=None, max_length=2000)
    command: str | None = Field(default=None, max_length=2000)
    exit_code: int | None = None


class EpisodeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200)
    episode_type: EpisodeType
    problem: str = Field(min_length=1, max_length=10000)
    context: str = Field(default="", max_length=10000)
    error_signature: str | None = Field(default=None, max_length=1000)
    attempts: list[Attempt] = Field(default_factory=list, max_length=50)
    solution_taken: str | None = Field(default=None, max_length=10000)
    rejected_alternatives: list[str] = Field(default_factory=list, max_length=50)
    verification_text: str | None = Field(default=None, max_length=5000)
    evidence_kind: EvidenceKind = EvidenceKind.NONE
    evidence: dict[str, Any] = Field(default_factory=dict)
    status: EpisodeStatus = EpisodeStatus.UNVERIFIED
    review_state: ReviewState = ReviewState.ACCEPTED
    origin: EpisodeOrigin = EpisodeOrigin.MANUAL
    verified_at_sha: str | None = Field(default=None, max_length=64)

    @field_validator("rejected_alternatives")
    @classmethod
    def validate_alternatives(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("rejected alternatives cannot be empty")
        return values


class Episode(EpisodeDraft):
    id: str = Field(default_factory=lambda: uuid4().hex)
    project_id: str
    supersedes_episode_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EpisodeAnchor(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    episode_id: str
    kind: AnchorKind
    value: str = Field(min_length=1, max_length=1000)
    version: str | None = Field(default=None, max_length=200)


class EpisodeResult(BaseModel):
    episode: Episode
    anchors: list[EpisodeAnchor] = Field(default_factory=list)
    staleness: StalenessLevel = StalenessLevel.UNKNOWN
    staleness_reasons: list[str] = Field(default_factory=list)
    match_reason: str | None = None


class Project(BaseModel):
    id: str
    name: str
    repo_root: str
    repo_fingerprint: str
    created_at: datetime = Field(default_factory=utc_now)
