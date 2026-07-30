"""Show/run discovery: derived state, iteration, and name resolution.

State is never stored; it is derived from which artifacts exist plus the
ledger, so it cannot go stale. Scan-on-demand — at this scale (~10^2 shows)
a walk is milliseconds.
"""
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from llama.errors import LlamaError
from llama.ledger import Ledger
from llama.locks import file_lock
from llama.models import LedgerEntry, Overrides, Provenance, Show
from llama.workspace import ShowWorkspace, read_json, read_model, read_overrides


ARCHIVE_URL = "https://archive.org/details/{identifier}"


class CatalogError(LlamaError):
    """Resolution failure; matches lists the candidates (empty = no match).

    The candidate list is exposed to the CLI error boundary as `details`.
    """

    def __init__(self, message: str, matches: list[str] | None = None):
        super().__init__(message, details=matches)
        self.matches = matches or []


@dataclass
class CatalogEntry:
    slug: str
    ws: ShowWorkspace
    state: str
    flags: list[str] = field(default_factory=list)
    provenance: Provenance | None = None
    artist: str = ""
    date: str = ""
    overrides: Overrides = field(default_factory=Overrides)


# (artifact attribute, depth, state name) from shallowest to deepest.
_STAGES = [
    ("selection", 1, "selected"),
    ("show", 2, "gathered"),
    ("research", 3, "researched"),
    ("vetting", 4, "vetted"),
    ("briefing_json", 5, "briefed"),
]


@dataclass
class ConsideredRecording:
    identifier: str
    score: float
    lineage: str
    kept_tracks: int


@dataclass
class RecordingInfo:
    identifier: str                       # the chosen recording
    url: str                              # ARCHIVE_URL filled in
    considered: list[ConsideredRecording]  # scores keys minus chosen, score desc


def recording_info(ws: ShowWorkspace) -> RecordingInfo | None:
    """Archive URL + considered-recordings extraction from selection.json
    (spec §10). None when selection.json is absent; never writes."""
    if not ws.selection.exists():
        return None
    data = read_json(ws.selection)
    chosen = data["identifier"]
    scores = data.get("scores", {})
    considered = [
        ConsideredRecording(
            identifier=ident,
            score=info.get("score", 0.0),
            lineage=info.get("lineage", ""),
            kept_tracks=info.get("kept_tracks", 0),
        )
        for ident, info in scores.items()
        if ident != chosen
    ]
    considered.sort(key=lambda c: c.score, reverse=True)
    return RecordingInfo(identifier=chosen,
                         url=ARCHIVE_URL.format(identifier=chosen),
                         considered=considered)


def _performance_id(ws: ShowWorkspace) -> str | None:
    if ws.provenance.exists():
        return read_model(ws.provenance, Provenance).performance_id
    if ws.show.exists():
        return read_model(ws.show, Show).performance_id
    return None


def library_performance_ids(root: Path) -> set[str]:
    """Performance ids of every show currently on disk, any state. The library
    half of dedup memory: what you have is never re-offered (spec §9)."""
    shows_dir = root / "shows"
    if not shows_dir.is_dir():
        return set()
    out = set()
    for d in sorted(shows_dir.iterdir()):
        if d.is_dir():
            pid = _performance_id(ShowWorkspace(d))
            if pid:
                out.add(pid)
    return out


def derive_state(ws: ShowWorkspace, delivered: set[str]) -> tuple[str, list[str]]:
    """(state, flags). held > delivered > packaged > ... > selected."""
    if ws.show.exists():
        show = read_model(ws.show, Show)
        if show.needs_review:
            return "held", show.review_flags
    pid = _performance_id(ws)
    if pid and pid in delivered:
        return "delivered", []
    if (ws.package_dir / "manifest.json").exists():
        return "packaged", []
    state = "selected"
    for attr, _, name in _STAGES:
        if getattr(ws, attr).exists():
            state = name
    return state, []


def deliver_refusals(ws: ShowWorkspace) -> list[str]:
    """Why deliver must refuse this show (empty = deliverable). Llama's whole
    deliver gate post-cut: packaged, not held for review, and every manifest
    track's audio file present on disk -- voice readiness (DJ script/audio/
    broadcast.m3u) moved to emcee and is no longer llama's concern. None of
    these three legs is overridable. Never raises."""
    manifest_path = ws.package_dir / "manifest.json"
    if not manifest_path.exists():
        return ["not packaged"]
    reasons: list[str] = []
    if ws.show.exists() and read_model(ws.show, Show).needs_review:
        reasons.append("held for review")
    manifest = read_json(manifest_path)
    tracks = manifest.get("tracks", [])
    missing = [t for t in tracks
               if not (ws.package_dir / "audio" / t["filename"]).exists()]
    if missing:
        reasons.append(f"{len(missing)} of {len(tracks)} audio files missing")
    return reasons


