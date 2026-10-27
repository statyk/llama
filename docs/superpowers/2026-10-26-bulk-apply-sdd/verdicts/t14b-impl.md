# Task 14b implementer report (t14b-impl)

**Status:** DONE_WITH_CONCERNS (one small signature addition, below)
**Commit:** 4a27c6c6 feat(bulk): backfill records the Checkpoint A rulings (structure flags on fix verdicts, rehold overrules, delivered no-verdict shows, reheld flags)
**Suite:** `./.venv/bin/python -m pytest -q` → 6337 passed, 1 skipped, 8 deselected (baseline 6330 + 7 new)

## What was implemented
- `llama.models.Overrule.note: str | None = None`. `overrules._ident`/`merge_rules` were already identity-by (identifier, kind, subject), so they ignore it with no change.
- `scripts/bulk_apply.py` backfill:
  - Today's rule unchanged and first; its records now carry `backfill verdict: <verdicts>/<slug>.json`.
  - (a) `action.kind == "fix"`: a still-listed flag (reason `verdict never ruled on this flag` / `only in other_flags (free text)`) whose kind is in `jerrybase-set-count, jerrybase-closer, research-sets, sets-not-found, venue, city` is recorded with the rule-a note.
  - (b) `--rehold-verdicts <dir>` (new CLI option, directory checked like `--verdicts`); `decision == "overrule"` records every remaining still-listed flag with the rule-b note. Unreadable or non-object rehold file → `LlamaError`, nothing planned (same reader as verdicts).
  - NEVER exclusions for (a) and (b) are explicit in code (`_NEVER_KINDS` titles/research-song, `_NEVER_RULINGS` research-wrong/research-right-show-wrong) beside the still-listed test.
  - (c) no verdict file and `derive_state(...)[0] == "delivered"`: every base flag recorded with the rule-c note (titles through `_titles_rule`, `cannot derive the unresolved files` on None; package flags listed `not overrulable (package flag)`); no NEVER exclusions. Other no-verdict shows keep `no verdict`.
  - (d) each `overrule_if_reheld_on` flag not in the base flags is recorded with the rule-d note (titles via `_titles_rule`, skipped on None; flag_key None skipped). `named` is now an ordered list so (d) records in the verdict's order.
  - Dry run: today's-rule lines byte-identical; other bases print ` (rule a|b|c|d)`; `shows with no verdict` counts rule-(c) shows too; `shows fully covered N of M` over every per-flag show; new line `recorded by basis: verdict N, rule a N, rule b N, rule c N, rule d N`.
  - `--apply`: same gates and order; `_backfill_one` re-plans with the same rehold dir and base path; `record.jsonl` `added` carries `note` via `model_dump`.

## Serialisation choice
`"note": null` is written for fix/triage/untitled overrules. `write_artifact` dumps whole models (it already writes `venue: null` etc.) and has no per-field exclude mechanism, so there was no natural way to omit it. No existing test pins the Overrule JSON shape (the full suite stayed green with no other edits).

## Deviation / concern
- **`plan_backfill(root, base, verdicts, delivered, rehold=None, *, base_path=None)`** (and `_plan_one`, `_backfill_one` take `base_path` too). The brief's fixed signature carries the base as a dict, so it has no path for rule (c)'s note `backfill rule c (delivered, no verdict): <base>`. I added a keyword-only `base_path`; `cmd_backfill` passes `args.base`. Direct callers that omit it get the note `backfill rule c (delivered, no verdict): the base arm`. The CLI never omits it.
- `_print_plan` takes `verdicts` as a third argument: `BackfillShow` keeps its four fields, so a rule-(c) show (show_reason None) is told apart from a per-flag show with a verdict by checking whether `<verdicts>/<slug>.json` exists, for the `shows with no verdict` count only.
- Rehold files are read for every considered show that reaches the verdict read (including no-verdict shows), so a broken rehold file refuses the plan wherever it sits.

## Existing test expectation moved (listed before editing)
- `test_no_verdict_lists_the_show`: totals moved from `splitlines()[-2]` to `[-3]`. Reason: brief "Output": "Then one extra line: `recorded by basis: …`", printed after the totals line and before `dry run: …`. The asserted totals text is unchanged.
- Fixture helpers `_verdict_a`/`_verdict_b` gained a defaulted `kind=` parameter (defaults keep the old values, so no existing test moves).

