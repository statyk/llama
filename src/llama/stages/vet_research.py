import re

from llama.llm.tasks import run_json_task
from llama.models import ResearchVetting, Show, VettingResult
from llama.songs import normalize_song
from llama.workspace import ShowWorkspace, read_model, should_run, write_artifact

# Every deterministic grounding flag starts with this prefix, so a re-vet can strip
# its own prior flags without disturbing flags from other stages (duration, guard).
_VET_FLAG_PREFIX = "research asserts "

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


def normalize_date(text: str) -> str | None:
    """Normalize common prose date spellings to YYYY-MM-DD; year-less forms
    ("December 2") to ISO 8601 --MM-DD; None if unparseable."""
    s = re.sub(r"\s+", " ", text.strip().lower().replace(",", " ").replace(".", " ")).strip()
    s = re.sub(r"^(?:mon|tues?|wed(?:nes)?|thur?s?|fri|sat(?:ur)?|sun)(?:day)? ", "", s)
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if m:
        return f"{_year(int(m[3])):04d}-{int(m[1]):02d}-{int(m[2]):02d}"
    m = re.fullmatch(r"([a-z]+) (\d{1,2})(?:st|nd|rd|th)? '?(\d{2,4})", s)
    if m and _month(m[1]):
        return f"{_year(int(m[3])):04d}-{_month(m[1]):02d}-{int(m[2]):02d}"
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)? ([a-z]+) '?(\d{2,4})", s)
    if m and _month(m[2]):
        return f"{_year(int(m[3])):04d}-{_month(m[2]):02d}-{int(m[1]):02d}"
    m = re.fullmatch(r"([a-z]+) (\d{1,2})(?:st|nd|rd|th)?", s)
    if m and _month(m[1]):
        return f"--{_month(m[1]):02d}-{int(m[2]):02d}"
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)? ([a-z]+)", s)
    if m and _month(m[2]):
        return f"--{_month(m[2]):02d}-{int(m[1]):02d}"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", s)
    if m:
        return f"--{int(m[1]):02d}-{int(m[2]):02d}"
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


def grounding_flags(vetting: ResearchVetting, show: Show) -> list[str]:
    """Deterministic check: research contradicting this show flags for review.
    The gate exists to catch wrong-show research, so a couple of unmatched
    titles (tracklist gaps, odd variants) pass; a mostly-unmatched set, or a
    date that belongs to a different show, blocks. Zero tokens."""
    flags: list[str] = []
    known = [normalize_song(t.title).split() for t in show.tracks]
    unknown = [s for s in vetting.asserted_songs if not _known_song(s, known)]
    if len(unknown) >= 2 and len(unknown) * 3 > len(vetting.asserted_songs):
        flags += [f"{_VET_FLAG_PREFIX}unknown song: {s}" for s in unknown]
    for date_text in vetting.asserted_dates:
        norm = normalize_date(date_text)
        if norm is None:
            continue  # can't verify is not a contradiction; kept in vetting.json
        if norm.startswith("--"):  # year-less: match on month and day
            if not show.date.endswith(norm[1:]):
                flags.append(f"{_VET_FLAG_PREFIX}wrong date: {date_text}")
        elif norm != show.date:
            flags.append(f"{_VET_FLAG_PREFIX}wrong date: {date_text}")
    if vetting.asserted_set_count is not None and show.tracks:
        actual = len({t.set for t in show.tracks if t.set != "encore"})
        if vetting.asserted_set_count != actual:
            flags.append(
                f"{_VET_FLAG_PREFIX}{vetting.asserted_set_count} sets"
                f" but structure has {actual}"
            )
    return flags


def run_vet_research(
    show_ws: ShowWorkspace, provider, show: Show, research_md: str, force: bool = False,
) -> VettingResult:
    if not should_run(show_ws.vetting, force):
        return read_model(show_ws.vetting, VettingResult)
    vetting = run_json_task(provider, "vet_research", ResearchVetting, research=research_md)
    flags = grounding_flags(vetting, show)
    # Rewrite show.json every run: drop our own prior flags (so a corrected re-vet clears
    # needs_review and repeats don't duplicate), keep flags from other stages, and recompute.
    current = read_model(show_ws.show, Show)
    kept = [f for f in current.review_flags if not f.startswith(_VET_FLAG_PREFIX)]
    current.review_flags = kept + flags
    current.needs_review = bool(current.review_flags)
    write_artifact(show_ws.show, current)
    result = VettingResult(vetting=vetting, flags=flags)
    write_artifact(show_ws.vetting, result)
    return result
