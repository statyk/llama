# The taper's set/encore markers win (held-backlog piece 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the selected recording's description (or, failing any marker there, its `notes`) writes a two- or three-set structure in worded markers and llama can pin every boundary exactly on the tape, ship exactly that structure; otherwise compute the show exactly as today.

**Architecture:** Two pure functions in one new module, `llama/taper.py`: `read_taper_structure` (a structure-only reader of the taper's text; `parse_setlist` is untouched) and `place_taper_structure` (the exact placement test). `compute_gather` calls them after today's deterministic alignment and jerrybase anchoring, and when the taper owns the structure it ships the taper's labels, skips the `align_structure` LLM, and turns jerrybase disagreements with the taper's own text into operator notes. `GatherResult` and `StructureInfo` carry a `taper_owned` boolean; `replay.compute_legs` relaxes the stored-`llm` needs-LLM rule only for taper-owned shows. A read-only yield gate runs the two pure functions over the evidence and the whole library before gather is touched. The replay harness gains a shipped-show structure report and an override-stripping mode for scoring.

**Tech Stack:** Python 3.11+, pydantic v2, pytest. Offline tests only (`herder.FakeProvider`, captured fixtures, `test_stage_gather`'s fake IA and `_jb_event` helpers, literal description excerpts).

**Spec:** `docs/superpowers/specs/2026-10-22-taper-set-markers-design.md` (approved 2026-10-22, review mode Opus). Every implementer reads the spec sections their task names, plus this task, plus Global Constraints. Evidence: `docs/superpowers/2026-10-22-taper-set-markers-evidence/` (`classified.jsonl`, `sort1.json`).

## Global Constraints

- **`parse_setlist`'s output is byte-identical.** No edit to `setlist.py`'s existing regexes or functions changes what `parse_setlist` returns. `taper.py` may import and call `setlist.py`'s private helpers (`_INLINE_MARKER`, `_TRACK_PREFIX`, `_NUM_PREFIX`, `_NOISE`, `_enumerated_prefix`, `_split_songs`, `is_junk_title`, `_SET_LINE`, `_ENCORE_LINE`); it adds its own regexes for anything new. Titles never change: any title change in the acceptance arms is a defect.
- **Byte-identical, never edited:** `songs.normalize_song`, `songs.DEFAULT_ALIASES`, `titles.is_real_title`, `titles._TRACK_NUM_PREFIX`, `structure._STRUCTURE_PREFIX`, `structure._FILLER`/`is_filler`, `structure._ENCORE_MARKER`, `jerrybase.closer_contradictions`'s matching, and every do-not-retune constant in `CLAUDE.md` (junk, tail-guard, `align()`'s `lookahead=8`, `_RECOVER_*`, sibling-align `AUTO`/`FLOOR`/`MIN_ANCHORS`, `_ENUMERATED_*`, `RIGHT_SHOW_*`, `ADJACENT_DAY_WINDOW`). Every code-quality review greps the diff for these names.
- **Recognised forms are exactly section 1's list.** Numbered: `Set` + 1–3 / `one`–`three` / `I`–`III` (word-bounded), `First`/`Second`/`Third Set`, `1st`/`2nd`/`3rd Set`, with decoration (dashes, asterisks, tildes, brackets, parentheses, `=`), alone or followed by `:`/`-` and songs; `Disc N (Set M)`, `Disc N - Set M`, `Disc N / Set M`. Encore: line-start (after decoration and after track-prefix stripping) `Encore`/`Encores`/`ENC`/`E`, followed by `:` or `- ` and songs or alone on the line; `Encore 1:`/`Encore #1:`/`1st Encore:`; plus the mid-line `Set II:`/`E:`/`Encore:` that `setlist._INLINE_MARKER` already splits. Set 4–9 (`Set 4`, `Set IV`, `Set Four`, `4th Set`) is recognised for voiding only. The builder adds no other form; Task 3's measurement may only drop or narrow one.
- No new config keys, no new CLI flags on `llama`. `scripts/replay_holds.py` and the new `scripts/taper_probe.py` may gain options.
- `StructureInfo.taper_owned: bool = False` and `GatherResult.taper_owned: bool = False` are the only new persisted/returned fields. Old show dirs (no key) read as `False`.
- Operator notes from this piece go to `GatherResult.notes` (`op_notes`, i.e. `notes.json`), never to `StructureInfo.conflicts`.
- Fixed strings: operator note `set breaks from the taper's markers (was <breaks>)`; set-count note `structure has <N> sets but jerrybase shows <M> (taper's markers)`; closer note `jerrybase set closer '<closer>' is not at a set break (taper's markers)`.
- `process_show` stays lock-free. Lock order stays run ⊃ show ⊃ ledger.
- Tests run from the worktree root as `./.venv/bin/python -m pytest ...`; never bare `pytest`, never `.venv/bin/pytest` from a copy (CLAUDE.md). Each task ends with the full suite green: `./.venv/bin/python -m pytest -q`.
- Tests are offline: no `~/.llama` reads in unit tests. "Real-case" tests embed the verbatim description excerpt (copied once from `~/.llama/cache/md_<identifier>.json`) and a minimal track list as literals.
- Every behavioural change gets a test that fails on today's code. Tests that only pin existing behaviour are marked **(pin)**.
- Never write to `~/.llama`. Probe and harness outputs go under `~/.llama-harness/piece2/`. No task runs `reapply`, `deliver`, `rm`, `fix` or `redo` against the live library.
- One commit per task, ending with the attribution trailer the orchestrating session specifies.

## Review Focus

1. **A description whose encore exists only in a form neither recognised nor vetoed** (anything the reader and `parse_setlist` both miss, e.g. `(Encore)` after a song). Expected: never "last set runs to the end" silently when encore-like text is present. Test: Task 1 `test_encore_like_text_anywhere_vetoes` (a parenthetical `(Encore)` on a song line, `encore break`, `E. Song`).
2. **A track list where the taper's set-B first song is also the set-A last song's segue partner on one merged track** (`Let It Grow > Greatest Story` as one file across a break). Expected: unplaced. Test: Task 2 `test_merged_track_spanning_the_boundary_is_unplaced`.
3. **A show with an operator `set_breaks`/`encore_after` override.** Expected: the reader never runs; output identical to today. Test: Task 4 `test_structure_override_bypasses_the_taper` **(pin)**.
4. **Notes as source with lineage noise** (`Set 1: MSR> C> DAT`). Expected: asserts or not, it never places, so today's structure. Test: Task 4 `test_notes_lineage_never_places`.
5. **A stored-`llm` show whose candidate is taper-owned but whose taper encore is absent while `parse_setlist` finds one.** Expected: the cross-check means not owned, so still needs-LLM. Test: Task 6 `test_cross_check_failure_keeps_stored_llm_needs_llm`.

---

### Task 0: Worktree and venv (orchestrator, once)

**Files:** none in the repo.

- [ ] **Step 1:** `cd /Users/shawn/projects/llama && git worktree add .claude/worktrees/taper-markers held-backlog-taper-markers` (switch the main checkout to `main` first if `held-backlog-taper-markers` is checked out there). `W=/Users/shawn/projects/llama/.claude/worktrees/taper-markers`.
- [ ] **Step 2:** `cd "$W" && python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
- [ ] **Step 3:** Run `cd "$W" && ./.venv/bin/python -c "import llama; print(llama.__file__)"`. Expected: a path under `$W/`.
- [ ] **Step 4:** Run `./.venv/bin/python -m pytest -q`. Expected: `4047 passed, 1 skipped` (the v2.15.0 baseline; record the exact line).

---

### Task 1: The structure-only reader, `read_taper_structure`

**Spec:** sections 1 and 2.

**Files:**
- Create: `packages/llama/src/llama/taper.py`
- Test: `packages/llama/tests/test_taper.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class TaperItem:
    title: str          # song text after _emit_items-style cleaning
    set: str            # "1" | "2" | "3" | "encore"

@dataclass(frozen=True)
class TaperText:
    items: tuple[TaperItem, ...]   # ordered song items (non-filler), every item labelled
    asserts: bool                  # True only for a valid 2-3 numbered-set structure
    has_encore: bool               # a recognised encore marker started the encore
    encore_like: bool              # encore-like text outside a recognised marker (veto input)
    reason: str | None             # why asserts is False: "no markers", "one set",
                                   # "void: <rule>", "cross-check: <label>", None when asserts

def read_taper_structure(text: str) -> TaperText: ...
def taper_text_for(meta: dict) -> tuple[str, str]:
    """(text, source) with source "description" | "notes" | "none": the description when it
    has any recognised marker, else the notes (string or list) when they have one, else "none"."""
```

- [ ] **Step 1: Write the failing tests.** In `test_taper.py`, one test per bullet, each with a verbatim excerpt literal (copy it from `~/.llama/cache/md_<identifier>.json`; cite the identifier in a comment):
  - `test_worded_headers_assert_two_sets_and_encore`: `acousticsyndicate-2005-05-29`'s description → `asserts`, sets `["1","2","encore"]` in order, `has_encore`.
  - `test_disc_with_set_headers`: a `Disc 2 (Set 2)` description → set 2 starts at that header.
  - `test_leading_block_is_set_one_only_before_set_two`: text with an unlabelled block then `Set II:` → block items are `"1"`; text with lines before `Set 1:` → those lines produce no items.
  - `test_track_prefix_stripped_before_markers`: `tedeschitrucksband-2019-02-16` (`18. E: Let's Go Get Stoned`) → encore starts there; `3. Encore: Higgins` likewise.
  - `test_inline_encore_marker`: `gratefuldead-1990-03-22` (`…, Sugar Magnolia, E: It's All Over Now Baby Blue`) → last item `encore`, `has_encore`.
  - `test_numbered_encore_lines_continue`: `Encore 1:` … `Encore 2:` → one encore, both lines' songs in it.
  - `test_set_and_encore_disc_line_asserts_nothing`: `umphreysmcgee-2004-04-14` (`Disc 3 - Set 2 + Encore` … `e:`) → that line changes no label; `e:` starts the encore; `asserts`.
  - `test_continuation_header_asserts_nothing`: `Disc 3 (Set 2 cont.)` → items stay set 2.
  - `test_void_rules`: separate texts for decreasing (`Set 2` then `Set 1`), skipping (`Set 1`, `Set 3`), empty set (`Set 1:` directly followed by `Set 2:`), numbered marker after the encore (`davidnelsonband-2007-09-07`), and `stringcheeseincident-2004-06-19` (`Set 4:`) → each `asserts is False`, `reason` starts `"void:"`.
  - `test_cross_check_against_parse_setlist`: `paf2007-10-12.schoeps.taraszki.barfield.87850.flac24` (`set 3, disc 2`) → `asserts is False`, `reason` starts `"cross-check:"`.
  - `test_one_set_or_encore_only_asserts_nothing`: a lone `Set 1:`; `charliehunter-2001-12-08` (`Early Show`/`Late Show` + `Encore`) → `asserts is False`.
  - `test_unrecognised_forms_are_not_markers`: each of the Giant Sand/Calexico/`signalpath-2005-06-09` `N:` tracklists, the DSO `1:`/`2:`/`3:` disc lines (`darkstarorchestra-2005-11-16` and the three others named in spec section 1: the bare digit lines are neither markers nor items, while `Set 2:`/`E:` still assert), `[1]` footnotes (`moe-2002-06-22`, `kinggizzardandthelizardwizard-2025-08-17`), `(E) With Allie Kral` (`railroadearth-2008-08-17`), Antibalas `[1]…[5]`, `E.Ville`, `B. E. Women`, `E. Rutherford, NJ`, `I Know You Rider`, `J`, `Untitled #12`, `1:08:07`, "Set I is Bobby and Jerry playing acoustic" (`gd1981-10-16`), `Set Intro`, `Set IV` (voids).
  - `test_encore_like_text_anywhere_vetoes`: no recognised encore plus `encore break` / `(Encore)` on a song line / `14 E. Playin' Reprise` (`gratefulshred-2023-11-10`) / `(E)Spectacle` / `\benc\b` → `encore_like is True`; a clean two-set text → `False`.
  - `test_leading_timestamp_and_disc_number_items_dropped`: `-04:41.50- Right in Tune` → title `Right in Tune`; a bare `2:` line and a `(2:33:33)` item → no item.
  - `test_taper_text_for_prefers_description`: description with any marker → `("…", "description")`; description with none and notes with `Set One` → `"notes"`; neither → `"none"`; notes as a list joins with newlines.
  - `test_parse_setlist_unchanged` **(pin)**: for three of the excerpts above, `parse_setlist(text)` equals a stored expected `ParsedSetlist` captured from `main` before this task (generate the expected values on `main` in the same step and paste them as literals).
- [ ] **Step 2:** Run `./.venv/bin/python -m pytest packages/llama/tests/test_taper.py -q`. Expected: FAIL (`ModuleNotFoundError: llama.taper`).
- [ ] **Step 3: Implement `read_taper_structure(text: str) -> TaperText` and `taper_text_for(meta: dict) -> tuple[str, str]` in `taper.py`.** Preprocess as `parse_setlist` does (`<br>`/tags to newlines, `html.unescape`), no truncation; apply `_INLINE_MARKER`'s split; per line strip `_TRACK_PREFIX` (and `_NUM_PREFIX` when `_enumerated_prefix`) before testing for a marker; then song lines through `_NOISE`, `_split_songs`, `is_junk_title`, the leading-timestamp strip and the bare-`\d{1,3}:?`/timestamp-only drop. Filler items (`is_filler`) are kept out of `items`. Validate per spec section 2 (consecutive from 1, strictly increasing, no post-encore numbered marker, no empty set, no set ≥4 mention, 2–3 sets). Last, the cross-check: `parse_setlist(text)`'s labels minus the reader's labels non-empty → `asserts=False, reason="cross-check: <label>"`. The veto regex for `encore_like` is spec section 2's (`\bencores?\b`, `\benc\b`, a song line starting `E.`, `E)`, `E\d`, `(E)`), matched only outside recognised marker lines.
- [ ] **Step 4:** Run the task's tests, then the full suite. Expected: PASS; suite count = baseline + new tests.
- [ ] **Step 5:** Commit `feat(taper): structure-only reader of the taper's set/encore markers`.

---

### Task 2: Exact placement, `place_taper_structure`

**Spec:** section 3.

**Files:**
- Modify: `packages/llama/src/llama/taper.py`
- Test: `packages/llama/tests/test_taper.py`

**Interfaces:**
- Consumes: `TaperText` (Task 1); `Track` (models); `structure.fuzzy_title_eq`, `structure.title_components`, `structure.is_filler`, `structure.TAUTOLOGICAL_TITLE_SOURCES`.
- Produces:

```python
@dataclass(frozen=True)
class TaperPlacement:
    sets: tuple[str, ...]          # per-track labels, parallel to tracks
    boundaries: tuple[int, ...]    # 1-based track index after which each boundary falls

def place_taper_structure(tracks: list[Track], taper: TaperText, *,
                          aliases: dict[str, str], today_sets: list[str]
                          ) -> TaperPlacement | str:
    """The placement, or a decline reason ("unplaced: <A>|<B> <why>")."""
```

- [ ] **Step 1: Write the failing tests** (tracks built inline with `Track(index=…, set="1", title=…, filename=…, title_source="tags")`):
  - `test_places_when_both_sides_match_uniquely_with_filler_between`: set 1 ends `Let It Grow` (track 7), track 8 `tuning`, set 2 opens `Scarlet Begonias` (track 9), `today_sets` all `"1"` (no split in the run) → boundary after 7 (filler goes with B), labels `1`×7 then `2`.
  - `test_filler_keeps_todays_split_point`: today_sets split the filler run after track 8 → boundary after 8, labels taper's.
  - `test_non_filler_between_is_unplaced`: a `Set Break` or `Donor Rap` track between a and b → decline.
  - `test_unresolved_or_tautological_between_is_unplaced`: a `title_source="unresolved"` and a `"setlist-gap"` track between → decline.
  - `test_missing_or_ambiguous_match_is_unplaced`: A's last song matching no track; matching two tracks → decline.
  - `test_repeated_title_across_boundary_is_unplaced`: `Jam` closing set 1 and opening set 2 in the taper's list → decline.
  - `test_merged_track_spanning_the_boundary_is_unplaced`: one track `Let It Grow > Greatest Story Ever Told` with A's last and B's first as its components → decline.
  - `test_order_must_increase`: b before a → decline.
  - `test_tautological_tracks_are_not_evidence`: the only match for A's last song is a `setlist-gap` track → decline.
  - `test_encore_boundary_uses_the_same_test`: set 2's last song → encore's first song placed; labels end `encore`.
  - `test_every_boundary_must_place`: three boundaries, one declines → returns the reason string, not a placement.
  - `test_family_aliases_apply`: `Scarlet` matches `Scarlet Begonias` only when `aliases=GD_SHORTHAND`.
- [ ] **Step 2:** Run them. Expected: FAIL (`ImportError: place_taper_structure`).
- [ ] **Step 3: Implement `place_taper_structure`.** A track matches an item when `fuzzy_title_eq` holds for its title or a `title_components` component (with `aliases`), counting only tracks whose `title_source` is not in `TAUTOLOGICAL_TITLE_SOURCES` and not `"unresolved"`; "also occurs on the other side" uses the same test over the taper's items. Filler rule per spec section 3 (today's split point inside the filler run, else filler with B). Labels are the taper's (`1..n`, `encore`); tracks before the first set-1 song carry `"1"`, tracks after the last song carry the last set's label.
- [ ] **Step 4:** Run the task's tests and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit `feat(taper): exact placement of the taper's boundaries`.

---

### Task 3: Yield gate and marker-form measurement (read-only; CHECKPOINT A)

**Spec:** Measurement, "Gate before building"; Measurement 5.

**Files:**
- Create: `scripts/taper_probe.py`
- Test: `scripts/test_taper_probe.py`

**Interfaces:**
- Consumes: Tasks 1–2; `docs/superpowers/2026-10-22-taper-set-markers-evidence/{sort1.json,classified.jsonl}`; read-only `~/.llama/shows/*/show.json`, `~/.llama/shows/*/provenance.json`, `~/.llama/cache/md_*.json`.
- Produces: `python scripts/taper_probe.py gate --out DIR` and `python scripts/taper_probe.py forms --out DIR`; files under `~/.llama-harness/piece2/gate/`.

- [ ] **Step 1: Write the failing tests** in `scripts/test_taper_probe.py` against a tmp fake library (two show dirs, a cache dir): `test_gate_counts_owned_and_target_matches` (one show owned and matching its target, one unplaced → the summary counts say so), `test_forms_counts_matches_per_form` (a cache with one `Set 2:` and one `ENC:` → per-form counts 1/1 and a sample file listing both), `test_probe_refuses_out_inside_library` (an `--out` under the library root exits 2).
- [ ] **Step 2:** Run them. Expected: FAIL (no script).
- [ ] **Step 3: Implement `scripts/taper_probe.py`** (stdlib + llama; refuses an `--out` overlapping `~/.llama`):
  - `gate`: for the 339 `taper_explicit` yes/partial rows, build tracks from the pre-adjudication track table in `~/.llama-harness/t3/bundles/<slug>.md` (parsed as `sort1.py` does; that is the numbering the adjudicator's targets use, and its set labels are `today_sets`), skipping and counting rows whose verdict renumbers tracks (`sort1.json` `renum`); read the selected recording's `md_<identifier>.json` via `taper_text_for`, run `read_taper_structure` and `place_taper_structure` (`aliases` = `GD_SHORTHAND` when `jerrybase.is_family_artist(artist)`). Report per row `owned | not-asserted(reason) | unplaced(reason)` and, for owned rows, song-level match against the adjudicator target (break positions parsed from the verdict command in `sort1.json`'s `t_breaks`/`t_enc`, filler-only differences in their own class). Write `gate_rows.jsonl` and `gate_summary.txt` (counts by `primary` form). Then the same over **every library show**, with tracks and `today_sets` from its current `show.json` (shows with an operator structure override are counted and skipped): `library_rows.jsonl` and `library_summary.txt` counting owned shows whose labels differ from the stored ones, tiered `songs moved` / `encore folded` (stored has `encore`, taper has none) / `encore added` / `sets merged or split` / `filler only`, with 10 sample slugs per tier.
  - `forms`: per recognised form (and per void/cross-check/veto rule), count matching lines over every `md_*.json` description and notes field in `~/.llama/cache`; write per form every hit on a family artist (`jerrybase.is_family_artist(creator)`) plus 30 random others (fixed seed `20261022`) to `forms_samples.txt`.
- [ ] **Step 4:** Run the tests and the full suite. Expected: PASS.
- [ ] **Step 5:** Run `./.venv/bin/python scripts/taper_probe.py gate --out ~/.llama-harness/piece2/gate` and `… forms --out ~/.llama-harness/piece2/gate`.
- [ ] **Step 6:** Commit `feat(scripts): taper yield gate and marker-form probe`.
- [ ] **Step 7: CHECKPOINT A (orchestrator; reports to the operator before Task 4).** Dispatch an Opus reviewer over `forms_samples.txt` to list every non-marker match that would place a boundary or change ownership (spec Measurement 5's drop criterion), and over `library_summary.txt`'s `encore folded` and `sets merged or split` samples to say whether each is a reader defect. Report up: the gate counts (owned / not asserted / unplaced, and owned-matching-target, by form), the library tiers, and the reviewer's verdicts. **Stop and wait for the operator if** owned rows are fewer than half of the in-scope rows (the 262 description-form rows minus `desc-encore-only` and minus rows whose only markers are unrecognised forms), or if the reviewer finds a defect class. Reader fixes found here go back into Tasks 1–2 (new commits, same tests extended) and Step 5 re-runs.

---

### Task 4: Wire the taper into `compute_gather`

**Spec:** sections 2 (veto on track titles), 4 (precedence, low-confidence flag, provenance), 6.

**Files:**
- Modify: `packages/llama/src/llama/models.py` (`StructureInfo`), `packages/llama/src/llama/stages/gather.py` (`GatherResult`, `compute_gather`'s structure block, roughly lines 1271–1380 and the `StructureInfo` construction near 1519)
- Test: `packages/llama/tests/test_stage_gather.py` (new tests at the end, reusing `_gather`, `_jb_event`, the fake IA fixtures)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: `StructureInfo.taper_owned: bool = False`; `GatherResult.taper_owned: bool = False` (last field, defaulted); `StructureInfo.alignment` may be `"taper"`.

- [ ] **Step 1: Write the failing tests** (each builds a candidate whose chosen `md` description is a literal and whose setlist.fm/jerrybase are stubbed as existing tests do):
  - `test_taper_structure_beats_unlabelled_setlistfm`: setlist.fm one unlabelled set, description `Set 1/Set 2/Encore` that places → shipped labels are the taper's, `structure.taper_owned is True`, `alignment == "taper"`, `GatherResult.taper_owned is True`, operator note `set breaks from the taper's markers (was [])`, no `setlist evidence shows multiple sets…`/`single-set…` flag.
  - `test_taper_agreeing_with_today_keeps_alignment`: description and alignment agree at song level → `alignment == "deterministic"`, `taper_owned is True`, no "was" note.
  - `test_taper_beats_jerrybase_anchoring`: a PLF-shaped one-set jerrybase event, taper two sets → taper labels ship; anchoring's `set breaks anchored from jerrybase …` entry is not in `structure.conflicts`.
  - `test_taper_owned_skips_align_structure`: low coverage, no anchoring, `align_provider=None` → `"align_structure"` not in `needs_llm`, and the reader-coverage rule: reader coverage ≥ threshold → no `low-confidence structure alignment`; reader coverage < threshold → that flag, still no `needs_llm` entry.
  - `test_track_title_encore_vetoes`: taper has no encore marker, a track titled `Encore: Box Of Rain` → `taper_owned is False` and the shipped labels, flags and `alignment` equal those of the same candidate gathered with a marker-free description.
  - `test_not_owned_is_exactly_today` **(pin)**: an unplaceable taper text → every field of `GatherResult` equals today's (`taper_owned False`).
  - `test_structure_override_bypasses_the_taper` **(pin)**: `overrides.set_breaks` set → identical to today; `taper_owned False`.
  - `test_notes_lineage_never_places`: description no marker, notes `Set 1: MSR> C> DAT\nSet 2: MSC> DAT> CD` → not owned, today's structure.
  - `test_notes_used_when_description_has_no_marker`: notes with placeable `Set One`/`Set Two` → owned.
  - `test_segues_and_matched_come_from_step_one` : owned show's `segue`/`matched` per track equal the step-1 alignment's.
  - `test_structure_info_created_without_canonical`: no setlist parse and no setlist.fm, taper owns → `structure` is not None, `taper_owned True`.
  - `test_old_structure_info_reads_without_taper_owned` **(pin)**: `StructureInfo.model_validate({...no key...}).taper_owned is False`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement in `compute_gather`**, in the spec's order: (1) deterministic `align` + jerrybase anchoring exactly as today, kept as the step-1 result; (2) `taper_text_for(md["metadata"])`, `read_taper_structure`, the track-title veto (`structure._ENCORE_MARKER` on any track title when `not has_encore`, or `encore_like`) and `place_taper_structure(tracks, …, aliases=family_aliases, today_sets=step1_sets)`; (3) if owned: tracks take the taper's labels with step-1 segues and `matched`; skip the LLM branch; raise `low-confidence structure alignment` only when no anchoring, step-1 coverage < `align_coverage_threshold` and `align(tracks, ParsedSetlist(items=<taper items as SetlistItem>))`'s coverage < threshold; set `alignment = "taper"` and append the "was" op note only when `set_breaks(tracks)` differs from step 1's; drop the anchoring note and `merge_conflicts`; (4) otherwise today's path unchanged. Create `StructureInfo` whenever owned. Return `taper_owned`.
