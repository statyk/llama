# Jerrybase Structure Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vendor the deadstream jerrybase-derived `set_breaks.csv` and use it as an offline structure-evidence source in `gather` — a tripwire for bad structure (multi-event dates, venue mismatches, contradicted set breaks, wrong set count) and a narrow deterministic corrector (break anchoring from set closers).

**Architecture:** A new `src/llama/data/` subpackage holds the byte-identical CSV. A defensive `src/llama/jerrybase.py` module (mirroring `setlistfm.py` — nothing raises, absence degrades to empty results) lazily parses the CSV into a `(artist_key, date) -> list[JerrybaseEvent]` index. `stages/gather.py` consults it after deterministic alignment; every step is a no-op for artists absent from the dataset, so behavior for them is byte-identical to today.

**Tech Stack:** Python 3.11+, Pydantic v2, stdlib `csv`, `importlib.resources`, hatchling packaging, PyInstaller, pytest (offline, `fake` LLM backend).

## Global Constraints

These apply to **every** task below; each task's requirements implicitly include them.

- **Defensive posture:** nothing in `jerrybase.py` raises. Any failure (missing file, malformed rows, bad values) degrades to an empty result and logs a warning — copied verbatim from `setlistfm.py`'s contract.
- **Canonical set vocabulary:** set names are exactly `"1" | "2" | "3" | "encore"`. `break_length` is exactly `"long" | "short"`.
- **Byte-identical vendoring:** `src/llama/data/set_breaks.csv` must be byte-identical to the pinned deadstream ref. Pin: deadstream `main` HEAD commit `adc6f827ae42861b5220ebd7fb9c3fa83abbeec3` (2026-06-28). The CSV content itself last changed in commit `5de5ad46ca2bc13ee3cf7630a66633db8ca67076` (2023-04-26, "added ratdog"). It has a header row + 18074 data rows; columns: `date,artist,event_id,venue,city,state,show_set,time,song,song_n,isong,next_set,Nevents,ievent,break_length`.
- **No runtime network:** the pipeline never fetches the CSV. Only `scripts/refresh_jerrybase.py` (manual) touches the network.
- **Offline deterministic tests:** all tests run offline with the `fake` LLM backend, via `pytest -q`. Unit tests assert against the real vendored CSV (in-package, deterministic).
- **Default enabled at config level (`[jerrybase] enabled = true`), opt-in at the function boundary:** `run_gather`'s `jerrybase_enabled` parameter defaults to `False` so existing gather unit tests stay isolated; the pipeline passes `config.jerrybase.enabled` (default `True`) so production behavior is on. (See "Resolved ambiguities" at the end.)
- **GPL-3.0 data** is vendored deliberately (owner intends to license llama GPL). Record provenance in the data README.
- **stdlib `csv`** parses the file (it contains quoted commas, e.g. `"Barton Hall, Cornell University"`).

---

## File Structure

- **Create** `src/llama/data/__init__.py` — makes `llama.data` an importable package for `importlib.resources`.
- **Create** `src/llama/data/set_breaks.csv` — the vendored dataset (byte-identical).
- **Create** `src/llama/data/README.md` — provenance record.
- **Create** `scripts/refresh_jerrybase.py` — manual refresh tool (no pipeline use, no pytest).
- **Create** `src/llama/jerrybase.py` — lookup module: `artist_key`, `normalize_set_label`, `build_index`, `lookup`, `anchor_breaks`, `closer_contradictions`.
- **Create** `tests/test_jerrybase.py` — unit tests.
- **Modify** `src/llama/models.py` — add `JerrybaseSet`, `JerrybaseEvent`, and `Show.venue_source`.
- **Modify** `src/llama/structure.py` — extend `structure_guard` with `expected_set_count`.
- **Modify** `src/llama/config.py` — add `JerrybaseConfig`, mount it, add to `DEFAULT_CONFIG_TOML`.
- **Modify** `src/llama/stages/gather.py` — jerrybase integration in `run_gather`.
- **Modify** `src/llama/pipeline.py` + `src/llama/cli.py` — thread `jerrybase_enabled`.
- **Modify** `src/llama/cli.py` (`show` command) — venue-adoption provenance display.
- **Modify** `packaging/llama.spec` — `collect_data_files("llama.data")`.
- **Modify** `CLAUDE.md` — one documentation line.
- **Modify** `tests/test_stage_gather.py`, `tests/test_structure.py`, `tests/test_config.py`, `tests/test_cli_commands.py` — new tests.

---

## Task 1: Vendored data subpackage

**Files:**
- Create: `src/llama/data/__init__.py`
- Create: `src/llama/data/set_breaks.csv`
- Create: `src/llama/data/README.md`
- Test: `tests/test_jerrybase.py`

**Interfaces:**
- Produces: the importable resource `llama.data / "set_breaks.csv"`, loadable via `importlib.resources.files("llama.data").joinpath("set_breaks.csv")`. Header + 18074 data rows; columns listed in Global Constraints.

- [ ] **Step 1: Write the failing test**

Create `tests/test_jerrybase.py`:

```python
import csv
from importlib import resources


def test_vendored_csv_is_present_and_well_formed():
    path = resources.files("llama.data").joinpath("set_breaks.csv")
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 18074
    assert list(rows[0].keys()) == [
        "date", "artist", "event_id", "venue", "city", "state", "show_set",
        "time", "song", "song_n", "isong", "next_set", "Nevents", "ievent",
        "break_length",
    ]
    # A known row survives quoted-comma parsing intact.
    cornell = [r for r in rows if r["date"] == "1977-05-08" and r["artist"] == "GratefulDead"]
    assert any(r["venue"] == "Barton Hall, Cornell University" for r in cornell)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jerrybase.py::test_vendored_csv_is_present_and_well_formed -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.data'` (or file-not-found).

- [ ] **Step 3: Create the subpackage marker**

Create `src/llama/data/__init__.py` with exactly this content (one line):

```python
"""Vendored offline datasets. See README.md for provenance."""
```

- [ ] **Step 4: Vendor the CSV byte-identically**

Download the pinned file directly into place (the SHA-pinned URL guarantees identical bytes forever):

```bash
curl -sfL \
  "https://raw.githubusercontent.com/eichblatt/deadstream/adc6f827ae42861b5220ebd7fb9c3fa83abbeec3/timemachine/metadata/set_breaks.csv" \
  -o src/llama/data/set_breaks.csv
wc -l src/llama/data/set_breaks.csv   # expect 18075 (header + 18074 data rows)
head -1 src/llama/data/set_breaks.csv # expect the column header line
```

Expected: `18075 src/llama/data/set_breaks.csv`.

- [ ] **Step 5: Write the provenance README**

Create `src/llama/data/README.md`:

