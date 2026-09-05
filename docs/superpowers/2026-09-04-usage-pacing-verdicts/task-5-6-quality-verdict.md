# Code-quality verdict — Tasks 5 & 6 (usage-pacing phase 1)

**Verdict: Changes requested.**

Reviewed `19a4aa9..f403239` (2 commits) on branch `usage-pacing`, read-only.
No edits, no commits. Every mutation applied was restored and verified.

The **implementation is correct**. I probed every path in `sleep_until`,
`parse_duration` and `format_delta` by hand and found no shipped behaviour that
is wrong on a reachable input. The implementer followed both briefs faithfully,
the `[pacing]` TOML block matches `PacingConfig` **exactly 5 fields for 5**, and
config validation genuinely fires at load time with a legible message. There is
no speculative phase-2 work: no usage-cache reader, no EWMA, no percent
thresholds, no `llama pacing` command. YAGNI is respected.

The problem is uniformly **coverage**. 55 mutations run against the full suite;
**22 genuine survivors** (4 further survivors are provably equivalent mutants).
Most consequentially, **the entire `cli.py` half of Task 6 can be deleted and all
1694 tests still pass**. Six Important findings below, all of them "the constraint
is not pinned" rather than "the code is wrong".

---

## Findings

### Important

**I1 — The whole `cli.py` half of Task 6 is unpinned.**
`packages/llama/src/llama/cli.py:461`, `:2180-2183`
Six targeted mutations survived (M43–M48): dropping the `STATE_PAUSED` label,
dropping the hint, deleting the `resumes …` line, firing that line for every
state, and pointing the paused hint at `llama run approve`. The decisive test:
`git checkout 19a4aa9 -- packages/llama/src/llama/cli.py` and the suite reports
**1694 passed** — the file's entire contribution to this task is invisible to the
suite. Brief Step 4 shipped unverified. Needs a CliRunner test over `run list`
and `_print_attention` asserting the `paused` label, the resume hint, and that
the `resumes <iso>` suffix appears for a paused run and not for an incomplete one.

**I2 — `parse_duration`'s `$` anchor is load-bearing and pinned by nothing.**
`packages/llama/src/llama/pacing.py:12`
Dropping `$` (M17) survives the full suite. Measured behaviour with the anchor
removed: `"6h banana"` → 21600, `"5h30m!"` → 19800, `"6s30m"` (out of order) → 6.
The existing reject-list does not discriminate because the regex is entirely
optional — `""`, `"6"`, `"-2h"` and `"6x"` all fall through to the
`any(m.groups())` guard (which *is* pinned, M15) and never exercise the anchor.
So the answer to "does anything pin that these raise" is: the guard pins some of
them, the anchor pins none. `max_wait = "6h or so"` would silently become 6h.
Add a trailing-garbage case (`"6h banana"`, `"6s30m"`) to
`test_parse_duration_rejects_nonsense`. (The `^` is by contrast redundant —
`re.match` already anchors the start; M16 is an equivalent mutant.)

**I3 — `format_delta`'s one-minute floor is unpinned.**
`packages/llama/src/llama/pacing.py:31`
`max(int(seconds), 60)` → `max(int(seconds), 0)` (M8) and dropping the floor
outright (M10) both survive. The only floor-adjacent assertion is
`format_delta(90) == "1m"`, and 90 // 60 == 1 with or without the floor. Raising
the floor to 120 *is* caught (M9), so the test pins an upper bound on the floor
and not the floor itself. The docstring's stated invariant — "never bare seconds"
— has zero coverage. Add `format_delta(5) == "1m"` and `format_delta(0) == "1m"`.

**I4 — The `field_validator` names three fields; only one is pinned.**
`packages/llama/src/llama/config.py:112`
`@field_validator("max_wait", "unknown_reset_wait", "reset_skew")` reduced to
`("max_wait",)` (M31), or with `reset_skew` dropped (M33), or with
`unknown_reset_wait` dropped (M34) — all three survive. The only rejection test
is `PacingConfig(max_wait="whenever")`. So for two of the three duration fields
the class docstring's promise — "validated at load time rather than at the point
of use, so a typo fails `llama get` immediately instead of four shows in" — is
unverified, and that is precisely the promise Task 7 will rely on. Deleting the
validator body *is* caught (M30), so the gap is per-field, not wholesale.
Parametrize the rejection test over all three fields.

