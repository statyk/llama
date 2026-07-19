# Deadstream Lessons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the four deadstream lessons: tag-title cleanup, track-tag
ordering, a sibling-relative downloads signal, and a title-fraction bonus
in recording selection.

**Architecture:** Two new pure helpers in `titles.py` define "cleaned tag
title" and "real title" for the whole codebase. `junk.filter_files` gains
tag-aware canonical ordering and returns an ordering report. Selection
(`scoring.py` + `stages/select_recording.py`) gains two bounded additive
score terms. Spec: `docs/superpowers/specs/2026-07-19-deadstream-lessons-design.md`.

**Tech Stack:** Python 3.11+, pydantic v2, pytest (offline; fixtures under
`tests/fixtures/`). Run tests with the venv active (`source .venv/bin/activate`).

## Global Constraints

- Prefix-strip regex (spec-fixed): `^[a-zA-Z]{2,5}_*\d{2}(?:\d{2})?[-.]\d{2}[-.]\d{2}\s*(?:[td]\d+)*`
- Real title = cleaned, non-empty, ≥3 ASCII letters ("Deal"/"Jam" real, "d1t02" not)
- `DOWNLOADS_WEIGHT = 0.75`, `TITLE_WEIGHT = 0.5` — constants in `scoring.py`, no config surface
- Track-tag order used ONLY when every kept file has a parseable, unique track number; else filename order
- New model fields must default (old artifacts/JSON must still load)
- All tests offline (`pytest -q`); never commit audio files
- Commit messages: conventional prefix (`feat:`/`test:`/`docs:`), end with the
  Co-Authored-By + Claude-Session trailer used in this repo

---

### Task 1: `clean_tag_title` / `is_real_title` + resolve_titles adoption

**Files:**
- Modify: `src/llama/titles.py`
- Test: `tests/test_titles.py`

**Interfaces:**
- Produces: `clean_tag_title(raw: str | None) -> str` and
  `is_real_title(cleaned: str) -> bool` in `llama.titles` — Tasks 3 and 6
  import both. `resolve_titles` behavior change: a tag title is used only
  when `is_real_title(clean_tag_title(...))`; the cleaned form is what's
  stored on the Track.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_titles.py` (add `import pytest` and extend the
existing `from llama.titles import ...` line with `clean_tag_title, is_real_title`):

```python
@pytest.mark.parametrize("raw,cleaned", [
    ("gd73-06-10d1t04 Here Comes Sunshine", "Here Comes Sunshine"),
    ("gd1977-05-08t12 Scarlet Begonias.flac", "Scarlet Begonias"),
    ("gd73.06.10d1t01 - Morning Dew", "Morning Dew"),
    ("gd73-06-10d1t04.mp3", ""),          # pure filename residue
    ("unknown", ""),
    ("Unknown", ""),
    ("Here Comes Sunshine", "Here Comes Sunshine"),  # plain titles untouched
    ("Deal", "Deal"),
    (None, ""),
])
def test_clean_tag_title(raw, cleaned):
    assert clean_tag_title(raw) == cleaned


@pytest.mark.parametrize("cleaned,real", [
    ("Deal", True), ("Jam", True), ("Here Comes Sunshine", True),
    ("d1t02", False), ("", False), ("A B", False),
])
def test_is_real_title(cleaned, real):
    assert is_real_title(cleaned) is real


def test_junk_tag_title_falls_through_cascade():
    # tag is filename residue -> cleaned to junk -> setlist wins
    files = make_files(["gd73-06-10d1t01.mp3", "China Cat Sunflower",
                        None, "Dark Star", None, None])
    tracks = resolve_titles(files, make_setlist())
    assert tracks[0].title == "Morning Dew"
    assert tracks[0].title_source == "setlist"


def test_tag_title_is_stored_cleaned():
    files = make_files(["gd73-06-10d1t01 Morning Dew", "China Cat Sunflower",
                        "I Know You Rider", "Dark Star", "Eyes of the World",
                        "Johnny B. Goode"])
    tracks = resolve_titles(files, make_setlist())
    assert tracks[0].title == "Morning Dew"
    assert tracks[0].title_source == "tags"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_titles.py -q`
Expected: FAIL — `ImportError: cannot import name 'clean_tag_title'`

- [ ] **Step 3: Implement**

In `src/llama/titles.py`, add at the top (after existing imports):

```python
import re

