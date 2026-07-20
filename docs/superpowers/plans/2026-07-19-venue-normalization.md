# Venue-name Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the jerrybase venue-mismatch tripwire from false-holding shows whose archive and jerrybase venue strings are high-confidence equivalents (RFK ↔ Robert F. Kennedy Stadium, MSG ↔ Madison Square Garden, Winterland ↔ Winterland Arena).

**Architecture:** Add a pure, deterministic predicate `venues_equivalent(a, b)` in `structure.py` alongside `norm_title`, with `_norm_place`'s tokenizer moved there as its shared basis. The gather stage's venue check swaps normalized-string inequality for `not venues_equivalent(...)`; flag text is unchanged. Three owner-approved rider nits ship in the same plan: a `write_bytes`/artist-column fix in the refresh script, a soft-closer-notes fix in gather, and a cosmetic CLAUDE.md re-wrap.

**Tech Stack:** Python 3, pytest, Pydantic. Tests run offline against the `fake` LLM backend and captured archive.org fixtures (`pytest -q`).

## Global Constraints

- Matching is **conservative, deterministic, offline** — no LLM, no curated alias data file. Only high-confidence equivalence patterns auto-pass; when uncertain, the caller still trips the flag. (spec: Decision)
- Venue is **NOT** part of performance identity (`performance_id` is `collection/date[/eN]`). This feature touches **only** the gather tripwire comparison — never grouping, ledger, or dedup. (spec: Scope note / Out of scope)
- **No fuzzy scoring** (edit distance, token-overlap thresholds) and **no LLM adjudication** of mismatches. (spec: Out of scope)
- The venue-mismatch **flag text is unchanged**: `f"venue mismatch: archive '{venue}' vs jerrybase '{event.venue}'"`. (spec: Design — "Flag text unchanged")
- `venues_equivalent` lives in `structure.py` alongside `norm_title` (no new module). (plan decision, permitted by spec Design)
- Tests are offline and deterministic; run with `pytest -q`.

---

## File Structure

- `src/llama/structure.py` — gains `venues_equivalent` plus the private helpers `_place_tokens`, `_tokens_equal`, `_token_subset`, `_acronym_match`, and the constants `_PLACE_STOPWORDS`, `_PLACE_ABBREV`. This is the home for pure performance/venue string logic; `norm_title` already lives here.
- `src/llama/stages/gather.py` — venue check calls `venues_equivalent`; the now-dead `_norm_place` helper and its sole `import re` are removed. The `structure_info` construction is restructured so soft notes survive when there is no setlist parse.
- `src/llama/models.py` — `StructureInfo.source` doc-comment gains the `"none"` value.
- `scripts/refresh_jerrybase.py` — writes bytes, and degrades gracefully when the upstream CSV lacks an `artist` column.
- `CLAUDE.md` — jerrybase paragraph re-wrapped (cosmetic only).
- Tests: `tests/test_structure.py` (predicate unit tests), `tests/test_stage_gather.py` (venue-equivalence integration + flipped mismatch test + soft-notes regression), `tests/test_refresh_jerrybase.py` (new file, artist-column guard).

---

### Task 1: `venues_equivalent` predicate in `structure.py`

**Files:**
- Modify: `src/llama/structure.py` (insert a venue-equivalence block immediately after `norm_title`, before `from_setlistfm`)
- Test: `tests/test_structure.py` (append)

