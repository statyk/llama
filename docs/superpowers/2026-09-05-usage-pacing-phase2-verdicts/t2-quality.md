# Code-quality review — Task 2 (`herder/usage.py`)

Range `e2ada6a..8c0a56d`. Reviewer: code quality only (spec compliance is a separate review).

## Verdict: **Changes requested**

The parser itself is correct against every input shape I could construct for the observed
`/usage` format — I found no live defect in the shipped code. What I did find is that the
**tests pin almost none of what the module promises**: 16 of 30 one-line mutations survive a
green run, and among the survivors are (a) the line-based-parsing property that is the module's
whole stated reason for existing in this shape, and (b) every single field of the per-model
meter. The implementer's self-audit named 4 survivors; all 4 confirm, and there are 12 more.

## Mutation harness — proof it looked

Private copy at `$D/work/t2-quality/`; the worktree was never modified and its suite never run.
`herder` resolves to the copy via `PYTHONPATH` (a planted `SENTINEL_MARKER` was read back from
`.../work/t2-quality/src/herder/usage.py`, proving shadowing over the main venv's
`_editable_impl_llama_herder.pth`). Runner is `.venv/bin/python -m pytest`, never the console
script.

- **Control: `6 passed`** (rc=0) against the unmutated copy.
- **30 mutants applied, 14 correctly CAUGHT** — including the stale-marker literal, the
  negative lookahead, `re.M` removal, `\d+`→`\d`, the session percent, the weekly bound, and
  moving the stale check after the session parse. An empty survivor list would therefore have
  been a real result, not a check that never looked.
- **16 SURVIVED.** Full log: `$D/t2-quality/t2-quality.log`.

---

## Findings

### Important

**1. `usage.py:37-42,72-85` — the line-based-parsing property is pinned by nothing.**
The spec calls the parse "Line-based", and the brief states `parse_usage_text` slices per line
precisely because `limits.parse_reset` documents a single-clause contract (its dated `.search`
scans the whole string and silently discards a time-only clause). That slicing is implemented
by `(.*)$` in all three regexes — and widening any one of them to span lines survives green:

| mutation | result |
| --- | --- |
| `_SESSION_RE` `(.*)$` → `([\s\S]*)$` | **SURVIVED** |
| `_WEEK_ALL_RE` `(.*)$` → `([\s\S]*)$` | **SURVIVED** |
| `_WEEK_MODEL_RE` `(.*)$` → `([\s\S]*)$` | **SURVIVED** |
| `_SESSION_RE` `^` anchor dropped | **SURVIVED** |
| `_SESSION_RE` `$` anchor dropped | **SURVIVED** |

The `REAL` fixture cannot see the difference because its session line carries its *own* dated
clause, which is also the first in the text — so the unsliced variant happens to pick the right
one. The harm is real and inside the bound that is supposed to catch it; measured directly:

```
text: "Current session: 10% used\n"
      "Current week (all models): 7% used - resets Sep 12 at 7am (America/New_York)\n"
now = 2026-09-12 05:00 EDT
  sliced   session reset -> None                       (correct: the line names no reset)
  unsliced session reset -> 2026-09-12 11:00:00+00:00  (the WEEKLY reset, worn as the session's)
```
That instant is under `FIVE_HOUR_MAX_AHEAD_S`, so the bound does not reject it — the downstream
`decide()` would pause the run for hours against a session window that may reset far sooner.

*Suggested change:* add a test whose session line has **no** reset clause while the weekly line
has one within 5.5 h, asserting `five_hour.resets_at is None`. That one test kills all five
mutations above and pins the contract the module was shaped around.

**2. `test_usage.py:28` — the per-model meter is entirely unpinned; the only assertion on it is
effectively tautological.** `assert r.per_model == {"Fable": usage.Meter(0, None)}` is the sole
check, and both of that `Meter`'s fields are their own zero value. Consequently every part of
the `usage.py:80-85` comprehension can be mutated with the suite still green:

