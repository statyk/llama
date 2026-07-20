# Multi-event dates: per-event performance identity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split a single archive date that carried two performances (early/late show) into one independent show per event — own candidate, own slug, own ledger entry — deciding identity at grouping time from vendored jerrybase evidence.

**Architecture:** `group_candidates` gains offline access to the jerrybase module. For a date jerrybase marks as multi-event (`Nevents > 1`) it partitions that date's recordings into per-event candidates keyed `collection/date/eN` (N = jerrybase `ievent` order), plus held `.../spans` and `.../unassigned` catch-alls. Single-event dates and dates with no jerrybase data keep today's behavior byte-for-byte (including the legacy `/early`|`/late` identifier-sniff path). Gather reads the `/eN` suffix to select the right `JerrybaseEvent` for every existing evidence check, and re-flags a tape whose aligned tracks span more than one event.

**Tech Stack:** Python 3, Pydantic models, pytest (offline, `fake` LLM backend + captured archive.org fixtures + the vendored `set_breaks.csv`).

## Global Constraints

- Multi-event date identity is `collection/date/eN`, N = jerrybase `ievent` order (e1 = first/early). Copy `ievent` semantics from `jerrybase.build_index` (events already sorted ascending by `ievent`, so `events[N-1]` is event N).
- Single-event dates keep `collection/date`. Dates with **no jerrybase data** preserve today's behavior **byte-for-byte**, including the existing `/early`|`/late` identifier-sniff suffix path.
- **No ledger migration. No legacy-id compatibility.** Pre-feature `collection/date` ledger rows simply don't match new per-event ids; write no migration code and no legacy matching. This mirrors the project's removed-migration precedent (`git log` @4cc1410).
- Jerrybase is offline/free but honors `config.jerrybase.enabled`: when disabled, grouping does **not** split (falls to the no-data path).
- Held candidates (`/spans`, `/unassigned`) and unpartitioned multi-event dates are always `needs-review`; they never auto-ship and are never split or auto-assigned.
- Partition signals apply **in priority order**: (1) early/late text (2-event dates only) in identifier/title/description; (2) description-text set-closer matching via `norm_title` containment; a recording matching (1) or (2) for **more than one** event → `/spans`; a recording matching **neither** → `/unassigned`.
- Grouping stores no flags on `Candidate` (the model is unchanged); the `/eN`, `/spans`, `/unassigned` pid **suffix** carries the semantics, and gather emits the review-flag text.
- Audio files are gitignored; fixtures are slimmed captured API responses (`scripts/capture_fixture.py`). Pipeline tests run offline against the `fake` backend.

---

### Task 1: Grouping — partition multi-event dates into per-event candidates

**Files:**
- Modify: `src/llama/grouping.py` (full rewrite of the module — same public entry point `group_candidates`)
- Test: `tests/test_grouping.py`

**Interfaces:**
- Consumes: `jerrybase.lookup(artist: str, date: str) -> list[JerrybaseEvent]` (existing; events sorted by `ievent`). `JerrybaseEvent.venue`, `.city`, `.sets: list[JerrybaseSet]`; `JerrybaseSet.closer: str`. `structure.norm_title(str) -> str`, `songs.normalize_song(str) -> str`. `models.Candidate`, `models.RecordingSummary`.
- Produces: `group_candidates(collection: str, docs: list[dict], jerrybase_enabled: bool = True) -> list[Candidate]`. Per-event candidates carry `performance_id == f"{collection}/{date}/e{N}"`; held candidates `f"{collection}/{date}/spans"` and `f"{collection}/{date}/unassigned"`. Single/no-data dates keep `f"{collection}/{date}"` and the legacy `/early`|`/late` suffix.

- [ ] **Step 1: Write the failing tests**

Add to the top of `tests/test_grouping.py` (after the existing `from llama.grouping import group_candidates`):

```python
import pytest

from llama import grouping
from llama.models import JerrybaseEvent, JerrybaseSet


def _event(venue, city, closers):
    return JerrybaseEvent(
        event_id=venue, venue=venue, city=city, state="NY",
        sets=[JerrybaseSet(name=str(i + 1), closer=c, break_length="long")
              for i, c in enumerate(closers)],
    )


def _two_fillmore_events():
    # e1 (early) closes on Turn On Your Lovelight; e2 (late) on And We Bid You Good Night.
    return [
        _event("Fillmore East", "New York", ["Turn On Your Lovelight"]),
        _event("Fillmore West", "San Francisco", ["And We Bid You Good Night"]),
    ]
```

Append these tests to `tests/test_grouping.py`:

