### Spec Compliance
- ❌ Issues found:
  - `scripts/bulk_apply.py` `cmd_pin` (diff: `write_pin(root, tag=args.tag, sha=sha, version=llama.__version__, ...)`): the pin's `version` is taken from `llama.__version__`, which in the pinned worktree is `0.1.0`. The spec ("Known constraints": "pinned to a release tag's commit, with that release's version stored beside the pin"; "its dev `llama` reports 0.1.0") calls for the release's version. Consequence: every `arm` (and every later wave or mark that calls `require_tools(pin=...)`) refuses with "llama newer than the pinned 0.1.0". See Critical 1.
  - `campaign_gate.retire_rekey_restore` / `_write_json` (`campaign_gate.py`, `_write_json`): the brief says the retirement is written "durably", but `batch_snapshot._durable_replace`'s docstring says "the caller syncs the directory", and `_write_json` never calls `_sync_dir(path.parent)`. The same applies to `pin.json`. See Important 1.
- Everything else matches the brief, with `CAMPAIGN_MIN_VERSION = "2.20.0"` per the parent ruling:
  - `GateRefused(LlamaError)`, `version_ok`/`version_newer`, `tool_versions` (`which -a`, then `<path> --version`), `require_tools` (both tools at least the minimum, llama not newer than the pin), `read_pin`/`write_pin` (`--replace` needed to overwrite), `require_pinned_code` (sha equality, so `-dirty` and `version:` identities are refused).
  - `retire_rekey_restore` is idempotent: it returns False when the file is absent and when it is already retired.
  - The `_record_gate` fixed string is byte-exact, and the test asserts it with `==`.
  - `bulk_apply.py` has the subcommands `pin`/`arm`/`snapshot`/`seal`/`restore` and exits 2 on GateRefused or LlamaError.
  - `arm` reuses `replay_holds.run` with `all=True` and no second process parser. `tool_processes`/`ps_lines` are untouched.
  - Every brief test name is present except one: `test_pin_requires_the_running_code` lives in the scripts test and the campaign_gate tests are split differently. That is acceptable.
- ⚠️ Cannot verify from the diff: whether Tasks 13-15 will pass a pin whose `version` is meaningful. Today no code path produces one; see Critical 1.

### Strengths
- The version rule is a faithful parameterisation of rekey's (`rekey_overrides.py:779-810`): fullmatch on a dotted version, numeric compare, and `rc1`, `0.1.0` and multi-line output all refused. Failing binaries report `exit <n>:`/`error:` text, which `version_ok` refuses.
- `_record_gate` checks `retired` after the readable/snapshot-name check and before the snapshot-name mismatch. Any snapshot asked for is therefore refused. The check runs both before and under the lock, because rekey's `restore` calls `_record_gate` at lines 1397 and 1409, before any write.
- The retirement merges into the existing record, so `snapshot` and `shows` are preserved and the first `retired` stays. The test proves both calls byte-identical, and that an absent file gives False with nothing created.
- `arm` goes through `replay_holds.run`, so it inherits `_check_identity` (`replay_holds.py:212`) and the `--out`-overlaps-library refusal.
- Test stubs replace only `subprocess.run`, so the real `which`/`--version` parsing and gate logic run under test. `test_restore_cli_dry_run_reports` drives the real `batch_snapshot` through the CLI: snapshot, a recorded write, a dry run that writes nothing, apply restores, seal, and a missing snapshot gives 2.
- Untouched items: the diff touches none of `DURATION_TOLERANCE_S`, `STOP_AFTER_LLM_FAILURES`, `load_list`, `briefing_reusable`, `purge_package_audio`, the junk constants or the `Manifest` model. `emcee` appears only as a subprocess tool name, never as an import.

### Issues
#### Critical (Must Fix)
1. **`scripts/bulk_apply.py` `cmd_pin`: the pin's version is `llama.__version__`, which is `0.1.0` in the pinned worktree, so the campaign's newer-installed gate refuses every real run.**
   - **What I checked.** `packages/llama/src/llama/__init__.py` reads `_version.py`, which is gitignored and only written at freeze time. Otherwise it falls back to package metadata, and `pyproject.toml` says `version = "0.1.0"`. In this worktree, `./.venv/bin/python -c "import llama; print(llama.__version__)"` prints `0.1.0`, and `campaign_gate.version_newer('2.20.0', '0.1.0')` is True.
   - **What happens.** After `bulk_apply.py pin --tag v2.20.0`, the pin records `version: "0.1.0"`. Then `arm` runs `require_tools(pin=pin)` and refuses `llama newer than the pinned 0.1.0: <path> 2.20.0`, as will every Task 13-15 caller. In a raw checkout with no metadata, `__version__` is `0.0.0+unknown`, and `_numeric("0.0.0+unknown")` raises ValueError: a traceback, not a GateRefused.
   - **Why the tests missed it.** `test_pin_requires_the_running_code` never asserts `pin["version"]`. `test_arm_runs_the_replay_over_all_shows` writes the pin by hand with `version="2.20.0"` and monkeypatches `require_tools`, so pin and gate are never exercised together.
   - **Fix.**
     - Derive the version from the tag: strip a leading `v` and require `_VERSION.fullmatch`, or require an explicit `--version` that must equal the tag.
     - Make `write_pin` refuse with GateRefused when the version does not fullmatch `_VERSION`, so `require_tools` can never crash on `pin["version"]`. Today a missing key is a KeyError and a malformed value is a ValueError.
     - Add a test that runs `cmd_pin` with `llama.__version__` patched to `0.1.0` and asserts the stored version is `2.20.0`.
     - Add a test that `require_tools(pin=read_pin(root))` passes against installed `2.20.0`.

