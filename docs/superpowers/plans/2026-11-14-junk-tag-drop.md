# Junk-tag drop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop tuning/crowd/silence tracks anywhere and intro/outro tracks at show/set edges, at any
length, in gather; hold the large drops; record every drop in the package, the website and the
host's script input; and build (not run) the tooling that rolls it out across the library.

**Architecture:** A pure rule module (`llama/junk_titles.py`) decides drops, the breaker and the
flag text. `compute_gather` applies it once, after the final titles and set labels exist and before
`Show` is built, re-indexing everything numbered by track; the drops ride `show.json`
`excluded_files` rows (reason `junk title`) into a new optional manifest list `dropped_tracks`.
emcee, transmitter and antenna each read that field on their own. A new script,
`scripts/junk_drop_rollout.py`, builds the membership list and the marking batch on top of
`scripts/bulk_apply.py`'s machinery.

**Tech Stack:** Python 3 (llama, emcee, herder), Python 3.11-compatible transmitter, pydantic,
pytest; antenna is plain ES modules tested with vitest.

**Spec:** `docs/superpowers/specs/2026-11-13-junk-tag-drop-design.md` (approved, reviewed).
Baseline: `docs/superpowers/2026-11-13-junk-tag-drop-evidence/` (`measure.py`, `drops.tsv`:
960 rows, 508 A / 431 B / 21 C, 19 held rows in 19 shows, 699 shows).

## Running this plan

- Work in a worktree at `/Users/shawn/projects/llama/.claude/worktrees/junk-tag-drop-impl` on a
  new branch cut from `junk-tag-drop` (that branch is checked out in the main checkout).
- Give the worktree its own venv, then prove it imports the worktree:
  `python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
  `./.venv/bin/python -c "import llama, emcee, transmitter; print(llama.__file__, emcee.__file__, transmitter.__file__)"`
  must print paths inside the worktree.
- **Test command (every Python task):** `./.venv/bin/python -m pytest -q` from the worktree root
  (the whole suite, offline). Run the task's own tests first with
  `./.venv/bin/python -m pytest <file> -q`. Never a bare `pytest`, never `.venv/bin/pytest`.
- **Antenna:** `cd antenna && npm ci && npm test` (once `npm ci`; then `npm test`).
- Each task ends with one commit on the branch. The message ends with the attribution lines the
  orchestrating session prescribes.
- Read before changing a package: root `CLAUDE.md`, plus `packages/llama/CLAUDE.md`,
  `packages/emcee/CLAUDE.md`, `packages/transmitter/CLAUDE.md`, `antenna/CLAUDE.md`,
  `scripts/CLAUDE.md` for the package the task touches. Each task updates the CLAUDE.md of the
  package it changes (one bullet, facts only).

## Global Constraints

- `llama`, `emcee` and `transmitter` never import each other (existing import tests enforce it).
  Scripts may import llama (and, where they already do, emcee).
- transmitter stays Python 3.11-compatible (no 3.12-only syntax: no PEP 695 generics, no nested
  same-quote f-strings). If docker is available, `packages/transmitter/scripts/test-in-debian12.sh`
  is the gate; otherwise say so in the task report.
- antenna: a deployed module gains no exports; new helpers go in a NEW module; no `innerHTML`,
  `outerHTML`, `insertAdjacentHTML`, `document.write` (`test/asset-bans.test.ts`).
  `antenna/public/player.js`, `nowplaying.js`, `style.css` are frozen.
- Manifest `schema_version` stays 3. `dropped_tracks` is optional; absent, `null` and `[]` all mean
  none in every reader (llama, emcee, transmitter, antenna).
- Exact strings: reason `junk title`; hold flag prefix `junk-title drop held for review: `;
  overrule kind `junk-drop` with adjudicator bar `never`; campaign marking reason
  `junk-title drop`.
- Breaker constants (operator-set; never retune): a drop holds when at least **2 of 3** hold, each a
  strict `>`: duration > **360.0 s**; duration > **0.05** x the show's total running time;
  duration > **1.0** x the show's median track length. Total and median are over the show's tracks
  **before** this rule's drops; a missing `duration_sec` counts as 0 (as `measure.py`).
- Vocabulary (operator's words; never widen), matched with `re.fullmatch(..., re.I)` per part:
  - A words: `tuning(?:\s*up)?|tune\s*up|crowd(?:\s+noise)?|silence` (exactly `measure.py`'s `W`)
  - intro words: `intro(?:duction)?s?`
  - outro words: `outros?`
- `junk.py` is not edited: its regexes, `parts`, the short arm, its constants and the fix-2201
  edge-label rule stay byte-identical.
- `station_mark.COMPARED` is unchanged.
- The now-playing view (timeline, tickets, `nowplaying.js`) does not change.
- No drop, no change: a show with no drop gathers, packages, renders (notes JSON, show page,
  scriptwrite prompt) byte-identically to today. The notes key `dropped` is written only when it
  has at least one valid entry.
- No task touches `~/.llama` (read or write), the station (`/Volumes/media/lma-radio`), hugo, any
  release, tag, `wrangler deploy` or `npm run deploy:assets`. **Single exception: Task 6 reads
  `~/.llama/shows`, `~/.llama/cache` and `~/.llama/config.toml` read-only** and writes only under
  `~/.llama-harness/junk-tag-drop/` and the repo's evidence directory. Tests use fixtures and
  `tmp_path` only.
- New fixtures are captured live from archive.org with `scripts/capture_fixture.py <identifier>`
  (never `--from-cache`, which reads `~/.llama/cache`).
- Never name a file `REPORT*`, `SUMMARY*`, `FINDINGS*` or `ANALYSIS*`.
- The audio-classifier follow-up is out of scope.

## Shared contracts (used across tasks)

`show.json` `excluded_files` row for a drop (appended after the existing rows, pre-drop order):

    {"filename": "gd79-12-05d1t01.mp3", "reasons": ["junk title"], "duration_sec": 280.0,
     "title": "Tuning", "set": "1", "after_track": 0}

`after_track` = the number of KEPT tracks before the dropped one in the pre-drop order (0 = before
the first kept track). `set` = the dropped track's set label.

Manifest top-level (llama `Manifest.dropped_tracks: list[DroppedTrack] | None = None`; `null` when
the show has no drop):

    "dropped_tracks": [{"title": "Tuning", "duration_sec": 280.0, "set": "1", "after_track": 0,
                        "source_file": "gd79-12-05d1t01.mp3", "reason": "junk title"}]

Notes JSON key (transmitter), present only when non-empty: `"dropped": [{"title", "set",
"after_track"}]`.

Website rendering (transmitter `_setlist_html` and antenna's new module share it): kept entries
group exactly as today. A struck entry with `after_track = a` sits right after the kept entry with
1-based global index `a`, in that entry's group; `a = 0` puts it at the start of the first group;
`a` beyond the kept count appends to the last group; several at one position keep input order. It
renders as `<li class="dropped"><s>Title</s></li>`. Numbering counts kept entries only: within a
group, every kept `<li>` that has a struck entry before it in that group carries `value="<its
1-based kept ordinal in the group>"`. With no kept entry at all, struck entries form one group.
Invalid entries (not an object, `title` not a non-empty string, `after_track` not a non-negative
integer, a boolean counting as invalid) are skipped. One CSS rule in `antenna/public/assets/radio.css`
(Task 12): `.jcard li.dropped { list-style: none; color: var(--perf); }`.

## Where this plan settles what the spec left open

- **Placement:** after slice 5, before the short-kept note; every other hold check sees the
  pre-drop list; structure is not re-run (Task 2), so the set-boundary delta is zero by
  construction and Task 6 measures it anyway.
- **Drop record:** on the `excluded_files` row (no new `Show` field). `run_brief` keeps passing
  the whole `show.json`, so the briefing LLM sees the new row keys; no other change there.
- **Re-indexing:** flags, operator notes and structure conflicts are renumbered by one text
  helper (`renumber_text`); `title_paths` are filtered; the in-process `CascadeRecord` keeps
  pre-drop positions and is remapped at its one serialization (`replay._cascade_dict`).
