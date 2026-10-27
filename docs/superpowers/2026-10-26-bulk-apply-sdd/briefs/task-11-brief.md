### Task 11: Per-batch snapshots and restore

**Spec:** "Undo". Strict surface 4. **Implementer: Opus.**

**Files:** Create `packages/llama/src/llama/batch_snapshot.py`; Test `packages/llama/tests/test_batch_snapshot.py` (new).

**Interfaces:**

```python
def take(snap: Path, root: Path, slugs: list[str], *, station_root: Path | None) -> None
    # per slug under its show lock: copy every file outside package/audio/, .audio-aside/, .txn/
    # and the top-level .lock to snap/shows/<slug>/<rel>, sha256-verified and flushed; record the
    # station manifest's sha256 (None: no station copy); manifest.json written last
    # {created_at, slugs, files: {"<slug>/<rel>": sha}, station: {slug: sha|None}}; any failure
    # removes the partial directory and raises LlamaError
def verify(snap: Path) -> list[str]                           # [] = verifies
def record_after(snap: Path, slug: str, root: Path, *, station_root: Path | None) -> None
    # append {slug, files: {rel: sha}, station: sha|None, at} to snap/after.jsonl; takes no lock:
    # the caller holds the show lock (reapply's after_commit hook, the backfill's per-show unit)
def restore(snap: Path, root: Path, *, station_root: Path | None, apply: bool,
            slugs: set[str] | None = None, echo) -> list[tuple[str, str]]   # (slug, action or refusal)
def seal(snap: Path, root: Path, *, station_root: Path | None) -> None    # per slug, under its show lock: record_after
```
- `restore`, per slug, under its show lock: no after-record → `untouched` when files and station equal the snapshot, else refuse `changed, and this batch recorded no write for it`. With an after-record: files ≠ after → refuse `library files changed after the batch: <first rel>`; station sha ≠ after → refuse `station manifest changed after the batch (re-delivered or re-voiced): roll forward instead`. Else: when the snapshot's `package/manifest.json` bytes differ from the current file, empty `package/audio/` first (flushed); delete tracked files absent from the snapshot; write the snapshot's files back atomically. Without `apply` it only reports. It never writes the station.
- [ ] **Step 1: Write the failing tests:** `test_take_copies_metadata_only_and_verifies` (audio excluded, `campaign.json` and `reuse-anchor.json` included; a tampered copy fails `verify`); `test_partial_snapshot_is_removed_on_failure`; `test_restore_rewinds_a_batch_write` (after a reapply-style rewrite + `record_after` → files byte-identical to the snapshot, created files gone, audio emptied because the manifest differs); `test_restore_refuses_a_later_library_change`; `test_restore_refuses_a_changed_station_manifest`; `test_restore_dry_run_writes_nothing`; `test_untouched_show_is_left_alone`.
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement** (port the copy/flush/verify pattern of `scripts/rekey_overrides.py` `_write_copy`/`_sync_dir`/`verify_snapshot`; do not import the script or change it here). **Step 4:** Full suite → PASS. Commit `feat(snapshot): per-batch library snapshots with a guarded restore`.

---

