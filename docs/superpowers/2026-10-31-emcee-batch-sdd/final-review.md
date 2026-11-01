# Final branch review: emcee-batch, 99606b44..6706ca85

Coverage: I read the review package in passes. I read every src, docs and script hunk, plus `test_voiced_on.py` and `test_backfill_voiced_on.py`. For `test_keep_script.py`, `test_run_keep_script.py`, `test_say_cmd.py` and `test_scriptwrite.py` I read the first part or the test names only, not every body. I formed the view below before opening `minors.txt`. I did not re-run the suite: the ledger records 6513 passed at 6706ca85.

Read-only probe of the live station, today: 2,786 manifests, 328 voiced, 136 voiced and marked `awaiting_fix`. All 328 reproduce as `json.dumps(indent=2)`. No `dj_notes` block has an extra or missing key. No failed-attempt packages exist. Nothing under the station or `~/.emcee` was written.

### Strengths
- The keep-script failure path holds. I walked every exit: the refusals come before any change, `kept_notes` runs before preflight, the clear writes `notes` back, `_repair` persists before the next render, plain `run` skips the state, and Ctrl-C leaves `dj_notes` in place. The script goes only by explicit `emcee voice` or by `llama deliver` (R5, accepted). The `ScriptNotes` round trip cannot drop data on the live station (probe: no extra keys).
- `_keyed_segments` is the single key computation for render, adopt and count, so the plan's `N of M` cannot drift from what renders.
- Adoption is written to disk before the unlink and stays out of `rendered`, so `voiced_on` is right across `--keep-script` and `--fresh` by construction, not by a special case.
- Default paths are unchanged: the plain `_process_one` flow and `run` sweep differ only by the failed-attempt skip, and `_TtsNow(config)` does no I/O at construction.
- The backfill is careful and matches the plan: raw JSON, one key, canonical-format refusal, mtime restore. Canonical format is confirmed on all 328.

### Issues

#### Critical
None.

#### Important

1. `scripts/backfill_voiced_on.py:96-107`: `apply_one` does not check that the decision still holds (strict surface).
   - **What:** `backfill()` reads the manifest and classifies it, then runs `ps`, then `apply_one` reads a new `old`. The re-read guard only covers changes after that second read.
   - **Why:** a writer landing between the two reads is unseen. If `dj_audio` was cleared, line 107 raises TypeError and aborts the run. If it was re-voiced, an older clip-derived date overwrites a new `voiced_on`. The window is small and the process check narrows it, but the plan says skip on any change.
   - **Fix:** in `apply_one`, after parsing, skip when `data["dj_audio"]` is not a dict or already has either key set. Add a test.

2. Undocumented cross-effect of the backfill on the bulk-apply rollback.
   - **What:** `scripts/bulk_apply.py:1097-1104` refuses `unmark` with `station copy changed since marking` when the station manifest's sha differs. The backfill changes the sha of the 136 voiced, marked shows (confirmed by the probe). The refusal is verified in the code.
   - **Why:** the operator loses that batch's reversal for those shows, with the campaign paused and resumable, and nothing tells them before `--apply`.
   - **Fix:** add a sentence to the script docstring and to the CLAUDE.md and README backfill text, and raise it with the operator before the first `--apply`. A code change is not needed.

#### Minor

3. `README.md:610`: wrong statement.
   - **What:** it says `--keep-script --fresh` carries both dates, but that run renders the named clip, so it stamps today and clears `voiced_before` (`process.py`, `if rendered:`). CLAUDE.md is correct.
   - **Fix:** drop the clause and add one pin test (same as deferred line 63).

4. `packages/emcee/src/emcee/cli.py:279`: false claim on the strict surface.
   - **What:** the `_process_one` docstring says a bad bed cannot take a package off air. `_resolve_bed` never opens the file, so it is only true for keep+fresh (adoption loads the bed). On plain voice and `voice --keep-script` alone the bed fails after the clear. `run --keep-script` is safe because the plan loads the bed first.
   - **Fix:** correct the wording.

5. `packages/emcee/src/emcee/cli.py:727` loop: plan-level gap.
   - **What:** `run --keep-script` without `--drifted` also processes ready packages whose clips are all current. Measured at plan time, 94 of 328 are all-match.
   - **Why:** each gets a clear and a rewrite for nothing: a window with `dj_audio` null, plus a newer manifest mtime that makes the show ineligible for transmitter's quiet period. The backfill goes to real lengths to avoid exactly that. It is plan-compliant ("every package").
   - **Fix (optional):** skip a `ready` package whose count is 0 of M when not `--force`, with a `skip` line. It may equally wait until the operator uses this mode.

6. `packages/emcee/src/emcee/cli.py:699`: `note: no package resolves to presenter X` also prints when `--profile` or `--assigned` filtered the presenter's packages out. The note is then false. Stays deferred.

7. `scripts/backfill_voiced_on.py:151`: the per-presenter count files a house-voiced block (`presenter: null`) under `?`, which elsewhere means no record. Display only. Use `manifest_voiced_by`, or stay deferred.

