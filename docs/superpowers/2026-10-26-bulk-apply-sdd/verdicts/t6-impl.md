# Task 6 handback: `llama clear-mark` (+ station encoding scope addition)

Status: DONE_WITH_CONCERNS (minor concerns only; see the end)
Commit: 003a5404 feat(cli): clear-mark keeps a voicing when the re-processed show is unchanged

## What was implemented
- `cli.py`: new command `clear-mark <name> [--accept-change]`, panel "Fix & ship", body in
  `_clear_mark_one`. It needs `delivery_path` in config (`no delivery_path in config`, exit 1;
  the brief gives no `--dest`). Under `file_lock(show_ws.lock)` it refuses in the brief's order,
  each refusal exiting 1 with the exact brief string and writing nothing:
  1. `StationUnreadable` text (`read_station_manifest`)
  2. `<slug>: the station copy is not marked; nothing to clear` (`mark_of(...) is None`)
  3. `<slug>: unvoiced destination; re-deliver it instead: llama deliver <slug>`
  4. `<slug>: awaiting fix; re-process it first`. This fires on: no record, `processed`
     null, `campaign.awaiting_fix(rec)`, an unparseable `processed.at`, OR `processed.at`
     earlier than the STATION mark's `marked_at`. The spec says "processed after
     `marked_at`". An absent or unparseable station `marked_at` (a malformed mark) falls back
     to the record test alone. An unreadable campaign.json refuses at this point with the
     `CampaignUnreadable` text.
  5. `<slug>: held for review` (show.json `needs_review`; a show.json that cannot be read
     refuses with `cannot read show.json (...)`)
  6. `<slug>: the library package changed since it was processed; re-process it`. This fires
     when the record's sha is None (processed while held), when the current library manifest
     sha differs, or when the library manifest cannot be read.
  7. `<slug>: the station copy differs: <names, ", "-joined>; pass --accept-change if the change is cosmetic`
  8. `refusing: emcee is running`, followed by the ps lines indented two spaces. The call goes
     through the module, as `station_mark.emcee_running()`.
  After the checks: `station_mark.clear_mark(out)`. A raw `OSError` from it becomes
  `<slug>: could not clear the station mark: <err>; <state>`, where `<state>` comes from
  re-reading the station: either "still carries the mark (retry)" or "check by hand". It exits
  1 with no traceback and records nothing. `StationRefused` exits 1 with its own text.
  Next comes `campaign.add_clear(ws, "equal" | "change accepted")`. If that write fails,
  `put_back(expect_sha256=sha(after), data=before)` restores the mark and the command exits 1
  with `<slug>: could not record the clear (...); the station mark was put back`. If the
  put-back also fails, the message says to check both by hand.
  Then it prints `mark cleared; the voicing is kept`, plus `change accepted: <names>` when the
  change was accepted, and runs the purge. Equal: deliver's three messages, through a new
  shared `_echo_purge`, which `_purge_after_delivery` now calls with identical behaviour.
  Accepted: `library audio kept (track lists differ)` when the purge skips with catalog's
  track-list reason (`station copy is a different package version`); any other outcome gets
  deliver's messages.
- Scope addition from the orchestrator: `station_mark._encode` now uses `json.dumps(data, indent=2)`,
  which is emcee's `rewrite_manifest` encoding (`json.dumps(data, indent=2) + "\n"`: ASCII
  escapes, default separators). It is also llama's own `write_artifact` encoding, minus the
  newline. The trailing newline still follows the bytes read. **Mark then clear now matches
  emcee's encoding exactly** and reproduces the bytes of both writers. Key order is kept
  because the code edits the dict in place. Nothing differs, so no concern there.

## Dry-run list (existing test expectations moved)
- `test_station_mark.py::_station` (the fixture helper used by most station_mark tests): its
  default encoding changes from `json.dumps(..., indent=2, ensure_ascii=False)` to emcee's
  `json.dumps(..., indent=2)`. Clause: the orchestrator's scope addition ("mark-then-clear
  reproduces emcee's bytes") and spec "The `awaiting_fix` contract" (only the key changes).
  No real writer produces the old fixture bytes. Without the change,
  `test_write_mark_adds_only_the_key`'s byte-for-byte round trip at line 87 fails, as
  predicted and observed. No assertion in any existing test was edited.

## Tests
New `packages/llama/tests/test_clear_mark.py` (30 tests):
- Refusals: unreadable station copy (bad-json, no-manifest), missing station dir, no
  delivery_path, not marked, null mark, unvoiced, newer record mark, never processed, no
  record, station marked_at newer than processing, unreadable campaign.json, held,
  awaiting-before-held order, library changed since processing, held processing (no sha),
  differences without the flag, emcee running, and emcee checked after the other refusals.
  Each refusal test asserts the exact string and the station tree, record and library tree
  unchanged.
