# Tier-A Title Defects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop llama shipping track-number-prefixed and missing track titles to
emcee's scriptwriter, by gating the number-strip on the recording and by
recovering titles from an item's lossless sibling files.

**Architecture:** Three changes in the title-resolution path.
(1) A new list-level `clean_tag_titles` decides whether a recording is an
*enumerated tape* and strips leading track numbers only then — a decision that
cannot be made from a single string. (2) `filter_files` gains ordered
format preference so `24bit Flac` stops being invisible. (3) `gather` recovers
titles from a different-format copy of the same archive.org item, matched by
filename stem, when the delivered format's tags are missing.

**Tech Stack:** Python 3.12+, pydantic v2, pytest. No new dependencies — all
titles come from archive.org's cached metadata response, so nothing is
downloaded and no tag library is involved.

**Spec:** `docs/superpowers/specs/2026-08-04-tier-a-title-defects-design.md`

## Global Constraints

- **Offline and deterministic.** Every test added here runs under plain
  `pytest -q` with no network. Titles come from cached metadata dicts.
- **No new dependencies.** `mutagen` exists but is write-only (`audio.py`);
  do not use it here.
- **The `\d{1,3}` bound is load-bearing.** Never widen the track-number regex
  to `\d+`: the bound is what puts `1952 Vincent Black Lightning` and a bare
  `2001` out of the rule's reach. Any change to it invalidates the spec's
  measurements.
- **Format matching is preference-ordered, never a union.** 5 corpus items
  carry both `Flac` and `24bit Flac`; a union keeps every track of those items
  twice.
- **Cite code by symbol, never by line number** in comments and commit
  messages — this repo has been bitten by line references going stale inside
  a single fix wave.
- **In a git worktree, give the worktree its own `.venv` and run
  `./.venv/bin/pytest`.** The repo-root `.venv` installs llama editable
  against the *main* checkout, so a bare `pytest` from a worktree collects the
  worktree's tests but imports the main checkout's source — it silently tests
  the wrong code and still passes.
- Baseline before starting: `pytest -q` is green at 1338 tests on `main`.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `packages/llama/src/llama/titles.py` | Title cleaning, the enumerated-tape gate, `title_fraction`, stem-matched format recovery, the resolve cascade | 1, 2, 4, 5 |
| `packages/llama/src/llama/junk.py` | File filtering and format preference | 3 |
| `packages/llama/src/llama/stages/gather.py` | Wiring: recovery trigger, cascade call | 2, 5 |
| `packages/llama/src/llama/stages/select_recording.py` | Wiring: `title_fraction` reuse | 2 |
| `packages/llama/src/llama/models.py` | `Track.title_source` doc comment | 5 |
| `packages/llama/tests/test_titles.py` | Tests for tasks 1, 4, 5 | 1, 4, 5 |
| `packages/llama/tests/test_junk.py` | Tests for task 3 | 3 |
| `packages/llama/tests/test_stage_gather.py` | Wiring tests | 2, 5 |

---

### Task 1: The enumerated-tape gate

Adds two pure functions to `titles.py`. Nothing calls them yet — Task 2 wires
them in. Splitting the two lets a reviewer judge the classifier on its own
merits before any behaviour changes.

**Files:**
- Modify: `packages/llama/src/llama/titles.py` (add after `is_real_title`)
- Test: `packages/llama/tests/test_titles.py`

**Interfaces:**
- Consumes: `clean_tag_title(raw)`, `is_real_title(cleaned)` — both already in
  `titles.py`, unchanged.
- Produces:
  - `clean_tag_titles(kept_files: list[dict]) -> list[str]`
  - `title_fraction(titles: list[str]) -> float`

- [ ] **Step 1: Write the failing tests**

Add to `packages/llama/tests/test_titles.py`. Note the import line at the top
of that file must grow to include the two new names.

