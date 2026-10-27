### Task 8: Strict station reuse and the held-outcome anchor

**Spec:** "Re-processing" (Audio reuse never silently falls back; Held outcomes keep a reuse anchor). Strict surface 5. **Implementer: Opus.**

**Files:** Modify `audio_reuse.py`, `stages/package.py` (`build_package`), `cli.py` (`_redo_show_locked`, `redo`, `fix`); Test `test_audio_reuse.py`, `test_redo_cmd.py`, `test_fix.py`; the dry run also reads `test_deliver_cmd.py` and `test_purge_audio.py`, which pin today's purged-show re-download route.

**Interfaces:**
- Consumes: Task 5 (`station_mark.StationUnreadable`, the one "unreadable" exception, raised here; no second class).
- Produces in `audio_reuse.py`:

```python
ANCHOR = "reuse-anchor.json"
class StationUnpaired(LlamaError): ...       # text "<slug>: station copy does not pair: <detail>"
@dataclass(frozen=True)
class ReusePlan:   # existing fields, plus
    strict: bool = False
    station_problem: str | None = None       # strict only: why the station copy cannot be read
def plan_reuse(show_ws, station_dir: Path | None, *, strict: bool = False) -> ReusePlan
    # station pairing: against show.json first; when that pairs nothing, against the anchor
    # (when the anchor's identifier equals the station manifest's source.identifier).
    # library pairing: against the library manifest first; when that pairs nothing and the
    # anchor's identifier equals show.json's, the anchor's track i (1-based) pairs its filename
    # with audio.packaged_filename(i, title, Path(filename).suffix) when that file is in
    # package/audio/ (a packaged show held by the apply, cleared later, reuses its own audio)
def check_pairs(plan: ReusePlan, show_ws) -> None
    # strict only: StationUnreadable(station_problem); StationUnpaired("no copy pairs") when
    # plan.station is empty and no plan.library file exists in package/audio/
def write_anchor_if_absent(show_ws) -> bool
def drop_anchor(show_ws) -> None
```
- `plan_reuse(strict=True)` with `station_dir is None` (`config.delivery_path` unset) sets `station_problem = "no delivery_path in config"`, so a delivered show refuses as unreadable.
- `build_package(..., tally: dict[str, int] | None = None)`: when `reuse.strict`, call `check_pairs` first; an identifier mismatch raises `StationUnpaired("a different recording")`; a source paired in the plan-time `library` or `station` map whose cached metadata has no length raises `StationUnpaired(f"{filename} has no metadata length")`, and one whose copy is not placed raises `StationUnpaired(f"{filename} failed its length check")`, instead of downloading; an unpaired source downloads. It increments `tally["reused"]`/`tally["downloaded"]`, logs one `detail(f"audio reused {r}, downloaded {d}")` line, and after the manifest write calls `drop_anchor` (then `campaign.after_package`, Task 3).
- `_redo_show_locked(..., allow_download: bool = False)`: `strict = <show delivered in the ledger> and from_stage != "select" and not allow_download`; before `drop_stage_artifacts`, `write_anchor_if_absent(show_ws)` when `package/manifest.json` exists or the show is delivered; `plan_reuse(..., strict=strict)`.
- `--allow-download` on `llama redo <name>` and `llama fix <name>` (by name only; with any batch selector it refuses before any write: `--allow-download takes one named show`): that one show's re-package is not strict, so it downloads whatever does not pair (today's route), for a delivered show whose station copy is gone or permanently unpaired. The CLI prints after either strict refusal the fixed hint line (Contracts).

- [ ] **Step 1: Dry run.** List the existing tests that expect a delivered show's `redo --from package` to re-download purged audio (CLAUDE.md's old route); each changes under the spec clause "Audio reuse never silently falls back".
- [ ] **Step 2: Write the failing tests:**
  - `test_strict_downloads_only_files_the_station_never_held` (Review Focus 3): delivered show, station copy pairs, the new list adds one unpaired file → `ia.download_file` called once (that file), `tally == {"reused": n, "downloaded": 1}`.
  - `test_strict_refuses_a_paired_copy_failing_its_length_check` (no download; the unit restores).
  - `test_strict_refuses_when_nothing_pairs` and `test_strict_refuses_a_missing_or_unreadable_station_copy` (exact strings; the unreadable case raises `station_mark.StationUnreadable`; each followed by the `--allow-download` hint line).
  - `test_strict_refuses_a_source_with_no_metadata_length` (`<file> has no metadata length`, no download) and `test_strict_refuses_without_a_delivery_path` (`config.delivery_path = None`, delivered show → `StationUnreadable`, detail `no delivery_path in config`).
  - `test_anchor_pairs_after_a_held_commit`: write the anchor, replace `show.json` with a retitled list (station no longer pairs with it), drop the library manifest → `plan_reuse` pairs the station through the anchor; a later package build removes the anchor.
  - `test_anchor_pairs_library_audio_of_a_packaged_show`: undelivered packaged show; write the anchor, replace `show.json` with a retitled list, drop the library manifest, leave `package/audio/` → `plan_reuse.library` maps every anchor filename to `packaged_filename(i, anchor title, ext)`; the package build reuses them with zero downloads and removes the anchor.
  - `test_allow_download_lets_one_named_show_download`: delivered show, station dir gone → `redo <slug> --from package --allow-download` downloads and packages; the same on `fix <slug> --set-venue X --allow-download`. `test_allow_download_refuses_a_selector`: `redo --held --from package --allow-download` exits 1 with the fixed string, nothing written.
  - `test_anchor_is_written_once`: a second `write_anchor_if_absent` leaves the first anchor byte-identical.
  - `test_reselection_redo_is_not_strict` **(pin)**: `redo --from select` on a delivered show downloads.
  - `test_undelivered_reuse_unchanged` **(pin)**.
- [ ] **Step 3:** Run → FAIL. **Step 4: Implement.** **Step 5:** Full suite → PASS. Commit `feat(reuse): strict station reuse for delivered shows, held-outcome anchor`.

---

