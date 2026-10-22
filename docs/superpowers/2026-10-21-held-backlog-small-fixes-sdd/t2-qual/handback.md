# t2-qual: CODE-QUALITY review, Task 2 (slice B venue tie-break), 158619f..fcbddf0

### Spec Compliance (SPEC role)
N/A (code-quality lane). Nothing Critical seen out of lane. Binding checks: no flag added or removed (every `flags.append` is unchanged, and `mismatch` is still built from the vote before the chain); `venue_source` is untouched in all three tie arms; no new normalization (only `_stripped`); no operator note; `provenance.json`/candidate not mutated. Do-not-retune grep over the full diff (all names in global-constraints.md): **0 hits**.

### Strengths
- `venue_tie_break` (gather.py:955-969) is pure, small and sits beside `_stripped`. It counts raw strings with the same `Counter(r.venue for r in recs if r.venue)` expression grouping uses (grouping.py:37), so the tie definition cannot drift from the vote's.
- It is computed once (gather.py:1405) and applied in exactly the three arms the brief names (1421-1422 unflagged 1a, 1430-1433 step 1, 1451-1452 no event). The swap, signature, 1c, final else, flagged 1a, 1d and overrides are untouched. 1d and the tie-break cannot both fire: the tie needs a compatible-or-blank selected city, 1d a conflicting one.
- Concrete risk checked: the research place filter must keep the vote (spec). `show_metadata_norms` (gather.py:544) reads `candidate.venue/city`, not the shipped `venue`, so it is unaffected.
- Tests build candidates through `grouping._make_candidate`, so the tie under test is grouping's real tie. Each asserts `cand.venue` first to document the precondition, and each arm test asserts venue flags.
- **Mutation check (Task 8 preview), run in a scratch `git archive` copy with PYTHONPATH shadowing (verified `llama.__file__` in the copy), PYTHONDONTWRITEBYTECODE and `__pycache__` wiped per mutant. Baseline is green. All 12 of B1-B12 turn their named test red:** B1 (majority + unit + `test_1d_does_not_fire...`), B2, B3 (+unit), B4 (+unit), B5, B6 (+blank-city test), B7, B8, B9 (+B10's test), B10, B11 (the existing signature test), B12. B1 and B12 had to be adapted to the implementation's form (`n == 0 or n != ... or sel.venue == ...`): B1 drops the `n !=` clause, B12 drops `n == 0`. Task 8 should mutate those spellings, not the brief's literal `==` expression.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
1. gather.py:955: `sel` has no type annotation, though the brief's interface is `sel: RecordingSummary | None`. gather.py does not import `RecordingSummary`. Neighbours such as `jerrybase_city(event)` are also untyped, so this is consistent but weaker. Fix: import it and annotate.
2. gather.py:1426-1432: step 1's three-clause predicate (`venues_equivalent(x, ev) and (_venues_equivalent_pre1b(x, ev) or cities_compatible(archive_city, jb_city))`) is now written twice, once for the vote and once for `tie[0]`. A local `passes_step_1(v)` would keep the two from drifting. That is optional: the explicit copy is what Task 8's B9/B10 mutate, and it reads fine.
3. test_stage_gather.py:3037-3038: module-level imports mid-file (an E402 shape). No linter is configured, and the file otherwise imports at the top or inside functions. Fix: move the two imports to the file header.
4. test_stage_gather.py:3080: `(lambda s: (s.venue, s.city))(...)` is an odd idiom (brief-verbatim). `show = _gd(...).show; assert (show.venue, show.city) == ...` reads better.
5. `test_a_tie_whose_selected_city_is_incompatible_ships_the_vote_unchanged`: the two raw strings strip to the same venue, so only the city assertion can detect B2. It does catch B2 (verified). A selected string that differs visibly (e.g. "R.F.K. Stadium" against "RFK Stadium") would make the venue half meaningful too.
6. `test_step_1_tie_keeps_the_vote_when_jerrybase_does_not_corroborate...` depends on the vendored jerrybase CSV row for DSO 2003-01-25 (Barrymore Theater, Madison). That is the same dependency the existing `test_swap_ships...` tests already carry. It is informational only, but a monkeypatched event would make it self-contained.
7. CLAUDE.md:623: the new sentence is one ~600-char line, while the surrounding bullet is hard-wrapped at ~80 columns. Fix: re-wrap.
8. Informational: inside `compute_gather` the `n == 0` guard cannot be reached, because `sel` always comes from `candidate.recordings`, so a non-blank `sel.venue` has at least one vote. It protects direct callers only and is unit-pinned (B12). Fine as defensive code.

### Assessment
**Task quality:** Approved
**Reasoning:** A small, pure function wired into exactly the three spec'd arms, with no flag, source or do-not-retune changes. The tests are behavioural, and a scratch-copy mutation run shows all 12 planned Task 8 mutants (B1-B12) are killed by their named tests. Remaining items are style or typing polish.