```python
from llama.titles import (
    clean_tag_title, clean_tag_titles, is_real_title, resolve_titles,
    set_breaks, title_fraction,
)


def numbered_files(titles: list[str]) -> list[dict]:
    """Kept-file dicts carrying only what the title path reads."""
    return [{"name": f"t{n:02d}.mp3", "title": t} for n, t in enumerate(titles, 1)]


def test_clean_tag_titles_strips_numbers_on_an_enumerated_tape():
    # gus2018-01-13's real shape: every track numbered, 1..n.
    files = numbered_files([
        "01 Intro - Ramona", "02 Two Points For Honesty", "03 Banter - Sports Talk",
        "04 G Major", "05 Demons",
    ])
    assert clean_tag_titles(files) == [
        "Intro - Ramona", "Two Points For Honesty", "Banter - Sports Talk",
        "G Major", "Demons",
    ]


def test_clean_tag_titles_protects_a_lone_numeric_title():
    # bt1990-08-17: "100 Years" is the only numbered title among 4 tracks.
    files = numbered_files(["The Way It Is", "100 Years", "Mandolin Rain", "Every Little Kiss"])
    assert clean_tag_titles(files) == [
        "The Way It Is", "100 Years", "Mandolin Rain", "Every Little Kiss",
    ]


@pytest.mark.parametrize("title", [
    "100 Years", "200 More Miles", "20 Eyes", "2 x 4",
    "52 Vincent Black Lightning", "40 Miles From Denver", "18 Wheels Of Love",
])
def test_clean_tag_titles_never_mutilates_a_real_numeric_title(title):
    """Every one of these is a real song title measured in the live corpus,
    sitting alone among unnumbered tracks. See the spec's A1 evidence."""
    files = numbered_files(["Opener", title, "Closer"])
    assert clean_tag_titles(files)[1] == title


def test_clean_tag_titles_leaves_a_four_digit_year_alone_even_when_enumerated():
    """The \\d{1,3} bound, not the gate, is what protects this one - so it must
    hold even on a tape the gate is actively stripping."""
    files = numbered_files([
        "01 Opener", "02 1952 Vincent Black Lightning", "03 Third", "04 Fourth",
    ])
    assert clean_tag_titles(files)[1] == "1952 Vincent Black Lightning"


def test_clean_tag_titles_strips_once_never_loops():
    """On an enumerated tape a title may legitimately begin with its own
    number. A looping strip would take this to "More Miles"."""
    files = numbered_files(["01 200 More Miles", "02 Second", "03 Third", "04 Fourth"])
    assert clean_tag_titles(files)[0] == "200 More Miles"


def test_clean_tag_titles_declines_below_the_count_floor():
    """Two numbered files out of ten is not an enumerated tape - dbt2014-01-31
    is exactly this shape, and both its numbers are song titles."""
    files = numbered_files(
        ["18 Wheels Of Love", "3 Dimes Down"] + [f"Song {n}" for n in range(8)]
    )
    assert clean_tag_titles(files)[:2] == ["18 Wheels Of Love", "3 Dimes Down"]


def test_clean_tag_titles_declines_below_the_coverage_floor():
    """dbt2017-09-30: three numbered titles, but only 3 of 30 files - well
    under 80%, so all three are real titles, not enumeration."""
    files = numbered_files(
        ["72 (This Highway's Mean)", "3 Dimes Down", "18 Wheels of Love"]
        + [f"Song {n}" for n in range(27)]
    )
    assert clean_tag_titles(files)[:3] == [
        "72 (This Highway's Mean)", "3 Dimes Down", "18 Wheels of Love",
    ]


def test_clean_tag_titles_accepts_its_known_false_negatives():
    """Fishbone1992-09-18's shape: disc 2 numbered 8..16, 9 of 15 files = 0.60
    coverage. These ARE track numbers and the gate deliberately misses them -
    the prefix survives, which is the pre-existing behaviour.

    Pinned so that widening the gate is a visible, deliberate change rather
    than a silent one. If this test starts failing, someone loosened a floor;
    that may be right, but it must be argued from a re-measurement."""
    files = numbered_files(
        [f"Song {n}" for n in range(6)]
        + [f"{n:02d} Numbered {n}" for n in range(8, 17)]
    )
    assert clean_tag_titles(files)[6] == "08 Numbered 8"


def test_clean_tag_titles_still_strips_the_identifier_prefix():
    """The per-string cleaner must keep working through the list wrapper."""
    files = [{"name": "d1t04.mp3", "title": "gd73-06-10d1t04 Here Comes Sunshine"}]
    assert clean_tag_titles(files) == ["Here Comes Sunshine"]


def test_clean_tag_titles_handles_empty_input():
    assert clean_tag_titles([]) == []


def test_title_fraction():
    assert title_fraction(["Dark Star", "Eyes of the World"]) == 1.0
    assert title_fraction(["Dark Star", "", "d1t02", "Eyes"]) == 0.5
    assert title_fraction([]) == 0.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest packages/llama/tests/test_titles.py -q -k "clean_tag_titles or title_fraction"`

Expected: collection error — `ImportError: cannot import name 'clean_tag_titles' from 'llama.titles'`.

- [ ] **Step 3: Implement**

In `packages/llama/src/llama/titles.py`, directly below `is_real_title`:

```python
# A leading track number on an enumerated tape: 1-3 digits, an optional single
# separator, then whitespace and a non-space character.
#
# The 1-3 digit bound with (?!\d) is LOAD-BEARING and must not be widened to
# \d+: it is what puts "1952 Vincent Black Lightning" and a bare "2001" out of
# this rule's reach entirely, without the gate below having to save them.
_TRACK_NUM_PREFIX = re.compile(r"^\d{1,3}(?!\d)[.)\-:]?\s+(?=\S)")

# Whether a leading number is a track number or part of the title cannot be
# decided from one string - "01 Intro - Ramona" and "100 Years" are identical
# in isolation. It is decided by the RECORDING: an enumerated tape numbers
# essentially every track, while a real numeric title is one lone numbered
# file among unnumbered ones.
#
# Measured over 2,095 cached archive.org items (see the spec's A1 evidence):
# this gate strips 94 of the 96 genuinely enumerated tapes, and mutilates NONE
# of the 105 items carrying a real numeric title. The two it misses keep their
# prefixes, which is today's behaviour - a false negative, never a destroyed
# title. Both floors are required; dropping either one breaks a pinned test.
_ENUMERATED_MIN_FILES = 3
_ENUMERATED_MIN_COVERAGE = 0.8


def title_fraction(titles: list[str]) -> float:
    """Fraction of cleaned titles that are usable. 0.0 for no titles."""
    return sum(1 for t in titles if is_real_title(t)) / len(titles) if titles else 0.0


def clean_tag_titles(kept_files: list[dict]) -> list[str]:
    """Cleaned embedded-tag titles for one recording's kept files, in play
    order. Wraps clean_tag_title with the one decision that needs the whole
    recording: whether to strip leading track numbers."""
    titles = [clean_tag_title(f.get("title")) for f in kept_files]
    numbered = sum(1 for t in titles if _TRACK_NUM_PREFIX.match(t))
    if numbered < _ENUMERATED_MIN_FILES or numbered < _ENUMERATED_MIN_COVERAGE * len(titles):
        return titles
    # Strip exactly one number, never loop: on an enumerated tape
    # "01 200 More Miles" must lose only the "01".
    return [_TRACK_NUM_PREFIX.sub("", t, count=1) for t in titles]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest packages/llama/tests/test_titles.py -q`
