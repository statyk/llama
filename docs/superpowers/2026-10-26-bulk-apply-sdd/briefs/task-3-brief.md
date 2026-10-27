### Task 3: The campaign record and "processed"

**Spec:** "The library side", "Writing a mark" (campaign half). **Implementer: Sonnet.**

**Files:** Create `packages/llama/src/llama/campaign.py`; Modify `workspace.py` (`ShowWorkspace.campaign`, `.reuse_anchor`), `replay.py` (visible-change helpers), `cli.py` (`_redo_show_locked`), `stages/package.py` (`build_package` tail); Test `packages/llama/tests/test_campaign.py` (new), `test_replay.py`.

**Interfaces:**
- Produces in `campaign.py`:

```python
CAMPAIGN_FILE = "campaign.json"
class CampaignUnreadable(LlamaError): ...
class CampaignMark(BaseModel): at: str; reason: str; start_stage: Literal["gather", "select"]; batch: str
class CampaignProcessed(BaseModel): at: str; digests: dict[str, str | None]; manifest_sha256: str | None
class CampaignClear(BaseModel): at: str; outcome: Literal["equal", "change accepted"]
class CampaignRecord(BaseModel):
    marks: list[CampaignMark] = []; processed: CampaignProcessed | None = None; clears: list[CampaignClear] = []
def read_record(ws: ShowWorkspace) -> CampaignRecord | None          # None: no file; CampaignUnreadable otherwise
def awaiting_fix(rec: CampaignRecord | None) -> bool
def last_mark(rec: CampaignRecord | None) -> CampaignMark | None
def add_mark(ws, *, reason: str, start_stage: str, batch: str, at: str) -> None   # durable write
def remove_marks(ws, batch: str) -> int                              # the reversal; count removed
def mark_processed(ws, *, held: bool) -> bool                        # False (nothing written) without a record
def after_package(ws) -> None        # a processed record's manifest_sha256 refreshed from package/manifest.json
def add_clear(ws, outcome: str) -> None
def manifest_sha256(ws) -> str | None
```
- `ShowWorkspace.campaign = dir / "campaign.json"`, `ShowWorkspace.reuse_anchor = dir / "reuse-anchor.json"`; neither is in `show_stage_artifacts` nor in `replay.input_digests`.
- Produces in `replay.py`: `VISIBLE_FIELDS = ("files", "titles", "sets", "segues", "set_breaks", "venue", "city", "date")`; `visible_changes(stored: Show, new: Show) -> list[str]` (filenames compared, so a same-count file swap counts; titles by text only); `row_visible_changes(row: dict, stored: Show) -> list[str]` (arm row: `filenames`, `title_changes` old≠new, `set_changes`, `segue_changes`, `set_breaks`, `venue`, `city`, `date`); `row_label_only(row: dict, stored: Show) -> bool` (no visible change, and a `title_source` or `alignment` change).

- [ ] **Step 1: Write the failing tests:**
  - `test_awaiting_fix_follows_marks_and_processed`: no record → False; one mark → True; processed after it → False; a later mark → True.
  - `test_mark_processed_writes_digests_and_sha`: a packaged show → `manifest_sha256 == sha256(package/manifest.json)`, `digests == input_digests(ws)`; `held=True` → `manifest_sha256 is None`; no record → returns False, writes nothing.
  - `test_redo_from_the_recorded_stage_marks_processed`: a record with start `gather`; `_redo_show` from `gather` (stubbed stages) → processed; from `brief` → still awaiting; start `select` and redo from `gather` → still awaiting; a failing redo → the unit restores `campaign.json` byte-identical.
  - `test_redo_refuses_an_unreadable_record_before_any_stage`: a corrupt `campaign.json` → `CampaignUnreadable`, the stubbed stages and providers record zero calls.
  - `test_package_build_on_processed_show_refreshes_manifest_sha`: processed, then `redo --from package` producing a different manifest → `manifest_sha256` equals the new manifest's.
  - `test_unreadable_record_raises` and `test_record_is_not_an_input_digest` **(pin)**.
  - `test_visible_changes_and_label_only`: a filename swap with equal titles → `["files"]`; a title_source-only change → `[]` and `row_label_only` True; `row_visible_changes` on a `replay_show` row equals `visible_changes` on the same legs.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.** Writes use `atomic_write_bytes` followed by `catalog._flush_to_disk` on the file. `_redo_show_locked`: `rec = read_record(ws)` BEFORE `process_show` (an unreadable record refuses before any spend); after `process_show` returns, when `rec` and `SHOW_STAGE_ORDER.index(from_stage) <= SHOW_STAGE_ORDER.index(last_mark(rec).start_stage)`, `mark_processed(ws, held=pkg is None)`. `build_package` calls `campaign.after_package(show_ws)` after the manifest write. `mark_processed` imports `input_digests` inside the function (`replay` imports the stages).
- [ ] **Step 4:** Full suite → PASS. Commit `feat(campaign): per-show campaign record, processed on a committed re-gather`.

---

