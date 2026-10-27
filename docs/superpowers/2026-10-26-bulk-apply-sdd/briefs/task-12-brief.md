### Task 12: Campaign gates, the pin, `bulk_apply.py` scaffold, rekey retirement

**Spec:** "Rollout" (version gate), "Known constraints" (pinned worktree, newer-installed refusal), "Undo" (rekey retired). **Implementer: Sonnet.**

**Files:** Create `scripts/bulk_apply.py`; Modify `packages/llama/src/llama/campaign_gate.py` (Task 5 created it with `tool_processes`/`ps_lines`), `scripts/rekey_overrides.py` (`_record_gate`); Test `packages/llama/tests/test_campaign_gate.py`, `scripts/test_bulk_apply_scaffold.py` (new), `scripts/test_rekey_overrides.py`.

**Interfaces:**
- Consumes: Task 5 (`campaign_gate.tool_processes`, `ps_lines`: the one process parser; no second one here).
- Produces in `campaign_gate.py` (beside Task 5's two functions):

```python
CAMPAIGN_MIN_VERSION = "2.19.0"       # the release this build ships in; confirm at release
class GateRefused(LlamaError): ...
def version_ok(text: str, minimum: str) -> bool        # rekey's rule, parameterised
def version_newer(text: str, than: str) -> bool
def tool_versions(tool: str) -> list[tuple[str, str]]  # `which -a <tool>` then `<path> --version`
def require_tools(echo, *, pin: dict | None) -> None
    # every llama and emcee on PATH >= CAMPAIGN_MIN_VERSION, and (with pin) no llama newer than pin["version"]
def read_pin(root: Path) -> dict | None
def write_pin(root: Path, *, tag: str, sha: str, version: str, worktree: str, replace: bool) -> dict
def require_pinned_code(root: Path) -> dict            # pin exists; replay.code_identity() == pin["sha"] (never -dirty)
def retire_rekey_restore(root: Path, *, by: str, at: str) -> bool
    # adds "retired": {at, by} to <root>/rekey-applied.json, durably; idempotent: True only when it
    # wrote, False when the file is absent or already retired (the first `retired` stays)
```
- `scripts/bulk_apply.py` (argparse, subcommands; exit 2 on a `GateRefused`/refusal, like `replay_holds.py`): `pin --tag vX.Y.Z [--replace]` (resolves `git rev-parse <tag>^{commit}`, requires it equal `code_identity()`); `arm --out <arm.json>` (`require_pinned_code` + `require_tools(pin=…)`, then `replay_holds.run` with `--all`); `snapshot --slugs <file>` → `<root>/campaign/snapshots/<stamp>/`; `seal <snap>`; `restore <snap> [--apply] [--slugs <file>]`. Later tasks add subcommands to this file.
- `rekey_overrides._record_gate` refuses with the rekey fixed string when the record has `retired`.
- `retire_rekey_restore` is called by whichever bulk write comes first, and harmlessly by every later one: backfill `--apply` (Task 14), `mark --apply` (Task 15), and a campaign list wave (Task 13).

- [ ] **Step 1: Write the failing tests:** `test_version_gate` (`2.19.0` ok, `2.18.0`/`0.1.0`/`2.19.0rc1` refused, for both tools; a pin of `2.19.0` and an installed `2.20.0` refused naming the path); `test_pin_requires_the_running_code` (a dirty tree and a mismatched tag refused; `--replace` needed to overwrite); `test_arm_refuses_without_a_pin`; `test_restore_cli_dry_run_reports`; `test_retired_record_refuses_restore` (scripts test: `_record_gate` raises with the fixed string; the rest of rekey's tests unchanged); `test_retire_is_idempotent` (a second call returns False and leaves `rekey-applied.json` byte-identical; absent file → False, nothing created).
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(campaign): version and pin gates, bulk_apply scaffold, rekey restore retired`.

---