Expected: all pass, including the pre-existing tests in that file.

- [ ] **Step 5: Prove the floors are load-bearing**

Not a test — a manual mutation check, because a comment claiming "test X pins
this" must ship with executed evidence. Temporarily set
`_ENUMERATED_MIN_COVERAGE = 0.0`, run the file, confirm
`test_clean_tag_titles_declines_below_the_coverage_floor` FAILS. Then restore
it, set `_ENUMERATED_MIN_FILES = 0`, confirm
`test_clean_tag_titles_declines_below_the_count_floor` FAILS. Restore both and
re-run to green.

If either mutation does *not* fail its test, the test is not pinning what its
name claims — fix the test before continuing.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/titles.py packages/llama/tests/test_titles.py
git commit -m "feat(titles): enumerated-tape gate for leading track numbers

Adds clean_tag_titles and title_fraction. Nothing calls them yet.

A leading number is a track number or part of the title depending on the
RECORDING, not the string: an enumerated tape numbers nearly every track,
a real numeric title is one lone numbered file. Gate is >=3 numbered files
and >=80% coverage; measured over 2,095 cached IA items it strips 94 of 96
enumerated tapes and mutilates none of the 105 real-title items."
```

---

### Task 2: Wire the gate into the four call sites

Behaviour changes here, not in Task 1. `select_recording` also stops
duplicating the `title_fraction` computation.

**Files:**
- Modify: `packages/llama/src/llama/titles.py` (`resolve_titles`)
- Modify: `packages/llama/src/llama/stages/gather.py` (`_sibling_titles`, and
  the sibling-recording gate in `run_gather`)
- Modify: `packages/llama/src/llama/stages/select_recording.py`
  (`title_fraction` in the `prepared` dict)
- Test: `packages/llama/tests/test_stage_gather.py`

**Interfaces:**
- Consumes: `clean_tag_titles`, `title_fraction` from Task 1.
- Produces: no new symbols. `resolve_titles`' signature is unchanged in this
  task; Task 5 extends it.

- [ ] **Step 1: Write the failing test**

Add to `packages/llama/tests/test_stage_gather.py`, in that file's existing
idiom — mutate a copy of the `gd73_metadata.json` fixture and feed it through
`StubIA`, exactly as the neighbouring `test_prefixed_tag_titles_align` does.
`json`, `Path`, `StubIA`, `FIXTURE`, `IDENT`, `make_candidate`,
`ShowWorkspace` and `FakeProvider` are all already imported there.

```python
def _enumerate_tag_titles(md: dict) -> dict:
    """Rewrite every tagged file's title as a numbered tracklist - the shape of
    gus2018-01-13, where all 26 files are numbered 1..26."""
    md = {"metadata": dict(md["metadata"]), "files": [dict(f) for f in md["files"]]}
    n = 0
    for f in md["files"]:
        if f.get("title"):
            n += 1
            f["title"] = f"{n:02d} {f['title']}"
    return md


def test_gather_strips_track_numbers_on_an_enumerated_tape(tmp_path: Path):
    """An enumerated tape's numbers must not reach the manifest - emcee's
    scriptwriter reads the title verbatim."""
    md = _enumerate_tag_titles(json.loads(FIXTURE.read_text()))
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    tagged = [t for t in show.tracks if t.title_source == "tags"]
    assert tagged
    assert all(not t.title[0].isdigit() for t in tagged)


def test_gather_keeps_a_lone_numeric_title(tmp_path: Path):
    """One numbered title among unnumbered ones is a song, not enumeration.
    This should already pass before Task 2 - it is a regression guard."""
    md = json.loads(FIXTURE.read_text())
    md = {"metadata": dict(md["metadata"]), "files": [dict(f) for f in md["files"]]}
    tagged = [f for f in md["files"] if f.get("title")]
    tagged[1]["title"] = "100 Years"
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert "100 Years" in [t.title for t in show.tracks]
```

**Do not disturb `test_sibling_titles_are_cleaned` or
`test_prefixed_tag_titles_align`.** Both concern the *identifier* prefix
(`gd73-06-10d1t01 `), which `clean_tag_title` still strips underneath the new
wrapper — they must stay green untouched, and are a useful check that the
wrapper did not swallow the per-string cleaner.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest packages/llama/tests/test_stage_gather.py -q -k "enumerated or lone_numeric"`
Expected: `test_gather_strips_track_numbers_on_an_enumerated_tape` FAILS with
titles still carrying `01 `/`02 ` prefixes. The lone-numeric test should
already PASS — it is a regression guard, not a new behaviour.

