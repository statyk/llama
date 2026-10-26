### Task 10: Measurement

**Files:**
- Create: `packages/transmitter/scripts/measure_scheduler.py`, `docs/superpowers/2026-10-2X-scheduler-measurement/{naive_filler.py,clock-a.toml,clock-b.toml,clock-c.toml,results.json,evidence.md}` (date = the day it runs)
- Test: `packages/transmitter/tests_transmitter/test_measure.py` (one smoke test on the fixture library)

**Interfaces:**
- Consumes: Tasks 3-9 only (`pieces`, `clock`, `history.Recency`, `scheduler.project`), not the pipeline; its floor checkpoint therefore lands before Task 11 wires the scheduler in.
- `measure_scheduler.py --root PATH --clock FILE --weeks N [--library delivered|eligible] [--no-interstitials] --out JSON` — one continuous `project` call over the whole span from an empty plan (`until_frame` at the span's end), history accumulating through the projection's own recency, no per-week restart; weekly figures are slices of that one projection. On estimated lengths (`--library delivered`: `pieces.scan_delivered`; `eligible`: `station.scan` + `pieces.build_pool(..., read_only=True)`). Writes per-week and total: block starts, misses, fill minutes by cause, bends by rule, repeat-gap distribution, share of block airtime on its own profile.
- `naive_filler.py` = `docs/superpowers/2026-10-10-playout-review/feasibility-sim.py` with: `--root` argument; anchors read from `clock-a.toml`; separate `overran` and `not_fillable` counts (no ×1000 weight); the scheduler's estimate (`pieces.estimate_frames` inputs: `total_duration_sec` + clip sizes, or the 4-minute allowance); fill exclusion read from `[open] exclude_profiles`; 50 seeds; JSON output.
- `clock-a.toml`: 07:00 dead, 12:00 bluegrass, 19:00 dead daily, Saturday 22:30 funk, Sunday 15:00 dead-family, `early_minutes = 0`, `late_minutes = 15`, `[open] exclude_profiles = ["dead", "funk", "dead-family"]`. `clock-b.toml`: the operator's shape (spec Measurement (b)). `clock-c.toml`: soft launch (Dead and funk blocks, open time).

- [ ] **Step 1: Smoke test** — `test_measure.py` runs the measurement function on the Task 8 fixture for 2 weeks and asserts the result keys, that `block_starts == 2 * occurrences_per_week`, and that projecting the 2 weeks takes under 10 s.
- [ ] **Step 2: Run to verify failure, implement, run.** Expected: PASS.
- [ ] **Step 3: Run the measurement** against `/Volumes/media/lma-radio/delivered` (read-only): clock (a) with `--library delivered --no-interstitials --weeks 50`, the naive script with 50 seeds; clocks (b) and (c) for 50 weeks (`c` also with `--library eligible`).
- [ ] **Step 4: Write `evidence.md`** — the numbers, the floor check (scheduler's share of block starts outside the window ≤ naive `overran + not_fillable`), and anything surprising. **Checkpoint:** if the floor fails, stop and escalate to the operator with the numbers before Task 11.
- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/scripts/measure_scheduler.py packages/transmitter/tests_transmitter/test_measure.py docs/superpowers/2026-10-2X-scheduler-measurement
git commit -m "docs: scheduler measurement against the delivered library, with the like-for-like naive baseline"
```

---

