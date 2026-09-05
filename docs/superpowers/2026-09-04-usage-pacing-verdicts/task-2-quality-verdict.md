# Task 2 — CODE-QUALITY verdict

**Verdict: Changes requested** (0 Critical, 4 Important, 7 Minor)

Reviewed: `05d6279..baf633d` — `packages/herder/src/herder/limits.py` (new, 94 lines),
`packages/herder/tests/test_limits.py` (new, 80 lines),
`packages/herder/src/herder/__init__.py` (+1). Read-only; no edits, no commits.

## What is right, verified rather than assumed

I worked the arithmetic independently rather than trusting the tests.

- **The central safety property holds.** I swept 1,728 combinations
  (hour 1–12 × am/pm × minute 0/10/59 × `now` at each of 24 hours) through
  `parse_reset`. Every accepted result is **strictly in the future**, and the
  **maximum accepted lead is 5.050 h**. No input path manufactures a long sleep,
  and none yields a negative one. The bound's comparison direction is correct
  and *is* pinned — flipping `>` to `<` fails the suite.
- **The am/pm conversion is correct at both breaking values.**
  `int(h) % 12 + (12 if pm)` gives 12am → 0 and 12pm → 12. The naive
  `int(h) + (12 if pm)` gives 12 and 24. The shipped formula is right.
- **The ambiguous (fall-back) hour errs in the safe direction.**
  `datetime.combine(..., tzinfo=tz)` defaults to `fold=0`, so a reset named
  `1:30am` on 2026-11-01 resolves to 05:30 UTC (EDT, the *earlier* of the two
  real instants) rather than 06:30 UTC. Waking up to an hour early costs one
  extra refused call; waking an hour late costs an hour of idle. Right choice —
  see Minor 8 on making it deliberate rather than accidental.
- Stdlib only; no `llama`/`emcee` import; tests offline with time injected;
  module docstring style, import placement and line lengths (max 86) all match
  the surrounding `herder` package.

No Critical: every failure mode I found degrades to `resets_at=None` or to a
bounded-and-slightly-wrong instant, never to an unbounded idle.

## Important

### I1. Seven of eight constraints in this module are unpinned — the suite is largely decorative

The report cites "10 passed" as evidence. It is not. I mutation-tested by reading
`limits.py`, applying one mutation in memory, injecting it as `herder.limits`, and
running the shipped 10 test functions against it. The harness is proven live:
the unmutated baseline passes, and M7 is killed.

| # | Mutation | Result |
|---|---|---|
| M1 | `% 12` → naive `int(h12) + 12` | **SURVIVED** |
| M2 | `MAX_RESET_AHEAD_S` 5.5 h → **20 h** | **SURVIVED** |
| M3 | delete the minute range guard entirely | **SURVIVED** |
| M4 | rollover `target <= local` → `<` | **SURVIVED** |
| M5 | delete the `usage limit reached` signature | **SURVIVED** |
| M6 | delete the `seven_day` signature | **SURVIVED** |
| M7 | truncation `[:500]` → `[:20]` | killed |
| M8 | reorder `_SIGNATURES`, generic pattern first | **SURVIVED** |

Only the message truncation is pinned, and only incidentally (via
`assert "session limit" in str(err)`). **Two of the three `_SIGNATURES` entries
have no test at all** — delete either and the suite stays green.

M1 is the sharpest: every test uses `11:10am`, where the correct and the naive
formulas agree (`grep -o 'resets [0-9:]*[ap]m'` returns three hits, all
`11:10am`). So the `% 12` — the exact thing the brief asked me to check — is
carried by no test. It is also doing unadvertised double duty: it caps `hour` at
23, which is what stops `13pm` from reaching `time(25, 30)` and raising an
uncaught `ValueError`.

This is the repo's own recorded lesson (`green-suite-does-not-mean-pinned`)
reproduced verbatim. Ask for tests at `12:00am`, `12:00pm`, an out-of-range
minute, both bound edges, and one text per signature.

