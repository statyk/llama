# Task 2 report: `run_gather` honours `overrides.include`

## Status
DONE

## Commit
`10d3202` — `feat(gather): re-admit files named in overrides.include`
(branch `overrides-include`, main checkout, not a worktree)

## Files changed

- `packages/llama/src/llama/stages/gather.py`
  - Hoisted `overrides = read_overrides(show_ws)` above the `filter_files`
    call (deleted the old duplicate that used to sit just above the
    `if overrides.exclude:` block).
  - `filter_files(...)` now passes `readmit=frozenset(overrides.include)`.
  - Added a warning loop for any `overrides.include` entry that matched no
    file in `kept`: `log.warning("overrides.include entry %r matched no
    file", missing)` — mirrors the existing `overrides.exclude` warning.
  - The `overrides.exclude` block's excluded-entry dicts now also carry
    `"duration_sec": length_seconds(f.get("length"))`, matching the shape
    `filter_files` now produces for its own excluded entries. `length_seconds`
    was already imported (`gather.py:26`); no new import added.
  - Immediately before the `show = Show(...)` construction, added the stamp:
    `if overrides.include: forced = set(overrides.include); for t in tracks:
    t.included = t.filename in forced`.

- `packages/llama/tests/test_stage_gather.py`
  - Appended the four tests from the brief's Step 1 verbatim:
    `test_gather_readmits_an_operator_included_file`,
    `test_gather_leaves_ordinary_tracks_unmarked`,
    `test_exclude_wins_when_a_file_is_in_both_override_lists`,
    `test_gather_warns_when_an_include_entry_matches_no_file` — with one
    fix to the last one's assertion (see Deviations below).
  - Added a fifth test per your ruling,
    `test_operator_excluded_entry_carries_duration_sec`, using
    `gd73-06-10d1t01.mp3` (a file the junk filter ordinarily keeps) excluded
    via `overrides.exclude`, asserting its `show.excluded_files` entry
    carries a `float` `duration_sec` — this exercises the
    `operator-excluded` code path specifically, not junk filtering (the
    fixture's actual junk file, `FOLLOW-ME @BYPIKENO.mp3`, never reaches
    `kept` under normal filtering, so it can't be used to test this branch).

## Test commands and output tails

Step 2 (verify the brief's 4 tests fail pre-implementation):
```
./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k "readmit or included or both_override or include_entry or duration_sec"
```
Result: `4 failed, 93 deselected` (the 5th of my own tests was included in
the `-k` filter via `duration_sec` and also failed, as expected, before the
implementation — confirming it too was a real red test, not accidentally
passing).

Step 5 (after implementation, gather test file only):
```
./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q
```
Result: `97 passed in 0.41s`

Step 6 (whole suite):
```
./.venv/bin/python -m pytest -q
```
Result:
```
1934 passed, 7 deselected, 26 warnings in 5.96s
```
(baseline was 1929 passed, 7 deselected; +5 new tests, all passing; the 26
warnings are pre-existing `os.fork()` DeprecationWarnings in concurrency
tests, unrelated to this change).

## Deviation from the brief, and why

The brief's Step 1 literal test `test_gather_warns_when_an_include_entry_matches_no_file`
asserts:
```python
assert any("not-on-this-tape.mp3" in r.message % r.args if r.args else
           "not-on-this-tape.mp3" in r.message for r in caplog.records)
```
This is buggy against pytest's actual `caplog` behavior, independent of my
implementation: `caplog`'s handler formats every record on capture
(`logging.Formatter.format` sets `record.message` to the already-%-substituted
string), so for any record that carries `args` — which is exactly the shape
of both the brief's own `log.warning("overrides.include entry %r matched no
file", missing)` call and the pre-existing `overrides.exclude` warning it
mirrors — `r.message % r.args` re-applies `%` formatting to a string that no
longer has `%` placeholders, raising `TypeError: not all arguments converted
during string formatting`, not returning `False`.

I verified this in isolation with a standalone caplog probe script (not
committed) before touching the test, confirming `r.message` is always
already the fully-rendered string regardless of `r.args`. I fixed the
assertion to:
```python
assert any("not-on-this-tape.mp3" in r.message for r in caplog.records)
```
which is the one code path of the original ternary that is actually correct
(the `if r.args else` branch), and is the behavior the test's own docstring-
free intent clearly wants: "was a warning naming the missing filename
logged." No other line of the test, and no implementation code, was
touched to work around this — the warning call in `gather.py` is exactly as
the brief specifies (`log.warning("overrides.include entry %r matched no
file", missing)`).

I judged this a test-only bug rather than something to escalate: it would
have failed identically no matter how compliant an implementation was
(any `%`-style log call with args trips it), it's isolated to one
assertion's dead branch, and fixing it doesn't touch any of the
brief's specified interfaces, values, or precedence rules.

## Concerns

None outstanding. Precedence (`exclude` wins over `include` when a filename
is in both lists) is pinned by test as instructed. No new imports, no
`ManifestTrack` field additions, no `extra="forbid"` added anywhere, and the
three junk-filter constants were not touched.

## Fix round 1

Status: DONE. Commit `2b6ccef` — `fix(gather): overrides.include review round 1 -- mutation-proof, doc, and warning gaps`.

### Item 1 — mutation-blind test rebuilt (Important)

`test_gather_leaves_ordinary_tracks_unmarked` wrote no `overrides.json`, so
`overrides.include` was empty, the stamp block at `gather.py` (`if
overrides.include: ...`) never executed, and the assertion
(`all(t.included is False for t in show.tracks)`) was satisfied by
`Track.included`'s `= False` default alone — true regardless of whether the
stamp block existed.

Rebuilt: the test now writes `Overrides(include=["FOLLOW-ME @BYPIKENO.mp3"])`
so the stamp block genuinely runs, and asserts every track OTHER than the
re-admitted one is `included is False`.

**Mutation observations, both performed on a temporary in-place edit and
reverted (no mutation left in the tree — restored from a full-file backup
before committing; `git diff` after restoring showed only the intended item
2 + item 4 changes):**

- Mutant: `t.included = t.filename in forced` → `t.included = True`
  (unconditional, inside the same `if overrides.include:` guard).
- Before rebuilding the test: PASSED against this mutant (confirmed the bug
  report's claim).
- After rebuilding the test: **FAILED** against this mutant —
  `assert all(t.included is False for t in others)` → `assert False`,
  because the six ordinary tracks all came back `included=True`.
- Restored the original stamp, reran: **PASSED** (`1 passed in 0.31s`,
  logged in `t2-impl.log`).

### Item 2 — recording-level side effect of re-admission (Important)

**Reachability finding: reachable through `run_gather`'s real inputs**, no
invented pure-function test needed. Used the existing
`_with_tagged_lossless` fixture helper (already in `test_stage_gather.py`,
built for the analogous exclusion-side recovery tests) plus
`overrides.include=["FOLLOW-ME @BYPIKENO.mp3"]`.

Mechanism confirmed by direct interactive run before writing the test: the
gd73 fixture's `FOLLOW-ME @BYPIKENO.mp3` (the junk file) has **no Shorten
counterpart** in the fixture data. Without re-admission (already pinned by
`test_gather_recovers_titles_from_the_lossless_sibling`), the 6 ordinary
mp3 tracks biject exactly against 6 tagged Shorten entries and all recover
`title_source="sibling-format"`. With `FOLLOW-ME` re-admitted, `kept` rises
to 7 while the Shorten side stays at 6; `sibling_format_titles`'s exact
length-bijection check declines, `format_titles` comes back `None` for the
**whole tape**, and all 7 tracks (not just the orphan) fall through to
`title_source="unresolved"`. This is the opposite-direction flip from the
one the bug report led with (turning recovery OFF via a broken bijection,
rather than turning it ON via a lowered title fraction) — both directions
are named in the extended comment, and this is the one that was concretely
reachable with the existing fixture without fabricating new file data.

Changes:
- Extended the comment above `_recover_format_titles` in `gather.py` to
  record the asymmetry: exclusion is kept out of the computation entirely
  (unchanged guarantee), re-admission is deliberately inside it (spec
  section 2), and one re-admitted file can flip a recording-level gate
  (title-fraction gate or the sibling bijection) for the whole tape, not
  just itself.
- Added `test_readmitting_a_lossless_orphan_suppresses_sibling_format_recovery`
  in `test_stage_gather.py`, placed beside the existing recovery tests
  (after `test_gather_recovery_survives_an_operator_exclusion`).

### Item 3 — `Track.included` comment (Minor)

Corrected in `models.py`: the comment previously said "True when
overrides.include re-admitted this file past the junk filter", which is
false whenever an include entry names a file the filter never dropped in
the first place — the code stamps `filename in overrides.include`
unconditionally. New comment states what is actually recorded (the operator
named this file in `overrides.include`) and notes `filter_files`' return
shape doesn't expose which re-admitted names were actually junk. Code
itself is unchanged — spec section 1 specifies exactly this stamp.

### Item 4 — missing both-lists warning (Minor)

Added a warning in the `overrides.exclude` block: for every name in
`set(overrides.include) & drop`, logs `"overrides: %r is in both include
and exclude; exclude wins"`. Placed in the exclude block (not the include
block) because the include block's no-match warning is computed against
`kept`, which by that point already contains the re-admitted file — it
can't see the ambiguity, only the exclude block (which runs after and has
both override lists in scope) can.

Extended `test_exclude_wins_when_a_file_is_in_both_override_lists` (added
`caplog` fixture) to assert the warning fires, containing both the filename
and "exclude wins".

### Test commands and output tails

```
./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py::test_gather_leaves_ordinary_tracks_unmarked -q
```
Pre-fix (before rebuild): `1 passed` (vacuously, per item 1 finding).
Post-rebuild, mutant applied: `1 failed` (`assert False`).
Post-rebuild, mutant reverted: `1 passed in 0.31s`.

```
./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py packages/llama/tests/test_models.py -q
```
Result: `111 passed`

```
./.venv/bin/python -m pytest -q
```
Result: `1935 passed, 7 deselected, 26 warnings in 6.33s`
(baseline 1929 + 6 net new tests across both commits on this branch:
5 from the first commit + 1 net-new from this round — item 1's test was
rebuilt in place, item 4's test was extended in place, item 2 added one
new test).

### Concerns

None outstanding. All four items addressed exactly as scoped; nothing else
touched (junk constants, `ManifestTrack`, `Overrides` strictness all
untouched, confirmed by `git diff --stat` showing only `models.py`,
`stages/gather.py`, and `tests/test_stage_gather.py`).
