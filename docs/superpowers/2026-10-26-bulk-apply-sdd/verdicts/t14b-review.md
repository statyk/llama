# Task 14b review (t14b-review), reviewer on Opus

### Spec Compliance
- ✅ Spec compliant. Every requirement in the brief is met in commit 4a27c6c6:
  - "Still listed" means only `NEVER_RULED` / `OTHER_ONLY` (`_STILL_LISTED`, bulk_apply.py diff l.59; `eligible`, diff l.243-244).
  - The NEVER exclusions are explicit: kinds via `_NEVER_KINDS`, rulings via `_NEVER_RULINGS` (diff l.60-61, l.243-244). The ruling check is redundant with "still listed", which is what the brief asked for.
  - Rule (a): `action.kind == "fix"` and kind in the six structure families (diff l.214, l.245).
  - Rule (b): `decision == "overrule"`, `escalate` records nothing, and nothing is recorded without `--rehold-verdicts` (diff l.186, l.215, l.247). An unreadable or non-object rehold file raises `LlamaError` through the same reader as the verdicts (diff l.92-103). The CLI checks the directory (diff l.379-380).
  - Rule (c): no verdict file and state `delivered`. It records every base flag with no exclusions; titles go through `_titles_rule`, and a None result is listed `cannot derive the unresolved files`. Package flags are listed. A no-verdict show in any other state keeps `no verdict` (diff l.199-210).
  - Rule (d): `overrule_if_reheld_on` texts not in the base flags are recorded in the verdict's order (`named` is now an ordered list, diff l.120). A titles flag goes through `_titles_rule` and is skipped on None; a `flag_key`-None flag is skipped (diff l.253-261).
  - Precedence: today's rule, then (a), then (b) on the verdict branch; (c) runs only on the no-verdict branch.
  - All five notes are exact, with `<path>/<slug>.json` built from the CLI path and `--base` for (c) (diff l.65-69).
  - `Overrule.note: str | None = None` (models.py diff l.29-31). `_ident`/`merge_rules` use (identifier, kind, subject) only, so the note never affects identity. I checked this in overrules.py:114-126, and also that `records_for` returns exactly one rule for a non-None key, which makes `[rule] = records_for(...)` at diff l.151 safe (overrules.py:101-111).
  - Dry run: today's-rule lines have no suffix; other bases print `(rule x)`. A rule-(c) show prints per flag. `shows with no verdict` counts rule-(c) shows, `fully covered … of M` counts every per-flag show, and the `recorded by basis:` line is in the brief's order (diff l.299-323).
  - `--apply` re-plans inside `show_unit` with the same inputs, `args.rehold_verdicts` and `args.base` included (diff l.357, l.411). `record.jsonl` `added` carries the note (pinned by the test at diff l.736-739).
  - All seven required tests exist under the fixed names.
- ⚠️ Cannot verify from the diff: whether the brief encodes Shawn's verbatim Checkpoint A rulings correctly. They are not in `orch-r1/ledger.md`, `orch-r2/ledger.md` or `checkpoint-a.md`; only the questions are. One point for the orchestrator to confirm with the parent: checkpoint-a.md List 1 tags 10 `research asserts unknown song` flags as rehold **overrule** (bandofheathens-2009-07-27 ×2, furthur-2011-02-11 ×4, geoffachisonandthesouldiggers-2003-05-28 ×3, and one more). The brief's NEVER exclusion keeps all of them listed, so those shows re-hold on them. If that is the ruling, the code is right. My read-only reconstruction gives about 30 flags still listed after (a)/(b), all of them titles, research-song or `ruled research-*`.
- Deviation, which I accept: `plan_backfill`/`_plan_one`/`_backfill_one` gained a keyword-only `base_path`, because the brief's fixed signature carries no path for rule (c)'s note. The CLI always passes it; the fallback text "the base arm" only reaches direct callers (diff l.203). This is backward compatible and justified.

### Strengths
- Small and well structured. A single `take()` closure replaces the duplicated titles/records_for branch. The explicit `continue` after today's rule makes the precedence obvious, and the basis is recoverable from the note, so `BackfillShow` keeps its four fields as required.
- The rehold read sits before the verdict branch (diff l.186), so a broken rehold file refuses the plan for any considered show. That is the same fail-loud stance as verdicts.
- The tests are discriminating:
  - The NEVER test runs a `fix` verdict together with a rehold `overrule`. Without `_NEVER_KINDS`, rule (b) would record both the titles flag (its `title_sources` maps to a real unresolved file) and the unknown-song flag, so the exclusion is genuinely pinned.
  - Rule b uses a non-structure flag on a fix verdict, so only (b) can record it.
  - The re-apply test covers both a null note and a different note on an identical rule, and asserts the tree is byte-identical.
