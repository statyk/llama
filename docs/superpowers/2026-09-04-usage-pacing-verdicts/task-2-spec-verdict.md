# Task 2 — SPEC-COMPLIANCE verdict

**Reviewer:** spec-compliance (Opus), read-only.
**Diff under review:** `05d6279..baf633d` (1 commit, 3 files, +175/-0)
**Binding authority:** `docs/superpowers/specs/2026-09-04-usage-pacing-design.md`
("Measured signals" item 4, lines 86-110; "Testing", lines 375-419;
"herder changes", lines 120-166), above `task-2-brief.md`.

## Spec verdict: ✅ PASS

The commit is **byte-identical** to the brief's literal code for both new
files, and the export is the single line the brief specified in the position
it specified. No scope creep, no divergence, no missing requirement. The four
load-bearing properties I was asked to check specifically all verify at the
byte / operator level, not merely at the "test passes" level.

## Requirement-by-requirement

| # | Requirement | Where met | Note |
|---|---|---|---|
| 1 | Create `packages/herder/src/herder/limits.py` | `packages/herder/src/herder/limits.py:1-94` (new) | Verified byte-identical to the brief's Step-3 code block (mechanical diff after strip; zero differing lines). |
| 2 | Create `packages/herder/tests/test_limits.py` | `packages/herder/tests/test_limits.py:1-80` (new) | Verified byte-identical to the brief's Step-1 code block. 10 `def test_` functions, matching the brief's 10. |
| 3 | ONE export line in `__init__.py`, after the `FakeProvider` line | `packages/herder/src/herder/__init__.py:2` | `from herder.limits import RateLimited, classify, parse_reset`. Exactly one added line, exactly the specified position. No `__all__` exists in this module, so no second edit was owed. |
| 4 | `RateLimited(HerderError)` with `scope: str \| None`, `resets_at: datetime \| None` | `limits.py:53-66` | Subclasses `HerderError` imported from `herder.provider` (`limits.py:21`), which is what makes the spec's Integration ordering hazard (`cli.py:237`) real for Task 5. Spec (line 122) types `scope` as the literal union `"five_hour" \| "seven_day" \| None`; the implementation annotates `str \| None`. Looser annotation, identical value set. Benign. |
| 5 | `classify(text, now=None) -> RateLimited \| None` | `limits.py:87-93` | Ordered scan of `_SIGNATURES`; first match wins; returns `RateLimited(text.strip()[:500], scope=…, resets_at=parse_reset(text, now))`. |
| 6 | `parse_reset(text, now=None) -> datetime \| None` | `limits.py:69-84` | Returns a UTC-normalized instant or `None`. |
| 7 | Spec "Measured signals" item 4 — positive fixture is the measured string, verbatim | `test_limits.py:9-12` | Implicit concatenation reassembles to exactly the spec's line 91 string, prefix included. The `claude exited 1: ` prefix is genuine, not invented: `claude_cli.py:126` renders `f"claude exited {proc.returncode}: {_error_detail(proc)}"`. |
| 8 | Spec "Testing" — reset parsing tested with frozen `now` on **both sides** of the named time | `test_limits.py:36-39` (08:30, before) and `test_limits.py:42-46` (12:00, after) | Both sides present, both with an injected `now`. |
| 9 | Spec "Testing" — DST-boundary test in `America/New_York` | `test_limits.py:63-69` | 2026-11-01, the morning after the EDT→EST switch; asserts against `datetime(...,tzinfo=NY).astimezone(utc)`, so the expected value is computed by `zoneinfo` rather than hard-coded — it cannot pass by a coincidental offset. |
| 10 | Spec "Testing" — sanity bound yields `None`, not a long sleep | `test_limits.py:41-46`, enforced at `limits.py:81-83` | See load-bearing check C below. |
| 11 | Offline / deterministic; time injected via `now` | whole test file | Every test that reaches the clock passes an explicit aware `now`. The only `datetime.now()` is the `now or datetime.now(timezone.utc)` default at `limits.py:79`, which no test reaches (the three tests omitting `now` — `test_dropped_connection_is_not_a_rate_limit`, `test_ordinary_failures_are_not_rate_limits`, `test_unknown_zone_or_unparseable_time_yields_no_reset` — all short-circuit before line 79: two never match a signature, the third returns at the `_RESET_RE` miss / `ZoneInfo` failure). No `$HOME` read, no sleeping. |
| 12 | Python 3.11+, no new third-party deps | `limits.py:17-21` | `re`, `datetime`, `zoneinfo` (stdlib) + `herder.provider`. |
| 13 | `herder` must not import `llama` or `emcee` | `limits.py:17-21`, `test_limits.py:1-4` | Neither file references either package. |
| 14 | Commit style `type(scope): subject` | `baf633d` | `feat(herder): classify usage-window exhaustion as RateLimited`. Body records both test commands and their output. |
| 15 | Pure functions only — no wiring into the provider | diff `--name-only` | `claude_cli.py` and `tasks.py` are absent from the commit. |

