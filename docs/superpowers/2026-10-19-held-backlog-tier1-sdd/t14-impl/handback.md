# t14-impl handback (Task 14: briefing guard 3a/3b/3c + reuse normalisation)

**Status: DONE**

## Commits (on held-backlog-tier1, BASE 1fe98b9)
- `cf98f15` refactor(brief): extract `_guard_prose`, the text `briefing_guard` scans (pure refactor; suite 3574 passed, 1 skipped, 8 deselected at that commit)
- `22f18d9` feat(brief): guard 3a empty sets, 3b narrow tolerant matching, 3c qualified set counts

## Tests
`./.venv/bin/python -m pytest -q` -> 3615 passed, 1 skipped, 8 deselected (from 3574; +41 new test cases). `llama.__file__` confirmed inside the worktree.

## What was built (packages/llama/src/llama/stages/brief.py)
- `_guard_prose(b)`: the exact prose `briefing_guard` scans (cautions still excluded). Used by `briefing_guard` and imported by scripts/replay_holds.py.
- 3a `normalize_briefing(b)`: deep copy with empty `per_set` entries removed; everything else equal; idempotent. `run_brief` applies it right after the narration stamp, before the guard and both writes. An empty `per_set` dict still yields "briefing has no per-set talking points".
- 3b `_BRIEF_STRUCTURE_PREFIX`, `_BRIEF_TRAILING`, `_BRIEF_PAREN`, `_BRIEF_SEGUE` (verbatim from the brief), `song_components`, `known_song` (exact first, then every component); `briefing_guard` builds `exact`/`components` exactly as specified.
- 3c `_SET_COUNT_CLAIM_3C`, `_NOT_SHOW_WIDE` (with the late-night comment), `_NEGATION_2`, `_NEGATION_4`, `_SCOPE_AFTER` (verbatim), `_claim_counts`. Full branch uses `_claim_counts`; vague branch keeps today's `_SET_COUNT_CLAIM`/`_ORDINAL_SET` finditer verbatim (moved inside the branch). The two old regexes are byte-identical.
- Small addition: `_claim_counts` is computed over `_claim_matches(prose) -> (count matches, ordinal matches)` that survive 3c, so the compare report can say which spans 3c drops without re-implementing it. Spans equal today's regexes' (the 3c pattern only adds a capture group).

## Replay call sites changed (packages/llama/src/llama/replay.py)
- New `_read_briefing(ws)` = `normalize_briefing(read_model(ws.briefing_json, Briefing))`: the ONE read of a stored briefing in replay.
  - `compute_legs`: `stored_briefing = _read_briefing(ws)` -> this single normalised object feeds `briefing_reusable(...)`, the `brief_flags = briefing_guard(stored_briefing, replayed)` path, and `Legs.briefing` (so reapply will write the normalised form).
  - `replay_show`: `stored_brief_guard = briefing_guard(_read_briefing(ws), stored)`.
- `briefing_reusable`: `briefing_guard(normalize_briefing(briefing), new_show)` — it is public and its test passes a raw briefing, so it normalises its own argument (idempotent when called from compute_legs).
- So: one loader for all stored reads + the public function's own guard; no hand-copied normalise at the brief_flags or Legs.briefing sites.

## compare (scripts/replay_holds.py)
- `_suppressed_claims(root)`: over `root/shows/*/briefing.json` with a sibling `show.json` (unreadable briefings skipped, vague briefings skipped), every `_SET_COUNT_CLAIM`/`_ORDINAL_SET` match over `_guard_prose(b)` whose span is not in `_claim_matches`: row `  <slug>  '<match>'  ...<60 chars either side, whitespace-collapsed>...`. Header `suppressed set-count/ordinal matches: N` heads the section; appended to briefings.txt after the existing sections. Root is the cand arm's `root` (falls back to base's). Read-only (`read_model` only).
- summary.txt's briefings line now also says `N suppressed set-count/ordinal match(es)`.