**Interfaces:**
- Consumes: `import re` (already imported at the top of `structure.py`).
- Produces:
  - `venues_equivalent(a: str, b: str) -> bool` — pure, symmetric, total (never raises). Two empty/whitespace-only venues are equivalent; one empty vs one non-empty is not.
  - Private helpers `_place_tokens(s: str) -> list[str]`, `_tokens_equal(a: str, b: str) -> bool`, `_token_subset(sub: list[str], sup: list[str]) -> bool`, `_acronym_match(short: list[str], long: list[str]) -> bool` (Task 2 does not reference these directly — only `venues_equivalent`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_structure.py`:

```python

import pytest

from llama.structure import venues_equivalent


@pytest.mark.parametrize("a,b", [
    ("RFK Stadium", "Robert F. Kennedy Stadium"),   # initialism + shared tail
    ("MSG", "Madison Square Garden"),               # bare initialism
    ("Winterland", "Winterland Arena"),             # token subset
    ("Barton Hall", "Barton Hall, Cornell University"),  # subset, city/school tail
    ("Fillmore Aud", "Fillmore Auditorium"),        # abbreviation expansion
    ("Fillmore East", "Fillmore East (New York)"),  # parenthetical tail dropped
    ("Fillmore Theatre", "Fillmore Theater"),       # theatre/theater
    ("The Spectrum", "Spectrum"),                   # stopword dropped
    ("RFK Stadium", "RFK Stadium"),                 # identity
])
def test_venues_equivalent_true(a, b):
    assert venues_equivalent(a, b)
    assert venues_equivalent(b, a)   # symmetric


@pytest.mark.parametrize("a,b", [
    ("Fillmore East", "Fillmore West"),             # different halls
    ("Boston Garden", "Boston Music Hall"),         # different venues, shared city
    ("Winterland", "Warfield"),                     # unrelated
])
def test_venues_not_equivalent(a, b):
    assert not venues_equivalent(a, b)
    assert not venues_equivalent(b, a)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_structure.py -k venues -q`
Expected: FAIL with `ImportError: cannot import name 'venues_equivalent' from 'llama.structure'`.

- [ ] **Step 3: Write the implementation**

In `src/llama/structure.py`, replace this exact block:

```python
def norm_title(title: str) -> str:
    return normalize_song(_STRUCTURE_PREFIX.sub("", title))


def from_setlistfm(raw: dict) -> ParsedSetlist | None:
```

with:

```python
def norm_title(title: str) -> str:
    return normalize_song(_STRUCTURE_PREFIX.sub("", title))


# --- Venue equivalence (jerrybase venue-mismatch tripwire) -------------------
# Conservative, deterministic, offline. Only high-confidence equivalences
# auto-pass; when uncertain, callers still flag. No fuzzy scoring, no aliases.

# Connective/positional tokens dropped before comparison.
_PLACE_STOPWORDS = {"the", "at", "of", "and"}

# Token-wise abbreviation expansions applied before matching. Each token maps to
# the set of full forms it may stand for; two tokens are equal when their
# expansion sets intersect ("st" is ambiguous, so any matching expansion counts).
_PLACE_ABBREV = {
    "aud": {"auditorium"},
    "theatre": {"theater"},
    "theater": {"theater"},
    "univ": {"university"},
    "coll": {"college"},
    "mem": {"memorial"},
    "ctr": {"center"},
    "cntr": {"center"},
    "gym": {"gymnasium"},
    "st": {"street", "state"},
}


def _place_tokens(s: str) -> list[str]:
    """Shared venue tokenizer: lowercase, alphanumerics only, stopwords dropped.
    (Replaces gather's old _norm_place; that folded to a joined string, this
    keeps tokens for subset/initialism comparison.)"""
    norm = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return [t for t in norm.split() if t not in _PLACE_STOPWORDS]


def _tokens_equal(a: str, b: str) -> bool:
    return a == b or bool(_PLACE_ABBREV.get(a, {a}) & _PLACE_ABBREV.get(b, {b}))


def _token_subset(sub: list[str], sup: list[str]) -> bool:
    return bool(sub) and all(any(_tokens_equal(x, y) for y in sup) for x in sub)


def _acronym_match(short: list[str], long: list[str]) -> bool:
    """True if `short`'s tokens match `long`'s in order, where a short token may
    be an initialism (>=2 letters) spelling a contiguous run of long tokens:
    [rfk, stadium] matches [robert, f, kennedy, stadium]."""
    i = j = 0
    while i < len(short) and j < len(long):
        s = short[i]
        if _tokens_equal(s, long[j]):
            i += 1
            j += 1
            continue
        if len(s) >= 2 and s.isalpha():
            run = 0
            k = j
            while k < len(long) and run < len(s) and long[k][0] == s[run]:
                run += 1
                k += 1
            if run == len(s):
                i += 1
                j = k
                continue
        return False
    return i == len(short) and j == len(long)


def venues_equivalent(a: str, b: str) -> bool:
    """Conservative venue-name equivalence for the jerrybase tripwire. Equivalent
    iff (after tokenizing and dropping stopwords) one token set is a subset of
    the other, or one side's initialism spells the other (RFK <-> Robert F.
    Kennedy). Abbreviations (aud/auditorium, theatre/theater, ...) are folded in
    token-wise. Anything less certain returns False so the caller still flags."""
    ta, tb = _place_tokens(a), _place_tokens(b)
    if not ta and not tb:
        return True
    if not ta or not tb:
        return False
    if _token_subset(ta, tb) or _token_subset(tb, ta):
        return True
    return _acronym_match(ta, tb) or _acronym_match(tb, ta)


def from_setlistfm(raw: dict) -> ParsedSetlist | None:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_structure.py -k venues -q`
Expected: PASS (24 parametrized assertions across the two tests).

- [ ] **Step 5: Run the full structure suite to check for regressions**

Run: `pytest tests/test_structure.py -q`
Expected: PASS (no existing test touched).

- [ ] **Step 6: Commit**

```bash
git add src/llama/structure.py tests/test_structure.py
git commit -m "feat: add venues_equivalent predicate for venue normalization"
```

---

### Task 2: Wire `venues_equivalent` into the gather venue check

**Files:**
- Modify: `src/llama/stages/gather.py` (remove `import re` at `:2`; remove `_norm_place` at `:20-25`; add `venues_equivalent` to the `llama.structure` import at `:13-14`; change the venue-check `elif` at `:186`)
- Test: `tests/test_stage_gather.py` (flip `test_gather_flags_venue_mismatch_never_overwrites`; add a venue-equivalence integration test)

**Interfaces:**
- Consumes: `venues_equivalent(a: str, b: str) -> bool` from `llama.structure` (Task 1).
- Produces: no new public interface. The venue check now reads `elif not venues_equivalent(venue, event.venue):`.

- [ ] **Step 1: Update the existing mismatch test to a genuine mismatch, and add the equivalence test**

In `tests/test_stage_gather.py`, replace this exact test:

```python
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
```

with:

```python
def test_gather_flags_venue_mismatch_never_overwrites(tmp_path, monkeypatch):
    # A genuinely different venue must still trip the flag, and never overwrite
    # the candidate's venue.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")],
        venue="Boston Garden", city="Boston")])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.venue == "RFK Stadium"          # candidate venue preserved
    assert show.venue_source == "item"
    assert any("venue mismatch" in f for f in show.review_flags)