def iter_shows(root: Path, ledger: Ledger) -> list[CatalogEntry]:
    delivered = {e.performance_id for e in ledger.entries() if e.status == "delivered"}
    entries = []
    shows_dir = root / "shows"
    for d in sorted(shows_dir.iterdir()) if shows_dir.is_dir() else []:
        if not d.is_dir():
            continue
        ws = ShowWorkspace(d)
        state, flags = derive_state(ws, delivered)
        prov = read_model(ws.provenance, Provenance) if ws.provenance.exists() else None
        artist, date = "", ""
        if ws.show.exists():
            show = read_model(ws.show, Show)
            artist, date = show.artist, show.date
        elif prov is not None:
            artist, date = prov.candidate.collection, prov.candidate.date
        entries.append(CatalogEntry(slug=d.name, ws=ws, state=state, flags=flags,
                                    provenance=prov, artist=artist, date=date,
                                    overrides=read_overrides(ws)))
    return entries


def select_shows(entries: list[CatalogEntry], *, states: set[str] | None = None,
                 artist: str | None = None,
                 run: str | None = None) -> list[CatalogEntry]:
    out = list(entries)
    if states:
        out = [e for e in out if e.state in states]
    if artist:
        out = [e for e in out if artist.lower() in e.artist.lower()]
    if run:
        out = [e for e in out if e.provenance and e.provenance.run == run]
    return out


def _resolve(name: str, candidates: list[str], kind: str) -> str:
    if name in candidates:
        return name
    hits = [c for c in candidates if name in c]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise CatalogError(f"no {kind} matches {name!r}", [])
    raise CatalogError(f"{name!r} is ambiguous", sorted(hits))


def resolve_show(root: Path, ledger: Ledger, name: str) -> CatalogEntry:
    p = Path(name).expanduser()
    if p.is_dir():  # an existing path is an exact match
        name = p.name
    entries = {e.slug: e for e in iter_shows(root, ledger)}
    return entries[_resolve(name, sorted(entries), "show")]


def resolve_run(root: Path, name: str) -> str:
    p = Path(name).expanduser()
    if p.is_dir():  # an existing path is an exact match
        name = p.name
    runs_dir = root / "runs"
    runs = sorted(d.name for d in runs_dir.iterdir() if d.is_dir()) if runs_dir.is_dir() else []
    return _resolve(name, runs, "run")


def remove_show(entry: CatalogEntry, ledger: Ledger, *,
                forget: bool = False, suppress: bool = False) -> list[str]:
    """Delete a show dir and apply one of three history dispositions,
    returning the echo lines the CLI prints verbatim (spec §8.1).

    default: ledger untouched. forget: purges every ledger row for this
    performance id (re-eligible). suppress: appends a reversible `rejected`
    row (excluded from future gets until `llama unsuppress`). The ledger
    change (if any) happens before the rmtree so a failed disposition never
    leaves the show deleted with history in the wrong state."""
    if forget and suppress:
        raise LlamaError("cannot pass both --forget and --suppress")

    show_ws = entry.ws
    with file_lock(show_ws.lock):
        pid = _performance_id(show_ws)
        if pid is None and (forget or suppress):
            raise LlamaError(
                f"cannot resolve a performance id for {entry.slug}; history flags need one")

        if forget:
            n = ledger.remove(pid)
            history_line = f"forgot {n} history row(s): re-eligible"
        elif suppress:
            if show_ws.show.exists():
                show = read_model(show_ws.show, Show)
                artist, date, venue = show.artist, show.date, show.venue
            else:
                candidate = read_model(show_ws.provenance, Provenance).candidate
                artist, date, venue = candidate.collection, candidate.date, candidate.venue
            ledger.record(LedgerEntry(
                performance_id=pid, artist=artist, date=date, venue=venue,
                status="rejected", run="manual",
                recorded_at=datetime.now(timezone.utc).isoformat(),
            ))
            history_line = f"suppressed: will not be offered again (undo: llama unsuppress {pid})"
        else:
            rows = [e for e in ledger.entries() if pid is not None and e.performance_id == pid]
            if rows:
                statuses = ", ".join(sorted({r.status for r in rows}))
                history_line = f"history kept ({statuses}): stays excluded from future gets"
            else:
                history_line = "no history rows; this show can be re-offered"

        shutil.rmtree(show_ws.dir)
    return [f"removed shows/{entry.slug}", history_line]