## Tests added
- test_stage_brief.py: the brief's tests verbatim (+ the `("Drums > Nope", ["Drums"], False)` row; imports `pytest`, `normalize_song`, `read_model` added), plus `test_3a_normalize_leaves_everything_else_byte_identical` and `test_3b_3c_wired_into_the_full_branch`.
- test_replay.py: the brief's `test_briefing_reusable_normalises_empty_sets_before_the_guard`, plus `test_compute_legs_reuses_and_stores_the_normalised_briefing` (Legs.briefing + brief_flags) and `test_stored_brief_guard_runs_on_the_normalised_briefing`.
- scripts/test_replay_holds.py: the brief's compare test, plus `test_suppressed_claims_lists_only_what_3c_drops_with_bounded_context` (kept claim not listed, cautions not scanned, vague skipped, exact 60-char context, missing shows dir -> 0). Fixture library only, never ~/.llama.

## Mutation table (MROOT=$TMPDIR/mut-t14-impl-XXXXXX, one rsync copy per mutant, PYTHONPATH shadowing + private PYTHONPYCACHEPREFIX, shadowing proven per mutant, apply-count==1 checked; MROOT removed)
Files run: test_stage_brief.py, test_replay.py, scripts/test_replay_holds.py.

| mutant | predicted test | caught by |
|---|---|---|
| (a) known_song all->any | test_3b_tolerant_matching_narrowly[Drums > Nope-titles12-False] | predicted (only) |
| (b) drop 2-word negation window | test_3c_set_count_claims[there is no second set], [not three sets but two] | predicted (+ wired test, suppressed-claims test) |
| (c) vague branch uses _claim_counts | test_3c_leaves_the_vague_branch_on_todays_regexes | predicted (only) |
| (d) 3C word widened to [\w-]+ | test_3c_set_count_claims[two hard-hitting sets] | predicted (only) |
| (e) normalize_briefing drops len(v)<=1 sets too | test_3a_empty_sets_are_dropped_and_the_guard_never_sees_them | predicted (+23 others) |
| (f) briefing_reusable not normalising | test_briefing_reusable_normalises_empty_sets_before_the_guard | predicted (only) |
| (g) _read_briefing not normalising | test_compute_legs_reuses_and_stores_the_normalised_briefing, test_stored_brief_guard_runs_on_the_normalised_briefing | both predicted (only) |
| (h) run_brief normalise removed | test_run_brief_normalises_before_the_guard_and_the_writes | predicted (only) |
| (i) scope check removed | test_3c_set_count_claims[two sets a night] | predicted (+ each night, per weekend rows) |
| (j) 4-word negation removed | test_3c_set_count_claims[expected two sets] | predicted (+ instead of, without rows) |
| (k) denylist check removed | test_3c_set_count_claims[two electric sets tonight] | predicted (+ night/weekend rows, wired, compare test) |
| (m) report lists kept matches too | test_suppressed_claims_lists_only_what_3c_drops_with_bounded_context | predicted (only) |
| (n) _guard_prose includes cautions | test_suppressed_claims_lists_only_what_3c_drops_with_bounded_context | predicted (only) |

No survivors. (A first driver pass falsely aborted every mutant on the shadowing check because `$TMPDIR` ends in `/`, giving `T//` vs Python's normalised path; the path was in fact inside the copy. Fixed by normalising MROOT and re-running everything fresh.)

## Deviations / notes
- Added `_claim_matches` (span-level) under `_claim_counts`; `_claim_counts`'s signature/behaviour are as specified. Mutants (b),(k) still sit in the same logic.
- Do-not-retune: structure.py, songs.py not in the diff; `_SET_COUNT_CLAIM`/`_ORDINAL_SET` definitions byte-identical.
- briefings.txt gains the section at its end; summary.txt's briefings line gains a count (no existing test asserted that line's exact text).

---

# Fix round 1

**Status: DONE.** Commit `b9ae699` fix(brief): 3c negation windows stay inside the claim's own clause and field.

