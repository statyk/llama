# Setlist Parser, Non-Songs and Title Variants (phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the setlist parser emitting junk, teach it the bare `E:` marker, recognise spoken segments as non-songs while keeping Drums/Space/Feedback as songs, and close the last title-variant classes that no general rule can reach.

**Architecture:** Three layers, touched in dependency order. `setlist.py` (the description parser) stops emitting non-songs and mis-titled items. `structure.py` gains a space-insensitive comparison fallback and a directional Jam/Space rule. `songs.py` gains variant entries in the existing family-gated table. `gather.py` gains the one filter that needs artist identity.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest. No new dependencies.

Spec: `docs/superpowers/specs/2026-08-02-setlist-parser-and-variants-design.md`

## Global Constraints

- **No new dependencies.**
- **`songs.normalize_song` and `songs.DEFAULT_ALIASES` must not be edited.** Phase 2's layering rests on the fuzz staying at the matching layer. `GD_SHORTHAND` may gain entries; `DEFAULT_ALIASES` may not.
- **Drums, Space, Feedback and Drumz are SONGS.** Any change that makes them filler is a spec violation, not a judgment call. Task 1 pins this with a test; do not weaken it later.
- **Baseline to beat: 1227 passed / 7 deselected**, at `f3c6f3b`. **In a git worktree, create the worktree's own venv and run `./.venv/bin/pytest`** — the repo-root `.venv` resolves `llama` to the *main* checkout, so a bare `pytest` from a worktree silently tests the wrong source and still passes.
- **Never verify library behavior with `llama show`** — it renders stored state and never re-runs `gather`. Verify in-process.
- **Commit after every task**, conventional-commit prefixes.
- Corpus scripts live in `~/projects/llama-setlist-analysis/` and are **not** part of this repo.

---

### Task 1: Non-song recognition

`_FILLER` covers tuning/repairs/announce/applause/crowd/banter/soundcheck/equipment. It misses the intro/outro/chat/talk class and `encore break` — 60 and 55 misses respectively on the Dead corpus, 77 + 21 + 15 + 12 on the non-Dead one. It correctly omits drums/space, and must keep omitting them.

**Files:**
- Modify: `packages/llama/src/llama/structure.py:18-26` (`_FILLER`, `is_filler`)
- Test: `packages/llama/tests/test_structure.py`

**Interfaces:**
- Consumes: nothing.
- Produces: no signature change. `is_filler` returns True for more titles.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_structure.py`:

```python
def test_filler_covers_spoken_and_break_segments():
    for t in ("Intro", "intro", "Outro", "Chat", "Chatter", "talk",
              "Band Intros & Chatter", "Encore Break", "encore break",
              "Intro by Fiona Black"):
        assert is_filler(t), t


def test_filler_never_swallows_drums_space_or_feedback():
    # Domain ruling: Drums, Space and Feedback are SONGS. They segue into and
    # out of adjacent songs and sit mid-second-set from ~1979 on. Treating them
    # as filler would drop them out of set-break reasoning entirely.
    for t in ("Drums", "Drums >", "Drumz", "Space", "Space ->", "Feedback",
              "Drums > Space >"):
        assert not is_filler(t), t


def test_filler_does_not_match_songs_containing_those_words():
    # "talk" must not fire on "Talkin'", "chat" must not fire on "Chattanooga".
    for t in ("Talkin' World War III Blues", "Chattanooga Choo Choo",
              "Introduction To The Blues Jam", "Big Railroad Blues"):
        assert not is_filler(t), t
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -k filler -q`
Expected: FAIL on `test_filler_covers_spoken_and_break_segments` — `Intro` is not currently filler.

- [ ] **Step 3: Implement**

Replace `packages/llama/src/llama/structure.py:18-26` with:

```python
# Non-song tracks (tuning, repairs, announcements, crowd noise, spoken
# segments, the gap before an encore) that no canonical setlist contains; they
# must not count against alignment coverage.
#
# DELIBERATELY ABSENT, and must stay absent: drums, drumz, space, feedback.
# Those are SONGS — they segue into and out of adjacent songs and sit
# mid-second-set from roughly 1979 on. See test_filler_never_swallows_drums_
# space_or_feedback.
#
# Whether any of these ships on air is a separate, per-show human decision,
# served by overrides.exclude / `llama fix --exclude`. This regex answers only
# "is it a song for setlist reconciliation and set-break placement".
#
# Word-anchored on the ambiguous members: bare "talk" and "chat" would
# otherwise fire on "Talkin' World War III Blues" and "Chattanooga".
_FILLER = re.compile(
    r"tun(?:ing|e\s*-?\s*up)|repairs?|announ?ce|applause|crowd|banter"
    r"|soundcheck|equipment|\bintros?\b|\boutros?\b|\bchat(?:ter)?\b"
    r"|\btalk\b|encore\s+break",
    re.I,
)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1227 + 3 new = 1230 passed, 7 deselected.

