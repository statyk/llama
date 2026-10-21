# Held-backlog small fixes (venue tie-break, safe `fix`, curly apostrophe) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three small confirmed fixes from the held-backlog adjudication: a tied venue vote ships the selected recording's own string (B), every `fix`/`redo`/triage edit runs as one snapshot-and-restore unit under the show lock so a refused or failed edit leaves the show byte-identical (C), and `’`/`‘` match `'` at the matching layer (D).

**Architecture:** B is a pure helper `venue_tie_break` in `stages/gather.py`, consulted in exactly three arms of the existing venue chain. C adds one module, `llama/show_unit.py` (a view of the show taken before any prompt, a context manager that takes the show lock, re-checks that view, snapshots every file outside `package/audio/` into `<show>/.txn/`, and restores on any exception). `cli._redo_show` splits into a lock-held `_redo_show_locked` plus a unit-wrapping `_redo_show`, and `fix`/triage run their edits and redo inside one unit. D adds `structure.fold_curly_apostrophes`, applied by `fuzzy_norm_title` and by vet_research's and brief's song matchers. `normalize_song` is not touched. The replay harness gains a `venue_changes.txt` report. Acceptance runs the harness on a base arm and a candidate arm.

**Tech Stack:** Python 3.11+, pydantic v2, typer (`CliRunner` in tests), `fcntl.flock`, pytest. All tests are offline (`herder.FakeProvider`, captured archive.org fixtures, `test_pipeline.FakeIA`).

**Spec:** `docs/superpowers/specs/2026-10-21-held-backlog-small-fixes-design.md` (approved 2026-10-21). Every implementer reads the spec slice their task names, plus this task, plus Global Constraints.

## Global Constraints

- **Byte-identical, never edited:** `songs.normalize_song`, `songs.DEFAULT_ALIASES`, `titles.is_real_title`, `titles._TRACK_NUM_PREFIX`, `structure._STRUCTURE_PREFIX`, and every do-not-retune constant named in `CLAUDE.md`: the junk constants (`SHORT_FRACTION_OF_MEDIAN`, `MIN_PLAUSIBLE_SEC`, `MIN_MEDIAN_SAMPLE`), the tail-guard constants (`TAIL_GUARD_ITEMS`, `TRACKS_REMAINING`, `MAX_SKIP`) and `align()`'s default `lookahead=8`, `gather._RECOVER_BELOW`/`_RECOVER_SIBLING_ABOVE`, the sibling-align `AUTO`/`FLOOR`/`MIN_ANCHORS`, `_ENUMERATED_MIN_FILES`/`_ENUMERATED_MIN_COVERAGE`, `RIGHT_SHOW_MIN_TAPE_FRACTION`, `RIGHT_SHOW_MIN_ASSERTED`, `ADJACENT_DAY_WINDOW`. Every code-quality review greps the diff for these names.
- `process_show` stays lock-free. Lock order stays **run ⊃ show ⊃ ledger**. Never take the show lock twice in one process (`file_lock` opens a new fd per call, and a second `LOCK_EX` deadlocks).
- No new config keys, no new CLI flags.
- Slice B adds and removes no flag, and `venue_source` stays `"item"` wherever B fires. `provenance.json`'s stored candidate is unchanged. The selected string is stripped (`_stripped`). B adds no new normalization and no operator note (plan's call: the spec names none).
- Slice D folds only U+2019 and U+2018 to `'`, on both sides of every comparison it touches. No other character is folded.
- Slice C fixed strings: refusal `"<slug>: changed by another command; run it again"`; removed show `"<slug>: the show was removed; nothing changed"`; no-`show.json` remedy suffix `"; rebuild it with: llama redo <slug> --from gather"`. The snapshot lives at `<show>/.txn/`.
- Tests: run from the worktree root as `./.venv/bin/python -m pytest ...`. Never use a bare `pytest`, and never `.venv/bin/pytest` from a copy (CLAUDE.md). Each task ends with the full suite green: `./.venv/bin/python -m pytest -q`.
- Every behavioural change gets a test that fails on today's code. A test that only pins existing behaviour is marked **(pin)** in this plan.
- Never write to `~/.llama`. Harness outputs go under `~/.llama-harness/small-fixes/`. No task runs `reapply`, `deliver`, `rm`, `fix` or `redo` against the live library.
- One commit per task. End each commit message with the attribution trailer the orchestrating session specifies.

## Review Focus

1. **Files that are not stage artifacts, present before or created during a failed unit** (an `llm-failure.txt` left by an earlier run, a `*.tmp` from a killed atomic write). Pre-existing ones are restored byte-identical. New ones are removed. Test: Task 4 `test_files_outside_the_known_artifacts_are_restored_and_new_ones_removed`.
2. **A show with no `package/` directory whose failed unit created `package/` and `package/audio/`** (never packaged, or redone from `select`). Both directories are gone after the restore. A leftover empty `package/` would otherwise survive. Test: Task 4 `test_new_directories_created_by_a_failed_unit_are_removed`.
3. **The first-ever edit: no `overrides.json` existed before the unit.** A failure removes the file the unit created rather than leaving it behind. Test: Task 6 `test_a_failed_first_edit_removes_the_overrides_file_it_created`.
4. **A selected recording whose raw venue is whitespace-only, or differs from the vote only by surrounding whitespace.** Raw strings are counted as grouping counts them, so either case can tie. A whitespace-only string never ships. A padded one ships stripped. Tests: Task 2 `test_a_whitespace_only_selected_venue_never_ships` and `test_tie_ships_the_selected_recordings_string_without_jerrybase`.
5. **A curly apostrophe at a title's edge or inside a segue chain on the tape side** (`He’s Gone > Truckin’`), with straight research or briefing mentions. Both sides are known. Tests: Task 1 `test_guard_folds_curly_apostrophes_inside_segue_chains` and `test_vet_folds_curly_apostrophes_in_a_tape_segue_chain`.

---

### Task 0: Worktree and venv (orchestrator, once, before Task 1)

**Files:** none in the repo.

- [ ] **Step 1: Create the worktree on a new branch from this branch's HEAD**

```bash
cd /Users/shawn/projects/llama
git worktree add -b held-backlog-small-fixes-impl .claude/worktrees/held-backlog-small-fixes held-backlog-small-fixes
W=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes
```

(Branching from `held-backlog-small-fixes` keeps the spec commits. If the orchestrator prefers to implement on `held-backlog-small-fixes` itself, use `git worktree add .claude/worktrees/held-backlog-small-fixes held-backlog-small-fixes` after switching the main checkout off that branch. Either way, the worktree path is the one above.)

- [ ] **Step 2: Give it its own venv**

```bash
cd "$W" && python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"
```

- [ ] **Step 3: Prove the import resolves inside the worktree**

Run: `cd "$W" && ./.venv/bin/python -c "import llama; print(llama.__file__)"`
Expected: a path starting with `/Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes/`.

- [ ] **Step 4: Record the baseline**

Run: `cd "$W" && ./.venv/bin/python -m pytest -q`
Expected: all green. Record the passed count in the SDD ledger.

---

### Task 1: Slice D, the curly-apostrophe fold at the matching layer

**Files:**
- Modify: `packages/llama/src/llama/structure.py` (new `fold_curly_apostrophes`, used by `fuzzy_norm_title`)
- Modify: `packages/llama/src/llama/stages/vet_research.py` (`_title_match`, `_known_song`, `right_show_gate`'s `research_known`/`tape_known`, `grounding_flags`' `known`)
- Modify: `packages/llama/src/llama/stages/brief.py` (`song_components`, `known_song`'s exact test, `briefing_guard`'s `exact` builder)
- Modify: `CLAUDE.md` (one clause in the fuzzy-matching paragraph)
- Test: `packages/llama/tests/test_structure.py`, `test_stage_vet.py`, `test_stage_brief.py`

**Interfaces:**
- Produces: `structure.fold_curly_apostrophes(text: str) -> str`, which returns `text` with `"’"` and `"‘"` replaced by `"'"` and nothing else changed. Task 2 does not use it. The harness picks it up through `fuzzy_norm_title`.

- [ ] **Step 1: Write the failing tests**

`test_structure.py`:
```python
from llama.songs import normalize_song
from llama.structure import contains_sequence, fold_curly_apostrophes, fuzzy_norm_title

def test_fuzzy_norm_title_folds_curly_apostrophes():
    assert fuzzy_norm_title("Don’t Ease Me In") == fuzzy_norm_title("Don't Ease Me In")
    assert fuzzy_norm_title("‘Round And Round") == fuzzy_norm_title("'Round And Round")
    assert fold_curly_apostrophes("a’b‘c“d") == "a'b'c“d"   # only the two

def test_normalize_song_still_splits_on_a_curly_apostrophe():   # (pin) the strict list
    assert normalize_song("Don’t Ease Me In") == "don t ease me in"

def test_contains_sequence_matches_a_curly_description():
    assert contains_sequence("Bertha &gt; Don’t Ease Me In", ["Don't Ease Me In"])
```