```markdown
# Vendored jerrybase structure dataset

`set_breaks.csv` is vendored **byte-identical** from the deadstream project.

- Source: https://github.com/eichblatt/deadstream
- File: `timemachine/metadata/set_breaks.csv`
- Pinned ref: `main` @ `adc6f827ae42861b5220ebd7fb9c3fa83abbeec3` (2026-06-28)
- File last modified upstream in commit `5de5ad46ca2bc13ee3cf7630a66633db8ca67076` (2023-04-26, "added ratdog")
- Raw URL (SHA-pinned, byte-identical):
  https://raw.githubusercontent.com/eichblatt/deadstream/adc6f827ae42861b5220ebd7fb9c3fa83abbeec3/timemachine/metadata/set_breaks.csv
- License: **GPL-3.0** (deadstream's license). llama vendors it deliberately;
  the owner intends to license llama GPL.

## What this is

One row per **set** per show. Generation chain:
`jerrybase.com` (authoritative per-show structure for the Garcia universe)
→ deadstream's `setbreaks.q` query → this CSV.

Columns: `date, artist, event_id, venue, city, state, show_set, time,
song (the set's closing song), song_n, isong (global running song index),
next_set, Nevents, ievent, break_length (long|short)`.

**It is ground truth for:** set count, each set's closing song, break length,
venue/city/state, and multi-event dates.
**It is NOT a setlist source:** no per-song rows; it can never build or rank
full setlists.

## Refreshing

Run `python scripts/refresh_jerrybase.py` (manual; never run by the pipeline).
After a refresh, update the pinned commit SHA above.
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_jerrybase.py::test_vendored_csv_is_present_and_well_formed -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/llama/data/__init__.py src/llama/data/set_breaks.csv src/llama/data/README.md tests/test_jerrybase.py
git commit -m "feat: vendor jerrybase set_breaks.csv as llama.data subpackage"
```

---

## Task 2: Manual refresh script

**Files:**
- Create: `scripts/refresh_jerrybase.py`

**Interfaces:**
- Consumes: the vendored `src/llama/data/set_breaks.csv` from Task 1.
- Produces: a standalone CLI script (no importable API relied on by other tasks). Never imported by the pipeline; no pytest.

This is a script, mirroring `scripts/capture_fixture.py`. It has **no automated test** (per spec); it is verified by running it.

- [ ] **Step 1: Write the script**

Create `scripts/refresh_jerrybase.py`:

```python
"""Manual refresh for the vendored jerrybase dataset (never run by the pipeline).

Usage:
  python scripts/refresh_jerrybase.py [ref]
      ref defaults to "main". Downloads deadstream's set_breaks.csv at that ref,
      prints a row-count and artist-coverage diff against the vendored copy, then
      overwrites the vendored file. Reminds the operator to update the README SHA.
"""
import csv
import io
import sys
from collections import Counter
from pathlib import Path

import httpx

VENDORED = Path(__file__).resolve().parent.parent / "src" / "llama" / "data" / "set_breaks.csv"
RAW_URL = ("https://raw.githubusercontent.com/eichblatt/deadstream/"
           "{ref}/timemachine/metadata/set_breaks.csv")


def _coverage(text: str) -> tuple[int, Counter]:
    rows = list(csv.DictReader(io.StringIO(text)))
    return len(rows), Counter(r["artist"] for r in rows)


def main() -> None:
    ref = sys.argv[1] if len(sys.argv) > 1 else "main"
    url = RAW_URL.format(ref=ref)
    print(f"fetching {url}")
    resp = httpx.get(url, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    new_text = resp.text

    old_text = VENDORED.read_text(encoding="utf-8") if VENDORED.exists() else ""
    old_n, old_cov = _coverage(old_text) if old_text else (0, Counter())
    new_n, new_cov = _coverage(new_text)

    print(f"rows: {old_n} -> {new_n} ({new_n - old_n:+d})")
    artists = sorted(set(old_cov) | set(new_cov))
    for a in artists:
        o, n = old_cov.get(a, 0), new_cov.get(a, 0)
        if o != n:
            print(f"  {a}: {o} -> {n} ({n - o:+d})")

    VENDORED.write_text(new_text, encoding="utf-8")
    print(f"wrote {VENDORED}")
    print(f"REMINDER: update the pinned commit SHA in {VENDORED.parent / 'README.md'} "
          f"(ref was '{ref}').")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script runs and is idempotent against the pinned ref**

Run (downloads the same pinned bytes, so the vendored file is unchanged):

```bash
python scripts/refresh_jerrybase.py adc6f827ae42861b5220ebd7fb9c3fa83abbeec3
git diff --stat src/llama/data/set_breaks.csv
```

Expected: script prints `rows: 18074 -> 18074 (+0)`, no per-artist diff lines, and `git diff --stat` shows **no change** to the CSV (byte-identical). If the CSV shows a diff, `git checkout src/llama/data/set_breaks.csv` to restore and investigate — the refresh must be byte-preserving for the pinned ref.

- [ ] **Step 3: Commit**

```bash
git add scripts/refresh_jerrybase.py
git commit -m "feat: add manual jerrybase refresh script"
```

---

## Task 3: Jerrybase Pydantic models + Show.venue_source

**Files:**
- Modify: `src/llama/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces:
  - `JerrybaseSet(name: str, closer: str, break_length: str, song_count: int | None = None)` — `name` in `"1"|"2"|"3"|"encore"`; `break_length` in `"long"|"short"`.
  - `JerrybaseEvent(event_id: str, venue: str, city: str, state: str, sets: list[JerrybaseSet])`.
  - `Show.venue_source: str = "item"` — `"item" | "jerrybase"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_jerrybase_models_construct():
    from llama.models import JerrybaseEvent, JerrybaseSet

    ev = JerrybaseEvent(
        event_id="2673", venue="Barton Hall, Cornell University",
        city="Ithaca", state="NY",
        sets=[
            JerrybaseSet(name="1", closer="Dancin' In The Streets", break_length="long"),
            JerrybaseSet(name="2", closer="Morning Dew", break_length="short", song_count=7),
            JerrybaseSet(name="encore", closer="One More Saturday Night",
                         break_length="long", song_count=1),
        ],
    )
    assert ev.sets[0].song_count is None
    assert ev.sets[1].break_length == "short"
    assert [s.name for s in ev.sets] == ["1", "2", "encore"]


def test_show_venue_source_defaults_to_item():
    from llama.models import Show

    s = Show(performance_id="X/2020-01-01", identifier="x", artist="X",
             date="2020-01-01")
    assert s.venue_source == "item"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_jerrybase_models_construct tests/test_models.py::test_show_venue_source_defaults_to_item -q`
Expected: FAIL — `ImportError: cannot import name 'JerrybaseEvent'` and `venue_source` attribute error.

- [ ] **Step 3: Add the models**

In `src/llama/models.py`, add these two classes immediately after the `SetlistItem` class (which ends at the `segue: bool = False  # runs directly into the following song` line):

```python
class JerrybaseSet(BaseModel):
    name: str  # "1" | "2" | "3" | "encore"
    closer: str  # raw closing-song title (matched via structure.norm_title)
    break_length: str  # "long" | "short"
    song_count: int | None = None  # isong delta from the prior set; None for the first


class JerrybaseEvent(BaseModel):
    event_id: str
    venue: str
    city: str
    state: str
    sets: list["JerrybaseSet"] = Field(default_factory=list)
```

In the `Show` class, add `venue_source` right after the `city: str | None = None` line and before the `item_date` comment block:

```python
    venue_source: str = "item"  # "item" | "jerrybase" (venue adopted from jerrybase)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/models.py tests/test_models.py
git commit -m "feat: add JerrybaseSet/JerrybaseEvent models and Show.venue_source"
```

---

## Task 4: jerrybase core — artist_key, normalize_set_label, build_index, lookup

**Files:**
- Create: `src/llama/jerrybase.py`
- Test: `tests/test_jerrybase.py`

**Interfaces:**
- Consumes: `JerrybaseSet`, `JerrybaseEvent` from `llama.models` (Task 3); `norm_title` from `llama.structure`.
- Produces:
  - `artist_key(artist: str) -> str` — lowercased alphanumerics only.
  - `normalize_set_label(label: str) -> str | None` — maps jerrybase set labels onto `"1"|"2"|"3"|"encore"`; `None` if unmappable.
  - `build_index(rows: Iterable[dict]) -> tuple[dict[tuple[str, str], list[JerrybaseEvent]], int]` — pure; returns `(index, skipped_count)`. Index keyed `(artist_key, date)`, events ordered by `ievent`.
  - `lookup(artist: str, date: str) -> list[JerrybaseEvent]` — public surface. Empty list = no evidence; length > 1 = multi-event date.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_jerrybase.py`:

```python
from llama import jerrybase
from llama.models import JerrybaseEvent


def test_artist_key_alphanumeric_only():
    assert jerrybase.artist_key("Grateful Dead") == "gratefuldead"
    assert jerrybase.artist_key("Phil Lesh and Friends") == "philleshandfriends"
    # llama string and CSV token collapse to the same key.
    assert jerrybase.artist_key("Phil Lesh and Friends") == jerrybase.artist_key("PhilLeshAndFriends")


def test_normalize_set_label_maps_conventions():
    n = jerrybase.normalize_set_label
    assert n("Set 1") == "1"
    assert n("Set One") == "1"
    assert n("Set I") == "1"
    assert n("Set II") == "2"
    assert n("Set III") == "3"
    assert n("Set 3") == "3"
    assert n("Show") == "1"
    assert n("Set") == "1"
    assert n("Encore") == "encore"
    assert n("Encore 1") == "encore"
    assert n("Encore 2") == "encore"
    assert n("Soundcheck") is None
    assert n("") is None


def _row(**kw):
    base = {"date": "1999-09-09", "artist": "TestBand", "event_id": "1",
            "venue": "V", "city": "C", "state": "ST", "show_set": "Set 1",
            "time": "", "song": "X", "song_n": "1", "isong": "0",
            "next_set": "", "Nevents": "1", "ievent": "1", "break_length": "long"}
    base.update(kw)
    return base


def test_build_index_song_count_deltas_and_first_none():
    rows = [
        _row(show_set="Set 1", song="A", isong="5"),
        _row(show_set="Set 2", song="B", isong="15"),
        _row(show_set="Set 3", song="C", isong="22"),
    ]
    index, skipped = jerrybase.build_index(rows)
    assert skipped == 0
    events = index[(jerrybase.artist_key("TestBand"), "1999-09-09")]
    assert len(events) == 1
    sets = events[0].sets
    assert [s.name for s in sets] == ["1", "2", "3"]
    assert [s.closer for s in sets] == ["A", "B", "C"]
    assert [s.song_count for s in sets] == [None, 10, 7]


def test_build_index_skips_malformed_rows():
    rows = [
        _row(show_set="Set 1", song="A", isong="5"),
        _row(show_set="Medical Emergency", song="B", isong="6"),  # unmappable label
        _row(show_set="Set 2", song="C", isong="not-an-int"),     # bad isong
    ]
    index, skipped = jerrybase.build_index(rows)
    assert skipped == 2
    events = index[(jerrybase.artist_key("TestBand"), "1999-09-09")]
    assert [s.name for s in events[0].sets] == ["1"]


def test_build_index_orders_events_by_ievent():
    rows = [
        _row(event_id="802", ievent="2", venue="Second", song="B", isong="10"),
        _row(event_id="801", ievent="1", venue="First", song="A", isong="5"),
    ]
    index, _ = jerrybase.build_index(rows)
    events = index[(jerrybase.artist_key("TestBand"), "1999-09-09")]
    assert [e.event_id for e in events] == ["801", "802"]
    assert [e.venue for e in events] == ["First", "Second"]


def test_lookup_known_show_three_sets():
    events = jerrybase.lookup("Grateful Dead", "1973-06-10")
    assert len(events) == 1
    ev = events[0]
    assert [s.name for s in ev.sets] == ["1", "2", "3"]
    assert [s.closer for s in ev.sets] == [
        "Playing In The Band", "Sugar Magnolia", "Johnny B. Goode"]
    assert [s.song_count for s in ev.sets] == [None, 10, 8]
    assert ev.venue == "Robert F. Kennedy Stadium"


def test_lookup_multi_event_date():
    events = jerrybase.lookup("Grateful Dead", "1970-02-14")
    assert len(events) == 2
    assert [e.event_id for e in events] == ["801", "802"]
    assert all(e.venue == "Fillmore East" for e in events)


def test_lookup_cornell_short_break_before_encore():
    events = jerrybase.lookup("Grateful Dead", "1977-05-08")
    assert len(events) == 1
    ev = events[0]
    assert [s.name for s in ev.sets] == ["1", "2", "encore"]
    assert ev.venue == "Barton Hall, Cornell University"
    by_name = {s.name: s for s in ev.sets}
    assert by_name["2"].break_length == "short"  # short break before the encore


def test_lookup_unknown_returns_empty():
    assert jerrybase.lookup("Nonexistent Artist", "1900-01-01") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jerrybase.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.jerrybase'` (the Task-1 CSV test still passes).

- [ ] **Step 3: Write the module**

Create `src/llama/jerrybase.py`:

```python
"""Best-effort jerrybase structure evidence from the vendored set_breaks.csv.

Defensive like setlistfm.py: nothing raises. Absence of evidence degrades to an
empty result. The CSV is one row per set per show; this module builds a lazy
(artist_key, date) -> list[JerrybaseEvent] index and offers deterministic
break-anchoring and closer cross-checks over it.
"""
import csv
import logging
import re
from collections.abc import Iterable
from importlib import resources

from llama.models import JerrybaseEvent, JerrybaseSet, Track
from llama.structure import norm_title

log = logging.getLogger("llama")

_INDEX: dict[tuple[str, str], list[JerrybaseEvent]] | None = None

# Roman numerals and spelled-out ordinals onto the canonical vocabulary.
_SET_WORDS = {
    "one": "1", "two": "2", "three": "3",
    "first": "1", "second": "2", "third": "3",
    "i": "1", "ii": "2", "iii": "3",
    "1": "1", "2": "2", "3": "3",
}


def artist_key(artist: str) -> str:
    """Lowercased alphanumerics only, so "Grateful Dead" and the CSV's
    "GratefulDead" collapse to the same key without an alias table."""
    return "".join(c for c in artist.lower() if c.isalnum())


def normalize_set_label(label: str) -> str | None:
    """Map a jerrybase show_set label onto "1"|"2"|"3"|"encore", or None if
    unmappable (unmappable rows are dropped by build_index)."""
    s = (label or "").strip().lower()
    if s.startswith("encore"):
        return "encore"
    if s in ("show", "set"):
        return "1"
    m = re.match(r"set\s*:?\s*(one|two|three|iii|ii|i|[123])\b", s)
    if m:
        return _SET_WORDS[m.group(1)]
    m = re.match(r"(first|second|third)\s+set\b", s)
    if m:
        return _SET_WORDS[m.group(1)]
    m = re.fullmatch(r"(one|two|three|first|second|third|iii|ii|i|[123])", s)
    if m:
        return _SET_WORDS[m.group(1)]
    return None


def build_index(rows: Iterable[dict]) -> tuple[dict[tuple[str, str], list[JerrybaseEvent]], int]:
    """Group rows into (artist_key, date) -> events ordered by ievent. Returns
    (index, skipped_count). A row is skipped when its set label is unmappable or
    its isong is not an integer. song_count is the isong delta from the prior set
    within one event; the first set of each event gets None. Never raises."""
    groups: dict[tuple[str, str], dict[str, list[dict]]] = {}
    skipped = 0
    for row in rows:
        label = normalize_set_label(row.get("show_set", ""))
        if label is None:
            skipped += 1
            continue
        try:
            isong = int(row["isong"])
        except (KeyError, ValueError, TypeError):
            skipped += 1
            continue
        key = (artist_key(row.get("artist", "")), row.get("date", ""))
        groups.setdefault(key, {}).setdefault(row.get("event_id", ""), []).append({
            "label": label,
            "closer": row.get("song", ""),
            "isong": isong,
            "break_length": row.get("break_length", ""),
            "venue": row.get("venue", ""),
            "city": row.get("city", ""),
            "state": row.get("state", ""),
            "ievent": row.get("ievent", ""),
        })

    index: dict[tuple[str, str], list[JerrybaseEvent]] = {}
    for key, by_event in groups.items():
        events: list[tuple[int, JerrybaseEvent]] = []
        for event_id, setrows in by_event.items():
            setrows.sort(key=lambda r: r["isong"])
            sets: list[JerrybaseSet] = []
            prev: int | None = None
            for r in setrows:
                count = None if prev is None else r["isong"] - prev
                prev = r["isong"]
                sets.append(JerrybaseSet(name=r["label"], closer=r["closer"],
                                         break_length=r["break_length"], song_count=count))
            first = setrows[0]
            try:
                ievent = int(first["ievent"])
            except (ValueError, TypeError):
                ievent = 0
            events.append((ievent, JerrybaseEvent(
                event_id=event_id, venue=first["venue"], city=first["city"],
                state=first["state"], sets=sets)))
        events.sort(key=lambda pair: pair[0])
        index[key] = [ev for _, ev in events]
    return index, skipped


def _load() -> dict[tuple[str, str], list[JerrybaseEvent]]:
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    try:
        with resources.files("llama.data").joinpath("set_breaks.csv").open(
                "r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        index, skipped = build_index(rows)
        if skipped:
            log.warning("jerrybase: skipped %d malformed rows", skipped)
        _INDEX = index
    except Exception as err:  # noqa: BLE001 - defensive: absence must never raise
        log.warning("jerrybase: could not load set_breaks.csv: %s", err)
        _INDEX = {}
    return _INDEX


def lookup(artist: str, date: str) -> list[JerrybaseEvent]:
    """Jerrybase events for (artist, date). Empty = no evidence; length > 1 =
    multi-event date. Never raises."""
    return _load().get((artist_key(artist), date), [])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jerrybase.py -q`
Expected: PASS (all tests, including the Task-1 CSV test).

- [ ] **Step 5: Commit**

```bash
git add src/llama/jerrybase.py tests/test_jerrybase.py
git commit -m "feat: jerrybase index — artist_key, set-label normalizer, lookup"
```

---

## Task 5: jerrybase break anchoring — anchor_breaks

**Files:**
- Modify: `src/llama/jerrybase.py`
- Test: `tests/test_jerrybase.py`

**Interfaces:**
- Consumes: `Track` from `llama.models`; `JerrybaseEvent`/`JerrybaseSet` (Task 3); `norm_title` (already imported in `jerrybase.py`).
- Produces: `anchor_breaks(tracks: list[Track], event: JerrybaseEvent) -> list[str] | None` — per-track set names parallel to `tracks`, or `None` when any closer is missing or ambiguous or the matches are out of order.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_jerrybase.py`:

```python
from llama.models import JerrybaseSet, Track


def _tracks(titles):
    return [Track(index=i + 1, set="1", title=t, filename=f"{i+1:02d}.mp3",
                  title_source="tags") for i, t in enumerate(titles)]


def _event(closers_and_names):
    return JerrybaseEvent(
        event_id="1", venue="V", city="C", state="ST",
        sets=[JerrybaseSet(name=n, closer=c, break_length="long")
              for c, n in closers_and_names],
    )


def test_anchor_breaks_places_sets_from_closers():
    tracks = _tracks(["A", "B", "C", "D", "E", "F"])
    event = _event([("C", "1"), ("E", "2")])
    assert jerrybase.anchor_breaks(tracks, event) == ["1", "1", "1", "2", "2", "2"]


def test_anchor_breaks_none_when_closer_missing():
    tracks = _tracks(["A", "B", "C"])
    event = _event([("C", "1"), ("Z", "2")])
    assert jerrybase.anchor_breaks(tracks, event) is None


def test_anchor_breaks_none_when_closer_ambiguous():
    tracks = _tracks(["A", "C", "B", "C"])  # "C" appears twice
    event = _event([("C", "1")])
    assert jerrybase.anchor_breaks(tracks, event) is None


def test_anchor_breaks_none_when_out_of_order():
    tracks = _tracks(["A", "E", "C", "D"])
    event = _event([("C", "1"), ("E", "2")])  # E precedes C in tracks
    assert jerrybase.anchor_breaks(tracks, event) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jerrybase.py -k anchor -q`
Expected: FAIL — `AttributeError: module 'llama.jerrybase' has no attribute 'anchor_breaks'`.

- [ ] **Step 3: Implement anchor_breaks**

Append to `src/llama/jerrybase.py`:

```python
def anchor_breaks(tracks: list[Track], event: JerrybaseEvent) -> list[str] | None:
    """Assign each track a set name by anchoring jerrybase set closers onto
    tracks (matched via norm_title). Succeeds only if every closer matches
    exactly one track and the matched positions are strictly increasing; then
    tracks up to and including closer i take set i's name, tracks after the last
    closer take the last set's name. Returns per-track set names (parallel to
    tracks) or None on any missing/ambiguous/out-of-order closer."""
    positions: list[int] = []
    for st in event.sets:
        target = norm_title(st.closer)
        hits = [i for i, t in enumerate(tracks) if norm_title(t.title) == target]
        if len(hits) != 1:
            return None
        positions.append(hits[0])
    if any(positions[k] >= positions[k + 1] for k in range(len(positions) - 1)):
        return None
    if not positions:
        return None
    names = [s.name for s in event.sets]
    out: list[str] = []
    si = 0
    for i in range(len(tracks)):
        while si < len(positions) and i > positions[si]:
            si += 1
        out.append(names[min(si, len(names) - 1)])
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jerrybase.py -k anchor -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/jerrybase.py tests/test_jerrybase.py
git commit -m "feat: jerrybase break anchoring from set closers"
```

---

## Task 6: jerrybase closer cross-check — closer_contradictions

**Files:**
- Modify: `src/llama/jerrybase.py`
- Test: `tests/test_jerrybase.py`

**Interfaces:**
- Consumes: `Track` (with final `.set` labels), `JerrybaseEvent`; `norm_title`.
- Produces: `closer_contradictions(tracks: list[Track], event: JerrybaseEvent) -> tuple[list[str], list[str]]` — `(hard_flags, soft_notes)`. A closer matched to exactly one track that is **not** the last track of its set is a hard flag; a closer absent from the tracks is a soft note; an ambiguous closer (multiple matches) is ignored.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_jerrybase.py`:

```python
def _tracks_with_sets(pairs):
    return [Track(index=i + 1, set=s, title=t, filename=f"{i+1:02d}.mp3",
                  title_source="tags") for i, (t, s) in enumerate(pairs)]


def test_closer_contradictions_none_when_closers_at_boundaries():
    tracks = _tracks_with_sets([("A", "1"), ("B", "1"), ("C", "2"), ("D", "2")])
    event = _event([("B", "1"), ("D", "2")])  # both closers end their sets
    hard, soft = jerrybase.closer_contradictions(tracks, event)
    assert hard == []
    assert soft == []


def test_closer_contradictions_flags_mid_set_closer():
    tracks = _tracks_with_sets([("A", "1"), ("B", "1"), ("C", "1"), ("D", "2")])
    event = _event([("B", "1")])  # jerrybase says set 1 ends on B, but C is still set 1
    hard, soft = jerrybase.closer_contradictions(tracks, event)
    assert any("B" in f and "set break" in f for f in hard)
    assert soft == []


def test_closer_contradictions_soft_note_when_closer_absent():
    tracks = _tracks_with_sets([("A", "1"), ("B", "1")])
    event = _event([("Z", "1")])
    hard, soft = jerrybase.closer_contradictions(tracks, event)
    assert hard == []
    assert any("Z" in n for n in soft)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jerrybase.py -k closer_contradictions -q`
Expected: FAIL — `AttributeError: module 'llama.jerrybase' has no attribute 'closer_contradictions'`.

- [ ] **Step 3: Implement closer_contradictions**

Append to `src/llama/jerrybase.py`:

```python
def closer_contradictions(tracks: list[Track],
                          event: JerrybaseEvent) -> tuple[list[str], list[str]]:
    """Cross-check jerrybase closers against tracks that already carry final set
    labels. Returns (hard_flags, soft_notes): a closer matched to exactly one
    track that is not the last track of its set is a hard flag (needs-review); a
    closer absent from the tracks is a soft note (context only). Ambiguous
    closers (multiple matches) are ignored."""
    if not tracks:
        return [], []
    breaks = {t.index for t, nxt in zip(tracks, tracks[1:]) if nxt.set != t.set}
    last_index = tracks[-1].index
    hard: list[str] = []
    soft: list[str] = []
    for st in event.sets:
        target = norm_title(st.closer)
        hits = [t for t in tracks if norm_title(t.title) == target]
        if not hits:
            soft.append(f"jerrybase set closer '{st.closer}' not found in tracks")
            continue
        if len(hits) != 1:
            continue  # ambiguous: no reliable position check
        tk = hits[0]
        if not (tk.index in breaks or tk.index == last_index):
            hard.append(f"jerrybase set closer '{st.closer}' is not at a set break")
    return hard, soft
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jerrybase.py -k closer_contradictions -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/jerrybase.py tests/test_jerrybase.py
git commit -m "feat: jerrybase closer cross-check for set-break tripwires"
```

---

## Task 7: structure_guard expected-set-count extension

**Files:**
- Modify: `src/llama/structure.py:134-149` (the `structure_guard` function)
- Test: `tests/test_structure.py`

**Interfaces:**
- Consumes: `Track` from `llama.models`.
- Produces: `structure_guard(tracks, set_breaks, evidence_sets=None, min_minutes=150, expected_set_count=None) -> str | None`. New keyword-only-by-default trailing param `expected_set_count: int | None`. When set and the aligned distinct-set-label count (including `encore`) differs, returns a flag string — this check runs even when breaks exist. All prior behavior is preserved when `expected_set_count is None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_structure.py`:

```python
def _guard_tracks(sets, dur=60):
    from llama.models import Track
    return [Track(index=i + 1, set=s, title=f"T{i}", filename=f"{i}.mp3",
                  duration_sec=dur, title_source="tags") for i, s in enumerate(sets)]


def test_structure_guard_flags_set_count_mismatch():
    from llama.titles import set_breaks
    from llama.structure import structure_guard

    tracks = _guard_tracks(["1", "1", "2", "2", "encore"])
    breaks = set_breaks(tracks)
    flag = structure_guard(tracks, breaks, expected_set_count=2)
    assert flag is not None
    assert "3" in flag and "2" in flag


def test_structure_guard_no_flag_when_set_count_matches():
    from llama.titles import set_breaks
    from llama.structure import structure_guard

    tracks = _guard_tracks(["1", "1", "2", "2", "encore"])
    breaks = set_breaks(tracks)
    assert structure_guard(tracks, breaks, expected_set_count=3) is None


def test_structure_guard_preserves_old_behavior_without_expected_count():
    from llama.titles import set_breaks
    from llama.structure import structure_guard

    tracks = _guard_tracks(["1", "1", "1"], dur=200 * 60)  # long single set
    assert structure_guard(tracks, set_breaks(tracks)) is not None
    short = _guard_tracks(["1", "1", "1"], dur=60)
    assert structure_guard(short, set_breaks(short)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_structure.py -k structure_guard -q`
Expected: FAIL — `structure_guard() got an unexpected keyword argument 'expected_set_count'`.

- [ ] **Step 3: Extend structure_guard**

Replace the entire `structure_guard` function in `src/llama/structure.py` with:

```python
def structure_guard(tracks: list[Track], set_breaks: list[int],
                    evidence_sets: set[str] | None = None,
                    min_minutes: int = 150,
                    expected_set_count: int | None = None) -> str | None:
    """Flag suspicious structure. When expected_set_count is given (jerrybase
    evidence), an aligned distinct-set-label count (including "encore") that
    differs is flagged even when breaks exist. Otherwise: flag single-set
    structure only on real evidence of a problem - the setlist sources showed
    multiple sets that alignment lost, or the show runs implausibly long for one
    uninterrupted set (single sets past 2.5 hours are rare; two-set shows
    usually exceed it). Track count alone is not a signal - plenty of artists
    play 20+ short songs in one set."""
    if not tracks:
        return None
    if expected_set_count is not None:
        actual = len({t.set for t in tracks})
        if actual != expected_set_count:
            return f"structure has {actual} sets but jerrybase shows {expected_set_count}"
    if set_breaks:
        return None
    if evidence_sets and len(evidence_sets) > 1:
        return "setlist evidence shows multiple sets but alignment found none"
    total = sum(t.duration_sec for t in tracks if t.duration_sec)
    if total >= min_minutes * 60:
        return f"single-set structure for a long show ({total / 60:.0f} min)"
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_structure.py -q`
Expected: PASS (existing structure tests too — the new param defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add src/llama/structure.py tests/test_structure.py
git commit -m "feat: structure_guard flags aligned/jerrybase set-count mismatch"
```

---

## Task 8: [jerrybase] config section

**Files:**
- Modify: `src/llama/config.py` (add `JerrybaseConfig`, mount on `Config`, extend `DEFAULT_CONFIG_TOML`)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Config.jerrybase: JerrybaseConfig` where `JerrybaseConfig(enabled: bool = True)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_jerrybase_enabled_default_on():
    from llama.config import Config

    assert Config().jerrybase.enabled is True


def test_jerrybase_disabled_from_toml(tmp_path):
    from llama.config import load_config

    p = tmp_path / "config.toml"
    p.write_text("[jerrybase]\nenabled = false\n")
    assert load_config(p).jerrybase.enabled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -k jerrybase -q`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'jerrybase'`.

- [ ] **Step 3: Add the config model and mount it**

In `src/llama/config.py`, add the `JerrybaseConfig` class right after the `SetlistFMConfig` class (which is `class SetlistFMConfig(BaseModel): api_key: str | None = None`):

```python
class JerrybaseConfig(BaseModel):
    # Vendored, offline, no key - so on by default (unlike setlist.fm). No
    # thresholds: break anchoring is all-or-nothing by design.
    enabled: bool = True
```

In the `Config` class, add the field right after `setlistfm: SetlistFMConfig = Field(default_factory=SetlistFMConfig)`:

```python
    jerrybase: JerrybaseConfig = Field(default_factory=JerrybaseConfig)
```

- [ ] **Step 4: Add the template section**

In `DEFAULT_CONFIG_TOML`, insert this block immediately after the `[setlistfm]` commented block (after the line `#                          # set-structure recovery is LMA-descriptions only`) and before `[winnow]`:

```
[jerrybase]
enabled = true             # vendored offline set-structure evidence (break
                           # anchoring + set-count/venue/multi-event tripwires);
                           # set false to ignore the dataset entirely
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -q`
Expected: PASS. In particular `test_default_config_template_matches_defaults` must still pass — the template's `[jerrybase] enabled = true` matches the `JerrybaseConfig` default, so the `model_dump` comparison holds.

- [ ] **Step 6: Commit**

```bash
git add src/llama/config.py tests/test_config.py
git commit -m "feat: add [jerrybase] config section (enabled, default on)"
```

---

## Task 9: gather integration

**Files:**
- Modify: `src/llama/stages/gather.py` (imports, `run_gather` signature + body)
- Modify: `src/llama/pipeline.py` (thread `jerrybase_enabled` through `process_show` → `run_gather`)
- Modify: `src/llama/cli.py` (two `process_show(...)` call sites: pass `jerrybase_enabled=config.jerrybase.enabled`)
- Test: `tests/test_stage_gather.py`

**Interfaces:**
- Consumes: `jerrybase.lookup`, `jerrybase.anchor_breaks`, `jerrybase.closer_contradictions` (Tasks 4-6); `structure_guard(..., expected_set_count=...)` (Task 7); `Show.venue_source` (Task 3); `Config.jerrybase.enabled` (Task 8).
- Produces: `run_gather(..., structure_cfg=None, jerrybase_enabled: bool = False) -> Show`. `process_show(..., jerrybase_enabled: bool = True)`.

- [ ] **Step 1: Write the failing integration tests**

Add to `tests/test_stage_gather.py` (top-of-file imports already include `json`, `Path`, `FakeProvider`, `Candidate`, `RecordingSummary`, `run_gather`, `ShowWorkspace`, `FIXTURE`, `IDENT`, `make_candidate`, `StubIA`). Add these imports at the top if absent: `from llama import jerrybase` and `from llama.models import JerrybaseEvent, JerrybaseSet`.

```python
from llama import jerrybase
from llama.models import JerrybaseEvent, JerrybaseSet


def _jb_event(closers_and_names, venue="V", city="C"):
    return JerrybaseEvent(
        event_id="1", venue=venue, city=city, state="ST",
        sets=[JerrybaseSet(name=n, closer=c, break_length="long")
              for c, n in closers_and_names],
    )


def test_gather_multi_event_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [
        _jb_event([("I Know You Rider", "1")], venue="Fillmore East"),
        _jb_event([("Johnny B. Goode", "1")], venue="Fillmore East"),
    ])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.needs_review is True
    assert any(f.startswith("multi-event date: 2 jerrybase events") for f in show.review_flags)


def test_gather_adopts_venue_when_candidate_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")],
        venue="Barton Hall", city="Ithaca")])
    cand = make_candidate()
    cand.venue = None
    cand.city = None
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), cand, IDENT, jerrybase_enabled=True)
    assert show.venue == "Barton Hall"
    assert show.city == "Ithaca"
    assert show.venue_source == "jerrybase"
    assert show.needs_review is False


def test_gather_flags_venue_mismatch_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")],
        venue="Robert F. Kennedy Stadium", city="Washington")])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.venue == "RFK Stadium"          # candidate venue preserved
    assert show.venue_source == "item"
    assert any("venue mismatch" in f for f in show.review_flags)


def test_gather_confident_but_contradicted_break_flags(tmp_path, monkeypatch):
    # gd73 aligns confidently to sets 1,1,1,2,2,encore (breaks [3,5]); jerrybase
    # says set 1 ends on China Cat Sunflower (track 2, mid-set 1) -> tripwire.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("China Cat Sunflower", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")])])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.needs_review is True
    assert any("China Cat Sunflower" in f and "set break" in f for f in show.review_flags)


def test_gather_flags_set_count_mismatch(tmp_path, monkeypatch):
    # jerrybase says 2 sets (closers at boundaries); alignment has 3 -> mismatch.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Johnny B. Goode", "2")])])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert any("jerrybase shows 2" in f for f in show.review_flags)


def test_gather_anchoring_rescues_low_confidence_without_llm(tmp_path, monkeypatch):
    md = json.loads(FIXTURE.read_text())
    # Replace the description with a DIFFERENT setlist so deterministic alignment
    # covers almost nothing (low confidence) while the real tag titles remain.
    md["metadata"]["description"] = (
        "Set 1:\nBertha\nJack Straw > Deal\n\n"
        "Set 2:\nTruckin > Wharf Rat\n\nEncore:\nOne More Saturday Night\n")
    # jerrybase closers reference the real tag titles; anchoring breaks after
    # China Cat Sunflower (track 2) and Eyes of the World (track 5).
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("China Cat Sunflower", "1"), ("Eyes of the World", "2")])])
    sws = ShowWorkspace(tmp_path / "show")
    fake_align = FakeProvider()
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      align_provider=fake_align, jerrybase_enabled=True)
    assert fake_align.calls == []  # anchoring short-circuited the LLM fallback
    assert show.set_breaks == [2]
    assert show.structure is not None and show.structure.alignment == "jerrybase"
    assert "set breaks anchored from jerrybase" in show.structure.conflicts
    assert "low-confidence structure alignment" not in show.review_flags


def test_gather_jerrybase_disabled_is_noop(tmp_path, monkeypatch):
    def _boom(a, d):
        raise AssertionError("lookup must not be called when disabled")
    monkeypatch.setattr(jerrybase, "lookup", _boom)
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=False)
    assert show.needs_review is False
    assert show.venue_source == "item"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_gather.py -k "jerrybase or multi_event or venue or contradicted or set_count or anchoring or disabled" -q`
Expected: FAIL — `run_gather() got an unexpected keyword argument 'jerrybase_enabled'`.

- [ ] **Step 3: Update gather imports**

In `src/llama/stages/gather.py`, replace the import header (lines 1-14) so it adds `re` and the `jerrybase` module. The new top of the file:

```python
import logging
import re

from llama import jerrybase
from llama.config import StructureConfig
from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.ia_client import IAError
from llama.llm.provider import LLMError, TaskFailed
from llama.llm.tasks import run_json_task
from llama.models import (AlignedStructure, Candidate, ParsedSetlist, Show,
                          SourcedParse, StructureInfo)
from llama.setlist import parse_setlist
from llama.structure import (align, apply_llm_alignment, blend_segues,
                             from_setlistfm, rank_parses, structure_guard)
from llama.titles import clean_tag_title, is_real_title, resolve_titles, set_breaks
from llama.workspace import ShowWorkspace, read_model, should_run, write_artifact

log = logging.getLogger("llama")


def _norm_place(s: str) -> str:
    """Lowercase, alphanumerics and spaces only, collapsed whitespace - the
    normal form for comparing archive and jerrybase venue strings."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split())
```

- [ ] **Step 4: Rewrite run_gather**

Replace the entire `run_gather` function (from `def run_gather(` through the final `return show`) in `src/llama/stages/gather.py` with:

```python
def run_gather(
    show_ws: ShowWorkspace,
    ia,
    provider,
    candidate: Candidate,
    identifier: str,
    audio_format: str = "mp3",
    force: bool = False,
    align_provider=None,
    setlistfm=None,
    structure_cfg: StructureConfig | None = None,
    jerrybase_enabled: bool = False,
) -> Show:
    if not should_run(show_ws.show, force):
        return read_model(show_ws.show, Show)
    structure_cfg = structure_cfg or StructureConfig()

    md = ia.metadata(identifier)
    meta = md.get("metadata", {})
    artist = str(_creator(meta) or candidate.collection)
    want = FORMAT_BY_AUDIO[audio_format]
    kept, excluded, ordering = filter_files(md.get("files", []), want_format=want)

    # Canonical performance setlist: every recording's description, plus
    # setlist.fm when configured, ranked pick-best.
    parses, notes, descriptions = _collect_parses(ia, candidate, identifier, meta)
    if setlistfm is not None:
        raw = setlistfm.setlist(artist, candidate.date,
                                venue=candidate.venue, city=candidate.city)
        converted = from_setlistfm(raw) if raw else None
        if converted is not None:
            parses.insert(0, SourcedParse(source="setlist.fm", parsed=converted))

    best = rank_parses(parses, target_count=len(kept))
    if best is None:
        longest = max(descriptions, key=len, default="")
        if longest.strip():
            parsed = run_json_task(provider, "extract_setlist", ParsedSetlist,
                                   description=longest)
            best = SourcedParse(source="llm", parsed=parsed)
    canonical = best.parsed if best else ParsedSetlist()
    if best is not None and best.source == "setlist.fm":
        best_lma = rank_parses([p for p in parses if p.source != "setlist.fm"],
                               target_count=len(kept))
        canonical = blend_segues(canonical, best_lma.parsed if best_lma else None)

    siblings = None
    if any(not is_real_title(clean_tag_title(f.get("title"))) for f in kept) and (
        canonical.confidence == "low" or len(canonical.items) != len(kept)
    ):
        siblings = _sibling_titles(ia, candidate, identifier, want, len(kept))
    tracks = resolve_titles(kept, canonical, sibling_titles=siblings)

    # Jerrybase structure evidence (no-op for artists absent from the dataset).
    events = jerrybase.lookup(artist, candidate.date) if jerrybase_enabled else []
    event = events[0] if len(events) == 1 else None

    result = align(tracks, canonical)
    alignment = "deterministic"
    flags = []
    if canonical.items and result.coverage < structure_cfg.align_coverage_threshold:
        anchored = jerrybase.anchor_breaks(tracks, event) if event is not None else None
        if anchored is not None:
            # Deterministic break anchoring from jerrybase closers: skip the LLM.
            result = result.model_copy(update={"sets": anchored})
            alignment = "jerrybase"
            notes.append("set breaks anchored from jerrybase")
        else:
            llm_result = None
            if align_provider is not None:
                try:
                    resp = run_json_task(align_provider, "align_structure", AlignedStructure,
                                         tracks=_format_tracks(tracks),
                                         setlist=_format_setlist(canonical))
                    llm_result = apply_llm_alignment(tracks, resp)
                except (TaskFailed, LLMError) as err:
                    log.warning("align_structure failed: %s", err)
            if llm_result is not None and llm_result.coverage >= structure_cfg.align_coverage_threshold:
                # Deliberate trade-off: apply_llm_alignment never populates
                # conflicts, so any deterministic-alignment conflicts are
                # dropped when the LLM realignment wins.
                result, alignment = llm_result, "llm"
            else:
                flags.append("low-confidence structure alignment")

    tracks = [t.model_copy(update={"set": s, "segue": g})
              for t, s, g in zip(tracks, result.sets, result.segues)]
    breaks = set_breaks(tracks)

    # Multi-event tripwire (groundwork only: identity/ledger unchanged here).
    if len(events) > 1:
        venue_list = ", ".join(sorted({e.venue for e in events}))
        flags.append(f"multi-event date: {len(events)} jerrybase events at {venue_list}")

    # Venue enrichment + cross-check (single-event only; never overwrite a venue).
    venue, city, venue_source = candidate.venue, candidate.city, "item"
    if event is not None:
        if not (venue and venue.strip()):
            venue, city, venue_source = event.venue, event.city, "jerrybase"
        elif _norm_place(venue) != _norm_place(event.venue):
            flags.append(f"venue mismatch: archive '{venue}' vs jerrybase '{event.venue}'")

    # Closer tripwire (single-event, non-anchored alignments; anchoring places
    # breaks at closers by construction, so it cannot contradict itself).
    if event is not None and alignment != "jerrybase":
        hard, soft = jerrybase.closer_contradictions(tracks, event)
        flags += hard
        notes += soft

    expected_sets = len({s.name for s in event.sets}) if event is not None else None
    guard = structure_guard(tracks, breaks,
                            evidence_sets={i.set for i in canonical.items},
                            min_minutes=structure_cfg.guard_min_minutes,
                            expected_set_count=expected_sets)
    if guard:
        flags.append(guard)

    if any(t.title_source == "unresolved" for t in tracks):
        flags.append("unresolved track titles")
    if canonical.confidence == "low":
        flags.append("low-confidence setlist")
    if not tracks:
        flags.append("no playable tracks")

    structure_info = None
    if best is not None:
        structure_info = StructureInfo(source=best.source, alignment=alignment,
                                       coverage=result.coverage,
                                       conflicts=result.conflicts + notes)

    show = Show(
        performance_id=candidate.performance_id,
        identifier=identifier,
        artist=artist,
        date=candidate.date,
        venue=venue,
        city=city,
        venue_source=venue_source,
        tracks=tracks,
        set_breaks=breaks,
        excluded_files=excluded,
        order_source=ordering["order_source"],
        reordered=ordering["reordered"],
        lineage=meta.get("lineage") or meta.get("source"),
        source_url=f"https://archive.org/details/{identifier}",
        needs_review=bool(flags),
        review_flags=flags,
        structure=structure_info,
    )
    write_artifact(show_ws.show, show)
    write_artifact(show_ws.reviews, md.get("reviews", []))
    return show
```

- [ ] **Step 5: Thread the flag through the pipeline**

In `src/llama/pipeline.py`, add a `jerrybase_enabled: bool = True` parameter to `process_show`. Change the signature block (currently ending `force_stage: str | None = None,`) to include it:

```python
    setlistfm=None,
    structure_cfg=None,
    selection_cfg=None,
    jerrybase_enabled: bool = True,
    force_stage: str | None = None,
```

Then in the `run_gather(...)` call inside `process_show` (currently passing `setlistfm=setlistfm, structure_cfg=structure_cfg`), add the argument:

```python
    with step(f"[{pid}] gathering"):
        show = run_gather(show_ws, ia, providers["extract_setlist"], cand, identifier,
                          audio_format=audio_format, force=force,
                          align_provider=providers.get("align_structure"),
                          setlistfm=setlistfm, structure_cfg=structure_cfg,
                          jerrybase_enabled=jerrybase_enabled)
```

- [ ] **Step 6: Pass config.jerrybase.enabled at both CLI call sites**

In `src/llama/cli.py`, both `process_show(...)` calls (around lines 180 and 527) currently pass `structure_cfg=config.structure`. Add `jerrybase_enabled=config.jerrybase.enabled` to each.

Call site 1 (the `find`/run loop, currently):
```python
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format,
                               force=force, script=script, setlistfm=setlistfm,
                               structure_cfg=config.structure, selection_cfg=config.selection,
```
becomes:
```python
            pkg = process_show(ws, ia, ledger, entry, providers, ws.name, config.audio_format,
                               force=force, script=script, setlistfm=setlistfm,
                               structure_cfg=config.structure, selection_cfg=config.selection,
                               jerrybase_enabled=config.jerrybase.enabled,
```
(keep the remaining trailing arguments on that call unchanged).

Call site 2 (around line 527):
```python
    pkg = process_show(ws, ia, ledger, shortlist_entry, make_providers(config),
                       ...
                       setlistfm=make_client(config), structure_cfg=config.structure,
```
Add `jerrybase_enabled=config.jerrybase.enabled,` immediately after `structure_cfg=config.structure,` in this call. Verify by searching: `grep -n "structure_cfg=config.structure" src/llama/cli.py` should show two lines, and after editing, `grep -n "jerrybase_enabled=config.jerrybase.enabled" src/llama/cli.py` must show two lines.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_stage_gather.py -q`
Expected: PASS (all existing gather tests plus the new ones; existing tests pass `jerrybase_enabled` implicitly as `False`, so they are unaffected).

- [ ] **Step 8: Commit**

```bash
git add src/llama/stages/gather.py src/llama/pipeline.py src/llama/cli.py tests/test_stage_gather.py
git commit -m "feat: integrate jerrybase structure evidence into gather"
```

---

## Task 10: `llama show` venue-adoption provenance

**Files:**
- Modify: `src/llama/cli.py` (the `show` command, around lines 408-413)
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `Show.venue_source` (Task 3).
- Produces: `llama show` appends `(venue from jerrybase)` to the place line when `venue_source == "jerrybase"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli_commands.py`:

```python
def test_show_displays_jerrybase_venue_provenance(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = ShowWorkspace(tmp_path / "shows" / "gd-1977-05-08")
    write_artifact(sws.show, Show(
        performance_id="GratefulDead/1977-05-08", identifier="gd77",
        artist="Grateful Dead", date="1977-05-08",
        venue="Barton Hall, Cornell University", city="Ithaca",
        venue_source="jerrybase"))
    result = runner.invoke(cli.app, ["show", str(sws.dir), "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "(venue from jerrybase)" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_commands.py::test_show_displays_jerrybase_venue_provenance -q`
Expected: FAIL — `(venue from jerrybase)` not in output.

- [ ] **Step 3: Add the provenance display**

In `src/llama/cli.py`, in the `show` command, the block currently reads:

```python
    s = read_model(sws.show, Show)
    place = ", ".join(p for p in [s.venue, s.city] if p)
    date_str = s.date
    if s.date_source == "research" and s.item_date:
        date_str = f"{s.date} (item date {s.item_date}, corrected via research)"
    typer.echo(f"{s.artist}  {date_str}  {place}".rstrip())
```

Change it to append the venue provenance to `place`:

```python
    s = read_model(sws.show, Show)
    place = ", ".join(p for p in [s.venue, s.city] if p)
    if s.venue_source == "jerrybase" and place:
        place = f"{place} (venue from jerrybase)"
    date_str = s.date
    if s.date_source == "research" and s.item_date:
        date_str = f"{s.date} (item date {s.item_date}, corrected via research)"
    typer.echo(f"{s.artist}  {date_str}  {place}".rstrip())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_commands.py::test_show_displays_jerrybase_venue_provenance -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: show jerrybase venue-adoption provenance in llama show"
```

---

## Task 11: PyInstaller data + CLAUDE.md documentation

**Files:**
- Modify: `packaging/llama.spec:72`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the `llama.data` subpackage (Task 1).
- Produces: PyInstaller bundles `llama.data`'s CSV; CLAUDE.md documents the source.

This task has no unit test (packaging + docs). It is verified by inspection and the full suite.

- [ ] **Step 1: Add the data-files line to the spec**

In `packaging/llama.spec`, the datas line currently reads:

```python
datas = collect_data_files("llama.prompts")
```

Change it to also collect the data subpackage:

```python
datas = collect_data_files("llama.prompts") + collect_data_files("llama.data")
```

- [ ] **Step 2: Verify the spec still parses as Python**

Run: `python -c "import ast; ast.parse(open('packaging/llama.spec').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Add the CLAUDE.md documentation line**

In `CLAUDE.md`, under the "Architecture (from the spec — the short version)" section's **LLM layer** bullet, append this sentence to the end of that bullet (it discusses gather and setlist.fm already):

Locate the sentence ending `...falling back to the `align_structure` LLM touchpoint for messy alignments.` and add a new sentence right after it, within the same bullet:

```
Structure evidence for the Garcia universe also comes from a vendored,
offline jerrybase-derived dataset (`src/llama/data/set_breaks.csv`, GPL-3.0
from deadstream; refresh via `scripts/refresh_jerrybase.py`): gather uses it
after alignment as a tripwire (multi-event dates, venue mismatch, contradicted
set breaks, wrong set count) and a deterministic break-anchoring corrector,
never as a setlist source (`[jerrybase] enabled`, default on).
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: PASS — the whole offline suite is green.

- [ ] **Step 5: Commit**

```bash
git add packaging/llama.spec CLAUDE.md
git commit -m "chore: bundle jerrybase data in PyInstaller + document in CLAUDE.md"
```

---

## Self-Review

**1. Spec coverage** — each spec section maps to a task:

- *Data layer — subpackage + byte-identical CSV + README provenance:* Task 1.
- *Data layer — `scripts/refresh_jerrybase.py`:* Task 2.
- *Data layer — packaging `collect_data_files("llama.data")`:* Task 11. (Wheel inclusion needs no change: hatchling ships `src/llama/**`, confirmed against the existing `llama.prompts` data pattern.)
- *Lookup module — Pydantic models `JerrybaseSet`/`JerrybaseEvent`:* Task 3.
- *Lookup module — lazy index, `artist_key`, set-label normalizer, `song_count` deltas, `lookup`, malformed-row skipping/counting:* Task 4.
- *Lookup module — closer matching via `norm_title`:* used in Tasks 5 and 6.
- *Pipeline integration — lookup after align:* Task 9.
- *Pipeline integration — multi-event tripwire:* Task 9.
- *Pipeline integration — venue enrichment + cross-check:* Task 9.
- *Pipeline integration — break anchoring + closer tripwire:* `anchor_breaks` (Task 5), `closer_contradictions` (Task 6), wired in Task 9.
- *Pipeline integration — structure-guard set-count extension:* Task 7, wired in Task 9.
- *Config — `[jerrybase] enabled` + config-init template:* Task 8.
- *Models and flags — provenance reuse + surface in `llama show`:* `venue_source` (Task 3), anchoring provenance via `StructureInfo.alignment == "jerrybase"` + the "set breaks anchored from jerrybase" note (Task 9), venue display (Task 10).
- *Testing — unit (Task 4/5/6, `tests/test_jerrybase.py`) + integration (Task 9, `tests/test_stage_gather.py`):* all named spec assertions covered (gd 1973-06-10 three sets; 1970-02-14 two events; Cornell short break before encore; anchoring rescues low-confidence with zero LLM calls; confident-but-contradicted; multi-event; venue adopt vs mismatch; no-op when disabled).
- *Docs — CLAUDE.md line:* Task 11.
- *Out of scope* (setlist construction, `break_length` in manifest/m3u, ledger/identity changes for multi-event, scraping/runtime fetch): none of these are implemented. `break_length` is stored on `JerrybaseSet` but never written to manifest/m3u; multi-event is flag-only; the CSV is only ever read from disk.

**2. Placeholder scan:** No `TBD`/`TODO`/"handle edge cases"/"add validation"/"similar to Task N". Every code step shows complete, runnable code. Where a task edits an existing function, the exact current text is quoted before the replacement.

**3. Type consistency:** Names/signatures are consistent across tasks: `artist_key`, `normalize_set_label`, `build_index(rows) -> (index, int)`, `lookup(artist, date) -> list[JerrybaseEvent]`, `anchor_breaks(tracks, event) -> list[str] | None`, `closer_contradictions(tracks, event) -> tuple[list[str], list[str]]`, `structure_guard(..., expected_set_count=None)`, `Show.venue_source`, `JerrybaseSet(name, closer, break_length, song_count)`, `JerrybaseEvent(event_id, venue, city, state, sets)`, `run_gather(..., jerrybase_enabled=False)`, `process_show(..., jerrybase_enabled=True)`, `Config.jerrybase.enabled`. `gather.py` calls exactly the `jerrybase.*` names defined in Tasks 4-6 and the `structure_guard` param from Task 7.

**Resolved ambiguities (flagged for the orchestrator):**

1. **`run_gather` default vs config default.** The spec says jerrybase is default-on. The canonical test fixture `gd73-06-10` *is* an in-dataset show (GD 1973-06-10), so a blanket default-on would change existing gather-test outcomes (notably a false "RFK Stadium" vs "Robert F. Kennedy Stadium" venue mismatch). Resolution: `run_gather`'s `jerrybase_enabled` parameter defaults to `False` (opt-in at the function boundary), while `Config.jerrybase.enabled` defaults to `True` and `process_show` forwards it — so production is on, and existing unit tests that don't pass the flag stay byte-identical. No test calls `process_show` directly (verified), so nothing else regresses.

2. **"Soft flag" semantics.** llama's flag→needs-review mechanism is binary. The spec's "closer absent → soft flag only... combines with other suspicion rather than forcing review alone" is implemented by routing absent-closer messages to `StructureInfo.conflicts` (via the gather `notes` list — visible in `llama show`'s structure conflicts) rather than to `review_flags`. So an absent closer never forces review by itself, but is visible and combines with any real flag. `song_count` deltas are stored on the model but never flagged (diagnostic only), matching "logged diagnostic only."

3. **`break_length` per set.** Stored as the CSV row's `break_length` value for that set (semantically the break *after* the set). The last set of an event carries whatever the file records (usually `long`); nothing downstream consumes it yet (manifest/m3u use is out of scope), so this is inert provenance.

4. **Anchoring only inside the low-confidence branch.** Per spec wording ("before the `align_structure` LLM fallback"), anchoring is attempted only when `canonical.items` exist and coverage is below threshold. Shows with no parsed setlist at all (empty canonical) are not anchored — consistent with today's behavior for such shows and with the spec's placement of anchoring in the existing fallback path.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-19-jerrybase-evidence.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
