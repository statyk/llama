### Task 6: `llama clear-mark`

**Spec:** "Clearing without re-delivery…" (all bullets). Strict surfaces 1, 3. **Implementer: Opus.**

**Files:** Modify `cli.py` (new command `clear-mark`); Test `packages/llama/tests/test_clear_mark.py` (new).

**Interfaces:**
- Consumes: Tasks 3, 5; `catalog.purge_package_audio`.
- Produces: `llama clear-mark <name> [--accept-change]` (panel "Fix & ship"). Under the show lock, in order, each refusal exiting 1 and writing nothing: station copy unreadable (`StationUnreadable` text); not marked (`<slug>: the station copy is not marked; nothing to clear`); unvoiced (`<slug>: unvoiced destination; re-deliver it instead: llama deliver <slug>`); not processed since the last mark (`<slug>: awaiting fix; re-process it first`); held (`<slug>: held for review`); library manifest sha ≠ record's (`<slug>: the library package changed since it was processed; re-process it`); differences without `--accept-change` (`<slug>: the station copy differs: <names>; pass --accept-change if the change is cosmetic`); `emcee_running()` non-empty (`refusing: emcee is running`). Then `clear_mark`, `add_clear(ws, "equal" | "change accepted")`, print `mark cleared; the voicing is kept` (plus `change accepted: <names>`), and purge: equal → `purge_package_audio(ws, out)` with deliver's three messages; accepted → `library audio kept (track lists differ)` when the purge skips.

- [ ] **Step 1: Write the failing tests:** one per refusal above (asserting the exact string and the station bytes unchanged); `test_equal_clears_and_purges` (station mark gone, `dj_audio` and audio files untouched, library `package/audio/` emptied, record `clears[-1].outcome == "equal"`); `test_accept_change_clears_and_keeps_library_audio`; `test_processed_then_overruled_still_clears` (Task 3's sha refresh: a `redo --from package` after processing still qualifies).
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(cli): clear-mark keeps a voicing when the re-processed show is unchanged`.

---