- [ ] **Step 4:** Run the task's tests, `packages/llama/tests/test_stage_gather.py`, and the full suite. Expected: PASS, no existing test changed.
- [ ] **Step 5:** Commit `feat(gather): the taper's markers own the structure when they place exactly`.

---

### Task 5: Jerrybase disagreements become notes on a taper-owned show

**Spec:** section 5.

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (the closer tripwire block near line 1485 and the `structure_guard` call)
- Test: `packages/llama/tests/test_stage_gather.py`

**Interfaces:**
- Consumes: Task 4's owned state and the `TaperText` items (taper's own set count and each set's last song).

- [ ] **Step 1: Write the failing tests:**
  - `test_set_count_disagreement_is_a_note_when_taper_text_disagrees`: taper 2 sets, jerrybase 1 → no `structure has 2 sets but jerrybase shows 1` flag; op note `structure has 2 sets but jerrybase shows 1 (taper's markers)`.
  - `test_agreeing_set_count_raises_neither_flag_nor_note` **(pin)**: taper 2 sets, jerrybase 2 → no set-count flag and no set-count note.
  - `test_closer_flag_is_a_note_when_taper_text_names_another_closer`: jerrybase set-1 closer `China Doll` single-matched mid-set, taper's set-1 last song `Let It Grow` → hard flag absent, op note `jerrybase set closer 'China Doll' is not at a set break (taper's markers)`.
  - `test_closer_flag_stays_hard_when_taper_text_agrees`: taper's set-1 last song equals jerrybase's closer but the placed break is elsewhere (construct via a filler-split case) → hard flag kept.
  - `test_closer_for_a_set_the_taper_lacks_is_a_note`: jerrybase 3 sets, taper 2 → set-3 closer flag becomes a note.
  - `test_tripwire_skipped_when_numbered_breaks_came_from_anchoring` **(pin)**: not owned, anchoring succeeded → no tripwire, as today.
- [ ] **Step 2:** Run them. Expected: FAIL for the behavioural ones.
- [ ] **Step 3: Implement.** On an owned show: compute `closer_contradictions` as today, then for each hard flag map jerrybase set k by name to the taper's set k (jerrybase's last numbered set ↔ "last"), demote to the fixed note when the taper has no set k or its last song differs (`fuzzy_title_eq`) from jerrybase's closer; demote the set-count flag when the taper's numbered set count differs from jerrybase's. Not owned: unchanged.
- [ ] **Step 4:** Run the task's tests and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit `feat(gather): jerrybase disagreements with the taper's own text are notes`.