## The four load-bearing checks

**A. U+00B7 MIDDLE DOT, verified at the byte level — ✅**
Read out of the committed blob (`git show baf633d:…`), not the working tree:
the UTF-8 sequence `C2 B7` occurs **exactly twice**, at
`test_limits.py:10` (the `SESSION_LIMIT` fixture) and `test_limits.py:66`
(`test_reset_survives_a_dst_boundary`'s local `text`). It is a real U+00B7,
not an ASCII hyphen (`2D`), not a bullet (`E2 80 A2`), not a normalized
substitute. This satisfies the spec's explicit instruction (line 393-394)
that the dot "must survive as a literal rather than being normalized into
the pattern" — and note the classifier never matches on the dot at all
(`_SIGNATURES[0]` is `hit your session limit`), so the literal is doing its
job as a *fixture* fidelity guard, which is exactly the spec's intent.

**B. `CLOSED_MID` classifies as `None` — ✅**
Pinned at `test_limits.py:23-24`, and I traced it against all three
signatures independently of the test: the string
`claude exited 1: API Error: Connection closed mid-response. The response
above may be incomplete.` contains no `hit your session limit`, no
`(weekly|7-day|seven[ -]day) limit` (the token `limit` does not appear at
all — `incomplete` is not a match), and no `usage limit reached`. Returns
`None` by falling off the loop at `limits.py:93`.
Fidelity of the fixture itself: the spec (line 388) points at "the
`CLOSED_MID` fixture already in `test_claude_cli.py`". That one
(`test_claude_cli.py:138-146`) is the JSON *envelope* dict; its `result`
field is `"API Error: Connection closed mid-response. The response above may
be incomplete."`, and `_error_detail` (`claude_cli.py:85-105`) returns that
`result` verbatim, which `claude_cli.py:126` then prefixes with
`claude exited 1: `. The string in `test_limits.py` is therefore the
**exact** rendered form of the existing fixture, reconstructed rather than
imported. Substance satisfied; see Minor 1 for the residual.

**C. `MAX_RESET_AHEAD_S` — operator and direction both correct — ✅**
`limits.py:38`: `MAX_RESET_AHEAD_S = 5.5 * 3600` (19800.0 s).
`limits.py:81-83`:
```
    out = target.astimezone(timezone.utc)
    if (out - now.astimezone(timezone.utc)).total_seconds() > MAX_RESET_AHEAD_S:
        return None
```
Direction verified: `out` is always strictly in the future of `now` (the
`target <= local` roll-forward at `limits.py:78-80` guarantees it), so the
delta is non-negative and the `>` refuses only the far side. A rolled-to-
tomorrow reset is ~24 h out and is refused — which is precisely the
"parsing must never be able to manufacture a day-long sleep" clause of spec
line 145-148. Boundary is consistent with the test: the code rejects at
`> 5.5h`, so exactly 5.5 h is accepted, and `test_limits.py:52` asserts
`<= timedelta(hours=5.5)`. No off-by-one between code and pin.
Failure mode on refusal is the safe one: `classify` still returns a
`RateLimited` with `resets_at=None` (pinned at `test_limits.py:76-79`), so
the caller falls back to `unknown_reset_wait` rather than sleeping a day.

**D. Zone of the message, and next-future-occurrence — ✅**
`limits.py:74-80` resolves `tz` from the **message's** captured zone name and
does `local = now.astimezone(tz)` before combining — the caller's zone is used
only to place `now` on the timeline, never to interpret the wall-clock time.
Pinned adversarially at `test_limits.py:56-60`: caller in UTC, message in
`America/New_York`, expecting 15:10 UTC. Next-future-occurrence is the
`target <= local` roll-forward at `limits.py:78-80`; `<=` (not `<`) means a
reset naming the current minute rolls forward rather than resolving to a
zero-length wait. Pinned at `test_limits.py:34-39` and `:42-46`.

**E. `_SIGNATURES` is the narrow, ordered list — ✅** (fifth check, same class)
`limits.py:40-49` carries exactly three entries in exactly the brief's order,
with exactly the brief's patterns and scopes. Nothing broadened (no bare
`limit`, no `rate limit`, no `429`), nothing added, nothing reordered. Since
`classify` returns on first match, order is semantic, and `five_hour` sits
first — the only measured one.

