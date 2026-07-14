from __future__ import annotations

from pydantic import BaseModel, Field


class SetlistConstraint(BaseModel):
    sequence: list[str]  # song names that must appear consecutively, in order


class Criteria(BaseModel):
    query: str
    collection: str | None = None
    artist: str | None = None
    date_from: str | None = None  # YYYY-MM-DD
    date_to: str | None = None
    setlist_constraints: list[SetlistConstraint] = Field(default_factory=list)
    soft_preferences: str | None = None
    min_avg_rating: float = 3.5
    min_reviews: int = 3
    count: int = 1


class RecordingSummary(BaseModel):
    identifier: str
    title: str = ""
    date: str | None = None
    venue: str | None = None
    coverage: str | None = None
    avg_rating: float | None = None
    num_reviews: int = 0
    description: str | None = None


class Candidate(BaseModel):
    performance_id: str
    collection: str
    date: str
    venue: str | None = None
    city: str | None = None
    recordings: list[RecordingSummary]


class QualityAssessment(BaseModel):
    performance_id: str
    quality_score: float  # 0..10
    non_attendee_evidence: str = ""
    recording_complaints: list[str] = Field(default_factory=list)
    rationale: str
    reviewed_identifier: str = ""  # set by winnow, not the LLM


class QualityBatch(BaseModel):
    assessments: list[QualityAssessment]


class ShortlistEntry(BaseModel):
    candidate: Candidate
    assessment: QualityAssessment
    external_reputation: str | None = None
    rank: int
    approved: bool | None = None  # None = not yet human-reviewed


class SetlistItem(BaseModel):
    title: str
    normalized: str
    set: str  # "1" | "2" | "3" | "encore"
    segue: bool = False  # runs directly into the following song


class ParsedSetlist(BaseModel):
    items: list[SetlistItem] = Field(default_factory=list)
    confidence: str = "low"  # "high" | "medium" | "low"


class Track(BaseModel):
    index: int  # 1-based play order
    set: str
    title: str
    filename: str  # source filename within the archive.org item
    duration_sec: float | None = None
    segue: bool = False
    title_source: str  # "tags" | "setlist" | "sibling" | "unresolved"


class Show(BaseModel):
    performance_id: str
    identifier: str
    artist: str
    date: str
    venue: str | None = None
    city: str | None = None
    tracks: list[Track] = Field(default_factory=list)
    set_breaks: list[int] = Field(default_factory=list)  # play-order index after which a break falls
    excluded_files: list[dict] = Field(default_factory=list)  # {"filename":..., "reasons":[...]}
    lineage: str | None = None
    source_url: str = ""
    needs_review: bool = False
    review_flags: list[str] = Field(default_factory=list)


class DJNotes(BaseModel):
    context: str = ""  # one-line era/tour context
    intro: str
    set_intros: dict[str, str]  # keyed by set: "1", "2", "encore"
    set_break_notes: list[str] = Field(default_factory=list)
    outro: str
    mentioned_songs: list[str] = Field(default_factory=list)


class ManifestTrack(BaseModel):
    index: int
    set: str
    title: str
    filename: str  # packaged filename, e.g. "01 - Morning Dew.mp3"
    duration_sec: float | None = None
    segue: bool = False


class SetBreak(BaseModel):
    after_track: int
    note_index: int  # index into dj_notes.set_break_notes


class Manifest(BaseModel):
    schema_version: int = 1
    show: dict
    source: dict
    tracks: list[ManifestTrack]
    set_breaks: list[SetBreak]
    dj_notes: DJNotes
    total_duration_sec: float
    set_durations_sec: dict[str, float]


class LedgerEntry(BaseModel):
    performance_id: str
    artist: str
    date: str
    venue: str | None = None
    status: str  # "selected" | "delivered" | "rejected"
    run: str
    recorded_at: str  # ISO-8601 UTC