---

### Task 6: The stored-`llm` relaxation in `replay.compute_legs`

**Spec:** section 7. Strict surface.

**Files:**
- Modify: `packages/llama/src/llama/replay.py` (`compute_legs`, the `"stored alignment llm"` line)
- Test: `packages/llama/tests/test_replay.py`, `packages/llama/tests/test_reapply.py`

**Interfaces:**
- Consumes: `GatherResult.taper_owned` (Task 4).

- [ ] **Step 1: Write the failing tests:**
  - `test_stored_llm_taper_owned_is_replayable`: a library show with stored `alignment="llm"` whose description places → `"stored alignment llm"` not in `legs.needs_llm`.
  - `test_stored_llm_alignment_is_needs_llm` stays as is **(pin)**; add `test_stored_llm_deterministic_candidate_stays_needs_llm` (candidate coverage above threshold, no taper markers) and `test_stored_llm_anchored_candidate_stays_needs_llm`.
  - `test_cross_check_failure_keeps_stored_llm_needs_llm`: description `Set 1/Set 2` plus an encore only `parse_setlist` sees → not owned → still needs-LLM.
  - `test_track_title_veto_keeps_stored_llm_needs_llm`.
  - In `test_reapply.py`: `test_reapply_processes_a_taper_owned_stored_llm_show` (a held stored-`llm` show whose candidate is taper-owned and structure-changed is refused without `--allow-structure-change` and processed with it) — reuse the existing reapply fixtures.