### I2. `MAX_RESET_AHEAD_S` — the module's declared safety constant — is unpinned, by a test whose name promises otherwise

The comment says "parsing must never be able to manufacture a day-long sleep."
Computed from the fixtures: the largest **accepted** delta any test exercises is
**4.17 h**; the smallest **rejected** delta is **23.17 h**. Any value in
`[4.17 h, 23.17 h)` passes all ten tests — I confirmed **20 h passes**, i.e. a
value that permits precisely the day-long sleep the comment forbids.

`test_reset_past_today_rolls_to_tomorrow_only_within_the_bound` reads as the
pin and is not one; it only rejects something 23 h out. Two edge tests fix it:
`now = 05:00` (6 h 10 m out → `None`) and `now = 06:00` (5 h 10 m out →
accepted). `limits.py:26`.

### I3. `_RESET_RE`'s zone class misses real IANA names — `UTC` most consequentially

`limits.py:39-40`: `([A-Za-z_]+/[A-Za-z_+-]+)` requires **exactly one** `/` and
admits no digits. Measured against real zones:

| Zone | Result |
|---|---|
| `UTC` | **MISS** (no slash) |
| `America/Indiana/Indianapolis` | **MISS** (two slashes) |
| `America/Kentucky/Louisville` | **MISS** |
| `America/Argentina/Buenos_Aires` | **MISS** |
| `America/North_Dakota/Center` | **MISS** |
| `Etc/GMT+5` | **MISS** (digit) |
| `America/New_York`, `Europe/London`, `Asia/Ho_Chi_Minh`, `America/Port-au-Prince`, `Asia/Ust-Nera`, `Pacific/Auckland` | match |

`UTC` is the one that matters: a headless CI/server host is the most likely place
an unattended run hits a session limit, and `TZ=UTC` is that host's default. The
feature would silently lose the reset instant in exactly its target deployment.

Consequence is safe (`resets_at=None`, not a wrong time) but silent. Small fix:
`([A-Za-z_]+(?:/[A-Za-z0-9_+-]+)*)`.

Also missed, lower stakes: `resets at 11:10am (...)`, `resets 11am (...)`,
`resets 11:10am` with no zone. Each returns `None`. Worth one comment recording
that only the measured shape is handled on purpose.

### I4. Two of three `_SIGNATURES` are speculative; one is unlabelled, and the ordering is silently load-bearing

`limits.py:28-35`. The docstring commits to a strict asymmetry — "A false
positive is worse than a false negative … So the patterns are narrow."

- `hit your session limit` — measured, dated, labelled. Correct.
- `(weekly|7-day|seven[ -]day) limit` — carries an explicit "Unverified" comment. Honest.
- `usage limit reached` — **no comment, no measurement, no test**, and the
  loosest of the three. It is also the only one yielding `scope=None`, which the
  second pattern's own comment describes as pausing without naming a window.

An unmeasured, unlabelled, untested pattern is the weakest link in a design whose
stated invariant is that a false positive idles a run for hours. Under YAGNI I'd
drop both unverified patterns and add each with its capture when observed; at
minimum give the third the same "Unverified" label the second has.

Separately: **the tuple order is load-bearing and nothing says so.** A text
matching both `hit your session limit` and `usage limit reached` must classify
`five_hour`, not `None` — that holds only because the specific pattern is listed
first. M8 confirmed reordering is invisible to the suite. Add a one-line comment
("most specific first — first match wins") and a text matching two patterns.

## Minor

