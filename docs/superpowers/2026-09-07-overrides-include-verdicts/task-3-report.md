# Task 3 report — show the dropped files

**Status:** DONE_WITH_CONCERNS (concerns are notes for Task 4/review, not defects)
**Commit:** `0401dc99da9bf864fa9eb62d6a5cc7ca92bbeeb7`
**Subject:** `feat(show): list junk-filtered files with x-handles and mark re-admitted tracks`
**Branch:** `overrides-include` (main checkout, no worktree). Not pushed.

## Test result

```
./.venv/bin/python -m pytest -q
1945 passed, 7 deselected, 26 warnings in 6.13s
```

Baseline was 1935 passed / 7 deselected; +10 new tests, no test removed.

## Changes, file by file

### `packages/llama/src/llama/cli.py`

1. **New `_excluded_handles(show) -> list[tuple[str, dict]]`**, immediately above
   `_format_tracks`. `[(f"x{i}", e) for i, e in enumerate(show.excluded_files, start=1)]`,
   with the docstring from the brief naming it the single producer Task 4's resolver
   consumes. Nothing else in the tree numbers handles.
2. **`_format_tracks`:**
   - The stale two-line duration comment above `_MARK` replaced with the brief's Step-5
     text (the `?` now *can* co-occur, on a re-admitted file with no metadata length).
   - **Both in-loop comments preserved** (per correction 2): the "duration before filename"
     one and the 14-wide `title_source` one. The brief's replacement body dropped both.
     Added a third short comment explaining why the `+` gets its OWN column rather than
     sharing `_MARK`'s (re-admission and setlist-match are orthogonal).
   - Row format gains `{'+' if t.included else ' '}` between the `.` and `" set "`.
   - `+ = re-admitted by operator (the junk filter had dropped it)` legend, emitted only
     when at least one track carries the mark, after the existing `?`/`-` legends.
   - `excluded (N):` section: handle right-aligned in 3, filename padded to the widest
     name in the set (so the duration column lines up), duration, reasons joined with
     `", "`. Then the `re-admit one with: llama fix <show> --include x1` hint.
   - **`e.get("duration_sec")` and `e.get("reasons", [])`**, never `e[...]`.
3. **`_print_show_entry`:** `recording:` line gains `, N dropped` when `excluded_files` is
   non-empty; `overrides:` line gains `include=[...]` immediately after `exclude=[...]`.
4. **`_print_show_json`:** `"include": ov.include` added to `data["overrides"]`;
   `data["excluded"] = s.excluded_files if s is not None else None` added inside the
   `if show_tracks:` block (so it appears only alongside `tracks`, matching the existing
   `tracks` gating).

### `packages/llama/tests/test_cli.py`

- **`_MARK_COL` 17 -> 18**, and its derivation comment rewritten.
  New derivation, verified against real `_format_tracks` output rather than arithmetic
  alone: 2 leading spaces + 2-digit index + `.` (1) + the re-admission `+` column (1) +
  `" set "` (5) + the 6-wide `set` field + 1 space = **18**. Empirically:
  `'   3.+ set 1      - C ...'` — index 18 holds the `-`/`?`/`" "` mark.
  Note the brief's own arithmetic labelled the old literal `". set "` as 6 characters;
  after the change the literal splits into `.` + the marker + `" set "` (5), so the sum is
  1+1+5 where it used to be 6. Same total shift of exactly one.

### `packages/llama/tests/test_show_cmd.py`

- `read_model` added to the existing `from llama.workspace import ...` line (correction 3).
- `test_tracks_flag_prints_every_title_source_in_full` passes a bare
  `SimpleNamespace(tracks=tracks)`; `_format_tracks` now also reads `excluded_files`, so
  the namespace gained `excluded_files=[]`. **Chosen over a defensive `getattr` in
  `cli.py`**: every real caller passes a `Show`, and `_excluded_handles` is about to be a
  public-ish seam for Task 4 — a silent `getattr` default there would hide a genuinely
  wrong argument.
- `test_json_schema_spot_checks` asserts `data["overrides"] ==` an exact dict; `"include": []`
  added. (This is the assertion that pins the JSON shape — see the mutation table.)
- Ten new tests appended under a `--- overrides.include ... ---` banner, plus the
  `_show_with_excluded` fixture.

## Departures from the brief, and why

### 1. Two of the brief's tests were passing/failing on the pytest tmp_path, not the behaviour

