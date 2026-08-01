# Fuzzy Title Matching (phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `align()` tolerate the four ways taper track titles disagree with canonical setlist titles — `&`/`and`, dropped subtitles, merged (segued) tracks, and Dead-canon shorthand — so that a title mismatch stops dragging the following songs into the wrong set.

**Architecture:** All matching changes live at the matching layer: `structure.py`'s existing fuzzy seam (`fuzzy_norm_title`, `title_components`, `fuzzy_title_eq`) plus `align()`. `songs.normalize_song` is not edited. New Dead vocabulary is a table in `songs.py` gated on artist family (derived from the vendored jerrybase CSV), composed by `gather` and passed into `align()` as an `aliases` dict.

**Tech Stack:** Python 3.11+, Pydantic v2 models, pytest. No new dependencies.

Spec: `docs/superpowers/specs/2026-08-01-fuzzy-title-matching-design.md`

## Global Constraints

- **No new dependencies.** Everything here is stdlib + existing Pydantic models.
- **`songs.normalize_song` and `songs.DEFAULT_ALIASES` must not be edited.** The whole design rests on the fuzz staying at the matching layer. A diff touching either is a spec violation.
- **`SetlistItem.normalized` keeps its current value** (`normalize_song(title)`, unfolded). `align()` bypasses it; nothing else changes.
- **Tests are offline and deterministic.** No network, no LLM; the `fake` backend only.
- **Baseline to beat: 1201 passed / 7 deselected.** Run `pytest -q` from the repo root. **In a git worktree, create the worktree's own venv and run `./.venv/bin/pytest`** — the repo-root `.venv` resolves `llama` to the *main* checkout, so a bare `pytest` from a worktree silently tests the wrong source and still passes.
- **Commit after every task.** Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `docs:`).

---

### Task 1: `artist_key` `&`-fold and the family predicate

`artist_key` strips `&` instead of folding it, so `Dead & Company` keys as `deadcompany` while the CSV holds `DeadAndCompany` → `deadandcompany`. Those shows get no jerrybase evidence today (confirmed live: 92 corpus rows, 0 hits), and under the new gate they would also be denied the vocabulary. The family predicate that Task 6 needs is built here too, since both are about artist identity.

**Files:**
- Modify: `packages/llama/src/llama/jerrybase.py:30-34` (`artist_key`), and add `is_family_artist` after `lookup` (around line 132)
- Test: `packages/llama/tests/test_jerrybase.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `jerrybase.is_family_artist(artist: str) -> bool`. Task 6 calls it.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_jerrybase.py`:

```python
def test_artist_key_folds_ampersand_to_and():
    # The CSV spells these "DeadAndCompany" / "PhilLeshAndFriends"; stripping
    # "&" instead of folding it silently denied both acts all evidence.
    assert jerrybase.artist_key("Dead & Company") == "deadandcompany"
    assert jerrybase.artist_key("Phil Lesh & Friends") == "philleshandfriends"
    assert jerrybase.artist_key("Grateful Dead") == "gratefuldead"


def test_is_family_artist_covers_dataset_and_extras():
    assert jerrybase.is_family_artist("Grateful Dead")
    assert jerrybase.is_family_artist("Dark Star Orchestra")
    assert jerrybase.is_family_artist("Dead & Company")
    # Absent from the dataset, but family by vocabulary.
    assert jerrybase.is_family_artist("Joe Russo's Almost Dead")
    # Not family: must get no Dead vocabulary.
    assert not jerrybase.is_family_artist("Fugazi")
    assert not jerrybase.is_family_artist("")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest packages/llama/tests/test_jerrybase.py -k "ampersand or family" -q`
Expected: FAIL — `test_artist_key_folds_ampersand_to_and` asserts `deadandcompany` but gets `deadcompany`; `is_family_artist` does not exist (`AttributeError`).

- [ ] **Step 3: Fold `&` in `artist_key`**

Replace `packages/llama/src/llama/jerrybase.py:30-34` with:

```python
def artist_key(artist: str) -> str:
    """Lowercased alphanumerics only, so "Grateful Dead" and the CSV's
    "GratefulDead" collapse to the same key without an alias table.

    "&" folds to "and" first: the CSV spells them out ("DeadAndCompany",
    "PhilLeshAndFriends"), so stripping the character instead of folding it
    denied those two acts every piece of jerrybase evidence."""
    folded = artist.replace("&", " and ")
    return "".join(c for c in folded.lower() if c.isalnum())
```

- [ ] **Step 4: Add the family predicate**

Insert after `lookup` (after line 131) in `packages/llama/src/llama/jerrybase.py`:

