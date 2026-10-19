"""Offline replay of gather/vet over the on-disk cache: no network, no LLM.

Slice 0 of the held-backlog Tier 1 work. This module holds the cache-only
clients and the input/config/code identities the harness stamps on each arm,
and the one place the needs-LLM verdict and the outcome class are decided
(`compute_legs` + `classify`, spec ruling 5), shared by the harness and
`llama reapply`.
"""
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import llama
from llama.catalog import derive_state
from llama.config import Config
from llama.errors import LlamaError
from llama.models import Briefing, Overrides, Provenance, Show, VettingResult
from llama.setlistfm import _pick, cache_key
from llama.stages.brief import briefing_guard
from llama.stages.gather import GatherResult, compute_gather
from llama.stages.vet_research import VetOutcome, apply_vet
from llama.workspace import ShowWorkspace, read_model, read_overrides

_REFUSED = "network refused by the cache-only client"


class CacheMiss(LlamaError):
    pass


class CacheOnlyIA:
    """An archive.org client that only ever reads `md_<id>.json` from the cache."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.misses: list[str] = []

    def metadata(self, identifier: str) -> dict:
        path = self.cache_dir / f"md_{identifier}.json"
        if not path.exists():
            self.misses.append(identifier)
            raise CacheMiss(f"cache miss: md_{identifier}.json")
        return json.loads(path.read_text())

    def search(self, *args, **kwargs):
        raise CacheMiss(_REFUSED)

    def scrape(self, *args, **kwargs):
        raise CacheMiss(_REFUSED)

    def download_file(self, *args, **kwargs):
        raise CacheMiss(_REFUSED)


class CacheOnlySetlistFM:
    """A setlist.fm client that only reads the client's own cache files."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.misses: list[tuple[str, str]] = []

    def setlist(self, artist: str, date: str,
                venue: str | None = None, city: str | None = None) -> dict | None:
        path = self.cache_dir / (cache_key(artist, date) + ".json")
        if not path.exists():
            self.misses.append((artist, date))
            return None
        # Like SetlistFMClient.setlist, never raise: a corrupted cache file
        # degrades to None. Not a miss: the real client would not fetch it.
        try:
            data = json.loads(path.read_text())
            return _pick(data.get("setlist", []), venue, city)
        except Exception:
            return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def input_digests(ws: ShowWorkspace) -> dict[str, str | None]:
    """sha256 of each file the replay reads; None when absent.

    `vetting.extraction` hashes only the extraction, never the flags (which
    are derived by the arm under test).
    """
    def of(path: Path) -> str | None:
        return _sha256(path.read_bytes()) if path.exists() else None

    extraction = None
    if ws.vetting.exists():
        result = read_model(ws.vetting, VettingResult)
        extraction = _sha256(result.vetting.model_dump_json().encode())
    return {
        "show.json": of(ws.show),
        "overrides.json": of(ws.overrides),
        "provenance.json": of(ws.provenance),
        "research.md": of(ws.research),
        "vetting.extraction": extraction,
    }


def setlistfm_configured(config: Config) -> bool:
    return bool(os.environ.get("SETLISTFM_API_KEY") or config.setlistfm.api_key)


def setlistfm_client(config: Config) -> CacheOnlySetlistFM | None:
    """The one place the replay's setlist.fm client is chosen."""
    if setlistfm_configured(config):
        return CacheOnlySetlistFM(config.root / "cache")
    return None


def config_fingerprint(config: Config) -> str:
    payload = {
        "audio_format": config.audio_format,
        "structure": config.structure.model_dump(),
        "jerrybase": config.jerrybase.model_dump(),
        "setlistfm_configured": setlistfm_configured(config),
    }
    return _sha256(json.dumps(payload, sort_keys=True).encode())