- **Leading-arrow exemption:** applies to the last track of the list each rule is judged on
  (rule A: the original list; rule C: what A left).
- **Numbering struck entries:** `<li value>` alone cannot hide a struck item's own number, so the
  struck `<li>` gets class `dropped` and one CSS rule (`list-style: none`); a stale cached CSS
  shows a stray number on the struck line only, the kept numbers stay right.
- **Byte stability:** the notes key and the scriptwrite note appear only when there is a drop;
  the manifest writes `dropped_tracks: null` when there is none.
- **Recorded pairs:** the list records the station tracks paired with a dropped source file
  (what the step 6 re-check needs).
- **Delivered with no station copy:** keeps `bulk_apply`'s existing `no station copy` outcome
  (campaign mark written, listed, exit 1).
- **Version gate vs. "mark before installing":** `CAMPAIGN_MIN_VERSION` is bumped as the spec
  asks, so the membership arm runs as `replay_holds.py run` from the pinned worktree (not
  `bulk_apply.py arm`), and `mark --apply` checks the pin plus tools at least `2.23.0`.
- **1979-12-05:** the library show is already operator-excluded, so its test runs on a freshly
  captured fixture with no overrides.

## Review Focus

1. A tape where every track drops (an all-`Tuning`/`Crowd` item): expect `no playable tracks`
   held, empty `set_breaks`, no crash — Task 2 test `test_all_tracks_dropped_holds_no_playable_tracks`.
2. Missing durations (`duration_sec` None) on dropped or kept tracks: breaker counts them as 0,
   flag text prints `0:00`, manifest carries `null` — Task 1 `test_breaker_missing_durations`,
   Task 9 `test_dropped_track_duration_none`.
3. A set made only of dropped tracks (an encore that is a lone `Crowd`; set 2 that is only `Intro`):
   the set disappears, breaks stay consistent, the struck entry renders at the end of the last
   group — Task 2 `test_set_of_only_dropped_tracks_vanishes`, Task 11/12 tail-placement tests.
4. Damaged `dropped_tracks` / `dropped` values (a string, a dict, entries missing keys,
   `after_track` `true`, `-1`, `"3"`, beyond the kept count): every reader tolerates and renders
   the rest — Tasks 9, 10, 11, 12 `*_damaged_*` tests.
5. Re-gathering an already re-gathered show is idempotent and not stale, and `fix --include` of a
   dropped file keeps it and clears its hold — Task 8 `test_regather_is_idempotent_and_not_stale`,
   `test_fix_include_restores_a_dropped_track_and_clears_its_hold`.

---

### Task 1: The rule module `llama/junk_titles.py`

Implementer model: sonnet

**Files:**
- Create: `packages/llama/src/llama/junk_titles.py`
- Test: `packages/llama/tests/test_junk_titles.py`

**Interfaces:**
- Consumes: `llama.junk.parts`, `junk.TIME_PAREN`, `junk.TRAILING_ARROW`, `junk.LEADING_ARROW`,
  `llama.titles.clean_tag_title` (all existing, unchanged).
- Produces (later tasks rely on these exact names):
  - `REASON = "junk title"`, `HOLD_PREFIX = "junk-title drop held for review: "`,
    `BREAKER_MIN_SEC = 360.0`, `BREAKER_SHOW_FRACTION = 0.05`, `BREAKER_MEDIAN_MULTIPLE = 1.0`,
    `BREAKER_NEEDED = 2`.
  - `@dataclass(frozen=True) class DropInput: filename: str; title: str; set: str; duration_sec: float | None; raw_arrow: bool = False`
  - `@dataclass(frozen=True) class Drop: position: int; rule: str` (0-based pre-drop position; `"A"|"B"|"C"`)
  - `@dataclass(frozen=True) class JunkDrop: filename: str; title: str; set: str; duration_sec: float | None; rule: str; position: int; after_track: int; held: bool`
  - `is_a_title(title: str) -> bool`, `is_intro_title(title: str) -> bool`, `is_outro_title(title: str) -> bool`
    (every part from `junk.parts(clean_tag_title(title))` fullmatches the vocabulary; intro/outro
    titles may mix in A words; an empty part list is False)
  - `trailing_arrow(title: str, *, raw_arrow: bool = False) -> bool` and `leading_arrow(title: str) -> bool`
    (read on `junk.TIME_PAREN.sub("", title)` of the uncleaned final title)
  - `plan_drops(tracks: Sequence[DropInput], *, include: frozenset[str] = frozenset()) -> list[Drop]` (sorted by position)
  - `show_stats(durations: Sequence[float | None]) -> tuple[float, float]` → `(total, median)`, None as 0, `(0.0, 0.0)` for an empty list
  - `held(duration: float | None, *, total: float, median: float) -> bool`
  - `hold_flag(drop: JunkDrop, *, total: float, median: float) -> str`
  - `renumber_text(text: str, numbers: Mapping[int, int | None]) -> str`

`plan_drops` algorithm (spec "The rule", "Edge runs", "Segue arrows keep"):
1. Rule A over the original list: position i drops when `filename not in include`,
   `not trailing_arrow(title, raw_arrow=...)`, not (i is the original last position and
   `leading_arrow(title)`), and `is_a_title(title)`.
2. On the list A left (`rest`, original order), once each, no iteration: rule B drops `rest[k]`
   when it is first (`k == 0` or `rest[k-1].set != rest[k].set`), not included, not trailing-arrowed,
   and `is_intro_title`; rule C drops `rest[-1]` when not included, not trailing-arrowed, not
   leading-arrowed, and `is_outro_title`. A position both B and C would drop is one drop, rule `B`.

`hold_flag` exact form:
`junk-title drop held for review: '<title>' (<m:ss>, <pct>% of show, <x>x median) file <filename>`
with `s = int(round(duration or 0))`, `m:ss = f"{s // 60}:{s % 60:02d}"`,
`pct = f"{100 * d / total:.1f}"` (0.0 when total is 0), `x = f"{d / median:.2f}"` (0.00 when median is 0).

`renumber_text` contract: rewrites only lowercase, word-bounded references `track N`, `tracks N-M`,
`tracks N, M[, ...]`, `track(s) N[, M ...]`; `numbers` maps old 1-based numbers (missing key = left
as written). A kept number becomes its new number. A single reference to a dropped track becomes
`dropped track`; a dropped member of a list is removed (all removed: `dropped tracks`); a range maps
to the new numbers of its first and last kept members (one kept: `track N`; none:
`dropped tracks`). An identity mapping returns the text unchanged.

- [ ] **Step 1: Write the failing tests** in `test_junk_titles.py`, including:

```python
from llama.junk_titles import DropInput as D, plan_drops, held, hold_flag, JunkDrop, renumber_text, show_stats

def _drops(rows, **kw):   # rows: (title, set) pairs; filename f"f{i}.mp3", duration 100
    return [(d.position, d.rule) for d in plan_drops(
        [D(f"f{i}.mp3", t, s, 100.0) for i, (t, s) in enumerate(rows)], **kw)]

@pytest.mark.parametrize("title", ["Tuning", "crowd", "Crowd Noise", "Crowd/Tuning", "crowd & tuning",
    "Tuning Up", "Tune Up", "tuneup", "Silence", "TUNING", "(crowd)", "[crowd]", "***crowd noise***",
    "Crowd + Tuning", "Crowd~", "01 Tuning", "Tuning (2:01)"])
def test_rule_a_drops_anywhere(title):
    assert _drops([("Song", "1"), (title, "1"), ("Song 2", "1")]) == [(1, "A")]

@pytest.mark.parametrize("title", ["Crowd/Banter", "crowd encore call", "Mexican Hat Dance Tuning",
    "Crowded Tub", "Tuning >", "Tuning ->", "Crowd > (1:20.19)", "Applause", "Intro", "Banter"])
def test_rule_a_keeps(title):
    assert _drops([("Song", "1"), (title, "1"), ("Song 2", "1")]) == []

def test_raw_arrow_keeps(): # slice 2a stripped the arrow from the shipped title
    assert plan_drops([D("a", "S", "1", 1), D("b", "Crowd", "1", 1, raw_arrow=True), D("c", "S", "1", 1)]) == []

@pytest.mark.parametrize("title", ["Intro", "Intro/Tuning", "Tuning & Intro", "crowd/intro",
    "Introductions", "(Intro)", "[Intro]", "Intro,", "~intro~"])
def test_rule_b_at_show_and_set_start(title):
    assert _drops([(title, "1"), ("Song", "1"), (title, "2"), ("Song", "2")]) == [(0, "B"), (2, "B")]

@pytest.mark.parametrize("title", ["Intro Jam", "Intro > Song", "Intro >"])
def test_rule_b_keeps_at_start(title):
    assert _drops([(title, "1"), ("Song", "1")]) == []

def test_intro_mid_set_keeps():
    assert _drops([("Song", "1"), ("Intro", "1"), ("Song", "1")]) == []

def test_rule_c_last_only():
    assert _drops([("Song", "1"), ("Outro", "1")]) == [(1, "C")]
    assert _drops([("Song", "1"), ("-> Outro", "1")]) == []
    assert _drops([("Song", "1"), ("Outro", "1"), ("Song", "1")]) == []

def test_edge_runs_go_whole():
    assert _drops([("S", "1"), ("Crowd", "2"), ("Intro", "2"), ("S", "2")]) == [(1, "A"), (2, "B")]
    assert _drops([("S", "1"), ("Outro", "1"), ("Crowd", "1")]) == [(1, "C"), (2, "A")]

def test_no_iteration_to_a_fixed_point():
    assert _drops([("Intro", "1"), ("Intro", "1"), ("S", "1")]) == [(0, "B")]

def test_include_wins():
    assert _drops([("S", "1"), ("Tuning", "1")], include=frozenset({"f1.mp3"})) == []

def test_breaker_two_of_three():
    assert held(400, total=6000, median=300)        # 3 of 3
    assert held(370, total=10000, median=300)       # >360 and >median
    assert not held(400, total=10000, median=500)   # >360 only
    assert not held(360, total=7000, median=360)    # strict >: 360 is not > 360; 5.14% passes alone

def test_breaker_missing_durations():
    assert show_stats([None, 100.0, None]) == (100.0, 0.0)
    assert not held(None, total=100.0, median=0.0)

def test_hold_flag_text():
    d = JunkDrop("gd79-12-05d1t01.mp3", "Tuning", "1", 280.4, "A", 0, 0, True)
    assert hold_flag(d, total=4000.0, median=250.0) == (
        "junk-title drop held for review: 'Tuning' (4:40, 7.0% of show, 1.12x median) "
        "file gd79-12-05d1t01.mp3")

def test_renumber_text():
    m = {1: 1, 2: 2, 3: None, 4: 3, 5: 4, 6: 5, 7: 6}
    assert renumber_text("segues restored: track 5 'X' (E3); track 7 'Y' (E2)", m) == \
        "segues restored: track 4 'X' (E3); track 6 'Y' (E2)"
    assert renumber_text("merged track(s) 4, 6 span a set break", m) == "merged track(s) 3, 5 span a set break"
    assert renumber_text("lossless title: tracks 2-5", m) == "lossless title: tracks 2-4"
    assert renumber_text("short-kept track 3 'Tuning'", m) == "short-kept dropped track 'Tuning'"
    assert renumber_text("tracks 3-3 demoted", m) == "dropped tracks demoted"
    assert renumber_text("set 2 has track 9 'Track 2'", m) == "set 2 has track 9 'Track 2'"
    ident = {i: i for i in range(1, 8)}
    assert renumber_text("tracks 1, 2, 3 and track 4", ident) == "tracks 1, 2, 3 and track 4"
```

- [ ] **Step 2: Run** `./.venv/bin/python -m pytest packages/llama/tests/test_junk_titles.py -q` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `junk_titles.py` per the Interfaces block (module docstring cites the spec; constants carry the "operator-set, do not retune" comment).
- [ ] **Step 4: Run** the file, then the whole suite — Expected: PASS.
- [ ] **Step 5: Commit** `feat(llama): junk-title drop rule module (pure)`.

---

### Task 2: Wire the rule into `compute_gather`

Implementer model: opus

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (`CascadeRecord`, `title_cascade`, `GatherResult`, `compute_gather`)
- Modify: `packages/llama/CLAUDE.md` (Domain gotchas: one bullet "Junk-title drop")
- Test: `packages/llama/tests/test_gather_junk_drop.py`

**Interfaces:**
- Consumes: Task 1's `plan_drops`, `DropInput`, `JunkDrop`, `show_stats`, `held`, `hold_flag`,
  `renumber_text`, `REASON`, `trailing_arrow`; `titles.set_breaks`.
- Produces:
  - `CascadeRecord.short2a_arrowed: tuple[int, ...] = ()` — 0-based positions where slice 2a
    (`accept_short_tags`) accepted a tag whose raw tag-layer text has a trailing arrow
    (`junk_titles.trailing_arrow(raw_tag)`).
  - `GatherResult.junk_drops: tuple[JunkDrop, ...] = ()` and
    `GatherResult.kept_positions: tuple[int, ...] | None = None` (pre-drop 0-based position of
    each kept track, in order; `None` when nothing dropped).
  - The `excluded_files` row shape in "Shared contracts".

Placement (spec "Placement in gather"; decided here): the drop runs in `compute_gather` right after
the slice-5 `cosmetic_strip` block and before the "short-kept track ... wholly junk" note loop, so
it sees final titles and final set labels. Everything above it (structure, taper, segue restore,
venue chain, closer tripwire, `filler_tail_closers`, multi-event span, `structure_guard`,
`unresolved track titles`, `low-confidence setlist`) is computed on the pre-drop list exactly as
today; structure is not re-run, so set labels of kept tracks cannot move. Overrides were resolved
against the pre-drop list (`title_inputs` is unchanged), so a `set_breaks`/`encore_after` key on a
dropped file lands after the last kept file before it through the labels.

Call the rule through the module (`junk_titles.plan_drops(...)`) so tests can patch it. When it
returns nothing, the function's result is exactly today's (same objects, same order;
`junk_drops=()`, `kept_positions=None`). When it drops:
1. Build `DropInput` per track from `t.title`, `t.set`, `t.duration_sec`,
   `raw_arrow = i in cascade.record.short2a_arrowed`; `include = frozenset(overrides.include)`.
2. `total, median = show_stats(...)` over the pre-drop tracks; each drop becomes a `JunkDrop` with
   `after_track` as defined in Shared contracts and `held = held(...)`.
3. Kept tracks: re-indexed 1..n; a kept track whose pre-drop next track was dropped gets
   `segue=False` unless `trailing_arrow(t.title)`; nothing else on a kept track changes.
4. `set_breaks = titles.set_breaks(kept)` (also on the override path).
5. `numbers` = old→new map; `renumber_text` is applied to every flag, every `op_notes` entry
   produced before the drop and `structure_info.conflicts`; `title_paths` keeps the kept positions
   only. (The short-kept note loop after the drop already reads the new indices; it is not
   renumbered again.)
6. Drop rows appended to `excluded`; one `hold_flag` per held drop appended to `flags`.
7. `no playable tracks` is evaluated on the kept list (moved below the drop; added when the kept
   list is empty and not already present).
`_apply_overrules` stays last.