# Identifier prefix embedded in tag titles ("gd73-06-10d1t04 Here Comes
# Sunshine"): 2-5 letters, 2- or 4-digit year, -/. separated date, then
# optional disc/track tokens. Adapted from deadstream, extended to 4-digit
# years.
_ID_PREFIX = re.compile(r"^[a-zA-Z]{2,5}_*\d{2}(?:\d{2})?[-.]\d{2}[-.]\d{2}\s*(?:[td]\d+)*")
_AUDIO_EXT = re.compile(r"\.(?:mp3|flac|ogg|shn)\s*$", re.I)
_EDGE_JUNK = " \t-–—_.|"


def clean_tag_title(raw: str | None) -> str:
    """Strip identifier prefix / audio extension from an embedded tag title.
    "unknown" is never a real title and maps to ""."""
    s = _ID_PREFIX.sub("", str(raw or "").strip())
    s = _AUDIO_EXT.sub("", s)
    s = s.strip(_EDGE_JUNK)
    return "" if s.lower() == "unknown" else s


def is_real_title(cleaned: str) -> bool:
    """At least 3 ASCII letters: accepts real short titles (Deal, Jam),
    rejects date-less filename residue (d1t02)."""
    return sum(ch.isascii() and ch.isalpha() for ch in cleaned) >= 3
```

In `resolve_titles`, replace:

```python
        tag_title = str(f.get("title") or "").strip()
        if tag_title:
            title, source = tag_title, "tags"
```

with:

```python
        tag_title = clean_tag_title(f.get("title"))
        if is_real_title(tag_title):
            title, source = tag_title, "tags"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_titles.py tests/test_stage_gather.py -q`
Expected: PASS (gather tests confirm no regression — fixture tag titles
are plain and pass through unchanged)

- [ ] **Step 5: Commit**

```bash
git add src/llama/titles.py tests/test_titles.py
git commit -m "feat: clean identifier prefixes from embedded tag titles"
```

---

### Task 2: Track-tag ordering in filter_files

**Files:**
- Modify: `src/llama/junk.py`, `src/llama/titles.py` (drop re-sort),
  `src/llama/models.py` (Show fields), `src/llama/stages/gather.py`,
  `src/llama/stages/select_recording.py`, `tests/test_live_smoke.py`
- Test: `tests/test_junk.py`

**Interfaces:**
- Consumes: nothing from Task 1 (independent).
- Produces: `filter_files(files, want_format="VBR MP3") -> tuple[list[dict], list[dict], dict]`
  — third element is `{"order_source": "track-tags" | "filename", "reordered": bool}`.
  `kept` is in canonical play order; `resolve_titles` now PRESERVES input
  order (no internal sort). `Show` gains `order_source: str = "filename"`
  and `reordered: bool = False`. Task 6 unpacks the 3-tuple.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_junk.py`:

