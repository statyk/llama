import re
from datetime import date as _date
from typing import NamedTuple

from herder import run_json_task
from llama.models import ResearchVetting, Show, ShowNotes, VettingResult
from llama.prompts import load_prompt
from llama.songs import normalize_song
from llama.structure import TAUTOLOGICAL_TITLE_SOURCES, is_filler
from llama.workspace import ShowWorkspace, read_model, should_run, write_artifact

# Every deterministic grounding flag starts with this prefix, so a re-vet can strip
# its own prior flags without disturbing flags from other stages (duration, guard).
_VET_FLAG_PREFIX = "research asserts "

# Slice 4 - 4b (spec "New constants"): another asserted full date within this
# many days of the show's own asserted full date is context, not a contradiction.
ADJACENT_DAY_WINDOW = 1

# Slice 4 - 4a (spec "New constants"): the right-show gate. At least this fraction
# of the tape's resolved, non-filler, non-tautological tracks must be asserted by
# research, and at least this many of them. RIGHT_SHOW_MIN_TAPE_FRACTION may move
# to `2 / 3` (written exactly so) only at 4a's decision point (Checkpoint E),
# before shipping; never retuned after.
RIGHT_SHOW_MIN_TAPE_FRACTION = 0.5
RIGHT_SHOW_MIN_ASSERTED = 4

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}


def _month(name: str) -> int | None:
    if name in _MONTHS:
        return _MONTHS[name]
    if len(name) >= 3:
        hits = [i for full, i in _MONTHS.items() if full.startswith(name)]
        if len(hits) == 1:
            return hits[0]
    return None


def _year(y: int) -> int:
    """Two-digit years: LMA coverage is overwhelmingly 20th-century."""
    if y >= 100:
        return y
    return 1900 + y if y >= 30 else 2000 + y


def _valid_ymd(y: int, m: int, d: int) -> bool:
    """Range check only (spec Slice 4 - 4c); a calendar-exact check is not needed."""
    return 1 <= m <= 12 and 1 <= d <= 31


def normalize_date(text: str) -> str | None:
    """Normalize common prose date spellings to YYYY-MM-DD; year-less forms
    ("December 2") to ISO 8601 --MM-DD; None if unparseable or out of range.
    A slash form that is invalid month-first but valid day-first is read
    day-first (spec Slice 4 - 4c)."""
    s = re.sub(r"\s+", " ", text.strip().lower().replace(",", " ").replace(".", " ")).strip()
    s = re.sub(r"^(?:mon|tues?|wed(?:nes)?|thur?s?|fri|sat(?:ur)?|sun)(?:day)? ", "", s)

    def full(y: int, mo: int, d: int) -> str | None:
        return f"{y:04d}-{mo:02d}-{d:02d}" if _valid_ymd(y, mo, d) else None

    def noyear(mo: int, d: int) -> str | None:
        return f"--{mo:02d}-{d:02d}" if _valid_ymd(0, mo, d) else None

    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return full(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if m:
        y = _year(int(m[3]))
        return full(y, int(m[1]), int(m[2])) or full(y, int(m[2]), int(m[1]))
    m = re.fullmatch(r"([a-z]+) (\d{1,2})(?:st|nd|rd|th)? '?(\d{2,4})", s)
    if m and _month(m[1]):
        return full(_year(int(m[3])), _month(m[1]), int(m[2]))
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)? ([a-z]+) '?(\d{2,4})", s)
    if m and _month(m[2]):
        return full(_year(int(m[3])), _month(m[2]), int(m[1]))
    m = re.fullmatch(r"([a-z]+) (\d{1,2})(?:st|nd|rd|th)?", s)
    if m and _month(m[1]):
        return noyear(_month(m[1]), int(m[2]))
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)? ([a-z]+)", s)
    if m and _month(m[2]):
        return noyear(_month(m[2]), int(m[1]))
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", s)
    if m:
        return noyear(int(m[1]), int(m[2])) or noyear(int(m[2]), int(m[1]))
    return None


_SEGUE_SPLIT = re.compile(r"\s*(?:->|>|→)\s*")


def _run_contained(short: list[str], long: list[str]) -> bool:
    n = len(short)
    return 0 < n <= len(long) and any(long[i:i + n] == short for i in range(len(long) - n + 1))


def _title_match(name: str, known: list[list[str]]) -> bool:
    """Prose titles are loose: "Caution" for "Caution (Do Not Step on
    Tracks)", "One More Saturday Night" for a track titled "Saturday Night".
    Match when either side's tokens appear as a contiguous run in the other."""
    tokens = normalize_song(name).split()
    return bool(tokens) and any(
        _run_contained(tokens, k) or _run_contained(k, tokens) for k in known
    )


