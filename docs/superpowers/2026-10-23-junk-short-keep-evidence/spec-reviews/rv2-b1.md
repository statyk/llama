Foundation: SOUND -- the loud-failure encoding works as claimed (verified: e37f670's `Overrides` rejects filename values for all three keys and accepts only the harmless `titles: {}` / `set_breaks: []`), but the repair and undo routes in 4.3 rest on the old binary working per show, which the catalog contradicts (finding 1). That is a fixable route, not the foundation.

- **[Important] The old binary crashes on every show once any show is migrated, so the 4.3 repair route and the undo post-condition cannot run as written**
  - Where: 4.3 "A refused show is repaired with the old binary: `llama-2.17.0 redo <show> --from gather`, then re-run the migration." and "Its post-condition is the old binary's `llama-2.17.0 redo <show> --from gather` for any show the new code re-gathered."
  - Problem: Every name-resolving or listing command loads the whole catalog. `resolve_show` calls `iter_shows`, and `iter_shows` calls `read_overrides(ws)` for every show dir with no exception handling. A loud `ValidationError` on one migrated show is therefore not per show: v2.17's `redo`, `fix`, `triage`, `show`, `status`, `deliver`, `rm` and `reapply` all die on the first migrated show they meet, whatever show was named. The repair route is dead the moment `--apply` has migrated the other 605 shows. Undo has the same problem: if even one show's undo refuses because it was edited after migration, the old binary cannot run on any show, including the ones that were undone.
  - Evidence: catalog.py:343-348 (`entries = {e.slug: e for e in iter_shows(root, ledger)}`); catalog.py:290-310 (`overrides=read_overrides(ws)` inside the loop, unguarded); workspace.py:59-62. Verified with the e37f670 model in the repo venv: filename-valued `titles`, `set_breaks` and `encore_after` each raise `ValidationError`.
  - Failure scenario: Migration day. The six checks refuse one show (e.g. the metadata cache was refreshed since its gather), and `--apply` migrates the rest. The operator runs `llama-2.17.0 redo <refused> --from gather` as instructed, and it raises `ValidationError` from some other show's `overrides.json`. Either the operator hand-edits files or undoes all 605 to repair one. The same thing happens on a rollback where any show's undo refuses.
  - Setup and likelihood: Certain whenever the migration refuses a show (0 today; the spec itself says to re-run the checks on migration day). On rollback, likely if the operator has used `fix` at all since the migration.
  - Suggested fix: Move the repair before the apply. Run the dry run, repair the refused shows with `llama-2.17.0` while nothing is migrated yet, re-run the dry run until it reports 0 refused, and only then `--apply` (or have `--apply` refuse while any show would be refused). Make undo all-or-nothing: its dry run must show every migrated show undoable before `--undo --apply` touches any. Also state that the **new** `Overrides` model must parse both forms and leave every validation to the resolver, or the new binary's catalog will crash the same way. These are runbook and spec changes only.

- **[Important] New-binary writers on a legacy (unmigrated or refused) file are undefined, and `--no-run` can produce a file neither binary nor the migration can handle**
  - Where: 4.2 "Writers take track numbers ... translated to a filename through `show.json`"; 4.1 "It refuses with `LlamaError` ... a file mixing legacy and filename values".
  - Problem: Round 1's "fix and triage refuse the same way before any prompt" is gone. Nothing now says what the new `fix --set-title`, `--set-breaks`, `--set-encore`, `--suggest-titles`, `--untitled` or the triage edits do when the existing file still holds integer keys. The obvious implementation adds a filename key next to the legacy ones. The auto-redo then refuses the mixed file and the unit rolls it back, which is safe. `fix ... --no-run` does no redo, though, so the mixed file persists. After that, v2.17 rejects it, the migration's checks either crash on `int("<filename>")` or refuse it, and the resolver refuses it. No `fix` route remains.
  - Evidence: Spec 4.1-4.3; CLAUDE.md "`--no-run` validates nothing"; cli.py:1393-1446 (`_edit_overrides` merges into the existing dict).
  - Failure scenario: Between steps 3 and 5 of the runbook, or at any later time on a show the migration refused, the operator runs `llama fix <show> --set-title 4=X --no-run`. The show is now wedged until someone hand-edits `overrides.json`.
  - Setup and likelihood: Low (it needs `--no-run` on an unmigrated show), but this is a strict surface and the outcome is a hand-edit.
  - Suggested fix: Restore the rule that every writer refuses before any prompt when the file has any legacy value (`run the migration`). Have the migration refuse a mixed file explicitly instead of parsing it. Add a test for each; together about a sentence and two tests.

- **[Important] Pre-check 3 for the voiced 37 cannot be done against the manifest**
  - Where: 5.5 "the re-packaged library manifest's tracks include every restored file listed for that slug".
  - Problem: `voiced-severe-final.json` lists source filenames (e.g. `gd70-04-15d1t10.mp3`). `ManifestTrack.filename` is the packaged name (`"01 - Morning Dew.mp3"`), which 5.4 itself points out. The check as written can never succeed. An implementer will either compare titles (two `Drums` on `gratefuldead-1977-05-13`, `Dark Star` x2 on 1991-06-17) or quietly drop the check. That check is the one guard confirming that a `--replace-voiced`, which discards paid voicing, actually ships the restoration.
  - Evidence: models.py:267-273 (`filename: str  # packaged filename`); spec 5.4, "the manifest records only the packaged filename".
  - Failure scenario: A re-pack that lost a restored file (it fell to the junk test after a cache refresh, or the operator excluded it) passes a title-based check. Voicing is discarded and the restored music is not there.
  - Setup and likelihood: Certain that the literal check is unimplementable; a wrong pass is rare.
  - Suggested fix: Check the library `show.json` instead: its tracks' `filename`s include every listed source file, with `short_kept` set, and the manifest's track count equals show.json's. This is one sentence.

- **[Minor] The migration writes the sidecar last, so an interruption leaves a show that can never be undone**
  - Where: 4.3 "Write, in this order: 1. the backup ... 2. the new `overrides.json` ... 3. the sidecar".
  - Problem: A crash or Ctrl-C between steps 2 and 3 leaves a migrated file with no sidecar. Undo then refuses that show for good: the hash is missing and the file differs from the backup. A re-run of the migration skips it, because it has no legacy keys, so the sidecar is never written. Under finding 1, that one show also blocks the old binary for everything.
  - Evidence: Spec 4.3 (the write order and undo's three cases).
  - Failure scenario: An interrupt lands between two renames during a 606-show loop.
  - Setup and likelihood: Very rare (a millisecond window), but this is a strict surface.
  - Suggested fix: Write the sidecar (the hash of the bytes about to be written) before the new `overrides.json`. Then any interruption leaves either a legacy file equal to its backup (reported as `already undone`, and re-migratable) or a file matching its sidecar. This is a one-line reorder plus a test.

- **[Minor] "Every `llama` on PATH reports the new version" has no defined reference, and blocks `--undo`**
  - Where: 4.3 runbook step 3.
  - Problem: The script runs on the repo venv. Its `llama.__version__` there is `0.1.0`, because pyproject is static and only release builds stamp `_version.py`. If the venv is activated, `.venv/bin/llama --version` also prints `0.1.0`. Comparing against "the new version" therefore means nothing unless the script hard-codes a minimum. The check also gates `--undo --apply`, which is run after the old binary is reinstalled, so the check refuses it exactly when it is needed. The runbook also never says when the step-1 sweep loop restarts.
  - Evidence: `/Users/shawn/projects/llama/.venv/bin/python -c "import llama; print(llama.__version__)"` prints `0.1.0`; `~/.local/bin/llama --version` prints `2.17.0`.
  - Failure scenario: The script refuses forever, and the operator adds a bypass flag.
  - Setup and likelihood: Certain if the check is implemented naively.
  - Suggested fix: The check is "no `llama` on PATH reports `2.17.0` or earlier" (a hard-coded floor; ignore a `0.1.0`/`0.0.0+unknown` dev build, or name it). Exempt `--undo`. Add "restart the sweep after step 5".

- **[Minor] The repair route cannot fix two of the six refusal reasons**
  - Where: 4.3 refusals "a `titles` key is outside `1..len(tracks)`" and "a track filename repeats".
  - Problem: `llama-2.17.0 redo` on an out-of-range title key raises `overrides.titles: no track k` (gather.py:1368-1371). A repeated filename comes back from the same metadata. Only `llama-2.17.0 fix --clear-title k` (or a metadata fix) gets out of these, and the spec names `redo` alone.
  - Failure scenario: A refused show cannot be repaired by the documented step.
  - Setup and likelihood: 0 such shows today.
  - Suggested fix: Name the route per reason, inside the pre-apply repair loop from finding 1.

- **[Minor] Positional edits refuse on the ~1,537 changed shows from migration until each is re-gathered**
  - Where: 4.2 "The staleness check compares `show.json`'s filename list with gather's final kept list".
  - Problem: Until the bulk apply re-gathers a show, its `show.json` was written under today's rule, while the shared helper uses `short_keep=True`. So every positional writer (`--set-title`, `--set-breaks`, `[t]`, `[u]`, `--suggest-titles`) refuses with "stale; redo" on every show the rule changes, including the 123 held ones the operator triages. The remedy works, but it is a surprise and costs a redo per edit.
  - Failure scenario: Triaging a held show between the migration and the apply: every edit asks for a redo first.
  - Setup and likelihood: Certain in that window; recoverable.
  - Suggested fix: Say this in the runbook (triage after the apply), or have the refusal message say "re-gather under the new rule first".

- **[Minor] The tripwire's bare `follow`/`download`/`subscribe` on titles can drop a short song, and a spam drop looks like an ordinary short drop**
  - Where: 2.3 `SPAM`, "`|\bfollow\b|\bdownload\b|\bsubscribe\b`"; 2.5 "A file the rule drops keeps the reason `implausibly short`".
  - Problem: `\bfollow\b` matches tags like `I'll Follow the Sun` (about 1:50), `Follow You Down` and `Follow the Drinking Gourd`, which are short on a long-jam tape, so they drop as spam. The real spam shape is already caught by `@\w{3,}` and the URL terms. And because the spam verdict is recorded as `implausibly short`, triage's `[i]nclude dropped` offers a spam-flagged file for re-admission with no warning, which weakens strict surface (c) at the operator's own hand.
  - Evidence: The spec's own regexes; 0 measured hits, so this is a future case.
  - Failure scenario: A short Beatles cover stays dropped. Or a lying-tag spam clip is re-admitted from `[i]` because nothing marked it.
  - Setup and likelihood: Rare.
  - Suggested fix: Keep the bare words for the filename stem only, or require `follow (me|us)`. Record a distinct reason (`spam-shaped name or tag`) so `show --tracks` and `[i]` show it.

- **[Minor] "then `emcee run`" is station-wide; the 37 want `emcee voice <slug>`**
  - Where: 5.5, "`deliver <slug> --replace-voiced` ... then `emcee run`".
  - Problem: `emcee run` voices every not-broadcast-ready package under the station root. After the unvoiced re-deliveries, that is potentially all of the ~1,028 delivered-unvoiced shows plus anything else pending. Its plan prompt shows the count, but the instruction as written invites approving a far larger spend than the 37.
  - Evidence: CLAUDE.md, emcee `run` / `voice`.
  - Failure scenario: A large unplanned TTS/LLM spend, or a plan the operator has to read carefully and decline.
  - Setup and likelihood: Likely if the step is followed literally.
  - Suggested fix: Use `emcee voice <slug>` per slug, or `emcee run --dry-run` and check the plan count is 37.

- **[Minor] The selector refusal is an enumerated list that omits `--held`, and the undo post-condition names an undefined set**
  - Where: 5.5 "refuses `--replace-voiced` with a selector (`--state`, `--packaged`, `--artist`, `--run`, `--profile`)"; 4.3 "for any show the new code re-gathered".
  - Problem: `deliver` also has `--held` (cli.py:2454). Today the gate makes `--held` harmless, but a hand-written list drifts as selectors are added; `deliver` already computes `other_selector` (cli.py:2478). Separately, "any show the new code re-gathered" is not recorded anywhere the operator can list.
  - Failure scenario: A future selector bypasses the refusal; or, on undo, the operator cannot tell which shows to re-gather.
  - Setup and likelihood: Low.
  - Suggested fix: Refuse on `other_selector`. Define the undo set, e.g. every show whose `show.json` carries a `short_kept` track or postdates the sidecar.

### Unverified premises
1. **The old binary's failure is per show.** It is not (finding 1: catalog.py:290-310, 343-348). The cheapest test: with one migrated fixture show in a scratch root, run `llama-2.17.0 show <another show>`.
2. **The new `Overrides` model parses legacy files without raising** (needed so the new binary's catalog survives the window before migration). The spec implies it but never states it. Test: load the 606 legacy files through the new model in a dry run.
3. **The 5.4 duration check is affordable over SMB.** It runs one `ffprobe` per station file over ~1,000 shows, on the station share. Test: time `ffprobe` over one delivered show's files on the share.
4. **Briefing reuse of 1,017/1,415** under the shipped `briefing_reusable`, guard included. Test: per-show agreement between the branch's function on the candidate arm and the harness figure.
5. **No writer of `overrides.json` besides `_edit_overrides` and the migration.** Confirmed by grep (cli.py:1444 is the only `write_artifact(show_ws.overrides, ...)`; `show_unit` only reads bytes), so this needs no test.

TOTAL: 10 findings (0 Critical, 3 Important, 7 Minor)
