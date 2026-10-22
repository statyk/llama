# gb-rr2: scoped re-review of the slice B narrowing wave (a9d9c78..ba8c964)

### Requirement Verdicts
- **R1: MET.** `gather.py:968-969` adds `if not venues_equivalent(_stripped(sel.venue), candidate.venue): return None` inside `venue_tie_break`, after the unchanged blank, count, tie and same-string checks and before the unchanged city gate. The call site `gather.py:1412` (`tie = ... if overrides.venue is None else None`) and the three arms (`:1428`, `:1438-1441`, `:1457`) are untouched. `git diff --stat a9d9c78 ba8c964` touches only CLAUDE.md, the spec, gather.py (the function only) and test_stage_gather.py. structure.py and songs.py are not in the diff, so `venues_equivalent`, `normalize_song`, `DEFAULT_ALIASES` and the constants are byte-identical. `candidate.venue` cannot be blank where the check runs, because the count-equality guard requires it to have n>0 votes.
- **R2: MET.** New test `test_a_tie_between_different_names_ships_the_vote_unchanged` (test_stage_gather.py:3063): "9:30 Club" vs "Nightclub", same city, no-event arm via `_gd(jerrybase_enabled=False)`. It asserts the vote's venue and city and no venue flags. Its city assertion cannot fail, because both recordings carry "Washington, DC" (minor, see below); the venue assertion is the one that discriminates. The implementer reports it RED on a9d9c78's source with `'Nightclub' != '9:30 Club'`. My m1 mutant reproduces exactly that failure. The equivalent-pair test `test_tie_ships_the_selected_recordings_string_without_jerrybase` ("R.F.K. Stadium"/" RFK Stadium ") is unchanged and green.
  - The one reshaped test is `test_step_1_tie_keeps_the_vote_when_jerrybase_does_not_corroborate_the_selected_string`. Vote "Barrymore Theatre Madison" vs selected "Madison"; jerrybase DSO 2003-01-25 is "Barrymore Theatre", Madison WI (set_breaks.csv:10438).
  - It still tests corroboration. "Madison" is a token subset of the vote, so the tie applies, and the added `venue_tie_break(...) is not None` assert pins that. The vote is equivalent to jerrybase, so the show takes step 1. "Madison" is not equivalent to "Barrymore Theatre", so step 1's full test refuses and the vote ships.
  - The old pair, "Barrymore Theatre"/"Orpheum Theater", would have passed without ever reaching step 1. The reshape was necessary and does not weaken anything.
  - Mutant check (m2, scratch): with the step-1 tie condition reduced to `tie is not None`, this test goes RED, along with `..._newly_equivalent_and_cities_conflict`. Removing only the `venues_equivalent(tie[0], event.venue)` conjunct would also turn it red, because the cities agree, so the remaining city disjunct passes and "Madison" would ship.
- **R3: MET (re-run independently).** Prediction logged first: `test_a_tie_between_different_names_ships_the_vote_unchanged`. Setup: a scratch copy from `git archive ba8c964`, with the two-line check deleted. `llama.__file__` was proven to be inside the scratch tree, and the run used `PYTHONPATH` shadowing, `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`. Result: exactly 1 failed (the predicted test), 170 passed. The unmutated control copy gave 171 passed. CAUGHT.
- **R4: MET.**
  - Spec slice B invariants: the new bullet names `venues_equivalent` and gives the measured reason, "about 38 of 234 ties … '9:30 Club' -> 'Nightclub'".
  - The CLAUDE.md "Venue tie-break" bullet adds the equivalence limit (with the 9:30 Club example) and "never under an operator venue override".
  - The CLAUDE.md triage line now reads "re-captures the view, then re-resolves, and re-prints". That matches `cli._interactive_resolve`: `capture_view` at cli.py:1837, `_resolve_show` at :1842, `_print_show_entry` after it. Both ShowChanged handlers (:1956, :1978) re-enter that function.
- **R5: MET.**
  - cand-2.json records `sha` ba8c964c7d1b… with no `-dirty` suffix. Its `config_fingerprint` (3f1af9a8…), `setlistfm_configured=True`, scope `all` and 3983 shows all match base.json. All digests are identical to both base and cand.
  - The compare output files hash to the implementer's values: summary.txt `753fd329…`, venue_changes.txt `75398f48…`.
  - No venue or city flag was added or removed, nothing is newly held, and all venue rows are `venues_equivalent` (numbers below).