```python
def test_single_event_keeps_plain_pid(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup",
                        lambda a, d: [_event("RFK Stadium", "Washington", ["Johnny B. Goode"])])
    cands = group_candidates("GratefulDead", [
        doc("gd73-06-10.sbd.hollister"),
        doc("gd73-06-10.aud.weiner"),
    ])
    assert len(cands) == 1
    assert cands[0].performance_id == "GratefulDead/1973-06-10"
    assert len(cands[0].recordings) == 2


def test_no_jerrybase_data_preserves_early_late(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: [])
    cands = group_candidates("GratefulDead", [
        doc("gd66-07-16.early.aud", date="1966-07-16T00:00:00Z"),
        doc("gd66-07-16.late.aud", date="1966-07-16T00:00:00Z"),
    ])
    ids = sorted(c.performance_id for c in cands)
    assert ids == ["GratefulDead/1966-07-16/early", "GratefulDead/1966-07-16/late"]


def test_two_event_split_by_early_late_text(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: _two_fillmore_events())
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.early.aud", date="1970-02-14T00:00:00Z", description="a set"),
        doc("gd70-02-14.late.sbd", date="1970-02-14T00:00:00Z", description="a set"),
    ])
    ids = sorted(c.performance_id for c in cands)
    assert ids == ["GratefulDead/1970-02-14/e1", "GratefulDead/1970-02-14/e2"]


def test_two_event_split_by_description_closers(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: _two_fillmore_events())
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.aud.a", date="1970-02-14T00:00:00Z",
            description="Cold Rain > Turn On Your Lovelight"),
        doc("gd70-02-14.aud.b", date="1970-02-14T00:00:00Z",
            description="Casey Jones ... And We Bid You Good Night"),
    ])
    by_id = {c.performance_id: c for c in cands}
    assert set(by_id) == {"GratefulDead/1970-02-14/e1", "GratefulDead/1970-02-14/e2"}
    assert by_id["GratefulDead/1970-02-14/e1"].recordings[0].identifier == "gd70-02-14.aud.a"


def test_recording_spanning_both_events_is_held(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: _two_fillmore_events())
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.sbd.complete", date="1970-02-14T00:00:00Z",
            description="Turn On Your Lovelight ... And We Bid You Good Night"),
    ])
    assert [c.performance_id for c in cands] == ["GratefulDead/1970-02-14/spans"]


def test_unassignable_recording_is_held(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: _two_fillmore_events())
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.aud.mystery", date="1970-02-14T00:00:00Z",
            description="a wonderful night of music"),
    ])
    assert [c.performance_id for c in cands] == ["GratefulDead/1970-02-14/unassigned"]


def test_per_event_venue_enrichment_when_archive_absent(monkeypatch):
    monkeypatch.setattr(grouping.jerrybase, "lookup", lambda a, d: _two_fillmore_events())
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.aud.a", date="1970-02-14T00:00:00Z", venue=None, coverage=None,
            description="Turn On Your Lovelight"),
    ])
    c = cands[0]
    assert c.performance_id == "GratefulDead/1970-02-14/e1"
    assert c.venue == "Fillmore East"
    assert c.city == "New York"


def test_jerrybase_disabled_does_not_split(monkeypatch):
    def _boom(a, d):
        raise AssertionError("lookup must not be called when disabled")
    monkeypatch.setattr(grouping.jerrybase, "lookup", _boom)
    cands = group_candidates("GratefulDead", [
        doc("gd70-02-14.late.sbd", date="1970-02-14T00:00:00Z"),
    ], jerrybase_enabled=False)
    assert cands[0].performance_id == "GratefulDead/1970-02-14/late"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_grouping.py -q`
Expected: FAIL — new tests error (`group_candidates()` takes no `jerrybase_enabled`, `grouping.jerrybase` attribute missing, `/eN` pids not produced).

- [ ] **Step 3: Rewrite `src/llama/grouping.py`**

Replace the entire file contents with:

```python
import re
from collections import Counter

from llama import jerrybase
from llama.models import Candidate, RecordingSummary
from llama.songs import normalize_song
from llama.structure import norm_title

_EARLY_LATE = re.compile(r"\b(early|late)\b", re.I)
_EARLY = re.compile(r"\bearly\b", re.I)
_LATE = re.compile(r"\blate\b", re.I)


def _first(value):
    """archive.org fields are sometimes lists; take the first element."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _summary(doc: dict, date: str) -> RecordingSummary:
    rating = _first(doc.get("avg_rating"))
    return RecordingSummary(
        identifier=doc["identifier"],
        title=str(_first(doc.get("title")) or ""),
        date=date,
        venue=_first(doc.get("venue")) or None,
        coverage=_first(doc.get("coverage")) or None,
        avg_rating=float(rating) if rating is not None else None,
        num_reviews=int(_first(doc.get("num_reviews")) or 0),
        downloads=int(_first(doc.get("downloads")) or 0),
        description=str(_first(doc.get("description")) or "") or None,
    )


def _make_candidate(pid, collection, recs, venue=None, city=None) -> Candidate:
    venues = Counter(r.venue for r in recs if r.venue)
    cities = Counter(r.coverage for r in recs if r.coverage)
    return Candidate(
        performance_id=pid,
        collection=collection,
        date=recs[0].date or "",
        venue=venues.most_common(1)[0][0] if venues else venue,
        city=cities.most_common(1)[0][0] if cities else city,
        recordings=recs,
    )


def _contains(tokens: list[str], closer: str) -> bool:
    """True if the normalized closer appears as a contiguous run of description
    tokens (norm_title containment)."""
    seq = norm_title(closer).split()
    if not seq:
        return False
    return any(tokens[i:i + len(seq)] == seq
               for i in range(len(tokens) - len(seq) + 1))


def _assign_recording(rec: RecordingSummary, events: list) -> list[int]:
    """0-based event indices this recording belongs to. [] = unassignable;
    one index = that event; multiple = the tape spans the evening.

    Signals in priority order: (1) early/late text (2-event dates only) in
    identifier/title/description; (2) description set-closer containment."""
    if len(events) == 2:
        text = f"{rec.identifier} {rec.title} {rec.description or ''}"
        early = bool(_EARLY.search(text))
        late = bool(_LATE.search(text))
        if early and late:
            return [0, 1]
        if early:
            return [0]
        if late:
            return [1]
    tokens = normalize_song(rec.description or "").split()
    hits: list[int] = []
    for i, ev in enumerate(events):
        if any(_contains(tokens, s.closer) for s in ev.sets if s.closer):
            hits.append(i)
    return hits


def _partition(collection: str, date: str, recs: list, events: list) -> list[Candidate]:
    by_event: dict[int, list] = {}
    spans: list = []
    unassigned: list = []
    for rec in recs:
        idxs = _assign_recording(rec, events)
        if len(idxs) == 1:
            by_event.setdefault(idxs[0], []).append(rec)
        elif len(idxs) > 1:
            spans.append(rec)
        else:
            unassigned.append(rec)
    out: list[Candidate] = []
    for i in sorted(by_event):
        ev = events[i]
        out.append(_make_candidate(f"{collection}/{date}/e{i + 1}", collection,
                                   by_event[i], venue=ev.venue, city=ev.city))
    if spans:
        out.append(_make_candidate(f"{collection}/{date}/spans", collection, spans))
    if unassigned:
        out.append(_make_candidate(f"{collection}/{date}/unassigned", collection, unassigned))
    return out


def _legacy_split(collection: str, date: str, recs: list) -> list[Candidate]:
    """No-jerrybase-data path: preserve today's per-recording early/late
    identifier-sniff split byte-for-byte."""
    groups: dict[str, list] = {}
    for rec in recs:
        pid = f"{collection}/{date}"
        m = _EARLY_LATE.search(rec.identifier)
        if m:
            pid += f"/{m.group(1).lower()}"
        groups.setdefault(pid, []).append(rec)
    return [_make_candidate(pid, collection, grp) for pid, grp in groups.items()]


def group_candidates(collection: str, docs: list[dict],
                     jerrybase_enabled: bool = True) -> list[Candidate]:
    by_date: dict[str, list[RecordingSummary]] = {}
    for doc in docs:
        date = str(_first(doc.get("date")) or "")[:10]
        if not date:
            continue
        by_date.setdefault(date, []).append(_summary(doc, date))

    candidates: list[Candidate] = []
    for date, recs in by_date.items():
        events = jerrybase.lookup(collection, date) if jerrybase_enabled else []
        if len(events) > 1:
            candidates.extend(_partition(collection, date, recs, events))
        elif len(events) == 1:
            candidates.append(_make_candidate(f"{collection}/{date}", collection, recs))
        else:
            candidates.extend(_legacy_split(collection, date, recs))
    return sorted(candidates, key=lambda c: (c.date, c.performance_id))
```

- [ ] **Step 4: Run the whole grouping suite to verify it passes**

Run: `pytest tests/test_grouping.py -q`
Expected: PASS — the new tests plus all pre-existing tests (`test_same_date_recordings_merge`, `test_early_late_split`, `test_venue_majority_and_missing_date_skipped`, `test_num_reviews_coerced`, `test_list_valued_numeric_fields_coerced`, `test_downloads_mapped_and_defaulted`).

Note: the pre-existing tests do not monkeypatch `jerrybase.lookup`, so they hit the real vendored CSV. `1973-06-10` is single-event there and `1966-07-16`/`1974-05-19` are absent — so `test_same_date_recordings_merge` gets the plain-pid path and `test_early_late_split` gets the legacy split. Both remain green.