### Triage of the deferred list
Numbers are ledger lines. "Must" means fix before merge, "wave" means ride this branch's one fix wave, "defer" means leave.

| Line | Item | Verdict | Reason |
|---|---|---|---|
| 20 | R1 | Stands | Correct. Only a failure at or after the last render can leave a null date, and readers tolerate it. |
| 21 | R2 | Stands | Process only. |
| 39-41 | R3, R4, R5 | Not findings | Accepted by the operator. |
| 31 | catchphrase example | Closed | Replaced by the 2516dc89 wording. |
| 32 | no prose check for profane titles | Defer | Operator decision, out of scope. |
| 33 | "character" at the house narrator | Defer | Wording ruled. |
| 34, 35 | test pins | Defer | Test polish, no behaviour. |
| 42 | "a bad bed" docstring | Wave | Strict-surface claim, false outside keep+fresh (issue 4). |
| 43 | adopt old-wording clip | Defer | Needs an off-route retry after a repair; no text is lost. |
| 44 | warning on keep+fresh only | Defer | Matches the plan; a bare run would warn falsely when all clips re-render. |
| 45 | invalid `dj_notes` reads kept script | Defer | Safe refusal; no such package exists. |
| 46 | no exit-code assertion | Wave | One line. |
| 53, 54 | `--tts` refusal text | Wave | Both are in the same few lines (`process.py:207,219`). Spec asks for a plain message, and the mlx hint is a dead end. Keep the refusal. |
| 55 | untested refusals | Wave | Plan requires tests for each refusal: presenter clone on elevenlabs, presenter clip with no transcript, house-clone branch. |
| 56 | stale wording | Wave for docstrings | Skip the `house_mlx` rename. |
| 57, 58 | kwargs seam, no-flag test | Defer | Resolution default path is covered by the existing suite. |
| 63 | README dates | Must | Wrong doc (issue 3), plus the test. |
| 64 | `voiced` default | Wave | One caller; a silent default on a recorded date. |
| 65 | helper near-duplicates | Defer | Harmless. |
| 70 | merged-title guard miss | Closed | Fixed by Task 1b. |
| 73, 74, 75 | wording items | Defer | Ruled; operator watch items. |
| 78 | `unmark` refusal | Must (docs and operator note) | Issue 2. |
| 79 | `apply_one` trusts classification | Must | Issue 1, strict surface. |
| 80 | backfill test gaps | Wave | Pre-existing `voiced_before`, formatting skip, no trailing newline. Cheap and strict. The rest may stay. |
| 81 | dry-run overstate, line order | Defer | All 328 are canonical today, so counts match. |
| 82 | summary lost on refusal | Defer | Idempotent re-run. |
| 88, 89, 90 | `w/` split, dead lookbehind, dead `->`, docstring | Wave | Same regex (`scriptwrite.py:134`). The brief asked for text uses to be handled deliberately. Pin `w/` with a test. |
| 91 | `E:` and ` - ` merges | Defer | Scope note. |
| 92 | GDTRFB stray `-` | Defer | Confirmed (`... Bad - into Not Fade Away`), but it comes from the existing symbol pass and only on a raw `->`, which the prompt forbids. |
| 97 | corrupt sidecar | Docstring in wave only | Atomic writes make the corrupt case very unlikely. |
| 98, 99, 100 | plan and test items | Defer | Abort is before any spend; `_keyed_segments` makes drift structurally impossible; the re-read is local and cheap. |

### Declined to judge
- Prompt wording, including "Name every other title plainly" against the vague note: the operator ruled it.
- A move or assign change between a failed attempt and its retry (R4): accepted.
- `llama deliver` overwriting the failed-attempt state (R5): accepted.
- The retry line's absence on preflight and adoption failure (R3): accepted.
- `run --keep-script` can sweep `themotet-2007-04-22` and `warrenzevon-2000-05-29` despite the "fresh script" note: the plan records it as documentation, not an exclusion, and it adds no new exposure over today's airing.
- No house-voice form of `run --keep-script` (`--presenter house` selects nothing): the plan selects by presenter id.
- A kept script that fails today's stricter guard during a repair: it fails safely with the script kept, and I have no case of it.
- `run --keep-script --dry-run` errors if the provider cannot be built (for example no key), where plain dry-run does not: an exact count needs the voice and model, and the failure is honest.
- `pieces._manifest_show`'s estimate key moves with manifest size after the backfill: it feeds the delivered-library preview only, and the airable show key hashes `broadcast.m3u` entries.
- The `.tmp` and mode behaviour of `atomic_write_bytes` on SMB: unchanged from every existing manifest writer.
- The SMB `os.utime` check: the plan makes it the operator's step before the first `--apply`.

### Assessment
**Ready to merge:** With fixes

**Reasoning:** No script-loss path or default-path regression found, and the cross-task behaviour of `--keep-script` with `voiced_on` holds. The backfill needs the `apply_one` recheck, the `unmark` side effect must be documented and told to the operator before `--apply`, and the README date claim must be corrected. The other wave items are optional polish.
