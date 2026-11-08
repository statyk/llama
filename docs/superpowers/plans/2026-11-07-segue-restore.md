# gather segue restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An add-only segue restore pass at the end of gather's structure decision. It puts back
segues setlist.fm marks (E3, every path but `override`) and segues the deterministic decision
would have shipped where the LLM alignment won (E2). Plus the offline measurement that proves it.

**Architecture:** Two pure helpers in `stages/gather.py` (`setlistfm_marks`, `restore_segues`) and
one extracted guard (`_may_add_segue`). `CanonicalBuild` gains one field carrying the marked
setlist.fm parse. `compute_gather` calls `restore_segues` once, after `donor_segues` and the final
set decision, and writes one `op_notes` line per evidence kind. A measurement script in `scripts/`
drives `replay.compute_legs` offline.

**Tech Stack:** Python 3, pydantic models (`llama.models`), pytest, offline fixtures.

**Spec:** `docs/superpowers/specs/2026-11-07-segue-restore-design.md` (read it; this plan argues
from it).

## Global Constraints

- The worktree is `.claude/worktrees/segue-restore` (branch `segue-restore`). Give it its own venv:
  `python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`.
  Run tests with `./.venv/bin/pytest` from the worktree. Check
  `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside the worktree.
- The rule only ever sets `segue` False → True. It never clears a segue. It never changes titles,
  sets, `matched`, coverage, conflicts, flags, or the track list.
- It does not run when `alignment == "override"`.
- A track whose title already ends in an arrow (`junk.TRAILING_ARROW.search(title)`) is never
  touched: it already renders as a segue.
- E3 marks a setlist.fm song when `junk.TRAILING_ARROW.search(info)`, i.e. its `info` **ends** in an
  arrow. `> 'Bridgeless' reprise` is not a mark.
- E3 is skipped on a track the segue donor's own `align()` matches with no mark.
- No new constants or thresholds. Reuse `TRAILING_ARROW`, `_leads_with_filler` and the extracted
  `may_add` guard unchanged.
- `from_setlistfm`, `blend_segues`, canonical ranking and the `align_structure` prompt are unchanged.
- The note goes to `op_notes` (notes.json), never to the structure `notes`/`conflicts`. It is ONE
  line: `segues restored: track 18 'China Cat Sunflower' (setlist.fm); track 4 'X' (the deterministic alignment)`.
- No captured fixture and no test fake carries setlist.fm `info` today, so E3 cannot move an existing
  test expectation; only E2 can (LLM-won fake-provider tests, possibly in `test_replay`,
  `test_reapply` or the adjudicator tests).
- `pytest -q` stays offline and deterministic.

## Review Focus

1. **Existing fixtures whose shipped segues change.** E3 is on every path, so a gather test using a
   setlist.fm fixture whose songs carry `info: ">"` may now ship more segues. Expected: each such
   change is listed in the task report with the setlist.fm `info` and the track that caused it. No
   expectation is edited silently. (Task 2, Step 6.)
2. **A repeated title** (`Turbin`, `Crazy Mona`, `Truckin'` twice). E3's own `align()` must pair the
   right occurrence. The donor-said-no skip must keep FW4 item 2's removals. (Task 2, test
   `test_restore_e3_skips_where_the_donor_said_no`.)
3. **The last track of a set carrying a setlist.fm mark** (setlist.fm writes `>` on a set-two closer
   that segues into the encore only on paper). It must not get a segue across the set break.
   (Task 2, test `test_restore_never_crosses_a_set_break`.)
4. **A setlist.fm response with `tape: true` songs or under 5 kept songs.** Tape songs are dropped,
   as `from_setlistfm` drops them; a stub gives no E3. (Task 1 tests.)