- [ ] **Step 5: Commit**

```bash
git add src/llama/grouping.py tests/test_grouping.py
git commit -m "feat: split multi-event dates into per-event candidates at grouping"
```

---

### Task 2: Thread `jerrybase_enabled` through search and the CLI

**Files:**
- Modify: `src/llama/stages/search.py:26-51`
- Modify: `src/llama/cli.py:155`
- Test: `tests/test_stage_search.py`

**Interfaces:**
- Consumes: `group_candidates(collection, docs, jerrybase_enabled=True)` (Task 1). `config.jerrybase.enabled: bool` (existing).
- Produces: `run_search(ws, ia, criteria, artists=None, force=False, jerrybase_enabled=True) -> list[Candidate]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_stage_search.py`:

```python
def test_run_search_splits_multi_event_when_enabled(tmp_path: Path):
    docs = [{"identifier": "gd1970-02-14.late.sbd", "date": "1970-02-14T00:00:00Z",
             "venue": "Fillmore East", "description": "Casey Jones ... And We Bid You Good Night"}]
    ia = StubIA(docs)
    on = run_search(RunWorkspace(tmp_path / "on", "r"), ia,
                    Criteria(query="q", collection="GratefulDead"), jerrybase_enabled=True)
    assert [c.performance_id for c in on] == ["GratefulDead/1970-02-14/e2"]

    off = run_search(RunWorkspace(tmp_path / "off", "r"), StubIA(docs),
                     Criteria(query="q", collection="GratefulDead"), jerrybase_enabled=False)
    assert [c.performance_id for c in off] == ["GratefulDead/1970-02-14/late"]
```

This exercises the real vendored `set_breaks.csv` (`1970-02-14` = 2 events; the `late` identifier + `And We Bid You Good Night` closer both point to e2).

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_stage_search.py::test_run_search_splits_multi_event_when_enabled -q`
Expected: FAIL — `run_search()` has no `jerrybase_enabled` parameter.

- [ ] **Step 3: Add the parameter and pass it through**

In `src/llama/stages/search.py`, change the signature (lines 26-30) to add the parameter:

```python
def run_search(
    ws: RunWorkspace, ia, criteria: Criteria,
    artists: list[dict] | None = None,
    force: bool = False,
    jerrybase_enabled: bool = True,
) -> list[Candidate]:
```

Update both `group_candidates` call sites in the same function:

```python
                candidates.extend(group_candidates(artist["identifier"], docs,
                                                   jerrybase_enabled=jerrybase_enabled))
```

and

```python
        candidates = group_candidates(label, docs, jerrybase_enabled=jerrybase_enabled)
```

In `src/llama/cli.py`, change line 155 to:

```python
    run_search(ws, ia, criteria, artists=artists, force=force,
               jerrybase_enabled=config.jerrybase.enabled)
```

- [ ] **Step 4: Run the search suite to verify it passes**

Run: `pytest tests/test_stage_search.py -q`
Expected: PASS — new test plus the pre-existing search tests (`test_run_search_groups_and_writes` uses `1973-06-10` single-event / `1974-05-19` single-event, both unaffected).

- [ ] **Step 5: Commit**

```bash
git add src/llama/stages/search.py src/llama/cli.py tests/test_stage_search.py
git commit -m "feat: thread jerrybase.enabled into search grouping"
```

---

### Task 3: Gather — select the per-event JerrybaseEvent and re-flag spanning tapes

**Files:**
- Modify: `src/llama/stages/gather.py` (import line 14-15; lines 140-143 event selection; lines 176-179 multi-event flag)
- Test: `tests/test_stage_gather.py`

**Interfaces:**
- Consumes: `Candidate.performance_id` ending in `/eN`, `/spans`, `/unassigned`, or neither (Task 1). `jerrybase.lookup(artist, date)`, `structure.norm_title`.
- Produces: no new public function — behavior change inside `run_gather`. A helper `_event_kind(pid) -> tuple[str | None, int | None]` local to `gather.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stage_gather.py` (the module already imports `jerrybase`, `JerrybaseEvent`, `JerrybaseSet`, and defines `_jb_event`, `make_candidate`, `StubIA`, `IDENT`):

```python
def _event_candidate(suffix):
    c = make_candidate()
    c.performance_id = f"GratefulDead/1973-06-10/{suffix}"
    return c


