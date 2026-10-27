# Task 18 (docs part): CLAUDE.md, the runbook, the spec's recorded rulings

**Implementer: Sonnet** (docs only — no code change except the `scripts/bulk_apply.py` module docstring). The orchestrator runs the acceptance and the whole-branch review afterwards.
**Files:** Modify `CLAUDE.md` (repo root of the worktree), `docs/superpowers/plans/2026-10-26-bulk-apply.md` (Appendix A and B only), `docs/superpowers/specs/2026-10-25-bulk-apply-design.md` (two "Recorded at" blocks only), `scripts/bulk_apply.py` (module docstring only).

Read first: the plan's Task 18, Open gaps, Appendix A, Appendix B (`docs/superpowers/plans/2026-10-26-bulk-apply.md`); the spec sections "The `awaiting_fix` contract", "The library side", "Overrules persist", "Re-processing", "Delivery after the fix", "Undo"; then CLAUDE.md's Commands section (the `llama deliver`, `llama fix`/`redo` "one unit", `llama reapply`, `emcee run`/`emcee status` bullets) and Architecture section (`overrides.json` bullet, the piece-4 "Junk short-keep" bullet's "reapply's path extended to packaged and delivered shows (spec 5.2) is NOT built and belongs to the bulk-apply plan" sentence). Verify every command, flag and string you write against the code (`./.venv/bin/python scripts/bulk_apply.py <sub> --help`, `./.venv/bin/python -m llama.cli <cmd> --help` or grep `packages/llama/src/llama/cli.py`, `packages/emcee/src/emcee/cli.py`), never from memory. The fixed strings are in the plan's Contracts section; copy them exactly.

CLAUDE.md's style: dense prose bullets, exact command lines and fixed strings in backticks, spec/plan paths cited, measured numbers with their dates. Edit in place; do not reorganise unrelated text. It is already ~117 KB: be complete but terse.

## 1. CLAUDE.md (plan Task 18 Step 1, plus the run's pointers)

Add or correct, each where it belongs:
- **Architecture:** the `awaiting_fix` contract (station-manifest top-level `awaiting_fix {reason, marked_at}`, written only by `llama/station_mark.py`; llama's `Manifest` model has no such field) and `<show>/campaign.json` (marks / processed / clears; "awaiting fix" definition; unreadable = awaiting) and `<show>/reuse-anchor.json`. emcee's `awaiting-fix` state (status reason, `skip … awaiting fix from llama`, voice/run refusal; malformed mark); transmitter: a manifest with a non-null `awaiting_fix` is not airable (already stated — keep consistent).
- **`overrides.json` bullet:** `overrules` (Contracts shape plus the optional `note`; flag kinds via `overrules.flag_key`; scoped to `identifier`; the `overruled: <flag>` note; `fix`/triage/`--untitled` record them; `source: backfill`).
- **Strict station reuse** replaces the stale text in the `llama deliver` bullet that a purged show "re-delivers via `llama redo <name> --from package`, which re-downloads what is missing" and that `fix`/`triage` edits of a delivered show do "a full re-download": for a delivered show the re-package now copies audio from the station copy (pairing by index + title + `source.identifier`, length-checked) and REFUSES (`station copy does not pair` / `station copy unreadable` + the hint) rather than download; `--allow-download` (by name only, on `reapply`/`redo`/`fix`) is the escape; a newly kept file the station never held downloads alone (`audio reused N, downloaded 1`).
- **`reapply` for every state** (held, packaged, briefed, delivered): replaces "re-processes HELD shows" and the piece-4 sentence quoted above (now built); new outcomes `label-only`, `unchanged`, `skipped: processed`, `skipped: re-selection (…)`; `--with-gather-llm`, `--seven-day-ceiling`, `--stop-at-points` (list form only), the per-batch snapshot `<root>/reapply/<hash>/snapshot/`, `--allow-download` by name.
- **New/changed commands:** `llama clear-mark <slug> [--accept-change]` (`mark cleared; the voicing is kept`), `llama deliver --fixed` (and the awaiting-fix refusal + re-process hint, batch suffix `  (refused: awaiting fix)`, the `--replace-voiced` equal-copy refusal naming `clear-mark`), `llama status --awaiting-fix`, emcee `status --state awaiting-fix`.
- **`scripts/bulk_apply.py`** (Commands): one bullet listing every subcommand (`pin`, `arm`, `snapshot`, `seal`, `restore`, `backfill [--rehold-verdicts DIR] [--apply]`, `freeze`, `reselect-check [--write]`, `mark [--apply]`, `unmark --batch DIR [--apply]`, `lists`, `wave-check`, `spot-check`, `revoice-list`, `trial-report`) with one clause each, the exit-2-on-a-gate rule, "run from the pinned worktree by path, never with its venv activated", `CAMPAIGN_MIN_VERSION = "2.20.0"`, and a pointer to the plan's Appendix A (runbook) and B (undo). Include the backfill's bases (today's rule; Checkpoint A rules a-d, each overrule's `note` naming its basis) and the marking reasons (five, with the new `newly held by today's checks: <kinds>`), and that `lists`/`mark`/`wave-check` refuse an unmounted or empty station root.
- **Open gaps** (plan "Open gaps", verbatim in substance) as a short list in the bulk-apply bullet.
- `rekey_overrides.py --restore` is retired once the bulk apply writes (the rekey refusal string).

## 2. The runbook (plan Appendix A and B) — operator caveats the run recorded

Add, in the step each belongs to (keep each to a sentence or two):
- Step 3 (backfill): pass `--rehold-verdicts ~/.llama-harness/t3/rehold-verdicts` (Checkpoint A rule b); the dry run can show a flag as listed that a recorded null-subject rule of the same kind will in fact overrule (identity is kind + subject; 0 such cases measured at Checkpoint A).
- Step 6 (mark): a recorded `no station copy` never clears within its batch — re-deliver the show, or accept it by hand; `marked by this batch, no verified before copy` never self-clears either (a hand decision); a slug whose last line is `not delivered` is not checked against the station.
- Step 7 (trial): after a trial stop the printed resume line repeats `--stop-at-points`; drop it once the trial is accepted. `trial-report`'s `not contiguous` means re-run as one block per kind. `--counts` JSON uses `"(none)"` for a show with no profile. `lists`/`--counts` refuse an unmounted station.
- Appendix B: reverse marking (`unmark`) BEFORE restoring the backfill snapshot; reverse only the latest marking batch, or re-derive with a fresh batch afterwards.

Change no command name; Appendix A's existing steps stay as written apart from these additions.

## 3. The spec's recorded rulings

The spec is the binding description; record the two operator rulings where they bind, as the repo does elsewhere ("Recorded at Checkpoint …" blocks):
- Under "Overrules persist" (its Backfill part): `**Recorded at Checkpoint A (operator, 2026-10-27):**` the backfill also records (a) on a verdict whose action kind is `fix`, every still-listed structure/closer/venue/city flag (kinds `jerrybase-set-count`, `jerrybase-closer`, `research-sets`, `sets-not-found`, `venue`, `city`), never `titles`/`research-song` or a flag ruled `research-wrong`/`research-right-show-wrong`; (b) a rehold-verdict `decision: overrule` (`~/.llama-harness/t3/rehold-verdicts/`) records every still-listed base flag except `titles` and those two rulings (parent ruling: it covers `research-song`); `escalate` stays listed; (c) a delivered show with no verdict records every base flag; (d) `overrule_if_reheld_on` entries the base arm did not raise are recorded; every recorded overrule carries a `note` naming its basis.
- Under "The `awaiting_fix` contract" → "Who gets marked": `**Recorded at Checkpoint B (operator, 2026-10-27):**` a fifth trigger — an arm row newly held with no visible change, not label-only and not processed, is marked last in priority with `newly held by today's checks: <flag kinds>` (88 packaged, 1 delivered at Checkpoint B2).

Measured numbers for the blocks (cite them): Checkpoint A2 at 3497e77e — 195 considered, 494 recorded (verdict 316, a 32, b 9, c 15, d 122), 21 listed, 187 of 195 fully covered; Checkpoint B2 at f1f447db — mark plan 2640 (2551 + 89).

## 4. `scripts/bulk_apply.py` module docstring
It lists subcommands only through Task 15; add `lists`, `wave-check`, `spot-check`, `revoice-list`, `trial-report` in the same style. No other code change.

## Checks before committing
- `grep -n "re-downloads what is missing\|full re-download\|NOT built and belongs to the bulk-apply plan\|re-processes HELD" CLAUDE.md` — each remaining hit is still true or rewritten.
- Every command line you added runs `--help` cleanly (`./.venv/bin/python scripts/bulk_apply.py <sub> --help`; llama via `./.venv/bin/python -m llama.cli <cmd> --help` if that entry point exists, else grep cli.py).
- `./.venv/bin/python -m pytest -q` from the worktree root still green (the docstring touch; and any test that reads CLAUDE.md).
- One commit `docs: bulk-apply campaign in CLAUDE.md, runbook caveats, recorded Checkpoint A/B rulings` with the trailer `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>` and the test command in the message.