```python
def _mp3(name, track=None, source="original", original=None, length="300.0"):
    d = {"name": name, "format": "VBR MP3", "source": source, "length": length}
    if track is not None:
        d["track"] = track
    if original is not None:
        d["original"] = original
    return d


def test_unique_track_tags_reorder():
    # filename order d1t01,d1t02,d1t03 but tags say d1t03 plays first
    files = [_mp3("gd73d1t01.mp3", track="2"), _mp3("gd73d1t02.mp3", track="3/16"),
             _mp3("gd73d1t03.mp3", track="1")]
    kept, _, ordering = filter_files(files)
    assert [f["name"] for f in kept] == ["gd73d1t03.mp3", "gd73d1t01.mp3", "gd73d1t02.mp3"]
    assert ordering == {"order_source": "track-tags", "reordered": True}


def test_track_tags_agreeing_with_filenames_not_flagged():
    files = [_mp3("gd73d1t01.mp3", track="1"), _mp3("gd73d1t02.mp3", track="2")]
    _, _, ordering = filter_files(files)
    assert ordering == {"order_source": "track-tags", "reordered": False}


def test_duplicate_track_tags_fall_back_to_filename_order():
    # per-disc numbering restarts at 1 -> ambiguous -> filename order
    files = [_mp3("gd73d1t01.mp3", track="1"), _mp3("gd73d2t01.mp3", track="1")]
    kept, _, ordering = filter_files(files)
    assert [f["name"] for f in kept] == ["gd73d1t01.mp3", "gd73d2t01.mp3"]
    assert ordering == {"order_source": "filename", "reordered": False}


def test_missing_track_tag_falls_back_to_filename_order():
    files = [_mp3("gd73d1t01.mp3", track="1"), _mp3("gd73d1t02.mp3")]
    _, _, ordering = filter_files(files)
    assert ordering["order_source"] == "filename"


def test_derivative_inherits_original_track_number():
    # originals are Shorten (not the wanted format) but carry the tags
    files = [
        {"name": "gd73d1t01.shn", "format": "Shorten", "source": "original", "track": "2"},
        {"name": "gd73d1t02.shn", "format": "Shorten", "source": "original", "track": "1"},
        _mp3("gd73d1t01.mp3", source="derivative", original="gd73d1t01.shn"),
        _mp3("gd73d1t02.mp3", source="derivative", original="gd73d1t02.shn"),
    ]
    kept, _, ordering = filter_files(files)
    assert [f["name"] for f in kept] == ["gd73d1t02.mp3", "gd73d1t01.mp3"]
    assert ordering == {"order_source": "track-tags", "reordered": True}
```

Also update the four existing `filter_files` unpackings in this file from
2-tuple to 3-tuple, e.g. `kept, _ = filter_files(load_files())` becomes
`kept, _, _ = filter_files(load_files())` (lines 14, 22, 29, 39).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_junk.py -q`
Expected: FAIL — `ValueError: not enough values to unpack` (or ordering
assertions failing)

- [ ] **Step 3: Implement in `src/llama/junk.py`**

Add near the top:

```python
import re

_LEADING_INT = re.compile(r"\s*(\d+)")
```

Add helper and rework the tail of `filter_files` (everything after the
`excluded.append(...)` / `kept.append(f)` loop):

```python
def _track_number(f: dict, orig_tracks: dict[str, object]) -> int | None:
    """Leading integer of the file's track tag ("5", "05", "5/16"). A
    derivative takes its original's tag - derivative entries often lack it."""
    raw = f.get("track") if f.get("source") == "original" else orig_tracks.get(f.get("original"))
    m = _LEADING_INT.match(str(raw)) if raw is not None else None
    return int(m.group(1)) if m else None
```

Replace the final `kept.sort(...)` / `return kept, excluded` with:

```python
    kept.sort(key=lambda f: f["name"])
    orig_tracks = {f["name"]: f.get("track") for f in files if f.get("source") == "original"}
    nums = [_track_number(f, orig_tracks) for f in kept]
    ordering = {"order_source": "filename", "reordered": False}
    # Track-tag order only when complete and unique: per-disc numbering
    # restarts at 1, which makes duplicates ambiguous.
    if kept and all(n is not None for n in nums) and len(set(nums)) == len(nums):
        by_track = [f for _, f in sorted(zip(nums, kept), key=lambda p: p[0])]
        ordering = {"order_source": "track-tags", "reordered": by_track != kept}
        kept = by_track
    return kept, excluded, ordering
```

Update the docstring's first line to mention the 3-tuple return.

- [ ] **Step 4: Update all call sites**

`src/llama/titles.py` — `resolve_titles`: replace
`files = sorted(kept_files, key=lambda f: f["name"])` with
`files = kept_files` and note in the docstring that callers pass files in
canonical play order (filter_files decides it).

`src/llama/stages/gather.py`:
- `_sibling_titles` line 37: `kept, _, _ = filter_files(...)`, and drop its
  internal re-sort: return `[f["title"] for f in kept]`.
- `run_gather` line 97: `kept, excluded, ordering = filter_files(...)`.
- The `Show(...)` construction gains `order_source=ordering["order_source"],
  reordered=ordering["reordered"],`.

`src/llama/models.py` — `Show` gains (after `excluded_files`):

```python
    order_source: str = "filename"  # "track-tags" | "filename" (canonical play order source)
    reordered: bool = False  # track tags disagreed with filename order