def test_gather_event_suffix_selects_right_event(tmp_path, monkeypatch):
    # e2's closers are gd73's real set-ends; e1's are songs gd73 never played.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [
        _jb_event([("Bertha", "1"), ("Truckin", "2")], venue="Fillmore East", city="New York"),
        _jb_event([("I Know You Rider", "1"), ("Eyes of the World", "2"),
                   ("Johnny B. Goode", "encore")], venue="Fillmore West", city="San Francisco"),
    ])
    cand = _event_candidate("e2")
    cand.venue = None
    cand.city = None
    show = run_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(), cand, IDENT,
                      jerrybase_enabled=True)
    assert show.venue == "Fillmore West"          # events[1] selected, not events[0]
    assert show.venue_source == "jerrybase"
    assert not any(f.startswith("multi-event date") for f in show.review_flags)
    assert not any("tape spans" in f for f in show.review_flags)
    assert show.needs_review is False


def test_gather_flags_tape_that_spans_events(tmp_path, monkeypatch):
    # /e1 candidate, but tracks carry closers from BOTH events -> mislabeled tape.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [
        _jb_event([("I Know You Rider", "1"), ("Eyes of the World", "2"),
                   ("Johnny B. Goode", "encore")]),
        _jb_event([("Morning Dew", "1")]),
    ])
    show = run_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(),
                      _event_candidate("e1"), IDENT, jerrybase_enabled=True)
    assert show.needs_review is True
    assert "tape spans 2 events" in show.review_flags


def test_gather_spans_candidate_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [
        _jb_event([("Turn On Your Lovelight", "1")]),
        _jb_event([("And We Bid You Good Night", "1")]),
    ])
    show = run_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(),
                      _event_candidate("spans"), IDENT, jerrybase_enabled=True)
    assert show.needs_review is True
    assert "tape spans 2 events" in show.review_flags


def test_gather_unassigned_candidate_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [
        _jb_event([("Turn On Your Lovelight", "1")]),
        _jb_event([("And We Bid You Good Night", "1")]),
    ])
    show = run_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(),
                      _event_candidate("unassigned"), IDENT, jerrybase_enabled=True)
    assert show.needs_review is True
    assert "unassigned multi-event recordings" in show.review_flags
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_stage_gather.py -k "event_suffix or spans or unassigned" -q`
Expected: FAIL — `_event_candidate("e2")` currently gets `event = None` (pid unrecognized), so venue is not adopted and no spans/unassigned flags are produced.

- [ ] **Step 3: Add the suffix helper and rework event selection + flags**

In `src/llama/stages/gather.py`, add `norm_title` to the structure import (lines 14-15) so it reads:

```python
from llama.structure import (align, apply_llm_alignment, blend_segues,
                             from_setlistfm, norm_title, rank_parses, structure_guard)
```

Add this helper just below `log = logging.getLogger("llama")` (after line 18):

```python
_EVENT_SUFFIX = re.compile(r"/e(\d+)$")


def _event_kind(pid: str) -> tuple[str | None, int | None]:
    """Read the per-event grouping suffix: ('event', N) | ('spans', None) |
    ('unassigned', None) | (None, None)."""
    m = _EVENT_SUFFIX.search(pid)
    if m:
        return "event", int(m.group(1))
    tail = pid.rsplit("/", 1)[-1]
    if tail in ("spans", "unassigned"):
        return tail, None
    return None, None
```

Replace the event-selection block (current lines 140-143):

```python
    # Jerrybase structure evidence (no-op for artists absent from the dataset).
    events = jerrybase.lookup(artist, candidate.date) if jerrybase_enabled else []
    event = events[0] if len(events) == 1 else None
```

with:

```python
    # Jerrybase structure evidence (no-op for artists absent from the dataset).
    # A per-event candidate (/eN) selects events[N-1] for every evidence check.
    events = jerrybase.lookup(artist, candidate.date) if jerrybase_enabled else []
    kind, n = _event_kind(candidate.performance_id)
    if kind == "event" and events and 1 <= n <= len(events):
        event = events[n - 1]
    elif kind == "event":
        event = None
    elif len(events) == 1:
        event = events[0]
    else:
        event = None
```

Replace the multi-event tripwire block (current lines 176-179):

```python
    # Multi-event tripwire (groundwork only: identity/ledger unchanged here).
    if len(events) > 1:
        venue_list = ", ".join(sorted({e.venue for e in events}))
        flags.append(f"multi-event date: {len(events)} jerrybase events at {venue_list}")
```

with:

```python
    # Multi-event handling. Held grouping catch-alls flag directly; an
    # unpartitioned multi-event date keeps the blanket flag (defensive); a
    # per-event candidate whose aligned tracks span >1 event was mislabeled.
    if kind == "spans":
        flags.append(f"tape spans {len(events)} events")
    elif kind == "unassigned":
        flags.append("unassigned multi-event recordings")
    elif kind is None and len(events) > 1:
        venue_list = ", ".join(sorted({e.venue for e in events}))
        flags.append(f"multi-event date: {len(events)} jerrybase events at {venue_list}")
    elif kind == "event" and len(events) > 1:
        spanned = sum(
            1 for ev in events
            if any(norm_title(t.title) == norm_title(s.closer)
                   for s in ev.sets for t in tracks)
        )
        if spanned > 1:
            flags.append(f"tape spans {len(events)} events")
