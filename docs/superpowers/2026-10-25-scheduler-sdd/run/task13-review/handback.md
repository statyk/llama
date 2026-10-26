# Task 13 review (task13-review): `schedule`, `library`, `status` lines, on-air line, probe `--time-one`

Range cd80cbe..d7f2bcf. HEAD suite: 877 passed, 1 skipped (`./.venv/bin/python -m pytest packages/transmitter/tests_transmitter`). The changed files parse under a real python3.11. Mutants (19 plus a no-op baseline, each with a predicted red test, run in a scratch `git archive` copy, imports confirmed to resolve inside the copy, no bytecode) and smoke runs (tmp TRANSMITTER_ROOT, fixture station, FakeEngine) are logged in task13-review.log.

### Spec Compliance
- **`schedule`**: matches the spec "Commands" and the brief. It calls `load_epoch` only, and with no epoch it uses a provisional in-memory epoch and prints a note; `epoch.json` and `epoch.lock` are not created (pinned: M3 goes red). It reads the clock with `live_clock(save=False)` or `load_clock(--clock)` and never calls `Station.clock()` (pinned: M1 goes red). It calls `scan_pieces(read_only=True)` (pinned: M2 goes red). It never calls `open_station`, `frames_of`, `analyze_show` or `load_or_create_epoch`, takes no plan lock and sends no alerts. The projection starts at `rows[-1].end_frame + gap` on all persisted rows plus history, with `until_frame` = now + days, and views at or past the horizon are trimmed. Estimates are marked `~` (pinned: M10). Missing announcement audio is shown per occurrence and in the summary (pinned: M11). `--library delivered` uses `scan_delivered` (which excludes awaiting_fix packages) plus the clips. My smoke run with a persisted plan of 11 rows and a `clock.last-good.toml` that differs from `clock.toml`: the workspace tree was byte-identical after `schedule` at both now and mid-block.
- **`library`**: profiles with count/median/p10/p90, the ID and announcement pool, ineligible packages by first reason (`awaiting fix from llama` grouped). Read-only.
- **`status`**: the anchors line is gone. New lines: the clock line (`clock.toml` / `last-good (…)` / `no clock: open all week`, through `live_clock(save=False)`), now/next block, last and next 24 h misses and fill by cause, bends, degraded blocks, and a count of missing announcements. It reads persisted rows and does one interstitials directory listing (stat per file). It calls no `scheduler.project`, `station.scan`, `scan_pieces` or `scan_delivered` (pinned for project/scan: M5 goes red). None of it alerts. I confirmed by smoke that the tree is unchanged at four instants.
- **Counting**:
  - Misses come from first-show rows (`miss` is only set there).
  - Fill is summed by cause.
  - Status sums per-row `bends`, which is correct under the scheduler's "each rule once per block" contract (scheduler.py:236-239). The schedule summary counts once per block via a per-block set, which is equivalent.
  - Degraded blocks are deduplicated by (block, nominal).
  - The 24 h windows go by row start frame.
- **On air**: names the show slug, `station break (station ID|announcement)` for an interstitial row (pinned: M9), and `(between shows, or not started)` in a gap (smoke).
- **Probe**: prints `error: package 'X' is not eligible: <reasons>` or `not found`, exit 1. It stays read-only and adds no llama/emcee import (pinned: M14).
- **Deviation from spec**: one, Important #1 below (the occurrence in progress is mis-reported by `schedule`).

### Strengths
- `report.py` is pure, with no IO or wall clock. The service functions keep IO at the edge. `_preview_station` is a clean single point that avoids `open_station`.
- The read-only guarantee for `schedule` is real and well pinned on the paths most likely to regress (`Station.clock()`, `scan_pieces(read_only=False)`, `load_or_create_epoch`).
- The write-nothing test deliberately seeds a `clock.last-good.toml` that differs from `clock.toml` and asserts `engine.analyzed == []`. Both are good test design.
- The disclosed `meta_of` kwarg is the right call: PlanRow has no artist/date, and `history.recency` uses the same shape.
- The "a mid-block entry records MISS by design" note sits in the help text and in CLAUDE.md, where the operator will meet it.

### Issues

#### Critical
None.

#### Important
1. **`schedule` mis-reports the occurrence in progress** (service.py:616, `shown = [r for r in base if r.end_frame > now_f]`; report.py:128-139).
   - **What:** `block_views` takes the block's start, slip, MISS and bends from the first show *in view*. When the show on air is not the block's first show, the earlier rows of that occurrence have already ended and are filtered out.
   - **Reproduced:** the plan's Block 0 started Sun 23:56 (-4 min). Previewing while its second show airs prints `Block 0  starts Mon 10-26 01:26 (+86 min)`. A first-show `miss=True` on that occurrence would also vanish, and so would a bend that the scheduler placed on the ended row (bends are written once per block, on the row whose placement bent them).
   - **Why it matters:** on hugo this is the first line the operator reads. A late-start-sized slip with no MISS flag is wrong and confusing.
   - **Fix:** keep every persisted row of any occurrence that still has a row ending after now:
     ```python
     live = {(r.block, r.nominal_start) for r in base if r.end_frame > now_f}
     shown = [r for r in base if r.end_frame > now_f or (r.block, r.nominal_start) in live]
     ```
     Optionally drop the ended rows from the per-show list while keeping them for start, slip, miss and bends. Add a test with a persisted plan, previewed at an instant inside the block's second show, that asserts the start, slip and MISS of the block on air.
