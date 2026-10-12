### Spec Compliance

- ✅ Spec compliant (Task 11 + R1-R6). Every file in the brief is present: r2.py, publish.py, test_r2.py, test_publish.py, and FakeBucket/write_seg/make_publisher in helpers.py. The produced interfaces match the brief (publish.py:137-147 constants, PutBudget, Uploader, guard_blocks_publishing, publish_lock, Publisher, horizon_doc, put_json, PublishReport, publish_batch). There are no List calls: FakeBucket.__getattr__ fails on them (helpers.py:729). Exact Cache-Control values are pinned for every object (test_publish.py:933-948).
- R1 ✅ high_water is saved durably before the horizon PUT (publish.py:396-398). plan_step uses `listed` for three things: the lost-plan floor, cut_for_recovery and _drop_unpublished_segments, plus a recovery-start floor (pipeline.py:42-80). render_step is unchanged. An old publish.json still loads (state.py:562, test_publish.py:1038).
- R2 ✅ (no dead code or unused imports in publish.py or test_publish.py). R3 ✅ check_epoch is public and tested (publish.py:281, test_publish.py:1174). R4 ✅ epoch creation runs under a blocking flock with a re-read (workspace.py:636-649), and it is tested. R5 ✅ helpers.py:145. R6 ✅ (test_publish.py:916-924 exact order, 1084, 1100).
- ⚠️ Cannot verify from the diff: Task 12/14 consumers of `check_epoch`, `runs` and the `analysis_for` wiring.

### task10-fix1 (4067e90)
1. ADDRESSED. Probe: in a scratch copy (sentinel import proven, isolated pycache) I applied the mutant `exclude = bool(mismatched)` at pipeline.py:246. My predicted red was `test_the_second_mismatch_rule_is_per_slug_for_package_changes` only. Observed: exactly that one failed, 28 passed. The test injects a stale key to reach the branch; that is acknowledged in its comment and acceptable.
2. ADDRESSED. A non-UTF-8 briefing is caught as a ValueError subclass (site.py:475). A non-dict `briefing` field returns `(manifest, None)` (site.py:468-470). Both are tested.
3. ADDRESSED. `pick()` falls back to meta on null as well as missing (site.py:487-490), and this is tested.
4. ADDRESSED. Tests cover all three items: cut_frame at row frame 1000, the 24 h exact-edge and just-inside bounds, and `recent` at 10 newest-first (test_site.py:1300-1327).

### Strengths
- The R1 crash test is a real crash: a BaseException raised after the fake stores horizon.json. It proves the persist-before-PUT order, and the implementer killed mutant B against it.
- The recovery-start floor (pipeline.py:47-51) closes a case the ruling did not name: hw beyond now, where a new run would otherwise start under listed keys.
- Budget accounting is per attempt, botocore retries are off (r2.py:447), and an unreadable guard fails closed.

### Issues
#### Critical
None.
#### Important
1. publish.py:349 + 378-384: the implementer's "horizon held" rule can wedge publishing permanently. The re-batch range is `range(nxt, nxt + batch_segments)`. If `[publish] batch_segments` is lowered while `high_water > last`, every re-batch ends below high_water. The batch is then held forever: no horizon, no local progress, and `batch_segments` PUTs spent each tick until the daily budget runs out. That window opens after a crash or any failed horizon PUT, for example during an R2 outage, which is exactly when an operator might lower the batch size. Dead air follows once hw passes.
   - **Probe:** scratch copy, crash at batch=10, then batch_segments=5. Four ticks all returned `horizon held: segment 104 is below the high-water mark 109`, with `last=None` and the PUT count rising 19→24→29→34.
   - **Fix:** extend the batch range to cover the mark, `range(nxt, max(nxt + batch, (state.high_water or -1) + 1))`. Pin it with a test that lowers the batch size after a crash.
#### Minor
1. pipeline.py:45-61 (implementer's concern b; agreed and sharpened). The recovery trigger still uses `pub.last`. When hw > now_n, recovery cuts the spanning show at hw+1 and the new run starts at hw+1. If R2 does list up to hw, listeners hear that show cut mid-song into a new one. If it does not, on-disk audio for (last, hw] is abandoned and the stretch to hw+1 is dead air.
   - **Reachability:** only after a horizon PUT fails or crashes, followed by an outage of about the render lead (24 h default).
   - **Fix:** base the recovery decision on `listed`, i.e. `publish_next(rows, listed) <= now_n`. When it is not due, the publisher just re-PUTs identical bytes, and render_step resumes once `last` catches up.
2. publish.py:223: the guard cache accepts `now_s - checked_at < interval` even when the difference is negative. If the clock steps backwards, a cached `blocked: false` is trusted until the clock catches up, which suppresses the spend kill switch. Use `0 <= now_s - checked_at < interval_s`.
3. Concern (a), agreed. After a lost-plan or recovery run that starts above hw, local seg files in (last, hw] are never deleted. That is about one batch on disk (around 360 files). Prune or plan_step could remove files at or below `listed` that will never be published.
4. Concern (c), agreed: unreachable in practice. render_step skips existing seg files (pipeline.py ~212), and files at or below hw are deleted only after the save that sets last=hw.
5. site.py:471: a dict `briefing` whose `file` is not a string (for example `5`) raises TypeError from `Path(5)`. That is outside fix item 2's letter but within its spirit. It surfaces as a whole-site-step error, which leaves timeline.json stale.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The ordering invariant, budget, guard, lock and R1 high-water persistence are correct and well pinned. The one blocking item is the held-horizon rule the implementer added: an operator config change can turn it into a permanent, budget-burning publish wedge, and the fix is one line.
