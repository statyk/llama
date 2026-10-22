### Spec Compliance (SPEC role) — n/a (CODE-QUALITY role). Nothing Critical noticed outside my lane; the diff matches the brief's rules, row format and summary line verbatim.

### Strengths
- `_shipped` (scripts/replay_holds.py:375-382) gets the derivation right for every case the row shape allows. Each arm's own `new` wins. Otherwise it falls back to the other arm's `old`, the stored value. When neither arm has a diff it returns None on both sides, so the show is correctly not a change. I checked this against `replay._pair` (packages/llama/src/llama/replay.py:182-183: null iff old == new). A genuine shipped null (`{"old": "X", "new": null}`) is never confused with "unchanged". A null shipped in one arm is always paired with the other arm's stored value, so `X -> null` only appears for a real change.
- Unlike `_exposure`, which prints the raw diff dicts (`null -> {"old":..,"new":..}`, :356), this report prints the shipped values. That is what a human checking acceptance needs.
- The skip test is the only filter besides equality, so a changed show cannot be dropped silently. Needs-LLM rows still carry `venue`/`city` (replay.py:474-478 computes `shipped_diff` after `classify`), so they are listed, not lost. Unreplayable rows are counted in the header.
- It is consistent with the neighbouring reports: the same `NONE` placeholder, `_j`, slug order, the `[state]` tag, the `compare` placement and the summary line.
- The brief's tests are verbatim. They kill the main wrong-derivation mutants I reasoned through:
  - A fallback that returns None fails test 1's `"RFK Stadium" ->` assertion.
  - A fallback that returns the other arm's `new`, or own-diff returning `old`, makes bv == cv, so nothing is listed and test 1 fails.
  - Comparing venue only fails test 2. Comparing city only fails test 1.
- None of the do-not-retune names appear in the diff (grep count 0).

### Issues
#### Critical
None.
#### Important
None.
#### Minor
1. **Unreplayable shows are counted but not named** (scripts/replay_holds.py:386-388, 403-404). The header lumps shows unreplayable in both arms (e.g. `show directory missing`) with shows that became unreplayable in only one arm. The second kind is the case where a code change broke a show, so whether its venue changed is unknowable. The summary.txt line (:820) does not mention the skip count at all. Across ~4,000 shows, a reader of summary.txt alone sees "N show(s)" and nothing about unknowns. This is plan-mandated ("skipped and counted in a header line"), so it is Minor. Fix if wanted: list the slugs unreplayable in exactly one arm under the header, and/or append `, {skipped} skipped (unreplayable)` to the summary line.
2. **A field that is unchanged and has no diff in either arm prints as `null -> null`** (:389-390, 396-397). An example is the venue line on a city-only change in the common case. Both sides are unknown-equal, not null. As shown above this is never ambiguous about *change*, but a human may read it as "ships no venue". Test 2's "unchanged venue still shown on the row" comment holds only because both arms carry an identical venue diff. Fix if wanted: print `(unchanged)` for a field where `_shipped` fell through on both sides.
3. **Several rules are untested**, so mutants of them survive. Reasoned from the fixture: `_two_arms` builds no unreplayable rows in these tests, both arms are `delivered` in test 1, and test 2 sets only `gather_flags`. The surviving mutants:
   - dropping the unreplayable skip or its counter (the header count is never asserted)
   - taking `state` from base instead of cand (test 1 has both arms `delivered`)
   - using `_flags` instead of `_all_flags` (test 2 changes only `gather_flags`, so a `brief_flags`-only change is unpinned)
   - swapping added/removed (only `"flags CHANGED: added"` is asserted, not its contents or `removed`)
   - the case where base has a diff and cand has none (a replay reverting to stored)

   Add one row in each test to cover them if wanted.
4. **The row omits `outcome`** (:394). A needs-LLM show's replayed venue is not necessarily what would ship, and a still-held show ships nothing. `[state]` gives part of this but not needs-LLM. Fix if wanted: `[{state}/{outcome}]`.

### Assessment
**Task quality:** Approved
**Reasoning:** The shipped-value derivation is correct for every row shape `_pair` can produce, no changed show is dropped except the counted unreplayable ones the plan mandates, and the tests kill the wrong-derivation mutants that matter. The remaining items are reporting polish and broader coverage.