- [ ] **Step 3: Implement the four call sites**

In `titles.py`, inside `resolve_titles`, replace the per-file
`clean_tag_title` call with a list computed once before the loop:

```python
    tag_titles = clean_tag_titles(files)

    tracks: list[Track] = []
    for pos, f in enumerate(files):
        tag_title = tag_titles[pos]
        if is_real_title(tag_title):
            title, source = tag_title, "tags"
```

(the rest of the loop body is unchanged)

In `gather.py`, in `_sibling_titles`:

```python
        titles = clean_tag_titles(kept)
```

In `gather.py`, the sibling-recording gate in `run_gather` — replace the
`any(not is_real_title(clean_tag_title(...)))` generator with:

```python
    if title_fraction(clean_tag_titles(kept)) < 1.0 and (
        canonical.confidence == "low" or len(canonical.items) != len(kept)
    ):
```

In `select_recording.py`, in the `prepared` dict:

```python
            "title_fraction": title_fraction(clean_tag_titles(kept)),
```

Update the imports in all three modules: `gather.py` and
`select_recording.py` import `clean_tag_titles` and `title_fraction`;
`clean_tag_title` stays imported only where still used.

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all pass. Watch specifically for pre-existing `select_recording`
tests — `title_fraction` there is now computed over gated titles, which
changes nothing for un-numbered fixtures but would surface any fixture that
relied on a numbered title scoring as unresolved.

**If a pre-existing test's expectation changed, do not edit it to match.**
Adjudicate against that fixture's documented intent first: an edited
expectation on a pre-existing test is the canonical shape of a papered-over
regression. Report it rather than silently updating it.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/titles.py packages/llama/src/llama/stages/gather.py \
        packages/llama/src/llama/stages/select_recording.py packages/llama/tests/test_stage_gather.py
git commit -m "fix(titles): gate track-number stripping at all four call sites

resolve_titles, gather's sibling-title probe and review gate, and
select_recording's title_fraction all now go through clean_tag_titles, so an
enumerated tape's numbers stop reaching the manifest and the DJ.

select_recording drops its inlined title-fraction computation in favour of
titles.title_fraction - same quantity, one definition."
```

---

### Task 3: Ordered format preference

Independent of tasks 1–2; can be reviewed and landed on its own. Fixes a live
defect (`audio_format = "flac"` currently yields zero files on a 24-bit-only
item) and is a prerequisite for Task 5.

**Files:**
- Modify: `packages/llama/src/llama/junk.py`
- Test: `packages/llama/tests/test_junk.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `FORMAT_BY_AUDIO: dict[str, tuple[str, ...]]` — values are now tuples
  - `LOSSLESS_TITLE_FORMATS: tuple[str, ...]`
  - `filter_files(files, want_format: str | Sequence[str] = "VBR MP3")` — a
    bare `str` still works
  - `ordering` gains a `"format"` key naming the format actually matched
    (`""` when nothing matched)

- [ ] **Step 1: Write the failing tests**

Add to `packages/llama/tests/test_junk.py`:

```python
def audio(name: str, fmt: str, length: str = "05:00") -> dict:
    return {"name": name, "format": fmt, "source": "original", "length": length}


def test_filter_files_falls_back_to_24bit_flac():
    """A 24-bit-only item must not read as 'no lossless available'."""
    files = [audio("t01.flac", "24bit Flac"), audio("t02.flac", "24bit Flac")]
    kept, _, ordering = filter_files(files, want_format=FORMAT_BY_AUDIO["flac"])
    assert [f["name"] for f in kept] == ["t01.flac", "t02.flac"]
    assert ordering["format"] == "24bit Flac"


def test_filter_files_prefers_plain_flac_and_never_unions():
    """5 corpus items carry both Flac and 24bit Flac. A union would keep every
    track of those items twice."""
    files = [
        audio("t01.flac", "Flac"), audio("t02.flac", "Flac"),
        audio("t01.24.flac", "24bit Flac"), audio("t02.24.flac", "24bit Flac"),
    ]
    kept, _, ordering = filter_files(files, want_format=FORMAT_BY_AUDIO["flac"])
    assert [f["name"] for f in kept] == ["t01.flac", "t02.flac"]
    assert ordering["format"] == "Flac"


def test_filter_files_still_accepts_a_bare_format_string():
    files = [audio("t01.mp3", "VBR MP3")]
    kept, _, ordering = filter_files(files, want_format="VBR MP3")
    assert len(kept) == 1
    assert ordering["format"] == "VBR MP3"


def test_filter_files_reports_no_format_when_nothing_matches():
    kept, _, ordering = filter_files([audio("t01.ogg", "Ogg Vorbis")],
                                     want_format=FORMAT_BY_AUDIO["flac"])
    assert kept == []
    assert ordering["format"] == ""


def test_lossless_title_formats_is_broader_than_the_delivery_formats():
    """Shorten is a title-reading source only - recovery never downloads it,
    and adding it to delivery would change what llama ships."""
    assert "Shorten" in LOSSLESS_TITLE_FORMATS
    assert "Shorten" not in FORMAT_BY_AUDIO["flac"]
```

