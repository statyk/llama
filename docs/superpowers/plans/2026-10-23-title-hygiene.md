# Title hygiene (held-backlog piece 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill unresolved tracks from the taper's own description list (D), the item's own lossless tags (C) and short tags the taper's list confirms (slice 4); stop the whole-tape `setlist` rung (S) from shipping junk or shifted titles; and strip narrow cosmetic junk from final titles (slice 5), all without a wrong title shipping silently.

**Architecture:** The rules are pure functions in three new modules: `llama/desc_list.py` (the two admissible-list readers and entry cleaning), `llama/title_hygiene.py` (definitions, the slice 1 gate, D, the S plan, slice 4) and `llama/lossless_titles.py` (C), plus `llama/title_cosmetics.py` (slice 5). One orchestrator, `gather.title_cascade`, runs today's title block (tag layer through 2a) with the new slices placed exactly where the spec puts them, each behind an `enabled` set. Before Checkpoint A it is NOT called by `compute_gather`: a read-only probe runs it over the whole library on the fresh-get view, proves that with every slice off it reproduces today's gather byte-for-byte (gate 0), and scores each slice against the hand-check rows. After the operator's Checkpoint A rulings, `compute_gather` calls it, Q2 and slice 5 are wired, and the replay harness measures acceptance (Checkpoint B).

**Gate ordering.** Tasks 1-11 build pure rules and the unwired orchestrator; Task 12 is harness-only; Tasks 13-14 measure. `compute_gather` is not edited before Checkpoint A. The only edits to live modules before it are additive keyword-only parameters whose defaults reproduce today's behaviour (Task 11), and gate 0 proves that over every library show.

