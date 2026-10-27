### Task 5: The station mark writer and deliver over a marked copy

**Spec:** "The `awaiting_fix` contract" (Writing a mark, No concurrent emcee, It clears by re-delivery, the `--replace-voiced` paragraph), "Delivery after the fix" (selector). Strict surfaces 1-2. **Implementer: Opus.**

**Files:** Create `packages/llama/src/llama/station_mark.py`, `packages/llama/src/llama/campaign_gate.py` (`tool_processes` and `ps_lines` only; Task 12 adds the rest); Modify `cli.py` (`_deliver_one`, `_deliver_batch`, `deliver`); Test `packages/llama/tests/test_station_mark.py` (new), `packages/llama/tests/test_campaign_gate.py` (new), `test_deliver_cmd.py`.

**Interfaces:**
- Produces in `station_mark.py`:

```python
MARK_KEY = "awaiting_fix"
COMPARED = ("source.identifier", "show.venue", "show.city", "show.date", "tracks.filename",
            "tracks.duration_sec", "tracks.title", "tracks.set", "tracks.segue", "set_breaks")
class StationRefused(LlamaError): ...
class StationUnreadable(StationRefused): ...   # text "<slug>: station copy unreadable: <detail>"; the ONE
                                               # "unreadable" exception (Task 8 raises it, Task 13 counts it)
def read_station_manifest(out: Path) -> tuple[bytes, dict]   # StationUnreadable: dir or file missing, OSError, invalid JSON, not an object
def mark_of(manifest: dict) -> dict | None
def destination_voiced(out: Path) -> bool                    # StationUnreadable: dir or manifest missing or unreadable; call it for delivered shows only
def write_mark(out: Path, *, reason: str, marked_at: str) -> tuple[bytes, bytes]   # (before, after)
def clear_mark(out: Path) -> tuple[bytes, bytes]
def put_back(out: Path, *, expect_sha256: str, data: bytes) -> None   # the reversal: replace only when the file's sha256 equals expect_sha256
def manifest_differences(library: dict, station: dict) -> list[str]   # the COMPARED names that differ, raw JSON values
def emcee_running() -> list[str]   # campaign_gate.tool_processes(campaign_gate.ps_lines(), "emcee", self_pid=os.getpid())
```
- Produces in `campaign_gate.py`: `ps_lines() -> list[str]` (`ps -axo pid=,ppid=,command=`) and `tool_processes(ps_lines: Iterable[str], tool: str, *, self_pid: int) -> list[str]`, ported from `scripts/rekey_overrides.py` `llama_processes`/`_runs_llama` with the tool name a parameter (`self_pid` and its ancestors never match). The script is not changed here.
- The rewrite algorithm (spec, pinned): the caller holds the llama show lock; re-read the raw bytes and dict; add or remove only `MARK_KEY` (key order otherwise preserved; trailing newline kept as the original had it; `json.dumps(…, indent=2)`); write a unique temp in the same directory and flush it (`catalog._flush_to_disk`); re-read the station file's bytes immediately before the rename and, when they differ from the bytes read, remove the temp and raise `StationRefused` (retryable, nothing written); `os.replace`; re-read and require every other key equal to the dict read and `MARK_KEY` equal to what was written. On a mismatch after the rename: when the file still holds the bytes this call wrote, write `before` back; raise `StationRefused`. Never `Manifest`; `tracks`, `dj_notes`, `dj_audio` untouched by construction. A write landing between the last byte check and the rename is overwritten undetected (documented limitation, Review Focus 1); the per-write `emcee_running()` check is the primary guard.
- `deliver`: a destination whose manifest `mark_of(...)` is non-null always goes through `_replace_destination`; `--replace-voiced` on a marked destination whose `manifest_differences(library, station) == []` refuses with the fixed string; `deliver --fixed` (selector) keeps only shows that are not awaiting fix, whose record is processed, and whose station manifest is marked; it combines with the other selectors and refuses `--replace-voiced` like them.

- [ ] **Step 1: Write the failing tests** (`test_station_mark.py`, fixture station dirs under `tmp_path`):
  - `test_write_mark_adds_only_the_key`: every other key equal, `tracks` byte-for-byte in the re-read dict, `dj_audio` untouched, mtime changed; `clear_mark` returns a dict equal to the original.
  - `test_unreadable_or_malformed_manifest_is_refused_and_untouched` (missing file, missing dir, invalid JSON, a JSON list): `StationUnreadable` with the fixed text, bytes unchanged; `destination_voiced` on a missing dir or a dir without a manifest raises `StationUnreadable`.
  - `test_write_mark_detects_a_concurrent_rewrite` (Review Focus 1): monkeypatch the temp flush so another writer changes `dj_audio` after the read and before the rename → `StationRefused`, the file holds the other writer's bytes, no temp left in the directory.
  - `test_write_mark_detects_a_rewrite_after_the_rename`: monkeypatch `os.replace` so another writer changes `dj_audio` right after the rename → `StationRefused`, and the file holds the other writer's content (never `before` over it).
  - `test_put_back_requires_the_expected_sha`.
  - `test_manifest_differences`: equal manifests (differing only in `dj_*`, `awaiting_fix`, `briefing`) → `[]`; a moved set label → `["tracks.set"]`; a changed duration → `["tracks.duration_sec"]`.
  - `test_tool_processes` (`test_campaign_gate.py`): rekey's `llama_processes` cases re-run with `tool="llama"`; for `tool="emcee"`, `emcee run`, `/path/.venv/bin/emcee voice x`, `python -m emcee` match, `grep emcee`, `vim emcee.toml` and the caller's own pid and ancestors do not.
  - `test_emcee_running_reads_ps` (monkeypatched `ps_lines`).
- [ ] **Step 2:** Deliver tests (`test_deliver_cmd.py`): `test_marked_destination_is_always_replaced` (same track list, unvoiced, marked → the staged swap runs, the mark is gone, no `.old-*` left); `test_replace_voiced_refuses_an_equal_marked_copy`; `test_replace_voiced_replaces_a_changed_marked_copy` **(pin)**; `test_deliver_fixed_selects_marked_and_processed` (also a voiced, marked, processed show: the `--fixed` batch refuses it, its station manifest bytes and `dj_audio` unchanged); `test_unmarked_voiced_destination_keeps_todays_route` **(pin)**.
- [ ] **Step 3:** Run → FAIL. **Step 4: Implement.** **Step 5:** Full suite → PASS. Commit `feat(station): awaiting_fix writer; deliver replaces a marked copy, --fixed selector`.

---