**I5 — `sleep_until`'s `chunk_s` default is unpinned in both directions.**
`packages/llama/src/llama/pacing.py:36`
`900 → 1` (M4) and `900 → 60000` (M5) both survive, because the one chunking test
passes `chunk_s=900` explicitly and the other test never sleeps. Neither
regression is cosmetic: at `chunk_s=1` a 6-hour wait emits **21,600** progress
lines; at `chunk_s=60000` it emits **none** — which is exactly the dead prompt the
function's docstring says it exists to prevent. Task 7 is the first caller and
will take the default. Add a test that calls `sleep_until` without `chunk_s` and
asserts the nap size or the echo count.

**I6 — `sleep_until` rejects a naive `when` with a bare `TypeError`.**
`packages/llama/src/llama/pacing.py:36-49`
Probed: `sleep_until(datetime(2026,9,4,9,0), ...)` raises
`TypeError: can't subtract offset-naive and offset-aware datetimes`. This is
undocumented, untested, and a live trap for Task 7 — which must parse
`resume_after` back out of the session marker, where it is stored as a **string**
(Task 6) and where `datetime.fromisoformat` on an offset-less instant yields a
naive value. Either coerce (`when.replace(tzinfo=timezone.utc)` when naive),
raise a legible `ValueError`, or state the aware-only contract in the docstring
and pin it.

### Minor

**m1 — Wall-clock dependence: a backward clock step never terminates.**
`pacing.py:43-45`. `_now()` is `datetime.now(timezone.utc)`, not monotonic. Probed
with a clock stepping back one hour per nap: the loop runs forever, recomputing
`remaining` from an ever-earlier wall clock. Realistic NTP corrections are seconds
and self-heal, and `KeyboardInterrupt` still lands promptly as documented, so this
is not urgent — but for a function whose whole purpose is unattended multi-hour
waits it deserves a bound (an iteration cap derived from the initial remaining, or
a `time.monotonic()` deadline alongside the wall-clock one). No test covers a
non-monotonic clock.

**m2 — `chunk_s <= 0` is unguarded.** `pacing.py:36`. Probed: `chunk_s=0` busy-spins
forever (`time.sleep(0)` never advances the clock); `chunk_s=-60` reaches
`time.sleep` with a negative and raises `ValueError`. The parameter is public.
Guard it, or document it as caller-trusted.

**m3 — The floor makes `format_delta` misleading at and below zero.**
`pacing.py:30-33`. Measured: `format_delta(0)`, `format_delta(1)` and
`format_delta(-3600)` all return `"1m"`. Unreachable from `sleep_until` (guarded
by `left > 0`), but Task 7 will render deltas from other sources; an overdue wait
reading "1m left" is a decision-boundary lie. Clamp non-positive input to `"0m"`
or reject it.

**m4 — The progress message's content is unpinned; only its count is.**
`pacing.py:47`. `echo("")` survives (M49), as does echoing the pre-nap `remaining`
instead of the post-nap `left` (M50). The cadence is well pinned (M2, M6, M7 all
killed) but a caller could render an empty line 3 times and stay green. Assert one
message's text.

**m5 — `pause_scope` is write-only.** `sessions.py:36`, `cli.py:2186`. It is
persisted to `session.json` but exposed by nothing: not a `SessionInfo` field, not
in `_session_json`. Blanking it in `_write` survives (M39) while the sibling
`resume_after`/`pause_reason` blanks are both killed (M37, M38). Either surface it
alongside the other two or drop it until Task 7 needs it.

**m6 — `run list --json` lost what the human table gained.** `cli.py:2186`.
`_session_json` omits `resume_after` and `pause_reason`, so the machine-readable
path — arguably where a resume instant matters most — does not carry it while the
text path does. The brief only asked for `_print_sessions`, so this is a gap the
brief left rather than one the implementer opened, but it ships an asymmetry.