**Tech Stack:** Python 3.11+, pydantic v2, pytest; offline tests (`herder.FakeProvider`, captured fixtures, `test_stage_gather`'s `StubIA`/`MultiIA`, verbatim description excerpts).

**Spec:** `docs/superpowers/specs/2026-10-22-title-hygiene-design.md` (approved; review mode Fable). Every implementer reads the spec sections their task names, this task, and Global Constraints. Evidence: `docs/superpowers/2026-10-22-title-hygiene-evidence/` (hand-check rows `handcheck/<S0..S3,U0..U3,A,A_rev,C,D>/rows.jsonl`; census tooling `census.py`, `dump.py`; census dump `~/.llama-harness/piece3/census/dump.jsonl`).

## Global Constraints

- **Protected, byte-identical, never edited:** `titles.is_real_title`, `titles._TRACK_NUM_PREFIX`, `titles._GLUED_NUM_PREFIX`, `titles._JOINED_NUM_PREFIX`, `titles._ENUMERATED_MIN_FILES`/`_ENUMERATED_MIN_COVERAGE`, `structure._STRUCTURE_PREFIX`, `structure.hygienic_title`, `structure.fuzzy_norm_title`, `structure.fuzzy_title_eq`, `structure.loosely_same_title`/`LOOSE_TITLE_RATIO`, `structure._FILLER`/`is_filler`, every pattern in `placeholders.py`, `songs.normalize_song`/`DEFAULT_ALIASES`/`GD_SHORTHAND`, `gather._RECOVER_BELOW`/`_RECOVER_SIBLING_ABOVE`, `siblings.AUTO`/`FLOOR`/`MIN_ANCHORS`/`INDEPENDENT_TITLE_SOURCES` (never extended), the tail-guard constants, `align()`'s `lookahead=8`, `junk.LOSSLESS_TITLE_FORMATS`, `RIGHT_SHOW_*`, `ADJACENT_DAY_WINDOW`. `parse_setlist`'s outputs stay byte-identical: `git diff main -- packages/llama/src/llama/setlist.py` is empty. Every code-quality review greps the diff for these names. A task touching `titles.py`, `structure.py`, `siblings.py` or `gather.py` says so and keeps the pins in `test_titles.py`, `test_structure.py`, `test_siblings.py` green unedited (`test_align_default_lookahead_is_8` included).
- **One definition.** Check 1 composes `hygienic_title`'s parts (`is_junk_title`, `MAX_TITLE_LEN`, the trailing `:`, `fuzzy_norm_title(t) in metadata_norms`), imported, never re-written; it drops only the `is_real_title` part. setlist-gap and sibling-align keep `hygienic_title` unchanged.
- **Constants fixed before measurement** (Task 1/4/6 define them; no task retunes them after Task 13 runs):
  - `AGREEMENT_FLOOR = 0.5` (spec).
  - `WRITTEN_DURATION_MIN_SHARE = 0.5` (spec: "at least half").
  - `WRITTEN_DURATION_TOL_SEC = 15.0`, `WRITTEN_DURATION_TOL_FRAC = 0.10`; a position fails when `abs(file - written) > max(15.0, 0.10 * written)`. Rationale: taper-written times are rounded to the second and differ from the cut by a few seconds of applause; 10% scales that to long jams; a one-track shift moves the comparison by a whole neighbouring song, normally well over a minute.
  - `SHORT_CORE_LETTERS = 3`: a core with fewer than 3 ASCII letters in its `fuzzy_norm_title` compares by `fuzzy_norm_title` equality only (spec).
  - `SHORT_TAG_WINDOW = 2`, `STEM_SUBSTRING_MIN = 2` (spec, slice 4).
  - Header grammar (spec, fixed): `taper._SET_HEADERS` and `taper._DISC_LABEL`, plus `_DISC_TRACK_HEADER = r"^\s*(?:disc|disk|cd)\s*\d{1,2}\s*[,:]\s*track\s*\d{1,3}\s*$"` (case-insensitive). As an ENTRY test ("header shape"), a `_SET_HEADERS` match counts only when its `rest` group is None or blank.
  - Disc index on a filename stem (basename minus extension), last match wins: `_DISC_INDEX = r"(?<![a-z])(?:cd|disc|disk|d)[\s_\-]*0?(\d{1,2})[\s_\-.]*(?:t|tr|trk|track)[\s_\-]*\d{1,3}"`; set index: `_SET_INDEX = r"(?<![a-z])(?:set|s)[\s_\-]*0?(\d{1,2})[\s_\-.]*(?:t|tr|trk|track)[\s_\-]*\d{1,3}"` (both case-insensitive). Rationale: LMA filenames put the disc or set token directly before the track token (`gd73-06-10d1t04`, `gd77-05-08s1t03`, `bt1997-10-13cd2t03`); requiring the track token and a non-letter before keeps `sbd`, `dsbd` and words out.
  - Entry leader (cleaning step 2): `_ENTRY_LEADER = r"^(?:\.\d{1,3}|\d{1,3}[-.)])\s*(?=[^\d\s])"`; the vote reuses `titles._ENUMERATED_MIN_FILES`/`_ENUMERATED_MIN_COVERAGE` over the list's entries after step 1.
  - Footnote parenthetical: `\s*\(\s*(?:\d{1,2}|[*#^+~@$%]+)\s*\)`. Trailing taper markers: `(?:\s*(?:=>|->|>|\*+|@+))+\s*$`. Leading encore marker: `^\s*(?:e|en|enc|encore)\s*:\s*` (case-insensitive). `Filler:` marker: `^\s*filler\s*:\s*` (case-insensitive). Wrapping quotes: a whole entry in `"…"` or `“…”`.
  - `?`-only: `^[?\s,;.]*\?[?\s,;.]*$`. Annotation: `^\s*w/\s` or `\bopened\b` (case-insensitive). Bare number: `^\d+[.\-)]?$` (spec).
  - Reader (i) empty numbered line (makes both readers inadmissible): `^\s*(?:(?:d|cd|disc)\s*\d+\s*)?(?:t(?:rack)?\s*)?\d{1,3}\s*[.)\-]\s*$`. Plan call: a bare `N` or `N:` line is a disc label in measured descriptions (piece 2's DSO lines) and is NOT an empty entry.
- **Plan readings of the spec** (each reported by the gate so the operator can overrule at Checkpoint A; see Spec questions in the hand-back):
  - Check 1's show-level classes are judged over the entries at positions the rung would fill (the spec's "candidate"); the gate also reports what judging every entry would add (row R15).
  - A numbering restart at 1 with no recognised header (and no disc-prefix change) makes reader (i) inadmissible ("non-contiguous"); an `Encore` header is not in the fixed grammar, so a restart after it is inadmissible too (row R16).
  - C1 per stem: a target whose lossless title agrees with reference (a) or (b) is adopted; one agreeing with neither (absent or disagreeing: "failing both") is adopted only when (c) holds for the show; if any target fails all three, C1 fills nothing on the show (row R17 reports the per-stem alternative). This is the reading under which the spec's derektrucksband-2007-05-27 track 1 becomes `Announcements/crowd`.
  - S ships today's item text (`items[pos].title`); the cleaned form is used only for its tests. D ships the cleaned form.
  - "Wholly untagged" counts a song-like position whose tag-layer title passes `is_real_title` and is not 2b-demoted, whatever its per-track source.
  - C uses the first format in `LOSSLESS_TITLE_FORMATS` order (skipping the delivered one) whose bijection with `recovery_basis` exists and has `title_fraction > 0`; C2's reference is the count-matched list when there is one, else the count-matched canonical.
- **Fixed strings** (operator notes, `notes.json` only, never `structure.conflicts`):
  - show-level decline: `positional fill declined: <rung> <check> (track <n> '<text>')`; per-track: `positional fill declined: <rung> track <n> <check> '<text>'`; Q1: `positional fill declined: setlist wholly untagged tape`. `<rung>` is `desc-position` or `setlist`.
  - C: `lossless title: track <n> '<old>' -> '<new>' (<C1|C2>)`; C skipped: `lossless titles declined: <reason>`.
  - slice 4: `short tag title confirmed by the taper's list: track <n> '<title>'`.
  - slice 5: `cosmetic title strip: track <n> '<old>' -> '<new>'`.
  - Check names: show-level `hygiene:<class>` (classes `header`, `banner`, `annotation`, `filename residue`, `timestamp`, `over length`, `junk title`, `trailing colon`, `no alnum`), `adjacent duplicate`, `tape agreement`, `written durations`, `block size`, `sibling durations`, `agreement`; per-track `slot placeholder`, `metadata`, `filler entry`. `SHIFT_CHECKS` = every show-level name not starting `hygiene:`.
- **New values and fields, all defaulted:** `title_source="desc-position"` (13 characters). In-process only: `GatherResult.self_filled: bool = False`, `GatherResult.title_paths: tuple[str, ...] = ()` (per track `""`, `C1`, `C2`, `S`, `S-deferred`, `D`, `4`, each optionally suffixed `+5`). Harness record only: `ShowReplay.self_filled`, `desc_position` (count), `titles`, `title_sources`, `title_paths`. No persisted model gains a field; old show dirs read unchanged.
- **Slice switches:** `title_hygiene.ALL_SLICES = frozenset({"slice1", "slice2", "slice3", "slice4", "slice5"})` and `ENABLED_SLICES` (= `ALL_SLICES` until Checkpoint A says otherwise). No config key, no `llama` CLI flag. Scripts may take options.
- `process_show` stays lock-free; lock order run ⊃ show ⊃ ledger is untouched.
- Tests run from the worktree root as `./.venv/bin/python -m pytest …`; never a bare `pytest`, never `.venv/bin/*` from a copy (CLAUDE.md). Each task ends with the full suite green. Baseline: `4474 passed, 1 skipped, 8 deselected`.
- Unit tests are offline. A "real-case" test embeds the verbatim description excerpt (copied once from `~/.llama/cache/md_<identifier>.json`; the identifier is in `~/.llama/shows/<slug>/show.json`) and a minimal track list as literals, citing the slug in a comment.
- Every behavioural change gets a test that fails on today's code; a pin is marked **(pin)**.
- Never write to `~/.llama`. Probe and harness output goes under `~/.llama-harness/piece3/`. No task runs `reapply`, `deliver`, `rm`, `fix` or `redo` on the live library; merge, push, tag and release are the operator's.
- One commit per task, ending with the attribution trailer the orchestrating session specifies. Status reports to the parent list every dispatch since the last report with its model.

## Review Focus

1. **A numbered list whose numbering continues across a `Disc 2` header** (`… 10. Song` / `Disc 2` / `11. Song`), and one that restarts at 1 with no header. Expected: the first is one admissible list in two blocks (boundary `disc`); the second is inadmissible. Test: Task 2 `test_numbering_continuing_across_a_header_is_one_list_two_blocks`.
2. **An operator `overrides.titles` position (as-is view).** Expected: no new rung writes it; it counts as an independent title for check 3 and for slice 4's neighbours. Test: Task 11 `test_overrides_survive_every_new_rung_and_anchor_check_3`.
3. **A sibling item whose description copies the selected one**, so the canonical source is `lma:<id>` though the text is the taper's own, with a count-matched list. Expected: S defers, D fills, no double fill. Test: Task 7 `test_copied_sibling_description_canonical_defers_to_d`.
4. **HTML entities and curly quotes in a description** (`Me &amp; My Uncle`, `“Sugaree”`, `Truckin’`). Expected: unescaped, wrapping quotes dropped, apostrophes kept, and check 3 agrees with the tag `Me & My Uncle`. Tests: Task 1 `test_entities_and_curly_quotes_clean`, Task 5 `test_check3_agrees_across_ampersand_and_curly_apostrophe`.
5. **Missing per-file durations** (`length` absent) beside written durations, and on the untagged sibling check. Expected: that position is skipped, nothing raises, the sibling check is inert. Tests: Task 5 `test_written_duration_check_skips_missing_file_lengths`, Task 6 `test_sibling_check_inert_without_durations`.

---

### Task 0: Worktrees and venvs (orchestrator, once)

**Files:** none in the repo.

- [ ] **Step 1:** Switch the main checkout to `main`, then `git worktree add .claude/worktrees/title-hygiene held-backlog-title-hygiene`. `W=/Users/shawn/projects/llama/.claude/worktrees/title-hygiene`.
- [ ] **Step 2:** `cd "$W" && python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`.
- [ ] **Step 3:** `./.venv/bin/python -c "import llama; print(llama.__file__)"` prints a path under `$W/`.
- [ ] **Step 4:** `./.venv/bin/python -m pytest -q` prints `4474 passed, 1 skipped, 8 deselected` (record the exact line).
- [ ] **Step 5:** The base worktree is made in Task 12 Step 6 (it needs Task 12's commit).

---

### Task 1: Entry cleaning, written durations and header shape

**Spec:** slice 1, check 1 (cleaning order and the cleaning fixtures); slice 2, "What it ships", "Written durations". **Implementer: Sonnet.**

**Files:** Create `packages/llama/src/llama/desc_list.py`; Test `packages/llama/tests/test_desc_list.py`.

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class Cleaned:
    text: str                       # the ONE form check 1 tests and D ships
    durations: tuple[float, ...]    # every written duration stripped, seconds, in order
    filler_marked: bool             # the entry began `Filler:` (marker removed from text)
    leader_stripped: bool

def clean_entries(raws: Sequence[str]) -> list[Cleaned]   # runs the leader vote over the list
def clean_one(raw: str, *, strip_leader: bool = False) -> Cleaned
def written_seconds(c: Cleaned) -> float | None           # the single duration; None for 0 or >1
def is_header_shape(text: str) -> bool
```

Order inside `clean_*` (spec check 1 then "What it ships"): `html.unescape`; durations (bracketed `[m:ss]`/`(m:ss)` anywhere; leading `(m:ss) ` and `m:ss - `; tab plus `m:ss`; a trailing `m:ss` preceded by text and whitespace; a trailing `m.ss` after a tab or 2+ spaces; `h:mm:ss` wherever `m:ss` is allowed); the leader under the vote; `Filler:`; footnote parentheticals anywhere; trailing taper markers; a leading encore marker; wrapping quotes; final whitespace strip. A whole entry that is only a time (`2:22`) is not stripped.

- [ ] **Step 1: Write the failing tests:**
  - `test_cleaning_fixtures_from_real_lists`: `clean_entries(["(05:12) 01-?", "(03:43) 02-Sneak Out", "(04:01) 03-X"])` texts are `["?", "Sneak Out", "X"]` (rosehilldrive-2008-12-31); `clean_one(".01  I'm No Good", strip_leader=True).text == "I'm No Good"` (motherhips-2010-10-16); `clean_one("Shot Shot  3.00").text == "Shot Shot"` and its `durations == (180.0,)` (gomez-2006-10-06); `clean_one("(05:12) Bertha").text == "Bertha"` (the spec's `1. (05:12) Bertha` after reader (i) takes the `1.`).
  - `test_duration_forms`: `[4:47]`, `(6:40)`, `Song\t4:47`, `Song 4:47`, `05:12 - Song`, `Song (1:02:03)` each strip to `Song` with one duration in seconds; `Song (4:47) (5:02)` has two durations and `written_seconds` returns None; `clean_one("2:22").text == "2:22"`.
  - `test_leader_stripped_only_under_the_vote`: four entries `01-A, 02-B, 03-C, D` (3 of 4 = 0.75 < 0.8) keep their leaders; `01-A, 02-B, 03-C, 04-D, E` (4 of 5 = 0.8) strip them; two entries `01-A, 02-B` keep them (fewer than 3).
  - `test_date_shaped_entries_keep_their_numbers`: under a passing vote, `09-15-00`, `12.28.99`, `01.` and `01-` are unchanged.
  - `test_markers_and_encore_and_quotes`: `Pyramid County (1) > Little Maggie` → `Pyramid County > Little Maggie`; `Bertha >` and `Dew ->` lose the arrow; `Jack Straw *` and `Jack Straw @` lose the mark; `E: Baby Blue`, `EN: X`, `Encore: X` lose the marker; `"Sugaree"` → `Sugaree`; `Filler: Dark Star` → text `Dark Star`, `filler_marked`.
  - `test_entities_and_curly_quotes_clean`: `Me &amp; My Uncle` → `Me & My Uncle`; `“Sugaree”` → `Sugaree`; `Truckin’` unchanged.
  - `test_header_shape`: True for `Set 2`, `CD 2`, `Disc Two`, `Disc 1, Track 10`, `[Set One]`; False for `Set 2: Bertha`, `"Set" 1:`, `Settle Down`, `Jam`.
- [ ] **Step 2:** `./.venv/bin/python -m pytest packages/llama/tests/test_desc_list.py -q` → FAIL (`ModuleNotFoundError: llama.desc_list`).
- [ ] **Step 3:** Implement in `desc_list.py` with the Global Constraints regexes; `is_header_shape` imports `taper._SET_HEADERS`, `taper._DISC_LABEL`.
- [ ] **Step 4:** Run the file, then the full suite → PASS.
- [ ] **Step 5:** Commit `feat(desc_list): entry cleaning, written durations, header shape`.

---

### Task 2: Reader (i), numbered lines

**Spec:** slice 2 "Source" (i) and its contiguity, header and disc-prefix rules; "A numbered line with no text". **Implementer: Sonnet.**

**Files:** Modify `desc_list.py`; Test `test_desc_list.py`.

**Interfaces:**
- Consumes: `clean_entries` (Task 1).
- Produces:

```python
@dataclass(frozen=True)
class DescList:
    reader: str                       # "numbered" | "parse"
    raws: tuple[str, ...]             # entry text after the taper's own number
    cleaned: tuple[Cleaned, ...]      # clean_entries(raws)
    blocks: tuple[int, ...]           # 0-based block per entry
    boundaries: tuple[str, ...]       # per block boundary: "set" | "disc" | "restart"

def read_numbered(desc: str) -> DescList | str     # a reason string when there is no admissible list
```

Grammar: the census preprocessing (`<br>` and tags to newlines, `html.unescape`); each line matched by the census `NUMLINE`, re-written with named groups and otherwise identical: `^\s*(?:(?:d|cd|disc)\s*(?P<disc>\d+)\s*)?(?:t(?:rack)?\s*)?(?P<num>\d{1,3})\s*[.):\-]?\s+(?P<text>\S.*)$`, skipping lines matching `^\s*\d{1,2}[:/]\d`. When every entry's number has 3 digits with a leading 1-9, read `disc = num // 100`, `track = num % 100`. A block boundary is a non-numbered header line (`_SET_HEADERS` → `set`, `_DISC_LABEL` or `_DISC_TRACK_HEADER` → `disc`) seen since the previous entry, or a disc-prefix change (`disc`). Numbering: the first entry is 1; then `prev + 1`, or 1 when a boundary or a disc-prefix change came since the previous entry. Reasons: `"no numbered lines"`, `"empty entry"`, `"non-contiguous at <num>"`.

- [ ] **Step 1: Write the failing tests:**
  - `test_reads_a_plain_numbered_list`: `1. Bertha\n2. Jack Straw\n3) Deal` → raws `["Bertha", "Jack Straw", "Deal"]`, one block.
  - `test_br_separated_entries`: the same with `<br />` separators.
  - `test_set_header_restart_is_a_new_block`: `Set 1:\n1. A\n2. B\nSet 2:\n=====\n1. C` → three entries, blocks `(0,0,1)`, boundaries `("set",)`.
  - `test_numbering_continuing_across_a_header_is_one_list_two_blocks`: `1. A … 10. J\nDisc 2\n11. K` → 11 entries, blocks split after 10, boundaries `("disc",)`; and `1. A\n2. B\n1. C` (no header) → `"non-contiguous at 1"`.
  - `test_disc_prefix_change_is_a_restart`: `d1t01- A\nd1t02- B\nd2t01- C` → admissible, blocks `(0,0,1)`, boundary `disc`.
  - `test_three_digit_numbers_read_as_disc_prefixed`: `101 A\n102 B\n201 C` → blocks `(0,0,1)`.
  - `test_gaps_are_inadmissible`: `1. A\n2. B\n4. D` → `"non-contiguous at 4"` (the alabamashakes-2012-01-13 and delmccouryband-2004-06-12 shape).
  - `test_empty_numbered_line_is_inadmissible`: `1. A\n07) \n3. C` → `"empty entry"`; a bare `2:` disc line between entries is not an entry and not empty.
  - `test_timestamp_lines_are_not_entries`: `12:30 tuning` is skipped.
  - `test_run_on_line_yields_no_list` (furthur-2012-04-21 excerpt) → a reason string, never a list matching the file count.
- [ ] **Step 2:** Run → FAIL (`ImportError: read_numbered`).
- [ ] **Step 3:** Implement `read_numbered`.
- [ ] **Step 4:** Run the file and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(desc_list): reader (i), numbered lines with blocks and contiguity`.

---

### Task 3: Reader (ii) and `read_desc_list`

**Spec:** slice 2 "Source" (ii), "A numbered line with no text", "When both lists qualify, prefer (i)". **Implementer: Opus** (mapping `parse_setlist`'s items back to the raw lines that produced them, and judging admissibility per line, without changing `parse_setlist`).

**Files:** Modify `desc_list.py`; Test `test_desc_list.py`.

**Interfaces:**
- Consumes: `DescList`, `read_numbered`, `clean_entries`; `setlist.parse_setlist` and its private helpers (`_SET_LINE`, `_LABELED_SET_LINE`, `_ENCORE_LINE`, `_NOISE`, `_may_start_a_show`, `_RECOVER_FLOOR`, `_emit_items`); `jerrybase.artist_key`.
- Produces:

```python
def drop_leading_artist_items(parsed: ParsedSetlist, artist: str) -> ParsedSetlist
def read_parse(desc: str, *, artist: str, clean: Callable[[ParsedSetlist], ParsedSetlist]) -> DescList | str
@dataclass(frozen=True)
class DescRead:
    used: DescList | None             # the count-matched admissible list, (i) preferred
    numbered: DescList | str
    parsed: DescList | str
def read_desc_list(desc: str, n_tracks: int, *, artist: str,
                   clean: Callable[[ParsedSetlist], ParsedSetlist]) -> DescRead
```

`clean` is supplied by the caller (gather: `lambda p: _strip_footnote_markers(drop_leading_artist_items(_strip_head_banner(p, metadata_norms), artist))`); `desc_list` imports no stage. Admissibility per spec (ii): lines above the first marker that header truncation removes, `_NOISE` lines, header-only lines and lines whose items `clean` removed are exempt; every other non-empty raw line must yield exactly one item, judged on the raw line. When the per-line item counts do not sum to `parse_setlist`'s item count, the list is inadmissible (`"per-line count disagrees"`). Blocks: runs of equal `SetlistItem.set` (boundary `set`).

- [ ] **Step 1: Write the failing tests:**
  - `test_parse_items_admissible_one_per_line`: `Set 1:\nBertha\nDeal\nEncore:\nRipple` → raws `["Bertha", "Deal", "Ripple"]`, boundaries `("set",)`.
  - `test_a_line_split_into_two_items_is_inadmissible`: `Bertha > Jack Straw\nDeal` → `"line yields 2 items: …"`.
  - `test_artist_item_dropped_only_in_the_banner`: railroadearth-2004-04-09 excerpt (a `Railroad Earth` song mid-list) keeps that item; a leading `Railroad Earth` banner line is dropped.
  - `test_banner_and_noise_lines_are_exempt`: a description with a venue/date banner and a lineage line above `Set 1:` is admissible.
  - `test_empty_numbered_line_makes_both_readers_inadmissible`: `1. A\n07) \n3. C` → `read_desc_list(...).used is None`, both reasons set.
  - `test_prefers_numbered_when_both_qualify`: a description both readers admit with 3 entries, `n_tracks=3` → `used.reader == "numbered"`; `n_tracks=4` → `used is None`.
  - `test_parse_only_when_numbered_absent`: an unnumbered one-per-line list → `used.reader == "parse"`.
  - `test_parse_setlist_unchanged` **(pin)**: for three of the excerpts above, `parse_setlist(text)` equals a `ParsedSetlist` literal generated on `main` in this step.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the file and the full suite → PASS; `git diff main -- packages/llama/src/llama/setlist.py` is empty.
- [ ] **Step 5:** Commit `feat(desc_list): reader (ii) over parse_setlist items, read_desc_list`.

---

### Task 4: Definitions, comparators and check 1

**Spec:** Definitions; slice 1 "Show-level or per-track", check 1 (decline list, PASS/DECLINE fixtures, "One definition"). **Implementer: Sonnet.**

**Files:** Create `packages/llama/src/llama/title_hygiene.py`; Test `packages/llama/tests/test_title_hygiene.py`.

**Interfaces:**
- Consumes: `Cleaned` (Task 1); `setlist.is_junk_title`, `setlist.MAX_TITLE_LEN`, `titles.is_placeholder_text`, `titles.tag_core`, `placeholders.is_placeholder`, `placeholders.is_timestamp`, `placeholders.looks_like_filename`, `structure.fuzzy_norm_title`, `fuzzy_title_eq`, `loosely_same_title`, `is_filler`.
- Produces:

```python
INDEPENDENT_SOURCES = frozenset({"tags", "sibling-format", "override", "sibling-align"})
DESC_POSITION = "desc-position"
ALL_SLICES: frozenset[str]; ENABLED_SLICES: frozenset[str]
AGREEMENT_FLOOR = 0.5; WRITTEN_DURATION_MIN_SHARE = 0.5
WRITTEN_DURATION_TOL_SEC = 15.0; WRITTEN_DURATION_TOL_FRAC = 0.10
SHORT_CORE_LETTERS = 3; SHORT_TAG_WINDOW = 2; STEM_SUBSTRING_MIN = 2

