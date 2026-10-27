### Finding Verdicts
- **CRITICAL: `cmd_pin` stored `llama.__version__` (0.1.0 / `0.0.0+unknown`), so `require_tools(pin=pin)` refused or crashed every arm/wave/mark.** ADDRESSED.
  - `scripts/bulk_apply.py:50-54`: the version now comes from the tag. The code strips one leading `v`, requires `_VERSION.fullmatch`, raises `GateRefused` naming the tag otherwise, and passes the result to `write_pin`. A `vv2.20.0` tag is refused, as it should be.
  - `packages/llama/src/llama/campaign_gate.py:238-239`: `write_pin` refuses a malformed version before anything is read or written. Pinned by `test_write_pin_refuses_a_malformed_version` (`0.0.0+unknown`, `2.20.0rc1`, empty, `release-x`), which also asserts that no pin was written.
  - Pin and gate are tested together in `scripts/test_bulk_apply_scaffold.py::test_pin_and_tool_gate_agree_end_to_end`. It sets `__version__` to `0.0.0+unknown`, writes the pin through `ba.main(["pin", ...])`, and runs the real `require_tools` against stubbed 2.20.0 `llama`/`emcee`. That reaches the `version_newer(out, pin["version"])` branch (`campaign_gate.py:210`).
  - The test fails if the fix is reverted. With the old `version=llama.__version__`, `write_pin` now refuses `0.0.0+unknown`, so `main` returns 2. Without `write_pin`'s check, `_numeric` would raise `ValueError` in `require_tools`. `test_pin_version_comes_from_the_tag` (`__version__` = 0.1.0, expects 2.20.0) and `test_pin_refuses_a_tag_that_is_not_a_version` cover the remaining paths.
- **IMPORTANT: `_write_json` did not sync the parent directory after `_durable_replace`.** ADDRESSED.
  - `campaign_gate.py:229-233` now calls `batch_snapshot._sync_dir(path.parent)` after the replace. That covers both callers: `write_pin` (`:244`) and `retire_rekey_restore` (`:275`).
  - `_durable_replace` does not sync the directory itself (`batch_snapshot.py:93-95`, "the caller syncs the directory"). So the exact-list assertions in `test_write_json_syncs_the_directory` (`[root/"campaign"]`, then `[root]`) count only this call, and fail if the line is removed.
  - The call goes through the module attribute, so the monkeypatch really intercepts it.

### New Breakage in the Fix Diff
No Critical or Important issues. Minor:
- **Minor: `scripts/bulk_apply.py:18` keeps `import llama`, which production code no longer uses.** It exists only so the tests can `monkeypatch.setattr(ba.llama, "__version__", ...)`. The patch itself is worth keeping: it is what makes the two pin tests fail on a revert to `__version__`. If someone later "cleans up" the import, the tests fail loudly at `setattr`, so nothing goes silently wrong. Acceptable as is. The cleaner form is to patch the module directly in the tests (`import llama; monkeypatch.setattr(llama, "__version__", ...)`) and drop the import from the script. No lint config in the repo flags it.
- **Minor: `campaign_gate.py:231-233` does not sync the new directory's own entry.** `_write_json` syncs `path.parent`, but when the first `pin` creates `root/campaign`, the entry for `campaign` inside `root` is never synced. The snapshot writer syncs `snap.parent` for exactly this case (`batch_snapshot.py:228`). A crash at that moment loses the pin, and the next arm/wave refuses with "no pin", so the failure is safe. Only the first pin is affected. `rekey-applied.json` sits directly in `root`, so its retirement is not affected.
- **Minor: `scripts/bulk_apply.py:20` imports the private `_VERSION` from `campaign_gate`.** The cross-module private use is consistent with the module's existing use of `batch_snapshot._durable_replace`/`_sync_dir`. A public alias, or one helper that turns a tag into a version, would read better. Cosmetic.

### Out-of-Scope Observations
- If `_sync_dir` raises after the replace has already landed, the pin file exists but `cmd_pin` reports an error. A re-run then needs `--replace`. The order is not new; it is a rare edge, and there is no data hazard.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage. Three Minor items, all non-blocking: the vestigial `import llama` seam, the unsynced entry for the first `campaign/` directory, and the private `_VERSION` import.