`test_stage_vet.py` (uses `grounding_flags`, `right_show_gate`, `ResearchVetting`, `Show`, `Track`):
```python
def _curly_show(titles):
    return Show(performance_id="GratefulDead/1973-06-10", identifier="gd73", artist="Grateful Dead",
                date="1973-06-10", tracks=[Track(index=i, set="1", title=t, filename=f"t{i}.mp3",
                                                 title_source="tags") for i, t in enumerate(titles, 1)])

@pytest.mark.parametrize("tape,research", [
    (["He’s Gone", "Don’t Ease Me In"], ["He's Gone", "Don't Ease Me In"]),   # curly on tape
    (["He's Gone", "Don't Ease Me In"], ["He’s Gone", "Don’t Ease Me In"]),   # curly in research
])
def test_vet_matches_curly_and_straight_apostrophes_both_ways(tape, research):
    v = ResearchVetting(asserted_songs=research, asserted_dates=["1973-06-10"], context="")
    flags, _, _ = grounding_flags(v, _curly_show(tape))
    assert not any("unknown song" in f for f in flags)

def test_vet_folds_curly_apostrophes_in_a_tape_segue_chain():
    # two unknowns today (He's Gone, Don't Ease Me In) of three asserted -> flagged today
    v = ResearchVetting(asserted_songs=["He's Gone", "Don't Ease Me In", "Truckin'"], asserted_dates=[], context="")
    flags, _, _ = grounding_flags(v, _curly_show(["He’s Gone > Truckin’", "Don’t Ease Me In"]))
    assert not any("unknown song" in f for f in flags)

def test_right_show_gate_counts_a_curly_tape_title_as_asserted():
    tape = ["He’s Gone", "Don’t Ease Me In", "Truckin’", "Sugar Magnolia"]
    v = ResearchVetting(asserted_songs=["He's Gone", "Don't Ease Me In", "Truckin'", "Sugar Magnolia"],
                        asserted_dates=["1973-06-10"], context="")
    _, info = right_show_gate(v, _curly_show(tape), date_flags_raw=[])
    assert info["asserted"] == 4 and info["unknown"] == []
```

