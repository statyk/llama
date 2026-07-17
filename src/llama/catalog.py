"""Show/run discovery: derived state, iteration, and name resolution.

State is never stored; it is derived from which artifacts exist plus the
ledger, so it cannot go stale. Scan-on-demand — at this scale (~10^2 shows)
a walk is milliseconds.
"""
from dataclasses import dataclass, field
from pathlib import Path

from llama.ledger import Ledger
from llama.models import Provenance, Show
from llama.workspace import ShowWorkspace, read_model


class CatalogError(Exception):
    """Resolution failure; matches lists the candidates (empty = no match)."""

    def __init__(self, message: str, matches: list[str] | None = None):
        super().__init__(message)
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


# (artifact attribute, depth, state name) from shallowest to deepest.
_STAGES = [
    ("selection", 1, "selected"),
    ("show", 2, "gathered"),
    ("research", 3, "researched"),
    ("vetting", 4, "vetted"),
    ("dj_notes_json", 5, "scripted"),
]
STAGE_DEPTH = {"select": 1, "gather": 2, "research": 3, "vet": 4,
               "synthesize": 5, "package": 6}


def stage_depth(ws: ShowWorkspace) -> int:
    """Deepest completed stage (0 = nothing). Used for migration collisions."""
    depth = 0
    for attr, d, _ in _STAGES:
        if getattr(ws, attr).exists():
            depth = d
    if (ws.package_dir / "manifest.json").exists():
        depth = 6
    return depth


def _performance_id(ws: ShowWorkspace) -> str | None:
    if ws.provenance.exists():
        return read_model(ws.provenance, Provenance).performance_id
    if ws.show.exists():
        return read_model(ws.show, Show).performance_id
    return None


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
                                    provenance=prov, artist=artist, date=date))
    return entries


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
    if p.is_dir() and (p / "criteria.json").exists():
        name = p.name
    runs_dir = root / "runs"
    runs = sorted(d.name for d in runs_dir.iterdir() if d.is_dir()) if runs_dir.is_dir() else []
    return _resolve(name, runs, "run")


def legacy_show_dirs(root: Path) -> list[Path]:
    """Show directories still nested under runs (pre-migration layout)."""
    runs_dir = root / "runs"
    if not runs_dir.is_dir():
        return []
    return sorted(d for d in runs_dir.glob("*/shows/*") if d.is_dir())
