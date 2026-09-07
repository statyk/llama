TASK QUALITY: CHANGES REQUESTED

Reviewed `10d3202` (`a431de1..10d3202`) against the Task 2 brief and the design
spec. Two Important findings, three Minor. The wiring itself is correct and
mutation-verified; both Important findings are about a test that cannot fail and
a reasoning gap that the repo's own comment convention would normally cover.

---

## Critical

None. The three do-not-retune junk constants are untouched, `ManifestTrack`
gains no field, no `extra="forbid"` is added, the exclude block still runs after
re-admission, the stamp still sits immediately before `Show(...)`, and no test
reaches the network.

---

## Important

### I1. `test_gather_leaves_ordinary_tracks_unmarked` cannot fail for the behaviour it names
`packages/llama/tests/test_stage_gather.py:2064-2067`

The test writes no `overrides.json` at all, so `overrides.include` is empty and
the guarded stamp block (`gather.py:1134`) never executes; the assertion is then
satisfied by `Track.included`'s `= False` default (`models.py:170`) alone.

Verified by mutation (both restored, tree confirmed clean):

- **M1** — deleted the whole stamp block: `test_gather_readmits_an_operator_included_file`
  went red, `..._leaves_ordinary_tracks_unmarked` stayed **green**.
- **M5** — `t.included = t.filename in forced` → `t.included = True`: again only
  the readmit test went red; this one stayed **green**.

So it pins neither "ordinary tracks are left unmarked by the stamp" nor
over-stamping — it pins the pydantic default, which no line of Task 2 touches.
The implementer's own Step-2 evidence corroborates this: the `-k` filter
(`readmit or included or both_override or include_entry or duration_sec`) does
not match `..._unmarked`, so this test was never observed red.

**Remedy:** make it exercise the stamp — write `Overrides(include=["FOLLOW-ME @BYPIKENO.mp3"])`
and assert every *other* track has `included is False` (that is the real
"ordinary tracks stay unmarked" claim, and it goes red under M5). If the intent
really is to pin the default, rename it accordingly so it stops advertising
coverage it does not have.

### I2. Re-admission silently participates in recording-LEVEL title heuristics, and the adjacent comment reasons only about exclusion
`packages/llama/src/llama/stages/gather.py:843-848`

`kept` is now post-re-admission at every downstream consumer, and four of them
are whole-recording decisions rather than per-file lookups:

- `_recover_format_titles` → `title_fraction(clean_tag_titles(kept)) >= _RECOVER_BELOW`
  (`gather.py:335`) — decides whether wholesale format recovery fires at all,
  and when it fires "the delivered format's own tags are not consulted at all".
- `clean_tag_titles`'s enumeration gate (`titles.py:193`, `numbered >= 0.8 * len(titles)`)
  — re-admitting unnumbered files can drop coverage under 80% and flip the
  leading-track-number strip off for **every** title on the tape.
- `sibling_format_titles`'s filename-stem **bijection** (`titles.py:212`) — a
  re-admitted file with no counterpart in the lossless format breaks the
  bijection, which declines rather than guessing.
- `fetch_siblings` (`gather.py:904`).

The comment immediately above the call site says the position is deliberate
because "moving it below the exclusion would let one dropped file change whether
recovery fires at all." That is still true of `exclude`, but `include` now
creates the exact mirror hazard — one *added* file changing whether recovery
fires — and nothing in the diff says so. It is reachable precisely in this
feature's target population: the `minutemen1983-03-09` case in CLAUDE.md has 27
of 38 files junk-filtered, so re-admitting them moves `title_fraction` from
11/11 to 11/38 and crosses `_RECOVER_BELOW` (0.5).

I am not asking for a behaviour change — a re-admitted file genuinely *is* part
of the tape, so participating is defensible. The defect is that in a repo where
this exact hazard is documented for the exclusion direction, the include
direction is undocumented and untested.

**Remedy:** extend the `gather.py:843-847` comment to state that re-admitted
files DO enter these recording-level heuristics and that this is the intended
reading of "the tape as the operator has ruled it", or, if the opposite is
wanted, compute `format_titles` from a pre-re-admission `kept`. Either way add
one test pinning the chosen direction.

---

## Minor

### M1. `Track.included` is stamped from the override list, not from what was actually re-admitted
`packages/llama/src/llama/stages/gather.py:1133-1137`