2. **Test gaps on the stated strict and counting surfaces.** The code is correct today (I verified each point by smoke), but none of this is pinned. Every mutant below passed the whole affected test set (test_cli, test_report, test_probe_estimates, test_service, 107 tests):
   - (a) **No `schedule` test has a persisted plan.** All schedule tests run on epoch + clock with no `plan.jsonl`, so the core path (persisted rows from now, then the continuation) is untested. Three mutants survive:
     - M19 `rows = []`
     - M20 continuation at `rows[-1].end_frame` with `run_start=True`
     - M21 `history.recency([], [], …)`, which drops the rotation history
     
     The write-nothing snapshot also never contains `plan.jsonl`, `aired.jsonl` or cache entries.
   - (b) **The `status` read-only guarantee for `clock.last-good.toml` is unpinned.** M4 switches `_scheduler_lines` to `live_clock(ws)` (save=True) and survives.
   - (c) **The `status` numbers are unpinned.** The tests only check that the labels exist. Survivors:
     - M7: misses counts any row with `miss is not None`
     - M8: fill is summed over all rows, not the window
     - M12: bends and degraded are counted over the whole plan, not "last 24 h and planned"
     - M15: "next" may name the current block
   
   **Fix:**
   - Run a `schedule` test after `pipeline.plan_step`. Assert that the first projected piece starts at `rows[-1].end_frame + gap` (not run_start), and wrap it in the tree snapshot.
   - Snapshot the tree around `status` with a differing last-good file.
   - Add one hand-written `plan.jsonl` with rows carrying miss, fill, bends and degraded at known frames on both sides of -24 h, now and +24 h, and assert the exact `last 24 h`, `next 24 h`, `bends`, `degraded` and `block` lines.

#### Minor
1. **`status` "block now" goes stale** (service.py:483-490).
   - After the plan has ended, it still prints `now Block 6 …; next not planned yet` (smoke: one hour after the last row).
   - During a boundary interstitial, "now" names the previous block, although the break belongs to the next one.
   - Fix: say "none" (or "off plan") when the last row of `cur`'s occurrence has ended.
2. **Dead condition** at service.py:484: `(cur.block, cur.nominal_start) != (None, None)` is always true, because `sched` already filters out `block is None`.
3. **`library` groups fragment by count** (report.py:256). `reason_key` keeps leading counts, so "1 DJ clip(s) missing" and "2 DJ clip(s) missing", or "3 of 12 track file(s) missing" and "1 of 9 …", each get their own line. Fix: normalise a leading `\d+( of \d+)? ` before grouping.
4. **`library` scans the NFS station root twice**: once in `scan_pieces`, once more with `station.scan` at service.py:636. Fix: call `station.scan` once and build the pool from its shows.
5. **Fill-cause label.** The spec's split is "pool short" and "longer than max_shows", but output prints the internal cause `structural`. Fix: map it to operator wording in `schedule_lines` and the status lines.
6. **Open-time slip is noise.** Under the implicit clock (or for open blocks) the slip against the occurrence's nominal is meaningless. Smoke printed `open  starts Sun 10-25 18:36 (-324 min)`. Fix: suppress the slip for open or untitled blocks.
7. **CLAUDE.md bullet** (CLAUDE.md:264-265). It is accurate and terse in the file's style, with one gap: "`status` reads persisted rows and the interstitials folder only" leaves out that it also reads `clock.toml`/`clock.last-good.toml` (the clock line). Suggested wording: "persisted rows, the clock files and the interstitials folder only".
8. **Weak `--library delivered` test.** `test_schedule_draft_clock_and_delivered_library` asserts only that "Block" is present. It never checks that the unvoiced package reaches the preview or that the `library    delivered: N package(s)` line is printed.
9. **"(projected)" on mixed blocks.** A block that mixes persisted and projected shows is labelled "(projected)" as a whole. Per-show provenance shows only through `~`, and a projected show measured exactly carries no `~`. Optional: mark projected shows individually.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** The read-only guarantees, the cost bound on `status`, the counting semantics, the on-air line and the probe change are all correct, and the most likely `schedule` read-only regressions are pinned by mutants that go red. However, `schedule` reports the occurrence on air wrongly whenever its first show has ended: the start, the slip and the MISS flag all come from whichever show is on air (Important #1). The persisted-plan path of `schedule`, `status`'s last-good read-only guarantee and every `status` count are also unpinned: 10 of 19 mutants survived (M4, M7, M8, M12, M15, M17, M18, M19, M20, M21; M17 and M18 are view-trimming, folded into Important #2a). Both fixes are small and local.