**m7 — The `[pacing]` TOML comments describe behaviour that does not exist yet.**
`config.py:235-255`. Verified: nothing consumes `config.pacing`, and no
`--max-wait` flag exists anywhere in `src/`. Yet `llama config init` writes, today,
"wait it out instead of failing every remaining show", "Set enabled = false to
restore the old behaviour", "checkpoint the session and exit 0", and
"(e.g. `--max-wait 30h`)". At this commit every one of those is false and the
flag is unrecognised. Task 7 makes them true on the same branch, so this is
transient — **but if these two commits could ever ship without Task 7, promote
this to Important.** Worth a one-line note in the Task 7 brief that the comments
become true only when it lands.

**m8 — Doc drift.** `sessions.py:100` — `SessionInfo.state`'s inline comment still
reads `STATE_AWAITING | STATE_COMPLETE | STATE_INCOMPLETE`, missing `STATE_PAUSED`.

**m9 — The template-parity test cannot catch an omitted key.** `test_config.py:177`.
Deleting `reset_skew` from the TOML block (M51) — or renaming the whole `[pacing]`
header so the block never parses (M52) — leaves the suite green, because a missing
key falls back to the same default the test compares against. Value drift *is*
caught (M25–M29 all killed). This is a **pre-existing** weakness affecting every
block, not something this task introduced, but it is cheap to close: assert
`set(tomllib.loads(DEFAULT_CONFIG_TOML)[section]) == set(Model.model_fields)` per
section. (I ran that check by hand for `[pacing]`: **exact parity, 5 for 5**.)

**m10 — `pytest.raises(Exception)` is over-broad.** `test_pacing.py:55`. It would
pass on a `TypeError`, or on an `ImportError` raised by the validator's deferred
`from llama.pacing import parse_duration`. Narrow to `pydantic.ValidationError`.

**m11 — Small style/typing nits.** `pacing.py:20` `parse_duration` is annotated
`-> float` but returns `int`. `pacing.py:21` the `(text or "")` defensive branch is
unreachable from the annotated `text: str` signature and is unpinned (M24); so is
`.strip()` (M23) — no test passes `" 6h "`. `pacing.py:12` `^` is redundant under
`re.match`. `pacing.py:16` `# noqa: E302` cites a linter the project does not
configure or run (no ruff/flake8 config, no ruff installed).

---

## What I checked and found **good**

- **Config validation timing and legibility.** Verified end-to-end against real
  TOML files: `max_wait = "whenever"` and `reset_skew = "2 minutes"` both raise
  `ConfigError: invalid config at <path>: 1 validation error for Config /
  pacing.max_wait / Value error, not a duration: 'whenever' (use forms like 6h,
  90m, 5h30m)`. Fails early, names the field, names the accepted forms. A natural
  TOML mistake (`max_wait = 6`, an int) is also caught. This is the right design.
- **`[pacing]` matches `PacingConfig` field for field** — 5 keys, 5 fields, no
  extras, no omissions, and all five default values are pinned by
  `test_default_config_template_matches_defaults` (M25–M29 all killed).
- **`sleep_until` terminates** for `when` in the past, `when` exactly now, and any
  sub-chunk wait. The `remaining <= 0` guard is genuinely load-bearing: weakening
  it to `< 0` (M3) sends the suite into an **infinite busy-spin** at
  `remaining == 0`. Detected — though as a hang rather than a failure, which is
  worth knowing if that guard is ever touched again.