def _known_song(name: str, known: list[list[str]]) -> bool:
    """Research prose asserts songs in standard live notation: single titles,
    segue chains ("China Cat Sunflower > I Know You Rider"), and comma-joined
    runs. Exact whole match first (a merged track may be titled with the full
    chain, and titles may contain commas); then a chain is known only if
    EVERY part is. Loose containment applies only to atomic titles - a chain
    must never pass just because one real song appears in it."""
    tokens = normalize_song(name).split()
    if any(tokens == k for k in known):
        return True
    parts = [p for p in _SEGUE_SPLIT.split(name) if p.strip()]
    if len(parts) > 1:
        return all(_known_song(p, known) for p in parts)
    parts = [p for p in name.split(",") if p.strip()]
    if len(parts) > 1:
        return all(_known_song(p, known) for p in parts)
    return _title_match(name, known)


def _within_window(a: str, b: str) -> bool:
    try:
        return abs((_date.fromisoformat(a) - _date.fromisoformat(b)).days) <= ADJACENT_DAY_WINDOW
    except ValueError:
        return False  # e.g. day 31 in a 30-day month: not comparable, keep the flag


def _date_flags(
    mismatched: dict[str, str], yearless: dict[str, str], show: Show,
    placeholder: bool, adopted: str | None,
) -> list[str]:
    """The date flags for a set of mismatched full dates; none when a date is adopted."""
    out: list[str] = []
    if adopted is not None:
        return out
    for norm, text in mismatched.items():
        if placeholder:
            out.append(
                f"{_VET_FLAG_PREFIX}{norm}; item date {show.date}"
                " looks like a year-only placeholder"
            )
        else:
            out.append(f"{_VET_FLAG_PREFIX}wrong date: {text}")
    for norm, text in yearless.items():  # year-less: match on month and day
        if not show.date.endswith(norm[1:]):
            out.append(f"{_VET_FLAG_PREFIX}wrong date: {text}")
    return out


def right_show_gate(
    vetting: ResearchVetting, show: Show, *, date_flags_raw: list[str],
) -> tuple[bool, dict]:
    """Slice 4 - 4a: do the tape and the research demonstrably describe the same
    show? Only then may unknown-song flags become a vet note. Tautological titles
    (their text IS the canonical's) count on neither side; the date flags are the
    ones read BEFORE 4b's adjacent-day window; the own date must be a full date,
    year included. Returns (holds, info) with info's counts for the note."""
    research_known = [normalize_song(s).split() for s in vetting.asserted_songs]
    resolved = [
        t for t in show.tracks
        if t.title_source != "unresolved"
        and not is_filler(t.title)
        and t.title_source not in TAUTOLOGICAL_TITLE_SOURCES
    ]
    asserted = [t for t in resolved if _known_song(t.title, research_known)]
    tape_known = [normalize_song(t.title).split() for t in show.tracks]
    unknown = [s for s in vetting.asserted_songs if not _known_song(s, tape_known)]
    unresolved_n = sum(1 for t in show.tracks if t.title_source == "unresolved")
    date_text = next(
        (d for d in vetting.asserted_dates if normalize_date(d) == show.date), None
    )
    own_full = date_text is not None
    holds = (
        len(resolved) > 0
        and len(asserted) >= RIGHT_SHOW_MIN_TAPE_FRACTION * len(resolved)
        and len(asserted) >= RIGHT_SHOW_MIN_ASSERTED
        and len(unknown) <= len(asserted)
        and unresolved_n * 2 < len(show.tracks)
        and not date_flags_raw
        and own_full
    )
    info = {
        "asserted": len(asserted),
        "resolved": len(resolved),
        "ratio": len(asserted) / len(resolved) if resolved else 0.0,
        "unknown": unknown,
        "date_text": date_text,
    }
    return holds, info