`test_stage_brief.py` (uses the file's `_briefing`, `Show`, `Track`):
```python
def _tape(*titles):
    return Show(performance_id="GratefulDead/1973-06-10", identifier="gd73", artist="Grateful Dead",
                date="1973-06-10", tracks=[Track(index=i, set="1", title=t, filename=f"t{i}.mp3",
                                                 title_source="tags") for i, t in enumerate(titles, 1)])

@pytest.mark.parametrize("track,mention", [("Don’t Ease Me In", "Don't Ease Me In"),
                                           ("Don't Ease Me In", "Don’t Ease Me In")])
def test_guard_matches_curly_and_straight_apostrophes_both_ways(track, mention):
    problems = briefing_guard(_briefing(per_set={"1": ["x"]}, mentioned_songs=[mention]), _tape(track))
    assert not any("unknown song" in p for p in problems)

def test_guard_folds_curly_apostrophes_inside_segue_chains():
    problems = briefing_guard(_briefing(per_set={"1": ["x"]}, mentioned_songs=["He's Gone", "Truckin'"]),
                              _tape("He’s Gone > Truckin’"))   # today: "he s gone" != "hes gone"
    assert not any("unknown song" in p for p in problems)
    assert song_components("E: He’s Gone >") == ["hes gone"]
```

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_structure.py packages/llama/tests/test_stage_vet.py packages/llama/tests/test_stage_brief.py -q -k "curly or apostroph"`
Expected: FAIL. `fold_curly_apostrophes` is not defined, and the vet/brief cases report unknown songs. The `normalize_song` pin passes.

- [ ] **Step 3: Implement**

- In `structure.py`, add `fold_curly_apostrophes` and call it first in `fuzzy_norm_title`: `norm_title(fold_curly_apostrophes(title).replace("&", " and "))`. Extend the docstring by one sentence: the curly fold lives here for the same reason the `&` fold does. `title_components` and `contains_sequence` inherit the fold through `fuzzy_norm_title`, and both sides of `contains_sequence` already pass through it.
- In `vet_research.py`, add a module-local `_song_tokens(name: str) -> list[str]` that returns `normalize_song(fold_curly_apostrophes(name)).split()`. Replace every `normalize_song(x).split()` in `_title_match`, `_known_song`, `right_show_gate` (`research_known`, `tape_known`) and `grounding_flags` (`known`) with it. Import `fold_curly_apostrophes` from `llama.structure`.
- In `brief.py`, add a module-local `_song_norm(s: str) -> str` that returns `normalize_song(fold_curly_apostrophes(s))`. Use it in `song_components` (per part), in `known_song`'s exact test, and in `briefing_guard`'s `exact` set. The `components` builders reach it through `song_components`.
- In `CLAUDE.md`'s "`align()` matches fuzzily" paragraph, after "folding `&`→`and`", add: "and curly apostrophes (`’`/`‘`) to `'` (`structure.fold_curly_apostrophes`, also applied by vet_research's and brief's song matchers on both sides)". The sentence that says `normalize_song` stays untouched still holds.

- [ ] **Step 4: Run the targeted tests, then the full suite**

Run: the Step 2 command, then `./.venv/bin/python -m pytest -q`
Expected: PASS, and the full suite is green.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/src/llama/stages/vet_research.py packages/llama/src/llama/stages/brief.py packages/llama/tests/test_structure.py packages/llama/tests/test_stage_vet.py packages/llama/tests/test_stage_brief.py CLAUDE.md
git commit -m "feat(match): fold curly apostrophes at the matching layer (slice D)"
```

---

### Task 2: Slice B, a tied venue vote ships the selected recording's string

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (new `venue_tie_break`, wired into the venue chain in `compute_gather`)
- Modify: `CLAUDE.md` (one sentence in the "Tier 1 held-backlog guards" bullet)
- Test: `packages/llama/tests/test_stage_gather.py` (new section `# --- slice B: venue tie-break ---`)

**Interfaces:**
- Consumes: `grouping._make_candidate(pid, collection, recs)` (tests build candidates through it so the vote is grouping's), `structure.cities_compatible`, `venues_equivalent`, `_venues_equivalent_pre1b`, `gather._stripped`.
- Produces: `gather.venue_tie_break(candidate: Candidate, sel: RecordingSummary | None) -> tuple[str, str | None] | None`. It returns `(venue, city)` to ship, or `None` when the tie-break does not apply. It returns a value only when all of these hold:
  1. `sel` is not None and `_stripped(sel.venue)` is non-empty.
  2. With `counts = Counter(r.venue for r in candidate.recordings if r.venue)` (raw strings, exactly as `grouping._make_candidate` counts), `counts[sel.venue] == max(counts.values())`.
  3. `sel.venue != candidate.venue`.
  4. `_stripped(sel.coverage)` is None, or `cities_compatible(sel_city, candidate.city)`.

  The value returned is `(_stripped(sel.venue), sel_city or candidate.city)`. Plan's call: "as many votes as the winning string" is read as "equals the top count". That is identical under grouping's own construction and robust to a hand-edited candidate.

- [ ] **Step 1: Write the failing tests**

All tests use this file's `StubIA`, `IDENT` (gd73), `DSO`/`DSO_IDENT`, `_gather` and `_penns_landing_event`. The helper `RS = RecordingSummary` sets `date` on each recording. Build candidates with `_make_candidate`, and assert `cand.venue` (the vote) first, so the test documents the tie.

```python
from llama.grouping import _make_candidate
from llama.stages.gather import venue_tie_break

def _cand(pid, coll, date, *specs):   # specs: (identifier, venue, coverage)
    return _make_candidate(pid, coll, [RecordingSummary(identifier=i, date=date, venue=v, coverage=c)
                                       for i, v, c in specs])

def _gd(tmp_path, cand):
    return compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(), None, cand, IDENT, jerrybase_enabled=False)

def _venue_flags(show):
    return [f for f in show.review_flags if f.startswith(("venue mismatch", "recordings of this date disagree"))]

def test_tie_ships_the_selected_recordings_string_without_jerrybase(tmp_path):
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "R.F.K. Stadium", "Washington"), (IDENT, " RFK Stadium ", "Washington, DC"))
    assert cand.venue == "R.F.K. Stadium"                         # listing order won the 1-1 tie
    res = _gd(tmp_path, cand)
    assert (res.show.venue, res.show.city, res.show.venue_source) == ("RFK Stadium", "Washington, DC", "item")
    assert _venue_flags(res.show) == []

def test_a_majority_keeps_the_consensus(tmp_path):
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("a", "R.F.K. Stadium", "Washington, DC"), ("b", "R.F.K. Stadium", "Washington, DC"),
                 (IDENT, "RFK Stadium", "Washington, DC"))
    assert _gd(tmp_path, cand).show.venue == "R.F.K. Stadium"

def test_a_tie_whose_selected_city_is_incompatible_ships_the_vote_unchanged(tmp_path):
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "RFK Stadium", "Washington, DC"), (IDENT, "RFK Stadium ", "Baltimore, MD"))
    res = _gd(tmp_path, cand)
    assert (res.show.venue, res.show.city) == ("RFK Stadium", "Washington, DC")

def test_a_tie_with_a_blank_selected_city_keeps_the_vote_city(tmp_path):
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "R.F.K. Stadium", "Washington, DC"), (IDENT, "RFK Stadium", None))
    assert (lambda s: (s.venue, s.city))(_gd(tmp_path, cand).show) == ("RFK Stadium", "Washington, DC")

def test_a_whitespace_only_selected_venue_never_ships(tmp_path):   # Review Focus 4
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "RFK Stadium", "Washington, DC"), (IDENT, "   ", "Washington, DC"))
    assert _gd(tmp_path, cand).show.venue == "RFK Stadium"

def test_step_1_tie_ships_the_selected_string_jerrybase_corroborates(tmp_path, monkeypatch):
    _penns_landing_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Philadelphia, PA"), (DSO_IDENT, "Penns Landing", "Philadelphia, PA"))
    assert cand.venue == "Penn's Landing"
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penns Landing" and _venue_flags(res.show) == []

def test_step_1_tie_keeps_the_vote_when_the_selected_string_is_newly_equivalent_and_cities_conflict(tmp_path, monkeypatch):
    # Narrowing S: the vote passes step 1 on pre-1b equivalence alone; the selected string is
    # equivalent only under 1b, and Camden is not jerrybase's Philadelphia, so it fails step 1's full test.
    _penns_landing_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Camden, NJ"), (DSO_IDENT, "Penns Landing", "Camden, NJ"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penn's Landing" and _venue_flags(res.show) == []

def test_step_1_tie_keeps_the_vote_when_jerrybase_does_not_corroborate_the_selected_string(tmp_path):
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Barrymore Theatre", "Madison, WI"), (DSO_IDENT, "Orpheum Theater", "Madison, WI"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Barrymore Theatre" and _venue_flags(res.show) == []

def _blank_venue_event(monkeypatch, city="Philadelphia", state="PA"):
    from llama.models import JerrybaseEvent
    ev = JerrybaseEvent(event_id="e1", venue="", city=city, state=state)
    monkeypatch.setattr(gather_mod.jerrybase, "lookup", lambda artist, date: [ev])

def test_1a_tie_ships_the_selected_string_when_cities_agree(tmp_path, monkeypatch):
    _blank_venue_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Philadelphia, PA"), (DSO_IDENT, "Penns Landing", "Philadelphia, PA"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penns Landing" and _venue_flags(res.show) == []

def test_1a_tie_keeps_the_vote_when_the_cities_conflict(tmp_path, monkeypatch):
    _blank_venue_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Camden, NJ"), (DSO_IDENT, "Penns Landing", "Camden, NJ"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penn's Landing"
    assert "venue mismatch: archive 'Penn's Landing' vs jerrybase ''" in res.show.review_flags

@pytest.mark.parametrize("tied,untied", [   # same show, the selected string set to the vote's
    ((("gd73-other", "R.F.K. Stadium", "Washington"), (IDENT, "RFK Stadium", "Washington, DC")),
     (("gd73-other", "R.F.K. Stadium", "Washington"), (IDENT, "R.F.K. Stadium", "Washington, DC"))),
])
def test_the_tie_break_never_changes_a_flag(tmp_path, tied, untied):
    a = _gd(tmp_path / "a", _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10", *tied))
    b = _gd(tmp_path / "b", _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10", *untied))
    assert a.show.venue != b.show.venue and a.show.review_flags == b.show.review_flags

def test_venue_tie_break_unit_cases():
    recs = [RecordingSummary(identifier="a", venue="X Hall", coverage="Austin, TX"),
            RecordingSummary(identifier="b", venue="X Hall ", coverage=None)]
    cand = _make_candidate("A/2000-01-01", "A", recs)
    assert venue_tie_break(cand, recs[1]) == ("X Hall", "Austin, TX")   # raw strings counted apart
    assert venue_tie_break(cand, recs[0]) is None                        # the selected string IS the vote
    assert venue_tie_break(cand, None) is None
```

Must stay green unmodified (the arms that keep the vote and flag): `test_the_signature_blocks_the_swap_when_the_selected_tape_agrees_with_jerrybase` (a hand-built 1-1 tie in which the selected Uptown tape agrees with jerrybase, and the signature arm must keep `'Rambler Room, Loyola College'`). The same goes for every other existing venue test. If an existing test changes outcome, stop and report it to the orchestrator: it is a spec question, not a test to edit.

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k "tie or majority or whitespace_only"`
Expected: FAIL. `venue_tie_break` cannot be imported. Once that is stubbed out, the positive cases still ship the vote.

- [ ] **Step 3: Implement `venue_tie_break` and wire it into `compute_gather`'s venue chain**

Compute `tie = venue_tie_break(candidate, sel)` once, after `sel`/`sel_venue`/`sel_city` are set and before the chain. Apply it in exactly these three places, setting `venue, city = tie` and leaving `venue_source` as `"item"`:
- **No event** (`event is None`): add an `else` to `if event is not None:` that applies `tie` when it is not None.
- **1a with no flag**: inside `if not event.venue.strip():`, when `cities_compatible(archive_city, jb_city)` holds (the branch that appends nothing today).
- **Step 1** (the `pass` branch): only when `tie` is not None, `venues_equivalent(tie[0], event.venue)`, and `(_venues_equivalent_pre1b(tie[0], event.venue) or cities_compatible(archive_city, jb_city))`. This is step 1's full test, applied to the selected string.

It is not applied in enrichment, the swap, `two_venue_signature`, 1c, the final `else`, or flagged 1a. 1d and the operator overrides are unchanged and still read `vote_venue`/`vote_city`. Every `mismatch` string is built from the vote before the chain, as today.

Add to `CLAUDE.md`'s Tier 1 guards bullet: "**Venue tie-break** (`gather.venue_tie_break`, spec `2026-10-21-held-backlog-small-fixes-design.md` slice B): on a tied grouping vote (raw strings, counted as `grouping._make_candidate` counts) the selected recording's own stripped venue ships, with `sel_city or vote_city`. It applies only when its city is blank or `cities_compatible` with the vote's, and only in the arms that ship the vote unflagged: no event, unflagged 1a, and step 1 when the selected string passes step 1's full test. It never adds or removes a flag, `venue_source` stays `item`, and `provenance.json` is unchanged."

- [ ] **Step 4: Run the targeted tests, then the full suite**

Run: the Step 2 command, then `./.venv/bin/python -m pytest -q`
Expected: PASS, and the full suite is green with no existing test edited.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/tests/test_stage_gather.py CLAUDE.md
git commit -m "feat(gather): a tied venue vote ships the selected recording's string (slice B)"
```

---

### Task 3: Harness `venue_changes.txt` report

**Files:**
- Modify: `scripts/replay_holds.py` (`OUTPUT_FILES`, new `_venue_changes`, `compare`, `summary.txt`)
- Test: `scripts/test_replay_holds.py`

**Interfaces:**
- Consumes: the arm row keys `venue`/`city` (each `{"old", "new"}` or null, where null means "replay equals the stored value"), `state`, `outcome`, and `_all_flags(r)`.
- Produces: `_venue_changes(base: dict, cand: dict) -> tuple[list[str], int, int]`, which returns the lines, the number of shows listed, and how many of those have a flag change. It writes `venue_changes.txt` and adds the summary line `f"venue_changes.txt: {n} show(s), {m} with a flag change"`.

Rules (plan's call):
- Each arm's shipped value of a field is `row[field]["new"]` when the row has a diff. Otherwise it is the stored value, which is `old` from whichever arm has a diff.
- A show is listed when base and cand differ on venue or city.
- Shows that are `unreplayable` in either arm are skipped and counted in a header line, because their fields are absent.
- Each row, in slug order:
  - `f"{slug}  [{state}]"` plus `"  DELIVERED"` when the cand `state == "delivered"`
  - `f"  venue: {_j(bv)} -> {_j(cv)}"`
  - `f"  city: {_j(bc)} -> {_j(cc)}"`
  - `"  flags: unchanged"`, or `f"  flags CHANGED: added {_j(sorted(added))}; removed {_j(sorted(removed))}"` over `_all_flags`

- [ ] **Step 1: Write the failing tests**

```python
def _venue(arm, slug, new, state=None, old="RFK Stadium"):
    s = arm["shows"][slug]
    s["venue"] = {"old": old, "new": new}
    if state:
        s["state"] = state

def test_venue_changes_lists_both_strings_and_delivery(tmp_path):
    slug = "gratefuldead-1973-06-11"
    base, cand = _two_arms(tmp_path, mutate_cand=lambda a: _venue(a, slug, "R.F.K. Stadium", "delivered"),
                           mutate_base=lambda a: a["shows"][slug].update(state="delivered"))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "venue_changes.txt").read_text()
    assert f"{slug}  [delivered]  DELIVERED" in text
    assert 'venue: "RFK Stadium" -> "R.F.K. Stadium"' in text and "flags: unchanged" in text
    assert "venue_changes.txt: 1 show(s), 0 with a flag change" in (out / "summary.txt").read_text()
    assert "venue_changes.txt" in rh.OUTPUT_FILES

def test_venue_changes_ignores_an_identical_diff_and_counts_a_flag_change(tmp_path):
    slug = "gratefuldead-1973-06-11"
    def both(a): _venue(a, slug, "R.F.K. Stadium")
    def cand_m(a):
        both(a)
        a["shows"][slug]["city"] = {"old": "Washington, DC", "new": "Washington, D.C."}
        a["shows"][slug]["gather_flags"] = ["venue mismatch: archive 'A' vs jerrybase 'B'"]
    base, cand = _two_arms(tmp_path, mutate_cand=cand_m, mutate_base=both)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "venue_changes.txt").read_text()
    assert "R.F.K. Stadium" in text                                   # unchanged venue still shown on the row
    assert 'city: "Washington, DC" -> "Washington, D.C."' in text
    assert "flags CHANGED: added" in text
    assert "venue_changes.txt: 1 show(s), 1 with a flag change" in (out / "summary.txt").read_text()
```

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest scripts/test_replay_holds.py -q -k venue_changes`
Expected: FAIL, because there is no `venue_changes.txt`.

- [ ] **Step 3: Implement**

Add `"venue_changes.txt"` to `OUTPUT_FILES`, implement `_venue_changes`, and call it in `compare` next to `packaged_exposure.txt`. Add the summary line after the `packaged_exposure.txt` line.

- [ ] **Step 4: Run the file's tests, then the full suite**

Run: `./.venv/bin/python -m pytest scripts/test_replay_holds.py -q`, then `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/replay_holds.py scripts/test_replay_holds.py
git commit -m "feat(harness): venue_changes.txt lists shipped venue/city changes between arms"
```

---

### Task 4: Slice C core, `llama/show_unit.py`

**Files:**
- Create: `packages/llama/src/llama/show_unit.py`
- Modify: `packages/llama/tests/helpers.py` (add `tree_bytes`)
- Test: `packages/llama/tests/test_show_unit.py`

**Interfaces:**
- Consumes: `locks.file_lock`, `workspace.ShowWorkspace`, `workspace.atomic_write_bytes`, `errors.LlamaError`.
- Produces (Tasks 5-8 rely on these exact names):
  - `TXN_DIR = ".txn"`
  - `@dataclass(frozen=True) class ShowView: provenance: bool; overrides: bytes | None; show: bytes | None` (equality is the re-resolve check). The name avoids `cli.ShowState`, which already exists.
  - `capture_view(show_ws: ShowWorkspace) -> ShowView` (`provenance.json` exists; `overrides.json` and `show.json` bytes, or None)
  - `class ShowChanged(LlamaError)`
  - `take_snapshot(show_ws) -> None`, `restore_snapshot(show_ws) -> None`, `discard_snapshot(show_ws) -> None`
  - `@contextmanager show_unit(show_ws: ShowWorkspace, expect: ShowView) -> Iterator[None]`
  - tests: `helpers.tree_bytes(d: Path) -> dict[str, bytes]`, which maps each file's posix path relative to `d` to its bytes, for every file under `d` except the top-level `.lock`

Behaviour (spec C1 steps 2-5, C2):
- `show_unit`:
  1. Takes `file_lock(show_ws.lock)` (blocking) for the whole context.
  2. Computes `now = capture_view(show_ws)`. If `now != expect`, it raises `ShowChanged`: when `expect.provenance and not now.provenance`, the text is `f"{slug}: the show was removed; nothing changed"`; otherwise it is `f"{slug}: changed by another command; run it again"` (`slug = show_ws.dir.name`). Nothing is written.
  3. Calls `discard_snapshot` (a leftover is deleted, never restored), then `take_snapshot`. If `take_snapshot` raises, it discards and re-raises.
  4. Yields.
  5. On any `BaseException` it calls `restore_snapshot`, then `discard_snapshot`, then re-raises. On normal exit it calls `discard_snapshot`.
- `take_snapshot` copies every file under the show dir, except the top-level `.lock`, everything under `.txn/` and everything under `package/audio/`, to `.txn/files/<relpath>`. It writes `.txn/index.json` = `{"audio": sorted file names directly in package/audio/, "dirs": sorted relative posix paths of every directory under the show dir except .txn and anything below package/audio}`.
- `restore_snapshot`, in this order:
  - (a) Unlink every file outside `package/audio/`, `.lock` and `.txn/` that is not in the snapshot.
  - (b) `atomic_write_bytes` every snapshot file back to its path.
  - (c) Unlink every file in `package/audio/` not on the `audio` list.
  - (d) Plan's call: `rmdir` every directory not in `dirs`, deepest first, when it is empty.
- Existing audio is never copied or rewritten. A retag that a failed package stage made in place stays, as the spec's limitation documents.

- [ ] **Step 1: Write the failing tests** (`test_show_unit.py`, `from helpers import tree_bytes`)

Fixture `_show(tmp_path)`: a `ShowWorkspace(tmp_path / "shows" / "s")` with `provenance.json`, `overrides.json`, `show.json`, `reviews.json`, `package/manifest.json` and `package/audio/a.mp3` (bytes `b"A"`), written with `write_artifact`/`atomic_write_bytes`.

```python
def _fail_inside(ws, exc, body):
    view = capture_view(ws)
    with pytest.raises(type(exc)):
        with show_unit(ws, view):
            body()
            raise exc

def test_a_failed_unit_restores_every_file_byte_identical(tmp_path):
    ws = _show(tmp_path); before = tree_bytes(ws.dir)
    def body():
        write_artifact(ws.show, {"changed": True}); ws.reviews.unlink()
        write_artifact(ws.research, "new"); write_artifact(ws.package_dir / "manifest.json", {"v": 9})
        atomic_write_bytes(ws.package_dir / "audio" / "new.mp3", b"N")
    _fail_inside(ws, LlamaError("refused"), body)
    assert tree_bytes(ws.dir) == before
    assert not (ws.dir / ".txn").exists() and ws.lock.exists()

def test_keyboard_interrupt_restores_and_re_raises(tmp_path):
    ws = _show(tmp_path); before = tree_bytes(ws.dir)
    _fail_inside(ws, KeyboardInterrupt(), lambda: ws.show.unlink())
    assert tree_bytes(ws.dir) == before

def test_a_successful_unit_keeps_its_writes_and_removes_the_snapshot(tmp_path):
    ws = _show(tmp_path)
    with show_unit(ws, capture_view(ws)):
        write_artifact(ws.research, "kept")
    assert ws.research.read_text() == "kept" and not (ws.dir / ".txn").exists()

def test_new_directories_created_by_a_failed_unit_are_removed(tmp_path):            # Review Focus 2
    ws = ShowWorkspace(tmp_path / "shows" / "s"); write_artifact(ws.provenance, {"p": 1})
    _fail_inside(ws, LlamaError("x"), lambda: atomic_write_bytes(ws.package_dir / "audio" / "n.mp3", b"N"))
    assert not ws.package_dir.exists()

def test_files_outside_the_known_artifacts_are_restored_and_new_ones_removed(tmp_path):   # Review Focus 1
    ws = _show(tmp_path); (ws.dir / "llm-failure.txt").write_text("old"); (ws.dir / "notes.json.1.tmp").write_text("t")
    before = tree_bytes(ws.dir)
    def body():
        (ws.dir / "llm-failure.txt").write_text("new"); (ws.dir / "stray.tmp").write_text("s")
    _fail_inside(ws, LlamaError("x"), body)
    assert tree_bytes(ws.dir) == before

def test_existing_audio_is_never_snapshotted_or_rewritten(tmp_path):
    ws = _show(tmp_path)
    _fail_inside(ws, LlamaError("x"), lambda: (ws.package_dir / "audio" / "a.mp3").write_bytes(b"RETAGGED"))
    assert (ws.package_dir / "audio" / "a.mp3").read_bytes() == b"RETAGGED"   # outside the guarantee
    assert not (ws.dir / ".txn" / "files" / "package" / "audio").exists()

def test_a_leftover_snapshot_is_deleted_not_restored(tmp_path):
    ws = _show(tmp_path); current = ws.show.read_bytes()
    atomic_write_bytes(ws.dir / ".txn" / "files" / "show.json", b"STALE")
    with show_unit(ws, capture_view(ws)):
        pass
    assert ws.show.read_bytes() == current and not (ws.dir / ".txn").exists()

@pytest.mark.parametrize("change", ["overrides", "show"])
def test_a_changed_show_refuses_and_changes_nothing(tmp_path, change):
    ws = _show(tmp_path); view = capture_view(ws)
    write_artifact(getattr(ws, change), {"other": "command"}); before = tree_bytes(ws.dir)
    with pytest.raises(ShowChanged, match="s: changed by another command; run it again"):
        with show_unit(ws, view):
            raise AssertionError("the body must not run")
    assert tree_bytes(ws.dir) == before

def test_a_removed_show_refuses_with_the_removed_message(tmp_path):
    ws = _show(tmp_path); view = capture_view(ws); ws.provenance.unlink()
    with pytest.raises(ShowChanged, match="s: the show was removed; nothing changed"):
        with show_unit(ws, view):
            pass

def test_the_lock_is_held_inside_the_unit_and_released_after(tmp_path):
    ws = _show(tmp_path)
    with show_unit(ws, capture_view(ws)):
        with pytest.raises(Locked):
            with file_lock(ws.lock, blocking=False):
                pass
    with file_lock(ws.lock, blocking=False):
        pass
```

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_show_unit.py -q`
Expected: FAIL with `ModuleNotFoundError: llama.show_unit`.

- [ ] **Step 3: Implement `show_unit.py` and `helpers.tree_bytes` as specified above**

Give the module docstring the three documented limitations from spec C2: audio retagged in place, the `.lock`-only husk left by a racing `rm`, and SIGKILL leaving a stale `.txn/`, which the next unit deletes and `llama redo <show> --from gather` repairs.

- [ ] **Step 4: Run the file's tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_show_unit.py -q`, then `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/show_unit.py packages/llama/tests/test_show_unit.py packages/llama/tests/helpers.py
git commit -m "feat(show_unit): snapshot-and-restore unit under the show lock (slice C core)"
```

---

### Task 5: Slice C, `redo` as a unit; runs survive a refused show

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`_redo_show` → `_redo_show_locked` + `_redo_show`; `_execute._process`'s except tuple)
- Modify: `packages/llama/tests/helpers.py` (add `packaged_gd73`)
- Modify: `CLAUDE.md` (one sentence each in the `llama redo` command line and the "Failure records" gotcha)
- Test: `packages/llama/tests/test_redo_cmd.py`, `test_pace_loop.py`, `test_reapply.py`

**Interfaces:**
- Consumes: Task 4's `ShowView`, `capture_view`, `show_unit`.
- Produces:
  - `cli._redo_show_locked(config, ia, ledger, entry, from_stage: str, *, with_research: bool = False) -> Path | None`: today's `_redo_show` body without the `file_lock`. The caller must already be inside a `show_unit` for `entry.ws`. It reads `provenance.json` itself, under the caller's lock (not `entry.provenance`), and raises today's `LlamaError(f"no provenance.json in {entry.ws.dir} - reprocess it via its run first")` when it is absent. Only `entry.ws` and `entry.slug` are used. The positional shape matches today's test stubs `(config, ia, ledger, e, stage, **kw)`, so Tasks 6-7 retarget those stubs by attribute name alone.
  - `cli._redo_show(config, ia, ledger, entry, from_stage: str, *, with_research: bool = False, expect: ShowView | None = None) -> Path | None`: `with show_unit(entry.ws, expect or capture_view(entry.ws)): return _redo_show_locked(...)`. `redo` (single), `_redo_batch` and every existing `_redo_show` stub keep working unchanged. Plan's call: batch redo captures each show's view when its turn comes, because its confirmation lists slugs, not content.
  - `helpers.packaged_gd73(tmp_path, monkeypatch) -> tuple[Path, ShowWorkspace]`: writes `config.toml` (`root = tmp_path`, `[jerrybase] enabled = false`), patches `cli.make_providers = test_pipeline.fake_providers` and `cli.IAClient = test_pipeline.FakeIA`, and runs `get "GD 1973" --auto --name r`. It returns `(cfg_path, ws)` for `shows/gratefuldead-1973-06-10`, which is packaged with `package/audio/*` (64-byte files). Import `test_pipeline` inside the function.

- [ ] **Step 1: Write the failing tests**

`test_redo_cmd.py`:
```python
from helpers import packaged_gd73, tree_bytes
import llama.pipeline as pipeline

def test_failed_redo_from_brief_restores_every_file(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_brief", lambda *a, **k: (_ for _ in ()).throw(TaskFailed("boom")))
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "brief"])
    assert r.exit_code == 1 and isinstance(r.exception, TaskFailed)
    assert tree_bytes(ws.dir) == before            # provenance.json's processed_at included

def test_package_failure_on_purged_audio_removes_new_audio_and_restores_manifest(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    for f in (ws.package_dir / "audio").iterdir():
        f.unlink()                                  # as `deliver` purges
    before = tree_bytes(ws.dir)
    from test_pipeline import FakeIA
    class SecondFails(FakeIA):
        n = 0
        def download_file(self, identifier, filename, dest, md5=None):
            SecondFails.n += 1
            if SecondFails.n == 2:
                raise IAError("download of x failed")
            return super().download_file(identifier, filename, dest, md5)
    monkeypatch.setattr(cli, "IAClient", SecondFails)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 1 and isinstance(r.exception, IAError)
    assert tree_bytes(ws.dir) == before and list((ws.package_dir / "audio").iterdir()) == []

def test_keyboard_interrupt_after_the_drop_restores_and_re_raises(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_brief", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    # through the function, not the runner: click turns KeyboardInterrupt into "Aborted!"
    from llama.config import load_config; from llama.ledger import Ledger
    config = load_config(cfg); ledger = Ledger(config.root / "ledger.jsonl")
    entry = cli._resolve_show(config, ledger, "gratefuldead")
    with pytest.raises(KeyboardInterrupt):
        cli._redo_show(config, cli.IAClient(), ledger, entry, "brief")
    assert tree_bytes(ws.dir) == before and not (ws.dir / ".txn").exists()

def test_a_leftover_txn_is_deleted_not_restored_by_the_next_redo(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    atomic_write_bytes(ws.dir / ".txn" / "files" / "show.json", b"STALE")
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 0, r.output
    assert ws.show.read_bytes() != b"STALE" and not (ws.dir / ".txn").exists()

def test_redo_runs_the_pipeline_inside_the_show_lock(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); seen = []
    def probe(*a, **k):
        try:
            with file_lock(ws.lock, blocking=False):
                seen.append("free")
        except Locked:
            seen.append("held")
        raise TaskFailed("stop")
    monkeypatch.setattr(pipeline, "run_brief", probe)
    runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "brief"])
    assert seen == ["held"]

def test_redo_batch_restores_a_failed_show_and_continues(tmp_path, monkeypatch):
    from test_catalog import build
    cfg = tmp_path / "config.toml"; cfg.write_text(f'root = "{tmp_path}"\n')
    a = build(tmp_path, "aready", stages={"select", "gather", "research", "vet", "package"})
    build(tmp_path, "bready", stages={"select", "gather", "research", "vet", "package"})
    before, done = tree_bytes(a.dir), []
    def fake(config, ia, ledger, e, stage, **kw):
        write_artifact(e.ws.show, {"half": "written"})
        if e.slug == "aready":
            raise LlamaError("boom")
        done.append(e.slug)
        return e.ws.package_dir
    monkeypatch.setattr(cli, "_redo_show_locked", fake)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "--packaged", "--from", "package", "--yes"])
    assert r.exit_code == 0 and "FAILED aready: boom" in r.output and done == ["bready"]
    assert tree_bytes(a.dir) == before
```
`test_pace_loop.py`:
```python
def test_a_show_refusing_its_overrides_is_a_per_show_failure_and_the_run_continues(tmp_path, monkeypatch):
    def _process(pid):
        if pid == "a":
            raise LlamaError("overrides.encore_after (20) must be greater than every set break [10, 20]")
        return f"{pid}/pkg"
    _, seen = _drive(tmp_path, monkeypatch, _process, ["a", "b"])
    assert seen == ["a", "b"]
    s = iter_sessions(tmp_path)[0]
    assert s.state == STATE_INCOMPLETE
    assert [(f["show"], f["kind"]) for f in s.failures] == [("a", "other")]
```

`test_reapply.py` **(pin)**:
```python
def test_reapply_on_refused_overrides_raises_and_writes_nothing(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    write_artifact(entry.ws.overrides, Overrides(set_breaks=[2, 4], encore_after=4))
    before = _snapshot(entry.ws)
    with pytest.raises(LlamaError, match="overrides\\.(encore_after|set_breaks)"):
        _run(config, ledger, entry)
    assert _snapshot(entry.ws) == before
```

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_redo_cmd.py packages/llama/tests/test_pace_loop.py packages/llama/tests/test_reapply.py -q -k "restores or leftover or inside_the_show_lock or refusing_its_overrides or refused_overrides"`
Expected: the restore, leftover and batch tests FAIL (files are left dropped, and `_redo_show_locked` does not exist). The run test FAILs because a `LlamaError` aborts `_execute`. The reapply pin PASSes.

- [ ] **Step 3: Implement**

- Split `_redo_show` as specified in Interfaces. `process_show` is unchanged and lock-free.
- In `_execute._process`, change `except (TaskFailed, HerderError, IAError) as exc:` to `except (TaskFailed, HerderError, LlamaError) as exc:`. Keep the `RateLimited` arm above it. `classify_failure` already maps `IAError`→`archive`/`download`, and any other `LlamaError` falls through to `other`.
- In `CLAUDE.md`'s command list, after `llama redo <name> --from <stage>`, add: "(one unit: see `llama fix` below)". In the "Failure records" gotcha, add: "a per-show `LlamaError` (e.g. gather refusing the show's overrides) is a per-show failure of kind `other`, not a run abort."

- [ ] **Step 4: Run the targeted tests, then the full suite**

Run: the Step 2 command, then `./.venv/bin/python -m pytest -q`
Expected: PASS. Existing `_redo_show` stubs in `test_redo_cmd.py`/`test_profile_selector.py` are unchanged and green.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/helpers.py packages/llama/tests/test_redo_cmd.py packages/llama/tests/test_pace_loop.py packages/llama/tests/test_reapply.py CLAUDE.md
git commit -m "feat(redo): every redo is a restoring unit; a refused show no longer aborts a run (slice C)"
```

---

### Task 6: Slice C, `llama fix` as one unit; edits on a show with no `show.json`

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`fix`, `_untitled_resolution`)
- Modify: `packages/llama/tests/test_fix.py` (retarget `_stub_redo` and the two inline `monkeypatch.setattr(cli, "_redo_show", ...)` calls to `_redo_show_locked`, plus the new tests)
- Modify: `packages/llama/tests/test_triage.py` (`_stub_redo` patches both names; see Step 3)
- Modify: `CLAUDE.md` (the `llama fix` entry in Commands)
- Test: `packages/llama/tests/test_fix.py`

**Interfaces:**
- Consumes: Task 4's `ShowView`, `capture_view`, `show_unit`, `ShowChanged`. Task 5's `_redo_show_locked`, `helpers.packaged_gd73`, `helpers.tree_bytes`. `test_cli._staged_ymsb_show` (24-track ymsb show).
- Produces: `cli._untitled_resolution(config, ia, ledger, entry, show: Show, view: ShowView) -> tuple[Literal["declined", "held", "packaged"], Path | None]`. It lists the tracks and confirms with no lock held, then runs in one `show_unit(entry.ws, view)`: `_edit_overrides(...)`, `_redo_show_locked(..., "gather")`, and if that returns None, `_clear_hold` followed by `_redo_show_locked(..., "brief")`. Task 7 calls it with triage's view.

New order inside `fix`:
1. `entry = _resolve_show(...)`, then `view = capture_view(sws)` immediately.
2. Today's argument-only refusals (flag combinations, parse errors), unchanged.
3. State gates and prompts, with no lock held:
   - `--untitled`: today's checks, then `_untitled_resolution(..., view)`.
   - `--suggest-titles`: today's checks, then `_propose_and_confirm_titles`.
   - `nothing to fix`.
   - The C4 gate. When `show.json` is absent, refuse `--narration`, `--overrule` and `--include` (and `--untitled`/`--suggest-titles` in their branches) with `f"no show.json in {sws.dir} (state: {entry.state}); rebuild it with: llama redo {entry.slug} --from gather"`, exit 1. `--set-*`/`--clear-*` and `--exclude`/`--unexclude` pass. A track-number `--exclude` keeps `_resolve_exclude_tokens`' own message (plan's call: it already names a remedy).
   - Plan's call: refusals that write nothing may stay before the lock, because the unit's view check re-verifies the state they judged.
4. `with show_unit(sws, view):` everything that writes, in today's order and with today's echo text: token resolution and the `--exclude`/`--include` clash check (still `typer.Exit(1)` with today's text, which now also restores), `_edit_overrides`, `_clear_hold`, then `--no-run` prints `staged; next: ...`. Otherwise `_redo_show_locked(config, ia, ledger, entry, stage)` and `packaged:`/`still held:`.
5. A failure propagates. `main_cli` prints `error: <msg>` and exits 1. Under `CliRunner`, that shows as `r.exit_code == 1` with `r.exception` set.

- [ ] **Step 1: Retarget the existing stubs, then write the failing tests**

Change `_stub_redo` and the inline stubs (around the `test_apply_prints_still_held_when_redo_returns_none` and `test_untitled_overrules_remaining_flags_then_continues_from_brief` tests) to patch `"_redo_show_locked"`. Until Step 3 these tests run the real redo, because `fix` still calls `_redo_show`, so they fail until then. That is expected.

New tests (`from helpers import packaged_gd73, tree_bytes`; `from test_cli import _staged_ymsb_show`):
```python
def _billy_shape(tmp_path, monkeypatch):
    """The billystrings-2021-12-04 sequence on a real 24-track tape: overrides already
    carrying edits, then the bad structure fix (pre-repair overrides set_breaks [10, 20],
    encore_after 20)."""
    from test_pipeline import fake_providers
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
    write_artifact(sws.selection, {"identifier": "ymsb2005-12-31.flac16.wav"})
    write_artifact(sws.overrides, Overrides(narration="vague", titles={1: "Kirby Hill"}))
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    return tmp_path / "config.toml", sws

def test_a_refused_structure_fix_leaves_every_file_byte_identical(tmp_path, monkeypatch):
    cfg, sws = _billy_shape(tmp_path, monkeypatch); before = tree_bytes(sws.dir)
    r = cli_invoke(cfg, "fix", "ymsb", "--set-breaks", "10,20", "--set-encore", "20")
    assert r.exit_code == 1 and isinstance(r.exception, LlamaError)
    assert "overrides.encore_after (20) must be greater than every set break [10, 20]" in str(r.exception)
    assert tree_bytes(sws.dir) == before            # provenance.json and overrides.json included
    r2 = cli_invoke(cfg, "fix", "ymsb", "--clear-encore", "--no-run")   # still editable afterwards
    assert r2.exit_code == 0, r2.output

def test_no_run_stages_bad_overrides_and_the_redo_restores_and_names_the_field(tmp_path, monkeypatch):   # C3
    cfg, sws = _billy_shape(tmp_path, monkeypatch)
    assert cli_invoke(cfg, "fix", "ymsb", "--set-breaks", "10,20", "--set-encore", "20", "--no-run").exit_code == 0
    assert read_overrides(sws).encore_after == 20
    before = tree_bytes(sws.dir)
    r = cli_invoke(cfg, "redo", "ymsb", "--from", "gather")
    assert r.exit_code == 1 and "encore_after" in str(r.exception) and tree_bytes(sws.dir) == before

def test_a_fix_adding_one_override_keeps_the_others(tmp_path, monkeypatch):   # (pin)
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); _stub_redo(monkeypatch)
    write_artifact(ws.overrides, Overrides(exclude=["junk.mp3"], venue="Hall", titles={2: "Dew"}, narration="vague"))
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-city", "Austin, TX").exit_code == 0
    ov = read_overrides(ws)
    assert (ov.exclude, ov.venue, ov.titles, ov.narration, ov.city) == (["junk.mp3"], "Hall", {2: "Dew"}, "vague", "Austin, TX")

def _held(ws):
    s = read_model(ws.show, Show); s.needs_review = True; s.review_flags = ["research asserts wrong date: 1974-01-01"]
    write_artifact(ws.show, s)

def test_failed_accept_vague_restores_the_hold_and_the_overrides(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); _held(ws); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_brief", lambda *a, **k: (_ for _ in ()).throw(RateLimited("limit")))
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague")
    assert r.exit_code == 1 and isinstance(r.exception, RateLimited)
    assert tree_bytes(ws.dir) == before and read_model(ws.show, Show).needs_review is True

def test_failed_overrule_restores_every_file(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); _held(ws); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_package", lambda *a, **k: (_ for _ in ()).throw(IAError("archive down")))
    assert cli_invoke(cfg, "fix", "gratefuldead", "--overrule").exit_code == 1
    assert tree_bytes(ws.dir) == before

def test_a_multi_flag_fix_whose_redo_fails_leaves_nothing_of_the_first_edits(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); _held(ws); before = tree_bytes(ws.dir)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague", "--set-breaks", "2,4", "--set-encore", "4")
    assert r.exit_code == 1 and "encore_after" in str(r.exception)
    assert tree_bytes(ws.dir) == before            # no narration, no cleared hold, no breaks

def test_a_failed_first_edit_removes_the_overrides_file_it_created(tmp_path, monkeypatch):   # Review Focus 3
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); assert not ws.overrides.exists()
    monkeypatch.setattr(cli, "_redo_show_locked", lambda *a, **k: (_ for _ in ()).throw(LlamaError("boom")))
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "Hall").exit_code == 1
    assert not ws.overrides.exists()

def test_fix_writes_overrides_under_the_show_lock(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); seen = []; real = cli._edit_overrides
    def probe(show_ws, **kw):
        try:
            with file_lock(show_ws.lock, blocking=False): seen.append("free")
        except Locked:
            seen.append("held")
        return real(show_ws, **kw)
    monkeypatch.setattr(cli, "_edit_overrides", probe)
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "Hall", "--no-run").exit_code == 0
    assert seen == ["held"]

def test_fix_refuses_when_the_show_changed_after_the_prompt(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); calls = _stub_redo(monkeypatch)
    def other_command_meanwhile(ia, config, entry, show):
        write_artifact(entry.ws.overrides, Overrides(venue="Elsewhere")); return {1: "Dew"}
    monkeypatch.setattr(cli, "_propose_and_confirm_titles", other_command_meanwhile)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--suggest-titles")
    assert r.exit_code == 1 and "changed by another command; run it again" in str(r.exception)
    assert read_overrides(ws) == Overrides(venue="Elsewhere") and calls == []

def test_untitled_failure_after_the_overrule_restores_everything(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path); ws = _all_unresolved_show(tmp_path); before = tree_bytes(ws.dir)
    def fake(config, ia, ledger, e, stage, **kw):
        if stage == "gather":
            s = read_model(e.ws.show, Show); s.needs_review = True; s.review_flags = ["x"]; write_artifact(e.ws.show, s)
            return None
        raise LlamaError("brief failed")
    monkeypatch.setattr(cli, "_redo_show_locked", fake)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert r.exit_code == 1 and tree_bytes(ws.dir) == before

def test_fix_on_a_show_with_no_show_json_takes_metadata_and_filename_edits(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select"})
    write_artifact(ws.overrides, Overrides(set_breaks=[10, 20], encore_after=20))
    assert cli_invoke(cfg, "fix", "gratefuldead", "--clear-encore", "--no-run").exit_code == 0
    assert read_overrides(ws).encore_after is None
    assert cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "junk.mp3", "--no-run").exit_code == 0
    calls = _stub_redo(monkeypatch)
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "Hall").exit_code == 0 and calls == ["gather"]

@pytest.mark.parametrize("args", [["--overrule"], ["--narration", "vague"], ["--include", "junk.mp3"],
                                  ["--suggest-titles"], ["--untitled"]])
def test_fix_on_a_show_with_no_show_json_refuses_the_rest_and_names_the_remedy(tmp_path, args):
    cfg = _cfg(tmp_path); build(tmp_path, "gratefuldead-1973-06-10", stages={"select"})
    r = cli_invoke(cfg, "fix", "gratefuldead", *args)
    assert r.exit_code == 1 and "rebuild it with: llama redo gratefuldead-1973-06-10 --from gather" in r.output
```
(Imports needed: `import llama.pipeline as pipeline`, `from llama.errors import LlamaError`, `from llama.ia_client import IAError`, `from herder.limits import RateLimited`, `from llama.locks import Locked, file_lock`, `from test_catalog import build`. `_all_unresolved_show` already exists in this file.)

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_fix.py -q`
Expected: the new restore, lock, changed-view and no-`show.json` tests FAIL, because today the overrides are written and the files dropped with no restore, and every flag is refused without `show.json`. The pin passes.

- [ ] **Step 3: Implement `fix` and `_untitled_resolution` in the order specified above**

Triage's `[u]` branch also calls `_untitled_resolution`. In this task, pass it `capture_view(entry.ws)` so the suite stays green; Task 7 replaces that with the show session's view. Triage's other branches still call `_redo_show`, which now wraps its own unit, so they keep working until Task 7. Because `[u]` now reaches `_redo_show_locked`, make `test_triage.py`'s `_stub_redo` patch **both** `_redo_show` and `_redo_show_locked` with the same recording fake, sharing one `calls` list. That keeps the three `[u]` tests (`test_triage_offers_u_only_when_every_track_is_unresolved`, `test_triage_u_declined_writes_nothing_and_returns_to_the_prompt`, `test_triage_u_confirmed_but_still_held_says_still_held`) on a stub. Add `packages/llama/tests/test_triage.py` to this task's `git add`.

Then replace the `llama fix <name> <edit-flags>` description in `CLAUDE.md`'s Commands with this addition (keep the existing text): "**One unit (2026-10-21):** `fix`, triage's edits and `redo` (single and batch, per show) ask any prompts first with no lock held. They then take the show lock, refuse with `changed by another command; run it again` if `overrides.json`/`show.json` changed (or `the show was removed`), snapshot every file outside `package/audio/` into `<show>/.txn/`, and do the work. Any exception, including Ctrl-C, restores those files byte-identical and removes new audio. A single `fix`/`redo` then exits 1 with the error. A stale `.txn/` (SIGKILL) is deleted, never restored, by the next unit. With no `show.json`, `fix` still accepts `--set-*`/`--clear-*` and filename `--exclude`/`--unexclude`. Every other flag refuses and names `llama redo <show> --from gather`, which is also the repair for any show left part-way. `--no-run` validates nothing: a later redo that refuses the overrides rolls back and names the field."

- [ ] **Step 4: Run the file's tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_fix.py packages/llama/tests/test_cli.py -q`, then `./.venv/bin/python -m pytest -q`
Expected: PASS. `test_cli.py`'s `--suggest-titles` tests are unchanged and green.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_fix.py packages/llama/tests/test_triage.py CLAUDE.md
git commit -m "feat(fix): one restoring unit per invocation; edits on a show with no show.json (slice C)"
```

---

### Task 7: Slice C, triage edits as units

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`_interactive_resolve`, `_metadata_editor`)
- Modify: `packages/llama/tests/test_triage.py` (`_stub_redo` drops its Task 6 `_redo_show` patch and keeps only `_redo_show_locked`, plus the new tests)
- Modify: `CLAUDE.md` (one sentence on `llama triage` in Commands)
- Test: `packages/llama/tests/test_triage.py`

**Interfaces:**
- Consumes: Task 4's `capture_view`, `show_unit`. Task 5's `_redo_show_locked`. Task 6's `_untitled_resolution(config, ia, ledger, entry, show, view)`.
- Produces: `cli._metadata_editor(entry) -> dict | None`. It returns the `_edit_overrides` keyword arguments (everything except `show_ws`) without writing anything, or None when nothing changed or the input was invalid (today's echo texts unchanged). Plan's call: the editor stops writing, so the write moves into the unit.

Behaviour:
- `view = capture_view(entry.ws)` is taken once per show, before `_print_show_entry`, and kept for the whole show session.
- Each branch runs its prompts with no lock held (`_pick_excludes`, `_pick_includes` + `_split_include_targets`, `_metadata_editor`, `_propose_and_confirm_titles`, `[u]`'s confirmation inside `_untitled_resolution`). It then builds the edit as a no-argument callable plus the stage, for example `lambda: _edit_overrides(entry.ws, add_exclude=files)` with `"gather"`, or `[o]` as `lambda: _clear_hold(entry.ws)` with `"package"`.
- The common tail is `with show_unit(entry.ws, view): edit(); echo-if-any; pkg = _redo_show_locked(config, ia, ledger, entry, stage)`, followed by today's `packaged:`/`still held:` and `return`.
- `except (LlamaError, HerderError) as exc:` prints `f"error: {exc}"` to stderr and `continue`s to the same show's prompt. `ShowChanged`, `IAError`, `TaskFailed` and `RateLimited` all fall in these two classes.
- `KeyboardInterrupt` and any other exception propagate after the restore, ending the walkthrough. `[u]` is wrapped in the same `try`.
- Plan's call: the view is not re-captured after a failure. A show that another command changed keeps refusing until the operator skips it and re-runs triage, so nothing is applied against content the operator was not shown.

- [ ] **Step 1: Drop `_stub_redo`'s `_redo_show` patch (only `_redo_show_locked` remains), then write the failing tests**

```python
def test_a_failed_triage_edit_prints_the_error_restores_and_returns_to_the_prompt(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); before = tree_bytes(ws.dir)
    monkeypatch.setattr(cli, "_redo_show_locked", lambda *a, **k: (_ for _ in ()).throw(LlamaError("boom")))
    r = cli_invoke(cfg, "triage", input="o\ns\n")
    assert r.exit_code == 0, r.output
    assert "error: boom" in r.output and r.output.count(PROMPT) == 2
    assert tree_bytes(ws.dir) == before            # still held

def test_a_triage_edit_whose_show_changed_meanwhile_refuses_and_changes_nothing(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); calls = _stub_redo(monkeypatch)
    def picker(show):
        write_artifact(ws.overrides, Overrides(exclude=["other.mp3"])); return ["a.mp3"], False
    monkeypatch.setattr(cli, "_pick_excludes", picker)
    r = cli_invoke(cfg, "triage", input="e\ns\n")
    assert "changed by another command; run it again" in r.output
    assert read_overrides(ws).exclude == ["other.mp3"] and calls == []

def test_triage_prompts_are_answered_without_the_show_lock(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); _stub_redo(monkeypatch); seen = []
    def picker(show):
        with file_lock(ws.lock, blocking=False):
            seen.append("free")
        return ["a.mp3"], False
    monkeypatch.setattr(cli, "_pick_excludes", picker)
    assert cli_invoke(cfg, "triage", input="e\n").exit_code == 0 and seen == ["free"]

def test_ctrl_c_in_a_triage_edit_restores_and_ends_the_walkthrough(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); _held_show(tmp_path, slug="gratefuldead-1974-01-01")
    before = tree_bytes(ws.dir)
    monkeypatch.setattr(cli, "_redo_show_locked", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    r = cli_invoke(cfg, "triage", input="v\ns\n")
    assert r.exit_code != 0 and r.output.count(PROMPT) == 1      # the second show is never offered
    assert tree_bytes(ws.dir) == before

def test_a_failed_metadata_edit_restores_the_overrides(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path)
    monkeypatch.setattr(cli, "_redo_show_locked", lambda *a, **k: (_ for _ in ()).throw(LlamaError("refused")))
    r = cli_invoke(cfg, "triage", input="m\nNew Hall\n\n\n\n\ns\n")
    assert "error: refused" in r.output and not ws.overrides.exists()
```
(Imports: `from helpers import tree_bytes`, `from llama.errors import LlamaError`, `from llama.locks import file_lock`, `from llama.models import Overrides`. Check `_held_show`'s second slug against `build`'s `pid` default. If two shows share a pid, pass a distinct `pid=` the way `_packaged_show` does.)

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_triage.py -q`
Expected: the new tests FAIL. The error escapes triage instead of returning to the prompt, nothing restores, and `_metadata_editor` writes before the redo.

- [ ] **Step 3: Implement `_interactive_resolve`/`_metadata_editor` as specified above**

Add to `CLAUDE.md`'s `llama triage` entry: "each edit is one unit like `fix`'s. A failure prints `error: …`, restores the show and returns to the same show's prompt. Ctrl-C ends the walkthrough after the restore."

- [ ] **Step 4: Run the file's tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_triage.py packages/llama/tests/test_cli.py -q`, then `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_triage.py CLAUDE.md
git commit -m "feat(triage): edits run as restoring units and a failure returns to the prompt (slice C)"
```

---

### Task 8: Mutation run on slice B's conditions and slice C's restore and re-resolve

**Files:** none committed, unless a survivor needs a test.

The recipe for each mutant (spec "Measurement and acceptance"; CLAUDE.md):
1. Write the predicted red test (`file::name`) down **before** flipping the mutant.
2. Fresh copy per mutant: `M=$(mktemp -d "$TMPDIR/mut-XXXX"); rsync -a --exclude .venv --exclude .git "$W/" "$M/tree/"`. Apply the mutant in `$M/tree` only.
3. Prove the shadowing: `cd "$M/tree" && PYTHONPATH="$M/tree/packages/llama/src:$M/tree/packages/herder/src" PYTHONPYCACHEPREFIX="$M/pyc" "$W/.venv/bin/python" -c "import llama; print(llama.__file__)"` must print a path under `$M/tree`.
4. Run with the same environment: `... "$W/.venv/bin/python" -m pytest <test files> -q`. Never use `.venv/bin/pytest`.
5. Record `mutant → predicted → caught by (test id) | SURVIVED`. A mutant counts as caught only by the predicted test or another named test, never by "some failure". A survivor gets a test (committed as `test: pin <mutant>`) or a written equivalence argument.

**Mutants (predicted red test in brackets):**

Slice B (`gather.venue_tie_break` and the chain), test file `test_stage_gather.py`:
- B1 count test `== max(...)` replaced with `>= 1` [`test_a_majority_keeps_the_consensus`]
- B2 city gate removed [`test_a_tie_whose_selected_city_is_incompatible_ships_the_vote_unchanged`]
- B3 returned city `sel_city or candidate.city` replaced with `sel_city` [`test_a_tie_with_a_blank_selected_city_keeps_the_vote_city`]
- B4 returns the raw `sel.venue` instead of the stripped one [`test_tie_ships_the_selected_recordings_string_without_jerrybase`]
- B5 the whitespace guard dropped (`sel.venue` truthiness only) [`test_a_whitespace_only_selected_venue_never_ships`]
- B6 no-event arm does not apply `tie` [`test_tie_ships_the_selected_recordings_string_without_jerrybase`]
- B7 unflagged-1a arm does not apply `tie` [`test_1a_tie_ships_the_selected_string_when_cities_agree`]
- B8 `tie` also applied in flagged 1a [`test_1a_tie_keeps_the_vote_when_the_cities_conflict`]
- B9 step 1 applies `tie` without testing it against jerrybase [`test_step_1_tie_keeps_the_vote_when_jerrybase_does_not_corroborate_the_selected_string`]
- B10 step 1's test on the selected string drops the city half [`test_step_1_tie_keeps_the_vote_when_the_selected_string_is_newly_equivalent_and_cities_conflict`]
- B11 `tie` applied in the `two_venue_signature` arm [`test_the_signature_blocks_the_swap_when_the_selected_tape_agrees_with_jerrybase`]

Slice C (`show_unit.py`; CLI view capture), test files `test_show_unit.py`, `test_fix.py`, `test_triage.py`, `test_redo_cmd.py`:
- C1 restore step (a) removed (new files kept) [`test_show_unit.py::test_a_failed_unit_restores_every_file_byte_identical`]
- C2 restore step (b) removed (no write-back) [same]
- C3 restore step (c) removed (new audio kept) [`test_redo_cmd.py::test_package_failure_on_purged_audio_removes_new_audio_and_restores_manifest`]
- C4 restore's directory cleanup removed [`test_new_directories_created_by_a_failed_unit_are_removed`]
- C5 `except BaseException` replaced with `except Exception` [`test_keyboard_interrupt_restores_and_re_raises`]
- C6 the `raise` after restore removed [`test_a_failed_unit_restores_every_file_byte_identical` (`pytest.raises`)]
- C7 `discard_snapshot` after restore removed [`test_a_failed_unit_restores_every_file_byte_identical` (`.txn` absent)]
- C8 a leftover snapshot restored instead of discarded [`test_a_leftover_snapshot_is_deleted_not_restored`]
- C9 snapshot includes `package/audio` [`test_existing_audio_is_never_snapshotted_or_rewritten`]
- C10 restore step (a) also unlinks `.lock` [`test_a_failed_unit_restores_every_file_byte_identical` (`ws.lock.exists()`)]
- C11 view check ignores `overrides` [`test_a_changed_show_refuses_and_changes_nothing[overrides]`]
- C12 view check ignores `show` [`test_a_changed_show_refuses_and_changes_nothing[show]`]
- C13 view check ignores `provenance` [`test_a_removed_show_refuses_with_the_removed_message`]
- C14 `fix` captures its view after the prompt instead of before [`test_fix.py::test_fix_refuses_when_the_show_changed_after_the_prompt`]
- C15 triage re-captures its view inside the branch, after the picker [`test_triage.py::test_a_triage_edit_whose_show_changed_meanwhile_refuses_and_changes_nothing`]

- [ ] **Step 1: Run every mutant by the recipe; fill in the table in the SDD ledger**
- [ ] **Step 2: Add a test for each survivor, re-run that mutant, and confirm it is caught**
- [ ] **Step 3: Full suite green on the unmutated worktree, then commit any added tests**

```bash
git add packages/llama/tests
git commit -m "test: pin mutation survivors (slices B/C)"
```

---

### Task 9: Acceptance measurement with the replay harness (reports only; nothing applied)

**Files:** none in the repo. Outputs go to `~/.llama-harness/small-fixes/`.

**Preconditions:** Tasks 1-8 are committed. `git -C "$W" status --porcelain` prints nothing (a `-dirty` identity makes the predicted lists unusable). The full suite is green. Ask the owner to hold off `llama get`/`fix`/`triage`/`run resume --all` on the library while both arms run, because a changed show makes `compare` exit 2.

- [ ] **Step 1: Base tree at the branch's fork point, with its own venv**

```bash
BASE_SHA=$(git -C "$W" merge-base HEAD main)
B=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-small-fixes-base
git -C /Users/shawn/projects/llama worktree add --detach "$B" "$BASE_SHA"
cd "$B" && python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"
./.venv/bin/python -c "import llama; print(llama.__file__)"     # must be under $B
```

- [ ] **Step 2: Both arms, each with its own tree's interpreter (read-only on `~/.llama`; run in the background)**

```bash
H="$HOME/.llama-harness/small-fixes"; mkdir -p "$H"
(cd "$B" && ./.venv/bin/python scripts/replay_holds.py run --all --out "$H/base.json")
(cd "$W" && ./.venv/bin/python scripts/replay_holds.py run --all --out "$H/cand.json")
```
Expected: each prints `replayed N show(s): ...` with the same N.

- [ ] **Step 3: Compare with the candidate tree (it has `venue_changes.txt`)**

Run: `cd "$W" && ./.venv/bin/python scripts/replay_holds.py compare "$H/base.json" "$H/cand.json" --out "$H/cmp"; echo "exit $?"`
Expected: `exit 0`. On `exit 2` (the library changed between arms), re-run both arms in one sitting. On `exit 3` (the base does not reproduce), stop and report: that is harness drift, not this branch.

- [ ] **Step 4: Check against the spec's acceptance and record the numbers**

- B: `venue_changes.txt`. Record the count of shows. The order of magnitude is the spec's ~270 ties, fewer after the city gate and step 1's test. **`0 with a flag change` is required.** Any flag change is a defect: stop and report it.
- D: `flags.txt` shows `added 0` for every family. `packaged_exposure.txt`'s "newly held" section is `(none)`. Record any title changes from D in `packaged_exposure.txt`/`title_sources.txt`. Few or none are expected.
- C: no harness effect is expected.
- `predicted_list.json`: record its row count. Near zero is expected, because B and D clear no holds by design.

- [ ] **Step 5: Report to the orchestrator (no library writes)**

Report the paths (`$H/base.json`, `$H/cand.json`, `$H/cmp/`), the text of `summary.txt`, and the numbers from Step 4. Then list what the owner should hand-check:
- every `venue_changes.txt` row whose two venue strings are not plain spelling variants of one place;
- every row marked `DELIVERED` (informational: delivered shows keep their spelling until something re-gathers them);
- every D-driven title change.

State plainly that nothing was applied, and that the base worktree at `$B` is left for the owner to remove. Also state that **`predicted_list.json` is tied to this branch's sha**: `llama reapply --from-list` refuses a list whose `sha` differs from the installed code, so after merging the owner re-runs both arms from the merged tree before applying (spec "Apply" is the owner's call).
