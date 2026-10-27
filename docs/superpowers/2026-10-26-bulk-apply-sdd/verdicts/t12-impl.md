# T12 handback
Status: DONE. Commit: see `git log -1` (feat(campaign): version and pin gates, bulk_apply scaffold, rekey restore retired).
Implemented in campaign_gate.py: CAMPAIGN_MIN_VERSION="2.20.0", GateRefused, version_ok/version_newer, tool_versions, require_tools, read_pin/write_pin/require_pinned_code, retire_rekey_restore. scripts/bulk_apply.py: pin/arm/snapshot/seal/restore (exit 2 on refusals; module-level REPO/code_identity/replay_holds/require_tools are monkeypatch seams). rekey `_record_gate` refuses `retired` with the fixed string.
Tests (9 new): test_version_gate, test_pin_roundtrip_and_replace, test_require_pinned_code, test_retire_is_idempotent (campaign_gate); test_pin_requires_the_running_code, test_arm_refuses_without_a_pin, test_arm_runs_the_replay_over_all_shows, test_restore_cli_dry_run_reports (scaffold); test_retired_record_refuses_restore (rekey). No existing test expectation moved.
RED: `./.venv/bin/python -m pytest <3 files> -q -k "version_gate or pin or retire or arm or restore_cli or retired"` -> 9 failed (scaffold file first ImportError at collection, then with a NotImplementedError stub bulk_apply all 5 scaffold tests failed; gate tests AttributeError; rekey test did not raise).
GREEN: full `./.venv/bin/python -m pytest -q` -> 6219 passed, 1 skipped, 8 deselected.
Concerns: restore dry run exits 1 if any row is "refused:" (my choice; brief silent). Pin tests monkeypatch bulk_apply.REPO/code_identity; arm test patches llama.replay.code_identity. Log: t12-impl.log.

## Fix round 1
Changes: cmd_pin derives version from the tag (strip one leading v, must fullmatch _VERSION, else GateRefused naming the tag); write_pin refuses a malformed version; _write_json now calls batch_snapshot._sync_dir(path.parent) after the replace.
New tests (RED first: 5 failed, 12 passed): test_write_pin_refuses_a_malformed_version, test_write_json_syncs_the_directory, test_pin_version_comes_from_the_tag, test_pin_refuses_a_tag_that_is_not_a_version, test_pin_and_tool_gate_agree_end_to_end.
GREEN: `./.venv/bin/python -m pytest -q` -> 6224 passed, 1 skipped, 8 deselected.
