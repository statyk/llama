# Task 14b (parent-directed follow-up to Task 14): the backfill records Shawn's Checkpoint A rulings

**Spec:** "Overrules persist" (Backfill), "Undo", "Rollout". Strict surface 4 (an irreversible-ish batch write into every considered show's `overrides.json`; its undo is `bulk_apply.py restore` of the backfill snapshot). **Implementer: Opus.**
**Files:** Modify `scripts/bulk_apply.py` (backfill section: `_rulings`, `_plan_one`, `plan_backfill`, `_print_plan`, `_backfill_one`, `cmd_backfill`, the `backfill` argparse entry), `packages/llama/src/llama/models.py` (`Overrule.note`, below); Test `scripts/test_bulk_apply_backfill.py`.

Task 14 (commits da32e253, 884dd4ad) built `bulk_apply.py backfill --base <migration-base.json> --verdicts <dir> [--apply]`. Read `scripts/bulk_apply.py` from `# --- backfill` to the start of `# --- marking`, and `scripts/test_bulk_apply_backfill.py`, before anything else. Its rule (unchanged by this task and still applied first): per considered show (base row `outcome == "newly-held"`, base `state != "held"`, not held today), each base flag (`gather_flags + vet_flags + brief_flags`) is recorded when its verdict is the layout's false-hold value (`flags[].verdict == "spurious"`, `claims[].verdict == "flag-spurious"`) or `action.overrule_if_reheld_on` names it; otherwise it is listed with a reason (`verdict never ruled on this flag`, `ruled <verdict>`, `only in other_flags (free text)`, `not overrulable (package flag)`, `cannot derive the unresolved files`), and a show with no verdict file is listed show-level (`no verdict`).

At Checkpoint A (dry run: 195 considered, 15 no verdict, 316 recorded, 62 listed; report `.superpowers/sdd/bulk-apply/orch-r1/checkpoint-a.md`) the operator ruled that the backfill ALSO records four more classes. Each is pinned by a test shown RED in the live tree before implementing.

## The four new bases (applied after today's rule, to flags today's rule did not record)

**Definitions.**
- A flag is **still listed** when today's rule lists it with reason `verdict never ruled on this flag` or `only in other_flags (free text)`. A flag listed `ruled <anything>`, `not overrulable (package flag)` or `cannot derive the unresolved files` is never recorded by rules (a) or (b).
- **The NEVER exclusions** (rules (a) and (b)): never a flag whose `flag_key` kind is `titles` (`unresolved track titles`) or `research-song` (`research asserts unknown song: …`), and never a flag any verdict entry ruled `research-wrong` or `research-right-show-wrong` (already guaranteed by "still listed", keep it explicit in code or a test).
- **The structure families** (rule (a)): `flag_key` kinds `jerrybase-set-count`, `jerrybase-closer`, `research-sets`, `sets-not-found`, `venue`, `city`. (`venue` includes the base flags today listed `only in other_flags (free text)`, e.g. `venue mismatch: archive 'Fuji Rock Festival - Field of Heaven' vs jerrybase 'Naeba Ski Resort'`.)

**(a) Verdict action `fix`.** When the show's verdict file has `action.kind == "fix"`, record every still-listed base flag whose kind is in the structure families. Shows whose action kind is anything else (`hold`, `overrule`, `untitled`, `narration-vague`, `rm`) gain nothing from (a).

**(b) Rehold verdicts.** New optional CLI input `--rehold-verdicts <dir>` (files `<dir>/<slug>.json`, shape `{"slug", "decision", "why"}`; the real directory is `~/.llama-harness/t3/rehold-verdicts/`, 34 files, `decision` is `overrule` or `escalate`). When given and the show's file has `decision == "overrule"`, record every still-listed base flag of the show, subject to the NEVER exclusions. `escalate` (or any other decision) records nothing. An unreadable or non-object rehold file refuses the whole plan (`LlamaError`, nothing planned), exactly as an unreadable verdict file does today. Without `--rehold-verdicts`, (b) does nothing.

**(c) Delivered, no verdict.** A considered show with NO verdict file whose derived state today is `delivered` (`derive_state(ws, delivered)[0] == "delivered"`) records every base flag: `titles` through the existing `_titles_rule` (base row `title_sources`; listed `cannot derive the unresolved files` when it returns None), a package flag (`flag_key` None) still listed `not overrulable (package flag)`. The NEVER exclusions do NOT apply to (c) (the operator delivered these shows, i.e. accepted every flag). A no-verdict show in any other state keeps today's show-level `no verdict`.

**(d) `overrule_if_reheld_on` flags the base arm did not raise.** For a considered show with a verdict, each flag text in `action.overrule_if_reheld_on` that is NOT among the base flags is recorded too (`records_for`; a `titles` one via `_titles_rule`, skipped when it returns None; a `flag_key`-None one skipped). Every other verdict ruling on a flag the base arm did not raise stays as today: neither recorded nor listed. Cross-check reference only (do not read it in code): `~/.llama-harness/bulk/backfill-not-in-base.json` (`{slug: [flag, …]}`, 174 pairs over 36 shows, mixing spurious rulings and `overrule_if_reheld_on` entries).

Precedence: today's rule, then (a), then (b), then (c); a flag is recorded once, under the first basis that records it. (d) adds flags outside the base list, so it never collides with the others.

## Every recorded overrule names its basis

Add `note: str | None = None` to `llama.models.Overrule` (a defaulted, permissive persisted field: old files read as `None`; `overrules._ident` and `merge_rules` ignore it, so a rule that differs only by note is "already present"). Every overrule the backfill records carries one of these exact notes (`<path>` is the path the CLI was given, joined with `<slug>.json`; for (c) the `--base` path):
- today's rule: `backfill verdict: <verdicts>/<slug>.json`
- (a): `backfill rule a (verdict action fix): <verdicts>/<slug>.json`
- (b): `backfill rule b (rehold overrule): <rehold-verdicts>/<slug>.json`
- (c): `backfill rule c (delivered, no verdict): <base>`
- (d): `backfill rule d (overrule_if_reheld_on, not raised by the base arm): <verdicts>/<slug>.json`

`fix`/`triage`/`untitled` keep writing overrules with `note` None. If serialising `note: null` into `overrides.json` moves any existing test expectation, do the Global Constraints dry run first: list each such test with its reason in your report, then edit. Prefer a serialisation that leaves a `None` note out of the written JSON if the existing writers already have a natural way to do that; if not, `"note": null` is acceptable — say which you chose.

## Output

- Dry run: per show, today's `  record: <flag>` lines stay byte-identical for today's-rule records; a record from a new basis prints `  record: <flag> (rule a)` / `(rule b)` / `(rule c)` / `(rule d)`. `list:` lines unchanged. A rule-(c) show prints as a per-flag show (`<slug>:` then its lines), not as `<slug>: no verdict`.
- Totals line: today's fields, where `shows with no verdict` still counts every considered show with no verdict file (rule-(c) shows included), and `shows fully covered N of M` counts over every show planned per flag (rule-(c) shows join M). Then one extra line: `recorded by basis: verdict N, rule a N, rule b N, rule c N, rule d N`.
- `--apply`: unchanged gates and order (pin, tools, snapshot of the shows with records, `retire_rekey_restore`, per show under `show_unit`: re-plan WITH THE SAME INPUTS (including `--rehold-verdicts`), re-read and refuse a legacy `overrides.json`, `merge_rules`, `write_artifact`, `record_after`, `record.jsonl`). The `record.jsonl` `added` entries carry the note (via `model_dump`). A re-run adds nothing already present (note ignored for identity).
- `plan_backfill(root, base, verdicts, delivered, rehold: Path | None = None)`; `_plan_one` takes the same extra input. `BackfillShow` keeps its four fields.

## Tests (names fixed; each RED in the live tree before implementing; fixtures inline as Task 14's are)

- `test_rule_a_records_structure_families_on_fix_verdicts` — on a verdict with `action.kind == "fix"`: a never-ruled `structure has 2 sets but jerrybase shows 1`, `jerrybase set closer 'X' is not at a set break`, `research asserts 3 sets but structure has 2`, `setlist evidence shows multiple sets but alignment found none`, a `recordings of this date disagree on city: …` and an `only in other_flags` `venue mismatch: …` are all recorded with the rule-a note; the same flags on a verdict with `action.kind == "hold"` stay listed with today's reasons.
- `test_rule_a_and_b_never_record_titles_unknown_song_or_research_rulings` — on a `fix` verdict that also has a rehold `overrule`: never-ruled `unresolved track titles` and `research asserts unknown song: S` stay listed `verdict never ruled on this flag`; a flag ruled `research-wrong` and one ruled `research-right-show-wrong` stay listed `ruled …`.
- `test_rule_b_rehold_overrule_records_still_listed_flags` — `decision: overrule` records a never-ruled `low-confidence structure alignment` (not a structure family: proves (b) is broader than (a)) with the rule-b note; `decision: escalate` records nothing; without `--rehold-verdicts` nothing from (b); an unreadable rehold file refuses the plan.
- `test_rule_c_delivered_no_verdict_records_every_base_flag` — a delivered no-verdict show records `unresolved track titles` (subject from the base `title_sources`), a `research asserts unknown song: S` and a `recordings … disagree on city` flag with the rule-c note; a package flag stays listed `not overrulable (package flag)`; a packaged no-verdict show still prints `<slug>: no verdict`.
- `test_rule_d_records_reheld_flags_not_raised_by_the_base` — a verdict's `overrule_if_reheld_on` naming a flag absent from the base row is recorded with the rule-d note; a `flags[]` `spurious` ruling on another non-base flag is neither recorded nor listed.
- `test_every_backfill_overrule_names_its_basis` — after `--apply` on a fixture covering all five bases, every overrule in `overrides.json` and every `record.jsonl` `added` entry carries its exact note; a second `--apply` writes nothing (`nothing to record…`), including when a pre-existing identical rule has a different or null note.
- `test_dry_run_prints_bases_and_totals` — the `(rule x)` suffixes, unchanged today's-rule lines, and the exact `recorded by basis:` line.

Keep Task 14's existing tests green; any whose expectation must move is listed in your report with its reason before editing.

## Constraints

- Never write under `~/.llama`, `~/.llama-harness` or `/Volumes/media/lma-radio/delivered/`; tests use tmp dirs only. Do not run the real backfill (the orchestrator runs the read-only Checkpoint A2 dry run afterwards).
- Stub `station_mark.emcee_running()` / `ps` in any test that reaches it.
- Global Constraints' Untouched list holds; `flag_key`, `records_for`, `merge_rules` semantics unchanged except that `note` is ignored for identity.
- Full suite green after: `./.venv/bin/python -m pytest -q` from the worktree root (baseline at 09742a80: 6330 passed, 1 skipped, 8 deselected).
- Commit `feat(bulk): backfill records the Checkpoint A rulings (structure flags on fix verdicts, rehold overrules, delivered no-verdict shows, reheld flags)` with the trailer `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>` and the test command in the message.

## SUPERSEDED (T14c, parent ruling 2026-10-27, commit 3497e77e)
Rule (b) no longer excludes `research-song`: a rehold `overrule` records never-ruled unknown-song flags; it still never records `titles` or a flag ruled research-wrong / research-right-show-wrong. Do not "fix" (b) back to this brief's NEVER list.
