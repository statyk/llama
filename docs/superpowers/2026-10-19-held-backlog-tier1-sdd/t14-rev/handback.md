# t14-rev: Task 14 review (1fe98b9..22f18d9)

### Spec Compliance

- ✅ Spec compliant. Every Interfaces item in task-14-brief.md is present and verbatim:
  - `normalize_briefing` at brief.py:91 (diff 224-229). It deep-copies, drops only empty entries and keeps key order. `run_brief` applies it after the narration stamp and before the guard and both writes (brief.py:260; the writes at the end of `run_brief` use the reassigned variable).
  - The 3b regexes are verbatim (diff 198-201). `song_components` and `known_song` follow the brief: the exact test runs first, then the all-components test (diff 232-251). `briefing_guard` builds `exact` and `components` exactly as specified (diff 309-314).
  - The 3c constants are verbatim (diff 178-193), including the late-night comment. `_claim_counts` has the specified signature and behaviour. The full branch uses it (diff 345). The vague branch keeps today's `_SET_COUNT_CLAIM`/`_ORDINAL_SET` `finditer` computation unchanged; it was only moved inside the branch (diff 335-337).
  - Do-not-retune check: `_SET_COUNT_CLAIM`/`_ORDINAL_SET` appear only as unchanged context lines (diff 164-167). structure.py and songs.py are not in the diff (stat, diff 8-13), so `structure._STRUCTURE_PREFIX`, `normalize_song` and `DEFAULT_ALIASES` are unchanged.
- Rulings:
  - `_guard_prose` (brief.py:158; diff 291-301) is a pure refactor in its own commit cf98f15. Its field order is identical to the old inline join. Both `briefing_guard` (diff 327) and the compare section (diff 613) use it.
  - The single normalisation path is `replay._read_briefing` (diff 62-67). It feeds `compute_legs` (diff 108), which serves the reuse decision, `brief_flags` and `Legs.briefing`, and it feeds `stored_brief_guard` (diff 132). `briefing_reusable` also normalises its own argument (diff 55), as the brief requires; this is idempotent.
  - The row `("Drums > Nope", ["Drums"], False)` is present at test_stage_brief.py (diff 492).
- Superset invariant (3b) holds by construction: `known_song` returns True on today's exact test before anything else (brief.py `known_song`, diff 248-249). I confirmed it with a read-only probe over 8 awkward titles (`Dark Star (jam) →`, `(tuning)`, whitespace-only, `E: Casey Jones%`, and others): every one was known against its own track list. `""` does land in `components` when a title has no components, but it is inert, because `known_song` requires a non-empty `cs` and `song_components` drops empties.
- Deviations:
  - `_claim_matches` (diff 271-281) is a span-level helper under `_claim_counts`. It is sound: `_SET_COUNT_CLAIM_3C` only adds a capture group, so its `finditer` spans equal `_SET_COUNT_CLAIM`'s. That is what makes the compare section's span subtraction (diff 614-618) exact rather than a re-implementation. Accepted.
  - The summary.txt briefings line now also carries the suppressed count (diff 671-672). Grep: no code or test parses that line. scripts/test_replay_holds.py:341-343 asserts only `base reproduces`, `briefing guard reproduces` and `needs-LLM held` on summary.txt, and the plan (line 991) does not fix the text. Safe.
- ⚠️ Cannot verify from diff:
  - Spec 3a says that "on every reuse of a stored briefing" `briefing.md` is re-rendered from the normalised json. Here `Legs.briefing` carries the normalised model (verified, diff 108-112), but writing and re-rendering it is reapply's job (slice 6, a later task). The controller should check that reapply writes both `briefing.json` and `briefing.md` from `Legs.briefing`.
  - The spec's 3c acceptance item "re-count the suppressed matches against ≈68" is a Checkpoint D measurement, not checkable here.

### Strengths
- The span-subtraction design for the compare section reuses `_claim_matches` instead of re-implementing 3c. This keeps the report and the guard from drifting apart. Mutant (m) in the implementer's table covers it.
- The single `_read_briefing` loader means `stored_brief_guard`, the reuse decision, `brief_flags` and `Legs.briefing` cannot disagree on normalisation. Mutant (g) is caught by two named tests.
- The tests go beyond the brief:
  - `test_3a_normalize_leaves_everything_else_byte_identical` checks the copy, idempotence, and that an empty dict still yields the "no talking points" problem.
  - `test_3b_3c_wired_into_the_full_branch` covers end-to-end wiring.
  - `test_suppressed_claims_lists_only_what_3c_drops_with_bounded_context` checks exact 60-character context, that cautions are excluded, that vague briefings are skipped, and that a missing shows dir gives 0.
