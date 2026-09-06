# Task 1 — CODE-QUALITY review

**Verdict: Changes requested.**

The implementation is correct on every input I could construct — the parsing
logic, the year inference, the DST behaviour and the branch separation all
hold up under hand-walking and under direct probing. Nothing here is a shipped
bug. What earns "changes requested" is the second half of the brief: the new
code's *guards* are almost entirely unpinned, and two comments state things
that are not true of the code as written.

## Method

- Hand-walked both regexes and `_dated_target`'s year loop, then probed the
  real module in the worktree venv (`./.venv/bin/python`, read-only; nothing
  in the worktree was modified and no commit was made).
- Ran a **mutation experiment**: ten one-line mutations of the new code, each
  exec'd into a module object injected as `sys.modules["herder.limits"]` before
  pytest collected the worktree's `test_limits.py`. The worktree was not
  touched. The harness is proven, not assumed: the control run is 27 passed,
  and `M10` (defaulting the absent minute to 30 instead of 0) is correctly
  caught. **Nine of the other ten mutations survive green.**

```
M0-control                         GREEN  27 passed
M1-drop-ValueError-guard           GREEN  27 passed
M2-drop-dated-zone-guard           GREEN  27 passed
M3-bogus-month-becomes-january     GREEN  27 passed
M4-drop-dated-minute-range-check   GREEN  27 passed
M5-target-ge-local                 GREEN  27 passed
M6-drop-month-suffix-tolerance     GREEN  27 passed
M7-month-slice-is-noop             GREEN  27 passed
M8-bound-gt-becomes-ge             GREEN  27 passed
M9-dated-tried-second              GREEN  27 passed
M10-no-minutes-defaults-to-30      red    1 failed, 23 passed   <- harness works
```

## What is right (so it is not re-litigated)

- `_hour24` is shared with the time-only branch, so the `% 12` conversion
  stays pinned by the pre-existing `test_reset_12am…` / `test_reset_12pm…`.
  Extracting it was the right call.
- The two patterns are genuinely disjoint on a **single** clause: measured,
  `_RESET_DATED_RE` does not match the refusal string and `_RESET_RE` does not
  match the dated string. No cross-misfire.
- Year inference is correct across the New Year boundary (Dec 31 → "Jan 2"
  resolves to 2027-01-02, ~2 days out, admitted).
