### Finding Verdicts

- **write_moves duplicates atomic_write_bytes's temp+replace+unlink block** — ADDRESSED. packages/emcee/src/emcee/workspace.py:21-38 gains keyword-only `fsync: bool = False` (flush + `os.fsync` inside the `with`, before `os.replace`); packages/emcee/src/emcee/moves.py:142-145 `write_moves` is now `payload = ...; atomic_write_bytes(moves_path(root), payload, fsync=True)`; the duplicated block and the `tempfile` import are gone (moves.py's remaining `os` uses are the lock at :130/:138). Test monkeypatch moved to `"emcee.workspace.os.fsync"` (packages/emcee/tests/test_moves.py:121); `assert synced` still fails if `fsync=True` were dropped, so the global constraint (unique temp + fsync + os.replace) stays pinned. Default `False` leaves the other callers (audio.py:345, cli.py:603, workspace.py:18 via atomic_write_text) byte-for-byte unchanged in behaviour. workspace.py imports no emcee module, so the new moves -> workspace import adds no cycle.

### New Breakage in the Fix Diff

None.

Checks run: `./.venv/bin/python -m pytest packages/emcee/tests/test_moves.py -q` -> 25 passed. Fix report names the covering run (full suite, 3001 passed, 1 skipped, 8 deselected) — not re-run. ruff not installed in the venv; imports inspected by hand (`moves_mod` still used at test_moves.py:174-185; no unused imports left in moves.py).

### Out-of-Scope Observations

- Minor: workspace.py module docstring (lines 1-8) still says only presenters and package_io use these writers; audio.py, cli.py and now moves.py (with `fsync=True`) do too. Cosmetic; ledger for final review.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