def agrees(a: str, b: str, aliases: dict[str, str] | None = None) -> bool
    # cleaned copies (clean_one); short core -> fuzzy_norm_title equality; else
    # loosely_same_title on the alias-expanded fuzzy_norm_title forms
def duplicate(a: str, b: str) -> bool        # filler on either side -> False; fuzzy_norm_title equal or fuzzy_title_eq
@dataclass(frozen=True)
class Hygiene:
    ok: bool
    scope: str | None                        # "show" | "track" | None
    check: str | None                        # Global Constraints check names
def judge(c: Cleaned, *, position: int, first: bool, stem: str, own_core: str,
          metadata_norms: set[str]) -> Hygiene
```

`judge` order: per-track first (`filler entry`; `?`-only, `is_placeholder`, `unknown`/`unk`/`(unknown)` and a bare number that is zero-led or equals `position` → `slot placeholder`, except a bare number equal to `own_core` passes; a `metadata_norms` hit when not `first` → `metadata`), then show-level (`metadata_norms` hit when `first` → `banner`; header shape → `header`; annotation; `is_timestamp`, or the leading `m:ss`/`h:mm:ss` + `)`/`]`/` - ` shape with no letter after it → `timestamp`; `looks_like_filename`, equal to `stem`, or `is_residue` gated as `is_placeholder_text` gates it → `filename residue`; `len > MAX_TITLE_LEN`; `is_junk_title`; trailing `:`; no letter or digit → `no alnum`). `is_junk_tag` is never used.

- [ ] **Step 1: Write the failing tests:**
  - `test_spec_pass_fixtures`: each of `2:45 AM`, `09-15-00`, `12.28.99`, `42`, `405`, `118`, `420`, `J`, `1 in 7` at position 5, not first, empty norms → `ok`.
  - `test_spec_decline_fixtures`: `?` and `??,  [4:47]` (via `clean_one`), `01.`, `01-` → `scope="track"`; `"Set" 1:`, `Disc 1, Track 10`, `s1t07:`, `w/ Eric Johnson`, `Fruit Bats opened`, `soulive2012-02-24-d1t01` → `scope="show"`; `Unknown` → `scope="track"`.
  - `test_bare_number_rules`: `5` at position 5 → track; `05` at position 9 → track; `42` at position 7 → ok; `07` at position 7 with `own_core="07"` → ok.
  - `test_metadata_hit_scope`: an entry in `metadata_norms` with `first=True` → show `banner`; `first=False` → track `metadata`.
  - `test_equal_to_own_stem_declines_show`.
  - `test_short_core_compares_by_equality_only`: `agrees("J", "Jack Straw") is False`; `agrees("J", "J") is True`; `agrees("Sailin On", "Sailing On") is True`.
  - `test_duplicate_comparator`: `duplicate("Dark Star", "Dark Star Jam") is True`; `duplicate("Truckin'", "Truckin' Jam") is False`; `duplicate("Sailing On", "Sailin On") is False`; `duplicate("Tuning", "Tuning") is False`.
  - `test_independent_sources_is_not_the_siblings_set` **(pin)**: `INDEPENDENT_SOURCES - siblings.INDEPENDENT_TITLE_SOURCES == {"sibling-align"}` and the siblings set is unchanged.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the file and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(title_hygiene): definitions, comparators, check 1`.

---

### Task 5: Checks 2 and 3, written durations, the agreement check, wholly untagged

**Spec:** slice 1 checks 2 and 3, "Written durations"; slice 2 "Agreement check"; Definitions "Wholly untagged". **Implementer: Sonnet.**

**Files:** Modify `title_hygiene.py`; Test `test_title_hygiene.py`.

**Interfaces:**
- Consumes: Task 4; `DescList`, `written_seconds` (Tasks 1-2); `Track`.
- Produces:

```python
def adjacent_duplicate(cands: dict[int, str], tracks: list[Track]) -> tuple[int, str, str] | None
    # cands: 0-based position -> candidate; a neighbour is its own candidate if it has one,
    # else its current title when not unresolved; first hit (pos, cand, neighbour)
def position_agreement(track: Track, c: Cleaned, aliases: dict[str, str]) -> str
    # "agree" | "neutral" | "disagree" | "skip" (source not in INDEPENDENT_SOURCES): check 3's
    # per-position judgement, shared with slice 4's neighbour test
def tape_disagreement(tracks: list[Track], dl: DescList,
                      aliases: dict[str, str]) -> tuple[int, str, str] | None
def written_duration_mismatch(tracks: list[Track], dl: DescList) -> tuple[int, float, float] | None
def agreement_share(dl: DescList, canonical: ParsedSetlist, aliases: dict[str, str]) -> float | None
def wholly_untagged(tag_titles: list[str], demoted: frozenset[int]) -> bool
```

Check 3 per position whose track source is in `INDEPENDENT_SOURCES`: filler title vs filler entry (`is_filler(text)` or `filler_marked`) is neutral; filler title vs song entry disagrees; song title vs filler entry disagrees; otherwise `agrees`. `agreement_share` is None when there are no canonical items or no song-like entries.