def grounding_flags(vetting: ResearchVetting, show: Show) -> tuple[list[str], str | None, list[str]]:
    """Deterministic check: research contradicting this show flags for review.
    The gate exists to catch wrong-show research, so a couple of unmatched
    titles (tracklist gaps, odd variants) pass; a mostly-unmatched set, or a
    date that belongs to a different show, blocks. One exception: an archive
    year-only placeholder date (YYYY-01-01) contradicted by unanimous,
    well-grounded research is corrected, not flagged - returns the adopted
    date as the second element; the third is the vet notes (operator-facing,
    never flags). Zero tokens."""
    flags: list[str] = []
    notes: list[str] = []
    known = [normalize_song(t.title).split() for t in show.tracks]
    unknown = [s for s in vetting.asserted_songs if not _known_song(s, known)]
    songs_grounded = not (len(unknown) >= 2 and len(unknown) * 3 > len(vetting.asserted_songs))

    full: dict[str, str] = {}      # normalized YYYY-MM-DD -> first surface text
    yearless: dict[str, str] = {}  # normalized --MM-DD -> first surface text
    for text in vetting.asserted_dates:
        norm = normalize_date(text)
        if norm is None:
            continue  # can't verify is not a contradiction; kept in vetting.json
        (yearless if norm.startswith("--") else full).setdefault(norm, text)

    mismatched_raw = {n: t for n, t in full.items() if n != show.date}
    placeholder = show.date.endswith("-01-01") and show.date_source == "item"
    adopted: str | None = None
    if placeholder and songs_grounded and len(full) == 1 and len(mismatched_raw) == 1:
        candidate = next(iter(mismatched_raw))
        if candidate[:4] == show.date[:4] and all(
            candidate.endswith(y[1:]) for y in yearless
        ):
            adopted = candidate

    # 4b: when research asserts the show's own full date, a full date within one
    # day of it is context. Adoption above reads the unwindowed set.
    own_full = show.date in full
    mismatched = {
        n: t for n, t in mismatched_raw.items()
        if not (own_full and _within_window(n, show.date))
    }
    # 4a reads date_flags_raw: the date flags WITHOUT the 4b window, so research
    # about an adjacent night that names this show's date still disqualifies it.
    date_flags_raw = _date_flags(mismatched_raw, yearless, show, placeholder, adopted)
    if not songs_grounded:
        ok, info = right_show_gate(vetting, show, date_flags_raw=date_flags_raw)
        if ok:
            notes.append(
                "unknown-song flags suppressed by the right-show gate: "
                f"{info['asserted']}/{info['resolved']} tape tracks asserted "
                f"(ratio {info['ratio']:.2f}), {len(info['unknown'])} unclaimed: "
                f"{'; '.join(info['unknown'])}; research date: {info['date_text']}"
            )
        else:
            flags += [f"{_VET_FLAG_PREFIX}unknown song: {s}" for s in unknown]
    flags += _date_flags(mismatched, yearless, show, placeholder, adopted)

    # Set-count check is independent of the date decision: an adoption must
    # not swallow a genuine structure contradiction.
    if vetting.asserted_set_count is not None and show.tracks:
        actual = len({t.set for t in show.tracks if t.set != "encore"})
        if vetting.asserted_set_count != actual:
            flags.append(
                f"{_VET_FLAG_PREFIX}{vetting.asserted_set_count} sets"
                f" but structure has {actual}"
            )
    return flags, adopted, notes


class VetOutcome(NamedTuple):
    show: Show
    result: VettingResult
    notes: list[str]


def apply_vet(vetting: ResearchVetting, show: Show) -> VetOutcome:
    """Pure grounding step: ground `vetting` against `show` and return a copy of
    `show` with the date adoption applied and its own `research asserts ` flags
    replaced (flags from other stages kept). Nothing is written."""
    flags, adopted, notes = grounding_flags(vetting, show)
    out = show.model_copy(deep=True)
    if adopted:
        out.item_date = out.date
        out.date = adopted
        out.date_source = "research"
    kept = [f for f in out.review_flags if not f.startswith(_VET_FLAG_PREFIX)]
    out.review_flags = kept + flags
    out.needs_review = bool(out.review_flags)
    return VetOutcome(out, VettingResult(vetting=vetting, flags=flags, adopted_date=adopted), notes)


def run_vet_research(
    show_ws: ShowWorkspace, provider, show: Show, research_md: str, force: bool = False,
) -> VettingResult:
    if not should_run(show_ws.vetting, force):
        return read_model(show_ws.vetting, VettingResult)
    vetting = run_json_task(provider, "vet_research", ResearchVetting,
                            template=load_prompt("vet_research"), research=research_md)
    # Grounds against show.json as read from disk, not the `show` parameter: the
    # only caller (pipeline.process_show) passes run_gather's return value, which
    # is exactly what run_gather just wrote to show.json, so the two are equal.
    # Rewrite show.json every run so a corrected re-vet clears needs_review and
    # repeats don't duplicate.
    out = apply_vet(vetting, read_model(show_ws.show, Show))
    write_artifact(show_ws.show, out.show)
    notes = read_model(show_ws.notes, ShowNotes) if show_ws.notes.exists() else ShowNotes()
    notes.vet = out.notes
    write_artifact(show_ws.notes, notes)
    # vetting.json is the stage's done-marker (should_run), so it is written last.
    write_artifact(show_ws.vetting, out.result)
    return out.result