- A stale dated reading (today's date, time already past) correctly returns
  `None` rather than a year-long sleep. Verified.
- DST: a non-existent local time (spring-forward 2:30am) does not raise; it
  resolves via `fold=0` to the pre-transition offset. See Minor 5 for the
  ambiguous-hour half.

---

## Important

### I1 — Two crash guards are unpinned; removing either ships an exception where the module promises `None`

`packages/herder/src/herder/limits.py:82-85` (the dated branch's `ZoneInfo`
try/except) and `:91-95` (the `except ValueError: continue`).

Measured consequences of removing them, with the whole suite still green:

```
M1 (no ValueError guard): parse_reset("resets Feb 29 at 7am (America/New_York)")
    -> RAISES ValueError: day 29 must be in range 1..28 for month 2 in year 2026
M2 (no dated zone guard): parse_reset("resets Sep 12 at 7am (Mars/Olympus)")
    -> RAISES ZoneInfoNotFoundError
```

The time-only branch's twin guards *are* pinned
(`test_unknown_zone_or_unparseable_time_yields_no_reset`); the dated branch's
are not, even though the module docstring's whole posture is "yield None
rather than guessing" and the `noqa` comment says in as many words "unknown
zone must not crash the caller". This is precisely the project's standing
lesson — a green suite is not a pinned constraint.

**Suggested change:** add two assertions (one test is enough):

```python
def test_dated_reset_degrades_to_none_on_a_bad_zone_or_impossible_date():
    # Both are guards, not accidents: parse_reset must never raise at its
    # callers (see the module docstring). Neither was pinned before.
    now = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
    W = 7.5 * 86400
    assert limits.parse_reset("resets Sep 12 at 7am (Mars/Olympus)", now=now,
                              max_ahead_s=W) is None
    assert limits.parse_reset("resets Feb 29 at 7am (America/New_York)",
                              now=now, max_ahead_s=W) is None   # 2026 not a leap year
    assert limits.parse_reset("resets Sep 31 at 7am (America/New_York)",
                              now=now, max_ahead_s=W) is None
```

### I2 — The ordering comment makes a false safety claim, and the single-clause contract is undocumented and unpinned

`packages/herder/src/herder/limits.py:58-59`:

> `# Tried FIRST because it is the more specific of the two; the time-only`
> `# pattern cannot match it anyway, since "Sep" is not a digit.`

The second clause is true per-clause and irrelevant to the ordering; what the
ordering actually decides is which clause wins in a **multi-clause text**, and
there the comment's reassurance is wrong. Measured on a two-line blob shaped
like real `/usage` output:

```
"Current session: 42% used, resets 5:20pm (America/New_York)\n"
"Current week: 61% used, resets Sep 12 at 7am (America/New_York)"

parse_reset(blob, now=…)                        -> None                  # session bound
parse_reset(blob, now=…, max_ahead_s=7.5*86400) -> 2026-09-12 11:00 UTC  # the WEEKLY clause
```

`_RESET_DATED_RE.search` scans the whole string, so a caller asking for the
session reset over the whole blob silently gets the weekly one (or, under the
session bound, `None` — a session reset that was right there in the text).
Task 2's `parse_usage_text` happens to slice per-clause before calling, so
nothing is broken today; but that is the caller's discipline, stated nowhere,
and `M9` (trying the dated pattern *second*) survives green — the ordering the
comment defends is not pinned by anything.

**Suggested change:** replace those two comment lines with the real reason, and
add the contract to `parse_reset`'s docstring: *"`text` must contain at most one
`resets …` clause; with more than one, the dated form wins wherever it appears."*
Then pin it with one test asserting which clause a two-clause string yields.

---

## Minor

### M1 — `_dated_target`'s minute-range check is dead code

`packages/herder/src/herder/limits.py:87-88`. Proven by executing both
variants side by side: `"7:99am"` and `"7:60am"` return `None` with **and
without** the check, because the out-of-range minute reaches
`datetime(..., minute=99)`, which raises `ValueError` and is swallowed by the
`except ValueError: continue` two lines below. It reads as a guard and guards
nothing (mutation `M4` survives green, as it must).

This is *not* true of its counterpart at `:148-149` — there `time(hour, 99)`
would raise uncaught, so the time-only check is load-bearing. The symmetry is
what makes the dead one look alive.

**Suggested change:** delete lines 87-88, or keep them and add a comment saying
they only short-circuit an error the loop would catch anyway. Deleting is
cleaner; the I1 test above then covers the behaviour.

### M2 — `_dated_target`'s docstring contradicts the test the diff ships

`packages/herder/src/herder/limits.py:74-76`: *"A date that has already passed
therefore resolves a full year out, which no caller's bound admits."* The
first assertion of `test_parse_reset_dated_rolls_to_next_year_then_fails_the_bound`
is a counter-example: on 2026-12-31, `"Jan 2"` has already passed this year,
resolves to 2027-01-02, is **two days** out, and is admitted — correctly.

**Suggested change:** *"…resolves to the same date next year, which no bound
admits except across the New Year boundary, where the roll is the right answer
and is short enough to pass."*

### M3 — The `_RESET_RE` header comment is now stale and actively misleading

`packages/herder/src/herder/limits.py:43-45`: *"'resets at …', 'resets 11am'
with no minutes … all correctly fail to match and **yield None** rather than
guessing."* Both of those shapes are now handled by the sibling pattern eleven
lines below, and `parse_reset` no longer yields `None` for them. The comment
survived the diff untouched.

**Suggested change:** scope it explicitly to the pattern — *"…fail to match
**this** pattern; the dated form below picks up the minute-less shape."*

### M4 — Month matching is looser than the measured input, and `[:3]` is a no-op

`packages/herder/src/herder/limits.py:61` and `:79`. `([A-Za-z]{3})[a-z]*\.?`
with `re.I` accepts `"Sepxyz 12"` as September 12 (measured), and full month
names / `"Sep."` are tolerated although the measured `/usage` output renders
`"Sep"` — YAGNI, and it widens the misfire surface. `month_s[:3]` at `:79` is a
no-op because the group is exactly three characters (mutation `M7`, dropping
the slice, survives green — it cannot fail).

**Suggested change:** either drop the `[a-z]*\.?` tolerance and the now-pointless
`[:3]`, or keep the tolerance and anchor it and add a one-line comment saying
why an unmeasured shape is accepted. Also unpinned: a bogus month word
(`"resets Foo 5 at 7am (…)"`) — mutation `M3`, which turns any unknown month
into January, survives green.

### M5 — An ambiguous local hour resolves to the *earlier* instant, which is the wrong side for a reset

`packages/herder/src/herder/limits.py:92-93` (and `:151`, pre-existing).
Measured: `"resets Nov 1 at 1:30am (America/New_York)"` on the fall-back date
resolves to `05:30 UTC` (EDT, `fold=0`), not `06:30 UTC` (EST, `fold=1`). For a
*reset* the later instant is the safe one — waking on the earlier one means the
window has not actually rolled over and the caller burns a refusal. The window
is one hour a year and a weekly reset is unlikely to land in it, so this is a
Minor, but nothing in the module says a choice was made.

Related: the pre-existing `test_reset_survives_a_dst_boundary` does not exercise
an ambiguous or non-existent time at all (11:10am on Nov 1 is nine hours past
the transition) — the name over-promises relative to the body. Not introduced
by this diff, but the diff doubles the surface it nominally covers.

**Suggested change:** pass `fold=1` in both constructions with a one-line
comment ("a reset that is ambiguous across a fall-back has not happened until
the later instant"), or state the deliberate `fold=0` choice in a comment.

### M6 — The two branches are asymmetric; the time-only path is still inline

`packages/herder/src/herder/limits.py:139-157`. The dated path is a clean
`_dated_target` helper, the time-only path is fifteen inline lines inside
`parse_reset`, and the two duplicate the `ZoneInfo` try/except and the
minute-range check. `_hour24(hour12, meridiem)` is recomputed three times in
the time-only branch. The `# noqa: BLE001 - see _dated_target` at `:146` points
at a comment in another function.

**Suggested change:** extract a `_time_only_target(m, now)` mirroring
`_dated_target`, leaving `parse_reset` as dispatch + bound check. Behaviour is
unchanged, so the existing tests carry the refactor.

### M7 — `max_ahead_s`'s default binds `MAX_RESET_AHEAD_S` at import time

`packages/herder/src/herder/limits.py:117`. The old body read the constant at
call time; the default argument now snapshots it at import. Any later
`monkeypatch.setattr(limits, "MAX_RESET_AHEAD_S", …)` silently has no effect —
a quiet trap for the downstream phase-2 tasks. Nothing pins the default value
in a way that would notice, either: `M8` (flipping the bound comparison from
`>` to `>=`) survives green, and no test sits exactly on the bound for the
dated path.

**Suggested change:** no code change needed if it is deliberate — one docstring
sentence ("the default is bound at import; pass `max_ahead_s` explicitly rather
than patching the constant") is enough.

### M8 — `classify()` does not use the new parameter, so the dated form is unreachable from the refusal path

`packages/herder/src/herder/limits.py:169`. `classify` knows the scope
(`seven_day`) at that call site but still passes the 5.5h default, so a weekly
refusal naming a dated reset classifies with `resets_at=None` (measured). The
global constraints say "refusal classification unchanged", and the weekly
refusal wording is still unobserved, so I read this as deliberate — but a
reader arriving at the new "the bound is a property of the WINDOW" docstring
and then at this call site will think it is an oversight.

**Suggested change:** one comment at `:169` — *"deliberately the session bound:
the 7-day refusal's wording is unobserved, and /usage (usage.py) is where the
weekly bound is applied."*

### M9 — `test_parse_reset_dated_rolls_to_next_year_then_fails_the_bound` is two tests, and its name describes only the second

`packages/herder/tests/test_limits.py:196`. The first assertion rolls to next
year and **passes** the bound; the name says it fails it. Both behaviours are
worth pinning, but they are different behaviours.

**Suggested change:** split into
`test_dated_reset_rolls_across_the_new_year` and
`test_dated_reset_a_year_out_fails_every_bound`.

### M10 — `test_parse_reset_still_handles_the_refusal_form_unchanged` duplicates an existing test

`packages/herder/tests/test_limits.py:214`. Same text, same expected instant
(15:10 UTC) as `test_reset_is_read_in_the_zone_the_message_names_not_the_callers`
at `:59`; only `now` differs (12:00 vs 13:00 UTC, both the same day, both inside
the bound). It is not tautological and it would catch a dated-branch takeover of
the refusal form, so it earns its keep as a regression pin — but its comment
should say that, otherwise it reads as an accidental copy.

**Suggested change:** add the one-line comment: *"pins that the dated pattern,
tried first, never swallows the refusal shape."*

---

## Not findings (checked, clean)

- No hour-range validation on either pattern (`"45:30pm"` → 21:30), but that is
  pre-existing in `_RESET_RE` and the bound catches nonsense downstream.
- `now = now or datetime.now(...)` moved above the match — no behavioural
  difference (datetimes are always truthy, no side effects between).
- `openrouter.py` untouched; `herder` imports nothing from `llama`; the diff
  touches exactly the two files the brief names.
- No commits were made by this review, and nothing in the worktree was modified.
