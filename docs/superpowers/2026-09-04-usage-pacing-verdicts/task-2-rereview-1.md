# Task 2 scoped re-review — fix round 1 (baf633d..8433771)

Scope: `packages/herder/src/herder/limits.py` and
`packages/herder/tests/test_limits.py` only, as touched by commit
`8433771`. Read-only review; no edits, no suite run (arithmetic verified
by hand and by reading the regex/code, plus one standalone Python
snippet to confirm a Unicode codepoint — not the test suite).

## Findings verdict

- **I1 (constraints unpinned)** — ADDRESSED. All 7 surviving mutations
  (M1, M2, M3, M4, M5, M6, M8) are now killed by a dedicated test; see
  kill table below. `packages/herder/tests/test_limits.py:90-166`.
- **I2 (`MAX_RESET_AHEAD_S` unpinned)** — ADDRESSED. Largest accepted
  delta across every test in the file is now 5h10m (5.1667h,
  `test_reset_just_under_the_bound_is_accepted`,
  `test_limits.py:112-116`); smallest rejected delta is 6h10m (6.1667h,
  `test_reset_just_over_the_bound_is_refused`, `test_limits.py:106-109`).
  Gap is 1h wide and brackets 5.5h tightly (margins −0.333h / +0.667h),
  versus the pre-fix gap of [4.17h, 23.17h).
- **I3 (zone regex too narrow)** — ADDRESSED. New group at
  `limits.py:49-50`,
  `r"\(([A-Za-z_]+(?:/[A-Za-z0-9_+-]+)*)\)"`, matches all four required
  shapes (`UTC`, `America/New_York`, `America/Indiana/Indianapolis`,
  `Etc/GMT+5`) — traced by hand below — and is tested for `UTC` and the
  multi-segment case (`test_limits.py:153-166`). No new mis-parse path:
  an invalid-but-regex-shaped zone still fails at `ZoneInfo(zone_name)`
  (`limits.py:79-82`) and returns `None`, same as before.
- **I4 (speculative patterns unlabelled/ordering undocumented)** —
  ADDRESSED. `usage limit reached` now carries the same "Unverified"
  comment as its `seven_day` sibling (`limits.py:38-40`); an ordering
  comment above `_SIGNATURES` records first-match-wins as load-bearing
  and cites the pinning test (`limits.py:28-30`); the ordering itself is
  pinned by `test_specific_pattern_wins_when_generic_also_matches`
  (`test_limits.py:143-151`).
- **Minor 5 (bare `except Exception`)** — ADDRESSED.
  `limits.py:82`: `except Exception:  # noqa: BLE001 - a malformed or
  unknown zone name must not crash the caller` — matches the repo's
  existing idiom verbatim (compared against `failures.py:48`).
- **Minor 10 (docstring hyphen vs U+00B7)** — ADDRESSED. `limits.py:5`
  now contains the literal U+00B7 (`·`) character, confirmed by decoding
  the file (`ord() == 0xb7`), not an ASCII hyphen.

## M1–M8 kill table (my own verdict, arithmetic worked independently)