#### Important (Should Fix)
1. **`packages/llama/src/llama/campaign_gate.py` `_write_json`: the rename is not durable.**
   - **What is wrong.** `_durable_replace` fsyncs the temp file and renames it, but by its own contract (`batch_snapshot.py:93-95`) "the caller syncs the directory". `_write_json` does not. The brief requires `retired` to be added "durably".
   - **Why it matters.** If the machine crashes after the first bulk write but before the directory entry is flushed, `rekey-applied.json` can revert to its unretired version. rekey's `--restore` would then be available again over writes that postdate its snapshot, and that is the hazard the retirement exists to block. The probability is low, but it is the one guard against a destructive restore.
   - **Fix.** Call `_sync_dir(path.parent)` after `_durable_replace`; it is a one-liner. Also consider exposing a public helper rather than importing two `_private` names from `batch_snapshot`.

#### Minor (Nice to Have)
1. **`campaign_gate.retire_rekey_restore`: writer and reader disagree on what counts as retired.**
   - The writer treats `"retired" in rec` as retired, while `_record_gate` (`rekey_overrides.py`, the new `if retired is not None`) treats only a non-null value as retired.
   - A record carrying `"retired": null` (hand edit only) is therefore never retired, and restore stays open.
   - Fix: test `rec.get("retired") is not None` in the writer.
2. **`campaign_gate.retire_rekey_restore`: an unreadable or non-dict record silently returns False, the same as "absent".**
   - This is safe today, because `_record_gate` refuses an unreadable record anyway.
   - But Tasks 13-15 cannot tell "nothing to retire" from "could not read the record", so they cannot echo a warning.
   - Consider returning or raising distinctly, or at least documenting the case for callers. The unreadable branch is also untested.
3. **`scripts/bulk_apply.py` `cmd_pin`: the identity tree is not checked against the recorded worktree.**
   - The tag is resolved in `REPO`, the scripts' tree, while `code_identity()` reads the git of `llama.__file__`'s tree, and `worktree` is recorded as `REPO`.
   - With the wrong interpreter (a CLAUDE.md-documented trap), the recorded worktree is not the tree whose code was checked. Sha equality still holds because tags are repo-global, so this is not unsafe, just misleading.
   - Fix: call `replay_holds._check_identity()` at the top of `cmd_pin`.
4. **`scripts/bulk_apply.py` `main`: some errors escape as tracebacks.**
   - It catches only `GateRefused`/`LlamaError`.
   - A missing `--slugs` file (`_read_slugs` raises OSError) or a `replay_holds.Refusal` from anywhere but `arm` gives a traceback rather than an exit-2 refusal.
   - Fix: catch OSError around the slug read, or in `main`.
5. **Restore exit codes.**
   - The implementer's choice is reasonable: 1 when any row reads `refused:` (dry run included, so the operator sees that an apply would be partial) and 2 for whole-command refusals. It matches rekey's convention of rc 1 for a partial restore.
   - However, the module docstring documents only "A refused gate exits 2", and no test asserts the `1` path.
   - Fix: document exit 1 in the docstring and add a refused-row case to `test_restore_cli_dry_run_reports`, for example a show changed after `record_after`.
6. **Duplication of rekey's version rule.**
   - `_VERSION`, `_numeric`, `_cmp` and `tool_versions` duplicate `rekey_overrides.py:779-830` almost verbatim.
   - This is acceptable: the brief says "rekey's rule, parameterised", rekey is a retired one-off, and Task 5 kept the script's own copy. Note it for the final review.
7. **Style.**
   - `packages/llama/tests/test_campaign_gate.py` puts module imports mid-file (`import json as _json`, `import pytest`, ...).
   - `campaign_gate.py` imports `Path` and `PurePosixPath` on two lines.
   - `_config` in `bulk_apply.py` re-implements `replay_holds.run`'s config resolution.
   - All cosmetic.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The gates, the retirement and the scaffold are well built and well tested in isolation. But `pin` stores the worktree's dev version (`0.1.0`), so the "installed llama newer than the pin" gate refuses every real `arm` and every later wave. The tests never check pin and gate together, which is why it passed. The retirement write also skips the directory sync its helper requires the caller to do.