5. **`except Exception` at `limits.py:71` is too wide and breaks the package's own convention.** Every other broad except in this repo carries `# noqa: BLE001 - <reason>` (`failures.py:48`, `emcee/speech_text.py:91,99`, `llama/jerrybase.py:128`); this one has neither noqa nor reason. On width: the `try` wraps a single `ZoneInfo(name)` call whose real failures are `ZoneInfoNotFoundError` (a `KeyError`) and `ValueError`. As written it also swallows an `OSError` from a broken or unreadable tzdata install — which would make *every* zone silently unresolvable, indistinguishable from a bogus zone name, with no diagnostic anywhere. Narrowing to `except (ZoneInfoNotFoundError, ValueError)` keeps the existing `Mars/Olympus` test green.

6. **No hour range guard, asymmetric with the minute guard.** `limits.py:73-75`: `\d{1,2}` admits `25:10am`, which `% 12` silently turns into 1:10am and the function returns as a genuine reset instant (verified). The guard immediately below correctly rejects `11:75am`. One garbage input is caught, the neighbouring one is coerced. Add `if not 1 <= int(hour12) <= 12` beside it. Note also that `% 12` is what prevents `time(25, 30)` from raising — worth a comment, since the line reads as pure format conversion.

7. **A naive `now` silently reads as machine-local time.** `now.astimezone(tz)` on a naive datetime assumes the host zone, so `parse_reset(text, now=datetime(2026, 9, 4, 8, 30))` returns a host-dependent answer (verified). For a module whose entire contract is injected deterministic time, and which tasks 3/4/7 will call, a caller writing `datetime.now()` instead of `datetime.now(timezone.utc)` gets a silently wrong result on any non-UTC host. Assert awareness or document the precondition.

8. **Nonexistent wall-clock times resolve an hour late, silently.** A reset named in the spring-forward gap (`2:30am` on 2026-03-08 in NY) resolves to 07:30 UTC = 03:30 EDT (verified) — an hour of extra idle. Bounded and rare, so fine to accept; but the ambiguous-hour case (which resolves *early*, the safe direction) is correct only by `combine`'s `fold=0` default. Both are untested. One comment recording that the safe direction was chosen deliberately would keep a future "simplification" from inverting it.

9. **Exact-equality rollover is a knife-edge and unpinned.** `limits.py:80`: `target <= local` means that when `now` is exactly the reset instant, the function rolls to tomorrow and is then refused by the bound, returning `None`; with `<` it would return `now`. Both defensible, neither documented nor tested (M4 survived). Pick one and pin it.

10. **The module docstring misquotes the string it claims to have captured verbatim.** `limits.py:5` renders the separator as an ASCII hyphen (`session limit - resets`) where the real captured string — and the test fixture at `test_limits.py:10` — use U+00B7 (`·`); the test file even comments "must not be normalized away". This docstring is the standing record behind "Do not loosen without a new capture," so its fidelity is load-bearing for the next person re-deriving the regex.

11. **Namespace and idiom nits.** `__init__.py:2` exports `classify` and `parse_reset` into the top-level namespace under very generic names — `herder.classify` does not say what it classifies, and per the brief only `RateLimited` is actually needed by tasks 3/4/7; consider exporting just that and leaving the functions on the submodule. Also `re.Pattern` in the `_SIGNATURES` annotation (`limits.py:28`) should be `re.Pattern[str]`, and `now = now or datetime.now(timezone.utc)` (`limits.py:77`) is the truthiness idiom where `if now is None:` is meant — harmless here since datetimes are always truthy, but it is the footgun form.

## Scope and process

Scope adherence is clean: exactly the three named files, no drift into Task 1's
`failures.py` or Tasks 3/4's `claude_cli.py`/`tasks.py`, no constant relaxed, no
pattern broadened. The implementer followed the brief verbatim — which is why
most findings above are inherited from the brief's own code block rather than
introduced. The report's "Concerns: None" is the one thing I'd push back on:
the suite it cites does not pin the constants the module declares load-bearing,
and that was discoverable by mutation before dispatch.

Full evidence log:
`/private/tmp/claude-501/-Users-shawn-projects-llama/f837f2ba-0078-43a2-bff3-c0a07ce36ae0/scratchpad/sdd/t2qual/t2qual.log`