```

- [ ] **Step 4: Run the gather suite to verify it passes**

Run: `pytest tests/test_stage_gather.py -q`
Expected: PASS — the four new tests plus every pre-existing gather test. In particular `test_gather_multi_event_flag` still passes: its candidate pid `GratefulDead/1973-06-10` has no recognized suffix (`kind is None`) and `len(events) == 2`, so it takes the blanket `multi-event date` branch exactly as before.

- [ ] **Step 5: Commit**

```bash
git add src/llama/stages/gather.py tests/test_stage_gather.py
git commit -m "feat: gather selects per-event jerrybase evidence and re-flags spanning tapes"
```

---

### Task 4: Capture the real GD 1970-02-14 fixtures (one-time live network)

**Files:**
- Create (committed, via capture): `tests/fixtures/gd1970-02-14_late_metadata.json`
- Create (committed, via capture): `tests/fixtures/gd1970-02-14_spans_metadata.json`
- Create: `tests/test_fixtures_multi_event.py`

**Interfaces:**
- Consumes: `scripts/capture_fixture.py <identifier> <out.json>` (existing; slims archive.org `/metadata` to `metadata`/`files`/`reviews`).
- Produces: two committed fixture files used by Task 5. The two verified identifiers (from archive.org advancedsearch on `collection:GratefulDead AND date:1970-02-14`, numFound=6) are:
  - late-show-only (clean e2): `gd1970-02-14.141007.late.show.sbd.pcm.dalton.miller.clugston.flac1644`
  - complete-evening SBD (spans both shows): `gd1970-02-14.sbd.miller.97644.flac16`

- [ ] **Step 1: Capture the fixtures — LIVE NETWORK STEP**

> **This step makes read-only HTTPS GETs to archive.org.** It must be run in an environment with outbound network. It downloads only JSON metadata (no audio). Run it once; thereafter every test is offline against the committed JSON.

```bash
python scripts/capture_fixture.py \
  gd1970-02-14.141007.late.show.sbd.pcm.dalton.miller.clugston.flac1644 \
  tests/fixtures/gd1970-02-14_late_metadata.json
python scripts/capture_fixture.py \
  gd1970-02-14.sbd.miller.97644.flac16 \
  tests/fixtures/gd1970-02-14_spans_metadata.json
```

Expected output: `wrote tests/fixtures/gd1970-02-14_late_metadata.json` and `wrote tests/fixtures/gd1970-02-14_spans_metadata.json`.

- [ ] **Step 2: Write the offline smoke test**

Create `tests/test_fixtures_multi_event.py`:

```python
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_late_fixture_is_late_only():
    md = _load("gd1970-02-14_late_metadata.json")
    desc = md["metadata"].get("description", "")
    desc = "\n".join(desc) if isinstance(desc, list) else str(desc)
    assert "1970-02-14" in md["metadata"].get("title", "")
    # Late-show-only: closes on the late set-closer, never mentions the early one.
    assert "And We Bid You Good Night" in desc
    assert "Turn On Your Lovelight" not in desc
    assert any(f.get("format") == "Flac" for f in md["files"])


def test_spans_fixture_covers_both_shows():
    md = _load("gd1970-02-14_spans_metadata.json")
    desc = md["metadata"].get("description", "")
    desc = "\n".join(desc) if isinstance(desc, list) else str(desc)
    # A complete-evening tape: both events' closers appear.
    assert "Turn On Your Lovelight" in desc
    assert "And We Bid You Good Night" in desc
    assert any(f.get("format") == "Flac" for f in md["files"])
```

- [ ] **Step 3: Run the smoke test to verify it passes**

Run: `pytest tests/test_fixtures_multi_event.py -q`
Expected: PASS. (If it FAILS with `FileNotFoundError`, Step 1 was not run in a networked environment — re-run Step 1 first.)

- [ ] **Step 4: Commit the fixtures and the smoke test**

```bash
git add tests/fixtures/gd1970-02-14_late_metadata.json \
        tests/fixtures/gd1970-02-14_spans_metadata.json \
        tests/test_fixtures_multi_event.py