- Failure paths: an OSError from `_swap_in` gives a clean exit with no traceback, no clear
  recorded, and the library audio kept. A StationRefused from the writer exits cleanly. A
  failed `add_clear` puts the mark back, leaving the station bytes identical.
- Success: `test_equal_clears_and_purges` (mark gone, other keys and `dj_audio` and voiced
  files untouched, library audio emptied, `clears[-1].outcome == "equal"`, no leftover
  siblings), equal with `--accept-change` recording "equal", purge skip and purge partial
  warnings, `test_accept_change_clears_and_keeps_library_audio`, accept-change with equal
  tracks still purging, `test_processed_then_overruled_still_clears` (sha refreshed by
  `campaign.after_package`, the package stage's last step), and the show lock held during
  `clear_mark`.
- An autouse fixture stubs `station_mark.emcee_running` to `[]`. The first full run had 4
  clear-mark failures because the real check reads `ps` and something matching `emcee` was
  running at that moment (probably another session's emcee tests). A rerun was clean, and the
  stub makes the tests deterministic.
New pin in `test_station_mark.py`: `test_mark_then_clear_reproduces_the_writers_bytes[emcee|llama]`,
using a non-ASCII venue plus the fixture's `Café Ü`. Each case asserts that the marked
file is ASCII and keeps the prefix, and that the cleared file is byte-identical to the original.

## TDD evidence
RED (live tree, before the implementation):
`./.venv/bin/python -m pytest -q packages/llama/tests/test_clear_mark.py packages/llama/tests/test_station_mark.py`
-> `31 failed, 15 passed` (every clear-mark test failed with `No such command 'clear-mark'`
(exit 2), and `test_mark_then_clear_reproduces_emcees_bytes` failed on `assert marked.isascii()`).
GREEN: the same files plus test_deliver_cmd.py -> `116 passed`. Full suite:
`./.venv/bin/python -m pytest -q` -> `6116 passed, 1 skipped, 8 deselected` (6084 + 32 new).

Mutants run in a scratch copy (import shadowing checked: `llama.__file__` resolved inside the
copy; `PYTHONDONTWRITEBYTECODE`). Each prediction was named before the mutant ran:
- M1, drop the station `marked_at` test: caught by test_station_mark_newer_than_the_processing_refuses (predicted).
- M3, no put_back: caught by test_failed_record_write_puts_the_station_mark_back (predicted).
- M4, accepted mode always prints "kept": caught by test_accept_change_with_equal_tracks_still_purges (predicted).
- M5, emcee check moved first: caught by test_emcee_check_comes_after_the_other_refusals (predicted).
- M2, drop the `sha is None` guard: SURVIVED. It is an equivalent mutant. A None sha differs
  from any real manifest's sha, and when the manifest is missing, `library is None` refuses
  anyway. The guard is kept as belt-and-braces.

## Files changed
- packages/llama/src/llama/cli.py (clear-mark, `_clear_mark_one`, `_processed_since_mark`, `_station_state`, `_echo_purge` split from `_purge_after_delivery`)
- packages/llama/src/llama/station_mark.py (`_encode`: emcee's encoding)
- packages/llama/tests/test_clear_mark.py (new)
- packages/llama/tests/test_station_mark.py (fixture encoding; new pin)

## Self-review
- Untouched: `purge_package_audio` (only called), junk constants, audio_reuse, reapply. Llama
  imports nothing from emcee. Lock order is show only, and the campaign write happens inside
  the show lock as the other writers do it.
- The order matches the brief, and the emcee check runs last, immediately before `clear_mark`.
- Nothing is written to the record unless the station write succeeded.
- `_processed_since_mark` uses `campaign._parse`, a private helper in the same package.

## Concerns
1. The station `marked_at` check (refusal 4) goes beyond the brief's wording ("not processed
   since the last mark") and follows the spec's literal "processed after `marked_at`". It only
   ever refuses more.
2. In the accepted case, "library audio kept (track lists differ)" prints only on catalog's
   track-list skip reason. That reason is matched by its exact text: catalog cannot gain a
   field under the constraints, and a test pins the text. Other skips get deliver's warning,
   so an untrue "track lists differ" never prints. The brief says "when the purge skips".
3. The command has no `--dest` and requires `delivery_path`, matching the brief's signature.
4. The emcee-running refusal prints the ps lines after the fixed string, as extra lines.