```python
# Family acts the vendored dataset has no rows for. Dead vocabulary still
# applies to them: vocabulary transfers across the family, event evidence
# does not.
_EXTRA_FAMILY = frozenset({"joerussosalmostdead", "jrad"})

_FAMILY: frozenset[str] | None = None


def is_family_artist(artist: str) -> bool:
    """True when `artist` belongs to the Garcia universe, and so may use the
    Dead shorthand vocabulary (`songs.GD_SHORTHAND`).

    Membership is derived from the vendored CSV's own artist keys — all ten of
    them are Garcia-universe (Grateful Dead, Dark Star Orchestra, Ratdog, Phil
    Lesh & Friends, Jerry Garcia Band, Furthur, Bob Weir, Dead & Company, The
    Dead, The Other Ones) — plus `_EXTRA_FAMILY`. Deriving rather than
    hardcoding means the nine side/tribute acts need no maintained list.

    Deliberately independent of `[jerrybase] enabled`: turning off *event
    evidence* must never silently turn off *vocabulary*."""
    global _FAMILY
    if _FAMILY is None:
        _FAMILY = frozenset({k for k, _ in _load()}) | _EXTRA_FAMILY
    return bool(artist) and artist_key(artist) in _FAMILY
```

Note for later tasks and tests: `_FAMILY` is cached on first use, like `_INDEX`.
A test that stubs the index must also reset `jerrybase._FAMILY = None`, or it
will read whichever index was loaded first.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest packages/llama/tests/test_jerrybase.py -q`
Expected: PASS, no regressions in the file.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: 1201 passed (+2 new = 1203), 7 deselected. Newly-keying artists may change *nothing* in tests, since no fixture uses Dead & Company; if any test fails, it is a real regression, not expected drift.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/jerrybase.py packages/llama/tests/test_jerrybase.py
git commit -m "fix(jerrybase): fold & in artist_key, add is_family_artist"
```

---

### Task 2: The gated shorthand table and the blocklist

Adds the Dead vocabulary as data, threads an `aliases` parameter through the fuzzy helpers, and blocks the one known cross-song false positive the subphrase rule produces.

**Files:**
- Modify: `packages/llama/src/llama/songs.py` (append `GD_SHORTHAND` after `DEFAULT_ALIASES`)
- Modify: `packages/llama/src/llama/structure.py:41-60` (`fuzzy_norm_title`, `title_components`), `:70-87` (`fuzzy_title_eq`)
- Test: `packages/llama/tests/test_structure.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `songs.GD_SHORTHAND: dict[str, str]`
  - `structure.fuzzy_norm_title(title: str, aliases: dict[str, str] | None = None) -> str`
  - `structure.title_components(title: str, aliases: dict[str, str] | None = None) -> list[str]`
  - `structure.fuzzy_title_eq(a: str, b: str) -> bool` (signature unchanged; behavior gains the blocklist)

  Tasks 4, 5 and 6 rely on these exact signatures. `aliases` is keyword-optional everywhere so existing callers keep working untouched.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_structure.py`:

```python
from llama.songs import GD_SHORTHAND
from llama.structure import fuzzy_norm_title, fuzzy_title_eq, title_components


def test_shorthand_expands_only_when_aliases_passed():
    assert fuzzy_norm_title("Scarlet") == "scarlet"
    assert fuzzy_norm_title("Scarlet", GD_SHORTHAND) == "scarlet begonias"
    assert fuzzy_norm_title("Chinacat", GD_SHORTHAND) == "china cat sunflower"


def test_shorthand_applies_to_each_merged_component():
    assert title_components("Scarlet > Fire", GD_SHORTHAND) == [
        "scarlet begonias", "fire on the mountain"]


def test_shorthand_targets_are_all_canonical_and_two_way_safe():
    # Every value must itself be a full title, never another key: a table that
    # chains would depend on lookup order.
    assert not (set(GD_SHORTHAND.values()) & set(GD_SHORTHAND))


def test_blocklist_stops_the_known_cross_song_subphrase():
    # Two different songs, both in the repertoire; the subphrase rule pairs
    # them on 15 corpus shows.
    assert not fuzzy_title_eq("its all over now", "its all over now baby blue")
    assert not fuzzy_title_eq("its all over now baby blue", "its all over now")
    # ... but the correct shortening must keep working.
    assert fuzzy_title_eq("baby blue", "its all over now baby blue")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest packages/llama/tests/test_structure.py -k "shorthand or blocklist" -q`
Expected: FAIL — `ImportError: cannot import name 'GD_SHORTHAND'`.

- [ ] **Step 3: Add the table**

Append to `packages/llama/src/llama/songs.py`, after `DEFAULT_ALIASES`:

```python
# Dead-canon shorthand: single-word stand-ins and closed-up spellings that
# tapers use constantly. Keys and values are in normalized form, so this table
# is applied AFTER `normalize_song` (which has already applied DEFAULT_ALIASES).
#
# Kept separate from DEFAULT_ALIASES and NOT applied globally: "scarlet",
# "help", "dew", "eyes", "wheel", "saint" and "stephen" are ordinary English
# words, and a Beatles cover titled "Help" on a punk tape must not become "help
# on the way". Callers gate it on `jerrybase.is_family_artist`; the jerrybase
# closer path applies it unconditionally because an event only exists for
# artists in the dataset.
#
# Every value below was checked present in the vendored set_breaks.csv song
# vocabulary. Note the deliberate split of the two "saint" cases: bare "Saint"
# in Dead usage is the "Sailor > Saint" pairing, while St. Stephen is written
# out (DEFAULT_ALIASES already maps "st stephen").
GD_SHORTHAND: dict[str, str] = {
    "scarlet": "scarlet begonias",
    "fire": "fire on the mountain",
    "help": "help on the way",
    "slip": "slipknot",
    "frank": "franklins tower",
    "estimated": "estimated prophet",
    "eyes": "eyes of the world",
    "sailor": "lost sailor",
    "saint": "saint of circumstance",
    "dew": "morning dew",
    "wheel": "the wheel",
    "stephen": "saint stephen",
    "china": "china cat sunflower",
    "chinacat": "china cat sunflower",
}
```

- [ ] **Step 4: Thread `aliases` through the fuzzy helpers**

In `packages/llama/src/llama/structure.py`, replace `fuzzy_norm_title` (lines 41-50) and `title_components` (lines 53-60) with:

```python
def fuzzy_norm_title(title: str, aliases: dict[str, str] | None = None) -> str:
    """`norm_title` with "&" folded to "and" first, then an optional
    caller-supplied shorthand table applied to the result.

    `normalize_song`'s punctuation strip turns "&" into whitespace, so
    "Me & My Uncle" and "Me and My Uncle" normalize differently. Folding
    beforehand collapses them. Deliberately kept out of `normalize_song`
    itself: folding there would also change grouping, vet_research, brief and
    setlist.fm artist matching, none of which was measured.

    `aliases` is `songs.GD_SHORTHAND` for Garcia-universe artists and empty for
    everyone else — see that table's comment for why it cannot be global."""
    norm = norm_title(title.replace("&", " and "))
    return (aliases or {}).get(norm, norm)


def title_components(title: str, aliases: dict[str, str] | None = None) -> list[str]:
    """Normalized components of a possibly-merged track title, in order.

    A trailing separator yields no empty component, so a dangling ">" stays a
    segue marker rather than becoming a phantom song."""
    parts = [p.strip() for p in _SEGUE_SEP.split(title) if p.strip()]
    return [fuzzy_norm_title(p, aliases) for p in parts] or [fuzzy_norm_title(title, aliases)]
```

- [ ] **Step 5: Add the blocklist**

In `packages/llama/src/llama/structure.py`, insert before `fuzzy_title_eq` (before line 70):

```python
# Normalized title pairs the subphrase rule must never equate. Both members of
# this pair are real songs in the repertoire, and the rule pairs them on 15
# corpus shows; the correct shortening ("... Baby Blue" -> "Baby Blue") is
# unaffected because it is not listed here.
_NEVER_EQUAL = frozenset({
    frozenset({"its all over now", "its all over now baby blue"}),
})
```

Then change the body of `fuzzy_title_eq` (line 87) from:

```python
    return a == b or _is_subphrase(a, b) or _is_subphrase(b, a)
```

to:

```python
    if a == b:
        return True
    if frozenset({a, b}) in _NEVER_EQUAL:
        return False
    return _is_subphrase(a, b) or _is_subphrase(b, a)
```

- [ ] **Step 6: Update the `fuzzy_title_eq` docstring's validation note**

In the same docstring (lines 82-86), replace the closing sentence:

```
    A later phase's alias table
    will widen this surface, so re-validate then.
```

with:

```
    `GD_SHORTHAND` widens that surface; the re-validation is Task 7 of the
    phase-2 plan, and `_NEVER_EQUAL` above is where any cross-song pair it
    turns up must be recorded.
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest packages/llama/tests/test_structure.py -q`
Expected: PASS, including the pre-existing tests (the `aliases` parameter defaults to `None`, so nothing else changes).

- [ ] **Step 8: Run the full suite**

Run: `pytest -q`
Expected: 1203 + 4 new = 1207 passed, 7 deselected.

- [ ] **Step 9: Commit**

```bash
git add packages/llama/src/llama/songs.py packages/llama/src/llama/structure.py packages/llama/tests/test_structure.py
git commit -m "feat: gated Dead shorthand table and fuzzy-match blocklist"
```

---

### Task 3: Drop trailing parentheticals per component

Run-matching is **not** self-guarding, contrary to an earlier assumption: `Lazy Lightning* -> (Cripe)` was observed forming a merge run whose second component matched a real setlist item. Dropping a component that is nothing but a parenthetical turns that title back into a single-component match.

**Files:**
- Modify: `packages/llama/src/llama/structure.py` (`title_components`, and a new `_TRAILING_PAREN` beside `_SEGUE_SEP` at line 38)
- Test: `packages/llama/tests/test_structure.py`

**Interfaces:**
- Consumes: `title_components(title, aliases=None)` from Task 2.
- Produces: same signature; components with a trailing `(...)` are stripped, and components that reduce to nothing are dropped.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_structure.py`:

```python
def test_components_drop_credit_only_parentheticals():
    # Seen live: "(Cripe)", "(SBD)", "(Tape Flip)", "(White Strat)".
    assert title_components("Lazy Lightning* -> (Cripe)") == ["lazy lightning"]
    assert title_components("New Orleans > (w/ Rick Danko)") == ["new orleans"]


