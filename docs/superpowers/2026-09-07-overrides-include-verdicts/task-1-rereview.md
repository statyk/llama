Finding 1 (Important): ADDRESSED
Finding 2 (Minor): ADDRESSED
New breakage in the fix diff: none
VERDICT: all findings addressed

# Scoped re-review — Task 1, fix round 1 (0b4264a..a431de1)

Branch `overrides-include`, main checkout. Fix diff: 2 files, +26/-9 —
`packages/llama/src/llama/models.py` (one comment line) and
`packages/llama/tests/test_junk.py` (one test rebuilt).

## Finding 1 (Important) — `test_readmit_does_not_move_the_duration_floor` was not mutation-sensitive

**ADDRESSED.** `packages/llama/tests/test_junk.py:312-338`.

I did not take the implementer's mutation run on trust. I reasoned the dataset
through from the code and then ran the mutation myself.

**Why the old dataset was blind (confirmed, not assumed).** The pre-fix data was
`5 x 300s` + `40s` + `50s`, all `source="original"` with a common stem, so every
file passed the two non-duration arms. `_keep_and_exclude`'s `clean_secs`
(`junk.py:118-125`) therefore already contained all seven durations no matter
where re-admission ran; the median is 300 and the floor 75.0 in both worlds.
Nothing about re-admission ordering could change the outcome.

**Why the new dataset is sensitive.** The rebuilt data is
`5 x 300s` clean + `5 x 20s` with `source="mystery"` + one `50s` canary. The
`_mp3` helper (`test_junk.py:82-88`) stamps `format="VBR MP3"` and no `original`,
so `source="mystery"` falls through `junk.py:107-110` to `"unknown provenance"` —
a NON-duration arm. Those five durations are consequently outside `clean_secs`:
`clean_secs = [300]*5 + [50]`, `len = 6 >= MIN_MEDIAN_SAMPLE`, `median = 300`,
`floor = 0.25 * 300 = 75.0`, so the 50s canary is still "implausibly short".
Move re-admission ahead of that computation and the five 20s files join the
sample: `median([20]*5 + [50] + [300]*5) = 50`, `floor = 12.5`, and the canary is
licensed. I computed both floors directly against the shipped constants:

```
$ ./.venv/bin/python -c "..."   # statistics.median with junk.SHORT_FRACTION_OF_MEDIAN
shipped floor: 75.0
mutant  floor: 12.5
```

Note the stem check is satisfied throughout: `_stem` cuts at the first digit, so
every `band1t..` name has stem `band` and `dominant` is unambiguous — the
provenance arm is the only non-duration arm firing, which is what makes the
dataset's intent legible.

**Mutation run (mine, independent).** I applied a temporary mutant to
`packages/llama/src/llama/junk.py` expressing exactly "re-admission runs before
the floor computation": `_keep_and_exclude` gained a `readmit` parameter, the
non-duration reason list became `[] if f["name"] in readmit else reasons`
(so a re-admitted file's duration enters `clean_secs`), and `filter_files`
passed `readmit` down. Results:

- New test against the MUTANT: **FAILED** —
  `AssertionError: assert set() == {'band1t20.mp3'}` (the canary was licensed,
  floor collapsed to 12.5). This is the exact predicted failure mode, not an
  incidental error.
- The OLD (pre-fix) version of the same test, replayed against the SAME mutant:
  **PASSED** — confirming the review finding was real and that the rebuild, not
  a change of mutant, is what closed the gap.
- New test against the restored shipped code: **PASSED**.

Mutation restored with `git checkout -- packages/llama/src/llama/junk.py`
(the command was run under a shell `trap ... EXIT` so restore could not be
skipped). Verified afterwards:
`git hash-object packages/llama/src/llama/junk.py` =
`20003bfadf405fc10a8e8f4d0289d0431be1573d`, identical to
`0b4264a:packages/llama/src/llama/junk.py`, `a431de1:...` and `HEAD:...`;
`git status --porcelain` empty.

**`junk.py` untouched in this fix round — confirmed independently.**
`git diff --quiet 0b4264a..a431de1 -- packages/llama/src/llama/junk.py` returns
clean, and all four blob hashes above match. The implementer's claim holds.

## Finding 2 (Minor) — stale `excluded_files` shape comment

**ADDRESSED.** `packages/llama/src/llama/models.py:187` now reads
`# {"filename":..., "reasons":[...], "duration_sec": float | None}`. The
documented shape matches what `_keep_and_exclude` (`junk.py:136-138`) and both
`_dedupe_duplicate_listings` appends (`junk.py:167-172`) actually emit, including
the `None` case for a file with no length (which is itself the "missing duration"
exclusion reason).

## New Breakage in the Fix Diff

**None.**

- The rebuilt test asserts `readmit <= {f["name"] for f in kept}` (frozenset ⊆
  set — valid) and narrows the "implausibly short" set to the canary. Both
  assertions are load-bearing; neither is trivially true.
- The five re-admitted files carry `["unknown provenance", "implausibly short"]`
  as reasons and are removed from `excluded` wholesale by the re-admission block
  (`junk.py:242-248`), which is why the second assertion's set is exactly
  `{"band1t20.mp3"}` — the test does not accidentally depend on reason ordering.
- No production behaviour changed: the only non-test edit is a comment.
- No network: the dataset is synthetic dicts built in-process; no fixture load,
  no HTTP.

## Constraint checks (all hold)

- `junk.py:66,69,70` — `SHORT_FRACTION_OF_MEDIAN = 0.25`,
  `MIN_MEDIAN_SAMPLE = 5`, `MIN_PLAUSIBLE_SEC = 90.0`, unchanged from 0b4264a
  (whole file byte-identical).
- `ManifestTrack` (`models.py:250-256`) gains no field — still
  `index/set/title/filename/duration_sec/segue`. `Track.included` sits at
  `models.py:170` as intended.
- `grep -n "extra=" packages/llama/src/llama/models.py` → no matches, so
  `Overrides` (`models.py:197-210`) has no `extra="forbid"` and still round-trips
  an old `overrides.json` with no `include` key.

## Tests I ran

```
$ ./.venv/bin/python -m pytest packages/llama/tests/test_junk.py packages/llama/tests/test_models.py -q
44 passed in 0.16s

$ ./.venv/bin/python -m pytest -q
1929 passed, 7 deselected, 26 warnings in 6.39s
```

Matches the implementer's reported counts exactly (1929 passed / 7 deselected /
26 warnings). Working tree clean at finish (`git status --porcelain` empty);
nothing committed, no branch or HEAD change.

## Out-of-Scope Observations

- None blocking. One nit, deferrable and outside the fix's behaviour: the
  rebuilt test's docstring narrates the review round itself ("Review round 1
  finding: ...") rather than only the invariant. It is accurate and the repo
  favours explanatory comments that record measurements, so this is a style
  preference at most — leave it.

## Verdict

**Fix round: All findings addressed, no new Critical/Important breakage.**
Finding 1 is mutation-proven by my own run, not by the implementer's report;
Finding 2 is a verified comment correction. Task 1 is clear to proceed.
