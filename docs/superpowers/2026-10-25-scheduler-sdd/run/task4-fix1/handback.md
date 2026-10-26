# task4-fix1: DONE
Changes (clock.py): _StrictModel allow_inf_nan=False; window fields (clock/block wiggle, early, late) le=10080; load_clock reads utf-8. Tests: non-finite/oversized ConfigErrors (wiggle inf at both levels, late inf, concert_gap_days inf, prefer weight inf, >1 week, 1e12), last-good not rewritten (inode+mtime), failed copy swallowed, unreadable clock.toml falls back, max_shows=0 via ConfigError.
Suite: 31 clock tests pass; full transmitter suite run once (see log).
Mutants (scratch copy, transmitter.__file__ verified inside scratch): no allow_inf_nan -> non_finite test red; always rewrite -> not_rewritten test red; OSError propagates -> swallowed test red. All as predicted.
