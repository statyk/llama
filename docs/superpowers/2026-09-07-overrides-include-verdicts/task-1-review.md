SPEC COMPLIANCE: PASS
TASK QUALITY: CHANGES REQUESTED

# Task 1 review — `Overrides.include`, `Track.included`, `filter_files(readmit=…)`

Base `e9e8911` → head `0b4264a`, one commit, 4 files, +138/-6. Working tree clean.

## Part 1: Spec compliance — ✅ PASS

Every item in the brief is present, and each global constraint I was asked to
verify holds. Checks run (all by reading the files, not by re-running the suite):

- **Junk constants unchanged.** `packages/llama/src/llama/junk.py:66`
  `SHORT_FRACTION_OF_MEDIAN = 0.25`, `:69` `MIN_MEDIAN_SAMPLE = 5`, `:70`
  `MIN_PLAUSIBLE_SEC = 90.0`. The diff touches none of them; no hunk in the
  review package is within 50 lines of them.
- **`ManifestTrack` gains no field.** `models.py` `class ManifestTrack` still has
  exactly `index, set, title, filename, duration_sec, segue`. `included` was added
  only to `Track` (`models.py:167`), with the comment explaining the split.
- **`Overrides` has no `extra="forbid"`.** `models.py:197` — plain `BaseModel`; the
  only `model_config` in the file is at `:277` (`populate_by_name`, a different
  model). `test_overrides_include_defaults_empty_and_survives_an_old_file`
  (`test_models.py:112`) pins the pre-feature `overrides.json` load.
- **Return shape unchanged**: `junk.py:184-187` — `tuple[list[dict], list[dict], dict]`,
  `readmit` keyword-only after `*`, default `frozenset()`.
- **`duration_sec` on every excluded entry produced by `filter_files`**: all three
  `excluded.append` sites updated — `junk.py:138-139` (`_keep_and_exclude`, reusing
  the already-computed `secs`, so `None` is recorded for a missing duration, which
  is itself an exclusion reason), and `junk.py:173-174` and `:176-177`
  (`_dedupe_duplicate_listings`, both branches).
- **Re-admission position** — `junk.py:225-243`, inserted after
  `excluded = excluded + dup_excluded` and before `orig_tracks = {...}`. All three
  required orderings hold; see the measurements below.
- **`readmit` names the winning format only**: `junk.py:238` filters `by_name` on
  `f.get("format") == matched`. No caller warning here — correctly deferred to Task 2.
- **Docstrings**: `filter_files` gained the `readmit` paragraph (`junk.py:210-214`);
  `Overrides`'s stage list now reads `(exclude, include, venue, …)` (`models.py:198`).
- **Backward compatibility of the new kwarg**: named cross-cutting risk — a new
  parameter on a shared API. Checked the call sites named in the report
  (`cli.py:2175`, `stages/select_recording.py:63`, `correspondence.py:305`,
  `stages/gather.py:195,340,834`); all call `filter_files` positionally without
  `readmit`, and the parameter is keyword-only with a default, so none break.

Nothing extra was built. CLI, gather wiring and display are absent, as scoped.

⚠️ **Cannot verify from diff:** the full-suite result (1929 passed / 7 deselected)
and the *baseline* warning count. The report quotes "26 warnings" but not the
pre-change count, so I cannot say whether this change introduced any. Controller
should confirm the warning count is unchanged from `e9e8911`.

## Strengths

- The three-position comment at `junk.py:225-237` is the best thing in the diff:
  it states the invariant, the reason, and the accepted consequence in place,
  where the next person moving this block will read it.
- `junk.py:241` uses `sorted(kept + back, key=…)` rather than appending. A plain
  append would leave a re-admitted file at the end of an otherwise name-sorted
  list, and `test_readmit_lands_in_filename_play_order` (`test_junk.py:326`) is a
  real pin on that: it asserts the full six-element order, not just membership.
- Re-admission pulls the original dict out of `files` (`junk.py:238-240`) rather
  than reconstructing one, so the identity invariant asserted by the pre-existing
  `test_clean_item_byte_identical_through_filter_files` survives re-admission.
- `duration_sec` in `_keep_and_exclude` reuses the already-computed `secs` instead
  of re-parsing — and correctly records `None` rather than eliding the key.

## Issues

### Important (Should Fix)

**1. `test_readmit_does_not_move_the_duration_floor` does not pin the invariant it
names — it passes against the exact mutation it claims to catch.
`packages/llama/tests/test_junk.py:311-321`.** *(Plan-mandated: the test body came
verbatim from the brief. Flagging per the reviewer rubric — the plan does not grade
its own work.)*

The floor is computed at `junk.py:118-126` from `clean_secs`, the durations of files
passing every **non-duration** arm. In the test's dataset all seven files are clean
`_mp3(...)` originals sharing one stem, so the 40 s and 50 s files are **already in
the median sample** before any re-admission happens. No placement of a re-admission
step can therefore change the floor for this data.

Measured, not reasoned. I re-implemented `_keep_and_exclude` in a scratch script
(`/private/tmp/claude-501/-Users-shawn-projects-llama/2c069ceb-0f4b-4b91-88b7-14ff6ccc8501/scratchpad/sdd/t1-rev/mutant_check.py`; nothing in the repo was modified) with
re-admission moved *inside* the junk pass and *before* the floor computation, so
readmitted files are treated as clean and their durations join the sample:

```
MUTANT A floor: 75.0
MUTANT A: test PASSES -> the test does NOT detect this mutation
```

