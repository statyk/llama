Task 13 fix round 1 (105b0b7..8ce9aed): scoped re-review

- **Important (epoch check): ADDRESSED.**
  - fallback.py:107-108 runs `load_publish_state` then `check_epoch` before any PUT, and before `save_fallback_version`.
  - The test at test_fallback.py:124-132 covers it: state for epoch `eold` raises a PublishError matching "epoch", `puts() == []`, and no local version is recorded.
  - The implementer reports this test failed before the fix.
- **Minor 1 (exact Cache-Control): ADDRESSED.**
  - test_fallback.py:76-78 asserts IMMUTABLE on each of `0.aac`, `1.aac`, `notice.aac` and `index.json`, and `no-store` on the horizon.
  - Those strings match publish.py:44 (`IMMUTABLE`) and :47 (`STATE_CACHE`).
- **Minor 2 (bool return): ADDRESSED.**
  - In fallback.py:98-125, the function returns False when there is no horizon yet or the high-water rule defers the rewrite, and True after the horizon PUT. The docstring states this.
  - Each of the four upload tests now asserts the return value with `is True` / `is False`.
- **New breakage in the fix diff: none.**
  - Moving `load_publish_state` above the uploads changes nothing. The read is still under `publish_lock`, and the only write in between (`save_fallback_version`) goes to a different file.
  - The guard check still runs first, and the upload order is unchanged.
- **Out of scope:**
  - The Debian-12 gate was not re-run for this round. The fix touches no ffmpeg path, so this is acceptable.
  - The whole-branch review should confirm that Task 14's CLI uses the returned bool.

Verdict: Approved
