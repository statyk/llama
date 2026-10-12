# Task 11 handback: publisher core

**Status: DONE_WITH_CONCERNS.** The concerns are minor and listed at the end.

**Commits** (branch playout-phase1):
- `251ff51` fix(transmitter): serialise epoch creation under an exclusive lock
- `ad6ef13` feat(transmitter): R2 publisher with the ordering invariant, retries, PUT budget and guard read

**Files**
- New: `src/transmitter/{r2,publish}.py`, `tests_transmitter/{test_r2,test_publish}.py`
- Modified: `state.py` (`high_water` + `listed_bound()`), `pipeline.py` (plan_step bound), `workspace.py` (epoch lock, `epoch_lock_path`), `tests_transmitter/helpers.py` (FakeBucket, write_seg, make_publisher, TEMPLATE_PATH), `test_pipeline.py`, `test_workspace.py`

**Tests:** 3 r2 + 23 publish + 3 pipeline + 1 workspace = 30 new.
- `./.venv/bin/python -m pytest -q -p no:cacheprovider` (3.14, whole repo): **2373 passed**, 7 deselected
- `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider` (3.11): **224 passed**
- boto3 1.43.111 was already installed in both venvs, so there are no new installs. `transmitter.__file__` resolves inside the worktree.

**Rulings**
1. **High-water mark.**
   - `PublishState.high_water` defaults to None and loads with `.get`, so an old publish.json still loads (tested).
   - `publish_batch` saves `high_water=last` durably (fsynced write_json) after the site step and before the horizon PUT. The final save also carries it.
   - plan_step uses `listed = max(last, high_water)` for three things: the lost-plan start floor, `cut_for_recovery`, and `_drop_unpublished_segments`. It also floors the **recovery** run start at `(listed+1)*441`. That case is reachable when high_water is beyond now: without the floor the new run would re-render under listed keys. For the old `last` this floor changes nothing, because `last+1 <= now_n` there.
   - **One addition beyond the ruling:** if a batch after a crash stops part-way below high_water, the horizon is **not** rewritten. Otherwise R2's `last` would move backwards. The report error says "horizon held"; segments and state are kept, and the next batch retries.
   - The pre-first-PUT runs save now also stamps `epoch_id`.
   - Tests:
     - The crash is simulated as a BaseException raised right after FakeBucket stores horizon.json. Local `last` stays None, `high_water` is 109, the files are kept, and the next batch re-PUTs and lands (100, 109).
     - Horizon-held test.
     - plan_step lost-plan, recovery-cut and recovery-start tests with high_water above `last`.
2. Dropped `NOW_US = None`. The listings have no unused imports.
3. `check_epoch` is in publish.py and has its own test.
4. **Finding: `load_or_create_epoch`'s create path was NOT serialised.** It has no production caller yet (Task 14), and the publish flock does not cover it (non-blocking, and in another module). Two processes could each see no epoch.json and write different epochs. **Fixed locally:** creation now takes a blocking flock on `<root>/epoch.lock`, re-reads, and only then writes (still via write_json/os.replace). The test holds the lock from another fd, proves the creator blocks, writes the "other" epoch, releases, and asserts the creator returns that epoch.
5. Tests use E = 4_000_000_000 * 1_000_000 µs (helpers `E`).
6. Pinned by tests:
   - notes and page both use `public, max-age=3600`; the page is `text/html; charset=utf-8` and JSON is `application/json`.
   - A failed notes PUT means no timeline.json and no page that batch, while the horizon still advances; the next batch PUTs page before timeline.
   - A second show entering the timeline gets its notes and page before that timeline, and the timeline goes before the horizon.

**Mutation checks** (scratch `git archive` copy run with PYTHONPATH shadowing; sentinel `transmitter.MUTANT_SENTINEL == "copy"` and `transmitter.__file__`/`helpers.__file__` printed inside the copy; separate PYTHONPYCACHEPREFIX, cleared between mutants). Every prediction matched exactly:

| Mutant | Predicted red | Observed |
|---|---|---|
| A: `listed = pub.last` in plan_step | the 3 new plan_step high-water tests | exactly those 3; 221 passed |
| B: no pre-horizon high-water save | `test_the_high_water_mark_is_saved_before_the_horizon_put`, `test_the_horizon_never_moves_below_the_high_water_mark` | exactly those 2; 222 passed |
| C: no epoch flock | `test_epoch_creation_is_serialised_against_a_concurrent_creator` | exactly that 1; 223 passed |

**Brief vs code**
- make_publisher builds ShowAnalysis with `r.slug`, not "band-1", so multi-row tests work.
- I added tests beyond the brief: Content-Type checks, the high-water tests, the old-state load, check_epoch, and the two ordering tests.

**Concerns**
- (a) After a recovery or lost-plan whose new run starts above high_water, local segment files in (last, high_water] are never re-uploaded or deleted. That leaks at most one batch on disk (~360 segments).
- (b) The recovery with high_water beyond now still cuts the spanning show at high_water+1. That follows the existing outage design, but it needs about a 20 h outage plus a crash in that window.
- (c) `render_step` still reads pub.last, as the ruling says. If seg files in (last, high_water] went missing and a package changed, `replan_from` could re-plan in that range. This is very unlikely and out of scope.