Import `FORMAT_BY_AUDIO` and `LOSSLESS_TITLE_FORMATS` at the top of the file
alongside the existing `filter_files` import.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest packages/llama/tests/test_junk.py -q`
Expected: `ImportError` on `LOSSLESS_TITLE_FORMATS`; the fallback and
`ordering["format"]` tests fail once that is stubbed.

- [ ] **Step 3: Implement**

In `junk.py`, replace the `FORMAT_BY_AUDIO` line:

```python
# Delivery formats, in preference order. archive.org tags lossless files
# either "Flac" or "24bit Flac"; matching only the first made every 24-bit
# item look like it had no lossless copy at all, so audio_format="flac"
# yielded zero kept files and the recording became unselectable.
FORMAT_BY_AUDIO = {"mp3": ("VBR MP3",), "flac": ("Flac", "24bit Flac")}

# Lossless formats worth READING titles from. Deliberately broader than the
# delivery formats: title recovery reads metadata strings and never downloads
# these files, so Shorten is safe here - and deliberately absent above, since
# adding it would change what llama ships.
LOSSLESS_TITLE_FORMATS = ("Flac", "24bit Flac", "Shorten")
```

Change `filter_files`' signature and its format selection:

```python
def filter_files(
    files: list[dict], want_format: str | Sequence[str] = "VBR MP3"
) -> tuple[list[dict], list[dict], dict]:
    """Returns (kept, excluded, ordering) with kept in canonical play order.

    `want_format` may be one format or an ordered preference list. A list is
    tried in order and the FIRST one present wins - never a union, because an
    item carrying both Flac and 24bit Flac would otherwise keep every track
    twice."""
    wanted = (want_format,) if isinstance(want_format, str) else tuple(want_format)
    audio: list[dict] = []
    matched = ""
    for fmt in wanted:
        audio = [f for f in files if f.get("format") == fmt]
        if audio:
            matched = fmt
            break
```

Add `from collections.abc import Sequence` to the imports. Then thread
`matched` into both `ordering` assignments:

```python
    ordering = {"order_source": "filename", "reordered": False, "format": matched}
```
```python
        ordering = {"order_source": "track-tags", "reordered": by_track != kept,
                    "format": matched}
```

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: all pass. `FORMAT_BY_AUDIO[...]` is now a tuple everywhere it is
read (`gather.py`, `select_recording.py`) and both pass it straight to
`filter_files`, so no other call site needs changing — confirm by grepping:

```bash
grep -rn "FORMAT_BY_AUDIO" packages/llama/src packages/llama/tests
```

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/junk.py packages/llama/tests/test_junk.py
git commit -m "fix(junk): ordered format preference; 24bit Flac was invisible

FORMAT_BY_AUDIO exact-matched 'Flac', so an item whose lossless files are
tagged '24bit Flac' read as having no lossless copy: audio_format='flac'
yielded zero kept files and scoring made the recording unselectable. 382 of
609 'no flac available' items in the sampled corpus are this case.

Preference-ordered, never a union - 5 sampled items carry both Flac variants
and a union would keep every track twice. ordering now records which format
actually matched. Adds LOSSLESS_TITLE_FORMATS for read-only title recovery,
which includes Shorten precisely because it is not a delivery format."
```

---

### Task 4: Stem-matched title recovery (pure function)

The join itself, with no wiring. Task 5 calls it.

**Files:**
- Modify: `packages/llama/src/llama/titles.py`
- Test: `packages/llama/tests/test_titles.py`

**Interfaces:**
- Consumes: `clean_tag_titles` from Task 1.
- Produces:
  `sibling_format_titles(kept: list[dict], other_kept: list[dict]) -> dict[str, str] | None`
  — maps each kept file's `name` to the title carried by the same track in a
  different-format copy of the same item. `None` unless the two sets are a
  stem bijection.

**Why a dict and not a list:** `run_gather` applies `overrides.exclude` to
`kept` *after* filtering, and `filter_files` may reorder by track tag. A
filename-keyed map survives both; a positional list would silently
misalign.

- [ ] **Step 1: Write the failing tests**

