VERDICT: NEEDS FIXES

### Findings

#### Critical
None.

#### Important

**I1. Some fetch failures skip the R4 thresholds and send `dead-clock` straight away.** `packages/transmitter/src/transmitter/deadclock.py:47-56` (`fetch_text`), together with `service.py:202-204` (`_step`'s generic `except Exception` → `alerts.alert(name, …)`).
- **What happens:** `fetch_text` catches only `HTTPError` and `URLError`/`OSError`. Three failures get past it:
  - `http.client.IncompleteRead` (the connection drops mid-body), raised by `resp.read()`;
  - `http.client.BadStatusLine` and `LineTooLong`;
  - `ValueError` (a malformed `site_url`).
  Any of these escapes `check()`. `Runner._step("dead-clock", …)` then alerts code `dead-clock` at once, using the step name.
- **Why it matters:**
  - One transient truncated response from the CDN pages the operator "dead-clock" immediately. That bypasses the 10-minute rule for unreachable reads and the two-stale-reads rule (R4).
  - The `unreachable` counter does not advance for that tick.
  - `_check_guard` is skipped for that tick, so `guard-stale` is neither raised nor resolved.
- **Evidence:** the scratch-copy run in Checks run below shows all three escape.
- **Fix:** in `fetch_text`, catch `(urllib.error.URLError, OSError, http.client.HTTPException, ValueError)` and return `(0, "")`. Add a test that injects a raising `urlopen`, needs no network, and asserts nothing is alerted on the first call.

**I2. A guard that hugo cannot read is never alerted: the monitor drops the error it is given.** `deadclock.py:106-108`, with `publish.py:151-153`.
- **What happens:**
  - When `state/guard.json` cannot be read, `guard_blocks_publishing` writes `error: "<exc>"` and `guard_evaluated_at: None`.
  - `_check_guard` then takes the `age_s is None` branch, and `if guard_cache.get("error") is None` makes it do nothing at all: no alert, no resolve.
  - The publish side only `log.info`s a `guard` stop (`_report_stop`, service.py ~121).
- **Why it matters:** if hugo's R2 reads keep failing (for example after rotated or expired R2 keys):
  - publishing stops (fail-closed, which is correct for spend);
  - the unexpected-403 alarm is disabled, because the cache says `blocked: true`;
  - `guard-stale` is permanently disabled, because the last known evaluation time is overwritten with `None`.

  Nothing on hugo alerts. The first signal is the cloud lead-floor alert, hours later. This is a swallowed error on the path next to spend. The brief's wording ("or a readable guard.json with none") leaves the unreadable case open, but the monitor is the backstop for exactly "the guard stopped evaluating, as far as hugo can tell".
- **Fix (either):**
  - (a) in `guard_blocks_publishing`, on a guard read error carry the previous cache's `guard_evaluated_at` forward. It is informational only, so the gate is untouched. The existing 45-min rule then fires naturally.
  - (b) in the monitor, record when `error` was first seen and alert `guard-stale` once it has persisted for `guard_stale_s`.

  Pin it with a test.

**I3. Two R4 rules have no test that would fail if they broke, and one test's name claims coverage it lacks.** `tests_transmitter/test_deadclock.py:60-68, 80-91`. Mutants run in a scratch copy, predictions named before each run:
- **M1:** removing `self.stale = 0` (deadclock.py:84), the reset that makes R4's rule "two *consecutive* stale checks". Predicted none red; **result: all 65 green.**
  - `test_a_fresh_playlist_resolves_and_one_stale_read_is_not_a_death` never makes a stale read: its middle playlist is 102.4 s old, under the 120 s threshold.
  - The intended pin, stale → fresh → stale must not alert, does not exist.
- **M3:** dropping `guard_cache.get("blocked")` from the 403-expected test (deadclock.py:73). Predicted none red; **result: all 65 green.**
  - The 403 test only exercises `offair=True`. Nothing pins that a **trip** (the spend case) makes a 403 expected.
  - If this arm broke, every trip lasting over 17 min would send a false "kill switch left on?" alarm.
- **Fix:**
  - Make the middle read of that test genuinely stale (e.g. `live_playlist(980)`, 204.8 s old), and add a stale/fresh/stale/fresh sequence asserting no alert.
  - Add a 403 run with `blocked=True, offair=False` over at least 17 checks, asserting no alert.

#### Minor

- **M-a, the upgrade false alarm (the implementer's concern, risk (d)).** `deadclock.py:105-108`. A `guard-cache.json` written by the old code has no `guard_evaluated_at` key and `error: None`. The first tick after upgrade reuses the cached file (<15 min old), so it sends a real `guard-stale` page: "is the antenna clock deployed?". A resolved page follows at the next refresh. This is deterministic, one-time and self-healing, and it will land during the operator's Task 17 checkpoint. One-line fix: treat a cache without the key as unknown, e.g. `if "guard_evaluated_at" not in guard_cache: return` before the age logic. A present-but-null value still alerts, as the brief wants.
- **M-b, checks are counted per tick, and the monitor's "now" is the tick start.** `service.py:233-235` passes `t_us`, captured before plan/render. While filling, render can take one show's encode (~10-20 min, R15). So:
  - "10 consecutive minutes" unreachable and "17 checks" for a 403 can mean hours;
  - the alert text "for N minutes" is wrong then;
  - a playlist fetched after a long render is dated against a `now` up to ~20 min in the past, which understates staleness. Detection of a dead clock is delayed to ~2-3 ticks during filling.

  It is never a false alarm, only a late one, and it follows the brief (plan-mandated wording "checks"). Cheaper and more correct: pass the wall clock at check time (`self.clock()` inside the lambda), and make the unreachable/403 thresholds elapsed time since first failure rather than counts.
- **M-c, the counters do not reset on other outcomes.** For example `stale`, then 5 network errors, then `stale` alerts as "two in a row". Likewise `unreachable` is not reset by a 403 that was not expected. Acceptable reading of "consecutive" (no good read in between), but worth a one-line comment saying it is intended.
- **M-d, the fetch timeout (risk (c)).** `urlopen(timeout=10)` limits each socket operation, not the whole fetch. DNS resolution is not covered at all. The worst case is a tick lengthened by tens of seconds. `Runner.run` subtracts elapsed time, so the cadence holds, and the 45-min watchdog is unaffected. `resp.read()` has no size cap: harmless for `live.m3u8`, but a mis-set `site_url` pointing at a large object would read all of it. Consider `resp.read(1 << 20)`.
- **M-e** `test_deadclock.py:1`: unused `import logging` (from the brief). Lint noise.
- **M-f** `cli.py:224`: no test checks that `run` passes `monitor=service.open_monitor(st)`. Only `Runner(monitor=…)` and `open_monitor` are tested separately.
- **M-g** `deadclock.py:84-86`: the `dead-clock` message always blames the clock Worker. A stale playlist can also mean the clock legitimately writes nothing, for example when a fallback loop entry is needed and none is published, or R2 is unreadable at invocation start. Consider "the antenna clock may have stopped or be writing nothing".

### ⚠️ Cannot verify from diff
- That `[antenna] site_url` on hugo is the origin that serves `live.m3u8` at its root (the deployed custom domain). It is the operator's config at Task 17.
- That a Cloudflare WAF block on the R2 custom domain answers **403**, not another code. If it answered something else, the blocked path would be counted as "unreachable" and alarm after 10 checks.
- That the edge really serves `live.m3u8` as a cache hit (measured A5, per the brief). This is not observable from code.

### Strengths
- **Risk (a): the gate is unchanged.**
  - It still returns `blocked` only: tripped, or an unreadable `guard.json` → `True`.
  - The freshness check and the backwards-clock re-read are untouched.
  - `evaluated_at` is read inside the same try as `tripped`, so a guard doc that is not a dict still fails closed.
  - The `offair.json` read sits in its own `try/except Exception`. An absent flag gives `None`, and a JSON value that is not a dict raises `AttributeError`, which is caught. A raising GET is caught too. It runs after the decision is made and never feeds `return`.
  - The new test_publish test pins both properties: mutants M5 (offair gates) and M7 (offair read unguarded) are each caught by it, as predicted.
  - Spend cost is one extra Class B GET per 15 min. No test reaches the network.
- The off-air MEDIA-SEQUENCE dating matches antenna exactly. `offairPlaylist`/`endlistOnly` emit `max(0, indexAt(scheduledTime + 75 s))` per invocation (clock.ts:299, playlist.ts:54/72), so a healthy off-air playlist reads as negative-to-small age and cannot false-alarm. The ENDLIST-only shape is covered by the same branch.
- Good design point: while blocked (403 expected), the playlist is invisible, and `guard-stale` is the right cover, because the guard runs in the same Worker as the clock.
- `iso_to_us` (Python 3.11 `fromisoformat`) parses antenna's millisecond `toISOString()` output, so `guard_evaluated_at` will not be misread.
- Python 3.11-compatible (no 3.12+ APIs). Placeholders only (`radio.example.org`); no account details.
- Moving `OFFAIR_KEY` into publish (cloudstate imports it) removes a duplicated literal without creating an import cycle.

### Checks run
- **(a) The gate:** read the `guard_blocks_publishing` hunk and `Uploader.get_json` (publish.py:126-133: it raises on non-404 errors and on corrupt JSON). Confirmed the decision variable and the cache freshness are unchanged, and the offair read cannot raise out. Mutants M5 and M7 → `test_the_guard_cache_records_evaluation_time_and_offair_but_gating_stays_on_tripped_only` red each time, as predicted.
- **(b) The thresholds:**
  - Checked `playlist_age_s` against antenna `playlist.ts` (`offairPlaylist`, `endlistOnly`, `buildPlaylist`) and `clock.ts:299`.
  - Checked that the 403 count is `ceil(guard_check_minutes)+2 = 17` (open_monitor) and that `publish_batch`/`prune` refresh the guard cache first, under the lock, every tick (publish.py:270, 382), so the cache really does catch up within `guard_check_minutes`.
  - Mutants: M1 (no stale reset) and M3 (`blocked` arm ignored) → 65/65 green, not pinned (I3). M6 (`forbidden` not reset on 200) → green (minor gap). M4 (`STALE_CHECKS=1`) → `test_two_stale_reads_in_a_row_alert` red, as predicted.
- **(c) The timeout:** read `fetch_text` and `Runner.run`/`_step`. Showed the escaping exceptions in a scratch copy, with no network and urlopen monkeypatched, run under `.venv311`:
  ```
  ESCAPES fetch_text: IncompleteRead
  ESCAPES fetch_text: BadStatusLine
  ESCAPES fetch_text: ValueError
  ```
- **(d) The upgrade:** traced the old cache shape `{"checked_at","blocked","error"}` through `_check_guard`. `at` is None and `error` is None, so it alerts. The cached path in `guard_blocks_publishing` returns early for up to `guard_check_minutes`.
- **Mutant harness:** `git archive HEAD packages/transmitter antenna/templates | tar -x` into the scratchpad, run from an empty cwd with `PYTHONPATH` into the copy (shadowing proven: `transmitter.__file__` and `tests_transmitter.__file__` both resolved inside the scratch tree), `PYTHONDONTWRITEBYTECODE=1`, `-B`, `-p no:cacheprovider`, `__pycache__` purged between mutants. Baseline: 65 passed (test_deadclock, test_publish, test_service). The live worktree was not touched, and the suite was not re-run there.
