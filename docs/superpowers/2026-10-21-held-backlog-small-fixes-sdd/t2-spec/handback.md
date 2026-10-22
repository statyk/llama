### Spec Compliance (SPEC role) — ✅ Spec compliant
⚠️ Cannot verify from diff: (a) the spec's "readers before selection keep the vote" (winnow rows, setlist.fm lookup, `_place_norms`, catalog suppress fallback) lives in unchanged code; the diff confines `tie` to compute_gather's venue chain, and `venue` after the chain flows only into `show.venue` (gather.py:1547), so nothing suggests a leak. (b) The library-wide "no venue/city flag changes" check is Task 9's.

### Strengths
- `venue_tie_break` (gather.py:958-972) implements the brief's four conditions exactly: stripped-non-blank selected venue; raw-string `Counter` identical to `grouping._make_candidate` (grouping.py:37); `n == vote count`, `n > 0`, `sel.venue != candidate.venue`; selected city blank or `cities_compatible` with the vote city. Returns `(_stripped(sel.venue), sel_city or candidate.city)`.
- Applied in exactly the three arms: no event (`elif tie is not None` on `if event is not None`), unflagged 1a (`elif` after the 1a flag), step 1 (replacing `pass`, guarded by `venues_equivalent(tie[0], event.venue) and (pre1b or cities_compatible(archive_city, jb_city))`). Not touched: enrichment, swap, `two_venue_signature`, 1c, final else, flagged 1a, 1d, overrides.
- `mismatch` is built from the vote before the chain. 1d still reads `vote_venue`/`vote_city`/`sel_venue` (gather.py:1464-1468), so the tie-break adds and removes no flag. `venue_source` is never reassigned by the tie (stays "item"). The candidate object is not mutated, so `provenance.json` is unchanged.
- All 11 brief tests present verbatim, at the end of test_stage_gather.py. The test diff has zero `-` lines, so no existing test was edited. Every behavioural change (no-event ship, blank-city ship, step-1 ship, 1a ship, unit cases) has a test that fails on today's code. Pins are marked.
- CLAUDE.md sentence matches the brief verbatim, placed inside the Tier 1 guards bullet.

**Named risk: which city the step-1 arm's city half uses.** Focused check: gather.py diff hunk at step 1. The city half uses `archive_city = sel_city or vote_city`, the selected recording's city with the vote's as fallback. That is the same city input the vote's own step-1 test uses, and it equals `tie[1]`, the city that ships. So the selected string passes "step 1's full test" with the same city input, and the city the test checks is the one that ships. This matches the spec. It also checks that the Narrowing-S pin really exercises the city half: `_venues_equivalent_pre1b('Penns Landing', "Penn's Landing")` is False, `venues_equivalent` is True and `cities_compatible('Camden, NJ', 'Philadelphia, PA')` is False (run read-only in the worktree venv, `llama.__file__` inside the worktree). So `test_step_1_tie_keeps_the_vote_when_the_selected_string_is_newly_equivalent_and_cities_conflict` would fail on an implementation that skipped Narrowing S.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
- packages/llama/tests/test_stage_gather.py (slice B section): no test puts a tie into the final `else` arm or the 1c arm to show the tie is not applied there. Only the signature arm is pinned, by the existing `test_the_signature_blocks_the_swap_when_the_selected_tape_agrees_with_jerrybase`, and the flagged 1a arm by the new 1a pin. The code shows structurally that both arms are untouched, and the brief did not ask for these tests. Optional fix: add one final-else pin (multi-event date, tie, selected string not equivalent) that asserts the vote ships with the vote-quoted mismatch flag.
- packages/llama/src/llama/stages/gather.py:958: `sel` lacks the `RecordingSummary | None` annotation that the brief's interface names. Cosmetic.

### Assessment
**Task quality:** Approved
**Reasoning:** The diff implements slice B exactly as the brief and the spec's invariants require. It applies in the three arms and nowhere else, adds no flag, keeps `venue_source`, provenance and the vote-quoted mismatch strings, and counts raw strings the way grouping does, with every behavioural change tested. The step-1 city half uses the selected/archive city, which is the city that ships, and this is consistent with "step 1's full test".
