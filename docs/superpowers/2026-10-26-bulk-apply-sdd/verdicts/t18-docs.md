# Task 18 docs handback
Commit: see `git log -1` (docs: bulk-apply campaign in CLAUDE.md, runbook caveats, recorded Checkpoint A/B rulings). Suite: `./.venv/bin/python -m pytest -q` -> 6350 passed, 1 skipped, 8 deselected.

## CLAUDE.md stale text removed/rewritten
- deliver bullet: "A purged show re-delivers via `llama redo <name> --from package`, which re-downloads what is missing -- the deliver gate's 'audio files missing' refusal already points there; so does any fix/triage edit of a delivered show ... a full re-download where it used to be an in-place retag." Rewritten to strict station reuse (stale: delivered re-package now copies from the station copy and refuses rather than downloads; --allow-download is the escape).
- deliver bullet: "so a purged show is not sent to re-download only to be refused anyway" -> "re-package".
- reapply bullet: "re-processes HELD shows" -> every state.
- piece-4 bullet: "reapply's path extended ... (spec 5.2) is NOT built and belongs to the bulk-apply plan" -> now BUILT; "The bulk apply of pieces 1-5 is planned separately" -> points at the bulk_apply.py campaign (Commands).
- rekey_overrides bullet: added that --restore is retired once the bulk apply writes.
## CLAUDE.md additions
deliver awaiting-fix refusal/hints/`--fixed`/`--replace-voiced` equal-copy refusal; `clear-mark`; `status --awaiting-fix`; reapply bulk-apply additions (outcomes, --with-gather-llm, --seven-day-ceiling, --stop-at-points, snapshot); `scripts/bulk_apply.py` bullet (all 15 subcommands, flags verified with --help, gate exit 2, CAMPAIGN_MIN_VERSION 2.20.0, backfill bases, five marking reasons, refusals of unmounted/empty root, rekey refusal string); Bulk-apply open gaps bullet; Architecture bullets for `overrules` and for `awaiting_fix`/`campaign.json`/`reuse-anchor.json`/emcee awaiting-fix state.
## Runbook (plan Appendix A/B)
Step 3 --rehold-verdicts + null-subject caveat; step 6 no-station-copy / unverified / not-delivered caveats; step 7 resume-line --stop-at-points, `not contiguous`, "(none)", unmounted refusal; Appendix B marking-before-backfill order and latest-batch-only.
## Spec
Two "Recorded at Checkpoint A/B" blocks with measured numbers. 
## Code
scripts/bulk_apply.py module docstring only (lists, wave-check, spot-check, revoice-list, trial-report).
## Notes
Not independently verified beyond reading cli.py/help: the claim that `clear-mark` refuses while emcee runs (cli.py comment at _clear_mark_one) and that `redo --from select` of a delivered show is non-strict (cli.py `strict = delivered and from_stage != "select" and not allow_download`).