```python
def fmt_files(names_titles: list[tuple[str, str]]) -> list[dict]:
    return [{"name": n, "title": t} for n, t in names_titles]


def test_sibling_format_titles_matches_by_stem():
    mp3 = fmt_files([("d1t01.mp3", ""), ("d1t02.mp3", "")])
    flac = fmt_files([("d1t01.flac", "Jack Straw"), ("d1t02.flac", "Sugaree")])
    assert sibling_format_titles(mp3, flac) == {
        "d1t01.mp3": "Jack Straw", "d1t02.mp3": "Sugaree",
    }


def test_sibling_format_titles_survives_a_reordered_sibling():
    """The map is keyed by name, so sibling order is irrelevant."""
    mp3 = fmt_files([("d1t01.mp3", ""), ("d1t02.mp3", "")])
    flac = fmt_files([("d1t02.flac", "Sugaree"), ("d1t01.flac", "Jack Straw")])
    assert sibling_format_titles(mp3, flac) == {
        "d1t01.mp3": "Jack Straw", "d1t02.mp3": "Sugaree",
    }


def test_sibling_format_titles_declines_on_a_count_mismatch():
    mp3 = fmt_files([("d1t01.mp3", ""), ("d1t02.mp3", "")])
    flac = fmt_files([("d1t01.flac", "Jack Straw")])
    assert sibling_format_titles(mp3, flac) is None


def test_sibling_format_titles_declines_when_stems_differ():
    """Same count, different naming convention - guessing by position here is
    exactly the failure this function exists to refuse."""
    mp3 = fmt_files([("d1t01.mp3", ""), ("d1t02.mp3", "")])
    flac = fmt_files([("track01.flac", "Jack Straw"), ("track02.flac", "Sugaree")])
    assert sibling_format_titles(mp3, flac) is None


def test_sibling_format_titles_declines_on_duplicate_stems():
    mp3 = fmt_files([("t01.mp3", ""), ("t01.mp3", "")])
    flac = fmt_files([("t01.flac", "A"), ("t01.flac", "B")])
    assert sibling_format_titles(mp3, flac) is None


def test_sibling_format_titles_declines_on_empty_input():
    assert sibling_format_titles([], []) is None


def test_sibling_format_titles_keeps_subdirectories_distinct():
    """archive.org names can carry a directory component; two files sharing a
    basename in different directories are different tracks."""
    mp3 = fmt_files([("d1/t01.mp3", ""), ("d2/t01.mp3", "")])
    flac = fmt_files([("d1/t01.flac", "Bertha"), ("d2/t01.flac", "Sugaree")])
    assert sibling_format_titles(mp3, flac) == {
        "d1/t01.mp3": "Bertha", "d2/t01.mp3": "Sugaree",
    }


def test_sibling_format_titles_cleans_recovered_titles():
    """Recovered FLAC tags carry leading track numbers too - measured at 5 of
    2,928 - so the enumerated-tape gate must run over them as well."""
    mp3 = fmt_files([(f"t{n:02d}.mp3", "") for n in range(1, 5)])
    flac = fmt_files([
        ("t01.flac", "01 Bertha"), ("t02.flac", "02 Sugaree"),
        ("t03.flac", "03 Dire Wolf"), ("t04.flac", "04 Loser"),
    ])
    assert sibling_format_titles(mp3, flac) == {
        "t01.mp3": "Bertha", "t02.mp3": "Sugaree",
        "t03.mp3": "Dire Wolf", "t04.mp3": "Loser",
    }
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest packages/llama/tests/test_titles.py -q -k sibling_format`
Expected: `ImportError: cannot import name 'sibling_format_titles'`.

- [ ] **Step 3: Implement**

In `titles.py`, below `clean_tag_titles`:

```python
def _stem_no_ext(name: str) -> str:
    """Filename without its extension, directory component retained - two
    files sharing a basename in different directories are different tracks."""
    head, sep, tail = name.rpartition(".")
    return head if sep and "/" not in tail else name


def sibling_format_titles(
    kept: list[dict], other_kept: list[dict]
) -> dict[str, str] | None:
    """Map each kept file's name to the title carried by the SAME track in a
    different-format copy of the same archive.org item.

    archive.org builds the lossy derivative from the lossless original and
    sometimes does not carry the tags across, leaving a fully-tagged FLAC
    beside an untagged MP3 of the same tracks. Matching is by filename stem
    and requires a bijection: anything less declines rather than guessing by
    position."""
    if not kept or len(kept) != len(other_kept):
        return None
    ours = {_stem_no_ext(f["name"]): f["name"] for f in kept}
    theirs = {_stem_no_ext(f["name"]): f for f in other_kept}
    if len(ours) != len(kept) or len(theirs) != len(other_kept) or set(ours) != set(theirs):
        return None
    titles = clean_tag_titles([theirs[stem] for stem in ours])
    return {name: title for name, title in zip(ours.values(), titles)}
```

- [ ] **Step 4: Run to verify they pass**

Run: `pytest packages/llama/tests/test_titles.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/titles.py packages/llama/tests/test_titles.py
git commit -m "feat(titles): stem-matched title recovery across formats

sibling_format_titles maps a kept file to the title on the same track of a
different-format copy of the SAME item. Nothing calls it yet.

Keyed by filename rather than position so it survives overrides.exclude and
filter_files' track-tag reordering. Requires a stem bijection and declines
otherwise - guessing by position is the failure it exists to refuse."
```

---

### Task 5: Wire recovery into gather

**Files:**
- Modify: `packages/llama/src/llama/titles.py` (`resolve_titles` signature)
- Modify: `packages/llama/src/llama/stages/gather.py` (`run_gather`)
- Modify: `packages/llama/src/llama/models.py` (`Track.title_source` comment)
- Test: `packages/llama/tests/test_stage_gather.py`

**Interfaces:**
- Consumes: `sibling_format_titles`, `title_fraction`, `clean_tag_titles`
  (tasks 1 and 4); `LOSSLESS_TITLE_FORMATS` and `ordering["format"]` (task 3).
- Produces: `resolve_titles(kept_files, setlist, sibling_titles=None,
  format_titles: dict[str, str] | None = None)`; a new `title_source` value
  `"sibling-format"`.

- [ ] **Step 1: Write the failing tests**

The `gd73_metadata.json` fixture already carries what this needs: 6 `VBR MP3`
derivatives and the 6 `Shorten` originals they came from, with **matching
stems** (`gd73-06-10d1t01.mp3` / `gd73-06-10d1t01.shn`). So the A3 shape is
one helper away.

