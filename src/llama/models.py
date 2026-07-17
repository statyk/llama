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
    # Persisted run intent (stamped by find/profile-run, honored on replay):
    # whether this run also generates the verbatim DJ script (on by default;
    # --no-script opts out).
    script: bool = True
    # Max share of a multi-artist shortlist/auto-pick one artist may hold
    # (ceil(n * cap) slots) while other artists still have candidates.
    # 1.0 = pure best-first; at or below 1/n = one-per-artist round-robin.
    artist_cap: float = Field(default=1 / 3, gt=0, le=1)
    # Max share of the shortlist/auto-pick one YEAR may hold, same semantics
    # as artist_cap. 1.0 (default) = off: scores alone decide the year mix.
    # Set it (e.g. 0.25, or <=1/count for strict rotation) for an era tour.
    # On multi-artist runs the year cap applies within each artist's own slots.
    year_cap: float = Field(default=1.0, gt=0, le=1)
    # Quality floor on the LLM review score (0-10): scored shows below it
    # never reach the shortlist, so a drying-up profile comes back short and
    # says so instead of quietly shipping mediocre shows.
    min_quality_score: float = Field(default=6.0, ge=0, le=10)
    # Pinned artist roster (LMA collection identifiers). Non-empty = skip the
    # LLM artist matcher entirely and fan the search out over exactly these -
    # deterministic runs for standing profiles.
    artists: list[str] = Field(default_factory=list)


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


class SourcedParse(BaseModel):
    source: str  # "setlist.fm" | "chosen" | "lma:<identifier>" | "llm"
    parsed: ParsedSetlist


class AlignResult(BaseModel):
    sets: list[str]
    segues: list[bool]
    matched: list[bool]
    coverage: float
    conflicts: list[str] = Field(default_factory=list)


class AlignedTrack(BaseModel):
    index: int
    set: str
    segue: bool = False
    matched_title: str = ""


class AlignedStructure(BaseModel):
    tracks: list[AlignedTrack]


class StructureInfo(BaseModel):
    source: str  # "setlist.fm" | "chosen" | "lma:<identifier>" | "llm"
    alignment: str  # "deterministic" | "llm"
    coverage: float
    conflicts: list[str] = Field(default_factory=list)


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
    structure: StructureInfo | None = None


class DJNotes(BaseModel):
    context: str = ""  # one-line era/tour context
    intro: str
    set_intros: dict[str, str]  # keyed by set: "1", "2", "encore"
    set_break_notes: list[str] = Field(default_factory=list)
    outro: str
    mentioned_songs: list[str] = Field(default_factory=list)


class ResearchVetting(BaseModel):
    """What research.md asserts about this show, extracted for grounding checks."""
    asserted_songs: list[str] = Field(default_factory=list)
    asserted_dates: list[str] = Field(default_factory=list)
    asserted_set_count: int | None = None  # explicit totals only; encores excluded
    context: str = ""  # one-line era/tour context for the manifest


class VettingResult(BaseModel):
    vetting: ResearchVetting
    flags: list[str] = Field(default_factory=list)  # empty = research passed


class ManifestTrack(BaseModel):
    index: int
    set: str
    title: str
    filename: str  # packaged filename, e.g. "01 - Morning Dew.mp3"
    duration_sec: float | None = None
    segue: bool = False


class SetBreak(BaseModel):
    after_track: int
    note_index: int | None = None  # index into dj_notes.set_break_notes when a script exists


class Manifest(BaseModel):
    schema_version: int = 2
    show: dict
    source: dict
    tracks: list[ManifestTrack]
    set_breaks: list[SetBreak]
    dj_notes: DJNotes | None = None
    research: str | None = None  # relative path within the package
    reviews: str | None = None
    research_vetted: bool = False
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


class Provenance(BaseModel):
    """Why this show exists: the run and shortlist context that processed it.
    Lets redo/deliver work standalone after the originating run is gone."""
    performance_id: str
    run: str
    dossier: str = ""  # shortlist rationale + external reputation, as fed to research
    candidate: Candidate
    # Winnow assessment (quality_score, recording_complaints, reviewed_identifier)
    # so redo --from select avoids complained-about recordings. Optional/None
    # keeps old provenance.json files parseable.
    assessment: QualityAssessment | None = None
    script: bool = True
    processed_at: str  # ISO-8601 UTC


class ArtistMatch(BaseModel):
    identifier: str
    reason: str = ""


class ArtistMatches(BaseModel):
    matches: list[ArtistMatch] = Field(default_factory=list)
