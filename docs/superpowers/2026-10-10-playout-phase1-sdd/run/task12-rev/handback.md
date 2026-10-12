### Spec Compliance

- ✅ Spec compliant. prune (publish.py:332-398) does everything the brief and rulings R1-R3 ask, and the tests (test_prune.py, 15 tests) pin it.
  - R1: config.py:59-73 sets the floor to ceil(((6+3)*10.24 + 5 + 120)/60) = 4.0, from named constants, with the derivation in a comment. The default stays 10.0 (config.py:83). A value below the floor raises ConfigError naming the key (test_config.py:72-77), and the template states the floor (config.py:165-166).
  - R2: helpers.py:145 has `E = 4_000_000_000 * 1_000_000`. The unused `grid` import is gone.
  - R3: the lock is taken first and does not wait, then the guard is checked, failing closed (publish.py:342-345). Tested at test_prune.py:107-125: an unreadable guard stops prune, and a held lock raises PublishLocked with bucket.log == [].
  - Spend surface: only per-key `Uploader.delete`, which is DeleteObject (publish.py:118-122). No List, no DeleteObjects. The horizon PUT happens before any delete (publish.py:363-379), with n_max <= state.last (publish.py:360). high_water is never written: the state is loaded and saved whole, which test_prune.py:168-174 pins.
- Extra, judged on the merits: the high-water deferral (publish.py:354-359) is correct and needed. It is better justified than the report claims. When high_water > last, R2 may hold a horizon written by a recovery batch whose `first` differs from local `first` as well as whose `last` does. Without the deferral, prune would regress both. Writing `last = listed_bound()` would also be safe for existence, because every segment up to high_water returned 200 before high_water was saved. But that path would skip publish's site and timeline step and its seg-file unlinking, so deferring is the cleaner choice.
- Starvation, checked as a named risk:
  - The deferral lasts exactly as long as publish_batch cannot reconcile. Reconciling needs the local files from last+1 to high_water. publish only unlinks them after a successful horizon save (publish.py:322-323). plan_step's `_drop_unpublished_segments(st, listed)` keeps everything up to `listed_bound()` (pipeline.py:131, 166). So the files survive, and prune is never the thing that holds the system stalled.
  - Cost while deferred: storage of unpruned segments only, about 1.4 GB per day of backlog at 128 kbps, roughly $0.02/month at R2 storage rates. There is no PUT spend and no listing hazard.
  - After a stall, prune catches up in one invocation, with deletes free and the horizon about 20-24 h ahead (lead_hours=24). Holding the lock through a long delete run does not threaten air.
- ⚠️ Cannot verify from this diff: nothing calls `prune` yet (grep finds no caller in src). The run loop is a later task. Whoever wires it in must log or alert on `stopped`/`error`. Otherwise a lasting "high-water" or "guard" stop is silent apart from storage growing.

### Strengths
- The order is horizon-first, then state save, then deletes, then saving runs. Every crash point is safe:
  - A crash after the horizon PUT but before the save means the next publish writes the old `first`. That re-lists segments that still exist, since deletes come later.
  - A crash during deletes re-deletes on resume, which is idempotent.
- A delete failure stops cleanly. The partial run is saved as [n, hi] and later runs are kept as they are (publish.py:382-397). Resuming then deletes exactly the rest (test_prune.py:67-85).
- Deleting old runs below `first` skips the horizon PUT, so it costs no spend (publish.py:363 gate).
- PutBudgetExceeded is reported as stopped="put-budget", the same as PublishReport (publish.py:371-373). test_prune.py:141-149 tests it.
- The tests that go beyond the brief are the right ones: a failed horizon PUT deletes nothing, a spent budget deletes nothing, the high-water deferral writes nothing, and high_water is preserved. The implementer's mutation table had a prediction for each mutant, and each prediction matched.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- publish.py:354: the deferral is checked before `n_max` is computed, so it also blocks the case that needs no horizon write. That case is deleting old runs that are entirely below `state.first`, such as the recovery leftovers in test_prune.py:47-53. Those deletes cannot move R2's `last`. Possible fix: skip only the horizon branch while high_water > last and still delete runs below `first`. The impact is low, because both cases wait for the same reconcile.
- test_config.py:67: `PRUNE_MARGIN_FLOOR_MINUTES * 60 >= (6 + 3) * 10.24 + 60` uses a 60 s allowance where the code uses 120 s and 5 s. The exact `== 4.0` pin on the line above makes it redundant and slightly misleading. Either drop it or make it match the derivation.
- config.py:62-65: the derivation's "listed (6 + 3) * d after it started" is an upper bound, not exact. A segment leaves a k=6 window 6d after its start, and the grace path ends at last + 3 (about 4d after last's start). The bound is conservative, so it is safe. Worth saying "at most" so the next reader does not take it as exact.
- The plan and spec still show `ge=0` for prune_margin_minutes (the implementer flagged this). Leave it for the doc-sync pass at the whole-branch review.

### Assessment

**Task quality:** Approved

**Reasoning:** prune holds the strict spend and listing invariants: per-key deletes only, the horizon advanced before any delete, never past `last`, and high_water untouched. It also stays safe at every crash point. The added high-water deferral is sound, and it can only starve while publish is already stalled, at a cost of storage only.

Checks run (read-only, no mutants needed):
- Uploader.delete and publish_batch's reconcile path: publish.py:85-123 and 241-325.
- Whether high_water is preserved through state load/save: state.py.
- Whether the pipeline's segment cleanup keeps files up to listed_bound: pipeline.py:114-121, 131, 166.
- That the test epoch matches R2: helpers.py:145.
- prune callers (none yet).
- lead_hours=24, for the lock-hold risk.
