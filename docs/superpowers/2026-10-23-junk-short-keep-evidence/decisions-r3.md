# Round-3 decisions: rebuild the migration around a whole-library snapshot (apply exactly)

Operator ruling (Shawn, 2026-10-24 ~00:50): option 2. Source review: piece45/rv3-s/handback.md (0 Critical, 8 Important, 9 Minor on section 4). Section 4's per-show undo machinery is REPLACED, not patched. Keep 4.1's encoding (filename values under the legacy key names; old model rejects them; both forms always parse in the new model; writers refuse legacy; resolver judges) and 4.2's writer rules, except where changed below.

## The migration (replace 4.3's apply / undo / repair / runbook text)

R1 Runbook, in this order:
  1. Stop the sweep loop; confirm no `llama` process is running (`pgrep -x llama` empty).
  2. With v2.17.0 STILL installed, run the migration's dry run from the repo (`/Users/shawn/projects/llama/.venv/bin/python scripts/rekey_overrides.py`, branch code). It checks every show and prints each refusal with its repair route.
  3. Repair refusals with the installed v2.17.0 `llama` (routes as in the refusal table, including a route for out-of-range `set_breaks`/`encore_after`: `fix <show> --clear-set-breaks` / `--clear-encore`, then re-set). Repeat 2-3 until 0 refused.
  4. Snapshot: `--snapshot` copies every show directory's files outside `package/audio/` (about 280 MB today) into `<root>/rekey-snapshot-<UTC timestamp>/shows/<slug>/...`, plus a `manifest.json` listing every copied path with its sha256. It verifies every copy against the hash and F_FULLFSYNCs before reporting success. The snapshot is never modified afterwards.
  5. Install the new release; `llama --version` must report the piece-4 version. Run nothing else in between.
  6. `--apply` (refuses unless steps 4 and 5 hold: a verified snapshot newer than the last write to any `overrides.json`, and every `llama` on PATH reporting at least the piece-4 version; refuses if any `llama` process is running).
  7. Restart the sweep loop.
  8. Harness and apply lists (R6), then the bulk apply; triage held shows only after their re-gather.

R2 `--apply`: takes a workspace-wide migration lock (`<root>/.rekey.lock`, flock) and then, per show, that show's lock; under the show lock it re-reads `overrides.json` and `show.json`, re-runs that show's checks (a refusal now stops the whole run with the show named; shows already migrated stay migrated and `--restore` is the way back), and rewrites the RAW JSON object: only `titles`, `set_breaks`, `encore_after` change; every other key and its value, known or unknown, is preserved byte-for-byte in meaning (load with `json`, edit, dump with the same formatting rules `write_artifact` uses). Each file is written temp + F_FULLFSYNC + rename + directory fsync. Re-running `--apply` after an interruption continues with the remaining legacy shows (already-migrated shows have no legacy value and are skipped).

R3 Undo is `--restore <snapshot-dir>`: wholesale. It requires no `llama` process running and the migration lock; it verifies the snapshot's hashes, then for every slug in the snapshot copies every snapshotted file back over the library (temp + F_FULLFSYNC + rename), and deletes any non-audio file a show directory gained since the snapshot only if it is one llama writes (state the list: e.g. `notes.json`, `.txn/`, briefing files written after) — simplest correct rule: AUTHOR'S CALL, but it must leave each show exactly as at the snapshot apart from `package/audio/`. Shows created after the snapshot are listed, not deleted. Then the operator reinstalls v2.17.0. State plainly: restore returns the library's metadata to the pre-migration moment and DISCARDS every edit, gather and apply made since, including the bulk apply; it is the rollback for "piece 4 is wrong", not a per-show tool. Re-delivered station copies are not touched by restore (state the consequence: the station keeps the new packages until re-delivered from the restored library).

R4 Remove entirely: the per-show backup `overrides.pre-rekey.json`, the sidecar `overrides.rekeyed.sha256`, hash-based `--undo`, "already undone", the undo set and its post-condition, the per-show "backup exists while legacy" refusal and the stale-backup route, the manual-rollback paragraph, and the "llama-2.17.0 saved copy" (v2.17.0 stays installed until step 5; to roll back, reinstall it from the release).

R5 Version gate (step 6): every `llama` on PATH must report at least the piece-4 release version (define it as the version this branch ships, compared numerically; a dev build `0.1.0`/`0.0.0+unknown` refuses); no `llama` on PATH refuses; a running `llama` process refuses. `--restore` has no version gate.

R6 Harness: both arms (base at e37f670 and the candidate with the measurement-only scratch re-key) are run and compared BEFORE the migration, exactly as measured. After the migration, a candidate-only re-run must reproduce the pre-migration candidate's per-show outcome and titles for every show (a repro check; any difference stops the apply and is investigated). Apply lists come from that post-migration re-run, so their `input_digests` match the migrated files. State this as the bulk apply's requirement.

R7 Minors to apply:
  - M1: "fails on every command" -> "fails on every command that lists or resolves shows, and on any gather/brief/reapply that reads a migrated file"; keep the conclusion (loud).
  - M2: the three `--clear-*` flags work without `show.json` when given a filename (dangling key repair); the resolver names every dangling key in one message.
  - M4: "legacy value" = anything the v2.17.0 model accepts as an int (state: a titles key or list item that int() parses after strip, an int-valued float such as 2.0); the new resolver treats all of those as legacy.
  - M5: a mixed file is refused in step 2; its route is undoing the hand edit with v2.17.0 still installed (fits the order).
  - M7: covered by R2's directory fsync.
  - M8: the up-front exclusion refusal covers the filename form and `--no-run`.
  - M9: an unreadable `overrides.json` refuses the show in step 2 (route: restore from git? no — route: the operator repairs the file; list it); a missing `selection.json` does not matter to the migration (it reads only `overrides.json` and `show.json`) — say so.

R8 Strict-surface stakes text and section 8 premises: update to the snapshot design (premise: the snapshot's 280 MB copy and hash check time over the local disk; test: time `--snapshot` once on the real library before step 5).