**The `.shn` entries have `length: None`, and `filter_files` drops all six as
"missing duration".** The helper must supply a length, or the lossless set is
empty, recovery never fires, and the tests pass or fail for a reason unrelated
to the constraint under test. Verify while writing them: a helper-built
`filter_files(md["files"], want_format="Shorten")` must return 6 files.

```python
_LOSSLESS_TITLES = {
    "gd73-06-10d1t01": "Morning Dew", "gd73-06-10d1t02": "China Cat Sunflower",
    "gd73-06-10d1t03": "I Know You Rider", "gd73-06-10d2t01": "Dark Star",
    "gd73-06-10d2t02": "Eyes of the World", "gd73-06-10d3t01": "Johnny B. Goode",
}


def _with_tagged_lossless(md: dict, *, lossless_format: str = "Shorten",
                          tag_mp3: bool = False) -> dict:
    """The A3 shape: the mp3 derivatives carry no titles while the lossless
    originals of the SAME item are fully tagged, stems matching.

    The fixture's .shn entries have length=None, which filter_files excludes as
    'missing duration' - a length MUST be set here or the lossless set is empty
    and every assertion below becomes vacuous."""
    md = {"metadata": dict(md["metadata"]), "files": [dict(f) for f in md["files"]]}
    for f in md["files"]:
        stem = f["name"].rsplit(".", 1)[0]
        if f.get("format") == "VBR MP3" and not tag_mp3:
            f["title"] = None
        if f.get("format") == "Shorten":
            f["format"] = lossless_format
            f["length"] = "05:00"
            f["title"] = _LOSSLESS_TITLES.get(stem)
    return md


def test_gather_recovers_titles_from_the_lossless_sibling(tmp_path: Path):
    """The mp3 derivative carries no titles; the lossless originals of the same
    item are fully tagged. Measured at 166 of 1,444 two-format items."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert [t.title for t in show.tracks] == list(_LOSSLESS_TITLES.values())
    assert all(t.title_source == "sibling-format" for t in show.tracks)


def test_gather_recovers_from_24bit_flac(tmp_path: Path):
    """gd1971-02-23's shape: the lossless files are tagged '24bit Flac', which
    was invisible before the format-preference fix."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()),
                               lossless_format="24bit Flac")
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert [t.title for t in show.tracks] == list(_LOSSLESS_TITLES.values())
    assert all(t.title_source == "sibling-format" for t in show.tracks)


def test_gather_prefers_its_own_tags_when_they_are_good(tmp_path: Path):
    """Recovery must not fire on a healthy tape. The sibling titles are
    poisoned so a wrongly-firing recovery is visible rather than silent."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()), tag_mp3=True)
    for f in md["files"]:
        if f.get("format") == "Shorten":
            f["title"] = "WRONG"
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert "WRONG" not in [t.title for t in show.tracks]
    assert all(t.title_source != "sibling-format" for t in show.tracks)


def test_gather_declines_recovery_when_the_sibling_is_also_untagged(tmp_path: Path):
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    for f in md["files"]:
        if f.get("format") == "Shorten":
            f["title"] = None
    show = run_gather(ShowWorkspace(tmp_path / "show"), StubIA(md), FakeProvider(),
                      make_candidate(), IDENT)
    assert all(t.title_source != "sibling-format" for t in show.tracks)


def test_gather_recovery_survives_an_operator_exclusion(tmp_path: Path):
    """overrides.exclude drops a file AFTER filtering. A positional recovery
    list would misalign every title after the hole; the filename-keyed map
    does not."""
    md = _with_tagged_lossless(json.loads(FIXTURE.read_text()))
    ws = ShowWorkspace(tmp_path / "show")
    write_artifact(ws.overrides, Overrides(exclude=["gd73-06-10d1t02.mp3"]))
    show = run_gather(ws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert [t.title for t in show.tracks] == [
        "Morning Dew", "I Know You Rider", "Dark Star",
        "Eyes of the World", "Johnny B. Goode",
    ]
```

`Overrides` and `write_artifact` are already imported in that file.

- [ ] **Step 2: Run to verify they fail**

Run: `pytest packages/llama/tests/test_stage_gather.py -q -k "recover or sibling_format or own_tags"`
Expected: the recovery tests FAIL with `title_source == "unresolved"`;
`test_gather_prefers_its_own_tags_when_they_are_good` should already PASS.

- [ ] **Step 3: Extend `resolve_titles`**

In `titles.py`:

```python
def resolve_titles(
    kept_files: list[dict],
    setlist: ParsedSetlist,
    sibling_titles: list[str] | None = None,
    format_titles: dict[str, str] | None = None,
) -> list[Track]:
```

and replace the tag layer inside it:

```python
    # When format recovery fired, the delivered format's own tags are known
    # bad and are not consulted at all - a manifest never interleaves two tag
    # sources. A recovered title that is still unusable falls through to the
    # setlist/sibling cascade rather than back to the bad tags.
    if format_titles is not None:
        tag_titles = [format_titles.get(f["name"], "") for f in files]
        tag_source = "sibling-format"
    else:
        tag_titles = clean_tag_titles(files)
        tag_source = "tags"

    tracks: list[Track] = []
    for pos, f in enumerate(files):
        if is_real_title(tag_titles[pos]):
            title, source = tag_titles[pos], tag_source
        elif aligned:
```