```

`src/llama/stages/select_recording.py` line 61:
`kept, _, _ = filter_files(files, want_format=want)`.

`tests/test_live_smoke.py` line 34:
`kept, excluded, _ = filter_files(md["files"])`.

- [ ] **Step 5: Run the offline suite**

Run: `pytest -q`
Expected: PASS (all; gd73 fixture files carry no conflicting track tags,
so fixture-based expectations are unchanged)

- [ ] **Step 6: Commit**

```bash
git add src/llama/junk.py src/llama/titles.py src/llama/models.py \
  src/llama/stages/gather.py src/llama/stages/select_recording.py \
  tests/test_junk.py tests/test_live_smoke.py
git commit -m "feat: canonical track order from track tags in filter_files"
```

---

### Task 3: Sibling-title cleanup in gather

**Files:**
- Modify: `src/llama/stages/gather.py`
- Test: `tests/test_stage_gather.py`

**Interfaces:**
- Consumes: `clean_tag_title`, `is_real_title` from `llama.titles` (Task 1);
  3-tuple `filter_files` (Task 2).
- Produces: `_sibling_titles` returns CLEANED titles and accepts a sibling
  only when every cleaned title is real; `run_gather`'s sibling-fallback
  trigger uses the same test.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_stage_gather.py`. It reuses `MultiIA` and the gd73
fixture; the chosen recording has NO tag titles and an EMPTY description
(empty on both recordings, so no setlist parse and no LLM-extraction
fallback fires — the canonical setlist stays empty/low-confidence, which
is what routes titling to the sibling cascade); the sibling has prefixed
tags:

```python
def test_sibling_titles_are_cleaned(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    titles = ["Morning Dew", "China Cat Sunflower", "I Know You Rider",
              "Dark Star", "Eyes of the World", "Johnny B. Goode"]
    chosen = {"metadata": dict(md["metadata"], description=""),
              "files": [dict(f) for f in md["files"]]}
    for f in chosen["files"]:
        f.pop("title", None)
    sib = {"metadata": dict(md["metadata"], description=""),
           "files": [dict(f) for f in md["files"]]}
    sib_audio = [f for f in sib["files"] if f.get("format") == "VBR MP3"]
    for f, title in zip(sorted(sib_audio, key=lambda f: f["name"]), titles):
        f["title"] = f"gd73-06-10d1t01 {title}"  # id-prefixed tag
    ia = MultiIA({IDENT: chosen, "gd73-06-10.aud.sibling": sib})
    cand = make_candidate()
    cand.recordings.append(RecordingSummary(identifier="gd73-06-10.aud.sibling"))
    show = run_gather(ShowWorkspace(tmp_path / "show"), ia, FakeProvider(), cand, IDENT)
    assert [t.title for t in show.tracks] == titles          # prefix stripped
    assert all(t.title_source == "sibling" for t in show.tracks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stage_gather.py::test_sibling_titles_are_cleaned -q`
Expected: FAIL — titles come back with the `gd73-06-10d1t01 ` prefix
(assert on `titles` list mismatches)

- [ ] **Step 3: Implement in `src/llama/stages/gather.py`**

Add to imports: `from llama.titles import clean_tag_title, is_real_title, resolve_titles, set_breaks`
(extending the existing `from llama.titles import ...` line).

Rewrite `_sibling_titles`'s acceptance/return (inside the loop):

```python
        kept, _, _ = filter_files(ia.metadata(rec.identifier).get("files", []), want_format=want)
        titles = [clean_tag_title(f.get("title")) for f in kept]
        if len(kept) == n and all(is_real_title(t) for t in titles):
            return titles
```

In `run_gather`, the sibling-fallback trigger (line ~123) becomes:

```python
    if any(not is_real_title(clean_tag_title(f.get("title"))) for f in kept) and (
        canonical.confidence == "low" or len(canonical.items) != len(kept)
    ):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stage_gather.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/stages/gather.py tests/test_stage_gather.py
git commit -m "feat: clean sibling tag titles and gate on real titles in gather"
```

---

