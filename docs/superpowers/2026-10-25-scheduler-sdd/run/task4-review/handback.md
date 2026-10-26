# task4-review: Task 4 (the clock), 084d6f9..57a15a6

### Spec Compliance

**Mostly compliant, with one gap on the stated invariant.** Every interface in the brief is present and behaves as specified: the models, the defaults, `IMPLICIT_CLOCK`, `load_clock`, `LiveClock`/`live_clock`, `Occurrence`, `occurrences`, and `Workspace.clock_path`/`clock_last_good_path`. The gap: a clock that loads can still crash planning, through a TOML `inf` (Important #1).

Checked against the named risks:
- **(a) Strict nesting:** holds. All seven models (Zone, AnnounceConfig, Prefer, BlockConfig, OpenConfig, RotationConfig, ClockConfig) derive from the local `_StrictModel` (`extra="forbid"`, clock.py:31-34). The test checks unknown keys at the top level, in a block and in `[announce]`.
- **(b) "Loads cannot crash planning":** mostly holds.
  - Templates are checked against exactly their allowed fields. I probed `{titel}`, `{}`, a stray `{`, a stray `}`, `{title.upper}`, `{title:{next_title}}`, and `next_*` in a one-block form: all give ConfigError. `{{x}}` and `{title!r}` load, which is fine.
  - The window must be positive. `days = []`, `start` values like "24:00", "7:00" or a TOML time literal, and `max_shows = 0` are all rejected.
  - A `timezone` or zone `tz` that is empty, a directory ("America"), an absolute path or "localtime" is rejected.
  - NaN is rejected by the `ge=` constraints.
  - **Infinity is not rejected** (Important #1).
- **(c) `live_clock`:** holds. It never raises ConfigError in any branch I traced:
  - missing file: implicit, no problem;
  - an OSError other than FileNotFoundError, a UnicodeDecodeError or a ConfigError: falls back to the last-good copy, and to implicit when that copy is missing or invalid (tested by `test_corrupt_last_good_is_implicit`);
  - the last-good copy is written with `atomic_write_bytes` (temp + fsync + rename), only when its bytes differ;
  - `save=False` writes nothing.

  Two behaviours have no test: "only when bytes differ" and "a failed write is swallowed" (Minor #2).
- **(d) Expansion:** matches the spec. Verified by probes and mutants:
  - `end_us` is the next occurrence's start. A single `["mon"]` block covers the week: Mon 19:00 EST to the next Mon 19:00 EDT, 2027-03-09T00:00Z to 2027-03-15T23:00Z. A daily block over spring-forward runs 23 h.
  - A collapsed zero-length occurrence is dropped; the later nominal wins via the `(utc, start)` sort. With 02:30 + 02:45, only 02:45 is kept, at 07:00Z.
  - Fall-back resolves with fold=0, giving 01:00 then 01:30 EDT. The 01:30 block runs to the 02:00 EST start (07:00Z).
  - A nonexistent time resolves to the transition instant. Also correct for Lord Howe (30-minute shift), Europe/Dublin, Havana (midnight), Gaza, and Apia's skipped 2011-12-30.
  - Span intersection is half-open at both ends, and the running occurrence is included.
  - The ±8-day padding is enough for a block of up to a week.
  - Weekday rotations with the same start work.
- **(e) Extra validation is justified:**
  - A descending `years` range would otherwise silently match nothing.
  - HH:MM is in the brief.
  - A repeated weekday is harmless input, and rejecting it is mildly over-strict. But with the last-good fallback and the alert it cannot take the station off air, so this is not a finding.
  - `weight > 0` and `on_this_day >= 0` are undocumented constraints. The scoring task should confirm they match its additive score (Minor #5).

⚠️ The diff cannot show:
- how the announcement renderer will pass `time`/`title`. The templates are validated with `str` dummies, so a format spec like `{time:>5}` is only safe if the renderer also passes strings;
- whether Task 11 turns `problem` (pydantic's multi-line text with errors.pydantic.dev URLs) into a readable alert.

### Strengths

- `_resolve` is correct and does not depend on any one zone. It uses the fold=0 equality test to separate a gap from the ambiguous and normal cases, then bisects between the fold=1 and fold=0 UTC instants. I checked six zones' edge transitions.
- The `occurrences` design is simple and easy to audit: expand local dates with padding, sort by `(utc, start)`, take the successor as the end, drop zero-length, then intersect spans. Mutants confirm the key rules are pinned:
  - removing the zero-length drop fails `test_spring_forward_collapses_and_drops`;
  - resolving the gap with fold=1 fails the same test;
  - reversing the tie-break fails the same test;
  - excluding the running occurrence fails `test_span_intersection_includes_running_block` and `test_implicit_clock_covers_everything`.

  Every one failed exactly as predicted.
- `live_clock` has no path that raises ConfigError. Reading the bytes once and comparing them to the last-good copy avoids a TOCTOU between the parse and the copy.
- The tests go beyond the brief: corrupt last-good, prefer validation, the ISO key, the implicit clock's ±12 h window. The test file runs clean (26 passed, no warnings or other output).

### Issues

#### Critical
None.

#### Important

1. **A clock with an infinite window loads, is saved as last-good, and then crashes every plan step** (clock.py:34, 116-118, 164, 347).
   - **What happens:** TOML has `inf`, and pydantic floats allow it by default, so `ge=0` passes. I verified that each of these loads without error and then makes `occurrences()` raise `OverflowError: cannot convert float infinity to integer` at `round(early * 60_000_000)`:
     - `wiggle_minutes = inf` (clock or block);
     - `late_minutes = inf` with `early_minutes = 0`.
   - **Why it matters:** `live_clock` copies that file to `clock.last-good.toml` before anything expands it. Planning then fails on every step, and a later invalid edit falls back to the same poisoned copy. That breaks the task's central invariant ("a clock that loads must never crash planning").
   - **Related loads:**
     - `concert_gap_days = inf` and `prefer weight = inf` also load, and will probably overflow a `timedelta` or produce NaN scores in later tasks.
     - A finite but huge window (`wiggle_minutes = 1e12`) loads, and `us_to_iso(o.lo_us)` raises `OverflowError: date value out of range`, so any status or schedule display of the window would crash.
   - **Fix:**
     - Add `allow_inf_nan=False` to the clock's `_StrictModel.model_config`.
     - Put an upper bound on the window minutes (for example `le=7*24*60`; anything past a week is meaningless, since the implicit clock uses 720).
     - Add ConfigError tests for `wiggle_minutes = inf`, `late_minutes = inf` and `concert_gap_days = inf`.

#### Minor

2. **Two `live_clock` behaviours have no test** (clock.py:252-261). The brief and spec ask for both:
   - the last-good copy is rewritten only when its bytes differ;
   - a failed copy is swallowed.

   Mutant M3 (always rewrite) and mutant M5 (the OSError propagates) both left all 26 tests passing. Fix:
   - assert the last-good copy's inode or mtime is unchanged after a second `live_clock` on identical bytes;
   - make the copy fail (for example, a directory at `clock_last_good_path`) and assert `source == "clock"`.

   The unreadable-clock branch (an OSError other than FileNotFoundError) is also untested.
3. **`load_clock` and `live_clock` decode the same file differently** (clock.py:223). `load_clock` uses `path.read_text()`, which decodes with the locale encoding; `live_clock` uses `raw.decode()`, which is UTF-8. TOML is UTF-8 by definition. Under systemd with a non-UTF-8 locale, the two could disagree about the same bytes, and the last-good copy is read through `load_clock`. Fix: `read_text(encoding="utf-8")`, or read bytes and decode the same way in both.
4. **`Occurrence` is a frozen dataclass but not hashable** (clock.py:270). `hash(o)` raises `TypeError: unhashable type: 'BlockConfig'`. Later tasks must key sets and dicts on `o.key`, not on `o`. Either note this in a docstring or use `eq=False`/`unsafe_hash` thoughtfully. Relatedly, `IMPLICIT_CLOCK` is a mutable module-global pydantic model shared by every `LiveClock`; `frozen=True` on the models would protect it.
5. **Undocumented constraints on preference values** (clock.py:95-96): `weight` must be > 0 and `on_this_day` must be ≥ 0. The spec's score is additive ("recency plus the block's preference weights"), so whoever builds scoring should confirm a zero or negative weight is meant to be invalid, and document the constraint in the runbook's clock reference.
6. **Weak exception assertion** (test_clock.py:243). `pytest.raises(Exception)` for `max_shows=0` should be `pydantic.ValidationError`, or better, a `load_clock` ConfigError like the other validation tests.
7. **Minor DRY:** a second `_StrictModel` duplicates `config._StrictModel` (clock.py:31-34). The brief allows a local base, but if #1's `allow_inf_nan=False` is added here only, the two bases diverge silently. Consider importing the shared one, or commenting on why the clock's base is stricter.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The expansion logic, the DST handling, the last-good fallback and the strict nesting are correct, and the tests pin them; mutants confirm this. But the task's headline invariant, "a clock that loads cannot crash planning", is broken by a TOML `inf` in any window field. That file loads, is saved as last-good, and then raises OverflowError in `occurrences()` on every plan step. The fix is one model_config flag plus window bounds and three tests. The Minor items can ride along.

Evidence: the probe output and mutation results are in task4-review.log. The mutants ran in a scratch `git archive` copy with `transmitter.__file__` proven inside it; M1, M2, M4 and M6 failed exactly as predicted, and M3 and M5 passed, which is the test gap in #2.