git commit -m "test: capture GD 1970-02-14 Fillmore East multi-event fixtures"
```

---

### Task 5: Integration — real fixtures split into distinct per-event shows and ledger rows

**Files:**
- Create: `tests/test_multi_event_integration.py`

**Interfaces:**
- Consumes: `group_candidates` (Task 1), `run_gather` (Task 3), the real vendored `set_breaks.csv` (1970-02-14 = 2 events; `events[1]` = event 802, venue `Fillmore East`, closer `And We Bid You Good Night`), the two committed fixtures (Task 4), `util.slugify`, `ledger.Ledger`, `models.LedgerEntry`.
- Produces: an end-to-end offline test proving one archive date yields two distinct-identity candidates that gather and slug independently and record distinct ledger rows.

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_multi_event_integration.py`:

```python
import json
from pathlib import Path

from llama.grouping import group_candidates
from llama.ledger import Ledger
from llama.llm.fake import FakeProvider
from llama.models import LedgerEntry
from llama.stages.gather import run_gather
from llama.util import slugify
from llama.workspace import ShowWorkspace

FIXTURES = Path(__file__).parent / "fixtures"
LATE_ID = "gd1970-02-14.141007.late.show.sbd.pcm.dalton.miller.clugston.flac1644"
SPANS_ID = "gd1970-02-14.sbd.miller.97644.flac16"


class FixtureIA:
    """Serves each 1970-02-14 fixture by identifier."""

    def __init__(self):
        self.md = {
            LATE_ID: json.loads((FIXTURES / "gd1970-02-14_late_metadata.json").read_text()),
            SPANS_ID: json.loads((FIXTURES / "gd1970-02-14_spans_metadata.json").read_text()),
        }

    def metadata(self, identifier):
        return self.md[identifier]


def _doc(identifier, md):
    m = md["metadata"]
    desc = m.get("description", "")
    desc = "\n".join(desc) if isinstance(desc, list) else str(desc)
    return {"identifier": identifier, "title": m.get("title", ""),
            "date": "1970-02-14T00:00:00Z", "venue": "Fillmore East",
            "coverage": m.get("coverage"), "description": desc}


def test_one_date_two_events_split_and_slug_independently():
    ia = FixtureIA()
    docs = [_doc(LATE_ID, ia.md[LATE_ID]), _doc(SPANS_ID, ia.md[SPANS_ID])]
    cands = {c.performance_id: c for c in group_candidates("GratefulDead", docs)}

    assert "GratefulDead/1970-02-14/e2" in cands       # clean late show
    assert "GratefulDead/1970-02-14/spans" in cands    # complete-evening tape held
    e2, spans = cands["GratefulDead/1970-02-14/e2"], cands["GratefulDead/1970-02-14/spans"]
    assert e2.recordings[0].identifier == LATE_ID
    assert spans.recordings[0].identifier == SPANS_ID
    # Distinct performance identity -> distinct workspace/library slug.
    assert slugify(e2.performance_id) != slugify(spans.performance_id)


def test_per_event_gather_stamps_event_identity(tmp_path):
    ia = FixtureIA()
    docs = [_doc(LATE_ID, ia.md[LATE_ID]), _doc(SPANS_ID, ia.md[SPANS_ID])]
    cands = {c.performance_id: c for c in group_candidates("GratefulDead", docs)}

    e2 = cands["GratefulDead/1970-02-14/e2"]
    late_show = run_gather(ShowWorkspace(tmp_path / "e2"), ia, FakeProvider(), e2, LATE_ID,
                           audio_format="flac", jerrybase_enabled=True)
    assert late_show.performance_id == "GratefulDead/1970-02-14/e2"
    assert late_show.venue == "Fillmore East"          # events[1] = event 802
    assert not any(f.startswith("multi-event date") for f in late_show.review_flags)

    spans = cands["GratefulDead/1970-02-14/spans"]
    held = run_gather(ShowWorkspace(tmp_path / "spans"), ia, FakeProvider(), spans, SPANS_ID,
                      audio_format="flac", jerrybase_enabled=True)
    assert held.needs_review is True
    assert "tape spans 2 events" in held.review_flags


def test_two_events_get_distinct_ledger_rows(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    for pid in ("GratefulDead/1970-02-14/e2", "GratefulDead/1970-02-14/spans"):
        led.record(LedgerEntry(performance_id=pid, artist="Grateful Dead",
                               date="1970-02-14", status="selected", run="r",
                               recorded_at="2026-07-19T00:00:00Z"))
    assert led.played_ids() == {"GratefulDead/1970-02-14/e2", "GratefulDead/1970-02-14/spans"}
```

- [ ] **Step 2: Run the integration test to verify it fails, then passes**

Run: `pytest tests/test_multi_event_integration.py -q`
Expected: PASS once Tasks 1, 3, and 4 are complete. If Task 4's fixtures are missing it FAILS with `FileNotFoundError` (capture them first); if Tasks 1/3 are incomplete it FAILS on the `/e2` / `/spans` assertions.