- [ ] **Step 2:** Run them. Expected: the new replayable test FAILS.
- [ ] **Step 3: Implement** `if stored.structure is not None and stored.structure.alignment == "llm" and not gathered.taper_owned:`. Nothing else in `replay.py` changes.
- [ ] **Step 4:** Run `test_replay.py`, `test_reapply.py`, and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit `feat(replay): a taper-owned candidate no longer needs the stored LLM structure`.

---

### Task 7: Harness: `taper_owned` in the record, report 3, override stripping

**Spec:** Measurement 1, 3; section 7 (listing moved stored-`llm` shows).

**Files:**
- Modify: `packages/llama/src/llama/replay.py` (`ShowReplay.taper_owned: bool = False`, set from `gathered.taper_owned`), `scripts/replay_holds.py`
- Test: `scripts/test_replay_holds.py`, `packages/llama/tests/test_replay.py`

**Interfaces:**
- Produces: `replay_holds.py run --strip-structure-overrides` (arm key `"structure_overrides_stripped": true`); `compare` writes `taper_changes.txt` (added to `OUTPUT_FILES`); `taper_probe.py score --arm ARM --out DIR`.

- [ ] **Step 1: Write the failing tests:**
  - `test_record_carries_taper_owned` (test_replay.py).
  - `test_taper_changes_report_tiers_and_states`: two fake arms where a delivered show's set labels change with songs moving, a packaged show changes filler only, a third changes provenance only → `taper_changes.txt` lists them under `songs moved` / `filler labels only` / `provenance only`, each row with base breaks, candidate breaks, stored breaks and state; a delivered row whose `delivery_path/<slug>/manifest.json` has `dj_audio` is marked `voiced` (use `cli._destination_is_voiced`).
  - `test_taper_changes_lists_unreplayable_and_slfm_miss_shipped_rows`, and `test_taper_changes_counts_not_owned_needs_llm_rows` (needs-LLM in the candidate and `taper_owned False` → counted on one line, not listed; needs-LLM base with owned candidate → listed with the stored structure as "before").
  - `test_stored_llm_moved_shows_listed_with_segue_changes`.
  - `test_strip_mode_removes_only_structure_overrides`: a show whose overrides hold `exclude`, `titles`, `set_breaks`, `encore_after` → the replay used overrides with only `set_breaks`/`encore_after` removed; the arm is stamped; the live `overrides.json` is untouched (hash before/after).
  - `test_compare_refuses_mixed_strip_arms_and_writes_no_lists_for_stripped`: base unstripped vs cand stripped → exit 2; both stripped → no `*_list.json` written.
  - `test_score_counts_matches_against_adjudicator_targets` (taper_probe `score` over a two-row fake stripped arm).
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.** Strip mode: for each target, build a shadow show dir under the scratch root holding copies of `provenance.json`, `show.json`, `vetting.json`, the briefing files and an `overrides.json` with `set_breaks`/`encore_after` removed, and replay that shadow `ShowWorkspace` (never a `compute_legs` parameter). `taper_changes.txt`: "before" is the base arm's replayed sets, or the stored structure where the base row is needs-LLM; tiers as above. `score`: song-level comparison of the stripped candidate arm with `sort1.json`'s targets for the `classified.jsonl` rows, by `primary`, filler-only differences separate, the 8 named disagreements scored by spec's restated expectations.
- [ ] **Step 4:** Run the tests and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit `feat(harness): taper_changes report, override stripping and scoring`.