def code_identity() -> str:
    """The git HEAD of the running llama (`-dirty` if uncommitted), else its version."""
    here = str(Path(llama.__file__).resolve().parent)
    try:
        sha = subprocess.run(["git", "-C", here, "rev-parse", "HEAD"], capture_output=True,
                             text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "-C", here, "status", "--porcelain"], capture_output=True,
                                text=True, check=True).stdout.strip()
        if sha:
            return sha + ("-dirty" if status else "")
    except (OSError, subprocess.CalledProcessError):
        pass
    return f"version:{llama.__version__}"


# --- flag families (plan "Contracts": Flag families) ---

# (family, predicate) in order; the first match wins. `research asserts ...`
# flags are told apart by their own texts before anything generic.
_FAMILIES: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("research-song", lambda f: f.startswith("research asserts unknown song")),
    ("research-sets", lambda f: f.startswith("research asserts ") and "sets but structure has" in f),
    ("research-date", lambda f: f.startswith("research asserts wrong date")
        or (f.startswith("research asserts ") and "looks like a year-only placeholder" in f)),
    ("structure", lambda f: f.startswith((
        "low-confidence structure alignment", "single-set structure",
        "setlist evidence shows multiple sets", "structure has ", "jerrybase set closer ",
        "low-confidence setlist", "merged track(s)"))),
    ("titles", lambda f: f.startswith("unresolved track titles")),
    ("venue", lambda f: f.startswith("venue mismatch")),
    ("city", lambda f: f.startswith("recordings of this date disagree on city")),
    ("briefing", lambda f: f.startswith("briefing ")),
    ("events", lambda f: f.startswith(("tape spans", "unassigned multi-event", "multi-event date"))),
    ("tracks", lambda f: f.startswith("no playable tracks")),
    ("package", lambda f: f.startswith("duration mismatch on ")),
)


def flag_family(flag: str) -> str:
    """The Contracts' family of a review flag; `other` when none matches."""
    for family, matches in _FAMILIES:
        if matches(flag):
            return family
    return "other"


# --- shipped fields and the briefing reuse rule ---

def _alignment(show: Show) -> str | None:
    return show.structure.alignment if show.structure is not None else None


def _pair(old, new) -> dict | None:
    return None if old == new else {"old": old, "new": new}


def shipped_diff(stored: Show, new: Show) -> dict:
    """The shipped fields (Contracts: per-track title, title_source, set, segue;
    set_breaks; venue; city; date; structure.alignment) that differ between
    the stored show and the replayed one. `[]`/`None` when equal.

    A track-count change makes per-index comparison meaningless, so every
    index up to the longer of the two is reported, in `title_changes`,
    `set_changes` and `segue_changes` alike, each side carrying its own
    track's value at that position (None past that show's end), so a
    hand-check list shows both tapes."""
    titles: list[dict] = []
    sets: list[dict] = []
    segues: list[dict] = []
    if len(stored.tracks) != len(new.tracks):
        for i in range(max(len(stored.tracks), len(new.tracks))):
            o = stored.tracks[i] if i < len(stored.tracks) else None
            n = new.tracks[i] if i < len(new.tracks) else None
            titles.append({"index": i + 1, "old": o.title if o else None,
                           "new": n.title if n else None,
                           "old_source": o.title_source if o else None,
                           "new_source": n.title_source if n else None})
            sets.append({"index": i + 1, "old": o.set if o else None,
                         "new": n.set if n else None})
            segues.append({"index": i + 1, "old": o.segue if o else None,
                           "new": n.segue if n else None})
    else:
        for o, n in zip(stored.tracks, new.tracks):
            if o.title != n.title or o.title_source != n.title_source:
                titles.append({"index": o.index, "old": o.title, "new": n.title,
                               "old_source": o.title_source, "new_source": n.title_source})
            if o.set != n.set:
                sets.append({"index": o.index, "old": o.set, "new": n.set})
            if o.segue != n.segue:
                segues.append({"index": o.index, "old": o.segue, "new": n.segue})
    return {
        "title_changes": titles,
        "venue": _pair(stored.venue, new.venue),
        "city": _pair(stored.city, new.city),
        "set_changes": sets,
        "segue_changes": segues,
        "set_breaks": _pair(list(stored.set_breaks), list(new.set_breaks)),
        "alignment": _pair(_alignment(stored), _alignment(new)),
        "date": _pair(stored.date, new.date),
    }