`t.included = t.filename in forced` marks any track whose filename appears in
`overrides.include`, including one the junk filter never dropped. `Track.included`'s
own comment (`models.py:167`) says "True when `overrides.include` re-admitted
this file past the junk filter" — false for that track, and the operator gets no
warning either (the file is in `kept`, so the `gather.py:842` loop stays quiet).
`show.json` is the operator's durable provenance record and Task 4 will render
this, so the falsehood is user-visible.

**Remedy:** reword `models.py:167` to "named in `overrides.include` and present
in the track list", or have `filter_files` return the actually-re-admitted set
(`readmitted` already exists as a local at `junk.py:255`) and stamp from it.
Either way, add the "included names an already-kept file" case to the tests —
it is currently untested in both directions.

### M2. In-place mutation where the surrounding code uses `model_copy`
`packages/llama/src/llama/stages/gather.py:1137`

`t.included = ...` mutates `Track` instances in place, whereas the rebuild 90
lines up (`gather.py:1042`) uses `model_copy(update={...})`. Harmless — `tracks`
is local and nothing aliases it — but it is the one place in this function that
mutates a model, and the stamp's own comment is *about* rebuilds, which makes
the inconsistency read as accidental. Optional.

### M3. "matched no file" is imprecise for a right-name/wrong-format entry
`packages/llama/src/llama/stages/gather.py:842-843`

`junk.py:248` documents that `readmit` names the **winning format's** files
only and that anything else "matches nothing here and is warned about by the
caller." So an operator who names a FLAC filename they can plainly see in the
item listing is told it "matched no file." The wording is consistent with the
pre-existing `overrides.exclude` warning, so I would not block on it, but
"matched no file in the selected format (%s)" would save a support round trip.

---

## Strengths

- **The `duration_sec` addition is a real improvement, not scope creep**
  (`gather.py:855-857`). `models.py:187` already documents `duration_sec` on
  *every* `excluded_files` entry; Task 1 delivered that for the three `junk.py`
  producers (`:139`, `:174`, `:178`) but the `operator-excluded` producer in
  `gather` was left inhomogeneous. Closing it here is correct, uses the already
  imported `length_seconds` (`gather.py:26`), and adds no import.
- **Four of the five behaviours are genuinely pinned.** I mutation-tested each
  and named the expected red test before flipping: disabling `readmit` reds the
  readmit + both-lists tests; dropping `duration_sec` reds the fifth test;
  deleting the warning loop reds the warning test; changing the stamp's value
  reds the readmit test. Only I1 above failed to earn its keep.
- **`test_exclude_wins_when_a_file_is_in_both_override_lists` is a strong test** —
  it asserts on `reasons == ["operator-excluded"]` rather than mere absence, so
  it distinguishes "excluded by the operator" from "never re-admitted at all";
  the M2 mutation showed it going red for exactly that reason.
- **The stamp's comment is accurate and load-bearing.** `tracks` really is
  rebuilt by `model_copy` at `gather.py:1042`, after `resolve_titles`, so
  "stamped here rather than in `titles.resolve_titles`" names a real hazard.
- **The `read_overrides` hoist comment is accurate** — `workspace.read_overrides`
  (`workspace.py:59-63`) is a pure read with no file creation, so "it only reads
  the show dir" holds, and hoisting it moves no side effect.
- **The caplog deviation was diagnosed rather than worked around**, and the
  finding is recorded as a comment at the assertion (`test_stage_gather.py:2085-2089`)
  rather than only in the report — which is the right home for it in this
  codebase. The implementation's `log.warning` call is exactly as briefed.
- Constants untouched, no `ManifestTrack` field, no `extra="forbid"`,
  include-then-exclude order preserved, late stamp preserved.

---

## Verification notes

- I did not re-run the full suite; the implementer's `1934 passed, 7 deselected`
  is accepted. All my runs were scoped to
  `packages/llama/tests/test_stage_gather.py` via
  `./.venv/bin/python -m pytest ... -q` (never a `.venv/bin/*` console script).
- Five temporary mutations were applied to
  `packages/llama/src/llama/stages/gather.py`, each reverted immediately with
  `git checkout --`. `git status --porcelain` is empty; the working tree is as I
  found it. Nothing was committed, pushed, or branched.