Coverage rising on a gather fixture is expected here — filler is excluded from the coverage denominator, so recognising more of it *raises* coverage. A fixture whose **set labels** move is not expected; investigate before blessing it.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/tests/test_structure.py
git commit -m "feat: recognise spoken segments and encore breaks as non-songs"
```

---

### Task 2: Parser — leading track numbers

`_TRACK_PREFIX` is `^\s*(?:(?:d\d+t\d+|t\d{1,2})\s*[\s.\-:]+|\d{1,2}\s*[.)]\s+)`. The bare-number branch requires **both** punctuation and trailing whitespace, and caps at 2 digits. So it strips `01. Song` but misses `01 intro`, `1.Sugaree`, `01....Song` and `207. Space >`.

**The naive widening is wrong.** These are real corpus titles that must survive:
`1952 Vincent Black Lightning`, `72 (This Highway's Mean)`, `8 Miles High`, `50 Ways To Leave Your Lover`.

The discriminator is that a track-number prefix is **enumerated**: it appears on many lines of the same description, ascending. A song that merely starts with a number does not. So the strip is decided per *description*, not per line.

**Files:**
- Modify: `packages/llama/src/llama/setlist.py:30-32` (`_TRACK_PREFIX`), and `parse_setlist` around line 107
- Test: `packages/llama/tests/test_setlist.py`

**Interfaces:**
- Consumes: nothing.
- Produces: module-private `_enumerated_prefix(lines: list[str]) -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_setlist.py`:

```python
def test_enumerated_track_numbers_are_stripped():
    desc = ("Set 1:\n01 Bertha\n02 Jack Straw\n03 Sugaree\n04 Row Jimmy\n"
            "05 Big River\nSet 2:\n06 Truckin'\n07 Drums\n08 Space\n")
    items = parse_setlist(desc).items
    assert [i.title for i in items] == [
        "Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River",
        "Truckin'", "Drums", "Space"]


def test_enumerated_prefixes_without_a_space_are_stripped():
    desc = ("Set 1:\n1.Sugaree\n2.Bertha\n3.Loser\n4.Deal\n5.Althea\n")
    assert [i.title for i in parse_setlist(desc).items] == [
        "Sugaree", "Bertha", "Loser", "Deal", "Althea"]


def test_three_digit_and_repeated_dot_prefixes_are_stripped():
    desc = ("Set 2:\n205....Scarlet Begonias\n206....Fire On The Mountain\n"
            "207. Drums\n208. Space\n209. Truckin'\n")
    assert [i.title for i in parse_setlist(desc).items] == [
        "Scarlet Begonias", "Fire On The Mountain", "Drums", "Space", "Truckin'"]


def test_song_titles_starting_with_numbers_survive():
    # NOT enumerated: three lines begin with a digit, but only two of them
    # satisfy _NUM_LINE, so the >=3 gate stays shut by a margin of ONE line.
    # (There is no ascending-run rule — the gate is a bare count. An earlier
    # draft of this comment claimed both, and neither was true.)
    desc = ("Set 1:\nBertha\n1952 Vincent Black Lightning\n8 Miles High\n"
            "72 (This Highway's Mean)\nSugaree\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert "1952 Vincent Black Lightning" in titles
    assert "8 Miles High" in titles
    assert "72 (This Highway's Mean)" in titles
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_setlist.py -k "prefix or enumerated or numbers" -q`
Expected: FAIL — `01 Bertha`, `1.Sugaree` and `205....Scarlet Begonias` keep their prefixes.

- [ ] **Step 3: Implement**

In `packages/llama/src/llama/setlist.py`, replace lines 30-32 with:

```python
# Disc/track tokens are unambiguous and always stripped.
_TRACK_PREFIX = re.compile(
    r"^\s*(?:d\d+t\d+|t\d{1,2})\s*[\s.\-:]+", re.I
)
# A bare leading number is ambiguous: "01 Bertha" is a track number, but
# "1952 Vincent Black Lightning", "8 Miles High" and "72 (This Highway's Mean)"
# are song titles. Only strip it when the description is ENUMERATED — several
# lines carry one — which is what distinguishes a numbered tracklist from a
# song that happens to start with a digit.
_NUM_PREFIX = re.compile(r"^\s*\d{1,3}\s*[.)]*\s*")
_NUM_LINE = re.compile(r"^\s*\d{1,3}\s*[.)]*\s+\S")


def _enumerated_prefix(lines: list[str]) -> bool:
    """True when at least 3 lines begin with a number, i.e. the description is
    a numbered tracklist rather than prose containing a numeric title."""
    return sum(1 for ln in lines if _NUM_LINE.match(ln)) >= 3
```

Then in `parse_setlist`, after the `lines = lines[first_marker:]` block (line 75), add:

```python
    enumerated = _enumerated_prefix(lines)
```

and replace line 107 (`rest = _TRACK_PREFIX.sub("", rest)`) with:

```python
        rest = _TRACK_PREFIX.sub("", rest)
        if enumerated:
            rest = _NUM_PREFIX.sub("", rest)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_setlist.py -q`
Expected: PASS, including every pre-existing setlist test.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1230 + 4 new = 1234 passed, 7 deselected.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/setlist.py packages/llama/tests/test_setlist.py
git commit -m "fix(setlist): strip leading track numbers only in enumerated tracklists"
```

---

### Task 3: Parser — personnel credits, durations, disc markers

Measured junk items: `comment` 39 shows, `jerry garcia guitar` 34, `bob weir guitar` 22, plus bare durations (`01:50`, `(13:33)`) and `Disc #2` (which `_NOISE`'s `disc\s*\d` misses because of the `#`).

Band-name items (`del mccoury band`, `los lobos`) are **not** handled here — the parser never sees the artist. That is Task 4.

**Files:**
- Modify: `packages/llama/src/llama/setlist.py:34-39` (`_NOISE`), and `parse_setlist`'s emit loop around line 108
- Test: `packages/llama/tests/test_setlist.py`

**Interfaces:**
- Consumes: nothing.
- Produces: module-private `_is_junk_title(title: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
def test_personnel_credits_are_not_songs():
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Jerry Garcia - guitar\nBob Weir - guitar\n"
            "Bill Kreutzmann - drums\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_bare_durations_and_disc_markers_are_not_songs():
    desc = ("Set 1:\nBertha\n(13:33)\nJack Straw\n01:50\nDisc #2\n"
            "Sugaree\nRow Jimmy\nBig River\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]


def test_a_song_called_drums_survives_a_drums_credit():
    # "Bill Kreutzmann - drums" is a credit; a bare "Drums" is a song.
    desc = ("Set 2:\nTruckin'\nDrums\nSpace\nStella Blue\nSugar Magnolia\n"
            "Mickey Hart - drums\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert "Drums" in titles
    assert not any("Mickey" in t for t in titles)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_setlist.py -k "credits or durations or drums_credit" -q`
Expected: FAIL — credits and durations are emitted as items.

- [ ] **Step 3: Implement**

In `packages/llama/src/llama/setlist.py`, extend `_NOISE` (line 35-39) — note `disc\s*#?\s*\d` and the credit pattern:

```python
_NOISE = re.compile(
    r"(recorded|transfer|lineage|source|taper|shnid|seeded|thanks|conversion|remaster"
    r"|\bsbd\b|\bdat\b|\bflac\b|\bshn\b|cassette|master reel|\bvia\b|d\d+t\d+\s*$"
    r"|disc\s*#?\s*\d"
    # "Jerry Garcia - guitar", "Bill Kreutzmann - drums": a name, a dash, an
    # instrument. Anchored on the dash so a bare "Drums" song line is untouched.
    r"|[a-z]\s+[-–—]\s*(guitar|bass|drums?|vocals?|keyboards?|piano"
    r"|organ|percussion|harmonica|mandolin|fiddle|banjo|sax(?:ophone)?)\s*$"
    r"|^comments?\b)",
    re.I,
)

# Emitted-title junk: a bare duration or a disc marker that survived line-level
# noise filtering because it sat inside a comma-separated run.
_JUNK_TITLE = re.compile(r"^\(?\d{1,3}[:.]\d{2}\)?$|^disc\s*#?\s*\d+$", re.I)


def _is_junk_title(title: str) -> bool:
    return bool(_JUNK_TITLE.match(title.strip()))
```

Then in the emit loop, replace lines 108-110:

```python
        for title, segue in _split_songs(rest):
            if len(title) > MAX_TITLE_LEN:
                continue  # implausibly long fragment - prose, not a song title
            if _is_junk_title(title):
                continue
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_setlist.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1234 + 3 new = 1237 passed, 7 deselected.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/setlist.py packages/llama/tests/test_setlist.py
git commit -m "fix(setlist): reject personnel credits, bare durations and disc markers"
```

---

### Task 4: Drop setlist items that are just the artist's name

`Del McCoury Band` appears as a setlist item on ~90 corpus rows; `Los Lobos`, `Built To Spill`, `Justin Townes Earle`, `Spin Doctors` and `Ruthie Foster` do the same on the non-Dead corpus. These are header lines the parser reads as songs. The parser cannot know — it never receives the artist — so the filter lives in `gather`, which does.

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (after `canonical` is chosen, before `align` is called at ~line 212)
- Test: `packages/llama/tests/test_stage_gather.py`

**Interfaces:**
- Consumes: `jerrybase.artist_key` (already imported via `jerrybase`).
- Produces: module-private `_drop_artist_items(parsed, artist)` in `gather.py`.

- [ ] **Step 1: Write the failing test**

Follow the file's existing fixture conventions for driving `run_gather`; the assertion is:

```python
def test_gather_drops_setlist_items_that_are_the_artist_name(...):
    """A description header line ("Del McCoury Band") parses as a song. It can
    never match a track and it inflates the setlist, pushing the two-pointer
    behind until later songs fall outside the lookahead window."""
    # ... arrange a description whose setlist includes the artist's own name ...
    assert "Del McCoury Band" not in show.structure.conflicts
    assert all("mccoury" not in c.lower() for c in show.structure.conflicts)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -k artist_name -q`
Expected: FAIL — the artist-name item survives and appears in conflicts.

- [ ] **Step 3: Implement**

Add to `packages/llama/src/llama/stages/gather.py`:

```python
def _drop_artist_items(parsed: ParsedSetlist, artist: str) -> ParsedSetlist:
    """Remove setlist items that are just the performing artist's name.

    LMA descriptions routinely put the band name on its own line above the
    songs; the parser has no artist to compare against, so it emits it as a
    song. It can never match a track, and every such item pushes the alignment
    pointer one step further from where the next real song sits.
    """
    key = jerrybase.artist_key(artist)
    if not key:
        return parsed
    kept = [i for i in parsed.items if jerrybase.artist_key(i.title) != key]
    if len(kept) == len(parsed.items):
        return parsed
    return parsed.model_copy(update={"items": kept})
```

and call it where `canonical` is finalised, immediately before the `align` call:

```python
        canonical = _drop_artist_items(canonical, artist)
        aliases = GD_SHORTHAND if jerrybase.is_family_artist(artist) else {}
        result = align(tracks, canonical, aliases=aliases)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1237 + 1 new = 1238 passed, 7 deselected.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/tests/test_stage_gather.py
git commit -m "fix(gather): drop setlist items that are just the artist's name"
```

---

### Task 5: The bare `E:` mid-line marker

`_ENCORE_LINE` (line 22) uses `e\d?` — digit optional — so a bare `E:` at line start works. `_INLINE_MARKER` (lines 26-29) uses `e\d` — digit **mandatory** — so a bare mid-line `E:` never splits, and `... Sugar Magnolia; E: Goin' Down the Road` leaves the encore songs in set 2 with `E: ` glued to the title.

Measured: `E: Brokedown Palace` 18 shows, `E: Johnny B. Goode` 11, `E: Casey Jones` 7, `E: Black Muddy River` 7.

**Phase 2 left a characterization test that pins today's WRONG behavior** in `test_structure.py`, commented as such and naming `_INLINE_MARKER` as the fix site. **Its set-label assertion must be updated in this task** — that is the signal the fix worked. Do not delete the test; retarget it.

**Files:**
- Modify: `packages/llama/src/llama/setlist.py:26-29` (`_INLINE_MARKER`)
- Modify: `packages/llama/tests/test_structure.py` (the `E:` characterization test)
- Test: `packages/llama/tests/test_setlist.py`

- [ ] **Step 1: Write the failing test**

```python
def test_bare_e_marker_mid_line_starts_the_encore():
    desc = ("Set 2: Truckin', Stella Blue, Sugar Magnolia; "
            "E: Goin' Down The Road Feelin' Bad, One More Saturday Night")
    items = parse_setlist(desc).items
    by_title = {i.title: i.set for i in items}
    assert by_title["Sugar Magnolia"] == "2"
    assert by_title["Goin' Down The Road Feelin' Bad"] == "encore"
    assert by_title["One More Saturday Night"] == "encore"
    # the marker must not survive inside a title
    assert all(not i.title.upper().startswith("E:") for i in items)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/pytest packages/llama/tests/test_setlist.py -k bare_e -q`
Expected: FAIL — the encore songs carry set `"2"`, and one title is `E: Goin' Down The Road Feelin' Bad`.

- [ ] **Step 3: Implement**

Replace `packages/llama/src/llama/setlist.py:26-29`:

```python
# A set/encore marker mid-line ("... Bertha Set II: Playin' ...") starts a new
# set: break the line there. Inline markers must carry a colon or a dash
# followed by space - unlike line-start markers - so prose like "the second
# set" never splits a title.
#
# The encore digit is OPTIONAL, matching _ENCORE_LINE's "e\d?": a bare "E:"
# mid-line is the single most common encore marker in LMA descriptions, and
# requiring the digit left the encore songs labelled with the preceding set.
_INLINE_MARKER = re.compile(
    r"\s+(?=(?:set\s*(?:one|two|three|i{1,3}|[123])|[123](?:st|nd|rd)\s+set"
    r"|encore|e\d?)\s*(?::|-\s))",
    re.I,
)
```

Note the trailing group changed from `[:\-]` to `(?::|-\s)`, matching `_ENCORE_LINE`. Without it, `e` + bare `-` would split hyphenated prose.

- [ ] **Step 4: Retarget phase 2's characterization test**

In `packages/llama/tests/test_structure.py`, find the `E:` prefix characterization test. Update its set-label assertion to the now-correct value, replace the "expected to change in phase 3" comment with a note that phase 3 fixed it, and keep the test as a regression guard.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_setlist.py packages/llama/tests/test_structure.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1238 + 1 new = 1239 passed, 7 deselected.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/setlist.py packages/llama/tests/
git commit -m "fix(setlist): a bare mid-line E: starts the encore"
```

---

### Task 6: Space-insensitive comparison fallback

Three high-frequency variant pairs are identical once spaces are ignored:
`turn on your lovelight` / `turn on your love light` (29 shows), `cc rider` / `c c rider` (18 + 18), `west la fadeaway` / `west l a fadeaway` (8).

Added as a fallback **after** exact and subphrase, never before, so it cannot pre-empt a better match.

**Files:**
- Modify: `packages/llama/src/llama/structure.py:70-87` (`fuzzy_title_eq`)
- Test: `packages/llama/tests/test_structure.py`

**Interfaces:**
- Consumes: `_NEVER_EQUAL` (phase 2).
- Produces: no signature change; `fuzzy_title_eq` matches more pairs.

- [ ] **Step 1: Write the failing tests**

```python
def test_space_insensitive_fallback_matches_spacing_variants():
    assert fuzzy_title_eq("turn on your lovelight", "turn on your love light")
    assert fuzzy_title_eq("cc rider", "c c rider")
    assert fuzzy_title_eq("west la fadeaway", "west l a fadeaway")


def test_space_insensitive_fallback_respects_the_blocklist():
    assert not fuzzy_title_eq("its all over now", "its all over now baby blue")


def test_space_insensitive_fallback_does_not_equate_distinct_songs():
    assert not fuzzy_title_eq("black peter", "black muddy river")
    assert not fuzzy_title_eq("the wheel", "wheel of fortune")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -k space_insensitive -q`
Expected: FAIL on the first test — `cc rider` != `c c rider` today.

- [ ] **Step 3: Implement**

In `fuzzy_title_eq`, after the subphrase branch:

```python
    if a == b:
        return True
    if frozenset({a, b}) in _NEVER_EQUAL:
        return False
    if _is_subphrase(a, b) or _is_subphrase(b, a):
        return True
    # Spacing-only variants: "Turn On Your Lovelight" / "... Love Light",
    # "CC Rider" / "C C Rider", "West LA Fadeaway" / "West L A Fadeaway".
    # Last resort, after exact and subphrase, so it can never pre-empt a
    # better-supported match. Validated against all 517 jerrybase closers:
    # it introduces no new cross-song pair (see the phase-3 spec).
    return a.replace(" ", "") == b.replace(" ", "")
```

- [ ] **Step 4: Validate against the closer vocabulary**

Run:

```bash
./.venv/bin/python - <<'PY'
import csv, itertools
from llama.songs import GD_SHORTHAND
from llama.structure import fuzzy_title_eq, title_components
rows = list(csv.DictReader(open('packages/llama/src/llama/data/set_breaks.csv')))
closers = sorted({title_components(r['song'], GD_SHORTHAND)[-1]
                  for r in rows if r.get('song')})
pairs = [(a, b) for a, b in itertools.combinations(closers, 2) if fuzzy_title_eq(a, b)]
print(len(closers), 'closers;', len(pairs), 'fuzzy-equal pairs')
for a, b in pairs:
    print('  ', a, '|', b)
PY
```

Phase 2's result was **16 pairs, all benign** (14 one-song-two-spellings, 2 of the `X`/`X Jam` shape). Any pair this task ADDS must be inspected individually. A genuine cross-song pair goes into `_NEVER_EQUAL` with a test, and this step re-runs. Report the pair count in the task report either way.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1239 + 3 new = 1242 passed, 7 deselected.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/tests/test_structure.py
git commit -m "feat: space-insensitive comparison fallback for spacing variants"
```

---

### Task 7: Spelling variants and the one true synonym

Family-gated, in the existing `GD_SHORTHAND` table. Every entry below recurs across many distinct corpus shows; entries are added on measured recurrence, not intuition.

**Files:**
- Modify: `packages/llama/src/llama/songs.py` (`GD_SHORTHAND`)
- Test: `packages/llama/tests/test_structure.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_spelling_variants_collapse_under_the_family_table():
    from llama.songs import GD_SHORTHAND
    pairs = [("Touch of Gray", "Touch of Grey"),
             ("Drumz", "Drums"),
             ("Throwin Stones", "Throwing Stones"),
             ("Man Smart, Woman Smarter", "Women Are Smarter")]
    for a, b in pairs:
        assert fuzzy_norm_title(a, GD_SHORTHAND) == fuzzy_norm_title(b, GD_SHORTHAND), (a, b)


def test_variants_do_nothing_without_the_family_table():
    assert fuzzy_norm_title("Touch of Gray") != fuzzy_norm_title("Touch of Grey")
    assert fuzzy_norm_title("Women Are Smarter") != fuzzy_norm_title("Man Smart, Woman Smarter")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -k variants -q`
Expected: FAIL — `touch of gray` and `touch of grey` differ.

- [ ] **Step 3: Implement**

Append to `GD_SHORTHAND` in `packages/llama/src/llama/songs.py`, inside the existing dict:

```python
    # --- Spelling variants (same song, two spellings). Each recurs across many
    # corpus shows: 22, 15, 10 and 8 distinct shows respectively.
    "touch of gray": "touch of grey",
    "mississippi half step uptown toodleloo": "mississippi half step uptown toodeloo",
    "drumz": "drums",
    "throwin stones": "throwing stones",
    # --- True synonym: the same song under two full names, 21 shows. Neither
    # is a subphrase of the other, so no general rule can ever connect them —
    # this is the case a table exists for. "Man Smart, Woman Smarter" is the
    # calypso title; "Women Are Smarter" is what Dead setlists usually say.
    "women are smarter": "man smart woman smarter",
```

- [ ] **Step 4: Re-check the table invariants**

The existing `test_shorthand_targets_are_all_canonical_and_two_way_safe` asserts no value is also a key (no chaining). Confirm it still passes — `drums`, `touch of grey`, `throwing stones` and `man smart woman smarter` must not appear as keys.

- [ ] **Step 5: Re-run the closer validation from Task 6 Step 4**

The table widens the fuzzy surface, so the 517-closer check must be re-run with these entries present. Report the pair count.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1242 + 2 new = 1244 passed, 7 deselected.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/songs.py packages/llama/tests/test_structure.py
git commit -m "feat: spelling variants and the Man Smart/Women Are Smarter synonym"
```

---

### Task 8: The directional Jam/Space rule

Setlists frequently write `Jam` where the tape says `Space` — 45 shows, the highest-frequency pair in the corpus sweep. The domain ruling:

> Space is always a jam, but a jam is not always space. Space basically implies a jam without the drummers (Drums being the inverse — just the drummers), so the lines get fuzzy.

So the rule is **directional and conditioned**: a track *called* Space, **immediately preceded by a Drums track**, may match an otherwise-unclaimed `Jam` item. Never the reverse — a `Jam` track must not match a `Space` item, and a Space track with no preceding Drums must not either. The track's own title is the evidence.

**Files:**
- Modify: `packages/llama/src/llama/structure.py` (`align`)
- Test: `packages/llama/tests/test_structure.py`

**Interfaces:**
- Consumes: `align` (phase 2).
- Produces: no signature change.

- [ ] **Step 1: Write the failing tests**

```python
def test_space_after_drums_matches_a_jam_item():
    c = canon(("2", "Eyes Of The World", True), ("2", "Drums", True),
              ("2", "Jam", True), ("2", "Stella Blue", False))
    r = align([tr(1, "Eyes Of The World >"), tr(2, "Drums >"),
               tr(3, "Space >"), tr(4, "Stella Blue")], c)
    assert r.matched == [True, True, True, True]
    assert r.sets == ["2", "2", "2", "2"]


def test_space_without_a_preceding_drums_does_not_match_jam():
    c = canon(("2", "Eyes Of The World", True), ("2", "Jam", True),
              ("2", "Stella Blue", False))
    r = align([tr(1, "Eyes Of The World >"), tr(2, "Space >"),
               tr(3, "Stella Blue")], c)
    assert r.matched == [True, False, True]


def test_a_jam_track_does_not_match_a_space_item():
    # The rule is directional: the TRACK being called Space is the evidence.
    c = canon(("2", "Drums", True), ("2", "Space", True), ("2", "Stella Blue", False))
    r = align([tr(1, "Drums >"), tr(2, "Jam >"), tr(3, "Stella Blue")], c)
    assert r.matched == [True, False, True]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -k "jam" -q`
Expected: FAIL on the first test — the Space track does not match the `Jam` item.

- [ ] **Step 3: Implement**

Add near the other helpers in `structure.py`:

```python
_SPACE_TITLE = re.compile(r"^\s*space\b", re.I)
_DRUMS_TITLE = re.compile(r"^\s*drum[sz]\b", re.I)
```

In `align`'s loop, after the single-match attempt fails and before falling through to the miss branch, add the conditioned fallback. `prev_title` is the previous track's raw title (`None` for the first track):

```python
        if hit is None and _SPACE_TITLE.match(t.title) and prev_title is not None \
                and _DRUMS_TITLE.match(prev_title):
            # Setlists often write "Jam" for what the tape calls Space. Space
            # is always a jam, but a jam is not always space — so this fires
            # only for a track titled Space that directly follows Drums, and
            # never in reverse. Measured on 45 corpus shows.
            hit = next((k for k in range(j, hi) if norms[k] == "jam"), None)
```

Track `prev_title` by assigning `prev_title = t.title` at the end of each loop iteration, initialised to `None` before the loop.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1244 + 3 new = 1247 passed, 7 deselected.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/tests/test_structure.py
git commit -m "feat: a Space track following Drums may match a Jam item"
```

---

### Task 9: Re-measure both corpora and record results

Measurement only — no production code. The spec's acceptance criteria are unmet until these numbers exist and have been read.

**Files:**
- No repo source. Uses `~/projects/llama-setlist-analysis/`.
- Modify: `docs/superpowers/specs/2026-08-02-setlist-parser-and-variants-design.md`

- [ ] **Step 1: Confirm which source is under test**

```bash
./.venv/bin/python -c "import llama; print(llama.__file__)"
```

Expected: a path inside **this checkout**. `score.py` hardcodes the main checkout's `src`, so a worktree that skips this step measures the wrong code and reports a convincing no-change.

- [ ] **Step 2: Anchoring must not regress**

```bash
cd ~/projects/llama-setlist-analysis
<checkout>/.venv/bin/python verify_impl.py corpus.jsonl
<checkout>/.venv/bin/python verify_impl.py corpus-nondead.jsonl
```

Expected: Dead **534/756 or better, 0 disagreements**; non-Dead 0/0. Any disagreement is stop-and-diagnose.

- [ ] **Step 3: Coverage must improve on BOTH corpora**

Re-run the phase-2 coverage measurement (mean per-show songish coverage and matched song-like tracks, old vs new). Baseline at `f3c6f3b`: **0.7598** Dead, **0.4653** non-Dead.

The non-Dead corpus is the anti-overfit guard — in phase 2 it improved *more* than the Dead corpus. A phase-3 change that helps only Dead tapes needs explaining, not excusing.

- [ ] **Step 4: Re-classify the miss buckets on both corpora**

Baseline: Dead C 56.3% / A 41.1% / B 2.6% / **D 0**; non-Dead C 39.4% / A 59.9% / B 0.7% / **D 0**.

**D must remain 0.** A is expected to FALL as junk items stop inflating the setlist. **If A does not fall, the cascade theory is wrong** and the parser work needs re-examining before anything else is built on it — say so plainly rather than reporting the other numbers and moving on.

Any classifier script must mirror `align()`'s real branch: `title_components` is used only when a title splits into more than one component; single-component titles go through `fuzzy_norm_title`, which keeps trailing parentheticals. Measuring with the stripped form manufactures phantom misses.

- [ ] **Step 5: Re-count the Space gap**

Baseline: 218 rows with a Space track and no Space item (209 of them ≥1979). Tasks 2, 3 and 8 all attack this from different directions. Report the new number — it is the input to the deferred synthesis decision.

- [ ] **Step 6: Record results in the spec**

Append a `## Measured results (phase 3)` section with: anchoring counts; coverage on both corpora; the four buckets on both corpora; the Space-gap count; the closer-pair count from Tasks 6-7 and any `_NEVER_EQUAL` additions; and the final `./.venv/bin/pytest -q` figure.

State plainly anything that came out worse than expected. The synthesis decision and any phase 4 are built on these numbers; a flattering summary is worse than no summary.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/specs/2026-08-02-setlist-parser-and-variants-design.md
git commit -m "docs: record phase-3 measured results"
```

---

## Self-review notes

Spec coverage: §1 non-songs → Task 1; §2 junk items → Tasks 2, 3, 4; §3 bare `E:` → Task 5; §4 variants → Tasks 6, 7; §5 Jam/Space → Task 8; acceptance criteria → Task 9. Space synthesis is deferred by the spec and has no task, deliberately.

Signature consistency: `is_filler(title)`, `fuzzy_title_eq(a, b)`, `fuzzy_norm_title(title, aliases=None)`, `title_components(title, aliases=None)`, `align(tracks, canonical, lookahead=3, aliases=None)` — all unchanged from phase 2. New module-privates: `setlist._enumerated_prefix`, `setlist._is_junk_title`, `gather._drop_artist_items`, `structure._SPACE_TITLE`, `structure._DRUMS_TITLE`.

Test-count expectations (1230 → 1234 → 1237 → 1238 → 1239 → 1242 → 1244 → 1247) assume no tests beyond those written here. Treat them as a guide; the **absence of failures** is the real gate.

Ordering is dependency-driven: parser tasks (2-5) precede the matching tasks (6-8) because they change what the matcher sees, and Task 9 must run last or its numbers describe a half-built branch.