def _structure_changed(diff: dict) -> bool:
    """Spec "structure-changed": set or segue labels, set_breaks or alignment."""
    return bool(diff["set_changes"] or diff["segue_changes"]
                or diff["set_breaks"] or diff["alignment"])


def briefing_reusable(stored_show: Show, new_show: Show, briefing: Briefing,
                      narration: str) -> str | None:
    """Spec slice 6 step 3, the reuse rule: None when the stored briefing can
    ship with `new_show`; else the first failing reason. Broadcast fields are
    per-track titles, sets and segues, set_breaks, date, venue, city
    (title_source is not one: the briefing never sees it)."""
    o, n = stored_show, new_show
    changed = [name for name, differs in (
        ("titles", [t.title for t in o.tracks] != [t.title for t in n.tracks]),
        ("sets", [t.set for t in o.tracks] != [t.set for t in n.tracks]),
        ("segues", [t.segue for t in o.tracks] != [t.segue for t in n.tracks]),
        ("set_breaks", o.set_breaks != n.set_breaks),
        ("date", o.date != n.date),
        ("venue", o.venue != n.venue),
        ("city", o.city != n.city),
    ) if differs]
    if changed:
        return f"broadcast fields changed: {', '.join(changed)}"
    if briefing.narration != narration:
        return f"narration differs: briefing {briefing.narration}, overrides {narration}"
    problems = briefing_guard(briefing, new_show)
    if problems:
        return f"briefing guard: {'; '.join(problems)}"
    return None


# --- the three legs ---

@dataclasses.dataclass
class Legs:
    """One show's deterministic replay: gather (LLM-free), vet (over the stored
    extraction) and the brief reuse decision. Nothing here is written."""
    gather: GatherResult
    stored: Show
    vet: VetOutcome | None
    # gather's verdicts, then "stored alignment llm", then "no vetting.json"
    needs_llm: list[str]
    brief: str                     # "reuse" | "fresh" | "none"
    brief_reason: str | None       # why a stored briefing.json is not reused
    brief_flags: list[str]
    briefing: Briefing | None      # the stored briefing, only when brief == "reuse"
    carried_flags: list[str]       # stored `package`-family flags, carried through
    flags: list[str]               # gather + vet + carried + brief_flags

    @property
    def replayed_show(self) -> Show:
        """The replayed show with vet applied: what would ship."""
        return self.vet.show if self.vet is not None else self.gather.show