def test_gather_venue_equivalent_passes_no_mismatch(tmp_path, monkeypatch):
    # Spec integration test: archive "RFK Stadium" vs jerrybase "Robert F.
    # Kennedy Stadium" is a high-confidence equivalence -> no mismatch flag.
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("I Know You Rider", "1"), ("Eyes of the World", "2"),
         ("Johnny B. Goode", "encore")],
        venue="Robert F. Kennedy Stadium", city="Washington")])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.venue == "RFK Stadium"          # never overwritten
    assert show.venue_source == "item"
    assert not any("venue mismatch" in f for f in show.review_flags)
    assert show.needs_review is False
```

- [ ] **Step 2: Run the two tests to verify the equivalence test fails**

Run: `pytest tests/test_stage_gather.py -k "venue_equivalent or never_overwrites" -q`
Expected: `test_gather_venue_equivalent_passes_no_mismatch` FAILS (a "venue mismatch" flag is still raised, so `needs_review` is `True`). `test_gather_flags_venue_mismatch_never_overwrites` PASSES (Boston Garden is a real mismatch under both old and new code).

- [ ] **Step 3: Add the import**

In `src/llama/stages/gather.py`, replace this exact import:

```python
from llama.structure import (align, apply_llm_alignment, blend_segues,
                             from_setlistfm, rank_parses, structure_guard)
```

with:

```python
from llama.structure import (align, apply_llm_alignment, blend_segues,
                             from_setlistfm, rank_parses, structure_guard,
                             venues_equivalent)
```

- [ ] **Step 4: Remove the dead `_norm_place` helper and its `import re`**

In `src/llama/stages/gather.py`, replace this exact block:

```python
log = logging.getLogger("llama")


