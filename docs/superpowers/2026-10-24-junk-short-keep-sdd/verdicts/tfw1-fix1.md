# tfw1-fix1 handback: FW1 fix round 1 (C-1, I-1)

**Status: DONE.**
- Commit: `1bcccd1`, "fix(junk): keep the copy named after its original; honour operator excludes", on `held-backlog-junk-filter` after `bcfeef4`.
- No push or merge.

## What changed
`packages/llama/src/llama/junk.py` and `packages/llama/src/llama/stages/gather.py`.

**C-1: the preference picks the copy named after its original.**
- `_derivative_preference` now returns `(vbr != PREFER_VBR_DERIVATIVE, stale, name)`. This is the reviewer's key: `stale` is true when the copy's `basename_without_extension` differs from its original's.
- For plain/`_vbr` pairs nothing changes, because the first element already decides them. The `_vbr` flip is still one line.
- The docstring records the gd1984 case and the 23-group measurement.

**I-1: operator excludes, using the preferred fix.**
- `filter_files` takes a new keyword, `exclude: frozenset[str] = frozenset()`. It is read only on the `short_keep=True` path, passes through `_choose_format`, and reaches `_dedupe_derivatives(kept, avoid)`.
- An avoided file is never grouped: it is never chosen and never dropped as a duplicate. It stays in the filter's `kept`, and the copy that is kept is chosen among the others.
- `gather.final_kept` passes `frozenset(overrides.exclude)`, then drops those files as `operator-excluded` as before.
- The comment on the preference constant now says the preference only chooses among copies the operator has not excluded.
- Unchanged:
  - the `short_keep=False` path: legacy `else` arm, which ignores `exclude`;
  - `_dedupe_duplicate_listings`;
  - the readmit block;
  - play order. An avoided copy stays in `kept` until after the order is derived, so its shared tag still forces filename order, as at a693878.
  - The running-time format choice counts the filter's `kept`, avoided copies included. With mp3 (one format) this cannot matter.

## Covering tests

The new tests are in `packages/llama/tests/test_format_choice_and_derivatives.py`, section "fix round 1":
- `test_gd1984_stale_copies_lose_to_the_copies_named_after_their_originals`: real fixture. Track 1 is Day Job, Scarlet follows `d1t10`, U.S. Blues is last, and both stale copies are `duplicate derivative`.
- `test_gd1985_baby_blue_stays_the_encore`: real fixture.
- `test_an_operator_exclude_of_the_plain_copy_keeps_the_vbr`
- `test_both_copies_excluded_stay_out` (pin)
- `test_sci_ships_the_same_songs_at_either_preference`: the same 25 originals at both `PREFER_VBR_DERIVATIVE` values, each once at the default, and no `matched no file` warning.
- `test_the_exclude_pass_through_leaves_the_legacy_filter_alone` (pin, against the v2.17.0 model)

The two new fixtures were cut with `scripts/capture_fixture.py --from-cache`:
- `gd1984-04-13.132772.Sennheiser-holbrook.flac24.json`
- `gd1985-07-01.176684.senn.nd41.strizak.flac2448.json`

They also join the v2.17.0 `short_keep=False` equivalence test, which still passes.

**RED on `bcfeef4`** (the live worktree before the fix): `./.venv/bin/python -m pytest -q packages/llama/tests/test_format_choice_and_derivatives.py` gave **5 failed, 17 passed**.
- gd1984: track 1 was `gd1984-04-13(24Bit48khz)d2t01.mp3`.
- gd1985: the last track was `s2t11 Satisfaction`, because Baby Blue had sorted second.
- Plain-exclude: no `x1t03` copy shipped.
- sci: `matched no file` warnings were logged.
- Legacy pin: `TypeError: unexpected keyword argument 'exclude'`.
- The both-excluded pin passed, as a pin should.

**GREEN:** `./.venv/bin/python -m pytest -q packages/llama/tests/test_format_choice_and_derivatives.py packages/llama/tests/test_short_keep_rule.py packages/llama/tests/test_junk.py` gives **140 passed**.

**Mutation check** (scratch `git archive` copy, `PYTHONPATH` shadow verified, run with `-B`). The expected red tests were named before each flip, and each mutant failed exactly those tests:
- F1, no stale rank: the gd1984 and gd1985 tests.
- F2, `avoid` ignored when grouping: the plain-exclude and sci tests.
- F3, `exclude` not passed through `filter_files`: the plain-exclude and sci tests.

**Full suite** (`./.venv/bin/python -m pytest -q`, run in the background): **5394 passed, 1 skipped, 8 deselected**. That is the earlier 5388 plus the 6 new tests. No existing expectation changed.

## Re-measure
Same scripts, outputs beside the old ones as `*-r1.*` under `~/.llama-harness/piece4/fw1/`. A new `FW1_SUFFIX` env var in `common.py` selects the suffix. The M2 old arm now wraps a693878's filter to drop the new `exclude` keyword.

- **M1 (cache scan):** no change at that level.
  - Flips are identical (mp3 0, flac 31), and so is the 111-item / 1,970-file mp3 kept-change set, with 0 non-dedupe changes.
  - Within those items, **11 of the 23 non-`_vbr` groups now keep the other copy**: the one named after its original. They are:
    - `bw2022-05-01.flac24`: `BWWB2022-05-01-001`
    - `gd1984-04-13…Sennheiser-holbrook.flac24`: `d2t01`, `d2t11`
    - `gd1985-07-01…strizak.flac2448`: `s2t12 Baby Blue`
    - `mp1988-01-30.sbd`: 4 groups
    - `wd2013-07-05…070513`: 3 groups
  - As a side effect, the kept copy is now the newer file (by `mtime`) in **23 of 23** such groups; before, it was 12 of 23 (`m1c_nonvbr_mtime-r1.json`).
- **M2 (library kept lists):** **identical to r0.**
  - 23 shows change and 414 files drop, every one a `_vbr` `duplicate derivative`. Nothing else is dropped or added, no order changes, and no song is lost (`m2_changed-r1.json`).
  - The difference is in the reasons only. On the five hand-repaired shows (sci, jrad, ttb2022, gd1970-05-06, gd1985-11-10), the operator's `_vbr` excludes now drop their files as `operator-excluded`, where r0 recorded them as `duplicate derivative` with a no-op exclude.
  - Exclude `matched no file` warnings in r1: 0. The 10 remaining warnings are pre-existing `include` entries, printed once per arm: `db2003-08-15`, `db2003-11-28`, `sci01-08-01`.
- **M2b:** unchanged. 13 of 414 dropped copies differ by more than 2 s, and the kept plain copy is always the longer.
- **M3 (selected recording):** **identical to r0.** The same 20 GD shows change selection (`m3_changed-r1.json`).

## Concerns
1. **A `_vbr` flip still has an `include` hazard** (deferred item M-2). On sci with `PREFER_VBR_DERIVATIVE=True`, the same 25 songs ship, but 5 of them ship twice. The operator's `include` names the five short plain copies, which the flip drops as duplicates, and `include` re-admits a dropped copy (the brief's requirement). So a flip has to revisit those includes. The sci test documents this rather than asserting it away.
2. The running-time format choice counts avoided copies with the rest of the filter's kept list. This only matters with two formats and an exclude list naming one of them; no library show measured is affected.