- `Meter(int(mm.group(2)), …)` → `Meter(0, …)` — **SURVIVED** (the fixture's percent *is* 0)
- `parse_reset(mm.group(3), …)` → `parse_reset(mm.group(2), …)` — **SURVIVED**
- `mm.group(1).strip()` → `mm.group(1)` — **SURVIVED**
- per-model bound `SEVEN_DAY_MAX_AHEAD_S` → `FIVE_HOUR_MAX_AHEAD_S` — **SURVIVED**

Four survivors in a three-line comprehension: nothing in the suite distinguishes "parsed the
per-model line" from "returned a zeroed meter under the right key".

*Suggested change:* extend `REAL` (or add a second fixture) with a per-model line carrying a
**non-zero** percent **and** its own dated reset clause — e.g.
`Current week (Opus): 31% used · resets Sep 12 at 7am (America/New_York)` — and assert both
fields. Add one key with surrounding whitespace to pin `.strip()`.

**3. `usage.py:72-73` — the five-hour bound is never exercised by this module's tests.**
Confirms the implementer's item (1): swapping `FIVE_HOUR_MAX_AHEAD_S` → `SEVEN_DAY_MAX_AHEAD_S`
on the session call **SURVIVES**, because the fixture's session reset is ~50 min out and clears
both bounds. The reverse (`test_weekly_reset_uses_the_weekly_bound_not_the_session_one`) is
pinned; the direction that actually protects against a manufactured long sleep is not — which
is the asymmetry the spec's own mutation list calls out.

*Suggested change:* one test with a session line whose reset is ~7 days out (a mis-parse or a
clock skew), asserting `five_hour.resets_at is None`.

### Minor

**4. `usage.py:20,22` — `json` and `subprocess` are imported and unused.** The implementer's
reasoning (Task 3's `read_usage` lands in this file) is sound, but as merged this is dead code
in shipped source. There is no ruff/flake8 config and no CI lint step (only `release.yml`), so
nothing will flag it. Either drop the two imports now and let Task 3 add them back, or leave
them with a one-line comment saying why.

**5. `usage.py:86-87` — `fetched_at` is asserted nowhere.** Confirms the implementer's item (4):
`fetched_at=now` → `fetched_at=None` **SURVIVES**. Add `assert r.fetched_at == NOW` to
`test_parses_all_three_meters_from_the_real_output`. Related: the field's declared type is
`datetime | None = None` while the brief's interface says `fetched_at: datetime`; the `None`
default lets a `UsageReading` be built with no timestamp at all.

**6. `usage.py:67` — the stale-marker check is exact and case-sensitive.** Placement is right:
it is the first statement of the only public entry point, ahead of every parse, and moving it
after the session parse is **caught**. Nothing in this module bypasses it. But
`"showing last-known usage"` (lower-cased banner) is accepted as a live reading, and loosening
the check to `.lower()` on both sides **SURVIVES** green — i.e. nothing pins the strictness
either way. For the one case where the command exits 0 and the number is a lie, I'd prefer the
looser match: `re.search(r"showing last[- ]known usage", text, re.I)`, with a test for a
case-varied banner.

**7. `usage.py:72,77,81` — no bound on the percent.** `Current session: 999% used` parses to
`Meter(percent=999)`, and `0999%` to `999`. A negative sign fails to match and correctly yields
`None`, so only the high side is open. The failure direction is conservative (over-pausing), so
this is not urgent, but a reading above 100 is by definition untrustworthy and the docstring
promises `None` for "anything else unrecognizable". Consider rejecting `> 100`.

**8. `usage.py:51-55` — `UsageReading(frozen=True)` is only shallowly frozen.** `per_model` is a
plain `dict`; `r.per_model["injected"] = Meter(99, None)` succeeds on a frozen instance
(verified). `UsageReading` is also unhashable for the same reason. Both are fine for the current
callers — worth knowing before someone caches a reading by key. Dropping `frozen=True` from
`Meter` also **SURVIVES** green.

**9. `usage.py:38,42` — the string `all models` is duplicated** between `_WEEK_ALL_RE`'s literal
and `_WEEK_MODEL_RE`'s negative lookahead. Drift in either direction *is* caught by the suite,
so this is cosmetic; a shared `_ALL_MODELS = r"all models"` interpolated into both would make
the coupling explicit.

**10. `test_usage.py:31-36` — the test's name and comment are broader than its assertion.**
It promises the per-model regex "does not swallow the all-models line" but asserts only
`"all models" not in r.per_model` — an exact-case key check. With `Current week (All models):`
the reading silently gains an `"All models"` sub-meter *and* loses `seven_day`, and this test
still passes (verified). Assert on the whole dict (`r.per_model == {"Fable": …}`) or match keys
case-insensitively.

### Observed and NOT a problem (recorded so it isn't re-derived)

- **CRLF input parses correctly.** `.` matches `\r` and `$` under `re.M` sits before the `\n`,
  so the trailing `\r` lands harmlessly inside the reset group, outside `parse_reset`'s closing
  `\)`. Verified end-to-end on a CRLF `REAL`.
- **`re.M` + `^`/`$` behaves as the code assumes**, and `(.*)` genuinely cannot cross a newline —
  the slicing claim is true as written (it is merely untested; see finding 1).
- **A per-model name containing `)`** (`(Opus 4.5 (beta))`) drops that sub-meter silently rather
  than mis-parsing it — fail-closed, acceptable.
- **A `Current session:` match mid-prose is impossible** while `^` is present; an indented meter
  line yields `None` for the whole reading — fail-closed, consistent with the docstring.
- **`parse_usage_text(None)` returns `None`** rather than raising, upholding the never-raises
  contract despite the `str` annotation. Removing the `not text` guard survives green, but that
  mutant is *equivalent* for `str` input (`_SESSION_RE.search("")` misses anyway) — the guard's
  only real job is the `None` case, which no test covers.
- Duplication, altitude, docstring accuracy and error handling are otherwise good. The module
  docstring's rationale for staying separate from `limits`, and for not reading
  `cachedUsageUtilization`, is the kind of comment that earns its space.

## Commits

None made — reviewers do not commit, and I had no reason to want one.