---

### Task 8: Mutation run (scratch copy only)

**Spec:** Measurement 6.

**Files:** none committed except `docs/superpowers/2026-10-22-taper-set-markers-sdd/mutation.md`.

- [ ] **Step 1:** Make a scratch copy (`git archive HEAD | tar -x -C <scratch>`), run from it with `PYTHONPATH=<scratch>/packages/llama/src:<scratch>/packages/herder/src` and `<worktree>/.venv/bin/python -m pytest`, after proving shadowing with a planted sentinel (memory: [[mutation-testing-from-a-copied-tree]]); isolate `PYTHONPYCACHEPREFIX` per mutant.
- [ ] **Step 2:** For each mutant, name the expected red test before flipping it ([[mutation-scoring-needs-a-prediction]]): (a) placement accepts a non-filler track between a and b; (b) placement accepts a non-unique match; (c) the repeated-title check removed; (d) the set-number rule accepts a skip; (e) post-encore numbered marker ignored; (f) the cross-check removed; (g) the `encore_like` veto removed; (h) the track-title veto removed; (i) the replay relaxation keys on "no LLM call" (`not gathered.needs_llm`) instead of `taper_owned`; (j) the relaxation removed entirely (the Tier 1 pin must catch the inverse); (k) jerrybase closer demotion ignores the taper's text agreement; (l) an `E.` form recognised; (m) a bare `1:` form recognised.
- [ ] **Step 3:** Record each mutant, its predicted test, and the observed result in `mutation.md`. Every mutant must be caught by its predicted test; a surprise catch or a survivor goes back to the owning task.
- [ ] **Step 4:** Commit `docs: taper-markers mutation record`.

