# fw2 — `llama reapply`: names-form structure-changed guard, failure type names, dry-run download count

Files: `packages/llama/src/llama/reapply.py` (`reapply_show`, `_PREDICTED`), `packages/llama/src/llama/cli.py` (`reapply` command names form ~3200-3240; `_reapply_list` ~3290-3370, its `fail` helper and the dry-run summary). Tests: `packages/llama/tests/test_reapply.py` (+ test_cli.py if the CLI tests live there; grep `reapply`).

## Items
1. **Final review I3.** In the names form (`row is None`), a show whose `classify` outcome is `structure-changed` is applied silently and printed `-> cleared`. Spec slice 6: a structure-changed show "joins the apply only once checked". Change: `reapply_show` gains a keyword `allow_structure_change: bool = False`. When `outcome == "structure-changed"`, not a dry run, and NOT allowed → return without writing anything a new outcome `"skipped: structure changed"` (add it to the `ReapplyOutcome.outcome` comment). Allowed when (a) the CLI names form is given a new flag `--allow-structure-change` (help: "apply a show whose replay changes its sets/segues/breaks; check `llama show <name>` first"), or (b) the list form's row has `row["outcome"] == "structure-changed"` (the structure_changed_list is a deliberate operator choice). A predicted_list row (outcome `clears`/`needs-brief`) whose replay now says `structure-changed` is skipped (not allowed). In the list form, record a `skipped: structure changed` row as finished with `retryable: false`? NO — record it `retryable: true` (the operator may later add the flag or move it to the structure list), and make sure a re-run does not loop forever on it (it is skipped again, printed again; that is fine). The names form prints `reapplied: <slug> -> skipped: structure changed (re-run with --allow-structure-change after checking)` and exits 0 for that show.
2. **Final review minor: FAILED lines name the exception type.** In `_reapply_list`'s last-resort `except Exception` arm and in the names form's catch, print `FAILED {slug}: {type(exc).__name__}: {exc}` (as `replay_show` does) — only for the catch-all arm in the list form (the typed arms keep today's text, since operators already read them); in the names form the typed arms are the only arms — leave their text alone too. If a `progress.jsonl` `outcome` string is built from the same text, keep it consistent with what is printed.
3. **Final review minor: dry-run download count.** The dry-run summary counts a download when `package/manifest.json` is absent; a delivered+held show has a manifest but purged audio, so it is undercounted. Count a row as a download when the show has no manifest OR any manifest track's file is missing from `package/audio/` (read the manifest's tracks the way `catalog.purge_package_audio` or the deliver gate does — reuse an existing helper if one exists rather than re-parsing).

## Tests (add)
- names form, a held show whose replay is structure-changed: without the flag → outcome `skipped: structure changed`, nothing written (byte snapshot like the existing `_snapshot`/`_stale` tests), CLI prints the hint; with `--allow-structure-change` → applied (`cleared`).
- list form: a structure_changed_list row (row outcome `structure-changed`) applies; a predicted row (`clears`) whose replay is now `structure-changed` is skipped and recorded `retryable: true`.
- catch-all arm prints `FAILED x: RuntimeError: boom` (monkeypatch something inside `reapply_show` to raise `RuntimeError("boom")`).
- dry-run: a held show with a manifest but an empty `package/audio/` counts as one download.

## Mutants
- M1: ignore `allow_structure_change` (always allow) → predicted: the names-form skip test.
- M2: allow every list row regardless of `row["outcome"]` → predicted: the predicted-row skip test.

## Constraints
Keep `classify`, `compute_legs` and the write order untouched. Do NOT add a general "skip when classify disagrees with row['outcome']" check (the final review's recommendation 4): a row whose fresh brief was written by an earlier interrupted run legitimately moves `needs-brief` → `clears` (measured in the waves) — only the structure-changed case is gated.

## Done when
Full suite green; commits `fix(reapply): names-form structure-changed needs --allow-structure-change` and `fix(reapply): failure lines name the exception type; dry-run counts purged audio`; mutation table in the handback.