### Task 4: Downloads field plumbing (search → model → grouping)

**Files:**
- Modify: `src/llama/stages/search.py`, `src/llama/models.py`,
  `src/llama/grouping.py`
- Test: `tests/test_grouping.py`, `tests/test_stage_search.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `RecordingSummary.downloads: int = 0`, populated by
  `group_candidates` from search docs. Task 6 reads `rec.downloads`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_grouping.py` (match its existing import style):

```python
def test_downloads_mapped_and_defaulted():
    docs = [
        {"identifier": "gd73-a", "date": "1973-06-10", "downloads": [1500]},
        {"identifier": "gd73-b", "date": "1973-06-10"},
    ]
    cands = group_candidates("GratefulDead", docs)
    recs = {r.identifier: r for r in cands[0].recordings}
    assert recs["gd73-a"].downloads == 1500
    assert recs["gd73-b"].downloads == 0
```

Append to `tests/test_stage_search.py`:

```python
def test_search_requests_downloads_field():
    from llama.stages.search import SEARCH_FIELDS
    assert "downloads" in SEARCH_FIELDS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_grouping.py tests/test_stage_search.py -q`
Expected: FAIL — downloads assertions (field missing / not requested)

- [ ] **Step 3: Implement**

`src/llama/stages/search.py` — `SEARCH_FIELDS` becomes:

```python
SEARCH_FIELDS = [
    "identifier", "title", "date", "venue", "coverage",
    "avg_rating", "num_reviews", "downloads", "description",
]
```

`src/llama/models.py` — `RecordingSummary` gains (after `num_reviews`):

```python
    downloads: int = 0
```

`src/llama/grouping.py` — in the `RecordingSummary(...)` construction,
after the `num_reviews=` line:

```python
            downloads=int(_first(doc.get("downloads")) or 0),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_grouping.py tests/test_stage_search.py tests/test_models.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/stages/search.py src/llama/models.py src/llama/grouping.py \
  tests/test_grouping.py tests/test_stage_search.py
git commit -m "feat: carry archive.org downloads through search into RecordingSummary"
```

---

### Task 5: Scoring terms (downloads_norm, title_fraction)

**Files:**
- Modify: `src/llama/scoring.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: nothing (pure function change).
- Produces: `score_recording(..., downloads_norm: float = 0.0,
  title_fraction: float = 0.0, ...)` plus module constants
  `DOWNLOADS_WEIGHT = 0.75`, `TITLE_WEIGHT = 0.5`. Task 6 passes both
  keyword arguments.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scoring.py`:

```python
def test_downloads_and_title_terms_are_additive_and_bounded():
    kw = dict(lineage="matrix", avg_rating=4.0, num_reviews=10,
              has_wanted_format=True, completeness=1.0, complaints=0)
    base = score_recording(**kw)
    assert score_recording(downloads_norm=1.0, **kw) == round(base + 0.75, 3)
    assert score_recording(title_fraction=1.0, **kw) == round(base + 0.5, 3)
    # defaults preserve old behavior
    assert score_recording(downloads_norm=0.0, title_fraction=0.0, **kw) == base


def test_new_terms_cannot_flip_sbd_vs_aud():
    kw = dict(avg_rating=4.5, num_reviews=20, has_wanted_format=True,
              completeness=1.0, complaints=0)
    maxed_aud = score_recording(lineage="aud", downloads_norm=1.0,
                                title_fraction=1.0, **kw)
    bare_sbd = score_recording(lineage="sbd", **kw)
    assert bare_sbd > maxed_aud


def test_new_terms_scale_with_completeness():
    kw = dict(lineage="sbd", avg_rating=None, num_reviews=0,
              has_wanted_format=False, complaints=0)
    full = score_recording(completeness=1.0, downloads_norm=1.0, **kw)
    half = score_recording(completeness=0.0, downloads_norm=1.0, **kw)
    # at completeness 0 the whole score (incl. the new term) is halved
    assert half == round(full / 2, 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scoring.py -q`
Expected: FAIL — `TypeError: score_recording() got an unexpected keyword
argument 'downloads_norm'`

- [ ] **Step 3: Implement in `src/llama/scoring.py`**