**This is the correction-4 case, and it hit exactly where the plan author predicted.**

`llama show` prints a `path:` line carrying the workspace directory, which under pytest is
`.../pytest-NNNN/test_no_dropped_clause_when_no0/...` — **the test's own name**. So the
brief's

```python
assert "dropped" not in r.output
```

is not a statement about the `dropped` clause at all; it is matching the substring
`dropped` inside `test_no_dropped_clause_when_nothing_was_dropped`'s temp directory. As
written it FAILED against correct code. The dangerous form of the same bug is the one a
rename would produce: name the test anything without the word `dropped` and the assertion
becomes vacuous while still looking like a pin.

The same defect existed in my own first draft of
`test_no_excluded_section_when_nothing_was_filtered` (`"excluded" not in r.output`, matched
by `test_no_excluded_section_when_0`) and, latently, in
`test_no_re_admitted_legend_...` (which survived only because the directory name uses
`re_admitted` with an underscore while the legend uses a hyphen — pure luck).

**Rewritten.** Every negative is now scoped to a line:

- `test_no_dropped_clause_when_nothing_was_dropped` pins the WHOLE recording line:
  `assert line == "recording: gd73  (1 tracks)"`. That both excludes the path line and
  catches the unconditional-clause mutation, which renders `", 0 dropped"`.
- `test_no_excluded_section_when_nothing_was_filtered`:
  `assert not any(ln.startswith("excluded (") ...)`.
- `test_no_re_admitted_legend_...`: `assert not any(ln.startswith("  + = ") ...)`.

Each carries a comment recording why the whole-output form is wrong here.

### 2. `test_tracks_listing_marks_a_re_admitted_track` — the `"2.+" not in dew` half rewritten

The brief flagged this pair as suspect. It is in fact *satisfiable* against the two obvious
mutations (drop the marker; mark every row), so it is not vacuous — but it is weak: it says
nothing about what an unmarked row carries in that column, so a marker rendered as a
zero-width string (the exact mutation `test_format_tracks_distinguishes_...` was written to
catch, per its docstring) would leave both halves true while the table misaligns.

Rewritten as whole-prefix pins:

```python
assert intro.startswith("   1.+ set "), intro
assert dew.startswith("   2.  set "), dew
```

This asserts the marker occupies a fixed one-character column and that an unmarked row
carries a **space** there.

### 3. `test_tracks_listing_shows_the_excluded_section` strengthened

The brief checked scattered substrings (`"x1" in r.output and "spam.mp3" in r.output`),
which cannot tell whether `x1` is on the same row as `spam.mp3` — a handle/entry
mis-pairing (precisely the failure mode `_excluded_handles`-as-single-producer exists to
prevent) would pass. Rewritten to pin whole rows by `split()`:

```python
assert spam.split() == ["x1", "spam.mp3", "1:12", "filename", "convention", "mismatch"]
assert tuning.split() == ["x2", "tuning.mp3", "0:12", "implausibly", "short"]
assert spam.index("1:12") == tuning.index("0:12")   # filename column really pads
assert "llama fix <show> --include x1" in r.output   # the hint, unpinned in the brief
```

### 4. Four tests added beyond the brief's six

- `test_excluded_section_survives_a_show_json_written_before_duration_sec` — the
  `e.get` requirement was stated in my instructions but **pinned by nothing** in the
  brief. Renders an entry with no `duration_sec` key and asserts the row reads
  `["x1", "old.mp3", "?", "spam"]`.
