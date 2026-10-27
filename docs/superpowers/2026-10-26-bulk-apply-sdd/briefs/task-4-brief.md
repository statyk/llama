### Task 4: Awaiting fix in `status` and `deliver`

**Spec:** "The library side" (Awaiting fix). **Implementer: Sonnet.**

**Files:** Modify `catalog.py` (`CatalogEntry`, `iter_shows`, `select_shows`), `campaign.py` (`frozen_slugs`), `cli_select.py` (`Selector`, `build_selector`, `selector_active`, `apply_selector`), `cli.py` (`status`, `_deliver_one`, `_deliver_batch`); Test `test_status_cmd.py`, `test_cli_select.py`, `test_deliver_cmd.py`.

**Interfaces:**
- Consumes: Task 3.
- Produces: `CatalogEntry.awaiting_fix: bool = False` (an unreadable record → True); `Selector.awaiting_fix: bool = False`; `build_selector(..., awaiting_fix: bool = False)`; `select_shows(..., awaiting_fix: bool = False)`; `status --awaiting-fix`; status row mark `awaiting-fix`; status JSON key `awaiting_fix`; `class _AwaitingFix(LlamaError)` in `cli.py`; in `campaign.py`, `FROZEN_FILE = "campaign/needs-llm-frozen.json"` and `frozen_slugs(root: Path) -> frozenset[str]` (the file's `slugs`; empty when missing or unreadable). The deliver `reapply` pointer adds ` --with-gather-llm` when the slug is in `frozen_slugs(config.root)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_status_marks_and_selects_awaiting_fix`: two packaged shows, one with an awaiting record → its row carries `[awaiting-fix]`; `--awaiting-fix` lists only it; `--json` has `"awaiting_fix": true`.
  - `test_deliver_refuses_awaiting_fix_by_name`: exit 1, stderr is the deliver awaiting string and the `reapply` pointer; a `select` start prints the `redo --from select` pointer; nothing copied, no ledger row.
  - `test_deliver_pointer_names_with_gather_llm_for_a_frozen_show`: the slug in `<root>/campaign/needs-llm-frozen.json` → the pointer line ends `--allow-structure-change --with-gather-llm`; a corrupt frozen file → the plain pointer.
  - `test_deliver_batch_skips_awaiting_fix`: `deliver --packaged --yes` delivers the other show and prints the awaiting one with `  (refused: awaiting fix)`.
  - `test_processed_show_delivers` **(pin)**.
  - `test_unreadable_campaign_record_counts_as_awaiting` (Review Focus 5): `status` marks it, `deliver` refuses with the campaign-record string.
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement**; in `_deliver_one` the check is the first one under the show lock, before the voiced check. **Step 4:** Full suite → PASS. Commit `feat(cli): awaiting-fix shows in status, refused by deliver`.

---