After `LINEAGE_SCORES`, add:

```python
# Bounded additive terms (spec 2026-07-19-deadstream-lessons): both at
# most format-bonus scale so they decide same-lineage ties but can never
# flip sbd-vs-aud (lineage gap >= 2.0).
DOWNLOADS_WEIGHT = 0.75  # x sibling-relative log1p(downloads) in [0, 1]
TITLE_WEIGHT = 0.5  # x fraction of kept files with a real embedded title
```

`score_recording` gains two keyword params (after `taper_bonus`):

```python
    downloads_norm: float = 0.0,
    title_fraction: float = 0.0,
```

and, after the `score += taper_bonus` line:

```python
    score += DOWNLOADS_WEIGHT * downloads_norm
    score += TITLE_WEIGHT * title_fraction
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scoring.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/llama/scoring.py tests/test_scoring.py
git commit -m "feat: downloads and title-fraction terms in recording score"
```

---

### Task 6: Wire the signals into select-recording

**Files:**
- Modify: `src/llama/stages/select_recording.py`, `docs/workflow.md:138`
- Test: `tests/test_stage_select.py`

**Interfaces:**
- Consumes: `rec.downloads` (Task 4), `score_recording(downloads_norm=,
  title_fraction=)` (Task 5), `clean_tag_title`/`is_real_title` (Task 1),
  3-tuple `filter_files` (Task 2 — call site already updated there).
- Produces: `selection.json` per-recording entries gain `downloads_norm`
  and `title_fraction` (both rounded to 3 places).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stage_select.py` (uses the module's existing `mp3`
helper, `ShowWorkspace`, `QualityAssessment` imports):

```python
class TitledIA:
    """Two same-lineage siblings; only .titled has real embedded titles."""

    def __init__(self):
        titled = [dict(mp3("gd73x-t01.mp3"), title="Morning Dew"),
                  dict(mp3("gd73x-t02.mp3"), title="Dark Star")]
        bare = [mp3("gd73y-t01.mp3"), mp3("gd73y-t02.mp3")]
        self.md = {"gd73.aud.titled": {"metadata": {"source": "AUD"}, "files": titled},
                   "gd73.aud.bare": {"metadata": {"source": "AUD"}, "files": bare}}

    def metadata(self, identifier):
        return self.md[identifier]


def _pair_candidate(a, b, downloads=(0, 0)):
    return Candidate(
        performance_id="GratefulDead/1973-06-10", collection="GratefulDead",
        date="1973-06-10",
        recordings=[RecordingSummary(identifier=a, downloads=downloads[0]),
                    RecordingSummary(identifier=b, downloads=downloads[1])],
    )


def test_title_fraction_breaks_same_lineage_tie(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "show")
    cand = _pair_candidate("gd73.aud.bare", "gd73.aud.titled")
    chosen = run_select_recording(sws, TitledIA(), cand, assessment(reviewed=""))
    assert chosen == "gd73.aud.titled"
    sel = json.loads(sws.selection.read_text())
    assert sel["scores"]["gd73.aud.titled"]["title_fraction"] == 1.0
    assert sel["scores"]["gd73.aud.bare"]["title_fraction"] == 0.0


def test_downloads_break_same_lineage_tie(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "show")
    cand = _pair_candidate("gd73.aud.bare", "gd73.aud.titled", downloads=(120000, 0))
    # bare has the crowd behind it; titled has tags. 0.75 > 0.5 -> bare wins.
    chosen = run_select_recording(sws, TitledIA(), cand, assessment(reviewed=""))
    assert chosen == "gd73.aud.bare"
    sel = json.loads(sws.selection.read_text())
    assert sel["scores"]["gd73.aud.bare"]["downloads_norm"] == 1.0
    assert sel["scores"]["gd73.aud.titled"]["downloads_norm"] == 0.0


def test_zero_downloads_everywhere_is_neutral(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "show")
    cand = _pair_candidate("gd73.aud.bare", "gd73.aud.titled")
    run_select_recording(sws, TitledIA(), cand, assessment(reviewed=""))
    sel = json.loads(sws.selection.read_text())
    assert all(v["downloads_norm"] == 0.0 for v in sel["scores"].values())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_select.py -q`
Expected: FAIL — `KeyError: 'title_fraction'` (artifact lacks the fields)

- [ ] **Step 3: Implement in `src/llama/stages/select_recording.py`**

Add imports:

```python
import math