## Scope creep

**None.** `git diff --name-only 05d6279..baf633d` returns exactly the three
brief-named paths and nothing else. Specifically confirmed untouched:
`packages/herder/src/herder/claude_cli.py` (Task 3),
`packages/herder/src/herder/tasks.py` (Task 4),
`packages/herder/src/herder/failures.py` (Task 1, landed at `05d6279`).
The `__init__.py` change is one added line with no reformatting of the
surrounding import block.

**Deliberate under-delivery, correctly deferred (not a finding).** The spec's
"herder changes" section also assigns `read_usage_snapshot(path)`
(spec:150-155), a config-overridable pattern list, and an `api_error_status`
structured discriminator (spec:135-140) to `limits.py`. None appear here.
That is correct, not missing: the spec's own "Implementation order" puts the
snapshot reader at item 3, and the `api_error_status` discriminator is
conditional on Task 1's capture actually showing an HTTP status — which has
not been observed yet. Reviewed as in-scope-for-a-later-task.

## Exact-value fidelity

The brief carried literal code for all three edits. I extracted the brief's
fenced Python blocks and diffed them mechanically against the committed
blobs: **`limits.py` IDENTICAL, `test_limits.py` IDENTICAL** (zero differing
lines after leading/trailing-whitespace strip), and the `__init__.py` line
matches the brief's Step-4 block character for character. No divergence to
adjudicate. Constants as specified: `MAX_RESET_AHEAD_S = 5.5 * 3600`,
`_RESET_RE` unmodified, `[:500]` truncation unmodified.

## Findings

**Minor 1 — the docstring quotes the measured string with an ASCII hyphen
where the spec has the middle dot.** `limits.py:5` reads
`claude exited 1: You've hit your session limit - resets 11:10am
(America/New_York)`, but the spec's captured line (spec:91) has `·`. This is
the brief's own text reproduced faithfully, it is a docstring with no
matching role, and the literal survives where it is load-bearing (the test
fixture, check A). Cosmetic documentation drift against the one string this
spec section tells everyone not to normalize. No behavioral effect.

**Minor 2 — `CLOSED_MID` is duplicated rather than imported from
`test_claude_cli.py`.** The spec (line 388) phrases the negative set as "the
`CLOSED_MID` fixture already in `test_claude_cli.py`". Importing it is not
mechanically possible as written (that fixture is the envelope dict; this
test needs the rendered string), and the duplicate is byte-exact for the
rendered form today — so the requirement is met in substance. The residual
is drift: if `_error_detail`'s rendering changes, the two fixtures diverge
silently and the negative test could go stale while still passing. Worth a
comment at most; the brief specified the duplication, so this is not the
implementer's deviation.

**Minor 3 — the injected-`now` contract is unpinned for a naive datetime.**
`limits.py:79-84` calls `.astimezone()` on `now`; a naive `now` would be
assumed to be in the system-local zone rather than UTC, quietly shifting the
5.5 h bound by the caller's offset. Every test passes an aware datetime and
the internal default is aware, so this is unreachable from anything in the
diff — and Task 3/5 are the call sites that would decide it. Noted for the
integration tasks, not chargeable here.

## ⚠️ Cannot verify from diff

1. **Suite count 1653 → 1663.** I was instructed not to re-run. Judged from
   the report's evidence, which is internally consistent: the file defines
   exactly 10 `def test_` functions (counted from the committed blob), and
   the commit body independently records `1663 passed, 7 deselected (was
   1653 passed, 7 deselected)`. The arithmetic closes and the delta is
   accounted for entirely by this file.
2. **Step 2's red state** (`ModuleNotFoundError: No module named
   'herder.limits'`) is not reconstructible from the diff. It is reported,
   and it is the mechanically expected failure for a module that did not
   exist at `05d6279` — I confirmed `limits.py` is a new file (`new file
   mode`, index `0000000..393a821`), so the import could not have resolved.
3. **The 26 `DeprecationWarning`s being pre-existing.** Reported as
   `multiprocessing.popen_fork` warnings from concurrency tests untouched by
   this diff; plausible on its face (no such test appears in the diff) but
   not verified.
4. **The measured provenance of the fixture string itself** — that a live
   2026-09-04 run emitted exactly this text — is spec-asserted upstream of
   this task and outside what the diff can show.

## Blocked

Not blocked.