| Mut. | Change | Killed by | My check |
|---|---|---|---|
| M1 | `hour = int(h12)%12+…` → naive `int(h12)+…` | `test_reset_12am_resolves_to_midnight_not_noon` (`:90-96`), `test_reset_12pm_resolves_to_noon_not_midnight` (`:98-104`) | 12am case: correct formula gives hour 0 (midnight, rolled to next day per `now=22:00`); naive gives hour 12 (noon), wrong instant asserted — RED. 12pm case: correct gives hour 12 (matches assert); naive gives `12+12=24` → `time(24,0)` raises `ValueError` — RED (as an error, still a non-green result). Both tests use an hour where `%12` and naive disagree, and assert the `%12`-produced value. KILLED. |
| M2 | `MAX_RESET_AHEAD_S` 5.5h → 20h | `test_reset_just_over_the_bound_is_refused` (`:106-109`) | Delta = 6h10m = 6.1667h. Under 20h bound this would be accepted (6.1667h < 20h) but test asserts `is None` — RED. KILLED. Bound now bracketed tightly: 5.1667h accepted / 6.1667h rejected. |
| M3 | delete minute-range guard | `test_reset_out_of_range_minute_yields_no_reset` (`:119-121`) | `11:75am` — with guard deleted, `time(hour, 75)` raises `ValueError` inside `parse_reset` (uncaught), so the call errors rather than returning `None` — test fails (errors count as non-green). KILLED. |
| M4 | rollover `target <= local` → `target < local` | `test_reset_exactly_now_rolls_to_tomorrow` (`:123-129`) | `now` exactly equals target (11:10 == 11:10). Correct: `<=` is true → rolls to tomorrow (24h out) → rejected (`None`), matching assert. Mutant: `<` is false → no rollover → today's 11:10, delta 0h, accepted, returns a datetime — assert `is None` fails. KILLED. |
| M5 | delete `usage limit reached` signature | `test_classifies_usage_limit_reached` (`:131-135`) | Text matches no other pattern once this one is gone → `classify` returns `None` → `isinstance(err, RateLimited)` fails. KILLED. |
| M6 | delete `(weekly\|7-day\|seven[ -]day) limit` signature | `test_classifies_seven_day_variant` (`:137-141`) | "You've hit your weekly limit" matches neither `hit your session limit` nor `usage limit reached` once this entry is gone → `classify` returns `None` → assertion fails. KILLED. |
| M8 | reorder `_SIGNATURES`, generic first | `test_specific_pattern_wins_when_generic_also_matches` (`:143-151`) | Text `"You hit your session limit; usage limit reached."` matches both `hit your session limit` and `usage limit reached` (verified: both are literal substrings). Correct order → `scope == "five_hour"` (asserted). Reordered → generic matches first → `scope is None` → assertion fails. KILLED. |

All 7 previously-surviving mutations are independently confirmed killed by my own tracing, consistent with the implementer's RED/GREEN log.

## New Critical/Important breakage introduced by this fix diff

None found. The one production change (I3's zone-regex widening,
`limits.py:49-50`) is additive-only: it recognizes previously-missed
zone shapes and cannot cause a previously-correct result to become
wrong, since (a) any regex-matched-but-invalid zone name still fails at
`ZoneInfo()` and returns `None`, and (b) the bound/rollover logic that
determines correctness of an accepted result is untouched. Traced the
widened group `[A-Za-z_]+(?:/[A-Za-z0-9_+-]+)*` against all 4 required
shapes by hand:
- `UTC` → base component only, matches.
- `America/New_York` → base + one segment, matches (as before).
- `America/Indiana/Indianapolis` → base + two segments via `*`, matches.
- `Etc/GMT+5` → base `Etc` + segment `GMT+5` (digits/`+` allowed in
  non-first segments), matches.

No case found where the widened group matches something that should be
rejected but isn't — the group requires the match to reach the literal
`)` immediately, so any disallowed character (space, stray punctuation)
still fails the whole `_RESET_RE.search`, same as pre-fix.

## Scope check

Confirmed via `git show --stat 8433771` and the diff itself: only
`packages/herder/src/herder/limits.py` (+14/−3) and
`packages/herder/tests/test_limits.py` (+85) were touched. No other
files in the commit. `__init__.py` untouched (correct — no new symbols
exported by this fix round).

## Deferred / out of scope

Nothing new beyond the ruling's explicit deferred list (hour-range
guard, naive machine-local `now`, DST wall-time ambiguity/`fold`,
exact-equality rollover returning `now`, `re.Pattern` typing, `now = now
or …`, the top-level `herder.classify` export, broad `except Exception`
left unnarrowed). No additional out-of-scope issues observed in the
diff.

## Overall verdict

ADDRESSED: I1, I2, I3, I4, Minor 5, Minor 10 — all 6 open findings
resolved, all 7 mutations (M1, M2, M3, M4, M5, M6, M8) independently
confirmed killed by the new tests, no new Critical/Important breakage,
scope held to the two named files. Fix round 1 is sound.
