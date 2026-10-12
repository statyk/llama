### Finding Verdicts
- Finding 2 (scan's per-entry checks on 3.11): ADDRESSED.
  - `station.py:218-224`: `entry.is_dir()` and `(entry/"manifest.json").exists()` now sit inside `try/except OSError`. A failure appends `Ineligible(entry.name, ("changing: …",))` and continues.
  - Re-ran my real-3.11 probe against a scratch `git archive` of 8bc35a7 (PYTHONPATH-shadowed; the import path was confirmed to be inside the scratch copy). A marker root plus one `chmod 000` subdirectory now returns `([], [Ineligible('c-locked', ("changing: [Errno 13] Permission denied: …/c-locked/manifest.json",))])`. At 6ad53ff it raised `PermissionError`.
  - Pinned by `test_scan_skips_a_package_whose_manifest_check_raises` and `test_scan_skips_a_package_whose_is_dir_raises` (both RED before the fix).
- (a) `iterdir` OSError → `StationRootError`: ADDRESSED.
  - `station.py:211-214` wraps `sorted(root.iterdir())`, which forces the lazy generator inside the `try`.
  - Real-3.11 probe: a marker root with mode 0311 (executable, not readable) raises `StationRootError: station root <root> cannot be listed: [Errno 13] …`. 3.14 behaves the same.
  - Pinned by `test_scan_listing_failure_is_station_root_error`.
- (b) narrow the `RuntimeError` catch: ADDRESSED.
  - `station.py:81-82`: only `_inside`'s `resolve()` catches `RuntimeError`, and it re-raises it as `OSError(ELOOP, …)`.
  - `station.py:115` now catches `OSError` only, so `NotImplementedError` and `RecursionError` propagate again.
  - Real-3.11 probe on an actual `a→b→a` symlink loop: `_inside` raises `OSError [Errno 62] symlink loop resolving a/x.mp3: …`, which `evaluate` maps to `changing:`.
  - The existing `test_symlink_loop_runtimeerror_is_changing` (monkeypatched `Path.resolve` raising `RuntimeError`) still passes through the new conversion path.
- (c) `UnicodeDecodeError` labelled `unreadable broadcast.m3u: …`: ADDRESSED.
  - `station.py:165-168` catches `UnicodeDecodeError` around `read_m3u` only.
  - The `evaluate` wrapper no longer catches it. That is correct: `broadcast.m3u` is the only remaining decode site, and `manifest.json`'s decode is already caught as `ValueError` at `station.py:121-124`.
  - Pinned by the renamed `test_m3u_with_invalid_utf8_is_unreadable`.
- (d) test for `require_root`'s `is_dir()` arm: ADDRESSED.
  - `test_require_root_is_dir_oserror_is_station_root_error`. It is green before and after, as the implementer disclosed, because the arm was already correct in 6ad53ff. It is a pin, not a RED test, which is what was asked.

### New Issues in the Fix Diff
- None blocking.
- Minor (cosmetic, not ruled): a persistent symlink loop or an EACCES package directory on 3.11 is still labelled `changing:` even though it will not resolve on its own. The package is correctly Ineligible and the scan survives; only the operator-facing wording is off.
- No monkeypatch leakage: all four new tests use the `monkeypatch` fixture. Their predicates are narrow, so the patched `is_dir`/`exists`/`iterdir` cannot affect the other package or the root checks:
  - `self.name == "a-show"` for `is_dir`;
  - parent `a-show` + `manifest.json` for `exists`;
  - `self == root` for `iterdir`.
- No duplicate test names.

### Out-of-Scope Observations
- Behavioural divergence between versions, harmless: on 3.14 a `chmod 000` package directory silently disappears from the scan (`exists()` returns False), while on 3.11 it is listed as skipped. Likewise, a symlink-loop m3u entry is "entry missing" on 3.14 and "changing" on 3.11. Both are Ineligible, so nothing can air.
- Still open from the first review, not ruled in: a non-dict `show`/`source` raises `AttributeError` at `station.py:198-201`. The previous round's note about Task 9's recovery branch (`_drop_unpublished_segments` running before `PlanError` on an empty eligible set) still stands for Task 9's review.

### Verdict: all findings addressed
