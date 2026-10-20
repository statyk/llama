### Finding Verdicts

- **Important 1: zero-writes test cannot see a write whose error is swallowed.** ADDRESSED.
  - `scripts/test_replay_holds.py:167-183`: `test_run_writes_only_the_arm_and_empties_its_scratch` now runs on a writable root, snapshots it before the run (`:174`), and asserts `_tree_state(root) == before` after it (`:179`).
  - The reviewer's mutant writes `ws.dir / "probe"`. `ws.dir` is the real library show directory (`packages/llama/src/llama/replay.py:290`, "`ws.dir` is only read"), so on a writable root the probe persists as a new key and the assertion fails.
  - The outcome check `{clears, clean}` (`:181-182`) proves the run actually replayed rather than passing over nothing.
  - `_tree_state` (`:19-31`) now records directories as `("dir", mtime_ns)` and includes the root itself (`"."`). A created empty directory shows up as a new key, and a create-then-delete moves the parent's mtime.
  - The helper is pinned by `test_tree_state_sees_an_empty_directory_and_a_deleted_file` (`:186-196`).
  - The fix report (`t5-impl/handback.md`, "Fix round 1") names the covering tests: 21 passed in the file, and the full suite 3271 passed. It also gives a mutant proof that follows the copy/PYTHONPATH-shadow/private-pycache recipe, with the prediction logged first. The mutant is caught by exactly the predicted test (1 failed, 20 passed).
  - I read and checked this against the diff and did not re-run it: no specific doubt arose.

### New Breakage in the Fix Diff

- Minor, `scripts/test_replay_holds.py:193-196`: the "deleted file" half of the helper test depends only on `cache/`'s mtime moving between `build_library`'s write into `cache/` (`fixture_library.py:46`) and the probe create/unlink a few microseconds later.
  - On APFS (ns timestamps), where this suite runs, that holds.
  - On a Linux filesystem with coarse (jiffy-granular) inode timestamps, both events could land in the same tick, and the assertion would then fail spuriously.
  - It is not currently reachable: `.github/workflows/release.yml` runs no pytest, and only the transmitter tests run on Debian.
  - It is worth noting if the scripts suite ever runs on Linux CI.
  - It is a false failure, never a false pass, so it does not weaken the zero-writes check.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