- [ ] **Step 1: Write failing tests** in `test_gather_junk_drop.py`, on a fixture-derived item
  (follow `test_stage_gather.py`'s `StubIA` and `_enumerate_tag_titles` pattern on
  `gd73_metadata.json`, re-tagging tracks), including:
  - `test_tuning_track_drops_and_is_recorded`: a mid-set `Tuning` file is not in `show.tracks`;
    indices are 1..n; its `excluded_files` row equals the Shared-contracts shape with
    `after_track` = kept count before it; `res.junk_drops[0].rule == "A"`; `res.kept_positions`
    skips its position.
  - `test_no_drop_show_is_unchanged`: for the unmodified fixture, `junk_drops == ()`,
    `kept_positions is None`, and `show.model_dump()` equals the result with
    `llama.junk_titles.plan_drops` monkeypatched to return `[]`.
  - `test_segue_into_a_dropped_track_is_lost_unless_arrowed`: kept track before a dropped one with
    `segue=True` and title `Song` loses it; with title `Song >` keeps it.
  - `test_set_breaks_recomputed_after_drop` and `test_set_of_only_dropped_tracks_vanishes`
    (an encore consisting of one `Crowd` file; via `overrides.encore_after` on the file before it).
  - `test_encore_after_on_a_dropped_crowd_lands_on_the_previous_kept_file` (synthetic; the real
    show is Task 3).
  - `test_include_keeps_a_junk_title` (`overrides.include` names the file).
  - `test_breaker_holds_with_flag` (a 400 s `Crowd` in a short show → `needs_review`, flag equals
    `hold_flag(...)`; the file is still dropped).
  - `test_all_tracks_dropped_holds_no_playable_tracks` (every tag `Tuning`/`Crowd`).
  - `test_flags_and_notes_are_renumbered`: monkeypatch `llama.stages.gather.structure_guard` to
    return `"merged track(s) 5 span a set break"` with track 3 dropped → flag reads track 4; and one
    op_note from a real producer after the drop (e.g. a slice-5 strip, tag `03:12 Bertha`) is
    renumbered.
  - `test_raw_2a_arrow_keeps` (a 2a-accepted tag `Crowd >` shipped as `Crowd`; use the existing 2a
    test setup in `test_stage_gather.py` as a model).
- [ ] **Step 2: Run** the file — Expected: FAIL.
- [ ] **Step 3: Implement** per the placement steps above (one private helper in gather is fine).
- [ ] **Step 4: Run** the file, then the whole suite. If an existing test changes because one of
  its fixtures now drops a track under the spec's rule, update that expectation only when the new
  value is what the spec mandates, and list every such test in the task report.
- [ ] **Step 5: Commit** `feat(llama): gather drops junk-titled tracks (rule A/B/C, breaker)`.

---

### Task 3: Real-item fixture tests (1979-12-05, railroadearth encore)

Implementer model: sonnet

**Files:**
- Create: `packages/llama/tests/fixtures/gd1979-12-05.sbd.miller.112163.flac16.json`,
  `packages/llama/tests/fixtures/rre2006-02-18.oktava.flac16.json` (captured)
- Test: `packages/llama/tests/test_gather_junk_drop.py` (append)

**Interfaces:** Consumes Task 2's `compute_gather` behaviour and `GatherResult.junk_drops`.

- [ ] **Step 1: Capture** (live archive.org, read-only):
  `./.venv/bin/python scripts/capture_fixture.py gd1979-12-05.sbd.miller.112163.flac16` and
  `./.venv/bin/python scripts/capture_fixture.py rre2006-02-18.oktava.flac16`.
- [ ] **Step 2: Write tests** (they should pass at once; if they do not, stop and report BLOCKED
  with the observed tracks):
  - `test_1979_12_05_tuning_drops`: empty overrides; `gd79-12-05d1t01.mp3` is not a track, its row
    has reason `junk title`, title `Tuning`, `after_track == 0`; `show.tracks[0].title` starts
    `Alabama Getaway`.
  - `test_railroadearth_2006_02_18_encore_on_dropped_crowd`: overrides
    `set_breaks=["rre2006-02-18d1t07.oktava.mp3"]`, `encore_after="rre2006-02-18d3t06.oktava.mp3"`;
    expect 19 tracks, `set_breaks == [7, 17]`, track 17 `Bird In A House` set `"2"`, track 18
    `Shockenaw Mountain Breakdown` set `"encore"`, the `d3t06` row title `Crowd`, set `"2"`,
    `after_track == 17`, not held.
- [ ] **Step 3: Run** the file and the whole suite — Expected: PASS.
- [ ] **Step 4: Commit** `test(llama): junk-title drop on real items (1979-12-05, rre 2006-02-18)`.

---

### Task 4: Replay rows carry the drops; cascade record re-indexed

Implementer model: sonnet

**Files:**
- Modify: `packages/llama/src/llama/replay.py` (`ShowReplay`, `replay_show`, `_cascade_dict`)
- Test: `packages/llama/tests/test_junk_drop_replay.py`

**Interfaces:**
- Consumes: `GatherResult.junk_drops`, `GatherResult.kept_positions`.
- Produces: `ShowReplay.junk_drops: list[dict] = []`, each
  `{"filename", "title", "set", "after_track", "duration_sec", "rule", "held"}` in drop order;
  `_cascade_dict(rec, keep: Sequence[int] | None = None)` — with `keep`, every position is mapped
  to its index in `keep` (then 1-based as today) and positions not in `keep` are omitted;
  `keep=None` is today's output exactly. `reapply` and `scripts/replay_holds.py` need no change:
  both go through `compute_gather` (spec: one implementation).

- [ ] **Step 1: Write failing tests**: `test_replay_row_lists_junk_drops` (replay a tmp-workspace
  show built on the Task 3 1979 fixture, or the Task 2 synthetic item, with the existing replay
  test helpers: `row.junk_drops` has the `Tuning` entry and `row.filenames` lacks it);
  `test_cascade_dict_remaps_positions` (construct a minimal `CascadeRecord`; `keep=(0, 2, 3)` maps
  0-based 3 → `"3"`, omits 1); `test_cascade_dict_identity_without_keep`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** the file and the suite — PASS.
- [ ] **Step 5: Commit** `feat(llama): replay rows carry junk-title drops`.

---

### Task 5: Measurement script against the baseline

Implementer model: sonnet

**Files:**
- Create: `scripts/junk_drop_measure.py`, `scripts/test_junk_drop_measure.py`
- Modify: `scripts/CLAUDE.md` (Replay and probe harnesses: one bullet)

**Interfaces:**
- Consumes: arm JSON from `scripts/replay_holds.py run` (rows keyed by slug with `filenames`,
  `titles`, `sets`, `segues`, `outcome`, `needs_llm`, and Task 4's `junk_drops`; a base-arm row
  lacks `junk_drops` = none); the baseline TSV columns of `drops.tsv`; `llama.junk.parts`.
- Produces: `junk_drop_measure.py compare --base B --cand C --baseline TSV --shows DIR --out OUT`
  (read-only; refuses, exit 2, an `--out` that is inside `--shows`' parent directory, i.e. the
  library root). Writes into OUT:
  - `summary.md`: drop rows and shows by rule (A/B/C) and held rows/shows, candidate vs baseline;
    the expected-delta reconciliation table (categories below with counts); hold changes is not
    its job (that is `replay_holds.py compare`).
  - `differences.tsv`: every (slug, filename) in exactly one side, columns
    `side, slug, filename, title_baseline, title_cand, rule, category`.
    Candidate-only categories, first match: `title-differs` (show.json title for that file differs
    from the candidate title), `not-in-show.json`, `parts-split` (no `measure.py` regex — `A`,
    `BS`, `BE`, copied verbatim — matches the cleaned candidate title), `edge-run` (rule B or C),
    `other`. Baseline-only, first match: `operator-include` (file in the show's
    `overrides.json` `include`), `arrowed` (candidate final title has a trailing arrow),
    `needs-llm-row` (candidate row outcome `needs-llm` or `unreplayable`), `title-differs`,
    `not-kept`, `other`.
  - `vocabulary.txt`: every candidate drop whose parts (`junk.parts(clean_tag_title(title))`) are
    not all in the union vocabulary (Global Constraints); exit 3 when non-empty.
  - `kept_track_deltas.tsv`: per filename kept in both arms, any difference in set label, title or
    segue between base and cand, with a column `adjacent_to_drop` (the cand-side next pre-drop
    track was dropped).
  - `override_keys.tsv`: shows whose `overrides.json` `set_breaks`/`encore_after` names a
    candidate-dropped file, with the candidate set labels of the kept tracks on each side of it.