- The mutation table covers all five mutants the brief listed plus eight more. Each has a predicted test, and there are no survivors.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **Plan-mandated: the 3c negation windows cross sentence and field boundaries.** Location: brief.py `_words_before`/`_qualified` (diff 254-268). Because the window is built from the tokens of `prose[:m.start()]`, a real show-wide claim is suppressed whenever a negation word happens to end the previous sentence or the previous briefing field. Read-only probes against this HEAD:
   - `"The band did not disappoint. Second set opened hot."` gives `(set(), {})`; the ordinal is dropped.
   - `"Fans could not complain: two sets and an encore."` gives `(set(), {})`. This is the shape of the spec's own real-error case, moe-2002-06-22's "two sets and an encore" against 3.
   - `"As expected, the second set was a monster."` gives `(set(), {})`.
   - A field join: context `"…Probably not"`, significance `"s"`, per_set `"Second set: …"` gives `(set(), {})`. `_guard_prose` joins the fields with spaces, so the window spans fields.

   The implementer followed the brief exactly, which specifies tokens of `prose[:m.start()]`; the spec's wording is "the two words before the match". This is a loss of detection on the strict surface: a reused briefing ships as written. It is mitigated, not removed, by the Checkpoint D hand-read of every suppressed match with 60 characters of context.

   Human decision: either accept the behaviour and have the Checkpoint D pre-screen look specifically for a negation word in the previous sentence or field, or clip the window at `.!?:;` and at field joins. Clipping would be a change to a 3c constant or rule, which is fixed a priori, so it is the operator's call before the harness runs. It cannot be changed after.

#### Minor (Nice to Have)
1. brief.py:66 (`_BRIEF_TRAILING`, plan-verbatim) does not include `→`, although `_BRIEF_SEGUE` treats `→` as a segue. So `"Dark Star (jam) →"` keeps its parenthetical: `song_components` gives `['dark star jam']`, and a mention of "Dark Star" against that track stays unknown. This is the conservative direction (today's flag stands) and does not break the superset, but it is inconsistent with spec 3b's "trailing segue markers". If anyone changes it, it changes 3b's measured clears.
2. scripts/replay_holds.py:647 (diff 647) falls back to `"."` when neither arm records `root`. That would glob `./shows` in the caller's cwd. The cand-then-base fallback goes beyond the brief ("from the cand arm's root") and is harmless in practice, but `"."` should be a no-op instead.
3. scripts/replay_holds.py (diff 594-622): `_suppressed_claims` reads the live library at compare time, not at arm time, so a library edited between `run` and `compare` would make the section disagree with the arms. Unlike the other sections, it is not digest-gated. Acceptable for a read-only report; worth a line in the section header or the docstring.
4. scripts/replay_holds.py (diff 566-570): import tidiness. `from llama.models import Briefing` sits out of alphabetical order after `llama.replay`, and `llama.workspace` is imported on two separate lines (`read_model`, `ShowWorkspace`).
5. test_stage_brief.py (diff 534-538): the vague-branch test pins counts only ("two electric sets"). A partial mutant in which the vague branch keeps today's count regex but routes ordinals through 3c (for example, "no second set" under vague) would survive. One more assertion would close it.
6. test_stage_brief.py (diff 441-445): mid-file imports (`import pytest`, `normalize_song`, `read_model`) were appended under the slice-3 banner. These are plan-mandated placement. Cosmetic.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation is faithful to the brief and the rulings. It has the specified superset and vague-branch invariants, one normalisation path in replay, and a compare section that is exact by construction, with strong mutation-backed tests. The one substantive concern is that the 3c negation window crosses sentence and field boundaries. That is plan-mandated, so it goes to the operator for a decision before Checkpoint D, not back to the implementer.

Checks run (read-only):
- Probes: `_claim_counts` over 13 prose variants; `song_components`/`known_song` over 10 titles plus the superset property.
- Greps: call sites of `briefing_guard`/`normalize_briefing` (only replay.py and brief.py; all sites are normalised), and consumers of the summary.txt briefings line (none).
- `llama.__file__` resolves inside the worktree.

Suite not re-run (the implementer reports 3615 passed).