def test_components_strip_trailing_subtitle_parenthetical():
    assert title_components("You Ain't Woman Enough (to Take My Man)") == [
        "you aint woman enough"]


def test_components_keep_a_real_second_song():
    assert title_components("China Cat Sunflower > I Know You Rider") == [
        "china cat sunflower", "i know you rider"]


def test_components_of_an_all_parenthetical_title_fall_back_to_the_whole_title():
    assert title_components("(Tape Flip)") == ["tape flip"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest packages/llama/tests/test_structure.py -k components -q`
Expected: FAIL — `title_components("Lazy Lightning* -> (Cripe)")` returns `['lazy lightning', 'cripe']`.

- [ ] **Step 3: Implement**

In `packages/llama/src/llama/structure.py`, add beside `_SEGUE_SEP` (after line 38):

```python
# A trailing parenthetical on a component is a taper's credit or lineage note
# ("(Cripe)", "(SBD)", "(Tape Flip)", "(w/ Rick Danko)"), or a canonical
# subtitle the taper kept ("(to Take My Man)"). Neither is a song, and a
# credit-only component would otherwise form a spurious merge run.
_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")
```

Replace `title_components`'s body with:

```python
def title_components(title: str, aliases: dict[str, str] | None = None) -> list[str]:
    """Normalized components of a possibly-merged track title, in order.

    A trailing separator yields no empty component, so a dangling ">" stays a
    segue marker rather than becoming a phantom song. A component that is
    nothing but a parenthetical credit is dropped entirely, which is what stops
    "Lazy Lightning -> (Cripe)" forming a two-song run. When every component
    drops out, the whole title is used, so a track genuinely titled
    "(Tape Flip)" still normalizes to something."""
    parts: list[str] = []
    for raw in _SEGUE_SEP.split(title):
        stripped = _TRAILING_PAREN.sub("", raw.strip()).strip()
        if stripped:
            parts.append(fuzzy_norm_title(stripped, aliases))
    return [p for p in parts if p] or [fuzzy_norm_title(title, aliases)]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest packages/llama/tests/test_structure.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: 1207 + 4 new = 1211 passed, 7 deselected. `test_jerrybase.py` exercises `title_components` through closer matching — if a jerrybase test fails here, check whether its fixture closer ends in a parenthetical before assuming the rule is wrong.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/tests/test_structure.py
git commit -m "fix: drop credit-only parentheticals from merged title components"
```

---

### Task 4: `align()` matches fuzzily

Replaces exact-equality matching with exact-first-then-subphrase across the lookahead window, normalizing **both** sides at compare time. This is the change that fixes gd 1973-08-01's `&`/subtitle misses.

**Files:**
- Modify: `packages/llama/src/llama/structure.py:227-260` (`align`)
- Test: `packages/llama/tests/test_structure.py`

**Interfaces:**
- Consumes: `fuzzy_norm_title(title, aliases)`, `fuzzy_title_eq(a, b)` from Tasks 2-3.
- Produces: `align(tracks, canonical, lookahead=3, aliases=None) -> AlignResult`, and a module-private `_window_match(norms, lo, hi, nt) -> int | None`. Task 5 extends `align`; Task 6 calls it with `aliases=`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_structure.py`:

```python
def test_align_folds_ampersand_on_both_sides():
    c = canon(("1", "Me and My Uncle", False), ("1", "Big River", False))
    r = align([tr(1, "Me & My Uncle"), tr(2, "Big River")], c)
    assert r.sets == ["1", "1"]
    assert r.matched == [True, True]


def test_align_matches_a_dropped_subtitle():
    c = canon(("1", "Mississippi Half Step Uptown Toodeloo", False),
              ("2", "Big River", False))
    r = align([tr(1, "Mississippi Half Step"), tr(2, "Big River")], c)
    assert r.sets == ["1", "2"]
    assert r.matched == [True, True]


def test_align_prefers_an_exact_match_over_a_subphrase_in_the_window():
    # "Not Fade Away" IS a subphrase of "Not Fade Away Chant", which sits first
    # in the window. Exact-first must reach past it to the real item; the sets
    # differ so the assertion says which item was actually consumed.
    c = canon(("1", "Not Fade Away Chant", False), ("2", "Not Fade Away", False))
    r = align([tr(1, "Not Fade Away")], c)
    assert r.sets == ["2"]
    assert r.conflicts == ["Not Fade Away Chant"]


def test_align_shorthand_only_with_aliases():
    from llama.songs import GD_SHORTHAND
    c = canon(("2", "Scarlet Begonias", True), ("2", "Fire on the Mountain", False))
    plain = align([tr(1, "Scarlet"), tr(2, "Fire")], c)
    assert plain.matched == [False, False]
    gated = align([tr(1, "Scarlet"), tr(2, "Fire")], c, aliases=GD_SHORTHAND)
    assert gated.matched == [True, True]
    assert gated.sets == ["2", "2"]


def test_align_does_not_pair_the_blocklisted_pair():
    c = canon(("1", "It's All Over Now, Baby Blue", False))
    r = align([tr(1, "It's All Over Now")], c)
    assert r.matched == [False]
    assert r.conflicts == ["It's All Over Now, Baby Blue"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest packages/llama/tests/test_structure.py -k align -q`
Expected: FAIL — the `&`, subtitle and shorthand cases all report `matched == [False, ...]`.

- [ ] **Step 3: Implement**

Replace `align` (lines 227-260) in `packages/llama/src/llama/structure.py` with:

```python
def _window_match(norms: list[str], lo: int, hi: int, nt: str) -> int | None:
    """Index of the first item in `norms[lo:hi]` matching `nt`, exact matches
    considered across the whole window before any fuzzy one.

    Exact-first is load-bearing, not a micro-optimisation: with a plain
    left-to-right scan a track called "Not Fade Away" would take an earlier
    "Not Fade Away Chant" item by subphrase and leave the real item stranded."""
    for k in range(lo, hi):
        if norms[k] == nt:
            return k
    for k in range(lo, hi):
        if fuzzy_title_eq(nt, norms[k]):
            return k
    return None


def align(tracks: list["Track"], canonical: ParsedSetlist, lookahead: int = 3,
          aliases: dict[str, str] | None = None) -> "AlignResult":
    """Map canonical set/segue structure onto tracks, in recording order.

    Two-pointer with lookahead: a track matches the next canonical item within
    `lookahead` positions, so repeated songs pair with the right occurrence and
    merged/split tracks skip over the gap.

    Titles are normalized on BOTH sides at compare time (`fuzzy_norm_title`)
    rather than read from the precomputed `SetlistItem.normalized`, because
    taper tags and canonical names disagree on "&", on dropped subtitles, and —
    for Garcia-universe artists, via `aliases` — on single-word shorthand. An
    unmatched track inherits the previous track's set, so every miss drags the
    songs after it into the wrong set; that is why matching is worth this."""
    items = canonical.items
    norms = [fuzzy_norm_title(it.title, aliases) for it in items]
    sets: list[str] = []
    segues: list[bool] = []
    matched: list[bool] = []
    matched_idx: set[int] = set()
    j = 0
    for t in tracks:
        nt = fuzzy_norm_title(t.title, aliases)
        hit = _window_match(norms, j, min(j + 1 + lookahead, len(items)), nt)
        if hit is None:
            sets.append(sets[-1] if sets else "1")
            segues.append(False)
            matched.append(False)
        else:
            sets.append(items[hit].set)
            segues.append(items[hit].segue)
            matched.append(True)
            matched_idx.add(hit)
            j = hit + 1
    coverage = _songish_coverage(tracks, matched)
    conflicts = [it.title for k, it in enumerate(items) if k not in matched_idx]
    return AlignResult(sets=sets, segues=segues, matched=matched,
                       coverage=coverage, conflicts=conflicts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest packages/llama/tests/test_structure.py -q`
Expected: PASS, including every pre-existing `test_align_*`.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: 1211 + 5 new = 1216 passed, 7 deselected.

If `test_stage_gather.py` or `test_pipeline.py` fails here, read the failure before changing anything: coverage rising on a fixture is *expected* (that is the point of the task), but a fixture whose *set labels* changed needs checking against the fixture's own setlist before the new value is blessed.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/tests/test_structure.py
git commit -m "feat: fuzzy title matching in align()"
```

---

### Task 5: Merged-track run matching, and flagging runs that span a set break

A merged file (`China Cat Sunflower > I Know You Rider`) carries several canonical items and can equal none of them. Matching it as a consecutive *run* both matches the track and advances the pointer past every item it consumed.

**Files:**
- Modify: `packages/llama/src/llama/models.py:120-125` (`AlignResult`)
- Modify: `packages/llama/src/llama/structure.py` (`align`, plus a new `_merge_run`)
- Test: `packages/llama/tests/test_structure.py`

**Interfaces:**
- Consumes: `title_components(title, aliases)` from Task 3, `align` from Task 4.
- Produces: `AlignResult.merge_conflicts: list[int]` (1-based track numbers, from `Track.index`). Task 6 turns it into a review flag.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_structure.py`:

```python
def test_align_matches_a_merged_track_as_a_run():
    c = canon(("2", "China Cat Sunflower", True), ("2", "I Know You Rider", False),
              ("2", "Big River", False))
    r = align([tr(1, "China Cat Sunflower > I Know You Rider"), tr(2, "Big River")], c)
    assert r.sets == ["2", "2"]
    assert r.matched == [True, True]
    # Both consumed items count as matched, so neither is a conflict.
    assert r.conflicts == []
    assert r.coverage == 1.0
    assert r.merge_conflicts == []


def test_merged_run_takes_the_segue_that_follows_the_last_component():
    c = canon(("2", "Scarlet Begonias", True), ("2", "Fire on the Mountain", True),
              ("2", "Estimated Prophet", False))
    r = align([tr(1, "Scarlet Begonias > Fire on the Mountain"),
               tr(2, "Estimated Prophet")], c)
    assert r.segues == [True, False]


def test_merged_run_spanning_a_set_break_is_flagged():
    # Physically impossible: one continuous performance cannot straddle a
    # break, so this is evidence the parse is wrong.
    c = canon(("1", "Playing in the Band", True), ("2", "Uncle John's Band", False))
    r = align([tr(1, "Playing in the Band > Uncle John's Band")], c)
    assert r.sets == ["1"]          # first component's set
    assert r.merge_conflicts == [1]  # 1-based track number


def test_merged_run_needs_every_component_to_match():
    # "patch" is a transfer note, not a song: the run must not form, and the
    # track falls back to a single-title match on the whole string.
    c = canon(("2", "Space", False), ("2", "The Other One", False))
    r = align([tr(1, "Space > patch"), tr(2, "The Other One")], c)
    assert r.matched == [False, True]
    assert r.merge_conflicts == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest packages/llama/tests/test_structure.py -k merge -q`
Expected: FAIL — `AlignResult` has no attribute `merge_conflicts`, and the merged track reports `matched == [False, ...]`.

- [ ] **Step 3: Add the model field**

In `packages/llama/src/llama/models.py`, replace lines 120-125 with:

```python
class AlignResult(BaseModel):
    sets: list[str]
    segues: list[bool]
    matched: list[bool]
    coverage: float
    conflicts: list[str] = Field(default_factory=list)
    # 1-based numbers of merged tracks whose components matched items in
    # different sets. Physically impossible, so it is evidence the parse is
    # wrong: gather turns it into a review flag.
    merge_conflicts: list[int] = Field(default_factory=list)
```

- [ ] **Step 4: Implement run matching**

In `packages/llama/src/llama/structure.py`, add before `_window_match`:

```python
def _merge_run(norms: list[str], lo: int, hi: int, comps: list[str]) -> int | None:
    """Start index of a consecutive run in `norms` matching every component of
    a merged track, searching only from `lo` up to (but not including) `hi`.

    Requiring *all* components to match is the guard against taper notes that
    look like a second song ("Space > patch", "New Orleans > (w/ Rick Danko)").
    Task 3's parenthetical drop handles the credit case; this handles the rest,
    by declining the run and letting the track fall back to a single match."""
    n = len(comps)
    for k in range(lo, hi):
        if k + n <= len(norms) and all(
                fuzzy_title_eq(c, norms[k + m]) for m, c in enumerate(comps)):
            return k
    return None
```

Then, inside `align`'s loop, replace the body from `nt = fuzzy_norm_title(...)` down to the `else:` branch with:

```python
    for t in tracks:
        hi = min(j + 1 + lookahead, len(items))
        comps = title_components(t.title, aliases)
        run = _merge_run(norms, j, hi, comps) if len(comps) > 1 else None
        if run is not None:
            n = len(comps)
            sets.append(items[run].set)
            # The segue that matters is the one after the LAST component: it
            # describes what follows this file, not what happens inside it.
            segues.append(items[run + n - 1].segue)
            matched.append(True)
            matched_idx.update(range(run, run + n))
            if len({items[run + m].set for m in range(n)}) > 1:
                merge_conflicts.append(t.index)
            j = run + n
            continue
        nt = fuzzy_norm_title(t.title, aliases)
        hit = _window_match(norms, j, hi, nt)
        if hit is None:
            sets.append(sets[-1] if sets else "1")
            segues.append(False)
            matched.append(False)
        else:
            sets.append(items[hit].set)
            segues.append(items[hit].segue)
            matched.append(True)
            matched_idx.add(hit)
            j = hit + 1
```

Declare the accumulator alongside the others (after `matched_idx: set[int] = set()`):

```python
    merge_conflicts: list[int] = []
```

and pass it through the return:

```python
    return AlignResult(sets=sets, segues=segues, matched=matched,
                       coverage=coverage, conflicts=conflicts,
                       merge_conflicts=merge_conflicts)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest packages/llama/tests/test_structure.py -q`
Expected: PASS. Pay attention to `test_align_skips_merged_canonical_item_via_lookahead` and `test_align_repeated_songs_map_in_order`: both use trailing `>` markers, which yield a single component and so must still take the single-match path.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: 1216 + 4 new = 1220 passed, 7 deselected.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/models.py packages/llama/src/llama/structure.py packages/llama/tests/test_structure.py
git commit -m "feat: match merged tracks as runs, flag runs spanning a set break"
```

---

### Task 6: Wire the vocabulary and the flag into `gather` and the closer path

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py:212` (the `align` call) and `:258` (where `coverage, conflicts` are read)
- Modify: `packages/llama/src/llama/jerrybase.py:134-148` (`_closer_candidates`)
- Test: `packages/llama/tests/test_stage_gather.py`, `packages/llama/tests/test_jerrybase.py`

**Interfaces:**
- Consumes: `jerrybase.is_family_artist` (Task 1), `songs.GD_SHORTHAND` (Task 2), `AlignResult.merge_conflicts` (Task 5).
- Produces: no new public API. A new review flag string: `merged track(s) N span a set break`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_jerrybase.py`:

```python
def test_closer_matching_uses_dead_shorthand():
    # The closer path is inherently family-gated (an event only exists for
    # artists in the dataset), so the table applies with no caller opt-in.
    tracks = [_track(1, "Truckin'"), _track(2, "Scarlet"), _track(3, "Sugaree")]
    assert jerrybase._closer_candidates(tracks, "Scarlet Begonias") == [1]
```

Use whatever `Track`-building helper `test_jerrybase.py` already defines; if it has none, build one locally:

```python
def _track(i, title, set_="1"):
    return Track(index=i, set=set_, title=title, filename=f"t{i}.mp3",
                 duration_sec=300.0, title_source="tags")
```

Append to `packages/llama/tests/test_stage_gather.py` (follow the file's existing fixture/helper conventions for building a gather run):

```python
def test_gather_flags_a_merged_track_spanning_a_set_break(...):
    """A merged track whose components land in different sets must hold the
    show rather than ship: the parse is provably wrong."""
    # Arrange a run whose canonical items straddle a break, run gather, then:
    assert show.needs_review
    assert any("span a set break" in f for f in show.review_flags)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest packages/llama/tests/test_jerrybase.py -k shorthand packages/llama/tests/test_stage_gather.py -k span -q`
Expected: FAIL — `_closer_candidates` returns `[]` for the shorthand track; gather raises no flag.

- [ ] **Step 3: Apply the table in the closer path**

In `packages/llama/src/llama/jerrybase.py`, add to the imports (line 15 area):

```python
from llama.songs import GD_SHORTHAND
```

and in `_closer_candidates` (lines 143-148) pass it on every call:

```python
    target = fuzzy_norm_title(closer, GD_SHORTHAND)
    exact = [i for i, t in enumerate(tracks)
             if title_components(t.title, GD_SHORTHAND)[-1] == target]
    if exact:
        return exact
    return [i for i, t in enumerate(tracks)
            if fuzzy_title_eq(title_components(t.title, GD_SHORTHAND)[-1], target)]
```

Extend that function's docstring with:

```
    The Dead shorthand table is applied unconditionally here, with no
    caller-side family gate: a jerrybase event only exists for artists in the
    dataset, so this path is inherently gated already.
```

- [ ] **Step 4: Gate and pass the vocabulary in `gather`**

In `packages/llama/src/llama/stages/gather.py`, add to the imports:

```python
from llama.songs import GD_SHORTHAND
```

and replace line 212:

```python
        result = align(tracks, canonical)
```

with:

```python
        # Single-word Dead shorthand ("Scarlet", "Dew", "Help") is only safe
        # inside the Garcia universe — they are ordinary English words
        # elsewhere. Non-family shows get an empty table, which makes the
        # vocabulary a provable no-op on the non-Dead corpus.
        aliases = GD_SHORTHAND if jerrybase.is_family_artist(artist) else {}
        result = align(tracks, canonical, aliases=aliases)
```

- [ ] **Step 5: Raise the review flag**

In the same file, replace line 258:

```python
        coverage, conflicts = result.coverage, result.conflicts
```

with:

```python
        coverage, conflicts = result.coverage, result.conflicts
        if result.merge_conflicts:
            nums = ", ".join(str(n) for n in result.merge_conflicts)
            flags.append(f"merged track(s) {nums} span a set break")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest packages/llama/tests/test_jerrybase.py packages/llama/tests/test_stage_gather.py -q`
Expected: PASS.

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: 1220 + 2 new = 1222 passed, 7 deselected.

- [ ] **Step 8: Verify the original bug against the real library**

Run:

```bash
llama show gratefuldead-1973-08-01 --tracks
```

Expected: set breaks `[11, 20]`, and **neither** `'Casey Jones' is not at a set break` nor `'Sugar Magnolia' is not at a set break` in the flags. This show is the reason the whole two-phase effort exists; if it regressed, stop and diagnose before continuing.

If the local library has no such show, skip this step and say so explicitly in the task report rather than silently omitting it.

- [ ] **Step 9: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/src/llama/jerrybase.py packages/llama/tests/
git commit -m "feat(gather): gate Dead vocabulary on artist family, flag spanning merges"
```

---

### Task 7: Re-score both corpora and re-validate the two-word floor

Measurement only — no production code changes. The spec's acceptance criteria are not met until this task's numbers exist and have been read.

**Files:**
- No repo files. Uses the external analysis repo at `/Users/shawn/projects/llama-setlist-analysis/` (`corpus.jsonl`, `corpus-nondead.jsonl`, `score.py`, `verify_impl.py`).
- Modify: `docs/superpowers/specs/2026-08-01-fuzzy-title-matching-design.md` (record the measured results at the end)

**Interfaces:**
- Consumes: everything from Tasks 1-6.
- Produces: measured figures for the spec and for the next phase's design.

- [ ] **Step 1: Re-score the real implementation against the Dead corpus**

```bash
cd /Users/shawn/projects/llama-setlist-analysis
python3 verify_impl.py --src=/Users/shawn/projects/llama/packages/llama/src corpus.jsonl
```

**Critical:** `score.py:9` hardcodes the *main* checkout's `src` path. If working in a worktree, `--src` must point at the worktree, or the run silently measures main and reports a convincing no-change.

Expected: anchors at or above the phase-1 baseline of **530/756**, and **0 disagreements** where both old and new rules anchor. A drop in anchors, or any disagreement, is a stop-and-diagnose result — not something to explain away.

- [ ] **Step 2: Re-score against the non-Dead corpus**

```bash
python3 verify_impl.py --src=/Users/shawn/projects/llama/packages/llama/src corpus-nondead.jsonl
python3 score.py corpus-nondead.jsonl
```

This is the anti-overfit guard: every rule in this phase was derived from Dead tapes. Unlike phase 1, this will **not** be a no-op, because `align()` changed. Jerrybase figures must stay 0/0 (no rows for these artists).

Read the results — do not assume them. Record the match-rate change and any show whose set breaks changed.

- [ ] **Step 3: Confirm the shorthand gate is a no-op off-family**

```bash
python3 - <<'PY'
import sys
sys.path.insert(0, '/Users/shawn/projects/llama/packages/llama/src')
from llama import jerrybase
import json, collections
seen = collections.Counter()
for line in open('corpus-nondead.jsonl'):
    row = json.loads(line)
    seen[jerrybase.is_family_artist(row.get('artist') or row.get('collection') or '')] += 1
print(seen)  # expect every row False
PY
```

Expected: `Counter({False: 874})` — the gate demonstrated, not asserted. Any `True` row means a non-Dead artist is receiving Dead vocabulary; investigate before proceeding.

- [ ] **Step 4: Re-validate the two-word floor with the table applied**

```bash
python3 - <<'PY'
import sys, csv, itertools, collections
sys.path.insert(0, '/Users/shawn/projects/llama/packages/llama/src')
from llama.songs import GD_SHORTHAND
from llama.structure import fuzzy_norm_title, fuzzy_title_eq
rows = list(csv.DictReader(open(
    '/Users/shawn/projects/llama/packages/llama/src/llama/data/set_breaks.csv')))
closers = sorted({fuzzy_norm_title(r['song'], GD_SHORTHAND) for r in rows if r.get('song')})
pairs = [(a, b) for a, b in itertools.combinations(closers, 2) if fuzzy_title_eq(a, b)]
print(len(closers), 'distinct closers;', len(pairs), 'fuzzy-equal pairs')
for a, b in pairs:
    print(' ', a, '|', b)
# Any pair that is genuinely two different songs must be added to
# structure._NEVER_EQUAL, and this check re-run.
PY
```

Phase 1's result on the pre-table vocabulary was 19 pairs: 18 one-song-two-spellings, 1 cross-song (`its all over now` / `... baby blue`, now blocklisted), and no event carrying both. Read every new pair the table introduces and judge it individually. Any genuine cross-song pair goes into `_NEVER_EQUAL` with a test, and this step re-runs.

- [ ] **Step 5: Record the results in the spec**

Append a `## Measured results (phase 2)` section to
`docs/superpowers/specs/2026-08-01-fuzzy-title-matching-design.md` with:
the Dead-corpus anchor count and disagreement count; the non-Dead corpus
match-rate change and break-change count; the family-gate counter from Step 3;
the fuzzy-pair count from Step 4 and any additions to `_NEVER_EQUAL`; and the
final `pytest -q` figure.

State plainly anything that came out worse than expected. The next phase's
design is built on these numbers, so a flattering summary is worse than no
summary.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-08-01-fuzzy-title-matching-design.md
git commit -m "docs: record phase-2 measured results"
```

---

## Self-review notes

Spec coverage checked section by section: layering (Task 4), matching order (Tasks 4-5), trailing parentheticals (Task 3), vocabulary + gate (Tasks 1-2, wired in 6), `artist_key` item 8 (Task 1), closer path gets the table (Task 6), blocklist (Task 2), merge span flag (Tasks 5-6), all five acceptance criteria (Task 7, plus the gd 1973-08-01 check in Task 6 Step 8).

Signatures are consistent across tasks: `fuzzy_norm_title(title, aliases=None)`, `title_components(title, aliases=None)`, `fuzzy_title_eq(a, b)`, `_window_match(norms, lo, hi, nt)`, `_merge_run(norms, lo, hi, comps)`, `align(tracks, canonical, lookahead=3, aliases=None)`, `is_family_artist(artist)`, `AlignResult.merge_conflicts: list[int]`.

Test-count expectations (1203 → 1207 → 1211 → 1216 → 1220 → 1222) assume no test is added beyond those written here; treat them as a guide, and the *absence of failures* as the real gate.