## Changes
1. **Clause-local negation (IMPORTANT).**
   - `brief._words_before` now looks back only to the last `_CLAUSE_BREAK = re.compile(r"[.!?;:,\n]")` before the match. Only the 2-word and 4-word negation windows use it.
   - `_SCOPE_AFTER` and the `_NOT_SHOW_WIDE` group-2 check are unchanged.
   - **Deviation: the comma is a break too.** The ruling listed `[.!?;:]`. But the probe "As expected, the second set was a monster." has only a comma between "expected" and the claim, so it can be KEPT only if the comma clips. This is the conservative direction: fewer suppressions.
   - **Field boundary.** `_guard_prose` now joins fields with `"\n"` instead of `" "`. This keeps the same length and today's `\s+` spans it, so spans are unchanged. `\n` is in `_CLAUSE_BREAK`.
   - **Proof that today's matches are unchanged.** The `test_guard_prose_field_marker_leaves_todays_matches_unchanged` test covers matches that span a field boundary. A read-only pass over `~/.llama/shows/*/briefing.json` compared old-join and newline-join: 2,455 briefings, 2,446 matches, 0 briefings whose `_SET_COUNT_CLAIM`/`_ORDINAL_SET` matches differ (same span, count word and words). So the vague branch is unchanged.
2. **No root, no read.** compare passes `None` when neither arm has a `root`. `_suppressed_claims(None)` then reports count 0 and never globs the cwd.
3. **Vague branch pins a negated ordinal.** Under vague narration, "there is no second set" still yields `briefing asserts set structure under vague narration`.

## Covering tests
- `test_stage_brief.py::test_3c_set_count_claims`, 3 new KEPT rows:
  - "The band did not disappoint. Second set opened hot." → (set(), {2: "second"})
  - "Fans could not complain: two sets and an encore." → ({2}, {})
  - "As expected, the second set was a monster." → (set(), {2: "second"})
  - All earlier rows stay green, including the same-clause negations: no, not, instead of, expected, without.
- `test_stage_brief.py::test_3c_negation_does_not_cross_a_briefing_field_boundary` (probe 4): a field ending "Probably not", then per_set "Second set: opened hot." The claim is kept and the guard flags "second set but structure has 1 sets".
- `test_stage_brief.py::test_guard_prose_field_marker_leaves_todays_matches_unchanged`
- `test_stage_brief.py::test_3c_leaves_the_vague_branch_on_todays_regexes`: adds the negated-ordinal assertion.
- `scripts/test_replay_holds.py::test_suppressed_claims_without_a_root_in_either_arm_reads_nothing`: both arms lose their root, and a library-shaped tree in cwd is not read.

## Commands and counts
- `./.venv/bin/python -m pytest packages/llama/tests/test_stage_brief.py packages/llama/tests/test_replay.py scripts/test_replay_holds.py -q` → 194 passed.
- `./.venv/bin/python -m pytest -q` → 3621 passed, 1 skipped, 8 deselected.

## Mutation table (r1)
- Each mutant ran in its own copy under a new normalised `MROOT=$TMPDIR/mut-t14-impl-r1-XXXXXX` (logged).
- Shadowing was proven per mutant and each mutant was checked to apply exactly once.
- The same three test files were run. `MROOT` was then removed by its exact path.

| mutant | predicted test | caught by |
|---|---|---|
| r1a remove clause clipping (`clause = prose[:start]`) | 3 new probe rows + test_3c_negation_does_not_cross_a_briefing_field_boundary | exactly those 4 |
| r1b field marker back to `" "` | test_3c_negation_does_not_cross_a_briefing_field_boundary | predicted (only) |
| r1c comma not a break | test_3c_set_count_claims[As expected, the second set was a monster.] | predicted (only) |
| r1d vague ordinals routed through 3c (`implied = _claim_counts(prose)[1]`) | test_3c_leaves_the_vague_branch_on_todays_regexes | predicted (only) |
| r1e compare root fallback back to `"."` | test_suppressed_claims_without_a_root_in_either_arm_reads_nothing | predicted (only) |

No survivors.

## Process note
I ran `git stash list` once while checking state. It is read-only and changed nothing, but the mandate says no `git stash` in any form, so I am recording it here.