- [ ] **Step 1: Write failing tests** on tiny synthetic arms, TSV and shows dir under `tmp_path`:
  one row per category, `test_vocabulary_violation_exits_3`, `test_base_row_without_junk_drops`,
  `test_kept_track_set_change_is_reported`, `test_refuses_out_inside_shows`.
- [ ] **Step 2–4:** run (FAIL), implement, run the file and the suite (PASS).
- [ ] **Step 5: Commit** `feat(scripts): junk-title drop measurement against the 2026-11-13 baseline`.

---

### Task 6: Library replay measurement (read-only)

Implementer model: opus

This task READS `~/.llama/shows`, `~/.llama/cache` and `~/.llama/config.toml` read-only. It
writes only under `~/.llama-harness/junk-tag-drop/` and
`docs/superpowers/2026-11-14-junk-tag-drop-evidence/`. It changes no code. It does not touch the
station.

**Files:**
- Create: `docs/superpowers/2026-11-14-junk-tag-drop-evidence/replay.md` (and copies of
  `summary.md`, `differences.tsv`, `vocabulary.txt`, `kept_track_deltas.tsv`, `override_keys.tsv`;
  never the arms)

- [ ] **Step 1: Base arm (pre-change code).** Confirm the main checkout's code equals the plan's
  base: `git -C /Users/shawn/projects/llama diff --quiet a03fc04e HEAD -- packages scripts` (exit 0)
  and `/Users/shawn/projects/llama/.venv/bin/python -c "import llama; print(llama.__file__)"` is
  under `/Users/shawn/projects/llama/packages/`. Then, in the background:
  `/Users/shawn/projects/llama/.venv/bin/python /Users/shawn/projects/llama/scripts/replay_holds.py run --all --out ~/.llama-harness/junk-tag-drop/base.json`
  If either check fails, stop and report BLOCKED (do not build a base any other way unasked).
- [ ] **Step 2: Candidate arm** (worktree code, committed tree):
  `./.venv/bin/python scripts/replay_holds.py run --all --out ~/.llama-harness/junk-tag-drop/cand.json`
- [ ] **Step 3: Hold deltas:**
  `./.venv/bin/python scripts/replay_holds.py compare ~/.llama-harness/junk-tag-drop/base.json ~/.llama-harness/junk-tag-drop/cand.json --out ~/.llama-harness/junk-tag-drop/compare`
  (exit 2 for differing show sets/config, or exit 3 for base reproduction under 99%, is a stop:
  report it; never pass `--no-repro-gate` without the parent's go).
- [ ] **Step 4: Baseline comparison:**
  `./.venv/bin/python scripts/junk_drop_measure.py compare --base ~/.llama-harness/junk-tag-drop/base.json --cand ~/.llama-harness/junk-tag-drop/cand.json --baseline docs/superpowers/2026-11-13-junk-tag-drop-evidence/drops.tsv --shows ~/.llama/shows --out ~/.llama-harness/junk-tag-drop/measure`
- [ ] **Step 5: Write `replay.md`**: commands and commit; counts table (cand vs baseline: rows and
  shows by rule, held rows/shows); the reconciliation against the spec's Acceptance expectations —
  ~31 extra drops from `junk.parts` splitting, the 26 arrowed titles still keeping, the 2 operator
  includes not dropping (`billystrings-2017-07-15`, `cubensis-2011-01-22`), the extra B/C edge-run
  drops — with every difference listed by category; `vocabulary.txt` (must be empty); every hold
  added or cleared between the arms OTHER than `junk-title drop held for review:` flags, with show
  and flag (from the compare reports); `kept_track_deltas.tsv` summary (expected: segue losses
  adjacent to drops only; any set or title change is a finding); the `override_keys.tsv` rows
  (expected 12 encore/break shows, each break after the last kept file before the drop).
- [ ] **Step 6: Commit** `docs(junk-tag-drop): library replay measurement against the baseline`.

### CHECKPOINT A — stop for the parent's go

The orchestrator stops here and sends the parent `replay.md`'s counts table, the reconciliation,
the non-zero difference categories, the hold adds/clears, the vocabulary result and any kept-track
set/title change. It continues only on the parent's explicit go (the parent may take the numbers
to the operator).

---

### Task 7: Overrule kind and adjudicator bars

Implementer model: sonnet

**Files:**
- Modify: `packages/llama/src/llama/overrules.py` (`_PATTERNS`),
  `packages/llama/src/llama/adjudicator/gate.py` (`OVERRULE_BAR`, `REFUSED_INCLUDE_REASONS`, `_title_edit`)
- Modify: `packages/llama/CLAUDE.md` (Adjudicator bullet: one clause)
- Test: `packages/llama/tests/test_overrules.py`, `packages/llama/tests/test_adjudicator_gate.py` (append)

**Interfaces:**
- Consumes: `junk_titles.HOLD_PREFIX`, `junk_titles.REASON`.
- Produces: `_PATTERNS` entry `(re.compile(r"^junk-title drop held for review: .* file (.+)$", re.S), "junk-drop", "raw")`
  (the subject is the filename; numbers never key it); `OVERRULE_BAR["junk-drop"] = "never"`;
  `REASON` joins `REFUSED_INCLUDE_REASONS`; `_title_edit` returns propose-only for a `set_title`
  whose file's `excluded_files` row carries `REASON`.
- [ ] **Step 1: Tests:** `test_junk_drop_flag_key_is_the_filename` (two flags differing only in
  duration/percent map to the same key); `test_junk_drop_overrule_turns_hold_into_note` (a gather
  with a held drop plus a recorded overrule of that kind/subject → `overruled: ...` note, not held);
  `test_adjudicator_never_overrules_junk_drop`; `test_include_of_junk_title_file_is_propose_only`;
  `test_set_title_on_junk_title_file_is_propose_only`.
- [ ] **Step 2–4:** FAIL, implement, PASS (file and suite).
- [ ] **Step 5: Commit** `feat(llama): junk-drop hold is operator-only (overrule kind, gate bars)`.

---

### Task 8: Staleness against the post-drop list

Implementer model: opus

**Files:**
- Modify: `packages/llama/src/llama/staleness.py`, `packages/llama/src/llama/cli.py`
  (`--suggest-titles` comparison near `kept_names != track_names`)
- Test: `packages/llama/tests/test_junk_drop_staleness.py`