The floor is 75.0 in both the shipped code and the mutant, and every assertion in
the test holds under the mutant. Under the repo's own standing rule
("green suite ≠ pinned"; "mutation scoring needs a prediction"), this test is
documentation, not a constraint.

**Remedy — a dataset that *is* sensitive.** The re-admitted files must be ones
excluded by a **non-duration** arm (so they are absent from `clean_secs`) and
numerous/short enough to move the median. Measured on this dataset:

```python
def test_readmit_does_not_move_the_duration_floor():
    files = ([_mp3(f"band1t0{i}.mp3") for i in range(1, 6)]              # 5 x 300s, clean
             + [_mp3(f"band1t1{i}.mp3", source="mystery", length="20.0") # 5 x 20s, dropped
                for i in range(5)]                                       #   by provenance
             + [_mp3("band1t20.mp3", length="50.0")])                    # the canary
    readmit = frozenset(f"band1t1{i}.mp3" for i in range(5))
    kept, excluded, _ = filter_files(files, readmit=readmit)
    assert readmit <= {f["name"] for f in kept}
    # The floor stays 0.25 * median([300]*5 + [50]) = 75, so the 50s canary is
    # still junk. If re-admission moved ahead of the floor computation the five
    # 20s files would join the sample, the median would fall to 50 and the
    # canary would be licensed.
    assert {e["filename"] for e in excluded
            if "implausibly short" in e["reasons"]} == {"band1t20.mp3"}
```

Verified both ways in the same scratch script: shipped code excludes
`band1t20.mp3`; the early-readmit mutant's floor collapses to **12.5** and keeps it.
Predicted red on the mutant, green on the shipped code — a real pin.

*(Keep the existing test too if you like; it is harmless as a smoke check. It just
must not be the thing standing in for the invariant.)*

### Minor (Nice to Have)

**2. `models.py:187` — the `excluded_files` shape comment is now stale.** It still
reads `# {"filename":..., "reasons":[...]}` while `filter_files` now emits a third
key. One-line fix: `# {"filename":..., "reasons":[...], "duration_sec": float|None}`.

**3. ⚠️ Cross-task, for the controller (not a Task 1 defect):
`stages/gather.py:847`** appends `operator-excluded` rows with no `duration_sec`,
so `Show.excluded_files` will be **heterogeneous** once Task 3 lands — some rows
carry the key, some do not. Task 3 should add it there, or Task 4's display must
use `e.get("duration_sec")`. Out of scope to fix here; flagging so it is not
discovered as a `KeyError` in Task 4.

**4. `junk.py:238-240` — duplicate filenames in the winning format would re-admit
the same dict twice.** If `files` ever contained two entries with the same `name`
and format, both would land in `excluded` under one filename and the list
comprehension over `excluded` would append `by_name[name]` twice to `kept`.
archive.org names are unique within an item, so this is theoretical; a
`dict.fromkeys` over the names, or building `back` from `readmit & by_name.keys()`
intersected with the excluded names, would close it. Not worth churn on its own.

**5. ⚠️ No captured TDD red evidence.** The report (Steps section, item 2) states
the failing run's text was not captured and substitutes "inspection of the
diff-not-yet-applied state", which is not a run. The expected failures here are
mechanically obvious (`TypeError` on an unknown kwarg, `KeyError`/`ValidationError`
on the new fields), and I independently mutation-tested the three load-bearing
positions myself, so this does not change the verdict — but the gap is real and the
one place it would have mattered is finding 1, where a red run would still have
been green-on-red-for-the-wrong-reason.

## Checks run that found nothing

- Position 2 (**after `_dedupe_duplicate_listings`**) **is** pinned. Mutant applying
  re-admission *before* dedupe:
  `MUTANT B (before dedupe): dup test FAILS (detected)` — kept collapses to
  `{'band99/band1t01.mp3'}` and `excluded` regains the `duplicate-listing` row, so
  `test_readmit_of_a_duplicate_listing_ships_the_track_twice`
  (`test_junk.py:352-363`) fails as designed.
- Position 3 (**before the ordering block**) **is** pinned. Mutant applying
  re-admission *after* the ordering block:
  `MUTANT C (after ordering): order test FAILS (detected)` — `order_source` comes
  back `track-tags` instead of `filename`, so
  `test_readmitting_an_untagged_file_falls_back_to_filename_order`
  (`test_junk.py:335-349`) fails as designed. The spec-sanctioned track-tags →
  filename reversion is genuinely covered.
- Test helpers were **reused, not redefined**: `test_junk.py` still defines
  `load_files` (:10), `_tape` (:29), `_short_reasons` (:38) and `_mp3` (:82) exactly
  once each.
- No network in the new tests: they use the on-disk `load_files()` fixture and
  hand-built dicts only.
- `test_excluded_entries_carry_a_duration` (`test_junk.py:366-374`) is load-bearing
  — `isinstance(spam["duration_sec"], float)` plus the `all(... in e ...)` sweep
  would fail if any of the three append sites had been missed.

## Assessment

**Spec compliance:** PASS — the implementation is faithful to the brief, the three
protected constants are untouched, `ManifestTrack` and `Overrides`'s permissiveness
are intact, and the re-admission block sits in the one position that satisfies all
three orderings.

**Task quality:** CHANGES REQUESTED — for finding 1 only. The code is correct; the
test that is supposed to defend its most important property is not sensitive to that
property, which I confirmed by mutation rather than by reading. The fix is one
dataset swap in one test.
