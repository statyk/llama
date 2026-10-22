# The taper's set/encore markers win (held-backlog piece 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the selected recording's description (or, failing any marker there, its `notes`) writes a two- or three-set structure in worded markers and llama can pin every boundary exactly on the tape, ship exactly that structure; otherwise compute the show exactly as today.

**Architecture:** Pure functions in one new module, `llama/taper.py`: `read_taper_structure` (a structure-only reader of the taper's text; `parse_setlist` is untouched), `place_taper_structure` (the exact placement test) and `decide_taper` (the one ownership decision: source, reader, both vetoes, placement). `compute_gather` calls `decide_taper` after today's deterministic alignment and jerrybase anchoring, and when the taper owns the structure it ships the taper's labels, skips the `align_structure` LLM, and turns jerrybase disagreements with the taper's own text into operator notes. `GatherResult` and `StructureInfo` carry a `taper_owned` boolean; `replay.compute_legs` relaxes the stored-`llm` needs-LLM rule only for taper-owned shows. A read-only yield gate runs `decide_taper` over the evidence and the whole library before gather is touched. The replay harness gains taper reports and an override-stripping mode for scoring.

**Gate ordering (a deliberate reading of the spec).** The spec's "Gate before building" runs "before any build task". Here Tasks 1–2 build the pure reader and placement with nothing wired into gather: they are the prototype the gate runs. Task 3 is the gate; nothing touches gather until Checkpoint A passes.

**Tech Stack:** Python 3.11+, pydantic v2, pytest. Offline tests only (`herder.FakeProvider`, captured fixtures, `test_stage_gather`'s fake IA and `_jb_event` helpers, literal description excerpts).

**Spec:** `docs/superpowers/specs/2026-10-22-taper-set-markers-design.md` (approved 2026-10-22, review mode Opus). Every implementer reads the spec sections their task names, plus this task, plus Global Constraints. Evidence: `docs/superpowers/2026-10-22-taper-set-markers-evidence/` (`classified.jsonl`, `sort1.json`).

## Global Constraints

- **`parse_setlist`'s output is byte-identical.** `git diff main -- packages/llama/src/llama/setlist.py` is empty; every code-quality review checks it. `taper.py` may import and call `setlist.py`'s private helpers (`_INLINE_MARKER`, `_TRACK_PREFIX`, `_NUM_PREFIX`, `_NOISE`, `_enumerated_prefix`, `_split_songs`, `is_junk_title`, `_SET_LINE`, `_ENCORE_LINE`); it adds its own regexes for anything new. Titles never change: any title change in the acceptance arms is a defect.
- **Byte-identical, never edited:** `songs.normalize_song`, `songs.DEFAULT_ALIASES`, `titles.is_real_title`, `titles._TRACK_NUM_PREFIX`, `structure._STRUCTURE_PREFIX`, `structure._FILLER`/`is_filler`, `structure._ENCORE_MARKER`, `jerrybase.closer_contradictions`'s matching, and every do-not-retune constant in `CLAUDE.md` (junk, tail-guard, `align()`'s `lookahead=8`, `_RECOVER_*`, sibling-align `AUTO`/`FLOOR`/`MIN_ANCHORS`, `_ENUMERATED_*`, `RIGHT_SHOW_*`, `ADJACENT_DAY_WINDOW`). Every code-quality review greps the diff for these names.
- **Recognised forms are exactly section 1's list.** Numbered: `Set` + 1–3 / `one`–`three` / `I`–`III` (word-bounded), `First`/`Second`/`Third Set`, `1st`/`2nd`/`3rd Set`, with decoration (dashes, asterisks, tildes, brackets, parentheses, `=`), alone or followed by `:`/`-` and songs; `Disc N (Set M)`, `Disc N - Set M`, `Disc N / Set M`. Encore: line-start (after decoration and after track-prefix stripping) `Encore`/`Encores`/`ENC`/`E`/`E1`/`E2` (`_ENCORE_LINE`'s `e\d?`), followed by `:` or `- ` and songs or alone on the line; `Encore 1:`/`Encore #1:`/`1st Encore:`; plus the mid-line `Set II:`/`E:`/`Encore:` that `setlist._INLINE_MARKER` already splits. Set 4 or higher (`Set 4`, `Set IV`, `Set Four`, `4th Set`) is recognised for voiding only. Operator ruling 2026-10-22 (Checkpoint A) adds two forms, listed exactly in spec section 1: a numbered header followed directly by a `(duration)`, a `(time range)` or `...` (`SET ONE (50:28)`, `Set One (9:30PM - 10:46PM):`); and the disc-and-set shapes, each carrying `Set` or an ordinal set (`Set 1 Disc 1`, `Set I Disc 1: 74:16`, `set 1 - disc 1`, `Set 1/Disc 1:`, `Disc I 1st Set`, `Disk 1: Set 1`, `Disc 1, Set 1`, `DISC 1 SET ONE`, `DISC 01:SET I :`, `disc 01 [Set I]`, `CD1 Set 1`, `Disc/Set1`, `Disc N: Set M`; `Disc`/`Disk`/`CD` interchangeable), never `Set 1/2` or `(Start Set N)`. The builder adds no other form; Task 3's measurement may only drop or narrow one.
- **Song matching** everywhere in this piece is `structure.fuzzy_title_eq(structure.fuzzy_norm_title(a, aliases), structure.fuzzy_norm_title(b, aliases))` (`fuzzy_norm_title(title: str, aliases: dict[str, str] | None = None) -> str`; `fuzzy_title_eq(a: str, b: str) -> bool` takes already-normalized titles). A merged track's components come from `structure.title_components(title, aliases) -> list[str]`, already normalized, so a component compares as `fuzzy_title_eq(component, fuzzy_norm_title(item, aliases))`.
- No new config keys, no new CLI flags on `llama`. `scripts/replay_holds.py` and the new `scripts/taper_probe.py` may gain options.
- **New fields, all defaulted:** `StructureInfo.taper_owned: bool = False` is the only new persisted field in llama proper. `GatherResult` (in-process, never persisted) gains `taper_owned: bool = False`, `taper: TaperDecision | None = None` (the `decide_taper` result, None on the override path) and `step1_alignment: str | None = None` (today's mechanism before the taper step: `deterministic`/`jerrybase`, or None on the override path); no new field for coverage (an owned show's `StructureInfo.coverage` records the reader's coverage). On the harness record `ShowReplay` only: `taper_owned: bool`, `sets: list[str]` (replayed per-track labels), `filler: list[bool]` (per-track `is_filler`), `taper_source: str | None`, `taper_reason: str | None`, `step1_alignment: str | None`. Old show dirs (no key) read as `False`; base-arm rows (base code) lack the harness keys and read as absent.
- Operator notes from this piece go to `GatherResult.notes` (`op_notes`, i.e. `notes.json`), never to `StructureInfo.conflicts`.
- Fixed strings: operator note `set breaks from the taper's markers (was <breaks> <labels>)`; set-count note `structure has <N> sets but jerrybase shows <M> (taper's markers)`; closer note `jerrybase set closer '<closer>' is not at a set break (taper's markers)`.
- `process_show` stays lock-free. Lock order stays run ⊃ show ⊃ ledger.
- Tests run from the worktree root as `./.venv/bin/python -m pytest ...`; never bare `pytest`, never `.venv/bin/pytest` from a copy (CLAUDE.md). Each task ends with the full suite green: `./.venv/bin/python -m pytest -q`.
- Tests are offline: no `~/.llama` reads in unit tests. "Real-case" tests embed the verbatim description excerpt (copied once from `~/.llama/cache/md_<identifier>.json`) and a minimal track list as literals.
- Every behavioural change gets a test that fails on today's code. Tests that only pin existing behaviour are marked **(pin)**.
- Never write to `~/.llama`. Probe and harness outputs go under `~/.llama-harness/piece2/`. No task runs `reapply`, `deliver`, `rm`, `fix` or `redo` against the live library.
- One commit per task, ending with the attribution trailer the orchestrating session specifies.

## Review Focus

1. **A description whose encore exists only in a form neither recognised nor vetoed** (anything the reader and `parse_setlist` both miss, e.g. `(Encore)` after a song). Expected: never "last set runs to the end" silently when encore-like text is present. Test: Task 2 `test_encore_like_text_anywhere_vetoes` (a parenthetical `(Encore)` on a song line, `encore break`, `E. Song`).
2. **A merged track spanning the boundary**: set A's last song on its own track, then one track `Space > Scarlet Begonias` where `Space` belongs to set A and `Scarlet Begonias` opens set B. Expected: unplaced. Test: Task 2 `test_merged_track_spanning_the_boundary_is_unplaced`.
3. **A show with an operator `set_breaks`/`encore_after` override.** Expected: `decide_taper` never runs; output identical to today. Test: Task 4 `test_structure_override_bypasses_the_taper` **(pin)**.
4. **Notes as source with lineage noise** (`Set 1: MSR> C> DAT`). Expected: asserts or not, it never places, so today's structure. Test: Task 4 `test_notes_lineage_never_places`.
5. **A stored-`llm` show whose candidate is taper-owned but whose taper encore is absent while `parse_setlist` finds one.** Expected: the cross-check means not owned, so still needs-LLM. Test: Task 6 `test_cross_check_failure_keeps_stored_llm_needs_llm`.

---

### Task 0: Worktrees and venvs (orchestrator, once)

**Files:** none in the repo.

- [ ] **Step 1:** `cd /Users/shawn/projects/llama && git worktree add .claude/worktrees/taper-markers held-backlog-taper-markers` (switch the main checkout to `main` first if `held-backlog-taper-markers` is checked out there). `W=/Users/shawn/projects/llama/.claude/worktrees/taper-markers`.
- [ ] **Step 2:** `cd "$W" && python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
- [ ] **Step 3:** Run `cd "$W" && ./.venv/bin/python -c "import llama; print(llama.__file__)"`. Expected: a path under `$W/`.
- [ ] **Step 4:** Run `./.venv/bin/python -m pytest -q`. Expected: `4047 passed, 1 skipped` (the v2.15.0 baseline; record the exact line).
- [ ] **Step 5:** Base arm tree: `git worktree add --detach .claude/worktrees/taper-base a26c4d1`, its own `.venv` as in Step 2, and the Step 3 check (`llama.__file__` under `.claude/worktrees/taper-base/`). Task 9's base arm runs only from it.

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
  - `test_decorated_headers`: `[Set One]`, `~Set One~`, `-Set I-` and an own-line `(Set 2)` each start their set; a mid-line `Song (set II)` is not a marker (the song keeps its set).
  - `test_leading_block_is_set_one_only_before_set_two`: text with an unlabelled block then `Set II:` → block items are `"1"`; text with lines before `Set 1:` → those lines produce no items.
  - `test_track_prefix_stripped_before_markers`: `tedeschitrucksband-2019-02-16` (`18. E: Let's Go Get Stoned`) → encore starts there; `3. Encore: Higgins` likewise.
  - `test_inline_encore_marker`: `gratefuldead-1990-03-22` (`…, Sugar Magnolia, E: It's All Over Now Baby Blue`) → last item `encore`, `has_encore`.
  - `test_numbered_encore_lines_continue`: `Encore 1:` … `Encore 2:` and `E1:` … `E2:` → one encore, both lines' songs in it.
  - `test_set_and_encore_disc_line_asserts_nothing`: `umphreysmcgee-2004-04-14` (`Disc 3 - Set 2 + Encore` … `e:`) and `lotus-2005-10-15` (a set-and-encore disc line, later `e:`) → that line changes no label; `e:` starts the encore; `asserts`.
  - `test_continuation_header_asserts_nothing`: `Disc 3 (Set 2 cont.)` → items stay set 2.
  - `test_void_rules`: separate texts for decreasing (`Set 2` then `Set 1`), skipping (`Set 1`, `Set 3`), empty set (`Set 1:` directly followed by `Set 2:`), numbered marker after the encore (`davidnelsonband-2007-09-07`), and `stringcheeseincident-2004-06-19` (`Set 4:`) → each `asserts is False`, `reason` starts `"void:"`. A continuation header and a header line carrying inline songs are not empty sets.
  - `test_cross_check_against_parse_setlist`: `paf2007-10-12.schoeps.taraszki.barfield.87850.flac24` (`set 3, disc 2`) → `asserts is False`, `reason` starts `"cross-check:"`.
  - `test_one_set_or_encore_only_asserts_nothing`: a lone `Set 1:`; `charliehunter-2001-12-08` (`Early Show`/`Late Show` + `Encore`) → `asserts is False`.
  - `test_unrecognised_forms_are_not_markers`: each of the Giant Sand/Calexico/`signalpath-2005-06-09` `N:` tracklists, the DSO `1:`/`2:`/`3:` disc lines (`darkstarorchestra-2005-11-16` and the three others named in spec section 1: the bare digit lines are neither markers nor items, while `Set 2:`/`E:` still assert), `[1]` footnotes (`moe-2002-06-22`, `kinggizzardandthelizardwizard-2025-08-17`), `(E) With Allie Kral` (`railroadearth-2008-08-17`), Antibalas `[1]…[5]`, `E.Ville`, `B. E. Women`, `E. Rutherford, NJ`, `I Know You Rider`, `J`, `Untitled #12`, `1:08:07`, "Set I is Bobby and Jerry playing acoustic" (`gd1981-10-16`), `Set Intro`, `Set IV` (voids).
  - `test_encore_like_flag`: no recognised encore plus `encore break` / `(Encore)` on a song line / `14 E. Playin' Reprise` (`gratefulshred-2023-11-10`) / `(E)Spectacle` / `\benc\b` → `encore_like is True`; a clean two-set text → `False`.
  - `test_leading_timestamp_and_disc_number_items_dropped`: `-04:41.50- Right in Tune` → title `Right in Tune`; a bare `2:` line and a `(2:33:33)` item → no item.
  - `test_taper_text_for_prefers_description`: description with any marker → `("…", "description")`; description with none and notes with `Set One` → `"notes"`; neither → `"none"`; notes as a list joins with newlines.
  - `test_parse_setlist_unchanged` **(pin)**: for three of the excerpts above, `parse_setlist(text)` equals a stored expected `ParsedSetlist` captured from `main` before this task (generate the expected values on `main` in the same step and paste them as literals).
- [ ] **Step 2:** Run `./.venv/bin/python -m pytest packages/llama/tests/test_taper.py -q`. Expected: FAIL (`ModuleNotFoundError: llama.taper`).
- [ ] **Step 3: Implement `read_taper_structure` and `taper_text_for` in `taper.py`.** Preprocess as `parse_setlist` does (`<br>`/tags to newlines, `html.unescape`), no truncation; apply `_INLINE_MARKER`'s split; per line strip `_TRACK_PREFIX` (and `_NUM_PREFIX` when `_enumerated_prefix`) before testing for a marker; then song lines through `_NOISE`, `_split_songs`, `is_junk_title`, the leading-timestamp strip and the bare-`\d{1,3}:?`/timestamp-only drop. Filler items (`is_filler`) are kept out of `items`. Validate per spec section 2: consecutive from 1, strictly increasing, no post-encore numbered marker, no empty set (a numbered or encore header with no song items before the next numbered/encore header; continuation headers and header lines carrying inline songs are not empty), no mention of set 4 or higher, 2–3 sets. Last, the cross-check: `parse_setlist(text)`'s labels minus the reader's labels non-empty → `asserts=False, reason="cross-check: <label>"`. The `encore_like` regex is spec section 2's (`\bencores?\b`, `\benc\b`, a song line starting `E.`, `E)`, `E\d`, `(E)`), matched only outside recognised marker lines.
- [ ] **Step 4:** Run the task's tests, then the full suite. Expected: PASS; suite count = baseline + new tests.
- [ ] **Step 5:** Commit `feat(taper): structure-only reader of the taper's set/encore markers`.

---

### Task 2: Exact placement and the ownership decision

**Spec:** sections 2 (vetoes) and 3.

**Files:**
- Modify: `packages/llama/src/llama/taper.py`
- Test: `packages/llama/tests/test_taper.py`

**Interfaces:**
- Consumes: `TaperText`, `read_taper_structure`, `taper_text_for` (Task 1); `Track` (models); `structure.fuzzy_title_eq`, `structure.fuzzy_norm_title`, `structure.title_components`, `structure.is_filler`, `structure.TAUTOLOGICAL_TITLE_SOURCES`, `structure._ENCORE_MARKER`.
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

@dataclass(frozen=True)
class TaperDecision:
    placement: TaperPlacement | None   # None when not owned
    taper: TaperText
    source: str                        # "description" | "notes" | "none"
    reason: str | None                 # why not owned (reader reason, "veto: track title",
                                       # "veto: encore-like text", or the placement decline)

def decide_taper(tracks: list[Track], meta: dict, *, aliases: dict[str, str],
                 today_sets: list[str]) -> TaperDecision: ...
```

`compute_gather` (Task 4) and the probe (Task 3) call `decide_taper`, never the parts.

- [ ] **Step 1: Write the failing tests** (tracks built inline with `Track(index=…, set="1", title=…, filename=…, title_source="tags")`):
  - `test_places_when_both_sides_match_uniquely_with_filler_between`: set 1 ends `Let It Grow` (track 7), track 8 `tuning`, set 2 opens `Scarlet Begonias` (track 9), `today_sets` all `"1"` (no split in the run) → boundary after 7 (filler goes with B), labels `1`×7 then `2`.
  - `test_filler_keeps_todays_split_point`: today_sets split the filler run after track 8 → boundary after 8, labels taper's.
  - `test_non_filler_between_is_unplaced`: a `Set Break` or `Donor Rap` track between a and b → decline.
  - `test_unresolved_or_tautological_between_is_unplaced`: a `title_source="unresolved"` and a `"setlist-gap"` track between → decline.
  - `test_missing_or_ambiguous_match_is_unplaced`: A's last song matching no track; matching two tracks → decline.
  - `test_repeated_title_across_boundary_is_unplaced`: `Jam` closing set 1 and opening set 2 in the taper's list → decline.
  - `test_merged_track_spanning_the_boundary_is_unplaced`: a < b, a is A's last song on its own track, b is the merged track `Space > Scarlet Begonias` where `Space` is in the taper's set A and `Scarlet Begonias` opens set B → decline.
  - `test_order_must_increase`: b before a → decline.
  - `test_tautological_tracks_are_not_evidence`: the only match for A's last song is a `setlist-gap` track → decline.
  - `test_encore_boundary_uses_the_same_test`: set 2's last song → encore's first song placed; labels end `encore`.
  - `test_every_boundary_must_place`: three boundaries, one declines → returns the reason string, not a placement.
  - `test_family_aliases_apply`: `Scarlet` matches `Scarlet Begonias` only when `aliases=GD_SHORTHAND`.
  - `test_real_case_declines`: `moe-1997-02-21` (encore boundary unplaced: `Head` and `Interstellar` between) and `darkstarorchestra-2005-11-16` (repeated `NFA`) → each declines, excerpt and track list as literals.
  - `test_track_title_encore_vetoes`: `decide_taper` with no recognised encore marker and a track titled `Encore: Box Of Rain` → `placement is None`, `reason == "veto: track title"`.
  - `test_encore_like_text_anywhere_vetoes`: no recognised encore plus a parenthetical `(Encore)` on a song line, `encore break`, `E. Song` (one text each) → `placement is None`, `reason == "veto: encore-like text"`.
  - `test_encore_like_does_not_veto_when_an_encore_is_marked`: the same encore-like text and an `Encore:` track title with a recognised `Encore:` marker → owned.
  - `test_decide_taper_reports_source_and_reader_reason`: notes-sourced placeable text → `source == "notes"`, owned; a void text → `reason` starts `"void:"`.
- [ ] **Step 2:** Run them. Expected: FAIL (`ImportError: place_taper_structure`).
- [ ] **Step 3: Implement `place_taper_structure` and `decide_taper`.** A track matches an item per Global Constraints' song matching, on its title or any `title_components` component, counting only tracks whose `title_source` is not in `TAUTOLOGICAL_TITLE_SOURCES` and not `"unresolved"`; "also occurs on the other side" uses the same test over the taper's items. Filler rule per spec section 3 (today's split point inside the filler run, else filler with B). Labels are the taper's (`1..n`, `encore`); tracks before the first set-1 song carry `"1"`, tracks after the last song carry the last set's label. `decide_taper`: `taper_text_for(meta)`, `read_taper_structure`; not asserting → reader's reason; then the vetoes, in this order, only when `not taper.has_encore`: `any(_ENCORE_MARKER.search(t.title) for t in tracks)` → `"veto: track title"`, else `taper.encore_like` → `"veto: encore-like text"`; then `place_taper_structure`. Operator ruling 2026-10-22 (Checkpoint A), keep today's encore: after a successful placement, when `not taper.has_encore` and `today_sets` has `"encore"` on any track after the taper's last placed numbered boundary (`today_sets[boundaries[-1]:]`), return not owned with reason `"veto: today's encore"`. It only turns ownership off; no merge.
- [ ] **Step 4:** Run the task's tests and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit `feat(taper): exact placement and the ownership decision`.

---

### Task 3: Yield gate and marker-form measurement (read-only; CHECKPOINT A)

**Spec:** Measurement, "Gate before building"; Measurement 5. This is the spec's pre-build gate, run on the Tasks 1–2 prototype (see the header).

**Files:**
- Create: `scripts/taper_probe.py`
- Test: `scripts/test_taper_probe.py`

**Interfaces:**
- Consumes: `decide_taper` (Task 2); `classified.jsonl`, `sort1.json`; read-only library `show.json`/`provenance.json`, cache `md_*.json`, and the adjudication bundles `<bundles>/<slug>.md`.
- Produces: `python scripts/taper_probe.py gate|forms [--root DIR] [--bundles DIR] [--evidence DIR] --out DIR`. Defaults: `--root ~/.llama`, `--bundles ~/.llama-harness/t3/bundles`, `--evidence docs/superpowers/2026-10-22-taper-set-markers-evidence`. Refuses an `--out` overlapping `--root` (exit 2). Outputs under `~/.llama-harness/piece2/gate/`.

- [ ] **Step 1: Write the failing tests** in `scripts/test_taper_probe.py` against a tmp fake library, cache, bundles and evidence dir:
  - `test_in_scope_set_is_fixed_before_the_reader_runs`: rows with `taper_explicit` `yes`/`partial`, other `primary` forms, and a `marker_quote` failing the worded-form regex → only `yes` rows of the three forms with a worded quote are in scope, and the set is the same with `decide_taper` patched to raise.
  - `test_gate_counts_owned_and_target_matches`: one in-scope row owned and matching its target, one unplaced, one owned `renum` row, one owned row with no target, all four in scope → ownership ratio 3/4, target match rate 1/1 (Step 3's definitions), the `renum` and no-target rows counted and listed separately.
  - `test_forms_counts_matches_per_form`: a cache with one `Set 2:` and one `ENC:` → per-form counts 1/1 and a sample file listing both.
  - `test_probe_refuses_out_inside_library`: an `--out` under `--root` exits 2.
- [ ] **Step 2:** Run them. Expected: FAIL (no script).
- [ ] **Step 3: Implement `scripts/taper_probe.py`** (stdlib + llama):
  - **In-scope set, computed without the reader:** `classified.jsonl` rows with `taper_explicit == "yes"`, `primary` in {`desc-set-header`, `desc-disc-with-set`, `desc-inline-marker`}, whose `marker_quote` matches the probe's own fixed worded-form regex `\bset\s*(?:[1-3]|one|two|three|i{1,3})\b|\b(?:first|second|third|1st|2nd|3rd)\s+set\b` (case-insensitive; documented in the script).
  - `gate`: for every `taper_explicit` yes/partial row, build tracks and `today_sets` from the pre-adjudication track table in `<bundles>/<slug>.md` (parsed as `sort1.py` does), read the selected recording's `md_<identifier>.json`, and call `decide_taper` (`aliases` = `GD_SHORTHAND` when `jerrybase.is_family_artist(artist)`). Per row: `owned | not-asserted(reason) | unplaced(reason)`, and for owned rows a song-level match against the adjudicator target (breaks from `sort1.json`'s `t_breaks`/`t_enc`; filler-only differences their own class). **Ownership ratio** = owned / in-scope (every in-scope row, `renum` or not: ownership uses the bundle's pre-adjudication tracks). **Target match rate** = matching / owned rows with a target and not `renum`; rows with no target and `renum` rows are counted and listed separately. Write `gate_rows.jsonl` and `gate_summary.txt` (the in-scope row list, the ratios, counts by `primary`).
  - The same over **every library show**, tracks and `today_sets` from its current `show.json` (shows with an operator structure override counted and skipped): `library_rows.jsonl` and `library_summary.txt` counting owned shows whose labels differ from the stored ones, tiered `songs moved` / `labels renamed` / `encore folded` (stored has `encore`, taper has none) / `encore added` / `sets merged or split` / `filler only`, 10 sample slugs per tier.
  - `forms`: per recognised form (and per void/cross-check/veto rule), count matching lines over every `md_*.json` description and notes field under `<root>/cache`; write per form every hit on a family artist (`jerrybase.is_family_artist(creator)`) plus 30 random others (seed `20261022`) to `forms_samples.txt`.
- [ ] **Step 4:** Run the tests and the full suite. Expected: PASS.
- [ ] **Step 5:** Run `./.venv/bin/python scripts/taper_probe.py gate --out ~/.llama-harness/piece2/gate` and `… forms --out ~/.llama-harness/piece2/gate`.
- [ ] **Step 6:** Commit `feat(scripts): taper yield gate and marker-form probe`.
- [ ] **Step 7: CHECKPOINT A (orchestrator; reports to the operator before Task 4).** The gate ran on the Tasks 1–2 prototype with nothing wired into gather (the header's reading of "before any build task"); say so in the report. Dispatch an Opus reviewer over `forms_samples.txt` to list every non-marker match that would place a boundary or change ownership (spec Measurement 5's drop criterion), and over `library_summary.txt`'s `encore folded` and `sets merged or split` samples to say whether each is a reader defect. Report up: the in-scope count, ownership ratio, target match rate, the `renum`/no-target lists, counts by form, the library tiers, and the reviewer's verdicts. **Stop and wait for the operator if** the ownership ratio is below 0.5, or the reviewer finds a defect class. Reader fixes found here go back into Tasks 1–2 (new commits, same tests extended) and Step 5 re-runs.

---

### Task 4: Wire the taper into `compute_gather`

**Spec:** sections 2 (veto on track titles), 4 (precedence, low-confidence flag, provenance), 6.

**Files:**
- Modify: `packages/llama/src/llama/models.py` (`StructureInfo`), `packages/llama/src/llama/stages/gather.py` (`GatherResult`, `compute_gather`'s structure block, roughly lines 1271–1380 and the `StructureInfo` construction near 1519)
- Test: `packages/llama/tests/test_stage_gather.py` (new tests at the end, reusing `_gather`, `_jb_event`, the fake IA fixtures)

**Interfaces:**
- Consumes: `decide_taper` (Task 2), called as `taper.decide_taper(...)` through the module so tests can monkeypatch `llama.taper.decide_taper`.
- Produces: `StructureInfo.taper_owned: bool = False`; `GatherResult.taper_owned: bool = False`, `GatherResult.taper: TaperDecision | None = None`, `GatherResult.step1_alignment: str | None = None` (last fields, defaulted; in-process only); `StructureInfo.alignment` may be `"taper"`.
- **"Exactly today" oracle:** the pins below compare against the same candidate gathered with `llama.taper.decide_taper` monkeypatched to return a not-owned decision.

- [ ] **Step 1: Write the failing tests** (each builds a candidate whose chosen `md` description is a literal and whose setlist.fm/jerrybase are stubbed as existing tests do):
  - `test_taper_structure_beats_unlabelled_setlistfm`: setlist.fm one unlabelled set, description `Set 1/Set 2/Encore` that places → shipped labels are the taper's, `structure.taper_owned is True`, `alignment == "taper"`, `GatherResult.taper_owned is True`, operator note `set breaks from the taper's markers (was [] …)`, no `setlist evidence shows multiple sets…`/`single-set…` flag.
  - `test_taper_agreeing_with_today_keeps_alignment`: description and alignment agree per track → `alignment == "deterministic"`, `taper_owned is True`, no "was" note.
  - `test_label_rename_at_same_positions_is_recorded`: step 1 ships `1,2,3` and the taper `1,2,encore` at the same break positions → `alignment == "taper"` and the "was" note citing step 1's breaks and labels.
  - `test_taper_beats_jerrybase_anchoring`: a PLF-shaped one-set jerrybase event, taper two sets → taper labels ship; anchoring's `set breaks anchored from jerrybase …` entry is not in `structure.conflicts`.
  - `test_taper_owned_skips_align_structure`: low coverage, no anchoring, `align_provider=None` → `"align_structure"` not in `needs_llm`.
  - `test_owned_low_confidence_uses_reader_coverage`: owned, canonical items present, no anchoring, step-1 coverage < threshold: reader coverage ≥ threshold → no `low-confidence structure alignment`; reader coverage < threshold → that flag, still no `needs_llm` entry; no canonical items → no flag. `StructureInfo.coverage` equals the reader's coverage.
  - `test_track_title_veto_is_exactly_today` **(pin)**: no encore marker, a track titled `Encore: Box Of Rain` → `taper_owned is False` and `GatherResult` equals the oracle's.
  - `test_not_owned_is_exactly_today` **(pin)**: an unplaceable taper text → `GatherResult` equals the oracle's.
  - `test_structure_override_bypasses_the_taper` **(pin)**: `overrides.set_breaks` set → equals the oracle's; `taper_owned False`; a patched `decide_taper` that raises is never called.
  - `test_notes_lineage_never_places`: description no marker, notes `Set 1: MSR> C> DAT\nSet 2: MSC> DAT> CD` → not owned, equals the oracle's.
  - `test_notes_used_when_description_has_no_marker`: notes with placeable `Set One`/`Set Two` → owned.
  - `test_segues_and_matched_come_from_step_one`: owned show's `segue`/`matched` per track equal the step-1 alignment's.
  - `test_owned_show_drops_merge_conflicts_not_owned_keeps_them`: the same merged-track candidate owned, and with `decide_taper` patched to not-owned → `merge_conflicts` entries absent when owned, present otherwise.
  - `test_structure_info_created_without_canonical`: no setlist parse and no setlist.fm, taper owns → `structure` is not None, `taper_owned True`.
  - `test_umphreys_2004_04_14_taper_owned_identical_to_today`: the real excerpt and track list → `taper_owned True`, labels/flags equal the oracle's, `alignment` unchanged, no "was" note.
  - `test_old_structure_info_reads_without_taper_owned` **(pin)**: `StructureInfo.model_validate({...no key...}).taper_owned is False`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement in `compute_gather`**, in the spec's order: (1) deterministic `align` + jerrybase anchoring exactly as today, kept as the step-1 result; (2) unless a structure override is set, `taper.decide_taper(tracks, md["metadata"], aliases=family_aliases, today_sets=step1_sets)`; (3) if owned: tracks take the taper's labels with step-1 segues and `matched`; skip the LLM branch; raise `low-confidence structure alignment` only when `canonical.items` and no anchoring and step-1 coverage < `align_coverage_threshold` and the reader coverage (`align(tracks, ParsedSetlist(items=<taper items as SetlistItem>))`'s) < threshold; record the reader coverage as `StructureInfo.coverage`; when the per-track labels of non-filler tracks differ from step 1's, set `alignment = "taper"` and append the "was" op note with step 1's breaks and labels; drop the anchoring note and `merge_conflicts`; (4) otherwise today's path unchanged. Create `StructureInfo` whenever owned. Return `taper_owned`.
- [ ] **Step 4:** `grep -rn "alignment" packages/emcee packages/transmitter antenna/src` for any reader switching on `structure.alignment`'s value; expected none (a new `"taper"` value is safe). Record the result in the commit message.
- [ ] **Step 5:** Run the task's tests, `packages/llama/tests/test_stage_gather.py`, and the full suite. Expected: PASS, no existing test changed.
- [ ] **Step 6:** Commit `feat(gather): the taper's markers own the structure when they place exactly`.

---

### Task 5: Jerrybase disagreements become notes on a taper-owned show

**Spec:** section 5.

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (the closer tripwire block near line 1485 and the `structure_guard` call)
- Test: `packages/llama/tests/test_stage_gather.py`

**Interfaces:**
- Consumes: Task 4's owned state and the decision's `TaperText`.
- Produces (pure, in `gather.py`):

```python
def demote_jerrybase_flags(hard: list[str], count_flag: str | None,
                           event: JerrybaseEvent, taper: TaperText
                           ) -> tuple[list[str], str | None, list[str]]:
    """(kept hard flags, kept count flag, op notes)."""
```

- [ ] **Step 1: Write the failing tests:**
  - `test_set_count_disagreement_is_a_note_when_taper_text_disagrees`: taper 2 sets, jerrybase 1 → no `structure has 2 sets but jerrybase shows 1` flag; op note `structure has 2 sets but jerrybase shows 1 (taper's markers)`.
  - `test_agreeing_set_count_raises_neither_flag_nor_note` **(pin)**: taper 2 sets, jerrybase 2 → no set-count flag and no set-count note.
  - `test_closer_flag_is_a_note_when_taper_text_names_another_closer`: jerrybase set-1 closer `China Doll` single-matched mid-set, taper's set-1 last song `Let It Grow` → hard flag absent, op note `jerrybase set closer 'China Doll' is not at a set break (taper's markers)`.
  - `test_closer_flag_stays_hard_when_taper_text_agrees`: against `demote_jerrybase_flags` directly, a synthetic hard flag for jerrybase's set-1 closer equal to the taper's set-1 last song → flag kept, no note (the test first asserts the input list really contains the flag).
  - `test_closer_for_a_set_the_taper_lacks_is_a_note`: jerrybase 3 sets, taper 2 → set-3 closer flag becomes a note.
  - `test_encore_closer_maps_to_the_taper_encore`: jerrybase `encore` closer flag, taper encore's last song differs → note; taper has no encore → note.
  - `test_tripwire_skipped_when_numbered_breaks_came_from_anchoring` **(pin)**: not owned, anchoring succeeded → no tripwire, as today.
- [ ] **Step 2:** Run them. Expected: FAIL for the behavioural ones.
- [ ] **Step 3: Implement.** On an owned show: compute `closer_contradictions` as today, then `demote_jerrybase_flags`: iterate `event.sets`; for each set whose closer string appears in a hard flag, map numbered set k to the taper's set k and jerrybase `encore` to the taper's encore; demote to the fixed note when the taper has no such set or its last song differs (Global Constraints' song matching) from jerrybase's closer; demote the set-count flag when the taper's numbered set count differs from jerrybase's. Not owned: unchanged, helper not called.
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
  - `test_cross_check_failure_keeps_stored_llm_needs_llm`: the `paf2007-10-12.schoeps.taraszki.barfield.87850.flac24` excerpt (`set 3, disc 2`, a label only `parse_setlist` sees) → not owned → still needs-LLM.
  - `test_track_title_veto_keeps_stored_llm_needs_llm`.
  - In `test_reapply.py`: `test_reapply_processes_a_taper_owned_stored_llm_show` (a held stored-`llm` show whose candidate is taper-owned and structure-changed is refused without `--allow-structure-change` and processed with it) — reuse the existing reapply fixtures.
- [ ] **Step 2:** Run them. Expected: the new replayable test FAILS.
- [ ] **Step 3: Implement** `if stored.structure is not None and stored.structure.alignment == "llm" and not gathered.taper_owned:`. Nothing else in `replay.py` changes.
- [ ] **Step 4:** Run `test_replay.py`, `test_reapply.py`, and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit `feat(replay): a taper-owned candidate no longer needs the stored LLM structure`.

---

### Task 7a: Harness record fields, override stripping and scoring

**Spec:** Measurement 1; section 7.

**Files:**
- Modify: `packages/llama/src/llama/replay.py` (`ShowReplay` fields, set in `replay_show`), `scripts/replay_holds.py` (`run`, `compare` refusals), `scripts/taper_probe.py` (`score`)
- Test: `packages/llama/tests/test_replay.py`, `scripts/test_replay_holds.py`, `scripts/test_taper_probe.py`

**Interfaces:**
- Produces: `ShowReplay` gains `taper_owned`, `sets`, `filler`, `taper_source`, `taper_reason`, `step1_alignment` (Global Constraints); `replay_holds.py run --strip-structure-overrides` (arm key `"structure_overrides_stripped": true`); `taper_probe.py score --arm ARM [--evidence DIR] --out DIR`.
- `taper_owned`, `sets` and `filler` come from `gathered.show`/`gathered.taper_owned`; `taper_source` = `gathered.taper.source`, `taper_reason` = `gathered.taper.reason` (both None when `gathered.taper` is None), `step1_alignment` = `gathered.step1_alignment` (Task 4's `GatherResult` fields).

- [ ] **Step 1: Write the failing tests:**
  - `test_record_carries_taper_fields` (test_replay.py): an owned and a not-owned replay → `taper_owned`, `sets`, `filler`, `taper_source`, `taper_reason`, `step1_alignment` as expected.
  - Update `test_show_replay_to_dict_has_the_contract_keys_plus_date` to the new key list (the six new keys after `unreplayable`).
  - `test_strip_mode_removes_only_structure_overrides`: a show whose overrides hold `exclude`, `titles`, `set_breaks`, `encore_after` → the replay used overrides with only `set_breaks`/`encore_after` removed; the arm is stamped; the live `overrides.json` is untouched (hash before/after).
  - `test_compare_refuses_mixed_strip_arms_and_writes_no_lists_for_stripped`: base unstripped vs cand stripped → exit 2; both stripped → no `*_list.json` written.
  - `test_score_counts_matches_against_adjudicator_targets` (test_taper_probe.py): `score` over a two-row fake stripped arm.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.** Strip mode: for each target, build a shadow show dir under the scratch root holding copies of `provenance.json`, `show.json`, `vetting.json`, the briefing files and an `overrides.json` with `set_breaks`/`encore_after` removed, and replay that shadow `ShowWorkspace` (never a `compute_legs` parameter). `score`: song-level comparison of the stripped candidate arm's `sets` with `sort1.json`'s targets for the `classified.jsonl` rows, by `primary`, filler-only differences separate (from `filler`), the 8 named disagreements scored by the spec's restated expectations.
- [ ] **Step 4:** Run the tests and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit `feat(harness): taper record fields, override stripping and scoring`.

---

### Task 7b: Harness reports

**Spec:** Measurement 2, 3; section 7 (listing moved stored-`llm` shows).

**Files:**
- Modify: `scripts/replay_holds.py` (`compare`: `--config`, `taper_cleared.txt`, `taper_changes.txt`, both added to `OUTPUT_FILES`; `NOTE_GROUPS`)
- Test: `scripts/test_replay_holds.py`

**Interfaces:**
- Consumes: Task 7a's record fields.
- Produces: `replay_holds.py compare … [--config P]` (reads `delivery_path` for the voiced check; default as `run`'s); `taper_cleared.txt`; `taper_changes.txt`; a `taper` note group.

- [ ] **Step 1: Write the failing tests:**
  - `test_taper_cleared_includes_structure_changed_clears`: base held; candidate outcomes `clears`, `needs-brief` and `structure-changed` → all three listed in `taper_cleared.txt`; a `still-held` candidate → not listed.
  - `test_taper_changes_report_tiers_and_states`: fake arms where a delivered show's songs move between sets, a packaged show's labels are renamed at the same positions, one changes filler only, one provenance only → `taper_changes.txt` lists them under `songs moved` / `labels renamed` / `filler labels only` / `provenance only`, each row with before breaks, candidate breaks, stored breaks, state, `taper_source` and the overruled `step1_alignment`; a delivered row whose `delivery_path/<slug>/manifest.json` has `dj_audio` is marked `voiced` (via `cli._destination_is_voiced`).
  - `test_taper_changes_before_is_stored_labels_with_base_set_changes`: a base row (no `sets` key) → "before" is the stored `show.json` labels with the base row's `set_changes` applied.
  - `test_taper_changes_lists_unreplayable_and_slfm_miss_shipped_rows`, and `test_taper_changes_counts_not_owned_needs_llm_rows` (needs-LLM in the candidate and `taper_owned False` → counted on one line, not listed; needs-LLM base with owned candidate → listed with the stored structure as "before").
  - `test_stored_llm_moved_shows_listed_with_segue_changes`.
  - `test_taper_note_group`: the three fixed note strings land in the `taper` group, the closer note not in `5c.1`; a plain `jerrybase set closer … is not at a set break` stays in `5c.1`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3: Implement.** `taper_cleared.txt`: every show held in the base arm whose candidate outcome is in `CLEARING` or is `structure-changed`. `taper_changes.txt`: "before" is the base arm's replayed `sets`, or, for a base row without `sets`, the stored `show.json` labels with the base row's `set_changes` applied, or the stored structure where the base row is needs-LLM; tiers as in the tests. `NOTE_GROUPS` gains `taper`, checked before `5c.1`; `_notes_by_group` places a note in it when it starts `set breaks from the taper's markers` or ends `(taper's markers)` (two of the three strings are identified by the suffix, not leading words).
- [ ] **Step 4:** Run the tests and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit `feat(harness): taper_cleared and taper_changes reports`.

---

### Task 8: Mutation run (scratch copy only)

**Spec:** Measurement 6.

**Files:** none committed except `docs/superpowers/2026-10-22-taper-set-markers-sdd/mutation.md`.

- [ ] **Step 1:** Make a scratch copy (`git archive HEAD | tar -x -C <scratch>`), run from it with `PYTHONPATH=<scratch>/packages/llama/src:<scratch>/packages/herder/src` and `<worktree>/.venv/bin/python -m pytest`, after proving shadowing with a planted sentinel (memory: [[mutation-testing-from-a-copied-tree]]); isolate `PYTHONPYCACHEPREFIX` per mutant.
- [ ] **Step 2:** For each mutant, the expected red test is named before flipping it ([[mutation-scoring-needs-a-prediction]]):
  - (a) placement accepts a non-filler track between a and b → `test_non_filler_between_is_unplaced`
  - (b) placement accepts a non-unique match → `test_missing_or_ambiguous_match_is_unplaced`
  - (c) the repeated-title check removed → `test_repeated_title_across_boundary_is_unplaced`
  - (d) the set-number rule accepts a skip → `test_void_rules`
  - (e) post-encore numbered marker ignored → `test_void_rules`
  - (f) the cross-check removed → `test_cross_check_against_parse_setlist`
  - (g) `decide_taper`'s encore-like veto removed → `test_encore_like_text_anywhere_vetoes`
  - (h) `decide_taper`'s track-title veto removed → `test_track_title_encore_vetoes`
  - (i) the replay relaxation keys on `not gathered.needs_llm` instead of `taper_owned` → `test_stored_llm_deterministic_candidate_stays_needs_llm`
  - (j1) the relaxation removed → `test_stored_llm_taper_owned_is_replayable`
  - (j2) the relaxation unconditional → `test_stored_llm_alignment_is_needs_llm`
  - (k) closer demotion ignores the taper's text agreement → `test_closer_flag_stays_hard_when_taper_text_agrees`
  - (l) an `E.` form recognised → `test_unrecognised_forms_are_not_markers`
  - (m) a bare `1:` form recognised → `test_unrecognised_forms_are_not_markers`
  - (n) jerrybase anchoring applied after the taper step on an owned show → `test_taper_beats_jerrybase_anchoring`
  - (o) the `\b` dropped from the Set I–III form (`Set Intro` reads as set 1) → `test_unrecognised_forms_are_not_markers`
  - (p) the merged-track-across-boundary rule removed → `test_merged_track_spanning_the_boundary_is_unplaced`
- [ ] **Step 3:** Record each mutant, its predicted test, and the observed result in `mutation.md`. Every mutant must be caught by its predicted test; a surprise catch or a survivor goes back to the owning task.
- [ ] **Step 4:** Commit `docs: taper-markers mutation record`.

---

### Task 9: Docs and acceptance measurement (reports only; CHECKPOINT B)

**Spec:** Measurement 1–5; Applying it.

**Files:**
- Modify: `CLAUDE.md` (one bullet under the Tier 1 guards: the taper rule, its sources, worded forms, whole-or-nothing ownership, the veto and cross-check, the replay relaxation, pointing at the spec)
- Create: `docs/superpowers/2026-10-22-taper-set-markers-evidence/acceptance.md`

- [ ] **Step 1:** Base arm from the Task 0 base worktree (`main` @ `a26c4d1`, its own venv), candidate arm from the branch: `replay_holds.py run --all --out ~/.llama-harness/piece2/{base,cand}.json`; and a stripped candidate arm only, `--strip-structure-overrides --slugs <the 394> --out ~/.llama-harness/piece2/cand-stripped.json`.
- [ ] **Step 2:** `replay_holds.py compare base.json cand.json --out ~/.llama-harness/piece2/cmp --no-repro-gate` (the gate fails on this library regardless of code, piece 1), and `taper_probe.py score --arm cand-stripped.json`.
- [ ] **Step 3:** Verify in `cmp`: zero title changes; every replayable row whose candidate `taper_owned` is false has zero base/candidate differences in shipped fields and flags; and list every newly held show (base outcome not held, candidate `newly-held`/`still-held`/`still-held-package`) with its added flags (Measurement 4). Any title change or not-owned difference is a defect.
- [ ] **Step 4:** Dispatch two Opus pre-screens: report 2 over `taper_cleared.txt` (completeness against the adjudicator's `partial-tape` tag, the 10 named partial tapes, and the date of every show on which a jerrybase flag became a note) and report 3 over `taper_changes.txt` (every `songs moved` and `labels renamed` row, a stratified sample of the rest by marker form, every stored-`llm` moved show with its segue changes).
- [ ] **Step 5:** A Step 3 defect or a pre-screen finding that is a rule defect goes back to the owning task (fix on the branch, re-run from Step 1) before anything below.
- [ ] **Step 6:** Write `acceptance.md`: arm shas, the score table by form, newly cleared/held counts with an explanation for each newly held show, `taper_changes.txt` tier counts by state (packaged/delivered/voiced), the pre-screen verdicts verbatim with their sha256 pins.
- [ ] **Step 7:** Update `CLAUDE.md`; commit `docs: taper markers in CLAUDE.md; acceptance record`.
- [ ] **Step 8: CHECKPOINT B (orchestrator → operator).** Report the acceptance numbers and pre-screen findings. Nothing is merged, released or applied without the operator; applying (reapply of held shows, any re-processing of shipped shows) is the separate, operator-gated step in the spec.