- **The wholesale-rewrite discipline in `_write` is properly pinned.** My first
  attempt (M35) was an equivalent mutant — the dict literal's explicit `None`
  overrode the merged value. Re-run with realistic merge semantics ("preserve
  fields the caller did not pass"), both the pause block (M35b) and `failures`
  (M35c) are **killed** by `test_completing_a_paused_run_erases_the_pause_block`.
  The comment's claim that `mark_complete` erases the pause block for free is
  true and defended.
- **`_state_of`'s widened whitelist is pinned** (M36 killed) — removing
  `STATE_PAUSED` does not silently degrade to `incomplete`; the round-trip test
  catches it. `mark_paused` writing the wrong state is caught (M42).
- **No state consumer mishandles `paused`.** Audited every `STATE_*` /
  `session_state()` reference outside `sessions.py`: `run rm` echoes the state
  (now correctly "paused"), `run resume` does not gate on state, and both
  attention dicts are read via `.get(..., default)`, so the additions are purely
  additive. The `_ATTENTION_LABELS`/`_ATTENTION_HINTS` entries the implementer
  added beyond the brief are correctly shaped.
- **Test hygiene is clean on the forbidden axes.** No test sleeps for real, reads
  a real clock, or touches a real `$HOME`; `_now`/`_sleep` are monkeypatched in
  both sleep tests and auto-restored. No test is vacuous —
  `test_sleep_until_returns_at_once_when_the_time_has_passed` asserts through a
  `pytest.fail` stub, which is legitimate.
- **YAGNI respected.** Nothing consumes `config.pacing` or `pacing.*` outside the
  validator and the tests, which is correct for phase 1; the Task 7 `_execute`
  integration is absent as intended. No phase-2 machinery anywhere.

---

## Mutation kill table

Method: one mutation at a time, **full suite** (`./.venv/bin/python -m pytest -q
-p no:randomly`, 1694 tests, ~7 s) run against each, `__pycache__` cleared before
and after every run **and** `PYTHONDONTWRITEBYTECODE=1` set, then `git checkout`
restore verified. A hang-detecting 90 s subprocess timeout wraps each run. The
harness was smoke-tested against a known-fatal mutation before use.

Baseline: **1694 passed, 7 deselected**.

### `pacing.py` — `sleep_until`

| # | Mutation | Result |
|---|---|---|
| M1 | `_sleep(min(remaining, chunk_s))` → `_sleep(remaining)` | KILLED |
| M2 | `if left > 0:` → unconditional echo | KILLED |
| M3 | `if remaining <= 0:` → `< 0` | **HANG** (infinite spin; detected only as a hang) |
| M4 | `chunk_s: float = 900` → `1` | **SURVIVED** |
| M5 | `chunk_s: float = 900` → `60000` | **SURVIVED** |
| M6 | `if left > 0:` → `if left >= 0:` | KILLED |
| M7 | `min(remaining, chunk_s)` → `max(...)` | KILLED |
| M49 | `echo(f"… {format_delta(left)} left")` → `echo("")` | **SURVIVED** |
| M50 | echo `remaining` instead of `left` | **SURVIVED** |

### `pacing.py` — `format_delta`

| # | Mutation | Result |
|---|---|---|
| M8 | `max(int(seconds), 60)` → `max(int(seconds), 0)` | **SURVIVED** |
| M9 | floor `60` → `120` | KILLED |
| M10 | drop the floor: `total = int(seconds)` | **SURVIVED** |
| M11 | `total // 60` → `int(total / 60)` | SURVIVED *(equivalent mutant)* |
| M12 | `divmod(total // 60, 60)` → `divmod(total // 60, 24)` | KILLED |
| M13 | `hours, minutes = divmod(...)` → swapped | KILLED |
| M14 | always render the `Xh Ym` branch | KILLED |

### `pacing.py` — `parse_duration`

| # | Mutation | Result |
|---|---|---|
| M15 | drop `not any(m.groups())` from the guard | KILLED |
| M16 | drop the `^` anchor | SURVIVED *(equivalent — `re.match` anchors)* |
| M17 | drop the `$` anchor | **SURVIVED** |
| M18 | `\d+` → `\d*` in all three groups | SURVIVED *(equivalent, verified by table)* |
| M19 | allow a leading `-` sign | KILLED |
| M20 | `minutes * 60` → `minutes * 30` | KILLED |
| M21 | `hours * 3600` → `hours * 60` | KILLED |
| M22 | drop the `+ seconds` term | KILLED |
| M23 | drop `.strip()` | **SURVIVED** |
| M24 | `(text or "")` → `text` | **SURVIVED** |

### `config.py` — `PacingConfig` and the TOML block

| # | Mutation | Result |
|---|---|---|
| M25 | `enabled: bool = True` → `False` | KILLED |
| M26 | `wait: bool = True` → `False` | KILLED |
| M27 | `max_wait = "6h"` → `"9h"` | KILLED |
| M28 | `unknown_reset_wait = "1h"` → `"3h"` | KILLED |
| M29 | `reset_skew = "2m"` → `"9m"` | KILLED |
| M30 | delete the validator body (keep `return v`) | KILLED |
| M31 | validator field list → `("max_wait",)` only | **SURVIVED** |
| M32 | validator field list → `("reset_skew",)` only | KILLED |
| M33 | validator drops `reset_skew` | **SURVIVED** |
| M34 | validator drops `unknown_reset_wait` | **SURVIVED** |
| M51 | TOML block omits `reset_skew = "2m"` | **SURVIVED** |
| M52 | TOML omits the entire `[pacing]` block | **SURVIVED** |

### `sessions.py`

| # | Mutation | Result |
|---|---|---|
| M35 | `_write` merges previous marker (literal wins) | SURVIVED *(equivalent mutant)* |
| M35b | `_write` preserves previous pause block when args are `None` | KILLED |
| M35c | `_write` preserves previous `failures` | KILLED |
| M36 | `_state_of` whitelist drops `STATE_PAUSED` | KILLED |
| M37 | `"resume_after": resume_after` → `None` | KILLED |
| M38 | `"pause_reason": reason` → `None` | KILLED |
| M39 | `"pause_scope": scope` → `None` | **SURVIVED** |
| M40 | `iter_sessions` passes `resume_after=None` | KILLED |
| M41 | `iter_sessions` passes `pause_reason=None` | KILLED |
| M42 | `mark_paused` writes `STATE_INCOMPLETE` | KILLED |

### `cli.py`

| # | Mutation | Result |
|---|---|---|
| M43 | drop `STATE_PAUSED` from `_ATTENTION_LABELS` | **SURVIVED** |
| M44 | drop `STATE_PAUSED` from `_ATTENTION_HINTS` | **SURVIVED** |
| M45 | delete the `resumes {resume_after}` line | **SURVIVED** |
| M46 | render that line for every state, not just paused | **SURVIVED** |
| M47 | paused hint → `llama run approve {id}` | **SURVIVED** |
| M48 | paused label → `"zzz"` | **SURVIVED** |
| M53 | **revert `cli.py` wholesale to `19a4aa9`** | **SURVIVED — 1694 passed** |

**Totals: 55 mutations — 28 KILLED, 1 HANG, 26 SURVIVED, of which 4 are provably
equivalent ⇒ 22 genuine survivors.**

### Unpinned constraints, stated plainly

1. Every line of the `cli.py` change (label, hint, `resumes` suffix, and its
   state condition) — the file can be reverted entirely with a green suite.
2. `parse_duration`'s `$` anchor — trailing garbage and out-of-order units.
3. `format_delta`'s 60-second floor (only an upper bound on it is pinned).
4. The `field_validator`'s coverage of `unknown_reset_wait` and `reset_skew`.
5. `sleep_until`'s `chunk_s` default of 900, in both directions.
6. The progress message's text (only the echo *count* is pinned).
7. `pause_scope`'s persistence.
8. `parse_duration`'s `.strip()` and its `text or ""` `None`-guard.
9. The presence of any given key — or of the whole block — in
   `DEFAULT_CONFIG_TOML` (pre-existing test weakness, all sections).

---

## Recommended before merge

Blocking (I1–I6): a CliRunner test for the `run list` paused rendering; a
trailing-garbage reject case; two `format_delta` floor assertions; parametrize
the validator-rejection test over all three duration fields; one `sleep_until`
call that takes the default `chunk_s`; and a decision on the naive-`datetime`
contract (coerce, raise legibly, or document + pin) before Task 7 consumes it.

Non-blocking: m1–m11, of which m7 (TOML comments describing not-yet-existing
behaviour) should at minimum be noted in the Task 7 brief so it is closed there.

## Process

- No subagents dispatched. Not blocked at any point.
- `git status --porcelain` is **clean** (empty) at the time of writing; HEAD is
  `f403239`; `git diff HEAD` over all six touched files is empty; full suite
  re-run after the last restore: **1694 passed, 7 deselected**.