## TDD evidence
RED (live tree, each test run separately, before any production change):
- test_rule_a_records_structure_families_on_fix_verdicts: `AssertionError: assert [] == [('structure ...cts/fx.json')]` (nothing recorded yet)
- test_rule_a_and_b_never_record_titles_unknown_song_or_research_rulings: `TypeError: plan_backfill() takes 4 positional arguments but 5 were given`
- test_rule_b_rehold_overrule_records_still_listed_flags: same TypeError (no rehold input)
- test_rule_c_delivered_no_verdict_records_every_base_flag: `TypeError: ... unexpected keyword argument 'base_path'`
- test_rule_d_records_reheld_flags_not_raised_by_the_base: `AttributeError: 'Overrule' object has no attribute 'note'`
- test_every_backfill_overrule_names_its_basis / test_dry_run_prints_bases_and_totals: `SystemExit: 2` (argparse: unknown `--rehold-verdicts`)
GREEN: `./.venv/bin/python -m pytest scripts/test_bulk_apply_backfill.py packages/llama/tests/test_overrules.py -q` → 25 passed. Full suite above.

Coverage notes: rule a is shown on both layouts (B with `other_flags` venue on fix vs hold); the never test runs a fix verdict WITH a rehold overrule, so both (a) and (b) are tried against titles, unknown song and both research rulings (one of them on a structure-family `research-sets` flag); rule b uses `low-confidence structure alignment` on a fix verdict so only (b) can record it, plus escalate, no `--rehold-verdicts`, unreadable JSON and a non-object file; rule c checks titles subject from base `title_sources`, research-song, city, the package flag, and the CLI printing `pk: no verdict` vs `dl:`; rule d checks a structure flag, a titles flag via base positions, a skipped package flag, and a non-base spurious ruling neither recorded nor listed; the apply test checks every note in `overrides.json` and `record.jsonl`, then a second apply with one rule's note set to null and another's changed: `nothing to record`, tree byte-identical.

## Files changed
- packages/llama/src/llama/models.py
- scripts/bulk_apply.py
- scripts/test_bulk_apply_backfill.py

## Self-review
- Precedence: a flag goes down one branch only (today's → a → b → listed); (c) only for no-verdict shows; (d) skips any flag in the base list. A (d) flag sharing kind+subject with a base record (e.g. two `research-sets` texts) can be planned twice; `merge_rules` dedupes it at apply, the same as today's rule could already do.
- No real data touched; the real backfill was not run.

---

# T14c (parent ruling: rule b covers research-song)

**Status:** DONE
**Commit:** 3497e77e fix(bulk): rule b rehold overrules cover research-song flags (parent ruling) (on HEAD f1f447db)
**Suite:** `./.venv/bin/python -m pytest -q` → 6343 passed, 1 skipped, 8 deselected

## What changed
- `scripts/bulk_apply.py`: `_NEVER_KINDS` is split per rule. `_NEVER_KINDS_A = {titles, research-song}` is (a)'s set and has no effect beside `_STRUCTURE_KINDS`, but is kept explicit. `_NEVER_KINDS_B = {titles}`. `eligible` now carries only the still-listed and `_NEVER_RULINGS` checks, and each rule applies its own kinds. The comment above the constants was updated to give the ruling. Precedence is unchanged.
- New test `test_rule_b_covers_research_song_but_not_titles`:
  - On a rehold-`overrule` show, a never-ruled `research asserts unknown song: S` is recorded (research-song, subject `["s"]`, rule-b note), while `unresolved track titles` stays listed `verdict never ruled on this flag`.
  - On a `fix` verdict with no rehold file, both flags stay listed, so rule (a) still excludes songs.

## Existing expectation moved (stated before editing)
- `test_rule_a_and_b_never_record_titles_unknown_song_or_research_rulings`: `research asserts unknown song: S` moves from listed (`verdict never ruled on this flag`) to recorded with the rule-b note `backfill rule b (rehold overrule): <rehold>/nv.json`. Reason: the T14c ruling, since that show has a rehold `overrule`. Titles and the three ruled flags (research-wrong ×2, research-right-show-wrong) still stay listed. The test keeps its name, which the brief fixed. It now pins the titles and research-ruling exclusions for both rules, and the new test covers the song half.

## TDD evidence
- RED: `./.venv/bin/python -m pytest "scripts/test_bulk_apply_backfill.py::test_rule_b_covers_research_song_but_not_titles" "scripts/test_bulk_apply_backfill.py::test_rule_a_and_b_never_record_titles_unknown_song_or_research_rulings" -q` gave 2 failed:
  - new test: `ValueError: not enough values to unpack (expected 1, got 0)`, because no rule-b record existed;
  - moved test: `AssertionError: assert [] == [('research a...old/nv.json')]`.
- GREEN: `./.venv/bin/python -m pytest scripts/test_bulk_apply_backfill.py -q` → 18 passed. The full suite result is above.