(the remaining branches are unchanged)

Update the `Track.title_source` comment in `models.py`:

```python
    title_source: str  # "tags" | "sibling-format" | "setlist" | "sibling" | "unresolved" | "override"
```

- [ ] **Step 4: Wire the trigger in `run_gather`**

In `gather.py`, immediately after the `filter_files` call and **before** the
`overrides.exclude` block:

```python
    format_titles = _recover_format_titles(md.get("files", []), kept, ordering)
```

and add the helper beside `_sibling_titles`:

```python
# Recovery fires below this and requires the sibling to clear the second
# threshold. Both are the values the spec's 166-item measurement was taken
# at and were not independently swept - changing them invalidates it.
_RECOVER_BELOW = 0.5
_RECOVER_SIBLING_ABOVE = 0.9


def _recover_format_titles(
    files: list[dict], kept: list[dict], ordering: dict
) -> dict[str, str] | None:
    """Titles lifted from a lossless copy of the same item, when the delivered
    format's own tags are missing. archive.org sometimes builds the lossy
    derivative without carrying the tags across."""
    if title_fraction(clean_tag_titles(kept)) >= _RECOVER_BELOW:
        return None
    for fmt in LOSSLESS_TITLE_FORMATS:
        if fmt == ordering.get("format"):
            continue  # that is the set we already have
        other, _, _ = filter_files(files, want_format=fmt)
        recovered = sibling_format_titles(kept, other)
        if recovered and title_fraction(list(recovered.values())) >= _RECOVER_SIBLING_ABOVE:
            return recovered
    return None
```

Then pass it through at the `resolve_titles` call:

```python
    tracks = resolve_titles(kept, canonical, sibling_titles=siblings,
                            format_titles=format_titles)
```

Import `LOSSLESS_TITLE_FORMATS` from `llama.junk` and `sibling_format_titles`
from `llama.titles` in `gather.py`.

**Note the ordering constraint:** `format_titles` is computed before
`overrides.exclude` runs, so it covers files the operator later drops. That is
harmless — it is a map, and `resolve_titles` only looks up the names still in
`kept`.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: all pass, 1338 + the new tests.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/titles.py packages/llama/src/llama/stages/gather.py \
        packages/llama/src/llama/models.py packages/llama/tests/test_stage_gather.py
git commit -m "feat(gather): recover track titles from an item's lossless sibling

When the delivered format's tags are missing (title_fraction < 0.5) and a
lossless copy of the SAME item is well tagged (>= 0.9) with a filename-stem
bijection, titles are lifted across and stamped title_source=sibling-format.
Measured: 166 of 1,444 two-format items are affected, all 166 have a perfect
bijection, and all 166 go from no usable titles to usable ones.

No download and no tag parsing - both formats' titles are already in the
cached metadata response.

Recovery replaces the tag layer wholesale rather than filling gaps, so a
manifest never interleaves two tag sources; a recovered title that is still
unusable falls through to the setlist cascade."
```

---

### Task 6: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/workflow.md`

- [ ] **Step 1: Update `CLAUDE.md`**

In the architecture section, alongside the existing description of the
title cascade, record three facts a future maintainer will otherwise
re-derive:

- `clean_tag_titles` gates the leading-track-number strip on the recording
  (>=3 numbered files and >=80% coverage); `clean_tag_title` remains the
  per-string cleaner. The `\d{1,3}` bound is what protects
  `1952 Vincent Black Lightning` and must not be widened.
- `FORMAT_BY_AUDIO` values are ordered preference tuples, tried in order,
  never unioned. `LOSSLESS_TITLE_FORMATS` is the broader read-only set used
  for title recovery and deliberately includes `Shorten`, which is not a
  delivery format.
- Title cascade is now recovered-format tags -> own tags -> setlist ->
  sibling recording -> unresolved, with `title_source` recording which fired.
  Recovery is wholesale, not gap-filling.

- [ ] **Step 2: Update `docs/workflow.md`**

Add `sibling-format` to any operator-facing list of title sources, so an
operator reading a manifest knows what it means.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/workflow.md
git commit -m "docs: record the enumerated-tape gate and format title recovery"
```

---

## Verification before finishing

- [ ] `pytest -q` green from the correct interpreter (in a worktree:
      `./.venv/bin/pytest -q`, and confirm `python -c "import llama; print(llama.__file__)"`
      resolves inside the worktree, not the main checkout).
- [ ] `grep -rn "clean_tag_title(" packages/llama/src` returns only the
      definition and `clean_tag_titles`' own use of it — no call site still
      bypasses the gate.
- [ ] `grep -rn "FORMAT_BY_AUDIO" packages/llama/src` — every reader passes
      the value straight to `filter_files`.
- [ ] The two mutation checks from Task 1 Step 5 were actually run and each
      failed its named test.

## Out of scope

- **A2**, the setlist parser splitting titles on commas — its own spec.
- Adding `Shorten` to the delivery formats.
- The 15 measured items where FLAC titles are *worse* than mp3.
- Verifying that a recovered title is the *correct* song for its track.
  `LosLobos2007-05-06`'s source tags are off by one against its own
  filenames; recovery imports a real-looking wrong title there. Accepted.
