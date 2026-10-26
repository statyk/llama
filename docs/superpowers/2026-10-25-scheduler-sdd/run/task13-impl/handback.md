# Task 13 handback (task13-impl)

Status: DONE. Commit d7f2bcf. Suite: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` -> 877 passed, 1 skipped.

## Implemented
- `report.py` (pure): `block_views(rows, projected, clock, epoch, *, missing=(), meta_of=...)`, `summary(views, span_us)`, `schedule_lines`, `profile_stats`, `reason_key`, `library_lines`. Interface deviation: `meta_of` kw supplies artist/date for persisted rows (PlanRow has none).
- `service.schedule_report` / `library_report` / `missing_announcements` / `clock_line`; `cli`: `schedule [--days --clock --library]`, `library`. `interstitials.ann_ids`.
- `status_lines`: anchors line replaced by clock, block (now/next), last/next 24 h misses and fill by cause, bends, degraded, missing announcement audio (8 days). Persisted rows + one directory read only. "on air" names the show, or `station break (station ID|announcement)` for an interstitial row.
- `probe_estimates.py --time-one`: prints the package's Ineligible reasons, or "not found" (test_probe_estimates.py).
- Repo CLAUDE.md: new Commands bullet (incl. the mid-block MISS-by-design note).

## Decisions
- schedule: `load_epoch` only; no epoch -> provisional in-memory Epoch at now, empty plan, note printed, nothing written. `live_clock(save=False)`. Station built directly (not `open_station`); `scan_pieces(read_only=True)` so nothing is analysed.
- If the persisted plan has already ended, previews a fresh run from now (with a note); history still includes the persisted rows.
- `--library delivered`: `scan_delivered` shows (awaiting_fix excluded) + the interstitial clips from the read-only scan.
- Views whose nominal start is at/after now+days are trimmed (project's `ahead` overshoots). Summary "repeat gap" is over the shown span only (not aired history).
- library groups ineligible by reason text before ": " ("awaiting fix from llama"); quiet-period reasons collapse to "changed within the quiet period".
- Missing announcement audio listed per occurrence (needed() dedupes by id, so each missing clip appears on the first occurrence needing it) and counted in summary.

## TDD
RED captured in task13-impl.log (11 failed, 24 passed on first run, before service/cli code; test_report passed once test arithmetic was fixed since report.py was written first). GREEN: full suite once before commit.
Tests: test_report.py (4), test_cli.py (+9: writes-nothing snapshot incl. last-good clock and engine.analyzed==[], no-epoch, estimates `~`, missing audio, draft clock/delivered, library, no-clock status, status with project/scan monkeypatched to raise, on-air station break, now/next block), test_probe_estimates.py (2). test_service anchors assertion updated.

## Sample (tmp workspace, 3 h draft blocks, tiny fixture library)
```
Sun 10-25 21:00  Block 21  starts Sun 10-25 22:29 (+89 min)  [MISS; bent: era]  (projected)
    Band 2005-11-03 (~4 min)
    Band 2005-11-02 (~4 min)
    . station ID id-hello
    ! missing announcement audio ann-559ee891c3f5.mp3: Coming up next, Block 21.
summary    9 block occurrence(s) over 24 h; misses 9; degraded 0
fill       0 min = 0.0% of the span (pool-short 0 min, structural 0 min)
bends      gap 7, era 8
repeat gap shortest 0.0 days
audio      32 announcement(s) missing
```
status:
```
on air     station break (station ID)
clock      clock.toml
block      now Block 9 (Tue 10-02 09:00); next Block 12 (Tue 10-02 12:00)
last 24 h  misses 1; fill 0 min (pool-short 0, structural 0)
next 24 h  misses 14; fill 0 min (pool-short 0, structural 0)
bends      gap 14, era 15 (last 24 h and planned)
degraded   0 block(s) played as open time (last 24 h and planned)
announce   32 announcement audio file(s) missing for the next 8 days (see `transmitter announcements`)
```
`library` smoke: `indie 4 shows median 4 p10 4 p90 4 ~4 estimated`, `station IDs 1: id-hello`, `1 awaiting fix from llama (held-1999-01-01)`.

## Files
packages/transmitter/src/transmitter/{report.py (new),service.py,cli.py,interstitials.py}; scripts/probe_estimates.py; tests_transmitter/{test_report.py,test_probe_estimates.py (new),test_cli.py,test_service.py}; CLAUDE.md.

## Self-review / concerns
- Bends in status count rows' bends over last 24 h + planned (each bend once per block by construction).
- `status` "block" uses show rows only; "last 24 h" window is by row start frame.
- The first block of a mid-block entry reads MISS by design (documented in help and CLAUDE.md).
- Python 3.11-compatible syntax only; not run under 3.11 here.