- Real-data cross-checks, read-only:
  - All 1063 verdicts have a dict `action` with `kind` in {fix 783, overrule 129, hold 125, untitled 18, narration-vague 4, rm 4}, so (a)'s key is right.
  - The 34 rehold files are 32 `overrule` and 2 `escalate`. Every one is an object, each `slug` matches its filename, and every one has a verdict file. So there is no rehold show that rule (b) silently cannot reach because it has no verdict.
- Untouched list: the diff touches only the `Overrule` model, the backfill section of `bulk_apply.py`, and its test file. No junk constants, `DURATION_TOLERANCE_S`, `audio_reuse`, purge, piece-3 constants, `STOP_AFTER_LLM_FAILURES`, `load_list` or `briefing_reusable` appear.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The dry run can list a flag that a recorded rule actually overrules** (bulk_apply.py diff l.243-261, `_print_plan` l.301-302). Identity is (kind, subject), and several kinds carry `subject: None` (`jerrybase-set-count`, `research-sets`, `sets-not-found`, `alignment`, …). Take a (d) record of `structure has 3 sets but jerrybase shows 2` on a show whose base flag `structure has 2 sets but jerrybase shows 1` is listed `verdict never ruled on this flag`. Gather's `split_overruled` (overrules.py:88-99) would overrule the listed flag, while the dry run tells the operator it re-holds. (d) widens this: by definition its texts differ from the base texts. The underlying property is Task 1's identity design and already applied to today's rule.
   - Measured: for every listed flag in checkpoint-a.md against its verdict's `overrule_if_reheld_on`, there are 0 same-identity overlaps, and none on the four `ruled research-wrong` shows. So it is latent, not live.
   - Fix (optional): in `_plan_one`, after (d), move any listed flag whose `flag_key` matches a planned record (`rule_matches`) to a distinct listed reason such as `covered by a recorded rule of the same kind`. At minimum, record it as a Task 18 runbook caveat.
2. **The dry-run totals can overcount what `--apply` writes** (diff l.315, l.322). The planned `record` can hold two rules with one identity, for example a (d) text and a base text of a null-subject kind. `merge_rules` dedupes them at apply (overrules.py:118-126), but `flags recorded` and `recorded by basis` count both. This is cosmetic, since apply is correct. A fix is to dedupe `record` by `_ident` in `_plan_one`; first wins, which matches the precedence rule.
3. **Untested precedence between (a) and (b), and between today's rule and (a)/(b).** No test has a structure-family flag on a `fix` verdict together with a rehold `overrule`, which should carry the rule-a note. No test has a `spurious`-ruled structure flag on a `fix` verdict, which should carry the verdict note. Swapping the `if`/`elif` at diff l.245-248 changes only the persisted note text, and no test would go red. One parametrised case in `test_rule_a_records_structure_families_on_fix_verdicts` would pin it. Also untested: rule (c) on a titles flag whose `_titles_rule` returns None, which should be listed `cannot derive the unresolved files`.
4. **`_basis`** (diff l.155-157) uses `next()` with no default. A record with an unrecognised note would raise StopIteration; inside the `Counter(...)` generator at diff l.322 that becomes a bare `RuntimeError`. It is unreachable today, because every planned record carries a `_BASES` prefix. Passing `next(..., "unknown")` or raising `LlamaError` would make it robust.
5. **Index access into `_BASES`** (`_BASES[0][0]` … `_BASES[4][0]`, diff l.203, 233, 246, 248, 259) is positional and easy to mis-edit. Named constants (`NOTE_VERDICT`, `NOTE_A`, …), with `_BASES` built from them, would read better. This is a readability nit.
6. **`_print_plan` checks the filesystem at print time** (`(verdicts / f"{slug}.json").exists()`, diff l.309-311) to tell a rule-(c) show from a verdict show. It works, and the brief's frozen `BackfillShow` forced some workaround. A comment already explains it, but it is hidden I/O in a printer. Alternatively, derive it from the plan step and pass a set of rule-(c) slugs.
7. **`note: null` is now written into every fix/triage/untitled overrule.** The brief allows this, and the implementer said so. Note that the first `fix` after this release rewrites old overrules with an added `"note": null`. That is harmless, because no code compares `overrides.json` bytes across versions for overrules, which I checked by grepping for `overrules` equality uses in `packages/llama/src` and `scripts/` (none).

### Assessment
**Task quality:** Approved
**Reasoning:** All four bases, the NEVER exclusions, the basis notes, the dry-run output and the apply path match the brief, and the tests pin the dangerous exclusions. Real verdict and rehold data match the shapes the code reads. The remaining findings are dry-run reporting precision and test coverage, none of which changes what gets written or suppressed in today's data.
