# gb-narrow handback — DONE

Commits: c139a65 fix(gather): venue tie-break applies only to venues_equivalent strings; ba8c964 docs: venue tie-break equivalence limit; triage step order matches code. Tree clean at ba8c964 for the candidate arm.

## Code
gather.venue_tie_break: after the blank/count/tie checks, `if not venues_equivalent(_stripped(sel.venue), candidate.venue): return None`; docstring updated. All other conditions, the three arms and the override suppression untouched.

## Tests
- NEW test_a_tie_between_different_names_ships_the_vote_unchanged ("9:30 Club" vs "Nightclub", same city; ships vote venue+city, no venue flags). RED on a9d9c78 source: `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k different_names` -> `AssertionError: 'Nightclub' != '9:30 Club'`, 1 failed. GREEN after edit.
- Equivalent-tie test kept: test_tie_ships_the_selected_recordings_string_without_jerrybase ("R.F.K. Stadium"/"RFK Stadium"), plus the 1a/step-1 Penn's Landing tests and unit cases, all unchanged and green.
- CHANGED (only one): test_step_1_tie_keeps_the_vote_when_jerrybase_does_not_corroborate_the_selected_string. It used "Barrymore Theatre" vs "Orpheum Theater" (not equivalent); it kept passing but would have stopped testing step 1's corroboration. Reshaped to vote "Barrymore Theatre Madison" vs selected "Madison" (equivalent to the vote, not to jerrybase's "Barrymore Theatre"), with an added assert `venue_tie_break(...) is not None` so the test reaches the step-1 test. Final venue assertion updated to the new vote string. No other assertion weakened. No other existing test changed outcome.
- Full suite: `./.venv/bin/python -m pytest -q` -> 4047 passed, 1 skipped, 8 deselected.

## Mutant (scratch copy: git archive HEAD | tar -x; PYTHONPATH shadow; llama.__file__ proven inside scratch)
Prediction (logged first): test_a_tie_between_different_names_ships_the_vote_unchanged goes red. Mutant: delete the venues_equivalent check. Command: `<worktree>/.venv/bin/python -m pytest -q -p no:cacheprovider packages/llama/tests/test_stage_gather.py` from the scratch dir. Result: 1 failed (exactly the predicted test), 170 passed. CAUGHT.

## Docs
Spec slice B invariant: added the equivalence sentence with the 38/234 measurement and "9:30 Club"->"Nightclub". CLAUDE.md Venue tie-break bullet: equivalence limit + never under an operator venue override. CLAUDE.md triage line: now "re-captures the view, then re-resolves, and re-prints" (matches cli._interactive_resolve: capture_view, then _resolve_show).

## Harness
- `./.venv/bin/python scripts/replay_holds.py run --all --out ~/.llama-harness/small-fixes/cand-2.json` exit 0: replayed 3983: clean=2830, clean-changed=126, needs-brief=5, needs-llm=697, newly-held=183, still-held=141, still-held-package=1.
- `compare base.json cand-2.json --out cmp-norepro-2 --no-repro-gate` exit 0 (arms matched; base-2 not needed).
- summary.txt: venue_changes.txt: 175 show(s), 0 with a flag change (was 234); packaged_exposure 161 (was 214); needs-LLM held base 192/cand 192; base reproduces 134/147; briefing guard 3/4; newly cleared 1 (johnkadlecik-2021-11-28); structure_changed 0; predicted_list/pilot_list 5 rows.
- venue_changes total 175 (234 -> 175, 59 fewer). Non-equivalent rows under venues_equivalent: 0 (all 175 rows checked). Rows whose city line differs: 50 (all cosmetic spellings e.g. "Athens, Ga." -> "Athens, GA"; none a different place on the 12 sampled lines). DELIVERED rows: 119. Flags changed: 0. No newly held: newly-held=183 is the non-held-before category, identical to the earlier cmp-norepro run (outcomes.txt differs from it only in clean 2788->2830 / clean-changed 168->126).
- sha256 cmp-norepro-2/summary.txt 753fd329d32c77ac3f5381c8191c47dd002c7121e943bc810076e35aae6fbb0c ; venue_changes.txt 75398f48ce48a9b5ec2d68f9006e54eba1668f29320272528c3c9f3dd2f14863

## Self-review / concerns
Diff is minimal. Concern: "newly-held=183" in outcomes is large but unchanged versus the prior comparison (not from this change); I did not investigate it. predicted_list.json is measurement only.