- [ ] **Step 1: Write the failing tests:**
  - `test_check2_finds_shift_signature`: candidates `{1: "Bertha"}` with track 0 tagged `Bertha` → hit; filler both sides → none.
  - `test_check2_neighbour_is_a_candidate_too`: `{0: "Jam", 1: "Jam"}` → hit (darkstarorchestra-2004-08-31 shape).
  - `test_check3_disagreement_declines`: gracepotter-2009-07-26 excerpt and tags → a hit naming the track.
  - `test_filler_tag_against_song_entry_disagrees`; `test_filler_against_filler_is_neutral`; `test_setlist_gap_title_is_neutral`.
  - `test_check3_runs_on_cleaned_copies`: tag `Joel Piano Solo (02:05)` vs entry `piano solo^` → no hit (umphreysmcgee-2004-03-17).
  - `test_check3_agrees_across_ampersand_and_curly_apostrophe`: tags `Me & My Uncle`, `Truckin'` vs entries `Me &amp; My Uncle`, `Truckin’` → no hit.
  - `test_written_durations_need_half_the_list`: 2 of 5 entries with durations → never fires; 3 of 5 → compares.
  - `test_written_tolerance_scales_with_length`: written 600 s, file 655 s → ok (55 ≤ 60); file 661 s → mismatch; written 120 s, file 136 s → mismatch (16 > 15).
  - `test_written_duration_check_skips_missing_file_lengths`: a `duration_sec=None` track at a position with a written time → skipped, no exception.
  - `test_agreement_share`: 4 of 5 song-like entries matched → 0.8; GD_SHORTHAND applies only when `aliases` is given (`Scarlet` vs `Scarlet Begonias`); `J` vs `Jack Straw` does not match; no canonical → None.
  - `test_agreement_exactly_at_floor_passes`: share exactly 0.5 is not below `AGREEMENT_FLOOR`.
  - `test_wholly_untagged_predicate`: one real tag → True; two real song-like tags → False; two real tags of which one is 2b-demoted → True; two filler tags → True.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the file and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(title_hygiene): checks 2 and 3, written durations, agreement, wholly untagged`.

---

### Task 6: The untagged checks and the D decision (slice 2)

**Spec:** slice 2 "When it fires", "What it ships", "Wholly untagged tapes" (a) and (b), "Self-filled tapes"; slice 1 "A track that fails the gate stays unresolved". **Implementer: Opus** (composes every check into the one decision the gate, S and Q2 all read).

**Files:** Modify `title_hygiene.py`; Test `test_title_hygiene.py`.

**Interfaces:**
- Consumes: Tasks 4-5; `siblings.DonorTape`, `siblings.SiblingRow`, `siblings.MIN_ANCHORS`.
- Produces:

```python
def block_size_mismatch(filenames: list[str], dl: DescList) -> str | None   # inert -> None
def sibling_disagreement(cands: dict[int, str], donor: tuple[DonorTape, list[SiblingRow]] | None
                         ) -> tuple[int, str, str] | None
SHIFT_CHECKS: frozenset[str]
@dataclass(frozen=True)
class DDecision:
    fills: dict[int, str]                    # 0-based -> shipped text; empty on a show decline
    failed: tuple[tuple[str, str], ...]      # every show-level failure (check, detail), in check order
    track_declines: dict[int, str]           # 0-based -> per-track check
    @property
    def shift(self) -> bool: ...             # any failed check in SHIFT_CHECKS
def decide_d(tracks: list[Track], dl: DescList, *, tag_titles: list[str], canonical: ParsedSetlist,
             metadata_norms: set[str], aliases: dict[str, str], wholly_untagged: bool,
             donor: Callable[[], tuple[DonorTape, list[SiblingRow]] | None]) -> DDecision | None
def apply_d(tracks: list[Track], d: DDecision) -> list[Track]               # source DESC_POSITION
def d_notes(d: DDecision, dl: DescList) -> list[str]
def is_self_filled(tracks: list[Track], d: DDecision | None) -> bool
```

`decide_d` returns None when `len(dl.raws) != len(tracks)` or no track is `unresolved`. Candidates are the cleaned entries at `unresolved` positions; every show-level check runs and is recorded in `failed` in this order: check 1 show-level (over candidates), check 2, check 3, written durations, then, only when `wholly_untagged`, block size and sibling durations (`donor` called only then, and only when there are candidates), then the agreement check when `agreement_share` is not None and below `AGREEMENT_FLOOR`. `block_size_mismatch` is inert unless the list has 2+ blocks, every filename yields the index, the index takes exactly as many values as there are blocks, and files are grouped by index in play order; the set index replaces the disc index when every boundary is `set` and every filename yields one. `sibling_disagreement` counts a pair only for a row whose `donor_span` has length 1 and is shared by no other row, whose donor title passes `is_real_title`, with filler on either side neutral; fewer than `MIN_ANCHORS` pairs is inert. `is_self_filled`: `d` passed (`not d.failed`) and every song-like track is `desc-position`.

- [ ] **Step 1: Write the failing tests:**
  - `test_d_fills_unresolved_and_never_touches_resolved`: a 4-track tape, tracks 1 and 3 tagged and agreeing → fills `{1: …, 3: …}` only.
  - `test_d_does_not_fire_without_count_match_or_unresolved`: 5 entries vs 4 tracks → None; no unresolved → None.
  - `test_d_may_fill_a_2b_demoted_position`: an `unresolved` track whose tag is `Track 03` gets its entry (the operator-confirmed amendment).
  - `test_check2_one_duplicate_declines_every_fill`: one adjacent duplicate → `fills == {}`, `failed[0][0] == "adjacent duplicate"`, `shift`.
  - `test_slot_placeholders_decline_per_track`: rosehilldrive-2008-12-31 excerpt (`?` entries) → the `?` positions in `track_declines` as `slot placeholder`, the rest filled.
  - `test_filler_marked_entry_is_never_filled`: a `Filler: Dark Star` entry → that position `filler entry`, others filled.
  - `test_show_level_hygiene_is_not_a_shift`: belafleckandtheflecktones-2003-06-08 excerpt (`"Set" 1:` lines) → `failed[0][0] == "hygiene:trailing colon"`, `not shift`.
  - `test_block_size_catches_the_two_shifted_untagged_shows`: billystrings-2023-06-10 (Set 1: 13 entries vs 12 `d1` files) and derektrucksband-2003-11-26 (9 + 5 entries vs 10 + 4 files), excerpts and filenames as literals → `"block size"` in `failed`.
  - `test_block_size_inert_without_index_or_matching_count`: filenames with no disc token, and 3 discs vs 2 blocks → None.
  - `test_set_headers_use_set_index`: set-header blocks with `s1t..`/`s2t..` filenames that also carry `d1` on every file → compared by set index.
  - `test_sibling_check_catches_a_shift`: a synthetic donor whose one-to-one paired titles disagree with two candidates → `"sibling durations"`.
  - `test_sibling_check_inert_without_durations`: `donor` returns None, and a donor pairing only one track → no sibling failure.
  - `test_untagged_checks_only_on_wholly_untagged`: the same mismatched blocks with `wholly_untagged=False` → no `block size`.
  - `test_agreement_check_declines_below_floor`: a list naming nothing in a setlist.fm canonical → `"agreement"` in `failed`, `shift`.
  - `test_ships_cleaned_text`: entry `Pyramid County (1) > Little Maggie` fills as `Pyramid County > Little Maggie`; `E: Ripple` as `Ripple`.
  - `test_self_filled_requires_d_to_pass_every_check`: all song-like `desc-position` and passed → True; same with an `agreement` failure → False; one independent song-like title → False; filler `tags` tracks do not stop it.
  - `test_notes_one_per_show_decline_and_per_track`: strings exactly per Global Constraints.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the file and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(title_hygiene): D decision with the untagged checks`.

---

### Task 7: The S plan and the deferred S fill (slice 1 placement)

**Spec:** slice 1 "The S rung splits by canonical source", "Declines bind setlist-gap"; operator rulings Q1 and the standing principle. **Implementer: Opus** (the branch structure decides which rung may title a track at all).

**Files:** Modify `title_hygiene.py`; Test `test_title_hygiene.py`.

**Interfaces:**
- Consumes: Tasks 4-6.
- Produces:

```python
@dataclass(frozen=True)
class SetlistPlan:
    mode: str                     # "none" | "today" | "untagged" | "chosen" | "deferred" | "gated"
    fills: dict[int, str]         # made inside resolve_titles (today's item text)
    deferred: dict[int, str]      # held for after D ("deferred" mode)
    declined: frozenset[int]      # passed to adopt_gap_titles
    notes: tuple[str, ...]
def plan_setlist_rung(*, canonical: ParsedSetlist, canonical_source: str | None,
                      s_positions: list[int], tag_titles: list[str], tag_real: list[bool],
                      filenames: list[str], metadata_norms: set[str], desc_used: bool,
                      wholly_untagged: bool, slice1: bool, slice2: bool) -> SetlistPlan
def apply_deferred_setlist(tracks: list[Track], plan: SetlistPlan, d: DDecision | None, *,
                           tag_titles: list[str], metadata_norms: set[str]
                           ) -> tuple[list[Track], list[str]]
```