def compute_legs(ws: ShowWorkspace, *, config: Config, ia, slfm: "CacheOnlySetlistFM | None",
                 scratch: Path) -> Legs:
    """Replay one library show into `scratch` (recreated empty, then given a
    copy of `overrides.json` and nothing else); `ws.dir` is only read.

    `slfm` is `setlistfm_client(config)` and nothing else (None when no key is
    configured), so the replay sees what `process_show` would. `CacheMiss`
    propagates; a missing `provenance.json`/`show.json` is a `LlamaError`.
    A `scratch` that is, contains or lies inside `ws.dir`, or lies inside the
    library's `shows/` (`ws.dir.parent`: another show's directory), is refused
    before anything is deleted: the recreate is an rmtree."""
    show_dir, scr = ws.dir.resolve(), scratch.resolve()
    if scr == show_dir or show_dir in scr.parents or scr in show_dir.parents:
        raise LlamaError(f"refusing scratch {scratch}: it overlaps the show directory {ws.dir}")
    if show_dir.parent in scr.parents:
        raise LlamaError(f"refusing scratch {scratch}: it lies inside the library's shows "
                         f"directory {ws.dir.parent}")
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    if ws.overrides.exists():
        shutil.copyfile(ws.overrides, scratch / ws.overrides.name)
    for path in (ws.provenance, ws.show):
        if not path.exists():
            raise LlamaError(f"cannot replay {ws.dir.name}: missing {path.name}")
    prov = read_model(ws.provenance, Provenance)
    stored = read_model(ws.show, Show)

    gathered = compute_gather(
        ShowWorkspace(scratch), ia, None, prov.candidate, stored.identifier,
        audio_format=config.audio_format, align_provider=None, setlistfm=slfm,
        structure_cfg=config.structure, jerrybase_enabled=config.jerrybase.enabled)
    needs_llm = list(gathered.needs_llm)
    if stored.structure is not None and stored.structure.alignment == "llm":
        needs_llm.append("stored alignment llm")

    vet: VetOutcome | None = None
    if ws.vetting.exists():
        vet = apply_vet(read_model(ws.vetting, VettingResult).vetting, gathered.show)
    else:
        needs_llm.append("no vetting.json")
    replayed = vet.show if vet is not None else gathered.show

    carried = [f for f in stored.review_flags if flag_family(f) == "package"]
    # The gate counts carried package flags too: a show that stays held on
    # one gets no brief (spec slice 6 step 3: "only when steps 1 and 2 left
    # no flag", and reapply never clears a carried package flag).
    flags = list(gathered.show.review_flags) + (list(vet.result.flags) if vet else []) + carried

    brief, reason, brief_flags, briefing = "none", None, [], None
    if not flags:
        brief = "fresh"
        if ws.briefing_json.exists():
            stored_briefing = read_model(ws.briefing_json, Briefing)
            reason = briefing_reusable(stored, replayed, stored_briefing,
                                       read_overrides(ws).narration)
            if reason is None:
                brief, briefing = "reuse", stored_briefing
                brief_flags = briefing_guard(stored_briefing, replayed)  # [] by construction

    return Legs(gather=gathered, stored=stored, vet=vet, needs_llm=needs_llm, brief=brief,
                brief_reason=reason, brief_flags=brief_flags, briefing=briefing,
                carried_flags=carried, flags=flags + brief_flags)


# --- outcome classification (plan "Contracts": Outcome classes) ---

def classify(legs: Legs, stored_state: str) -> tuple[str, str | None]:
    """`(outcome, would_be)`. needs-LLM is decided first and admits no
    exception (spec ruling 5; "No stored vetting.json means needs-LLM"), then
    held shows (`stored_state == "held"`) and non-held shows apart."""
    if legs.needs_llm:
        return "needs-llm", None
    diff = shipped_diff(legs.stored, legs.replayed_show)
    if stored_state == "held":
        if legs.carried_flags:
            return "still-held-package", None
        if legs.flags:
            return "still-held", None
        would_be = "clears" if legs.brief == "reuse" else "needs-brief"
        if _structure_changed(diff):
            return "structure-changed", would_be
        return would_be, None
    if legs.flags:
        return "newly-held", None
    if any(diff.values()):
        return "clean-changed", None
    return "clean", None


@dataclasses.dataclass
class ShowReplay:
    """One show's row in a harness arm (plan "Contracts": ShowReplay), plus
    `date` beside `venue`/`city` (orchestrator ruling M7: date is a shipped
    field). Filled by `replay_show` (Task 5)."""
    slug: str
    state: str
    stored_flags: list[str] = dataclasses.field(default_factory=list)
    stored_core_flags: list[str] = dataclasses.field(default_factory=list)
    gather_flags: list[str] = dataclasses.field(default_factory=list)
    vet_flags: list[str] = dataclasses.field(default_factory=list)
    brief_flags: list[str] = dataclasses.field(default_factory=list)
    stored_brief_guard: list[str] | None = None
    needs_llm: list[str] = dataclasses.field(default_factory=list)
    outcome: str = ""
    would_be: str | None = None
    briefing: str = "none"
    reproduces: bool = False
    title_changes: list[dict] = dataclasses.field(default_factory=list)
    venue: dict | None = None
    city: dict | None = None
    date: dict | None = None
    selected_venue: str | None = None
    selected_city: str | None = None
    set_changes: list[dict] = dataclasses.field(default_factory=list)
    segue_changes: list[dict] = dataclasses.field(default_factory=list)
    set_breaks: dict | None = None
    alignment: dict | None = None
    notes: list[str] = dataclasses.field(default_factory=list)
    digests: dict = dataclasses.field(default_factory=dict)
    slfm_miss: bool = False
    unreplayable: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class _OverridesUnreadable(Exception):
    pass