- [ ] **Step 3: Commit**

```bash
git add tests/test_multi_event_integration.py
git commit -m "test: end-to-end per-event split for GD 1970-02-14"
```

---

### Task 6: Document per-event identity and the no-migration stance

**Files:**
- Modify: `CLAUDE.md` (Architecture "Two modes" bullet; Domain gotchas)

**Interfaces:**
- Consumes: nothing. Produces: documentation only.

- [ ] **Step 1: Update the "Two modes" architecture bullet**

In `CLAUDE.md`, find the `ledger.jsonl` sentence in the "Two modes" bullet:

```
  runs with a `ledger.jsonl` dedup history keyed by performance identity
  (artist + date + venue), not archive.org item id.
```

Append to that bullet:

```
  A date carrying two performances (early/late show) splits at grouping
  time into one show per jerrybase event, keyed `collection/date/eN`
  (e1 = first show); single-event dates and dates with no jerrybase data
  are unchanged. There is deliberately NO ledger migration and NO legacy-id
  compatibility for pre-split `collection/date` rows — purge and re-run.
```

- [ ] **Step 2: Add a Domain-gotchas note**

In `CLAUDE.md`, under the `## Domain gotchas` section, add a new bullet after the "Multiple recordings of the same performance" bullet:

```
- One archive date can hold two performances (early/late show). jerrybase
  `Nevents`/`ievent` is the ground truth; grouping partitions recordings by
  early/late text then description set-closer matching. A tape that spans the
  evening (`.../spans`) or resists assignment (`.../unassigned`) is held for
  review, never split or auto-shipped. gather re-checks the split and flags a
  per-event tape whose tracks actually span both events.
```

- [ ] **Step 3: Verify the docs render and the suite is green**

Run: `pytest -q`
Expected: PASS (full offline suite).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: per-event multi-event date identity, no ledger migration"
```

---

## Self-Review

**1. Spec coverage**

- Identity `collection/date/eN` (ievent order), single-event keeps `collection/date`, early/late folds into e1/e2 — Task 1 (`_partition`, `_assign_recording`, `group_candidates`).
- No-jerrybase-data date byte-identical (incl. `/early`|`/late`) — Task 1 `_legacy_split` + `test_no_jerrybase_data_preserves_early_late`.
- Grouping gets jerrybase access; collection→artist_key via `jerrybase.lookup` — Task 1.
- Partition signals in order (early/late text → closer containment → spans → unassigned) — Task 1 `_assign_recording`; `/spans` and `/unassigned` held.
- Per-event venue/city enrichment when archive absent — Task 1 `_partition` passes `ev.venue`/`ev.city`; `test_per_event_venue_enrichment_when_archive_absent`.
- Gather `/eN` selects `events[N-1]` for all evidence checks — Task 3 event-selection block.
- Blanket multi-event flag only for spans/unassigned/unpartitioned — Task 3 flag block.
- Spans-both detection at gather from aligned tracks — Task 3 `kind == "event"` branch.
- Ledger/workspace/packaging unchanged; slugs inherit `/eN` — verified in Task 5 (`slugify`, `Ledger`), no code change needed.
- New fixture captured one-time, offline thereafter — Task 4 (live step marked).
- Unit (grouping) + unit (gather) + end-to-end (fake backend) — Tasks 1, 3, 5.
- No ledger migration / legacy compat — Global Constraints + Task 6 docs; no such code anywhere.
- `jerrybase.enabled` honored in grouping — Task 2 + `test_jerrybase_disabled_does_not_split`.

No gaps found.

**2. Placeholder scan** — no TBD/TODO/"handle edge cases"/"similar to Task N". Every code and test step carries complete literal code.

**3. Type consistency** — `group_candidates(collection, docs, jerrybase_enabled=True)` defined in Task 1, consumed with that exact keyword in Tasks 2 and 5. `_event_kind` returns `("event", int) | ("spans"|"unassigned", None) | (None, None)`, consumed consistently in Task 3. Flag strings are identical everywhere they appear: `f"tape spans {len(events)} events"` (grouping-suffix and spans-both paths both render `tape spans 2 events` for a 2-event date), `"unassigned multi-event recordings"`, `"multi-event date: {n} jerrybase events at {venues}"` (unchanged). Pid suffixes `/eN`, `/spans`, `/unassigned` are produced in Task 1 and parsed by the same spellings in Task 3. `run_gather(..., audio_format="flac", jerrybase_enabled=True)` matches the existing signature.

Fixed inline during review: a confusing `FakeProvider() and StubIA()` idiom in `test_gather_unassigned_candidate_flag` was simplified to `StubIA()`.
</content>
</invoke>