5. **The LLM-won path where the LLM's set labels differ from step 1's.** (Anchoring and the taper
   step both skip the LLM branch, so on that path the final sets are the LLM's.) E2 must use the
   final shipped sets for its guard, not step 1's. (Task 2, test `test_gather_llm_won_restores_the_deterministic_segue`.)

---

### Task 1: setlist.fm marks, the extracted guard, and the `CanonicalBuild` field

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (`CanonicalBuild` ~830, `build_canonical` ~943,
  `donor_segues` ~1009)
- Test: `packages/llama/tests/test_stage_gather.py` (next to the FW4 tests, ~4960)

**Interfaces:**
- Produces:
  - `setlistfm_marks(raw: dict) -> ParsedSetlist | None`: the same items, titles, `normalized` and
    set labels as `structure.from_setlistfm(raw)`, with
    `segue = bool(TRAILING_ARROW.search((song.get("info") or "").strip()))`. Returns None exactly
    when `from_setlistfm` does (under 5 items).
  - `_may_add_segue(tracks: list[Track], shipped_sets: list[str], k: int) -> bool`: `donor_segues`'
    current `may_add` closure, moved to module level, behaviour unchanged. `donor_segues` calls it.
  - `CanonicalBuild.setlistfm_marked: ParsedSetlist | None = None`. It is set in `build_canonical` to
    `clean(setlistfm_marks(raw))` when setlist.fm returned a setlist that `setlistfm_marks` accepts,
    whichever parse won the canonical; otherwise None. `clean` is `build_canonical`'s own inner
    function. Nothing but Task 2 reads it.

- [ ] **Step 1: Write the failing tests**

```python
def test_setlistfm_marks_reads_trailing_arrows_in_info():
    from llama.stages.gather import setlistfm_marks
    raw = {"sets": {"set": [
        {"song": [{"name": "China Cat Sunflower", "info": ">"},
                  {"name": "I Know You Rider", "info": "->"},
                  {"name": "Row Jimmy", "info": "John Mayer on lead vocals) (>"},
                  {"name": "In the Kitchen", "info": "> 'Bridgeless' reprise"},
                  {"name": "Tape Song", "tape": True, "info": ">"},
                  {"name": "Morning Dew"}]},
        {"encore": 1, "song": [{"name": "Werewolves of London", "info": ">"}]}]}}
    p = setlistfm_marks(raw)
    assert [(i.title, i.set, i.segue) for i in p.items] == [
        ("China Cat Sunflower", "1", True), ("I Know You Rider", "1", True),
        ("Row Jimmy", "1", True), ("In the Kitchen", "1", False),
        ("Morning Dew", "1", False), ("Werewolves of London", "encore", True)]

def test_setlistfm_marks_matches_from_setlistfm_items_and_stub_rule():
    # Same titles/normalized/sets as from_setlistfm; None under 5 items.
    ...  # assert [(i.title, i.normalized, i.set) ...] equal for one fixture; 4-song raw -> None

def test_may_add_segue_extraction_is_behaviour_preserving():
    # Last track False; same set True; different set False unless title ends in ">".
    ...

def test_canonical_build_carries_cleaned_setlistfm_marks():
    # Reuse the FW4 builder (_fw4_build with _DC15_SLFM, plus one setlist.fm item named after
    # the artist): cb.setlistfm_marked is not None, the artist item is dropped (clean() ran),
    # and a build with no setlist.fm client gives None.
    ...
```

Fill the `...` bodies with the assertions named in each comment, using the existing FW4 helpers
(`_fw4_build`, `_DC15_SLFM`, `StubIA`, `make_candidate`). Give `_FakeSetlistFM`
(test_stage_gather.py ~3486) an optional `info: dict[str, str]` per song name, existing callers
unchanged; Task 2 uses it.

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -k "setlistfm_marks or may_add_segue or carries_cleaned" -q`
Expected: FAIL (ImportError / AttributeError).

- [ ] **Step 3: Implement**

Write `setlistfm_marks` as its own walk in gather.py (mirroring `from_setlistfm`'s rules: encore
label, `tape` songs skipped, blank names skipped, None under 5 items); structure.py is not touched. Import `TRAILING_ARROW` from `llama.junk` (gather already imports
from it). In `build_canonical`, keep `raw` from the existing `setlistfm.setlist(...)` call; don't
fetch twice.

- [ ] **Step 4: Run the new tests, then the whole gather and structure suites**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py packages/llama/tests/test_structure.py -q`
Expected: all pass, including every existing `test_fw4_*` test, unchanged.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/tests/test_stage_gather.py
git commit -m "gather: setlist.fm segue marks on CanonicalBuild; may_add extracted"
```

---

### Task 2: `restore_segues` and its wiring into `compute_gather`

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (new function next to `donor_segues`; the
  structure decision ~1836-1995)
- Test: `packages/llama/tests/test_stage_gather.py`

**Interfaces:**
- Consumes: Task 1's `setlistfm_marks`, `_may_add_segue`, `CanonicalBuild.setlistfm_marked`.
- Produces:

```python
def restore_segues(tracks: list[Track], segues: list[bool], *, shipped_sets: list[str],
                   det_segues: list[bool] | None, slfm_marked: ParsedSetlist | None,
                   donor: ParsedSetlist | None,
                   aliases: dict[str, str] | None) -> tuple[list[bool], list[tuple[int, str]]]:
    """Returns (new segues, [(k, evidence), ...] in track order).
    evidence: "the deterministic alignment" (E2) or "setlist.fm" (E3)."""
```

Rule for each `k`, in order. Skip the track if `segues[k]` is already True, or
`TRAILING_ARROW.search(tracks[k].title)`, or `not _may_add_segue(tracks, shipped_sets, k)`, or
`k + 1 < n and _leads_with_filler(tracks[k + 1].title)`. Otherwise:
- **E2:** `det_segues is not None and det_segues[k]` → add, attributed to E2.
- **E3:** else, if `slfm_marked` is not None: `own = align(tracks, slfm_marked, aliases=aliases)`
  (computed once). If `own.matched[k] and own.segues[k]`, and the donor did not say no, add,
  attributed to E3. "The donor said no" means `donor` is not None and
  `d = align(tracks, donor, aliases=aliases)` (once) has `d.matched[k] and not d.segues[k]`.

Wiring in `compute_gather`. On the non-override branch, keep the deterministic `result` (after
anchoring) as `det_result` before the LLM branch can replace it. After the existing
`donor_segues` block and once `final_sets` is known:
- `det_segues = donor_segues(tracks, det_result, cb.segue_donor, family_aliases, shipped_sets=final_sets).segues` when `alignment == "llm"`, else None.
- `segues, restored = restore_segues(tracks, result.segues, shipped_sets=final_sets, det_segues=det_segues, slfm_marked=cb.setlistfm_marked, donor=cb.segue_donor, aliases=family_aliases)`.
- `result = result.model_copy(update={"segues": segues})`.
- If anything was restored, append the ONE line from Global Constraints, entries in track order,
  each `track <n> '<title>' (<evidence>)`. For that, `restore_segues`' second return value is
  `list[tuple[int, str]]` of `(k, evidence)` instead of the dict below; the caller formats it.

The override branch is untouched.

- [ ] **Step 1: Write the failing unit tests** (inline `Track(index=…, set=…, title=…, filename=…,
  title_source=…)`, as the module's tests do, e.g. ~2795)

```python
def test_restore_e3_china_cat():
    # tracks: "China Cat Sunflower", "I Know You Rider", "Morning Dew", all set "2", all False;
    # slfm_marked items: China Cat (segue True), I Know You Rider (False), Morning Dew (False) + 2 more
    # so it is not a stub; donor None, det_segues None.
    # -> segues == [True, False, False]; restored == [(0, "setlist.fm")]

def test_restore_never_removes():           # segues True with no evidence stays True
def test_restore_never_on_the_last_track():
def test_restore_never_crosses_a_set_break():   # shipped_sets "2","encore"; slfm marks k -> not added
def test_restore_skips_a_mark_into_filler():    # next title "Crowd" -> not added
def test_restore_skips_a_title_with_an_arrow(): # "Slipknot! >" -> unchanged, not in restored
def test_restore_e3_skips_where_the_donor_said_no():
    # donor's own align matches k with no mark -> E3 not added; a donor that doesn't match k -> added.
    # Include a repeated title ("Turbin" twice) so the second occurrence is the one tested.
def test_restore_e2_adds_where_the_deterministic_decision_said_segue():
    # det_segues [True, False, False], slfm None -> [True, ...], restored [(0, "the deterministic alignment")]
def test_restore_e2_wins_attribution_over_e3():  # both hold -> listed under E2 only
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -k restore_ -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `restore_segues`**

- [ ] **Step 4: Write the failing gather integration tests**, one per path, through
  `compute_gather` (or the module's existing gather harness: `_fw4_gather`; for taper,
  `_tp_gather`/`_tp_md`/`TP_SONGS` ~3500; for jerrybase, the `jerrybase_enabled=True` tests ~3667),
  with `_FakeSetlistFM`'s `info` on a track the canonical does not mark:

```python
def test_gather_deterministic_restores_a_setlistfm_mark():  # alignment "deterministic"; op_notes line
def test_gather_jerrybase_restores_a_setlistfm_mark():      # alignment "jerrybase"
def test_gather_taper_owned_restores_a_setlistfm_mark():    # alignment "taper"
def test_gather_llm_won_restores_the_deterministic_segue():
    # align_structure stub returns full coverage but segue False on a track the deterministic
    # result + donor_segues marks; alignment "llm" -> segue True and the E2 op_notes line.
    # Make the stub's set labels differ from step 1's on one track (a break moved by one), and
    # assert the guard reads the final (LLM) sets: a mark across the LLM's break is not added.
def test_gather_e3_respects_the_donor():
    # Via _fw4_gather(..., sib_desc=...): the donor's own alignment matches a track with no mark,
    # setlist.fm marks it -> no segue added. Pins that the wiring passes cb.segue_donor.
def test_gather_dc15_10_31_shape():
    # setlist.fm shaped on deadandcompany-2015-10-31: Truckin' info ">", Wang Dang Doodle
    # "> Truckin' reprise", China Cat Sunflower ">", tracks titled without arrows.
    # -> China Cat restored; Wang Dang Doodle not restored by E3 (starts-with-arrow form).
def test_gather_override_does_not_restore():                # structure override -> no restore, no note
def test_gather_restore_note_is_op_notes_only():            # not in structure.conflicts / show.json
```

- [ ] **Step 5: Wire it in, then run the new tests**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -k "restore_ or gather_.*restore" -q`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `./.venv/bin/pytest -q`
Expected: all pass. If an existing test's expected segues change (only E2 can do that), **stop
before Step 7 and report BLOCKED** with each test name, the track and the cause. The orchestrator
decides whether the new expectation is right before you update it and commit.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/tests/test_stage_gather.py
git commit -m "gather: add-only segue restore pass (setlist.fm marks; deterministic segues where the LLM won)"
```

---

### Task 3: the offline measurement script and docs

**Files:**
- Create: `scripts/segue_restore_measure.py`, `scripts/test_segue_restore_measure.py`
- Modify: `scripts/CLAUDE.md` (one entry under One-offs), `packages/llama/CLAUDE.md` (one paragraph
  where segues/structure are described: the pass, E2/E3, the donor-said-no skip, the op_notes line)

**Interfaces:**
- Consumes: `replay.compute_legs(ws, config=..., ia=..., slfm=..., scratch=..., gather_providers=...)`,
  Task 2's `restore_segues` (patched to a no-op for the "off" arm).
- Produces: `python scripts/segue_restore_measure.py spot --slugs S... --out DIR` and
  `python scripts/segue_restore_measure.py library --out DIR [--limit N]`. Both are read-only: they
  write only under `DIR` and replay scratch dirs.

**One replay per show, both arms at once.** The script wraps `llama.stages.gather.restore_segues`
(monkeypatch) with a recorder that calls the real function twice, with the real `donor` and with
`donor=None`, and records its input segues (arm A), its output (arm B), and the second call's extra
adds (the **donor-said-no skips**). It returns the first call's result. No rule logic is copied.
The `info` form of an E3 add or skip is recovered by walking the show's raw cached setlist.fm songs
in order and matching on `normalize_song` title (first unused match).

`spot`: for each slug, `compute_legs` with `gather_providers=(None, stub)` where the stored alignment
was `llm`. The stub is an object with `.complete(prompt) -> str` (herder/tasks.py ~94). It parses the
`index | filename | title | dur` lines `_format_tracks` renders (gather.py ~450) and answers EVERY
index: `set`/`segue` from the stored `show.json` track with that **filename**, `matched_title` = the
title. A filename missing from the stored show gets the previous track's set and `segue=False`. The
script records an error for any stored-`llm` show whose replay `structure.alignment` isn't `llm`, and
reports any arm-A segue that differs from the stored one. Write `DIR/spot.json` and `DIR/spot.txt`:
per show, every A→B add with its evidence and `info` form, and the donor-said-no skips.

`spot --live`: the same with real `gather_providers` from config (`extract_setlist`,
`align_structure`), for Task 4 Step 3. It reads only, writes nothing outside `DIR` and replay scratch.

`library`: every library show whose replay has no gather LLM touchpoint (`legs.gather.needs_llm`
empty and the stored alignment not `llm`; a missing `vetting.json` does not exclude a show). No
providers. Write `DIR/library.json` and print:
- shows changed and segues added;
- changed shows **by state**: library-only, delivered unvoiced, delivered voiced (from the ledger and
  `station_mark.destination_voiced`). A v2.23.0 campaign arm marks every one of them;
- adds by `info` form (`>`, `->`, `) (>`, other), and the donor-said-no skips, counted the same way;
- a seeded sample (`--seed`, default 20261107) of 20 adds stratified by form, and 20 skips, each with
  slug, track number and title, `info`, and the selected recording's description line containing
  the title (from `~/.llama/cache`), for hand-checking.

`CacheMiss` or `LlamaError` on a show is recorded and skipped; it never stops the run. For library
enumeration, config, `CacheOnlyIA` and `setlistfm_client`, follow `scripts/replay_holds.py`.

- [ ] **Step 1: Write failing tests** for the pure parts: the stub's prompt parsing and
  by-filename answers (every index answered, `matched_title` filled, a missing filename handled),
  the `info`-form classifier (`">"`, `"->"`, `"x) (>"` → `") (>"`, `"> X reprise"` → other), the
  recorder (A, B and the donor-said-no difference on a synthetic call), and the stratified sample
  being seeded and deterministic.
- [ ] **Step 2: Run to verify they fail** — `./.venv/bin/pytest scripts/test_segue_restore_measure.py -q`, FAIL.
- [ ] **Step 3: Implement the script.**
- [ ] **Step 4: Run** — `./.venv/bin/pytest scripts/test_segue_restore_measure.py -q` PASS, then `./.venv/bin/pytest -q` PASS.
- [ ] **Step 5: Docs** — the two CLAUDE.md entries.
- [ ] **Step 6: Commit**

```bash
git add scripts/segue_restore_measure.py scripts/test_segue_restore_measure.py scripts/CLAUDE.md packages/llama/CLAUDE.md
git commit -m "scripts: segue restore measurement (spot A/B, library counts); docs"
```

---

### Task 4: run the measurements (orchestrator, not an implementer)

- [ ] **Step 1: Spot A/B** on the 10 spot-check slugs (from `~/.llama-harness/bulk/spot-{dead,funk}-llm-v3.txt`).
  Pass: China Cat on deadandcompany-2015-10-31 is restored; none of the 9 good changes in the spec's
  table is reverted (the rule only adds, so check that no segue the re-run dropped correctly comes
  back: Uncle John's Band on 2015-11-10, the 5 lettuce-2008-08-06 drops); every other add listed
  with evidence.
- [ ] **Step 2: Library run**, then hand-check both 20-samples against the descriptions. Write the
  results to `docs/superpowers/2026-11-07-segue-restore/measurement.md` (counts, changed shows by state,
  both hand-check tallies, and every misfire with its slug, including any setlist.fm mark that lands
  on a tape that skips the next song).
- [ ] **Step 3: Live sample: STOP for Shawn's go.** About 37 held needs-LLM shows via
  `segue_restore_measure.py spot --live` (read-only, nothing written or delivered), ~0.2 points of
  the 5-hour meter each under usage pacing. Report the LLM's own adds and drops versus stored
  separately from the rule's restores (restores also lower the campaign's `align_reproduced`
  metric), hand-check every restore and a sample of the remaining drops, append to `measurement.md`.
- [ ] **Step 4: Campaign handoff.** Append to `~/.llama-harness/bulk-apply/handoff-campaign.md`:
  a v2.23.0 arm shows every show the rule changes as a visible `segues` change, and `mark` would
  stamp delivered and voiced copies off air, so Shawn decides from `measurement.md`'s by-state
  counts before any `mark --apply`; held shows are re-gathered with `reapply
  --allow-structure-change` on v2.23.0 **before** they are adjudicated (the adjudicator's staleness
  check compares filenames only, so it would judge a not-reapplied show and then restore the apply
  on the unpredicted segue);
  `align_reproduced` falls by the number of restores; the 20 voiced
  needs-LLM shows are re-voiced via `llama deliver <slug> --replace-voiced` then `emcee run`
  (17 funk/jamesbrown, 2 indie/kurt, 1 bluegrass/monroe); the other library shows E3 would change
  are listed in `measurement.md` and not swept without Shawn's word. Also document, in the
  packages/llama/CLAUDE.md paragraph (Task 3), the known limitation: a setlist.fm mark lands as a
  segue into the next TRACK even where the tape skips the next song.
