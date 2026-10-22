# t7a-rr1: DONE — Fix round 1: all findings addressed, no new Critical/Important breakage

### Finding Verdicts
- **I1, renumbered rows never graded** — ADDRESSED.
  - `scripts/replay_holds.py:105-125`: `_shadow` returns `{key: value}` for each stripped key that was present.
  - `scripts/replay_holds.py:134-150`: `_replay_stripped` writes it to `row["stripped"]` on stripped arms only. Unstripped rows have no key (`:189-191`).
  - `scripts/taper_probe.py:674-684`: `_fix_applied` compares `sorted(set_breaks or [])` with `sorted(t_breaks or [])`, and `encore_after` with `t_enc`. An empty or missing `stripped` counts as not applied.
  - `scripts/taper_probe.py:714`: grading is gated on `_fix_applied`, and "not graded" stays the fallback.
  - Check run, part (a). I read `sort1.json` (394 rows; `t_breaks` is a list or None, `t_enc` is an int or None). I read the live `~/.llama/shows/<slug>/overrides.json` read-only and ran the real `tp._fix_applied` over every `renum` yes/partial row.
    - Result: **55 graded (45 yes + 10 partial), 18 not graded**, which equals the reviewer's count. All 18 have no `overrides.json` at all.
    - Types line up. Library `set_breaks` is a list (45) or a present `null` (10), and `None or []` handles the null. `encore_after` is an int (47) or a present `null` (8), which equals sort1's `None`.
    - Breaks use the same 1-based convention on both sides; the 55 exact equalities show this.
    - Script: `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/0443a042-e8ee-4093-a603-2fbd14e62179/scratchpad/t7a-rr1/check_renum.py`. Output is in the log.
  - Both branches are tested:
    - `scripts/test_taper_probe.py` `test_score_grades_a_renumbered_row_only_when_the_adjudicators_fix_was_stripped` covers four cases: applied, different breaks, nothing stripped, and missing encore.
    - `scripts/test_replay_holds.py:858-862` pins the stripped record and its absence on an unstripped arm.
- **I2, known-disagreement encoding weaker than spec** — ADDRESSED.
  - `scripts/taper_probe.py:626-636`: stevekimockband-2003-03-11 is now `no-encore`. deadandcompany-2018-06-16 and ekoostikhookah-2009-12-31 are now `not-asserted`. Only gratefuldead-1981-12-31 keeps `ships`.
  - `:662-663`: an owned `not-asserted` row is UNEXPECTED, and a declined one is "as expected" (the `not owned` branch runs first).
  - The test covers both directions for each new kind. Declined or no-encore-owned is "as expected". Owned with an encore label, for ekoostik, deadandcompany and stevekimock, is UNEXPECTED (`scripts/test_taper_probe.py`, second `score_rows` pass).
- **M3, headline over `row["in_scope"]` with a yes/partial split** — ADDRESSED.
  - `scripts/taper_probe.py:740-757`: there is a new IN SCOPE headline over `row["in_scope"]` (set at `:696`), with "of which yes" and "of which partial" lines. The old line is renamed "yes/partial excluding filename/track-tag".
  - Asserted in `test_score_counts_matches_against_adjudicator_targets`.

Check (b), the changed test assertions:
- In `test_score_counts_matches...`, two assertions changed their label text only. The numbers are the same (4 and 3), and the fixture has no renum rows, so 3 is still the correct count.
- In the known-disagreement test, the deadandcompany `"owned; the taper's structure ships"` assertion became `startswith("declined")`. The fixture now marks deadandcompany as not owned, which is correct for its new kind. A 1981-12-31 `"happens to equal"` assertion was added. The owned direction is now tested by the new UNEXPECTED pass, so the test is stronger, not weaker.

### New Breakage in the Fix Diff
- Minor: `scripts/taper_probe.py:668-669`, the `ships` branch. The "owned; the taper's structure ships, differing from the target" detail is no longer exercised by any test.
  - Before the fix, deadandcompany and stevekimock covered it. The only `ships` fixture left (1981-12-31) equals the target.
  - The verdict is "as expected" in both sub-branches, so only the detail text is unpinned.
  - Fix: one extra 1981 fixture with differing sets.
- Note, not a defect: `_replay_stripped`'s docstring still says "so arms stay comparable with an unstripped base". That is the earlier review's Minor 1, which was deferred.

### Out-of-Scope Observations
None beyond the review's deferred Minors 1, 2 and 4, which remain open by orchestrator ruling.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage. One new Minor: the ships-differing detail branch has no test.

Status: DONE. Commits: none (reviewer). Tests: none run. The one check was a read-only `_fix_applied` simulation over the live library's renum yes/partial rows, giving 55 graded and 18 not graded. Nothing was written outside `$D/t7a-rr1/` and the scratchpad. Log: $D/t7a-rr1/t7a-rr1.log.