from llama.titles import clean_tag_title, is_real_title
```

In the `prepared.append({...})` loop, after computing `kept`, add a
`title_fraction` entry (and keep the existing keys):

```python
        prepared.append({
            "rec": rec,
            "lineage": lineage_class(rec.identifier, meta),
            "has_format": bool(kept),
            "kept_tracks": len(kept),
            "title_fraction": (
                sum(1 for f in kept if is_real_title(clean_tag_title(f.get("title")))) / len(kept)
            ) if kept else 0.0,
            "addeddate": str(meta.get("addeddate") or ""),
            "complaints": len(assessment.recording_complaints)
            if rec.identifier == assessment.reviewed_identifier else 0,
        })
```

Before the scoring loop, compute the sibling-relative normalizer:

```python
    max_log_downloads = max((math.log1p(p["rec"].downloads) for p in prepared), default=0.0)
```

In the scoring loop, per recording:

```python
        downloads_norm = (
            math.log1p(p["rec"].downloads) / max_log_downloads if max_log_downloads else 0.0
        )
        scores[p["rec"].identifier] = {
            "score": score_recording(
                lineage=p["lineage"],
                avg_rating=p["rec"].avg_rating,
                num_reviews=p["rec"].num_reviews,
                has_wanted_format=p["has_format"],
                completeness=p["kept_tracks"] / max_kept,
                complaints=p["complaints"],
                taper_bonus=bonuses[p["rec"].identifier],
                downloads_norm=downloads_norm,
                title_fraction=p["title_fraction"],
                lineage_scores=era_scores,
            ),
            "lineage": p["lineage"],
            "kept_tracks": p["kept_tracks"],
            "downloads_norm": round(downloads_norm, 3),
            "title_fraction": round(p["title_fraction"], 3),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stage_select.py tests/test_pipeline.py -q`
Expected: PASS

- [ ] **Step 5: Update the docs row**

`docs/workflow.md` line 138, extend the select-recording description: after
"`[selection.tapers]` reputation bonuses (miller/seamons for GD; newest
revision of a taper preferred)" append
", sibling-relative download popularity, and embedded-title coverage
(both small tie-breaker-sized terms)".

- [ ] **Step 6: Commit**

```bash
git add src/llama/stages/select_recording.py tests/test_stage_select.py docs/workflow.md
git commit -m "feat: select recordings with downloads and title-coverage signals"
```

---

### Task 7: Integration test + full-suite sweep

**Files:**
- Test: `tests/test_stage_gather.py`

**Interfaces:**
- Consumes: everything above; adds no new interfaces.

- [ ] **Step 1: Write the integration test**

Append to `tests/test_stage_gather.py` — a chosen recording whose tag
titles are id-prefixed must produce clean titles, "tags" sourcing, and
successful alignment (no structure flags):

```python
def test_prefixed_tag_titles_align(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    md = {"metadata": dict(md["metadata"]), "files": [dict(f) for f in md["files"]]}
    for f in md["files"]:
        if f.get("title"):
            f["title"] = f"gd73-06-10d1t01 {f['title']}"
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    tagged = [t for t in show.tracks if t.title_source == "tags"]
    assert tagged and all(not t.title.startswith("gd73") for t in tagged)
    assert "low-confidence structure alignment" not in show.review_flags
    assert show.order_source in ("track-tags", "filename")  # recorded on the artifact
```

- [ ] **Step 2: Run the new test**

Run: `pytest tests/test_stage_gather.py::test_prefixed_tag_titles_align -q`
Expected: PASS (the feature is already built; if this fails, the cleanup
or ordering wiring is wrong — fix before proceeding)

- [ ] **Step 3: Run the full offline suite**

Run: `pytest -q`
Expected: PASS, ~430+ tests, no skips beyond the usual live markers

- [ ] **Step 4: Commit**

```bash
git add tests/test_stage_gather.py
git commit -m "test: end-to-end coverage for prefixed tag titles and order artifact"
```
