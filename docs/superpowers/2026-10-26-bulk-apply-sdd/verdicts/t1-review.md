# t1-review handback: Task 1 (Overrule records and flag normalisation), 3a2c1352..11a22de3

### Spec Compliance

- ✅ Spec compliant. Every Interfaces item and every brief step is present:
  - `models.Overrule` has the exact fields and defaults (models.py:208-218). `Overrides.overrules` is `Field(default_factory=list)` and comes right after `encore_after` (models.py:238). Both models are plain `BaseModel`, so they are permissive, as the Global Constraints require.
  - `overrules.py` has `NOTE_PREFIX = "overruled: "`, the `FlagKey` NamedTuple, `flag_key`, `rule_matches`, `split_overruled`, `records_for` and `merge_rules`, with the signatures the plan gives.
  - Its only imports are `llama.models` and `llama.structure.fold_curly_apostrophes`, with no replay and no stage. `structure.py` itself imports only `models` and `songs`, so there is no cycle when gather imports `overrules.py` later.
  - Contracts flag-kinds table, checked row by row against `_PATTERNS` (overrules.py:26-51) and `flag_key` (overrules.py:55-74):
    - Order: `research-song` → `research-date` (both forms) → `research-sets` → … → `briefing-song`/`-set` → `briefing-other` → `other`.
    - `research-date` takes D raw, as the contract's `[D]` says. Every other subject is `norm(...)`.
    - `jerrybase-closer` uses a greedy `'(.*)'`.
    - `briefing-other` is `re.sub(r"\d+","N",norm(flag))`.
    - `duration mismatch on ` gives None.
    - Matching (overrules.py:77-84) requires the same identifier and the same kind. Subjects must be equal, except `titles`, which matches when the new set is a subset of the recorded one.
  - Fixture provenance, checked independently: I recomputed the sorted unique `flags`, `gather_flags`, `vet_flags`, `brief_flags` and `stored_flags` over `shows` in both `~/.llama-harness/piece4/migration-{post,base}.json` (read only). That gives 2016 strings, equal to `arm_flags.json`. The sha256 is `3e29c306…cd64e4`, matching the commit message. The arm's extra `stored_core_flags` field adds no string outside the fixture (1582 strings, 0 new).
  - Kind distribution over the fixture:
    - research-song 1784, research-date 59, venue 55, single-set 51, jerrybase-closer 29, city 13, jerrybase-set-count 7, research-sets 6, briefing-other 3, `None` 2.
    - 1 each: briefing-set, low-confidence-setlist, alignment, no-tracks, sets-not-found, tape-spans, titles.
    - `other` 0.
  - Venue and closer names with an inner apostrophe split correctly ("Marvin's Mountaintop", "Lockn' Festival", "Lupo's Heartbreak Hotel", "Knockin' on Heaven's Door").
  - Every test the brief names is present (test_overrules.py), including both pins. The merged-tracks text matches the real raise site (gather.py:2003, `merged track(s) {nums} span a set break`). The `titles` subject predicate matches gather's raise predicate (gather.py:2145, `title_source == "unresolved"`).
  - Untouched names: I grepped the diff for every Global Constraints name (DURATION_TOLERANCE_S, STOP_AFTER_LLM_FAILURES, load_list, briefing_reusable, purge_package_audio, audio_reuse, the junk constants and rule functions, the piece-3 constants, `Manifest`, emcee, transmitter). There were 0 hits outside fixture strings. `Manifest` gains no field.
- ⚠️ Cannot verify from the diff:
  - (1) Commit trailer. The commit ends `Co-Authored-By: Claude Opus 5.5 (1M context)` with no `Claude-Session:` line. The Global Constraints say "the attribution trailer the orchestrating session specifies". The orchestrator should confirm this is the trailer it gave.
  - (2) A forward risk for the backfill and overrule tasks. `records_for` derives the `titles` subject from the `show` it is passed. The backfill records base-arm flags against a show that is "not held today". If it passes today's `show.json` (no unresolved tracks), it records `subject: []`, which matches no future non-empty set. That is safe (it holds) but inert. The backfill task must pass the track list the flag was raised on, or accept that titles overrules are not backfilled.

### Strengths

- The fixture test (`test_every_arm_flag_has_a_kind`) is an exhaustive check against real data rather than examples. Every one of the 2016 arm strings is classified, and none falls to `other`.
- `test_subjects` pins the normalisation pieces (curly-apostrophe fold, casefold, whitespace collapse via "Fixin’ to  Die"), the two-item venue and city subjects, raw `research-date`, digit folding for `briefing-other`, and the count-insensitive `single-set` key.
- Overrules are scoped to the identifier and never deleted, as the spec's design call requires. `merge_rules` dedupes within `new` as well (`seen.add`, overrules.py:124).
- The module is small and pure, with the import discipline the brief asks for.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. overrules.py:26-51 vs replay.py:153-167 — duplicate flag-text classification.
   - `replay._FAMILIES` already classifies the same flag prefixes, at coarser granularity. Now two tables can drift: a new flag text added to one and not the other. They already order `research-sets` and `research-date` differently, which is harmless today.
   - The brief forbids overrules importing replay. The reverse is possible later: replay's families could be derived from `flag_key` kinds. Not needed for this task.
2. test_overrules.py:97-110 — `merge_rules` is not tested with a rule that has the same kind and subject on a different identifier.
   - That rule must be kept, because records on another identifier coexist after a re-selection. The code keeps it (`_ident` includes `identifier`, overrules.py:113-114), but no test pins it.
   - The test also does not cover duplicates inside `new`.
3. overrules.py:80-81 — for `titles`, an empty key subject is a subset of any rule, so it matches.
   - This is unreachable from gather: the flag is only raised when at least one track is unresolved (gather.py:2145).
   - It is reachable if a caller passes a `show` inconsistent with the flags (see ⚠️ 2). A one-line comment would make that contract explicit.
4. models.py:221-224 — the `Overrides` docstring still lists only gather's and brief's existing reads.
   - It does not mention `overrules` (who writes it: fix, triage, untitled, backfill; who reads it: gather, vet, brief once wired).
   - "Hand-authored" is no longer quite true. Polish only.

Checks run:
- Recomputed the fixture from the arm files (above).
- Classified the full fixture with `flag_key` and inspected the subjects of the venue, city, closer and date flags.
- Read the flag raise sites: gather.py:2003, :2046, :2099, :2146; jerrybase.py:316; package.py:26 (`FLAG_PREFIX = "duration mismatch on "`, the only package-family prefix); brief.py:14 (`"briefing "`).
- Checked `structure.py`'s imports for a cycle.
- Searched for code iterating `Overrides` fields or `exclude_defaults`: none, so the new defaulted field cannot change other behaviour.
- `./.venv/bin/python -m pytest packages/llama/tests/test_overrules.py -q`: 8 passed in 2.41 s, no warnings.
- I did not re-run the full suite. No mutants were run: reading showed that each mutation of the matching logic (subset direction, identifier check, digit fold, curly fold, casefold, whitespace) is caught by a named assert.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation matches the Contracts table row for row. A fixture regenerated independently from the arm files classifies all 2016 real flags correctly. The minors are drift insurance, test-coverage gaps and a forward caution for the backfill task, not defects in this task.