`s_positions` are the 0-based positions that reach today's S branch (not demoted, tag fails `is_real_title`); `tag_real[i]` is True when position i resolves from its tag. Mode order: no count-matched canonical with confidence not `low` → `none`; `slice1` off → `today` (fills exactly today's: every `s_position` whose item is not `is_placeholder_text`); `wholly_untagged` → `untagged` (no fills, `declined` = all `s_positions`, one Q1 note); `canonical_source == "chosen"` and `slice2` → `chosen` (nothing, nothing declined); `desc_used` and `slice2` → `deferred` (`deferred` = every `s_position`'s item, `declined` = those positions); else `gated` (check 1 over the cleaned candidates at `s_positions`, check 2 against the tag-layer titles of `tag_real` positions and the other candidates; a show-level failure fills nothing and declines all; a per-track failure declines that one). `apply_deferred_setlist` fills only `unresolved` positions, only when `d` has no `shift` failure, never a `filler entry` position, re-running checks 1 and 2 against the current tracks; source `setlist`.

- [ ] **Step 1: Write the failing tests:**
  - `test_today_mode_is_todays_rung` **(pin)**: `slice1=False` → `fills` equal to what today's `resolve_titles` adopts on the same items (one placeholder item refused).
  - `test_s_never_fills_a_wholly_untagged_tape`: setlist.fm canonical, `wholly_untagged=True` → `mode == "untagged"`, no fills, all declined, the Q1 note.
  - `test_chosen_canonical_moves_to_d`: `canonical_source="chosen"` → `mode == "chosen"`, `declined` empty; with `slice2=False` → `gated`.
  - `test_count_matched_list_defers_s`: setlist.fm canonical and `desc_used=True` → `deferred`, positions declined for setlist-gap.
  - `test_copied_sibling_description_canonical_defers_to_d`: `canonical_source="lma:x"`, `desc_used=True` → `deferred`.
  - `test_gated_mode_runs_checks_1_and_2`: a header item → nothing filled, note `positional fill declined: setlist hygiene:header …`; an adjacent duplicate against a tag → nothing filled; one `?` item → only that position declined.
  - `test_deferred_s_fills_after_a_hygiene_decline`: D failed only `hygiene:annotation` → deferred items fill the still-unresolved positions.
  - `test_deferred_s_declines_with_d_on_a_shift`: D failed `tape agreement` → nothing filled.
  - `test_deferred_s_skips_filler_entry_positions`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the file and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(title_hygiene): S plan split by canonical source, deferred S`.

---

### Task 8: Per-track lossless titles (slice 3, C)

**Spec:** slice 3 in full; Definitions "Agree", "2a shape", "Real tag". **Implementer: Opus** (strict surface (b): the one rung that replaces a tag, with interlocking scope, reference and veto rules).

**Files:** Create `packages/llama/src/llama/lossless_titles.py`; Test `packages/llama/tests/test_lossless_titles.py`.

**Interfaces:**
- Consumes: `titles.sibling_format_titles`, `clean_tag_titles`, `title_fraction`, `tag_core`, `is_placeholder_text`, `is_real_title`; `junk.filter_files`, `LOSSLESS_TITLE_FORMATS`; `structure.hygienic_title`; `placeholders.is_junk_tag`; `title_hygiene.agrees`; `desc_list.clean_one`, `DescList`.
- Produces:

```python
@dataclass(frozen=True)
class LosslessResult:
    titles: list[str]               # tag layer after C, parallel to kept
    sources: list[str]              # per track: the incoming source, or "sibling-format" where C acted
    changed: dict[int, str]         # 0-based -> "C1" | "C2"
    declined: str | None            # show-level reason, or None
    notes: tuple[str, ...]
def apply_lossless(kept: list[dict], tag_titles: list[str], tag_source: str, *, in_scope: bool,
                   files: list[dict], ordering: dict, recovery_basis: list[dict],
                   desc: DescList | None, canonical: ParsedSetlist,
                   metadata_norms: set[str]) -> LosslessResult
```

`in_scope` is computed by the caller: `format_titles is None` and `title_fraction(clean_tag_titles(recovery_basis)) >= gather._RECOVER_BELOW`. References: (a) the count-matched list's cleaned entry at the same position; (b) the canonical item at the same position when `len(canonical.items) == len(kept)`. C1 accepts either; C2 and the show-level skip use one reference, (a) when there is a list, else (b). Lossless vetoes: wholly `[...]`; ending `:`; equal to the delivered title plus only trailing `@ ^ * #`. C1 target: delivered blank, `is_placeholder_text`, or failing `is_real_title`, and not the 2a shape; lossless real (`is_real_title`, not `is_placeholder_text`) and `hygienic_title`. C1 adoption (Global Constraints' reading): a target is adopted when its lossless title `agrees` with (a) or (b), or, failing both, when (c) holds (at least `MIN_ANCHORS` comparison stems agree and none disagrees); if any target is not adopted, no C1 fill on the show. C2: both real (or the delivered tag in 2a shape), `fuzzy_norm_title` differs, lossless `agrees` with the reference and delivered does not; no reference → no C2. Show-level skip: 2+ lossless tags each `loosely_same_title` the reference at ±1 but not at their own position.

- [ ] **Step 1: Write the failing tests:**
  - `test_c_does_not_run_below_recover_below`: `in_scope=False` → nothing changed, `declined == "out of scope"`.
  - `test_c1_fills_tmp_from_lossless_with_list_agreement`: a furthur/DSO `tmp` × 6 tape, lossless real, count-matched list agreeing → 6 `C1` changes, source `sibling-format`, one note per track.
  - `test_c1_needs_a_reference_or_consistent_tags`: no list, no count-matched canonical, two comparison stems agreeing → fills; one disagreeing comparison stem → nothing.
  - `test_c1_is_show_level`: one target disagreeing with its entry while (c) fails → no C1 fill on the show; the same with (c) holding → every target filled.
  - `test_2a_shape_delivered_tag_is_not_a_c1_target`: delivered `J`, lossless `Jack Straw`, list `J` → unchanged (C2: lossless does not agree with `J`).
  - `test_c2_replaces_a_stale_mp3_title`: radiators-1991-11-01 shape, delivered `No Skin Off My Back`, lossless `Mood To Move`, list entry `Mood To Move` → `C2`.
  - `test_c2_needs_a_reference`: no list and canonical count ≠ file count → unchanged.
  - `test_case_or_punctuation_difference_is_not_c2`.
  - `test_lossless_vetoes`: `[Banter]`, `Song (0:25):`, `Song @` beside delivered `Song` → never taken (builttospill-1997-10-13, mountaingoats-2017-06-02, greensky-2014-07-18 shapes).
  - `test_two_off_by_one_lossless_tags_skip_c`: two lossless tags equal to the entry at ±1 and not their own → `declined`, nothing changed.
  - `test_readmitted_file_is_untouched_and_keeps_no_vote`: a kept file absent from `recovery_basis` keeps its delivered title.
  - `test_derektrucksband_2007_05_27_track1`: blank MP3 track 1, lossless `Announcements/crowd`, a count-matched canonical whose item 1 is `Sailing On`, and the other stems tagged identically in both formats → track 1 becomes `Announcements/crowd` (`C1` via (c)); with one comparison stem disagreeing → unchanged.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the file and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(lossless_titles): per-track lossless titles (slice 3)`.

---

### Task 9: Short tags confirmed by the taper's list (slice 4)

**Spec:** slice 4 in full; Definitions "Entry", "Real-tagged neighbour". **Implementer: Sonnet.**

**Files:** Modify `title_hygiene.py`; Test `test_title_hygiene.py`.

**Interfaces:**
- Consumes: Tasks 1, 4, 5 (`position_agreement`); `titles.tag_core`, `shipped_short_tag`, `is_real_title`; `placeholders.is_junk_tag`.
- Produces:

```python
def confirm_short_tags(tracks: list[Track], tag_titles: list[str], tag_sources: list[str], *,
                       desc: DescList | None, demoted: frozenset[int], metadata_norms: set[str],
                       aliases: dict[str, str]) -> tuple[list[Track], list[str], list[int]]
    # (tracks, notes, accepted 0-based positions)
```

- [ ] **Step 1: Write the failing tests:**
  - `test_short_tag_confirmed_by_whole_entry_and_neighbour`: thenewdeal-2004-12-31 shape (`J` tag, entry `J`, neighbour tagged and agreeing) → title `J`, source `tags`, note.
  - `test_short_tag_needs_an_agreeing_neighbour`: no independent neighbour within ±2 → unchanged; a disagreeing neighbour → unchanged (robertwalters `VA`, zwan scramble shapes).
  - `test_whole_entry_only`: tag `VA`, entry `Quantico, VA` → unchanged.
  - `test_core_inside_the_stem_is_refused`: tag `d206` on stem `jg2011-12-31d206` → unchanged.
  - `test_junk_and_metadata_vetoes_still_apply`: `12-28-99`, `2:22` and a metadata-norms core → unchanged.
  - `test_ships_shipped_short_tag`: `415 ->` → `415`; `7-11 (3)>` → `7-11`.
  - `test_fills_only_unresolved_and_never_demoted`: a resolved track and a 2b-demoted one are untouched (moe-2008-01-26 shape).
  - `test_sibling_format_source_kept`: a `sibling-format` per-track source is stamped as such.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the file and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(title_hygiene): short tags confirmed by the taper's list (slice 4)`.

---

### Task 10: Cosmetic junk stripping (slice 5)

**Spec:** slice 5 in full. **Implementer: Sonnet.**

**Files:** Create `packages/llama/src/llama/title_cosmetics.py`; Test `packages/llama/tests/test_title_cosmetics.py`.

**Interfaces:**
- Produces:

```python
STRIP_SOURCES = frozenset({"tags", "sibling-format", "setlist", "setlist-gap", "desc-position", "sibling-align"})
def cosmetic_strip(tracks: list[Track]) -> tuple[list[Track], list[str], list[int]]
    # (tracks, notes, changed 0-based positions)
```

Shapes only: leading `^[(\[]?\d{1,2}:\d{2}(?::\d{2})?(?:[)\]]\s*|\s+-\s+)`; an embedded stem `(?<![a-z0-9])(?:[a-z&]{2,10}\d{2,4}[.\-]\d{2}[.\-]\d{2,4}(?:\.[a-z0-9]+)*?\.?)?(?:d|cd|s|set)\d{1,2}t\d{1,3}[\s\-_.:]*` (case-insensitive); a trailing `\.(?:wav|flac)\s*$` or `\.flac:[0-9a-f]{32}\s*$`. A result is kept only if non-empty, not `is_placeholder_text`, and `is_real_title` or 2a-shaped (alphanumeric core, not `is_junk_tag`); otherwise the title is unchanged.

- [ ] **Step 1: Write the failing tests:**
  - `test_strips_leading_timestamp_shapes`: `06:58 - Who Took the Happiness Out?` → `Who Took the Happiness Out?`; `16:34) Waiting For the Punchline` → `Waiting For the Punchline`; `[05:12] Song` → `Song`.
  - `test_strips_embedded_stems_and_tails`: `Greensky Bluegrass - d2t07-In Control` → `Greensky Bluegrass - In Control`; `Song.wav` → `Song`; `Song.flac:<32 hex>` → `Song`.
  - `test_bare_time_word_titles_are_never_stripped`: `4:20 Polka`, `8 Cylinders`, `16 Military Wives`, `20 Eyes`, `3 AM`, `1 Samuel 15:23`, `2:45 AM` unchanged.
  - `test_encore_and_set_markers_kept`: `E: Ripple`, `S2: Song`, `set1: Song` unchanged.
  - `test_never_override_or_unresolved`: an `override` `06:58 - X` and an unresolved `phish1995-12-31d2t05.flac` unchanged.
  - `test_residue_only_title_left_alone`: `d&co2017.06.17.mg21.set01t01` (strips to nothing) unchanged.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the file and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(title_cosmetics): cosmetic junk stripping (slice 5)`.

---

### Task 11: Additive seams and the unwired `title_cascade`

**Spec:** slice 1 placement, slice 2 "When it fires", slice 3 "Placement" and "Per-track source" (every listed consumer), slice 4 placement, Constraints "Ordering". **Implementer: Opus** (must reproduce gather lines 1176-1328 exactly with every slice off, then place each slice). Touches `titles.py`, `structure.py`, `gather.py`: protected names untouched; `compute_gather` NOT edited.

**Files:**
- Modify: `packages/llama/src/llama/titles.py` (`TagLayer`; `resolve_titles` kw-only `layer`, `setlist_fills`), `packages/llama/src/llama/structure.py` (`adopt_gap_titles` kw-only `declined`), `packages/llama/src/llama/stages/gather.py` (`accept_short_tags` kw-only `tag_sources`; new `TitleInputs`, `CascadeRecord`, `TitleCascade`, `title_cascade`, `gather_cleaner`)
- Test: `packages/llama/tests/test_title_cascade.py`; additions to `test_titles.py`, `test_structure.py`

**Interfaces:**
- Consumes: Tasks 1-9.
- Produces:

```python
# titles.py
@dataclass(frozen=True)
class TagLayer:
    titles: list[str]; sources: list[str]; demoted: frozenset[int]
def resolve_titles(..., *, corroboration=..., item_title=None,
                   layer: TagLayer | None = None,
                   setlist_fills: Mapping[int, str] | None = None) -> list[Track]
# structure.py
def adopt_gap_titles(tracks, canonical, *, metadata_norms, aliases=None,
                     declined: frozenset[int] = frozenset()) -> list[Track]
# gather.py
def accept_short_tags(tracks, tag_titles, tag_source, *, corroboration, metadata_norms, demoted,
                      tag_sources: Sequence[str] | None = None) -> tuple[list[Track], list[str]]
def gather_cleaner(metadata_norms: set[str], artist: str) -> Callable[[ParsedSetlist], ParsedSetlist]
@dataclass(frozen=True)
class TitleInputs:
    kept: list[dict]; files: list[dict]; ordering: dict
    recovery_basis: list[dict]; tag_gate_basis: list[dict]
    format_titles: dict[str, str] | None
    cb: CanonicalBuild; item_title: str | None; metadata_norms: set[str]
    overrides_titles: dict[int, str]; family_aliases: dict[str, str]
    desc: DescRead
    sibling_step: Callable[[list[Track]], tuple[list[Track], list[str]]]
    donor_check: Callable[[list[Track]], tuple[DonorTape, list[SiblingRow]] | None]
@dataclass(frozen=True)
class CascadeRecord:
    wholly_untagged: bool; fetch_siblings: bool
    lossless: LosslessResult | None; s_plan: SetlistPlan; d: DDecision | None
    short4: tuple[int, ...]; gap_filled: tuple[int, ...]; deferred_applied: tuple[int, ...]
@dataclass(frozen=True)
class TitleCascade:
    tracks: list[Track]; op_notes: list[str]; struct_notes: list[str]
    self_filled: bool; paths: tuple[str, ...]; record: CascadeRecord
def title_cascade(inp: TitleInputs, *, enabled: frozenset[str] = ENABLED_SLICES) -> TitleCascade
```

`_inputs_like_gather` (test helper) computes each field with the same expressions `compute_gather` uses (its lines 1080-1205: `filter_files`, `recovery_basis`, `_recover_format_titles`, exclusion, `build_canonical`, `show_metadata_norms`, `tag_gate_basis`). Order inside `title_cascade`: `titles.tag_layer` → C (`slice3`, `in_scope` as Task 8) → 2b `placeholder_positions` on the delivered layer minus C-changed and override positions, with its notes → 2c/2d notes skipping C-changed → `fetch_siblings` (its `or demoted` arm over the C-filtered set) → the format-sibling note (not when C changed anything) → `wholly_untagged` → `plan_setlist_rung` → `resolve_titles(layer=…, setlist_fills=plan.fills)` → overrides loop (same `LlamaError`) → `sibling_step` when `fetch_siblings` (its notes into `struct_notes`) → `adopt_gap_titles(declined=plan.declined)` → `accept_short_tags(tag_sources=…, demoted=C-filtered)` → `confirm_short_tags` (`slice4`) → `decide_d`/`apply_d` (`slice2`) → `apply_deferred_setlist`. `paths` is computed from the record. Defaults of every new parameter reproduce today's behaviour.

- [ ] **Step 1: Write the failing tests:**
  - `test_resolve_titles_defaults_unchanged` **(pin)** and `test_resolve_titles_layer_and_fills`: a layer with per-track sources stamps them; `setlist_fills={2: "X"}` fills only position 2 and only where today's S branch is reached.
  - `test_declined_positions_bind_setlist_gap` (test_structure.py): a count-forced gap containing a declined position stays unresolved; without `declined` it fills **(pin for the default)**.
  - `test_accept_short_tags_per_track_sources`.
  - `test_cascade_with_no_slices_equals_todays_gather`: for the gd73, gd74 (siblings), ymsb, lossless-recovery (`_with_tagged_lossless`) and short-tag fixtures of `test_stage_gather.py`, build `TitleInputs` from the same values `compute_gather` computes (test helper `_inputs_like_gather`), then `title_cascade(enabled=frozenset())`'s tracks, op notes and struct notes equal `compute_gather`'s tracks (title, source) before alignment, its notes prefix and its sibling notes.
  - `test_each_slice_runs_at_its_place`: a synthetic tape where C, slice 4, D and deferred S each fill one position → `paths` `("C1", "4", "D", "S-deferred", …)`; setlist-gap does not fill an S-declined position.
  - `test_overrides_survive_every_new_rung_and_anchor_check_3`: an override at a D position and at a C position keeps its title and source `override`; an override disagreeing with its entry makes D fail `tape agreement`.
  - `test_c_changed_stems_leave_2b_and_fetch_and_notes`: a `tmp` tape C fills → no 2b demotion note on those stems, no format-sibling note, `fetch_siblings` False when nothing else is unresolved.
  - `test_wholly_untagged_evaluated_after_c`: an untagged MP3 that C fills from lossless is not wholly untagged.
  - `test_exclusion_changes_the_count_d_sees`: an excluded file makes the list count-matched and D fires.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. `gather_cleaner` composes `_strip_head_banner`, `drop_leading_artist_items`, `_strip_footnote_markers`.
- [ ] **Step 4:** Run the task's tests, `test_titles.py`, `test_structure.py`, `test_stage_gather.py`, then the full suite → PASS with no existing test edited; `git diff main -- packages/llama/src/llama/stages/gather.py` shows no change inside `compute_gather`.
- [ ] **Step 5:** Commit `feat(gather): unwired title_cascade and additive seams`.

---

### Task 12: Harness `--strip-title-overrides` (scripts only)

**Spec:** Acceptance preamble (the fresh-get view). **Implementer: Sonnet.** Touches only `scripts/`, so it can be cherry-picked onto the base tree.

**Files:** Modify `scripts/replay_holds.py`; Test `scripts/test_replay_holds.py`.

**Interfaces:**
- Produces: `replay_holds.py run --strip-title-overrides` (alone or with `--strip-structure-overrides`; strips `titles`); `_shadow(d, shadow_root, keys: tuple[str, ...])`; arm key `"title_overrides_stripped": bool`; `compare` refuses arms whose title-strip flags differ (exit 2) and writes no apply lists when either strip flag is set.

- [ ] **Step 1: Write the failing tests:** `test_strip_titles_removes_only_titles` (overrides with `exclude`, `titles`, `set_breaks` → only `titles` gone in the shadow, live file hash unchanged, arm stamped); `test_both_strip_flags_together`; `test_compare_refuses_mixed_title_strip_arms`; `test_no_apply_lists_for_title_stripped_arms`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `scripts/test_replay_holds.py` and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(harness): --strip-title-overrides`.
- [ ] **Step 6 (orchestrator):** Base tree: `git worktree add --detach .claude/worktrees/title-hygiene-base 11dbffb && cd .claude/worktrees/title-hygiene-base && git cherry-pick <Task 12 sha>`; its own `.venv` as in Task 0 Step 2; check `llama.__file__` resolves inside it and `git diff 11dbffb HEAD -- packages` is empty.

---

### Task 13: The gate probe, `dump` (read-only)

**Spec:** Acceptance 1 (the yield gate, "before wiring"). **Implementer: Opus** (in-process capture of gather's inputs and the gate-0 proof that the orchestrator is today's code).

**Files:** Create `scripts/title_hygiene_probe.py`; Test `scripts/test_title_hygiene_probe.py`.

**Interfaces:**
- Consumes: `title_cascade`, `TitleInputs`, `gather_cleaner` (Task 11); `read_desc_list`; `cosmetic_strip`; `replay.compute_legs`, `CacheOnlyIA`, `setlistfm_client`; `replay_holds._shadow` with keys `("titles", "set_breaks", "encore_after")`.
- Produces: `python scripts/title_hygiene_probe.py dump [--config P] [--slugs F] [--jobs N] --out DIR` → `DIR/dump.jsonl` (first line `{"_meta": {sha, config_fingerprint, setlistfm_configured, n}}`). Refuses an `--out` overlapping the library root and a `llama` imported from outside this tree (exit 2, as `replay_holds._check_identity`).

Per show, on the fresh-get shadow: wrap `gather.resolve_titles`, `build_canonical`, `_recover_format_titles`, `show_metadata_norms`, `accept_short_tags` and `_sibling_transfer` (as the census `dump.py` does) to capture today's pre-alignment tracks and every `TitleInputs` field, run `compute_legs`, then call `title_cascade` with closures over the cache-only client for arms `none` (`frozenset()`), `all` (`ALL_SLICES`) and `all-<slice>` for each slice, applying `cosmetic_strip` to every arm containing `slice5`. Each row: slug, state, voiced, identifier, artist, family, `today` tracks (title, source, duration, filename, raw tag), today's fresh-view flags/outcome/notes, whether the stored overrides held a structure override, `desc` (reader used, both reasons, entries), the canonical (items, source, confidence), and per arm: tracks (title, source, path), `self_filled`, the `CascadeRecord` as JSON, `align()` coverage of the arm's tracks against the canonical, and `gate0` (arm `none` equal to `today` in titles, sources, op notes and struct notes, with the first difference).

- [ ] **Step 1: Write the failing tests** against a tmp library (gd73 and gd74 fixtures as cache files, provenance and show dirs): `test_gate0_parity_on_fixtures` (every row `gate0 is True`); `test_strips_titles_and_structure_overrides_in_the_shadow` (live overrides hash unchanged); `test_arms_present_and_slice5_applied_last`; `test_refuses_out_inside_library`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the tests and the full suite → PASS.
- [ ] **Step 5:** Run `./.venv/bin/python scripts/title_hygiene_probe.py dump --jobs 6 --out ~/.llama-harness/piece3/gate`. Expected: every replayable row `gate0 true`. Any `false` is a Task 11 defect: fix it there (new commit, a test reproducing the row) and re-run before Task 14.
- [ ] **Step 6:** Commit `feat(scripts): title hygiene gate probe, dump`.

---

### Task 14: The gate table (CHECKPOINT A)

**Spec:** Acceptance 1 (every bullet); Acceptance 4 (the bar, previewed). **Implementer: Sonnet** (report code from fixed row definitions); Step 6 is the orchestrator's.

**Files:** Modify `scripts/title_hygiene_probe.py`; Test `scripts/test_title_hygiene_probe.py`.

**Interfaces:**
- Produces: `title_hygiene_probe.py gate --dump DIR/dump.jsonl [--handcheck DIR] [--census FILE] --out DIR` (defaults: the evidence dir's `handcheck/`, `~/.llama-harness/piece3/census/dump.jsonl`) → `gate_table.md`, `gate_rows.jsonl`, `untagged_unchecked.txt`, `samples/<row>.txt`.
- Scoring. A changed track is one whose `all`-arm title or source differs from `today`. Hand-check index: `(slug, n)` → rows from every `handcheck/*/rows.jsonl`. Judged when some row's `candidate` equals the new title by `fuzzy_norm_title` after `clean_one`: `right`/`right-partial` → right, `wrong` → wrong, `cant-tell`. Otherwise "inferred" from a non-null `correct_title` via `agrees` (reported separately, never pooled with judged), else unjudged. Show verdicts: good = `all-right`, `fix-helps`, `strip-fixes-it`; bad = `shifted`, `some-wrong-not-shift`, `fix-hurts`, `mixed`, `strip-would-damage`, `strip-not-enough`. Each slice is scored on its own classes (slice1: S; slice2: D, U; slice3: C; slice4: A_rev; slice5: A). Held (approximate, labelled so): today's fresh-view flags minus `unresolved track titles`, minus `low-confidence structure alignment` when the arm is self-filled or its coverage reaches the threshold, plus `unresolved track titles` when any track is unresolved.

Rows of `gate_table.md`:
- R0 gate 0 (rows equal / total) and the census cross-check (today vs census `tracks` on shows with no structure override).
- R1 per slice, from paths in `all` and from `all` vs `all-<slice>`: tracks filled or changed; judged right / wrong / cant-tell; inferred right / wrong; unjudged; good shows newly held; bad shows newly held; the ≤ 2% wrong preview per path and pooled.
- R2 S re-count by canonical source and plan mode; S's caught and uncaught bad shows after Q1 and the split.
- R3 shows where deferred S was withdrawn because D declined on a shift; setlist-gap fills on chosen-canonical tapes where D then declined.
- R4 the stricter non-chosen alternative (`gap_span`-bracketed runs only): added holds and bad shows it would stop. Reported, not adopted.
- R5 Q1's trade on the fresh-get view (shows, tracks, verdict split, held now) and per slice the changed shows unheld today ("ships silently").
- R6 `metadata` per-track declines (self-titled songs). R7 positions left unresolved by `Filler:`. R8 every `adjacent duplicate` decline with its pair (split songs).
- R9 `agreement` declines, and those on hand-checked-right shows as their own row. R10 `block size` declines on hand-checked-right shows and library-wide.
- R11 shows newly above the coverage threshold by independent-denominator size (1, 2, 3+); shows with a 4a suppression note today and a D fill now (upper bound on consequence (2)).
- R12 D's residual: wholly untagged D-filled shows with both untagged checks inert and no written durations.
- R13 the wholly untagged count-matched population under Definitions: total, in `U0`-`U3`, not checked (written to `untagged_unchecked.txt`).
- R14 the bare-number rule over all 128 S rows: declines by verdict.
- R15 extra show-level hygiene declines if every entry were judged (plan reading).
- R16 lists inadmissible only because a numbering restart follows an `Encore` header (plan reading).
- R17 C1 show-level declines, with how many of their targets would pass on their own (the per-stem alternative; plan reading).
- R18 the agreement check's and `WRITTEN_DURATION_TOL`'s firings on hand-checked-right shows.

- [ ] **Step 1: Write the failing tests** on a three-row fake dump and a fake hand-check dir: `test_judged_vs_inferred_vs_unjudged`; `test_show_verdict_mapping`; `test_newly_held_approximation`; `test_untagged_unchecked_list`; `test_every_row_heading_present` (R0-R18).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the tests and the full suite → PASS; then `… gate --dump ~/.llama-harness/piece3/gate/dump.jsonl --out ~/.llama-harness/piece3/gate`.
- [ ] **Step 5:** Commit `feat(scripts): title hygiene gate table`.
- [ ] **Step 6: CHECKPOINT A (orchestrator → operator, then stop).** Hand-check every show in `untagged_unchecked.txt`: packets as `untagged_packets.py` builds them (tagged siblings included) under `~/.llama-harness/piece3/gate/packets/U4/`, Sonnet checkers on the class U brief (run the `usage-pacing` fleet check before more than two concurrent), then an Opus pre-screen of their rows and of R8, R9, R10 and every judged-wrong track in R1. Fold the new rows into R1/R13 and re-run Step 4. Report to the operator: the table, the pre-screen verdicts, and these decisions: (1) keep or DROP each slice (operator, 2026-10-23: an LLM adjudicator at about 1-2% of LLM spend is the alternative to engineering a small-yield slice); (2) the plan readings behind R15, R16, R17; (3) any constant the table shows misfiring (a constant changes only by operator ruling, recorded, and the gate re-runs). Wait for the rulings. Rule defects found here go back to the owning task (new commit, its tests extended) and Steps 4-6 re-run.

---

### Task 15: Apply the Checkpoint A rulings (conditional)

**Spec:** the operator's Checkpoint A rulings. **Implementer: Sonnet.** Skip when every slice is kept and no reading changed.

**Files:** as the rulings require: `title_hygiene.py` (`ALL_SLICES`/`ENABLED_SLICES`), the dropped slice's module or functions and their tests.

- [ ] **Step 1:** For each dropped slice, delete its code, tests and switch name: slice 3 → `lossless_titles.py`, `test_lossless_titles.py`; slice 4 → `confirm_short_tags` and its tests; slice 5 → `title_cosmetics.py`, its tests, and Task 18 is skipped; slice 2 → `decide_d`, `apply_d`, `is_self_filled`, the untagged checks and D-only tests (the readers, check 1, the comparators and check 3's per-position judgement stay; `plan_setlist_rung` keeps its `slice2=False` branches), and Task 16's `desc-position` steps and Task 17's Q2 steps are skipped; slice 1 → `plan_setlist_rung` always takes `today` mode (its other modes and tests are deleted). The cascade's branch for the dropped slice goes with it.
- [ ] **Step 2:** Apply any ruled change of reading or constant, with a test for the new behaviour.
- [ ] **Step 3:** Re-run gate 0 on the fixtures (`scripts/test_title_hygiene_probe.py`) and the full suite → PASS.
- [ ] **Step 4:** Commit `refactor: apply Checkpoint A rulings (<summary>)`.

---

### Task 16: Wire the cascade into `compute_gather`

**Spec:** slice 2 "Tautology" and its consequences; Constraints "Persisted models stay permissive"; every placement rule. **Implementer: Opus** (replaces gather's live title block; strict surface (a)). Touches `gather.py`, `structure.py`, `models.py`.

**Files:**
- Modify: `stages/gather.py` (`compute_gather`'s block from `tag_layer` through `accept_short_tags` becomes one `title_cascade` call; `family_aliases` computed above it; `GatherResult.self_filled`, `title_paths`), `structure.py` (`TAUTOLOGICAL_TITLE_SOURCES` gains `"desc-position"`), `models.py` (the `Track.title_source` comment names `desc-position`)
- Test: `test_stage_gather.py`, `test_structure.py`, `test_show_cmd.py`

**Interfaces:**
- Consumes: `title_cascade` (Task 11).
- Produces: `GatherResult.self_filled: bool = False`, `GatherResult.title_paths: tuple[str, ...] = ()` (last fields, defaulted). `compute_gather` passes `enabled=title_hygiene.ENABLED_SLICES` read through the module at call time (so `--disable-slices` and tests can patch it), and builds `desc` with `read_desc_list(_description(meta), len(kept), artist=artist, clean=gather_cleaner(metadata_norms, artist))`.

- [ ] **Step 1: Write the failing tests:**
  - `test_desc_position_is_tautological`: `"desc-position" in TAUTOLOGICAL_TITLE_SOURCES`; a D-filled track gets `matched=None` and leaves `_songish_coverage`'s denominator.
  - `test_gather_fills_from_the_taper_list` (an untagged fixture tape plus a count-matched numbered description) → `desc-position` titles, no `unresolved track titles` flag.
  - `test_gather_s_withdrawn_when_list_count_matched` (setlist.fm canonical stubbed, count-matched list) → D's titles, not setlist.fm's.
  - `test_gather_q1_untagged_setlistfm_stays_unresolved`.
  - `test_gather_c1_fills_tmp_tape` (`_with_tagged_lossless` with `tmp` MP3 tags and a count-matched list).
  - `test_title_paths_reported`.
  - `test_show_tracks_prints_desc_position` (test_show_cmd.py; the 14-character column) **(pin)**.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Notes order is today's: cascade `op_notes` are the first entries of `op_notes`, cascade `struct_notes` follow `cb.notes` in `notes`.
- [ ] **Step 4:** Run the full suite. Every existing test whose expectation changes must change only because of a spec rule (the gd73 fixture's 6-for-6 chosen-canonical S fill moving to D is the expected one): list each in the commit message with the spec clause, update it, and leave a comment naming the clause. No other existing test changes. `grep -rn "title_source" packages/emcee packages/transmitter antenna/src` finds no reader switching on its values (record in the commit message).
- [ ] **Step 5:** Commit `feat(gather): wire title_cascade; desc-position is tautological`.

---

### Task 17: Q2 self-filled tapes and the replay relaxation

**Spec:** slice 2 "Self-filled tapes (Q2)", "Replay"; strict surface (e). **Implementer: Sonnet.** Touches `gather.py`, `replay.py`.

**Files:** Modify `stages/gather.py` (the not-owned `today_llm` branch), `replay.py` (`compute_legs`; `ShowReplay` fields, set in `replay_show`); Test `test_stage_gather.py`, `test_replay.py`, `test_reapply.py`, `test_taper.py`.

**Interfaces:**
- Consumes: `GatherResult.self_filled`, `title_paths` (Task 16).
- Produces: in the not-owned branch, `elif today_llm and not self_filled:` keeps today's LLM call and flag; a self-filled `today_llm` show records no `align_structure` call, no `needs_align`, no low-confidence flag; `today_reaches_llm` passed to `decide_taper` is unchanged. `compute_legs`: `… == "llm" and not gathered.taper_owned and not gathered.self_filled`. `ShowReplay` gains `self_filled: bool = False`, `desc_position: int = 0`, `titles: list[str]`, `title_sources: list[str]`, `title_paths: list[str]` (after the piece-2 fields).

- [ ] **Step 1: Write the failing tests:**
  - `test_self_filled_tape_skips_align_structure_and_the_flag`: a self-filled tape with a non-matching setlist.fm canonical and an `align_provider` that raises if called → no call, `"align_structure"` not in `needs_llm`, no `low-confidence structure alignment`; labels equal deterministic `align()`'s.
  - `test_one_independent_title_keeps_low_confidence` **(pin)**: the same tape with one tagged song-like track → today's LLM branch and flag.
  - `test_jerrybase_anchoring_still_labels_a_self_filled_family_tape`.
  - `test_taper_never_owns_a_self_filled_tape` (test_taper.py, the spec's defensive test): `decide_taper` on all-`desc-position` tracks with placeable markers → not owned.
  - `test_today_reaches_llm_unchanged_for_self_filled` (patch `decide_taper`, assert its argument).
  - `test_stored_llm_self_filled_is_replayable` and `test_stored_llm_not_self_filled_stays_needs_llm` (test_replay.py).
  - `test_record_carries_title_fields`; update `test_show_replay_to_dict_has_the_contract_keys_plus_date` to the new key list.
  - `test_reapply_processes_a_self_filled_stored_llm_show` (test_reapply.py, existing fixtures; refused without `--allow-structure-change` when structure changes).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the task's tests and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(gather,replay): self-filled tapes ship (Q2); replay relaxation`.

---

### Task 18: Wire slice 5 before `Show` is built (skip if slice 5 dropped)

**Spec:** slice 5 placement. **Implementer: Sonnet.** Touches `gather.py`.

**Files:** Modify `stages/gather.py` (immediately before `show = Show(...)`, after the include stamp); Test `test_stage_gather.py`.

- [ ] **Step 1: Write the failing tests:** `test_cosmetic_strip_runs_after_flags` (a `06:58 - Song` tag ships as `Song`; flags equal those of the same gather with `cosmetic_strip` patched to identity); `test_cosmetic_strip_keeps_included_stamp`; `title_paths` gains `+5`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement (only when `"slice5" in title_hygiene.ENABLED_SLICES`, read at call time; notes appended to `op_notes`; changed positions add `+5` to `title_paths`).
- [ ] **Step 4:** Run the full suite → PASS.
- [ ] **Step 5:** Commit `feat(gather): cosmetic title strip on final titles (slice 5)`.

---

### Task 19: Harness reports for acceptance

**Spec:** Acceptance 2 and 3. **Implementer: Sonnet.**

**Files:** Modify `scripts/replay_holds.py` (`run --disable-slices LIST`; `compare` reports, `OUTPUT_FILES`, `NOTE_GROUPS`), `scripts/title_hygiene_probe.py` (`packets`, `parity`); Test `scripts/test_replay_holds.py`, `scripts/test_title_hygiene_probe.py`.

**Interfaces:**
- Consumes: Task 17's record fields; base rows lack them and read as absent (titles reconstructed from the stored `show.json` plus `title_changes`).
- Produces: `run --disable-slices slice5,…` (removes them from `title_hygiene.ENABLED_SLICES` for the run; arm key `"disabled_slices"`); `compare` writes `holds_delta.txt` (holds cleared, split held now / would-hold on a fresh get / currently packaged; holds added with their flags, by state; each show attributed to the slices its `title_paths` name, a show with several listed under each), `title_changes.txt` (titles changed on shows that stay unheld, by state packaged / delivered / voiced and by path, title-text changes separate from source-only changes), and extends `needs_llm.txt` with the D shows reaching an `agreement` decline or the LLM branch; `NOTE_GROUPS` gains `positional`, `lossless`, `short4`, `cosmetic`; `title_hygiene_probe.py parity --arm CAND --dump DIR/dump.jsonl --out DIR` (wired fresh-get titles vs the gate's `all` arm, per show); `title_hygiene_probe.py packets --cmp DIR --dump … --out DIR` (Acceptance 3 strata: every newly cleared wholly untagged show with 3+ D fills, all self-filled included; a stratified 60 of the other newly cleared, seed `20261023`; every changed title on a delivered show).

- [ ] **Step 1: Write the failing tests:** one per report on fake arms (`test_holds_delta_three_way_split`, `test_holds_added_by_flag_and_state`, `test_title_changes_text_vs_source_only`, `test_voiced_marked_from_station_manifest`, `test_needs_llm_counts_d_agreement_and_llm_branch`, `test_note_groups_for_piece3`, `test_disable_slices_stamped_and_applied`, `test_parity_lists_mismatches`, `test_packets_strata`).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the tests and the full suite → PASS.
- [ ] **Step 5:** Commit `feat(harness): title hygiene acceptance reports`.

---

### Task 20: Mutation run (scratch copy only)

**Implementer: Sonnet.** **Files:** commit only `docs/superpowers/2026-10-2x-title-hygiene-sdd/mutation.md` (the SDD dir, dated by the run).

- [ ] **Step 1:** Scratch copy via `git archive HEAD | tar -x -C <scratch>`; run `<worktree>/.venv/bin/python -m pytest` with `PYTHONPATH=<scratch>/packages/llama/src:<scratch>/packages/herder/src`, after a planted sentinel proves shadowing; `PYTHONPYCACHEPREFIX` per mutant.
- [ ] **Step 2:** For each mutant (dropped slices skipped), name the predicted red test before flipping:
  (a) check 2 declines only the duplicate → `test_check2_one_duplicate_declines_every_fill`; (b) filler-tag-vs-song-entry neutral → `test_filler_tag_against_song_entry_disagrees`; (c) short cores via `loosely_same_title` → `test_short_core_compares_by_equality_only`; (d) own-tag-core exemption removed → `test_bare_number_rules`; (e) leader strip without the vote → `test_leader_stripped_only_under_the_vote`; (f) leader lookahead removed → `test_date_shaped_entries_keep_their_numbers`; (g) Q1 removed → `test_s_never_fills_a_wholly_untagged_tape`; (h) deferred S after a shift → `test_deferred_s_declines_with_d_on_a_shift`; (i) `declined` ignored → `test_declined_positions_bind_setlist_gap`; (j) 2a-shape as C1 target → `test_2a_shape_delivered_tag_is_not_a_c1_target`; (k) C scope gate removed → `test_c_does_not_run_below_recover_below`; (l) C ±1 skip removed → `test_two_off_by_one_lossless_tags_skip_c`; (m) slice 4 neighbour rule removed → `test_short_tag_needs_an_agreeing_neighbour`; (n) stem veto removed → `test_core_inside_the_stem_is_refused`; (o) bare `m:ss Word` stripped → `test_bare_time_word_titles_are_never_stripped`; (p) self-filled ignores `failed` → `test_self_filled_requires_d_to_pass_every_check`; (q) Q2 on a tape with one independent title → `test_one_independent_title_keeps_low_confidence`; (r) relaxation unconditional → `test_stored_llm_not_self_filled_stays_needs_llm`; (s) `desc-position` not tautological → `test_desc_position_is_tautological`; (t) disc index where the set index applies → `test_set_headers_use_set_index`; (u) agreement floor `<=` → `test_agreement_exactly_at_floor_passes`; (v) `Filler:` entry shipped → `test_filler_marked_entry_is_never_filled`; (w) tolerance without the 10% → `test_written_tolerance_scales_with_length`; (x) contiguity check removed → `test_gaps_are_inadmissible`; (y) reader (ii) accepts a 2-item line → `test_a_line_split_into_two_items_is_inadmissible`.
- [ ] **Step 3:** Record mutant, predicted test, observed result. Every mutant is caught by its predicted test; a survivor or a surprise catch goes back to the owning task.
- [ ] **Step 4:** Commit `docs: title hygiene mutation record`.

---

### Task 21: Acceptance measurement (CHECKPOINT B)

**Spec:** Acceptance 2-5. **Orchestrator**, with Sonnet hand-checkers and Opus pre-screens. Writes only under `~/.llama-harness/piece3/accept/` and `docs/superpowers/2026-10-22-title-hygiene-evidence/acceptance.md`.

- [ ] **Step 1:** Four arms, `--all`: base (the Task 12 base tree) and candidate (this branch), each as-is and fresh-get (`--strip-title-overrides --strip-structure-overrides`); plus a candidate fresh-get arm with `--disable-slices slice5` (if slice 5 kept).
- [ ] **Step 2:** `compare` base vs candidate per view (`--no-repro-gate`, as piece 1); compare the candidate fresh-get arm with its `slice5`-disabled twin; `title_hygiene_probe.py parity` against the Task 13 dump.
- [ ] **Step 3:** Verify: parity has no mismatch (else a wiring defect); slice 5 changes no gather flag and no set label, and every vet or brief flag change it causes is listed for the hand check; every newly held show is explained by its flag.
- [ ] **Step 4:** `packets`, then Sonnet hand-checkers over the three strata (the `usage-pacing` fleet check first), then an Opus pre-screen of their rows. The operator sees the results.
- [ ] **Step 5:** Compute the bar: wrong ≤ 2% of tracks filled or replaced, per path (C1, C2, D, slice 4, S, slice 5) and pooled; zero shifted shows in the hand check and in the gate's untagged hand check; slice 1 holds at most 2 hand-checked-good S shows, Q1 declines reported apart. A miss or a rule defect goes back to the owning task, and Steps 1-5 re-run.
- [ ] **Step 6:** Write `acceptance.md`: arm shas (and that the base tree's packages equal 11dbffb), the gate table's final numbers, holds cleared/added by state, title changes by state and path, needs-LLM counts, the hand-check and pre-screen verdicts with sha256 pins of their row files, the bar per path. Suite green from the worktree venv (Acceptance 5).
- [ ] **Step 7: CHECKPOINT B (orchestrator → operator, then stop).** Report the acceptance numbers and findings. The final branch review is the spec's Fable seat. Merge, push, release and any `reapply`/`deliver` are the operator's.

---

### Task 22: CLAUDE.md and the SDD record

**Implementer: Sonnet.**

**Files:** Modify `CLAUDE.md`; Create `docs/superpowers/2026-10-2x-title-hygiene-sdd/` (the run's ledger and per-task verdicts; dated by the run).

- [ ] **Step 1:** One bullet in CLAUDE.md's Architecture list, after the taper-markers bullet, in the pieces 1-2 style: what piece 3 adds (D `desc-position` from the selected description, readers (i)/(ii), the slice 1 gate and its show/per-track split, S by canonical source and Q1, C per-track lossless at the tag layer, slice 4, slice 5 on final titles, Q2 self-filled and the replay relaxation), its fixed constants, the slices dropped at Checkpoint A, the accepted limitations (GY!BE `12-28-99`, the untagged residual, `w/ …` in a setlist-gap run, the anchor-span limitation on `fix --suggest-titles`), and the spec, plan, evidence and SDD paths. Name `title_hygiene_probe.py dump|gate|parity|packets` and `replay_holds.py --strip-title-overrides`/`--disable-slices` under Commands.
- [ ] **Step 2:** Copy the SDD ledger and verdicts into the SDD dir (`.superpowers/` is gitignored; copy before any worktree is removed).
- [ ] **Step 3:** Commit `docs: title hygiene in CLAUDE.md; SDD record`.