---

### Task 9: Docs and acceptance measurement (reports only; CHECKPOINT B)

**Spec:** Measurement 1–5; Applying it.

**Files:**
- Modify: `CLAUDE.md` (one bullet under the Tier 1 guards: the taper rule, its sources, worded forms, whole-or-nothing ownership, the veto and cross-check, the replay relaxation, pointing at the spec)
- Create: `docs/superpowers/2026-10-22-taper-set-markers-evidence/acceptance.md`

- [ ] **Step 1:** Base arm from a clean `main` @ `a26c4d1` tree with its own venv, candidate arm from the branch: `replay_holds.py run --all --out ~/.llama-harness/piece2/{base,cand}.json`; and stripped arms `--strip-structure-overrides --slugs <the 394>` for both.
- [ ] **Step 2:** `replay_holds.py compare base.json cand.json --out ~/.llama-harness/piece2/cmp --no-repro-gate` (the gate fails on this library regardless of code, piece 1), and `taper_probe.py score` on the stripped candidate arm.
- [ ] **Step 3:** Verify zero title changes in `cmp` (any is a defect: back to the owning task).
- [ ] **Step 4:** Dispatch two Opus pre-screens: report 2 (every newly cleared show; completeness against the adjudicator's `partial-tape` tag, the 10 named partial tapes, and the date of every show on which a jerrybase flag became a note) and report 3 (`taper_changes.txt`: every `songs moved` row, a stratified sample of the rest by marker form, every stored-`llm` moved show with its segue changes).
- [ ] **Step 5:** Write `acceptance.md`: arm shas, the score table by form, newly cleared/held counts, `taper_changes.txt` tier counts by state (packaged/delivered/voiced), the pre-screen verdicts verbatim with their sha256 pins.
- [ ] **Step 6:** Update `CLAUDE.md`; commit `docs: taper markers in CLAUDE.md; acceptance record`.
- [ ] **Step 7: CHECKPOINT B (orchestrator → operator).** Report the acceptance numbers and pre-screen findings. Nothing is merged, released or applied without the operator; applying (reapply of held shows, any re-processing of shipped shows) is the separate, operator-gated step in the spec.
