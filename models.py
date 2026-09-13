from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Expertise(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"


class PodcastStyle(str, Enum):
    CONCISE = "concise"
    CONVERSATIONAL = "conversational"
    TECHNICAL = "technical"
    DEBATE = "debate"


class VideoSource(BaseModel):
    video_id: str
    url: str
    title: str
    channel: str
    duration_seconds: int
    description: str | None = None


class TranscriptSegment(BaseModel):
    video_id: str
    start_seconds: float
    duration_seconds: float
    text: str


class SourceChunk(BaseModel):
    chunk_id: str
    video_id: str
    start_seconds: float
    end_seconds: float
    text: str
    summary: str = ""
    concepts: list[str] = Field(default_factory=list)
    relevance_score: float = 0.0


class Citation(BaseModel):
    video_id: str
    start_seconds: float
    end_seconds: float


class Insight(BaseModel):
    id: str
    title: str
    explanation: str
    importance: float
    source_chunks: list[str] = Field(default_factory=list)
    source_citations: list[Citation] = Field(default_factory=list)


class GroundedClaim(BaseModel):
    claim: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = 0.0


class PodcastEpisode(BaseModel):
    title: str
    description: str
    target_minutes: int
    script: str
    insights: list[Insight] = Field(default_factory=list)
    sources: list[VideoSource] = Field(default_factory=list)
    claims: list[GroundedClaim] = Field(default_factory=list)
    made_the_cut: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


class SourceError(BaseModel):
    url: str
    video_id: str | None = None
    stage: str
    message: str


class CatchUpJob(BaseModel):
    job_id: str
    urls: list[str]
    target_minutes: int = 10
    focus: str
    expertise: Expertise = Expertise.INTERMEDIATE
    style: PodcastStyle = PodcastStyle.CONVERSATIONAL
    channel_id: str | None = None
    thread_ts: str | None = None
    user_id: str | None = None
    status: Literal[
        "received",
        "reading",
        "analyzing",
        "synthesizing",
        "writing",
        "rendering",
        "complete",
        "failed",
    ] = "received"
    source_errors: list[SourceError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EpisodeEval(BaseModel):
    citation_coverage: float = 0.0
    citation_validity: bool = True
    length_adherence: float = 0.0
    actual_words: int = 0
    target_words: int = 0
    source_coverage: int = 0
    source_total: int = 0
    grounded_claim_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class JobResult(BaseModel):
    job: CatchUpJob
    episode: PodcastEpisode | None = None
    evaluation: EpisodeEval | None = None
    mp3_path: str | None = None
    script_path: str | None = None
    slack_file_url: str | None = None
    drive_url: str | None = None
    notion_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ChunkAnalysisResult(BaseModel):
    summary: str
    concepts: list[str]
    relevance_score: float = Field(ge=0.0, le=1.0)


class InsightDraft(BaseModel):
    title: str
    explanation: str
    importance: float = Field(ge=0.0, le=1.0)
    source_chunk_ids: list[str]
    citations: list[Citation]


class SynthesisResult(BaseModel):
    insights: list[InsightDraft]
    made_the_cut: list[str]
    skipped: list[str]


class GroundedClaimsResult(BaseModel):
    claims: list[GroundedClaim]


class PodcastScriptResult(BaseModel):
    title: str
    description: str
    script: str
    made_the_cut: list[str]
    skipped: list[str]