- `test_no_excluded_section_when_nothing_was_filtered` — the `if handles:` guard.
- `test_no_re_admitted_legend_when_no_track_was_re_admitted` — the legend's guard.
  (The brief pinned the legend's presence but not its absence.)
- `test_json_omits_excluded_without_the_tracks_flag` — `data["excluded"]` sits inside
  `if show_tracks:`; nothing in the brief pinned that placement.

`test_overrides_line_and_json_carry_include` also gained
`assert data["tracks"][1]["included"] is False`, so the JSON check distinguishes the two
tracks rather than only confirming a `True` somewhere.

## Mutation observations

14 mutants, each applied to `cli.py` alone with a **named predicted failing test** before
running, then reverted and the file byte-compared against the original. Run over
`test_show_cmd.py` + `test_cli.py`. **All 14 CAUGHT, every one by its predicted test.**

| # | Mutation | Predicted test | Result |
|---|---|---|---|
| 1 | `dropped` clause emitted unconditionally | `test_no_dropped_clause_when_nothing_was_dropped` | CAUGHT (sole failure) |
| 2 | `+` marker never emitted (`.  set`, width preserved) | `test_tracks_listing_marks_a_re_admitted_track` | CAUGHT (sole failure) |
| 3 | `+` marker on every row | `test_tracks_listing_marks_a_re_admitted_track` | CAUGHT (sole failure) |
| 4 | `+` legend emitted unconditionally | `test_no_re_admitted_legend_when_no_track_was_re_admitted` | CAUGHT (sole failure) |
| 5 | `e['duration_sec']` instead of `e.get(...)` | `test_excluded_section_survives_a_show_json_written_before_duration_sec` | CAUGHT (sole failure) |
| 6 | handles `enumerate(..., start=0)` | `test_excluded_handles_number_from_one_in_show_json_order` | CAUGHT (+2 collateral) |
| 7 | `excluded (N):` header emitted even when empty (crash-free variant) | `test_no_excluded_section_when_nothing_was_filtered` | CAUGHT (sole failure) |
| 8 | `data["excluded"]` hoisted out of `if show_tracks:` | `test_json_omits_excluded_without_the_tracks_flag` | CAUGHT (sole failure) |
| 9 | `include=` line dropped from `overrides:` | `test_overrides_line_and_json_carry_include` | CAUGHT (sole failure) |
| 10 | `"include": ov.include` dropped from `--json` | `test_json_schema_spot_checks` | CAUGHT (+1 collateral) |
| 11 | re-admit hint line dropped | `test_tracks_listing_shows_the_excluded_section` | CAUGHT (sole failure) |
| 12 | `+` column reverted to the pre-feature layout | `test_format_tracks_distinguishes_matched_unmatched_and_unknown` | CAUGHT (+3) |
| 13 | excluded filename column unpadded | `test_tracks_listing_shows_the_excluded_section` | CAUGHT (sole failure) |
| 14 | `if handles:` -> `if True:` (first, crashing variant) | `test_no_excluded_section_when_nothing_was_filtered` | CAUGHT, but see note |

**Note on 14 vs 7.** My first `if handles: -> if True:` mutant made `max()` run over an
empty sequence, so the predicted test failed by `ValueError`, not by seeing an
`excluded (0):` line — a caught-for-the-wrong-reason result exactly of the kind
`mutation-scoring-needs-a-prediction` warns about. I re-ran it as mutant 7, which emits the
header *before* the guard and crashes nowhere; it is still caught, by the predicted test
alone, so the guard is genuinely pinned.

**Note on 12.** This is the `_MARK_COL` check. Reverting the row format to the pre-feature
string (rather than merely blanking the marker, as in mutant 2) shifts every row back to
column 17 and fails three `test_cli.py` fixed-offset tests plus the marker test — i.e.
`_MARK_COL = 18` is load-bearing, not a number I merely made consistent.

**Tree restored** after every mutant (`CLI.read_text() == orig` asserted in the harness);
`git status --porcelain` was empty of unintended changes before the commit, and is empty now.

## Constraints honoured

- `junk.py` constants untouched (file not modified at all).
- No fields added to `ManifestTrack` (`models.py` not modified).
- No `extra="forbid"` added anywhere.
- `_excluded_handles` is the only producer of `x`-handle numbering in the tree
  (`grep -rn "x{i}\|x%d" packages/` finds nothing else).
- `llama show` remains read-only — the change is print-only; no write path touched.
- Offline/deterministic; no network in any new test.
- One commit, conventional subject, both trailers present.

## Concerns

1. **The hint advertises a flag that does not exist yet.** `--tracks` now prints
   `re-admit one with: llama fix <show> --include x1`, but `fix --include` lands in Task 4.
   Between this commit and Task 4 the branch tells an operator to run a command that exits
   with a usage error. Self-resolving within the branch; flagged only so it is not merged
   to `main` alone.
2. **`Track.included` means "the operator named this file", not "the junk filter had
   dropped it"** (Task 1's own docstring says so), yet the legend I was given to render
   reads `+ = re-admitted by operator (the junk filter had dropped it)`. If an operator
   lists a filename in `overrides.include` that the filter would have kept anyway, the
   parenthetical is a false claim about that row. The text is the brief's and the spec's,
   and the divergence is narrow, so I shipped it as specified — but a reviewer may want
   the parenthetical dropped or softened to "(re-admitted past the junk filter)".
3. **`data["excluded"]` is gated on `--tracks`**, mirroring `data["tracks"]`. The brief
   specifies this and it is symmetric, but a JSON consumer wanting the dropped list must
   now pass a flag named for something else. Noting it as a deliberate shape decision,
   pinned by `test_json_omits_excluded_without_the_tracks_flag` so Task 4 cannot change it
   silently.
4. **The interactive `[e]xclude` picker now shows the excluded section too**, because it
   shares `_format_tracks`. This is what spec section 4 asks for ("The picker gains the
   excluded *listing* as context"), and its prompt still takes play-order track numbers
   only — but it means the picker displays `x`-handles it will not accept as input. No test
   covers the picker's new rendering; I left it alone as out of scope.
5. **No linter was run** — `ruff` is not installed in `.venv` and the repo carries no lint
   config (`pyproject.toml`, `setup.cfg`, `tox.ini`, `.flake8` all have no
   `line-length`/`flake8`/`ruff` key). I checked manually that no line I added exceeds 101
   characters, the widest pre-existing line in `cli.py`'s neighbourhood.

---

# Fix round 1

**Status:** DONE — all five findings applied, nothing else touched.
**Commit:** `eb1e278dbe6e528b9d8dcc510c3f2dd1dcfc1bc7`
**Subject:** `fix(show): correct the re-admission legend and move the hint to the reader path`
**Branch:** `overrides-include`. Not pushed. Working tree clean.

## Test results

```
./.venv/bin/python -m pytest packages/llama/tests/test_show_cmd.py packages/llama/tests/test_cli.py packages/llama/tests/test_triage.py -q
101 passed in 1.10s

./.venv/bin/python -m pytest -q
1947 passed, 7 deselected, 26 warnings in 6.12s
```

1945 -> 1947: two new tests (the empty-`reasons` row, the picker listing). No test removed.

## 1 — Important: the `+` legend's false parenthetical

**New legend text, verbatim:**

```
  + = ruled in by the operator (overrides.include)
```

Two leading spaces and the `+ = ` prefix preserved, so it still matches the shape of the
sibling `? = no setlist match` / `- = not measured` lines and the
`ln.startswith("  + = ")` negative in `test_no_re_admitted_legend_...`. The claim is now
exactly what `Track.included` encodes — the operator named this file in `overrides.include`
— with no assertion about what the junk filter did. A four-line comment above the
`lines.append` records why the old parenthetical was wrong, so it is not restored as a
"clearer" wording later.

`test_tracks_listing_marks_a_re_admitted_track`'s assertion tightened from a substring
(`"+ = re-admitted by operator" in r.output`) to exact line membership
(`... in r.output.splitlines()`), which is what makes the wording itself pinned rather than
just its prefix.

## 2 — Minor: the re-admit hint moves to `_print_show_entry`

Removed from `_format_tracks`; emitted in `_print_show_entry`'s `if show_tracks:` block
after the `_format_tracks` lines, gated on `_excluded_handles(s)` being non-empty:

```python
        handles = _excluded_handles(s)
        if handles:
            typer.echo(f"  re-admit one with: llama fix {entry.slug} "
                       f"--include {handles[0][0]}")
```

Renders as `  re-admit one with: llama fix gratefuldead-1973-06-10 --include x1`.

Three notes:

- **The handle still comes from `_excluded_handles`**, not a literal `"x1"`, so the
  single-producer constraint holds at the new site too.
- **The picker loses the hint for free.** `_interactive_resolve` calls
  `_print_show_entry(entry)` with `show_tracks` defaulting to `False` (cli.py:1410), so the
  hint is unreachable from the walkthrough by construction rather than by a second guard.
  Verified by the new picker test, not by reading.
- A comment at the new site records both reasons (no slug on a `Show`; the helper is the
  picker's renderer) so the hint is not "tidied" back into the helper.

`test_tracks_listing_shows_the_excluded_section`'s hint assertion updated to the new home
and pinned as an exact line carrying the real slug.

## 3 — Minor: trailing whitespace on a reason-less excluded row

The row is now built and `.rstrip()`ed. Rendered sample (second entry has no `reasons`
key at all):

```
excluded (2):
   x1  spam.mp3         1:12  filename convention mismatch
   x2  no-reason.mp3    0:12
```

New test `test_excluded_row_with_no_reasons_has_no_trailing_whitespace` covers **both**
reachable shapes — key absent, and key present but `[]` — and asserts `ln == ln.rstrip()`
plus `ln.endswith("1:12")`, so it fails whether the whitespace survives or the duration
column is dropped instead.

## 4 — Minor: the picker's excluded listing is now pinned

New test in `packages/llama/tests/test_triage.py`, placed after the existing `[e]xclude`
tests: `test_exclude_picker_lists_the_dropped_files_but_not_the_re_admit_hint`.

Drives the real walkthrough (`cli_invoke(cfg, "triage", input="e\n\n")`, i.e. enter the
picker then pick nothing) against a held show whose `show.json` carries one excluded file.
Asserts **both halves**, as instructed:

- listing present: `"excluded (1):"` as an exact line, and the entry row parsed with
  `.split()` to `["x1", "spam.mp3", "1:12", "filename", "convention", "mismatch"]` — so a
  handle/entry mis-pairing cannot pass;
- hint absent: no line contains `--include`, and no line contains `re-admit one with`.

Also asserts `calls == []` so the test is exercising the picker's *rendering* and not
accidentally triggering a redo. Imports added to the file: `Show` (from `llama.models`)
and `read_model` (from `llama.workspace`).

## 5 — Minor: the last whole-output negative

`test_dropped_count_shows_without_the_tracks_flag`'s `"excluded (2):" not in r.output`
became `assert not any(ln.startswith("excluded (") for ln in r.output.splitlines())`, with
a comment naming the reason.

**Correction, found by actually running the sweep rather than asserting it.** My first
draft of this section claimed `grep -n "not in r.output"` returned nothing. It did not.
One of MY OWN negatives had survived — `test_no_excluded_section_when_nothing_was_filtered`
line 377, `assert "--include" not in r.output`, sitting three lines under the comment
explaining why whole-output negatives are wrong here. It was safe only because a pytest
tmp_path cannot contain `--include`, which is exactly the "safe today by luck of the
directory name" the finding objects to. Rewritten to
`assert not any("--include" in ln for ln in r.output.splitlines())`.

Eight further hits remain in the file at lines 48, 61, 69, 70, 81, 82, 261 and 274. All
eight PRE-DATE this task (archive-URL, considered-block and old-edit-flag assertions) and
none is mine, so I left them under the "do not change anything else" instruction. Flagging
them for whoever owns the standing rule: they are the same shape, and at least
`assert "archive.org" not in r.output` is the kind that a rename could quietly weaken.

The two new tests in this round were written line-scoped from the start.

## Mutation observations

Seven mutants, each with a **named predicted failing test** fixed before the run, applied
to `cli.py` alone, reverted immediately, and the file verified by **sha256** (not just a
string compare) against its pre-mutation digest. Run over
`test_show_cmd.py` + `test_cli.py` + `test_triage.py`.

`cli.py` sha256[:12] `18073023966e` before and after — **RESTORED**.

**All 7 CAUGHT, every one by its predicted test, every one as the SOLE failure.**

| # | Mutation | Predicted test | Result |
|---|---|---|---|
| 1 | legend reverted to the false parenthetical | `test_tracks_listing_marks_a_re_admitted_track` | CAUGHT, sole |
| 2 | hint put back inside the shared `_format_tracks` | `test_exclude_picker_lists_the_dropped_files_but_not_the_re_admit_hint` | CAUGHT, sole |
| 3 | hint dropped from `_print_show_entry` | `test_tracks_listing_shows_the_excluded_section` | CAUGHT, sole |
| 4 | hint emitted even when nothing was dropped | `test_no_excluded_section_when_nothing_was_filtered` | CAUGHT, sole |
| 5 | hint prints a literal `<show>` instead of `entry.slug` | `test_tracks_listing_shows_the_excluded_section` | CAUGHT, sole |
| 6 | `.rstrip()` dropped from the excluded row | `test_excluded_row_with_no_reasons_has_no_trailing_whitespace` | CAUGHT, sole |
| 7 | picker stops rendering the listing (simulates a future renderer split) | `test_exclude_picker_lists_the_dropped_files_but_not_the_re_admit_hint` | CAUGHT, sole |

Mutant 2 is the one that proves finding 2 is now a *pin* and not merely a relocation: it
puts the hint back in the shared helper, which is exactly the regression a later
refactor would make, and the picker test catches it. Mutant 7 is its complement — it
removes the listing from the picker while leaving `show --tracks` intact, the regression
finding 4 exists to prevent; before this round nothing failed on it.

## Scope discipline

The three parked reviewer minors were **not** acted on: the excluded rows' filename-first
column order and row width (spec section 4 depicts that order; referred to final review),
the absent `handle` key on `--json` excluded entries (plan and spec both specify
`data["excluded"] = s.excluded_files`), and the hint naming `fix --include` before Task 4
lands (recorded as a merge-order constraint). Nothing outside the five findings was
changed; `git diff` for this commit touches only the legend line, the excluded-row
`lines.append`, the hint's removal and re-siting, and the four test edits described above.

## Concerns

None outstanding. Concern 2 from the first report (the false parenthetical) is resolved by
finding 1; concern 4 (the picker's unpinned rendering) by finding 4. Concerns 1 and 3 from
the first report remain open by the orchestrator's explicit ruling, and concern 5 (no
linter in the venv, no lint config in the repo) still stands — I again checked by hand that
no added line exceeds 101 characters.

---

# Fix round 2

**Status:** DONE — the single ruled change applied, nothing else touched.
**Commit:** `fd7e60d593af506b5fb52499cc85b8692ae53041`
**Subject:** `refactor(show): drop the excluded row's filename padding and move it last`
**Branch:** `overrides-include`. Not pushed. Working tree clean.

## Test results

```
./.venv/bin/python -m pytest packages/llama/tests/test_show_cmd.py packages/llama/tests/test_cli.py packages/llama/tests/test_triage.py -q
102 passed in 1.07s

./.venv/bin/python -m pytest -q
1948 passed, 7 deselected, 26 warnings in 6.08s
```

1947 -> 1948: one new test (`test_excluded_rows_align_regardless_of_filename_length`).
No test deleted — the retired padding assertion was replaced in place.

## The change

`width = max(len(e["filename"]) for _, e in handles)` is gone entirely. The row is now:

```python
            lines.append((f"  {handle:>3s}  {_fmt_dur(e.get('duration_sec')):>6s}  "
                          f"{e['filename']}  "
                          f"{', '.join(e.get('reasons', []))}").rstrip())
```

`e.get('duration_sec')`, `e.get('reasons', [])` and `.rstrip()` all retained.

Rendered, at realistic LMA lengths (the same four entries, old shape vs new):

```
excluded (4):
   x1    0:37  dm1969-08-08t13.mp3  implausibly short
   x2    1:12  FOLLOW-ME @BYPIKENO.mp3  filename convention mismatch
   x3    4:02  gd73-06-10.sbd.hollister.174.sbeok.shnf.t07.mp3  duplicate-listing
   x4       ?  no-reason.mp3
```

53 / 68 / 81 / 28 characters. Under the padded shape every one of those rows was the
width of the longest name plus its own reasons — which is where the reviewer's 121
came from.

A comment at the row records the author's points 1 and 3 as instructed (the track-row
convention directly above, and the never-truncate rule with its reason: `--include` takes
the filename verbatim). Point 2 (the 121-character measurement) is recorded too, since it
is the measured fact that a later reader would otherwise re-litigate. This is the second
comment on this branch preserving a measured rendering decision — the first was the
"duration before filename" one I was told to keep in round 1, and it is now the precedent
this change cites.

## Tests updated

I swept for affected assertions rather than working from the supplied list, which found
**two sites the list did not name**:

| Site | Change |
|---|---|
| `test_show_cmd.py` `test_tracks_listing_shows_the_excluded_section` | both `split()` equalities reordered; padding assertion replaced (below) |
| `test_show_cmd.py` `test_excluded_section_survives_a_show_json_written_before_duration_sec` | expected row -> `["x1", "?", "old.mp3", "spam"]` |
| **`test_show_cmd.py` `test_excluded_row_with_no_reasons_has_no_trailing_whitespace`** | **not in the list.** It asserted `ln.endswith("1:12")`; with the filename last, a reason-less row now ends at the *filename*. Now asserts `endswith("no-reason.mp3")` / `endswith("empty.mp3")` |
| **`test_triage.py` `test_exclude_picker_lists_the_dropped_files_but_not_the_re_admit_hint`** | **not in the list.** Its parsed-row equality carried the old field order; reordered |

**The replacement for the padding assertion.** `spam.index("1:12") == tuning.index("0:12")`
became:

```python
    assert spam.index("1:12") + 4 == tuning.index("0:12") + 4 == 13
    assert spam.index("spam.mp3") == tuning.index("tuning.mp3") == 15
```

plus a dedicated `test_excluded_rows_align_regardless_of_filename_length` at the extremes
(`a.mp3`, 5 chars, against a 47-character `gd73-06-10.sbd.hollister.174.sbeok.shnf.t07.mp3`).

Two things I got wrong on the first attempt and fixed by running rather than reasoning:

- **I asserted the duration's START column (`== 7`). It is 9.** The field is right-aligned
  in 6, so what is fixed is where it ENDS, not where it begins. Pinned as
  `index(...) + len(...) == 13`.
- **I gave both rows an equal-width duration**, which makes start and end columns coincide
  and would let a mutant that drops `>6` pass. The test now uses `0:37` against `62:02`
  (4 vs 5 characters) and additionally asserts the two START columns DIFFER — so
  right-alignment is pinned as right-alignment, not as accidental equality.

## Mutation observations

Six mutants, each with a named predicted failing test fixed before the run, `cli.py` only,
reverted and verified by sha256. Run over `test_show_cmd.py` + `test_cli.py` +
`test_triage.py`. `cli.py` sha256[:12] `ffc9dfec8470` before and after — **RESTORED**.

| # | Mutation | Predicted test | Result |
|---|---|---|---|
| 1 | duration loses its `>6` right-alignment (**replaces retired mutant 13**) | `test_excluded_rows_align_regardless_of_filename_length` | CAUGHT |
| 2 | fields reordered back to filename-before-duration | `test_tracks_listing_shows_the_excluded_section` | CAUGHT |
| 3 | filename padding reinstated | `test_excluded_rows_align_regardless_of_filename_length` | **MISSED, then CAUGHT** — see below |
| 4 | filename truncated to 20 (what the comment forbids) | `test_excluded_rows_align_regardless_of_filename_length` | CAUGHT, sole |
| 5 | handle loses its `>3`, shifting every later column | `test_excluded_rows_align_regardless_of_filename_length` | CAUGHT |
| 6 | `.rstrip()` dropped (load-bearing in the new position too) | `test_excluded_row_with_no_reasons_has_no_trailing_whitespace` | CAUGHT, sole |

Mutant 1 is the named replacement for retired mutant 13 ("excluded filename column
unpadded"), which is now the shipped behaviour. It attacks the invariant the new shape
introduces — fixed-width fields left of the filename — and is caught by the new test.

### Mutant 3 MISSED first, and the test was at fault

My `assert len(short_row) < len(long_row)` was supposed to pin unpadded-ness. It does not:
**with the padding reinstated it stays true**, because the long row's longer *reasons* keep
it longer either way. The assertion was measuring the reasons, not the padding, and I would
have shipped it believing otherwise had I not named the predicted test and run the mutant.

Replaced with two assertions that do bite:

```python
    assert len(short_row) == 15 + len("a.mp3") + 2 + len("spam")
    assert short_row.index("spam") != long_row.index("duplicate-listing")
```

The exact length pins "the row is as long as its own content needs"; the second pins the
author's point 4 — the reasons column is deliberately ragged, not columnar. Mutant 3 was
re-run against the strengthened test and is now CAUGHT as the sole failure, with the sha
restored. The comment at the assertion records the measurement so the weaker form is not
restored later.

This is the third time on this branch that a green-looking assertion turned out to be
pinning something other than what it named, and the second where the mutation prediction
is what exposed it.

## Scope

Nothing outside the row shape changed. The track row, the round-1 legend wording and the
hint's new home in `_print_show_entry` are untouched — confirmed by reading
`git show --stat` and the diff: `cli.py` changes are confined to the `if handles:` block.

## Concerns

None new. The first report's concerns 1 and 3 remain open by the orchestrator's ruling
(hint naming `fix --include` before Task 4; no `handle` key on `--json` excluded entries),
and the no-linter note still applies — checked by hand that no added line exceeds 101
characters. The eight pre-existing whole-output negatives in `test_show_cmd.py` (lines 48,
61, 69, 70, 81, 82, 261, 274) remain flagged-not-fixed from round 1, as none is mine.
