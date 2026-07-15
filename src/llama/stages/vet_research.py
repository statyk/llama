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
    """Normalize common prose date spellings to YYYY-MM-DD; None if unparseable."""
    s = re.sub(r"\s+", " ", text.strip().lower().replace(",", " ").replace(".", " ")).strip()
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
    return None


def grounding_flags(vetting: ResearchVetting, show: Show) -> list[str]:
    """Deterministic check: research assertions must match this show. Zero tokens."""
    flags: list[str] = []
    known = {normalize_song(t.title) for t in show.tracks}
    for song in vetting.asserted_songs:
        if normalize_song(song) not in known:
            flags.append(f"{_VET_FLAG_PREFIX}unknown song: {song}")
    for date_text in vetting.asserted_dates:
        norm = normalize_date(date_text)
        if norm is None:
            flags.append(f"{_VET_FLAG_PREFIX}unparseable date: {date_text}")
        elif norm != show.date:
            flags.append(f"{_VET_FLAG_PREFIX}wrong date: {date_text}")
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