### Recomputed numbers
These come from a read-only script over the arm JSONs, using the harness's own `_shipped` and `_all_flags` logic and the worktree's `structure.venues_equivalent`.

**base vs cand-2:**
- venue_changes: **175** rows (all 175 change the venue; none is city-only). **0** non-equivalent.
- City changes: **50**. DELIVERED: **119**.
- Shows whose venue/city flag set differs: **0**.
- Shows whose flag set differs at all: 8. All 8 are removals only: `research asserts unknown song` and `low-confidence structure alignment` on joerussosalmostdead and johnkadlecik shows and thetravelinmccourys-2014-05-24. These come from the other slices and are identical to base vs cand.
- Outcome differences:
  - clean→clean-changed: 121
  - newly-held→clean: 1 (joerussosalmostdead-2019-03-03)
  - still-held→needs-brief: 1 (johnkadlecik-2021-11-28)
- No show becomes newly-held or still-held in cand-2 that was not already in base. cand-2's 183 "newly-held" is a subset of base's 184; it is a replay-versus-stored category, not something this change caused.

**cand (36473d8, pre-narrowing) vs cand-2:**
- **59** shows differ, and they differ only in `venue` (58), `city` (15), `outcome` (42, all clean-changed→clean) and `briefing` (42). No flags differ and no digests differ.
- In all 59 shows, cand-2's venue/city record equals base's, so the tie-break simply no longer fires there.
- **58** are venue ties whose two strings are NOT `venues_equivalent`. This is exactly the set the narrowing removes, and it equals the 58 non-equivalent rows in base vs cand.
- **1 other difference:** jackiegreene-2010-05-29 is a city-only change. cand shipped `'angels camp, california'` and cand-2 ships the stored `'Angels Camp, California'`; the show has an overrides.json. This is the effect of the intervening commit **12af7eb** (an operator venue override takes no tie-break city), which postdates cand.json's 36473d8. It is not caused by the narrowing.
- 234 − 175 = 59 = 58 + 1, so the arithmetic closes.

### New Breakage in the Wave
None.
- Minor: in test_stage_gather.py:3063-3069 the new test's city assertion cannot discriminate, because both recordings carry "Washington, DC". The brief asked for "ships the vote unchanged (venue and city)". A selected city that is compatible but spelled differently (e.g. "Washington, District of Columbia") would make the city half real. Not blocking: the venue half pins the rule, and the city follows from the same `return None`.

### Out-of-Scope Observations
- **The narrowing removes 58 ties, not the ~38 cited in the spec and CLAUDE.md.** About 20 of the 58 look like one venue spelled two ways that `venues_equivalent` does not fold: "Knaack Club"/"Knaack Klub", "1st Avenue"/"First Avenue", "Ironhorse"/"Iron Horse Music Hall", "Studio 105"/"Studio 10S", "Wakarusa Music Fest"/"…Festival", "The Ice Palace Sound Stage(s)", "Henry J Kaiser Arena"/"Auditorium", "Riviera Theatre"/"Riviera Th. Chicago, Ill.", "WVU Mountainlair Ballroom"/"Mountainlair Ballroom @ West Virginia University", "Mullins Center, University of Massachusetts"/"The Mullins center @ Umass". In those cases the vote now ships, which is the base behaviour, so this is not a regression; slice B just covers less than the "~38" framing suggests. The doc sentence states the owner's figure as the reason, so it is not wrong, but it could be read as "only ~38 ties are affected". Worth one line to the owner.
- Within the 175 surviving rows, `venues_equivalent`'s subset rule lets in some long-form strings, e.g. belafleckandtheflecktones-1991-08-02: "Lonesome Pine" -> "Kentucky Center for the Arts, Bomhard Hall, Lonesome Pine Special" (DELIVERED). This follows the ruled predicate exactly; noted only so the owner knows equivalence is not the same as "a tidier spelling".

### Verdict
**Wave:** All requirements met, no new Critical/Important breakage.

Scratch (outside the repo and outside $D): /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-held-backlog-small-fixes/ebe57100-b9d1-4f05-a3b0-c4b5afb1ad48/scratchpad/rr2/ (check.py, check2.py; m0 control, m1 and m2 mutant copies). Log: $D/gb-rr2/gb-rr2.log. The live worktree was not mutated (clean at ba8c964); ~/.llama was not read; nothing was written under ~/.llama-harness.