def _selected(prov: Provenance, identifier: str) -> tuple[str | None, str | None]:
    """The stripped non-empty `venue`/`coverage` of the provenance candidate's
    recording `identifier` (Contracts: selected_venue/selected_city)."""
    for rec in prov.candidate.recordings:
        if rec.identifier == identifier:
            return (rec.venue or "").strip() or None, (rec.coverage or "").strip() or None
    return None, None


def replay_show(ws: ShowWorkspace, *, config: Config, ia, slfm: "CacheOnlySetlistFM | None",
                scratch: Path, delivered: set[str]) -> ShowReplay:
    """One show's arm row (plan "Contracts": ShowReplay). Never raises for a
    per-show failure: a cache miss, an unreadable `overrides.json` or any
    other exception is recorded as `outcome="unreplayable"`, so one bad show
    cannot stop a run. Writes only into `scratch` (via `compute_legs`).

    The stored-side fields (stored/core flags, stored_brief_guard,
    selected_venue/city) are filled before the replay, so they are present
    for a needs-LLM show and, where readable, for an unreplayable one."""
    r = ShowReplay(slug=ws.dir.name, state="unknown")
    misses = len(slfm.misses) if slfm is not None else 0
    try:
        r.state = derive_state(ws, delivered)[0]
        if ws.overrides.exists():
            try:
                read_model(ws.overrides, Overrides)
            except (OSError, ValueError) as err:   # pydantic ValidationError is a ValueError
                raise _OverridesUnreadable() from err
        r.digests = input_digests(ws)
        if ws.show.exists():
            stored = read_model(ws.show, Show)
            r.stored_flags = list(stored.review_flags)
            r.stored_core_flags = [f for f in stored.review_flags
                                   if flag_family(f) not in ("package", "briefing")]
            if ws.briefing_json.exists():
                r.stored_brief_guard = briefing_guard(read_model(ws.briefing_json, Briefing),
                                                      stored)
            if ws.provenance.exists():
                r.selected_venue, r.selected_city = _selected(
                    read_model(ws.provenance, Provenance), stored.identifier)

        legs = compute_legs(ws, config=config, ia=ia, slfm=slfm, scratch=scratch)
        r.gather_flags = list(legs.gather.show.review_flags)
        r.vet_flags = list(legs.vet.result.flags) if legs.vet is not None else []
        r.brief_flags = list(legs.brief_flags)
        r.needs_llm = list(legs.needs_llm)
        r.briefing = legs.brief
        r.outcome, r.would_be = classify(legs, r.state)
        r.reproduces = sorted(r.stored_core_flags) == sorted(r.gather_flags + r.vet_flags)
        diff = shipped_diff(legs.stored, legs.replayed_show)
        for key in ("title_changes", "venue", "city", "date", "set_changes",
                    "segue_changes", "set_breaks", "alignment"):
            setattr(r, key, diff[key])
        r.notes = list(legs.gather.notes) + (list(legs.vet.notes) if legs.vet is not None else [])
    except CacheMiss as err:
        r.outcome, r.unreplayable = "unreplayable", str(err)
    except _OverridesUnreadable:
        r.outcome, r.unreplayable = "unreplayable", "overrides.json unreadable"
    except Exception as err:
        r.outcome, r.unreplayable = "unreplayable", f"{type(err).__name__}: {err}"[:200]
    if r.unreplayable is not None:
        r.reproduces = False
    r.slfm_miss = slfm is not None and len(slfm.misses) > misses
    return r
