# task10-impl handback

Status: DONE_WITH_CONCERNS (floor check PASS; one finding the operator should see before Task 11).

Floor check (clock a): scheduler 0/1151 block starts outside the window = 0.0%; naive overran 15 + not fillable 17 of 1100 gaps = 2.9% (1.4% + 1.5%). PASS.

Built: packages/transmitter/scripts/measure_scheduler.py (one continuous project() over N weeks from nominal start of the first occurrence on/after 2026-11-02, empty Recency, seed 0; per-week slices; estimates only; optional --scan-cache pickle in own scratch); test_measure.py smoke test; naive_filler.py, clock-a/b/c.toml, results-*.json, evidence.md under docs/superpowers/2026-10-25-scheduler-measurement/.

Decisions: epoch = nominal start of first occurrence (no mid-block entry); extra frames measured via aacenc.extra_frames() (ffmpeg on synthetic silence); pause 0.75 s, gap 2 s (config defaults); no interstitial clips loaded in any run (none on this machine), so IDs/announcements never appear; clock (b) illustrative; clock (c) has no open block (other profiles only as fill); naive uses scheduler's estimate via pieces.scan_delivered when transmitter is importable, else manifest total + 4 min fallback; naive window = clock late_minutes.

Summary (50 weeks, results in evidence.md): all four runs 0 misses. a: 1151 starts, fill 7.6% structural, bends gap 347 / era 10, own-profile 92.4%. b: 2101 starts, no fill, bends gap 663 / artist_day 15 / era 2, own 100%. c delivered: 1051 starts, no fill, gap 323, own 100%. c eligible (224 voiced): fill 12.8% (22k pool-short, 43k structural, mostly indie), own 87.2%.

Surprising: Dead repeats heavily. Clock a airs only 39 of 413 dead shows in 50 weeks (median repeat gap 5 d, 824/1540 repeats within 7 d); b 38/413; c-delivered 66 dead of 413, 87 funk of 221. Likely window-landing outranking rotation rules (gap rule is the most-bent rule); not diagnosed. No MAX_FILL clusters (no misses at all). Country negligible (2 packages).

Concerns: floor comparison not fully like-for-like (scheduler max_shows 2, real 2 s gaps, history over 50 weeks vs naive one week/no history); estimates only. Sanity run on a 6-show pool produced 44/46 misses, so zero-miss is not a metric artifact.

Tests: ./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q -> 798 passed, 1 skipped.
Commits: 854d00a, f67ebd6, c356d08, 1644270, plus a wording-fix commit.