def _norm_place(s: str) -> str:
    """Lowercase, alphanumerics and spaces only, collapsed whitespace - the
    normal form for comparing archive and jerrybase venue strings."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split())


def _description(meta: dict) -> str:
```

with:

```python
log = logging.getLogger("llama")


def _description(meta: dict) -> str:
```

Then, at the top of the file, delete the now-unused `import re` line (it is the second line, immediately after `import logging`). Replace this exact block:

```python
import logging
import re

from llama import jerrybase
```

with:

```python
import logging

from llama import jerrybase
```

- [ ] **Step 5: Swap the venue check**

In `src/llama/stages/gather.py`, replace this exact line:

```python
        elif _norm_place(venue) != _norm_place(event.venue):
```

with:

```python
        elif not venues_equivalent(venue, event.venue):
```

- [ ] **Step 6: Run the venue tests to verify they pass**

Run: `pytest tests/test_stage_gather.py -k "venue" -q`
Expected: PASS (equivalence test, flipped mismatch test, and the existing `test_gather_adopts_venue_when_candidate_absent` all green).

- [ ] **Step 7: Run the full gather suite to check for regressions**

Run: `pytest tests/test_stage_gather.py -q`
Expected: PASS. (Confirms removing `import re`/`_norm_place` broke nothing — `re` had no other use in this module.)

- [ ] **Step 8: Commit**

```bash
git add src/llama/stages/gather.py tests/test_stage_gather.py
git commit -m "feat: use venues_equivalent for the jerrybase venue tripwire"
```

---

### Task 3: Record soft closer-notes even when there is no setlist parse

**Files:**
- Modify: `src/llama/stages/gather.py` (the `structure_info` construction near `:211-215`)
- Modify: `src/llama/models.py` (`StructureInfo.source` doc-comment at `:138`)
- Test: `tests/test_stage_gather.py` (append a regression test)

**Interfaces:**
- Consumes: `StructureInfo(source: str, alignment: str, coverage: float, conflicts: list[str])` from `llama.models` (unchanged signature); `jerrybase.closer_contradictions` already appends soft notes into the local `notes` list.
- Produces: `Show.structure` is non-`None` whenever there are notes to record, with `source == "none"` when no setlist parse was chosen (`best is None`).

**Context (the bug):** `jerrybase.closer_contradictions` returns soft notes for closers absent from the tracks, appended to `notes`. But `notes` reaches the artifact only through `StructureInfo.conflicts`, which today is built solely when `best is not None`. When no recording description parses and the LLM fallback does not fire, `best is None`, so `structure_info` stays `None` and the soft notes are silently dropped.

- [ ] **Step 1: Write the failing regression test**

Append to `tests/test_stage_gather.py`:

```python
def test_gather_records_soft_closer_notes_without_setlist_parse(tmp_path, monkeypatch):
    # Empty description -> no LMA parse and no LLM fallback (best is None), so
    # tracks resolve from the fixture's tags. A jerrybase closer absent from the
    # tracks must still be recorded as a soft note despite there being no
    # setlist source.
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = ""
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [_jb_event(
        [("Truckin", "1")], venue="RFK Stadium")])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    assert show.structure is not None
    assert show.structure.source == "none"
    assert any("Truckin" in c and "not found in tracks" in c
               for c in show.structure.conflicts)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_stage_gather.py::test_gather_records_soft_closer_notes_without_setlist_parse -q`
Expected: FAIL with `AssertionError` on `assert show.structure is not None` (structure is `None` because `best is None`).

- [ ] **Step 3: Restructure the `structure_info` construction**

In `src/llama/stages/gather.py`, replace this exact block:

```python
    structure_info = None
    if best is not None:
        structure_info = StructureInfo(source=best.source, alignment=alignment,
                                       coverage=result.coverage,
                                       conflicts=result.conflicts + notes)
```

with:

```python
    structure_info = None
    if best is not None or notes:
        source = best.source if best is not None else "none"
        structure_info = StructureInfo(source=source, alignment=alignment,
                                       coverage=result.coverage,
                                       conflicts=result.conflicts + notes)
```

- [ ] **Step 4: Document the new `source` value**

In `src/llama/models.py`, replace this exact line:

```python
    source: str  # "setlist.fm" | "chosen" | "lma:<identifier>" | "llm"
```

with:

```python
    source: str  # "setlist.fm" | "chosen" | "lma:<identifier>" | "llm" | "none"
```

- [ ] **Step 5: Run the regression test to verify it passes**

Run: `pytest tests/test_stage_gather.py::test_gather_records_soft_closer_notes_without_setlist_parse -q`
Expected: PASS.

- [ ] **Step 6: Run the full gather suite to check for regressions**

Run: `pytest tests/test_stage_gather.py -q`
Expected: PASS. (In particular `test_gather_flags_unresolved` still passes: empty description with no jerrybase produces no notes, so `structure` stays `None` there.)

- [ ] **Step 7: Commit**

```bash
git add src/llama/stages/gather.py src/llama/models.py tests/test_stage_gather.py
git commit -m "fix: record soft closer-notes when there is no setlist parse"
```

---

### Task 4: Harden `refresh_jerrybase.py` (byte-write + artist-column guard)

**Files:**
- Modify: `scripts/refresh_jerrybase.py` (add `_require_artist_column` helper; call it in `main`; change the final write to `write_bytes`)
- Test: `tests/test_refresh_jerrybase.py` (new file)

**Interfaces:**
- Consumes: module-level `csv`, `io`, `sys`, and `VENDORED` (all already present in the script).
- Produces: `_require_artist_column(text: str) -> None` — returns normally when the CSV header contains an `artist` column; otherwise prints a clear message to stderr and raises `SystemExit(1)` (no traceback).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_refresh_jerrybase.py`:

```python
import importlib.util
from pathlib import Path

import pytest

# scripts/ is not an importable package; load the module directly by path.
_PATH = Path(__file__).resolve().parent.parent / "scripts" / "refresh_jerrybase.py"
_spec = importlib.util.spec_from_file_location("refresh_jerrybase", _PATH)
refresh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refresh)


def test_require_artist_column_accepts_valid_csv():
    # No raise when the header has an artist column.
    refresh._require_artist_column("artist,date,show_set\nGratefulDead,1977-05-08,Set 1\n")


def test_require_artist_column_exits_without_artist():
    with pytest.raises(SystemExit) as excinfo:
        refresh._require_artist_column("date,venue\n1977-05-08,Barton Hall\n")
    assert excinfo.value.code == 1


def test_require_artist_column_exits_on_empty_input():
    with pytest.raises(SystemExit) as excinfo:
        refresh._require_artist_column("")
    assert excinfo.value.code == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_refresh_jerrybase.py -q`
Expected: FAIL with `AttributeError: module 'refresh_jerrybase' has no attribute '_require_artist_column'`.

- [ ] **Step 3: Add the guard helper**

In `scripts/refresh_jerrybase.py`, replace this exact block:

```python
def _coverage(text: str) -> tuple[int, Counter]:
    rows = list(csv.DictReader(io.StringIO(text)))
    return len(rows), Counter(r["artist"] for r in rows)
```

with:

```python
def _coverage(text: str) -> tuple[int, Counter]:
    rows = list(csv.DictReader(io.StringIO(text)))
    return len(rows), Counter(r["artist"] for r in rows)


def _require_artist_column(text: str) -> None:
    """Exit cleanly (message + non-zero status, no traceback) when the CSV has
    no 'artist' column, rather than crashing deep inside _coverage."""
    fields = csv.DictReader(io.StringIO(text)).fieldnames
    if not fields or "artist" not in fields:
        print(f"error: downloaded CSV has no 'artist' column (columns: {fields}); "
              f"refusing to overwrite {VENDORED}", file=sys.stderr)
        raise SystemExit(1)
```

- [ ] **Step 4: Call the guard and switch to `write_bytes`**

In `scripts/refresh_jerrybase.py`, replace this exact block:

```python
    resp = httpx.get(url, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    new_text = resp.text

    old_text = VENDORED.read_text(encoding="utf-8") if VENDORED.exists() else ""
```

with:

```python
    resp = httpx.get(url, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    new_text = resp.text
    _require_artist_column(new_text)

    old_text = VENDORED.read_text(encoding="utf-8") if VENDORED.exists() else ""
```

Then, in the same file, replace this exact line:

```python
    VENDORED.write_text(new_text, encoding="utf-8")
```

with:

```python
    VENDORED.write_bytes(resp.content)  # exact upstream bytes (no CRLF rewrite)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_refresh_jerrybase.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/refresh_jerrybase.py tests/test_refresh_jerrybase.py
git commit -m "fix: refresh_jerrybase writes bytes and guards a missing artist column"
```

---

### Task 5: Re-wrap the CLAUDE.md jerrybase paragraph (cosmetic)

**Files:**
- Modify: `CLAUDE.md` (the jerrybase paragraph, currently lines 63-71)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. Documentation-only, no content change — the byte content of the text is identical, only line wrapping changes.

- [ ] **Step 1: Re-wrap the ragged lines**

In `CLAUDE.md`, replace this exact block:

```
  a vendored, offline jerrybase-derived dataset
  (`src/llama/data/set_breaks.csv`, GPL-3.0 from deadstream; refresh via
  `scripts/refresh_jerrybase.py`): gather uses it after alignment as a
  tripwire (multi-event dates, venue mismatch, contradicted set breaks, wrong
  set count) and a deterministic break-anchoring corrector, never as a
  setlist source (`[jerrybase] enabled`, default on). Nine named touchpoints,
  each with a prompt template file under `prompts/` and a Pydantic output
  schema. LLM calls live only at stage
  boundaries — everything else is deterministic.
```

with:

```
  a vendored, offline jerrybase-derived dataset
  (`src/llama/data/set_breaks.csv`, GPL-3.0 from deadstream; refresh via
  `scripts/refresh_jerrybase.py`): gather uses it after alignment as a
  tripwire (multi-event dates, venue mismatch, contradicted set breaks, wrong
  set count) and a deterministic break-anchoring corrector, never as a setlist
  source (`[jerrybase] enabled`, default on). Nine named touchpoints, each
  with a prompt template file under `prompts/` and a Pydantic output schema.
  LLM calls live only at stage boundaries — everything else is deterministic.
```

- [ ] **Step 2: Verify no content changed**

Run: `git diff CLAUDE.md`
Expected: only line-wrap differences within the jerrybase paragraph (the same words, re-flowed). No word added or removed.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: re-wrap the jerrybase paragraph in CLAUDE.md"
```

---

## Final Verification

- [ ] **Run the full suite**

Run: `pytest -q`
Expected: PASS (all pre-existing tests plus the new venue-equivalence, soft-notes, and refresh-guard tests).

---

## Self-Review

**1. Spec coverage:**
- Problem / Decision — conservative deterministic offline predicate: Task 1. ✅
- Design rule 1 (normalized equality): Task 1, `_token_subset` with equal token sets (equality is subset-both-ways). ✅
- Design rule 2 (initialism match): Task 1, `_acronym_match`. ✅
- Design rule 3 (token-subset after stopword drop): Task 1, `_place_tokens` + `_token_subset`. ✅
- Design rule 4 (abbreviation expansion, token-wise, `st` ambiguous set): Task 1, `_PLACE_ABBREV` + `_tokens_equal`. ✅
- Design — `venues_equivalent` located in `structure.py` alongside `norm_title`; `_norm_place`'s tokenizer moved there as `_place_tokens`: Tasks 1 & 2. ✅
- Design — call site swap in `stages/gather.py`, flag text unchanged: Task 2. ✅
- Error handling — pure predicate, None/empty at the call site (call site already guards absent venue via the adoption branch; predicate is still total for empty inputs): Tasks 1 & 2. ✅
- Testing — table-driven equivalent/non-equivalent unit tests: Task 1. ✅
- Testing — gather integration test (real gd73-06-10 "RFK Stadium" vs "Robert F. Kennedy Stadium", no mismatch flag): Task 2, `test_gather_venue_equivalent_passes_no_mismatch`. ✅
- Testing — existing `[jerrybase] enabled = false` isolation untouched: no pipeline/cli e2e test is modified. ✅
- Scope note / Out of scope — no grouping/ledger/identity change; no fuzzy scoring, alias file, or LLM: Global Constraints; nothing in any task touches those. ✅
- Rider — refresh_jerrybase `write_bytes` + artist-column graceful degrade: Task 4. ✅
- Rider — soft closer-notes recorded regardless of `best is None`, with regression test: Task 3. ✅
- Rider — CLAUDE.md jerrybase paragraph re-wrap (cosmetic): Task 5. ✅

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N". Every code step shows complete code. ✅

**3. Type consistency:** `venues_equivalent(a: str, b: str) -> bool` is defined in Task 1 and called with that signature in Task 2. Helper names (`_place_tokens`, `_tokens_equal`, `_token_subset`, `_acronym_match`) are used consistently within Task 1. `StructureInfo(source, alignment, coverage, conflicts)` in Task 3 matches the model in `models.py`. `_require_artist_column(text) -> None` defined and called consistently in Task 4. The removed `_norm_place` has no remaining reference after Task 2 (verified: `re` and `_norm_place` occur only in the venue helper and check). ✅