**Interfaces:**
- Produces: `staleness.expected_track_files(kept: Sequence[str], show: Show) -> list[str]` — `kept`
  (gather's `final_kept(...).kept` names, in order) minus the filenames of `show.excluded_files`
  rows whose `reasons` contain `junk_titles.REASON`. `stale_message` and the `--suggest-titles`
  comparison both compare `show.tracks` filenames with it (the canonical in `--suggest-titles`
  keeps being built over the pre-drop `kept`, as gather builds it).
- [ ] **Step 1: Tests:** `test_show_the_rule_changed_is_not_stale` (gather a dropped show into a
  tmp workspace through the CLI path, then `stale_message(...) is None`);
  `test_genuinely_stale_show_still_refused` (an edited `overrides.exclude` with `--no-run`);
  `test_suggest_titles_not_declined_on_a_dropped_show`; `test_regather_is_idempotent_and_not_stale`
  (`redo --from gather` twice: identical `show.json`); `test_fix_include_restores_a_dropped_track_and_clears_its_hold`
  (a held drop; `fix --include <file>` → track kept, no junk row, not held);
  `test_show_tracks_lists_junk_title_reason` (`llama show <name> --tracks` prints the row with
  reason `junk title`, distinct from `implausibly short`).
- [ ] **Step 2–4:** FAIL, implement, PASS (file and suite).
- [ ] **Step 5: Commit** `fix(llama): staleness compares against gather's post-drop list`.

---

### Task 9: `dropped_tracks` in the package; equal-copy tests unchanged

Implementer model: sonnet

**Files:**
- Modify: `packages/llama/src/llama/models.py` (`DroppedTrack`, `Manifest.dropped_tracks`),
  `packages/llama/src/llama/manifest.py` (`build_manifest`), `packages/llama/src/llama/stages/package.py`
- Modify: root `CLAUDE.md` (the Architecture bullet on manifest v3: one clause naming the
  optional `dropped_tracks` list)
- Test: `packages/llama/tests/test_junk_drop_package.py`

**Interfaces:**
- Produces: `class DroppedTrack(BaseModel): title: str; duration_sec: float | None = None; set: str; after_track: int; source_file: str; reason: str`
  (permissive, like the other persisted models); `Manifest.dropped_tracks: list[DroppedTrack] | None = None`;
  `build_manifest(..., dropped_tracks: list[DroppedTrack] | None = None)`; `build_package` passes the
  `REASON` rows of `show.excluded_files` in row order (`source_file` = row `filename`, `reason` =
  `REASON`), or `None` when there are none.
- [ ] **Step 1: Tests:** `test_package_writes_dropped_tracks` (manifest JSON equals the Shared
  contracts example for a show with one drop row); `test_package_without_drops_writes_null`;
  `test_manifest_reads_absent_null_empty_and_list`; `test_dropped_track_duration_none`;
  `test_station_readers_tolerate_damaged_dropped_tracks` (llama reads station manifests as raw
  JSON: `station_mark.manifest_differences`, `deliver`'s voiced-destination check and
  `audio_reuse.plan_reuse` behave as today on a station manifest whose `dropped_tracks` is a
  string, a dict, or a list with a malformed entry); `test_compared_is_unchanged` (pins
  `station_mark.COMPARED` to today's tuple and `"dropped_tracks"` absent from it);
  `test_clear_mark_ignores_dropped_tracks` and `test_replace_voiced_equal_test_ignores_dropped_tracks`
  (library and station manifests equal on COMPARED but differing in `dropped_tracks`: `clear-mark`
  clears; `deliver --replace-voiced` refuses as "equals the voiced station copy"; use the existing
  `test_clear_mark.py` / `test_deliver_gate.py` setups).
- [ ] **Step 2–4:** FAIL, implement, PASS (file and suite).
- [ ] **Step 5: Commit** `feat(llama): manifest dropped_tracks (optional, schema stays v3)`.

---

### Task 10: emcee reads and preserves `dropped_tracks`

Implementer model: sonnet

**Files:**
- Modify: `packages/emcee/src/emcee/scriptwrite.py` (`write_script` inputs),
  `packages/emcee/src/emcee/prompts/scriptwrite.md` (line 91 becomes `{{dropped_note}}{{encore_note}}`)
- Modify: `packages/emcee/CLAUDE.md` (Architecture: one clause on the dropped note)
- Test: `packages/emcee/tests/test_dropped_tracks.py`

**Interfaces:**
- Produces: `scriptwrite.dropped_note(manifest: dict) -> str` — `""` when `dropped_tracks` is
  absent, `null`, `[]`, not a list, or has no entry with a non-empty string `title`; otherwise
  exactly (entries in order, duration as `m:ss` when numeric else omitted, position
  `before track 1` for `after_track == 0`, `after track N` for an int N > 0, omitted otherwise):

```
Cut from this broadcast as non-music: "Tuning" (4:40, before track 1); "Crowd" (2:05, after track 11). These are normally not worth mentioning; mention one only when it matters, for example a long cut that explains a jump in the show.
Dropped titles are not songs: never put one in mentioned_songs.
```
  (each line ends with `\n`). `script_guard` is unchanged.
- [ ] **Step 1: Tests:** `test_dropped_note_text`; `test_prompt_byte_identical_without_drops`
  (render the scriptwrite template with the four "none" forms: identical to today's render);
  `test_prompt_carries_note_with_drops` (fake provider captures the prompt);
  `test_dropped_note_damaged_values` (string, dict, entry without title, `after_track` `true`/`-1`/`"3"`);
  `test_rewrite_manifest_preserves_dropped_tracks`; `test_retitle_plan_accepts_dropped_tracks`;
  `test_status_and_readiness_with_each_form` (`station.scan`/`readiness` on packages with the field
  absent, null, `[]`, a list).
- [ ] **Step 2–4:** FAIL, implement, PASS (file and suite).
- [ ] **Step 5: Commit** `feat(emcee): scriptwrite sees dropped tracks; manifest field preserved`.

---

### Task 11: transmitter notes key and static setlist

Implementer model: sonnet

**Files:**
- Modify: `packages/transmitter/src/transmitter/site.py` (`build_notes`, `_setlist_html`, `render_show_page`)
- Modify: `packages/transmitter/CLAUDE.md` (one sentence)
- Test: `packages/transmitter/tests_transmitter/test_site_dropped.py`

**Interfaces:**
- Produces: `build_notes` adds `"dropped": [{"title", "set", "after_track"}]` from the manifest's
  `dropped_tracks` (valid entries only, per Shared contracts; the key is absent when none, so the
  notes doc is byte-identical for every show without a drop); `_setlist_html(setlist, dropped=())`
  implements the Shared-contracts rendering, byte-identical to today with no dropped entries;
  `render_show_page` passes `notes.get("dropped") or ()`. The `setlist` key is unchanged.
- [ ] **Step 1: Tests:** `test_build_notes_without_field_is_unchanged` (absent/null/`[]` → no
  `dropped` key, dict equal to today's); `test_build_notes_lists_valid_entries`;
  `test_build_notes_damaged_dropped_tracks` (string, dict, bad entries); `test_setlist_html_unchanged_without_dropped`;
  `test_struck_entry_inline_and_not_counted` (kept 1,2 | drop after 2 | kept 3 in one set →
  `<li>A</li><li>B</li><li class="dropped"><s>Tuning</s></li><li value="3">C</li>`);
  `test_struck_entry_at_start_joins_first_group`; `test_struck_after_last_set_joins_last_group`;
  `test_after_track_beyond_count_appends`; `test_only_struck_entries`;
  `test_package_eligibility_with_each_form` (station package reading with the field absent, null,
  `[]`, a list).
- [ ] **Step 2–4:** FAIL, implement, PASS (file and the suite; Debian-12 script if docker exists).
- [ ] **Step 5: Commit** `feat(transmitter): dropped tracks struck through on the show page`.

---

### Task 12: antenna panel merges struck entries (new module)

Implementer model: sonnet

**Files:**
- Create: `antenna/public/assets/dropped.js`, `antenna/test/dropped.test.ts`
- Modify: `antenna/public/assets/panel.js` (`setlistCard` and its caller; no new exports),
  `antenna/public/assets/radio.css` (the one rule in Shared contracts)
- Modify: `antenna/CLAUDE.md` (player bullet: one sentence)

**Interfaces:**
- Consumes: `setlistLine` from `./notes.js`, `tidyTitle` from `./timeline.js` (existing exports;
  `notes.js` and `timeline.js` are not edited).
- Produces: `dropped.js` exports `mergeDropped(setlist, dropped)` →
  `[{ set, items: [{ text: string, struck: boolean, value: number | null }] }]`, the Shared-contracts
  algorithm (kept text = `setlistLine(entry)`, struck text = `tidyTitle(title)`; `value` set as in
  the contract, else `null`); with `dropped` absent/null/`[]`/invalid it equals `groupSets(setlist)`
  mapped to `{text, struck: false, value: null}`. `panel.js` builds the card from
  `mergeDropped(notes.setlist || [], notes.dropped)` (the raw notes it already fetched), rendering a
  struck item as `el("li", "dropped")` holding `el("s", null, text)` and setting `li.value` when
  `value` is not null. `panelModel` is not changed.
- [ ] **Step 1: Tests** in `dropped.test.ts`, one `it` per Task 11 rendering case (inline and not
  counted, start of the first group, tail of the last group, beyond the kept count, only struck
  entries), asserted on the model (`text`, `struck`, `value`), plus `ignores a damaged dropped
  value` (string, object, bad entries) and `equals groupSets without dropped` (absent, null, `[]`).
- [ ] **Step 2–4:** `cd antenna && npm test` (FAIL), implement, `npm test` (PASS; if the pages
  freshness check fails, `npm run pages` and include `src/pages.ts`). `asset-bans` must pass.
- [ ] **Step 5: Commit** `feat(antenna): notes panel strikes dropped tracks (new module)`.

### CHECKPOINT B — stop for the parent's go before the rollout tooling

The orchestrator stops and reports: Tasks 7–12 status, any test expectation Task 2 changed, the
transmitter 3.11 result, and the whole-suite and `npm test` results. Rollout tooling (Tasks 13–15)
starts only on the parent's explicit go.

---

### Task 13: Membership list (`junk_drop_rollout.py list`)

Implementer model: opus

**Files:**
- Create: `scripts/junk_drop_rollout.py`, `scripts/test_junk_drop_rollout.py`
- Modify: `scripts/CLAUDE.md` (new "Junk-title drop rollout" bullet)

**Interfaces:**
- Consumes: an arm from `scripts/replay_holds.py run --all` (Task 4 rows); `emcee status --json`
  output (rows with `slug`, `voiced_by`, `tts_now`); `audio_reuse.plan_reuse(ws, station_dir)`'s
  `station` pairing (source filename → station audio path; it already falls back to
  `reuse-anchor.json`); `junk_titles.plan_drops`/`show_stats`/`held` for needs-LLM rows;
  `llama.replay.code_identity`, `config_fingerprint`; `bulk_apply._station_root_problem`.
- Produces: `junk_drop_rollout.py list --arm A --emcee-status S --out DIR [--config P]`
  (read-only everywhere: library, station, arm). Refuses (exit 2) an arm whose `sha` is not the
  running code's (or `-dirty` on either side), a config-fingerprint mismatch, a missing
  `delivery_path`, an unmounted or empty station root, an `--out` overlapping the library or
  station. Per show:
  - drops: the arm row's `junk_drops` (`drop_source: "replay"`), or, when the row's outcome is
    `needs-llm`/`unreplayable`, `plan_drops` over the CURRENT `show.json` tracks (titles, set
    labels, `overrides.include`; `drop_source: "show.json"`, breaker over show.json durations).
  - station copy present (`<delivery_path>/<slug>/manifest.json`): pair with `plan_reuse`; no pair
    and drops non-empty → `unpaired`; a member when a paired source file is a drop. Not on the
    station: a member when drops is non-empty.
  - writes `DIR/members.json` = `{sha, config_fingerprint, written_at, arm_sha256, rows}`; each row
    `{slug, outcome: "member", briefing, digests, needs_llm, drop_source, station: {state:
    "unvoiced"|"voiced"|"not on station", presenter, backend_now, clips}, drops: [{source_file,
    title, duration_sec, set, after_track, rule, held}], held, pairs: [{station_file,
    station_title, source_file}], other_differences: [str]}`. `pairs` are the station tracks paired
    with a dropped source file. `clips` = `len(dj_audio.set_intros) + (1 if dj_audio.outro else 0)`
    from the station manifest; `presenter` = the status row's `voiced_by`; `backend_now` =
    `tts_now.backend`. `other_differences` compares the paired station tracks other than the drop
    pairs with the predicted post-reprocess tracks (the arm row's `filenames`/`titles`/`sets`/
    `segues`; for needs-LLM rows, show.json minus the drops) as `title <src>: '<a>' -> '<b>'`,
    `set <src>: <a> -> <b>`, `segue <src>: <a> -> <b>`, `added <src> '<title>'`,
    `removed <src> '<title>'`.
  - `DIR/reapply-replayable.json` and `DIR/reapply-needs-llm.json`: predicted-list documents
    (`{sha, config_fingerprint, written_at, rows: [{slug, outcome, briefing, digests}]}`, loadable
    by `reapply.load_list`) splitting members by `needs_llm`; `DIR/unpaired.json`.
  - prints counts: members by station state, voiced by `backend_now`, held, the needs-LLM wave
    size on its own line (`with-gather-llm wave: N`), unpaired.
- [ ] **Step 1: Tests** (tmp library, station and arm; monkeypatch `code_identity`):
  `test_member_by_paired_station_track`; `test_not_on_station_member`; `test_unpaired_is_left_out_and_listed`;
  `test_station_track_not_dropped_is_not_member`; `test_needs_llm_row_uses_show_json`;
  `test_with_gather_llm_shows_are_their_own_wave` (both reapply lists, and the printed line);
  `test_reapply_lists_load_with_reapply_load_list`; `test_voiced_entry_carries_clips_presenter_backend`;
  `test_other_differences_reported`; `test_refuses_stale_arm_and_unmounted_station`;
  `test_list_writes_nothing_outside_out` (library and station trees byte- and mtime-identical).
- [ ] **Step 2–4:** FAIL, implement, PASS (file and suite).
- [ ] **Step 5: Commit** `feat(scripts): junk-title drop rollout membership list`.

---

### Task 14: Marking command (`junk_drop_rollout.py mark`)

Implementer model: opus

**Files:**
- Modify: `scripts/junk_drop_rollout.py`, `scripts/bulk_apply.py` (`_mark_station`, `_mark_one`,
  `mark_apply`, `_STATION_OK`, `_REASON_KINDS`), `packages/llama/src/llama/campaign_gate.py`
  (`require_tools`, `CAMPAIGN_MIN_VERSION`)
- Modify: `scripts/CLAUDE.md`
- Test: `scripts/test_junk_drop_rollout.py`, `scripts/test_bulk_apply_mark.py` (append),
  `packages/llama/tests/test_campaign_gate.py` (append)

**Interfaces:**
- Produces:
  - `bulk_apply.REASON_JUNK = "junk-title drop"` (joins `_REASON_KINDS`);
    `bulk_apply.VOICED_CAMPAIGN_ONLY = "voiced: campaign mark only"` (joins `_STATION_OK`).
  - `mark_apply(..., skip_voiced: bool = False)` threaded to `_mark_station`: with `skip_voiced`,
    the station manifest re-read under the station lock (the existing `read_station_manifest` in
    `_mark_station`) with a non-null `dj_audio` and no mark of THIS batch returns
    `(VOICED_CAMPAIGN_ONLY, None, None)`: no station write, no before copy. Default `False` is
    today's behaviour exactly.
  - `campaign_gate.require_tools(echo, *, pin, minimum: str | None = None)` (None = `CAMPAIGN_MIN_VERSION`);
    `CAMPAIGN_MIN_VERSION = "2.24.0"` (comment: the junk-title drop release; confirm at release);
    `junk_drop_rollout.JUNK_MARK_TOOLS_FLOOR = "2.23.0"` (marking runs BEFORE the release
    binaries are installed, spec Rollout step 3).
  - `junk_drop_rollout.py mark --list DIR/members.json [--apply]`: refuses (exit 2) a list whose
    `sha`/`config_fingerprint` is not the running code's/config's; with `--apply` also requires
    `require_pinned_code(root)` and `require_tools(..., minimum=JUNK_MARK_TOOLS_FLOOR)`, refuses
    `--campaign-dir` (it has none) and an unmounted station. Items:
    `MarkItem(slug, REASON_JUNK, "gather", row["digests"])`; batch id
    `sha256(list bytes)[:16]`; batch dir `<root>/campaign/marking/<id>/` with `inputs.json`
    (`list`, `list_sha256`, `sha`, `station_root`, `created_at`); then
    `mark_apply(..., skip_voiced=True)`. The dry run prints per member the station state it would
    act on (re-read, no lock) and `would station-mark` only for unvoiced copies.
- [ ] **Step 1: Tests:** `test_mark_never_station_marks_a_voiced_copy` (voiced station manifest
  byte- and mtime-identical after `--apply`; campaign mark written; record line
  `voiced: campaign mark only`); `test_mark_station_marks_unvoiced_held_or_not`;
  `test_voiced_check_reads_under_the_lock` (the copy becomes voiced between the dry-run read and
  the apply: not marked); `test_not_on_station_member_gets_campaign_mark_only`;
  `test_bulk_unmark_reverses_a_junk_batch` (unvoiced copy put back, campaign marks removed, the
  voiced row's mark removed, processed shows left and listed); `test_rerun_skips_recorded_items`;
  `test_mark_refuses_stale_list`; `test_skip_voiced_default_is_todays_behaviour` (existing
  `bulk_apply mark` tests stay green and one asserts a voiced copy IS marked without the flag);
  `test_require_tools_minimum`.
- [ ] **Step 2–4:** FAIL, implement, PASS (files and suite).
- [ ] **Step 5: Commit** `feat(scripts): junk-title drop marking batch (never station-marks voiced copies)`.

---

### Task 15: Voiced approval list and pre-replace re-check

Implementer model: opus

**Files:**
- Modify: `scripts/junk_drop_rollout.py`, `scripts/test_junk_drop_rollout.py`, `scripts/CLAUDE.md`

**Interfaces:**
- Produces:
  - `approval --list DIR/members.json --emcee-status S [--backend voxtral|mlx_audio|elevenlabs] [--out F]`
    (read-only): for each member whose LIVE station copy is voiced (re-read now), one block: slug,
    presenter, `backend_now` from the fresh status file, clip count from the live `dj_audio`, the
    drop list (title, `m:ss`, held), `other_differences` from the list, and the library
    `show.json` hold flags now (brief/vet holds from re-processing); a held show is listed under
    `held (not approvable)`. `--out F` writes the approvable slugs one per line. A member voiced
    after the list was built appears (live state wins); one no longer voiced is listed under
    `no longer voiced (unvoiced route)`.
  - `recheck --list DIR/members.json <slug>` (read-only; exit 0 only when it passes): the slug is a
    member; at least one recorded pair has its `station_file` with `station_title` still in the
    live station manifest's tracks AND its `source_file` excluded in the library `show.json` with
    reason `junk title`; the library show is not held; the station copy is voiced. Prints each
    check `ok`/`FAIL` and, on failure, `leave <slug> out of this batch`.
- [ ] **Step 1: Tests:** `test_approval_uses_live_state`; `test_approval_lists_held_apart`;
  `test_approval_writes_approvable_slugs`; `test_recheck_passes`;
  `test_recheck_fails_after_include` (source file now kept); `test_recheck_fails_when_station_track_gone`;
  `test_recheck_fails_on_held`; `test_recheck_reads_without_writing`.
- [ ] **Step 2–4:** FAIL, implement, PASS (file and suite).
- [ ] **Step 5: Commit** `feat(scripts): junk-title drop voiced approval list and re-check`.

---

### Task 16: Final acceptance

Implementer model: opus

**Files:**
- Create: `docs/superpowers/2026-11-14-junk-tag-drop-evidence/acceptance.md`
- Modify: whichever CLAUDE.md a review finds stale (facts only)

- [ ] **Step 1:** If any commit after Task 6 touched `junk_titles.py`, `stages/gather.py` or
  `replay.py`, re-run Task 6 Steps 2–4 (same read-only rules, same output directory with a
  `-final` suffix) and record the deltas against Task 6's numbers.
- [ ] **Step 2:** Run the whole suite (`./.venv/bin/python -m pytest -q`), `cd antenna && npm test`,
  and the Debian-12 script if docker is available. Record counts.
- [ ] **Step 3: Write `acceptance.md`**: one row per spec Acceptance bullet with the evidence:
  library replay counts vs baseline with every difference explained (Task 6 / Step 1); zero
  out-of-vocabulary drops (`vocabulary.txt` empty); the 1979-12-05 case (Task 3 test name); not
  stale (Task 8 test); `encore_after` on a dropped `Crowd` (Task 3 test and Task 6
  `override_keys.tsv`); `dropped_tracks` leaves the equal-copy tests unchanged (Task 9 tests);
  every reader with the field present, absent, null, `[]` (Tasks 9–12 test names per reader); the
  marking command never station-marks a voiced copy (Task 14 test); the `--with-gather-llm` shows
  as their own wave (Task 13 test). Also each Stakes strict surface with the test that guards it.
- [ ] **Step 4: Commit** `docs(junk-tag-drop): acceptance record`.

---

## Appendix A: Operator runbook (NOT executed by this run)

Run on the operator's go, in order. `WT` = the campaign worktree, `H` = `~/.llama-harness/junk-rollout`.
Nothing here is done by an implementer or the orchestrator.

1. **Release.** Tag and build llama, emcee and transmitter at one version (this plan assumes
   `2.24.0`; if not, correct `CAMPAIGN_MIN_VERSION` first). Deploy transmitter on hugo and the
   antenna assets (`npm run deploy:assets -- --dry-run`, then without it; the Worker itself is
   unchanged). Do NOT install the new llama/emcee binaries yet.
2. **Pin.** `git worktree add .claude/worktrees/campaign-v2.24.0 v2.24.0`; give it its own venv;
   `WT/.venv/bin/python WT/scripts/bulk_apply.py pin --tag v2.24.0 --replace`. Stop the
   `run resume --all` loop. From here until step 5 ends: no `emcee run`, no `emcee voice`.
3. **Arm.** `WT/.venv/bin/python WT/scripts/replay_holds.py run --all --out H/arm.json`
   (not `bulk_apply.py arm`: its tool gate would refuse the old installed binaries).
4. **List.** `emcee status --json > H/emcee-status.json`, then
   `WT/.venv/bin/python WT/scripts/junk_drop_rollout.py list --arm H/arm.json --emcee-status H/emcee-status.json --out H/list`.
   Read the counts; take `H/list/unpaired.json` to the operator (left as they are).
5. **Mark.** `... junk_drop_rollout.py mark --list H/list/members.json` (dry run), then `--apply`.
   Exit 0 required; a stop (emcee running, station locked) is re-run after the cause is cleared.
6. **Install** llama and emcee 2.24.0.
7. **Re-process.** Pilot a few shows from `H/list/reapply-replayable.json`
   (`llama reapply --from-list ... --allow-structure-change --stop-at-points <n>`, reading the
   `meter:` lines to size waves), then the rest in waves; then
   `llama reapply --from-list H/list/reapply-needs-llm.json --allow-structure-change --with-gather-llm`
   as its own wave(s), pilot first. Brief/vet holds are in each batch's report.
8. **Unvoiced.** `llama deliver --fixed` (re-delivers and clears each mark).
9. **Voiced, per batch the operator approves before anything is replaced.**
   `emcee status --json > H/status-now.json`;
   `... junk_drop_rollout.py approval --list H/list/members.json --emcee-status H/status-now.json [--backend voxtral] --out H/batch-N.txt`;
   operator approves the batch; then per slug, one at a time:
   `... junk_drop_rollout.py recheck --list H/list/members.json <slug> && llama deliver <slug> --replace-voiced && emcee voice <slug>`.
   A failed re-voice is retried with `emcee voice <slug>` (the show is off air until then).
10. **Held.** `llama triage` over the held members, any voicing. Overrule → the show's normal route
    (unvoiced: `deliver --fixed`; voiced: a step 9 batch). `--include` → no change when no other
    drop remains (unvoiced: `deliver --fixed` clears the mark; voiced: keeps airing); a show still
    a member continues by its normal route. `gratefuldead-1969-03-01` (Voxtral, held) follows this.
11. **Close.** `WT/.venv/bin/python WT/scripts/bulk_apply.py unmark --batch <root>/campaign/marking/<id>`
    (dry run), then `--apply`; it reverses never-processed shows and lists the processed ones.

Notes: `deliver`'s awaiting-fix refusal hint adds `--with-gather-llm` only for the old frozen
needs-LLM list; for this rollout use the list's `needs_llm` field. A selector `deliver` (incl.
`--fixed`) never replaces a voiced destination.
