### Task 1b: Honor `awaiting_fix` (operator-approved 2026-10-25; not in the original plan)

**Source of truth:** the draft bulk-apply spec, section "The `awaiting_fix` contract", at
/Users/shawn/projects/llama/docs/superpowers/specs/2026-10-25-bulk-apply-design.md (main checkout — READ ONLY, never modify it). Summary:
`"awaiting_fix": {"reason": "<one line>", "marked_at": "<UTC ISO-8601>"}` — a new optional top-level field in a delivered package's `manifest.json`, written in place by llama (atomic temp + rename), changing nothing else (not tracks, dj_*, broadcast.m3u or audio). Absent or `null` = no fix pending; ANY other value = not to be voiced and not to be aired. It clears by re-delivery (or a llama escape-hatch command).

**Files:**
- Modify: `packages/transmitter/src/transmitter/station.py` (`evaluate`), `packages/transmitter/src/transmitter/pieces.py` (`scan_delivered`)
- Test: `test_station.py`, `test_pieces.py`, `test_pipeline.py`

**Interfaces / behaviour:**
- `station.evaluate`: a manifest whose top-level `awaiting_fix` is present and not `None` makes the package `Ineligible`. Reason text: `awaiting fix from llama: <reason>` when the value is a dict whose `reason` is a non-empty string (strip whitespace; one line — collapse newlines to spaces); else `awaiting fix from llama`. Never raise on a malformed value (a string, a list, a number, `true`, a dict without `reason`, a non-string `reason`): any non-null value means not airable. The check sits with the other manifest-level eligibility checks; order it so a marked package reports this reason (state where it sits relative to the existing checks and why).
- The reader must stay tolerant if the committed spec changes the object's inner shape: only "present and non-null" decides eligibility; `reason` is display only.
- `pieces.scan_delivered` (the `--library delivered` rehearsal): a marked package is left out of the rehearsal pool (it is held from broadcast until re-delivered). Controller ruling R20. Test it.
- Already-planned rows: no new code is expected — render's existing re-validation (`render_step`, which re-scans via `Station.scan_pieces` → `station.scan`) sees the package as Ineligible and takes the skip path (`replan_from`) for a planned row whose first segment is not yet encoded. NOTE: the file-set key does NOT change when only `manifest.json` is rewritten (the key covers the broadcast.m3u entries), so the drop happens because the package is Ineligible, not because the key changed. Pin it with a test: plan two shows, render the first show's segments only partially (or none of the second's), mark the second show's manifest, render again → the second row is dropped with every row after it, re-extended without that show, `plan-changed` logged, no error, plan covered.
- Already-encoded/published pieces air as planned: a row whose segments are already encoded is not dropped (the existing on-air guard). Pin it with a test: mark the show that is mid-render (some of its segments encoded) → render continues it, no LayoutError, no drop.
- `status`/`library` visibility: the reason flows through `station.scan`'s Ineligible list; Task 13 builds `library`'s ineligible-by-reason summary later — no change to cli/service here unless an existing status line already lists ineligible reasons (check and say).

**Steps:** failing tests first (RED captured), implement, full transmitter suite (`./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`), commit `transmitter: a delivered package awaiting a fix from llama is not airable`.
