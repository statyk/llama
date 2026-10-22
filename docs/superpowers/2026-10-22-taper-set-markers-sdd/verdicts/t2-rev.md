# t2-rev handback: Task 2 review (1467961..5010a00)

### Spec Compliance
- ✅ Spec compliant. Every requirement in the brief and spec §2-3 is met, checked against the diff (taper.py additions at diff lines 60-182) and by probes on real and constructed tracks:
  - **Matching:** follows the Global Constraints formula exactly. `hit()` (diff L92-97) checks `fuzzy_title_eq(fuzzy_norm_title(title))` or any `title_components` component. `_counts` (L77-78) excludes `unresolved` and `TAUTOLOGICAL_TITLE_SOURCES`.
  - **Unique a, unique b, a < b:** L99-107.
  - **Strictly-between tracks:** each must be `is_filler` and must count, so unresolved or tautological tracks are rejected (L119-121).
  - **Merged track on both sides, for a and for b:** L112-118. **Repeated title across the boundary:** checked over every taper item on each side (L108-111), which declines more than a reading limited to the adjacent sets would.
  - **Filler split** (L122-127): today's split anywhere in a..b-1 is kept when filler exists. With no split, the filler goes with B. Probed: split at b-1 gives filler with A; split at a, or before a, gives filler with B.
  - **Labels** (L159-165): leading tracks carry "1" and trailing tracks carry the last set's label. Probed: tuning,LIG,Scarlet,applause,Brokedown,crowd -> 1,1,2,encore,encore,encore.
  - **Every boundary must place:** L151-153.
  - **Veto order and condition:** only when `not has_encore`; track title first, then `encore_like` (L174-178). Probed with both present -> "veto: track title".
  - **Passthrough:** the reader's reason and `source` are passed through (L172-173).
- Extra declines. All of them own nothing (the taper owns nothing and the show falls back to today's computation) and all are justified:
  - "fewer than two sets" (L140): unreachable through `decide_taper`, since the reader asserts only 2-3 sets and voids empty sets (probed: `Encore:` with no songs -> `void: empty set`).
  - "today's structure splits the filler run more than once" (L124-125): declining is right, because picking one split could move a break.
  - "boundaries out of order" (L155): sets that overlap on the tape.
- Real cases, re-run READ-ONLY against `~/.llama/shows/*/show.json` and `~/.llama/cache/md_*.json` with their real titles and today_sets:
  - moe-1997-02-21 -> `unplaced: 2|encore non-filler track 'Head >' between the songs`.
  - darkstarorchestra-2005-11-16 -> `unplaced: 2|encore last song 'NFA' matches 2 tracks`.
  - Both match the brief's description.
- ⚠️ Cannot verify from diff: nothing material. That `today_sets` has the same length as `tracks` is Task 4's job (see Minor 1).

### Strengths
- The order of checks inside `_place_boundary` keeps the decline reasons accurate and specific.
- No scores or margins. Every gate is an exact count or an exact `fuzzy_title_eq`, as spec §3 requires.
- The "other side" test reuses the same normalization (`left_norms`/`right_norms`) as the match test.
- The reading of the filler rule is correct on the point that matters: a split at the edge of the run is honoured. That is what makes "a taper boundary that agrees with today's at song level moves no filler" hold.
- The tests reach the intended gates. Both repeated-title cases reach the "other side" check instead of tripping on "matches 2 tracks". The veto tests use texts that would otherwise place, so deleting a veto turns them red.
- Mandatory checks:
  - (a) Protected names: the diff only imports and uses them (`_ENCORE_MARKER`, `is_filler`, `TAUTOLOGICAL_TITLE_SOURCES`). Only `taper.py` and `test_taper.py` changed. No do-not-retune constant appears.
  - (b) `git diff main -- packages/llama/src/llama/setlist.py` is empty (0 lines).
- `test_taper.py` passes 108 tests under `-W error` with no warnings.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. **A short `today_sets` is silently ignored** (`taper.py` diff L122, `k + 1 < len(today_sets)`). Probed: `today_sets=["1"]` against 5 tracks placed with filler going to B. Task 4 should pass a list parallel to the tracks. A length mismatch is a caller bug, and raising (or declining) on it would be safer than quietly dropping today's split rule.
2. **Test gaps on edge branches.** None of these is pinned:
   - today's split at b-1 (filler with A). Narrowing `range(a, b)` to the strict interior still passes `test_filler_keeps_todays_split_point`, whose split is mid-run.
   - the two-split decline, "boundaries out of order", and "fewer than two sets".
   - leading and trailing labels.
   - the veto order when both conditions hold.
   All of these behave correctly when probed.
3. **The brief's `Set Break` case was swapped for `Space`** in `test_non_filler_between_is_unplaced` (test diff L258). `Set Break` is the case named in the spec's Documented limitations (`is_filler("Set Break")` is False, so it does decline). It is worth adding back.
4. **The real-case literals are slightly off the real show.** The moe track list adds a leading `tuning/banter` and drops the real titles' trailing ` >`. The DSO assertion checks only `'NFA'` in the reason. My probe with the real show.json gives the same outcomes, so this is fidelity polish only.
5. **Style.** The mid-file imports in `test_taper.py` (diff L204-206, `# noqa: E402`) belong at the top of the file. The decline `"unplaced: fewer than two sets"` lacks the `<A>|<B>` part of the documented format, though it is unreachable.

Observation outside Task 2's scope: the reader turns moe's `03) 32 Things` into `Things`. `parse_setlist` on main does the same, so Task 1's reader inherits it; it is the accepted `100 Years` class. In the taper it can only cause a decline (0 matches), never a moved break.

### Assessment
**Task quality:** Approved
**Reasoning:** Placement and the ownership decision match spec §2-3 exactly. Every added decline leaves the taper owning nothing, and probes on real and constructed edge cases behave correctly. The remaining items are test-coverage and robustness polish.
