# Alert noise, the hugo ntfy relay, and two hugo service fixes: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate every-minute alerts at 3 consecutive failing observations on both sides, relay antenna's alerts to ntfy through hugo, move hugo's dead-clock check onto its own thread with a fresh guard view, and feed the watchdog during long plan steps.

**Architecture:** antenna (TypeScript Worker) gains a streak per gated key in `state/alerts.json` and one bounded relay write per sending invocation to `state/alert-relay.json`; its ntfy channel is removed. transmitter (Python 3.11) gains a streak per gated code in the `Dispatcher`, driven by explicit per-observer observations, a daemon monitor thread (dead-clock check + relay reader) that only reads R2, and a watchdog ping per show analysis.

**Tech Stack:** TypeScript on Cloudflare Workers (vitest via `@cloudflare/vitest-plugin`, R2 binding); Python 3.11 (pytest, boto3, urllib, threading).

**Spec:** `docs/superpowers/specs/2026-10-24-alert-noise-and-hugo-fixes-design.md` (authoritative; read it in full before any task, including the operator ruling at its end).

## Global Constraints

- Review mode: **Opus** (spec, plan and final branch reviewers). Implementers per task as the orchestrator announces.
- **Strict surfaces** (each has a test in the task that owns it, named in that task):
  - `tripped-spend`, `tripped-blind`, the `budget-50/80:*` levels, `guard-state-corrupt`, `offair-corrupt` (antenna) and `put-budget` (transmitter) are never gated or delayed (Task 1 test K, Task 3 `test_each_ungated_code_sends_on_its_first_fire`).
  - No gate may silence a one-shot key forever: `waf-corrected`, `budget-*`, `budget-file-invalid`, `horizon-refused`, `frame-count-drift` are ungated; the two immediate raise sites bypass the gate (Task 1 tests B, J, O, P).
  - The relay never delays an email: email is sent first, the relay write is bounded by 10 s (Task 2 `relay: a hung write ...`).
  - The monitor thread never writes to R2, never touches `guard_cache_path`, never calls notify (Task 4 `test_the_monitor_only_reads_r2_never_touches_the_guard_cache_and_never_notifies`).
  - Publish's guard cache keeps a single writer, `publish.guard_blocks_publishing` (Task 4 `test_guard_blocks_publishing_is_the_only_cache_writer`).
  - The watchdog keeps meaning "the main loop is alive": only the main thread pings it (Task 4, same test; Task 6).
- `GATE = 3` is a named constant on each side, not config. The gated lists are exactly the spec's Part 1 tables:
  - antenna `GATED_KEYS`: `waf-api`, `guard-unknown`, `guard-write`, `budget-unreadable`, `index-write`, `clock-inputs`, `clock-failed`, `guard-crashed`, `horizon-missing`, `metronome-down`.
  - transmitter `GATED_CODES`: `prune`, `publish`, `publish-state`, `station-root`, `plan`, `render`, `dead-clock-check`.
- Unchanged (do not touch): `dead-clock`'s 2/10/17 debounces, `guard-stale` 45 min, `guard-reading-failing` 1 h, `horizon-held` 3, `lead-low`, `COOLDOWN_MS` (15 min), alert titles, priorities, `repeat_hours`/`ALERT_REPEAT_HOURS`, `CHANNEL_COOLDOWN_S`. Never stack the gate on an already-debounced key.
- Exact constants: relay key `state/alert-relay.json`; ring of **50**; relay write timeout **10 s** (`10_000` ms); `RELAY_MAX_AGE` **1 h**; relay pass budget **30 s**; monitor interval **60 s**; `monitor-stalled` threshold **5 min** (300 s); monitor reader timeouts **connect 5 s, read 10 s**.
- transmitter stays **Python 3.11-compatible** (no PEP 695 generics, no `typing.override`, no 3.12 f-string quote reuse, no `itertools.batched`). Final gate: `packages/transmitter/scripts/test-in-debian12.sh`.
- transmitter never imports llama or emcee (`test_no_llama_or_emcee_imports.py`).
- `wrangler.jsonc` carries no account id, zone id or address (`test/wrangler-config.test.ts`).
- Every task leaves BOTH suites green:
  - antenna: `cd antenna && npm test && npx tsc --noEmit`
  - transmitter: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` (from the worktree root; never a bare `pytest`, never a `.venv/bin/*` console script, per CLAUDE.md).
- One commit per task, ending with the attribution lines the orchestrating session specifies. Never `git stash`. Never write a file named `REPORT*`/`SUMMARY*`/`FINDINGS*`/`ANALYSIS*`.
- Tasks 1-2 (antenna) and 3-6 (transmitter) touch disjoint packages; within each package keep the order. Task 7 (docs) is last.

## Review Focus

1. **antenna deploy over an `alerts.json` written by the old Worker** (entries with no `streak`, an active gated episode mid-flight). Expected: a missing streak reads as 0; the episode continues active (no new alert, no "resolved"); its next due repeat waits for 3 consecutive presences. Test: Task 1 `M. an entry from before the gate continues; its due repeat waits for GATE presences`.
2. **A gated antenna key's first alert whose email AND relay write both fail.** Expected: the entry stays undelivered and the next minute retries it at once (its streak is already at `GATE`), never re-gated for 3 more minutes. Test: Task 2 `a gated alert whose email and relay both failed is retried the next minute, not re-gated`.
3. **The relay object recreated with a new stream while hugo's cursor sits at a high seq** (corrupt overwrite or a hand delete). Expected: hugo restarts at seq 0 in the new stream and sends the new stream's messages younger than 1 h. Test: Task 5 `test_a_stream_change_restarts_at_seq_0_in_the_new_stream`.
4. **Clock skew between antenna and hugo, and a garbled `at`.** Expected: an `at` in the future is younger than `RELAY_MAX_AGE` and is sent; an unparseable `at` is skipped with one WARNING and the cursor advances past it (no wedge). Test: Task 5 `test_an_at_in_the_future_is_sent_and_an_unparseable_at_is_skipped_and_advanced`.
5. **A transmitter restart mid-episode** (an active gated code on disk, in-process streaks gone). Expected: after the restart a fire inside the still-active episode sends nothing until 3 consecutive observations rebuild the streak; the entry stays active; a level code still resolves aloud. Test: Task 3 `test_after_a_restart_an_active_episode_continues_without_a_send_until_the_streak_rebuilds`.

## Ambiguities resolved by this plan

- **Pending over a still-active entry** (antenna): "the old entry stays exactly as it is" means unchanged except its `streak` field; it finishes clearing (and sends "resolved") through the normal absent-key path on a later allowed batch, or is replaced by the new episode on the 3rd presence.
- **Stall-branch detection** (antenna): `metronome-core.ts` gains `fallbackCause()` returning `{ reason, stall }`; `fallbackReason()` stays as a wrapper so its tests are unchanged.
- **Repeated fires of a gated code within one observation** (transmitter): only the first fire reaches the Dispatcher's state; later ones are logged at ERROR (by `alerts.alert`) and otherwise ignored (no `count`/`last_fired_at` change).
- **A step skipped by `PublishLocked`** did not observe anything: it is not reported as "ran" (neither advances nor resets).
- **Relay document shape**: `{ "stream": string, "ring": RelayMessage[] }`, seq starting at 1 in a new stream. hugo treats the document as malformed exactly when antenna would (no string `stream`, `ring` not a list, any entry without an integer `seq`); an entry with other bad fields (unparseable `at`, non-string text) is skipped with a WARNING and the cursor advances past it.
- **Delivered with no sink at all** (antenna, tests only): unchanged (the log line is all there is). With a relay present, delivered = email accepted OR relay write succeeded.
- **ntfy 3xx** (NtfyChannel raises a plain `OSError`) counts as a transport error for the relay: the pass stops and retries next pass.
- **`monitor-stalled`** is added to `LEVEL_CODES` (it resolves when passes are fresh again).
- **Notify wiring** (Part 4): `Runner.__init__` sets `st.notify` when unset; `open_station` is unchanged (every other CLI command runs outside systemd, where notify is a no-op).
- **`--once`**: a new `Runner.run_once()` runs one tick then one monitor pass with `relay=False` on the main thread; it uses the same get-only reader (built on the main thread).
- **DeadClockMonitor.check order**: `check(now_us, guard_view)` takes a zero-argument callable, called only after the playlist fetch; existing tests wrap their dict in a lambda.
- **The monitor's reader** lives in a new `monitor.py` (not `r2.py`, which must not import `publish`); `r2.make_client` gains timeout keywords.

---

### Preamble: worktree setup (orchestrator, once; not a task)

- [ ] From `/Users/shawn/projects/llama/.claude/worktrees/alert-noise`:

```bash
python3 -m venv .venv && ./.venv/bin/python -m pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"
./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"   # must resolve inside this worktree
(cd antenna && npm ci)
```

- [ ] Record baselines: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` (pass count) and `cd antenna && npm test` (pass count) and `npx tsc --noEmit` (clean). Each task's report states the new counts.

---

### Task 1: antenna 3-consecutive gate

**Files:**
- Modify: `antenna/src/conditions.ts` (`AlertCondition.immediate`)
- Modify: `antenna/src/alerts.ts` (`GATE`, `GATED_KEYS`, `AlertEntry.streak`/`pending`, `planAlerts`, header comment)
- Modify: `antenna/src/metronome-core.ts` (`fallbackCause`)
- Modify: `antenna/src/clock.ts` (`renew` uses `fallbackCause`; the stall site sets the flag)
- Modify: `antenna/src/guard.ts` (the post-unblock race branch sets the flag)
- Test: `antenna/test/alerts.test.ts`, `antenna/test/metronome-core.test.ts`, `antenna/test/clock-metronome.test.ts`, `antenna/test/guard.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces (Task 2 relies on these):
  - `conditions.ts`: `AlertCondition.immediate?: boolean`. Doc comment: bypasses the 3-consecutive gate; set at exactly two raise sites (name them in prose; the doc comment must NOT contain the literal text `immediate: true`, which test B counts).
  - `alerts.ts`: `export const GATE = 3;` `export const GATED_KEYS: ReadonlySet<string>` (the 10 keys in Global Constraints). `AlertEntry` gains `streak?: number` (gated keys only; consecutive presences, capped at `GATE`; missing = 0) and `pending?: boolean` (true only on a pending-only entry: a gated key with no stored history whose streak is below `GATE`; `active: false`, never sent).
  - `planAlerts(prev, conditions, nowMs, repeatMs, batch)`: signature unchanged.
  - `metronome-core.ts`: `export function fallbackCause(sent: Lease | null, r: { status: MetronomeStatus } | { error: string }): { reason: string; stall: boolean } | null`; `fallbackReason(sent, r)` returns `fallbackCause(sent, r)?.reason ?? null`.

- [ ] **Step 1: Write the failing tests in `antenna/test/alerts.test.ts`** (new `describe("the 3-consecutive gate", ...)`; `const at = (n: number) => T0 + n * 60_000;`; `cond(key)` as in the file; `imm = (key) => ({ ...cond(key), immediate: true })`; `const DONE: AlertBatch = { complete: true, guardComplete: true }`; `const NONE: AlertBatch = { complete: false, guardComplete: false }`):

```ts
it("A. GATED_KEYS is exactly the approved list", () => {
  expect(GATE).toBe(3);
  expect([...GATED_KEYS].sort()).toEqual(["budget-unreadable", "clock-failed", "clock-inputs", "guard-crashed",
    "guard-unknown", "guard-write", "horizon-missing", "index-write", "metronome-down", "waf-api"]);
});

it("C. a gated key sends only on its 3rd consecutive presence; the first message says so", () => {
  let r = planAlerts({}, [cond("waf-api")], at(0), REPEAT);
  expect(r.send).toEqual([]);
  expect(r.next["waf-api"]).toMatchObject({ active: false, pending: true, streak: 1 });
  r = planAlerts(r.next, [cond("waf-api")], at(1), REPEAT);
  expect(r.send).toEqual([]);
  expect(r.next["waf-api"]).toMatchObject({ active: false, pending: true, streak: 2 });
  r = planAlerts(r.next, [cond("waf-api")], at(2), REPEAT);
  expect(r.send.map((o) => o.kind)).toEqual(["alert"]);
  expect(r.send[0].message).toMatch(/3 consecutive/);
  expect(r.next["waf-api"]).toMatchObject({ active: true, streak: 3 });
  expect(r.next["waf-api"].pending).toBeUndefined();
});

it("D. an absence on a batch that could clear it drops a pending-only entry", () => {
  let s = planAlerts({}, [cond("waf-api")], at(0), REPEAT).next;
  s = planAlerts(s, [], at(1), REPEAT, DONE).next;
  expect(s).not.toHaveProperty("waf-api");
  expect(planAlerts(s, [cond("waf-api")], at(2), REPEAT).next["waf-api"].streak).toBe(1);
});

it("E. an incomplete batch over a pending entry leaves it unchanged; guardComplete resets a guard-family one", () => {
  const s = planAlerts({}, [cond("clock-inputs"), cond("guard-write")], at(0), REPEAT).next;
  const r = planAlerts(s, [], at(1), REPEAT, NONE);
  expect(r.next).toEqual(s);
  const g = planAlerts(s, [], at(1), REPEAT, { complete: false, guardComplete: true });
  expect(g.next["clock-inputs"]).toEqual(s["clock-inputs"]);
  expect(g.next).not.toHaveProperty("guard-write");
  // the incomplete minute neither advanced nor reset: two more presences reach GATE
  let t = planAlerts(r.next, [cond("clock-inputs")], at(2), REPEAT).next;
  expect(planAlerts(t, [cond("clock-inputs")], at(3), REPEAT).send.map((o) => o.kind)).toEqual(["alert"]);
});

it("G. pending over a kept inactive entry keeps its history; a reset keeps it as before", () => {
  const old = { active: false, resolvable: true, title: "t", first_at: iso(T0 - H), last_sent_at: iso(T0 - H),
                delivered: true, cleared_at: iso(T0 - 30 * 60_000) };
  const r = planAlerts({ "waf-api": old }, [cond("waf-api")], at(0), REPEAT);
  expect(r.send).toEqual([]);
  expect(r.next["waf-api"]).toEqual({ ...old, streak: 1 });
  expect(planAlerts(r.next, [], at(1), REPEAT, DONE).next["waf-api"]).toEqual(old);
});

it("H. pending over a still-active entry whose clearing elapsed: it stays, may resolve, or is replaced at GATE", () => {
  const live = { active: true, resolvable: true, title: "t", first_at: iso(T0 - H), last_sent_at: iso(T0 - H),
                 delivered: true, cleared_at: null, clearing_since: iso(T0 - COOLDOWN_MS - 60_000), streak: 3 };
  const r = planAlerts({ "waf-api": live }, [cond("waf-api")], at(0), REPEAT);
  expect(r.send).toEqual([]);
  expect(r.next["waf-api"]).toEqual({ ...live, streak: 1 });
  const gone = planAlerts(r.next, [], at(1), REPEAT, DONE);
  expect(gone.send.map((o) => [o.kind, o.key])).toEqual([["resolved", "waf-api"]]);
  let s = planAlerts(r.next, [cond("waf-api")], at(1), REPEAT).next;
  const back = planAlerts(s, [cond("waf-api")], at(2), REPEAT);
  expect(back.send.map((o) => o.kind)).toEqual(["alert"]);
  expect(back.next["waf-api"].first_at).toBe(iso(at(2)));
});

it("I. a single blip inside an active episode never sends a repeat", () => {
  let s = [0, 1, 2].reduce((st, n) => planAlerts(st, [cond("waf-api")], at(n), REPEAT).next, {} as AlertState);
  s = planAlerts(s, [], at(2) + REPEAT, REPEAT, DONE).next;          // a clean minute: streak reset, clearing starts
  let r = planAlerts(s, [cond("waf-api")], at(3) + REPEAT, REPEAT);    // back inside the window, repeat due
  expect(r.send).toEqual([]);
  expect(r.next["waf-api"].active).toBe(true);
  r = planAlerts(r.next, [cond("waf-api")], at(4) + REPEAT, REPEAT);
  r = planAlerts(r.next, [cond("waf-api")], at(5) + REPEAT, REPEAT);
  expect(r.send.map((o) => o.kind)).toEqual(["repeat"]);
});

it("J. an immediate condition sends at once, advances the streak, and its repeat is not gated", () => {
  let r = planAlerts({}, [imm("metronome-down")], at(0), REPEAT);
  expect(r.send.map((o) => o.kind)).toEqual(["alert"]);
  expect(r.send[0].message).not.toMatch(/consecutive/);
  expect(r.next["metronome-down"]).toMatchObject({ active: true, streak: 1 });
  r = planAlerts(r.next, [imm("metronome-down")], at(0) + REPEAT, REPEAT);   // streak 2 < GATE, repeat due
  expect(r.send.map((o) => o.kind)).toEqual(["repeat"]);
});

it("K. ungated keys send at their first presence and store no streak (strict surfaces)", () => {
  for (const c of [cond("tripped-spend"), cond("tripped-blind"), cond("guard-state-corrupt"), cond("offair-corrupt"),
                   cond("horizon-refused"), cond("lead-low"), cond("guard-reading-failing"),
                   cond("offair-without-fallback"), cond("waf-corrected", false),
                   { ...cond("budget-file-invalid", false), once: true },
                   { ...cond("budget-50:2026-10-11:15", false), once: true },
                   { ...cond("budget-80:2026-10-11:15", false), once: true }]) {
    const r = planAlerts({}, [c], T0, REPEAT);
    expect([c.key, r.send.map((o) => o.kind)]).toEqual([c.key, ["alert"]]);
    expect([c.key, "streak" in r.next[c.key]]).toEqual([c.key, false]);
  }
});

it("L. the stored streak stops at GATE: a steady active episode writes alerts.json no more", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const bucket = new MemoryBucket();
  for (let n = 0; n < 6; n++) await dispatchAlerts(bucket, [], [cond("waf-api")], at(n), REPEAT);
  expect(bucket.puts(ALERTS_KEY)).toBe(3);
});

it("M. an entry from before the gate continues; its due repeat waits for GATE presences", () => {
  const legacy = { active: true, resolvable: true, title: "t", first_at: iso(T0 - REPEAT), last_sent_at: iso(T0 - REPEAT),
                   delivered: true, cleared_at: null };                 // written by the old Worker: no streak
  let r = planAlerts({ "waf-api": legacy }, [cond("waf-api")], at(0), REPEAT);
  expect(r.send).toEqual([]);
  expect(r.next["waf-api"]).toMatchObject({ active: true, first_at: legacy.first_at, streak: 1 });
  r = planAlerts(r.next, [cond("waf-api")], at(1), REPEAT);
  r = planAlerts(r.next, [cond("waf-api")], at(2), REPEAT);
  expect(r.send.map((o) => o.kind)).toEqual(["repeat"]);
});
```

(`iso = (ms: number) => new Date(ms).toISOString()`.)

Extend the existing `classifies every key the guard and the clock raise` test (B):

```ts
// B. only two raise sites bypass the gate
const sources = import.meta.glob("../src/*.ts", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const sites = Object.entries(sources).flatMap(([f, s]) => (s.match(/immediate:\s*true/g) ?? []).map(() => f));
expect(sites.sort()).toEqual(["../src/clock.ts", "../src/guard.ts"]);
for (const k of GATED_KEYS) expect(CLOCK_KEYS.has(k) || keyFamily(k) === "guard").toBe(true);
```

(If `import.meta.glob` does not load under the workers pool, import each `src/*.ts` file with `?raw` explicitly, as `wrangler-config.test.ts` does for `wrangler.jsonc`, and say so in the task report.)

- [ ] **Step 2: Write the failing tests for the two raise sites.**
  - `antenna/test/metronome-core.test.ts`, `N. fallbackCause marks only the stall branch`: `fallbackCause(p, { error: "x" })` → `{ stall: false }` with the same reason as `fallbackReason`; `status({ wrote: false })` → `stall: false`; `status({ stalls: 2, stalledMs: 70_000 })` → `stall: true`; `status({ stalls: 1 })` → `null`; for every input in the file's existing `fallbackReason` cases, `fallbackCause(...)?.reason ?? null` equals `fallbackReason(...)`.
  - `antenna/test/clock-metronome.test.ts`, `O. only the stall trigger raises metronome-down immediate`: add `conds: AlertCondition[]` to `Run` (the sink records `cs`); over the existing `triggers` table, `out.conds.find((c) => c.key === "metronome-down")!.immediate` is `true` for `"(c) stalls >= 2"` and `undefined` for the other four.
  - `antenna/test/guard.test.ts`, `P. the post-unblock re-check that cannot read state raises guard-unknown immediate; the read branch does not`: set up as `a non-evaluating run that turns the kill switch off folds in a racer's newer trip` (first `step` at T0, then `c.state.enabled = true`), but override `bucket.head` to throw for `GUARD_KEY`; `out.blocked` is `true`; the `guard-unknown` condition has `immediate: true`. In `when state cannot be read the outcome is unknown`, add `expect(out.conditions[0].immediate).toBeUndefined()`.

- [ ] **Step 3: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/alerts.test.ts test/metronome-core.test.ts test/clock-metronome.test.ts test/guard.test.ts`
Expected: FAIL (`GATE`/`GATED_KEYS`/`fallbackCause` not exported; sends on first presence; `immediate` undefined).

- [ ] **Step 4: Implement `fallbackCause` in `metronome-core.ts`** with the same three branches in the same order as today's `fallbackReason` (the stall branch is the third, `stall: true`); make `fallbackReason` the wrapper.

- [ ] **Step 5: Set the flag at the two sites.** `clock.ts` `renew`: `const cause = fallbackCause(lease, r)`; `fallback = cause?.reason ?? null` (the clock line is unchanged); the pushed `metronome-down` condition spreads `...(cause.stall ? { immediate: true } : {})`. `guard.ts`: the `catch` of the post-unblock re-check adds `immediate: true` to its `guard-unknown` condition. No other file may contain `immediate: true`.

- [ ] **Step 6: Implement the gate in `planAlerts` (`alerts.ts`).** Not determined by the signature, so the algorithm is fixed here:

```
gated(c) = GATED_KEYS.has(c.key) && !c.once
present loop, per condition c (first occurrence only, as today):
  if gated(c): streak = min(GATE, (e?.streak ?? 0) + 1); held = !c.immediate && streak < GATE
  else:        streak = undefined; held = false            // ungated: never write a streak
  if c.once: unchanged
  else if (new-episode test as today):
    if held:   next = !e ? { active:false, pending:true, resolvable, title, first_at: now, last_sent_at:null,
                             cleared_at:null, streak }
                    : { ...e, streak }                      // pending-only, kept history, or still-active: unchanged but streak
               (no send)
    else:      next = fresh active entry as today (no `pending`), plus streak when gated; send "alert";
               message = gated(c) && !c.immediate ? `${c.message} (Alerted after ${GATE} consecutive failing minutes.)`
                                                  : c.message
  else if repeat due && !held: repeat as today (+ streak)
  else: continuing as today (+ streak)                     // a held due repeat lands here: no send
absent loop, per prev entry not seen (BEFORE the `!e.active -> keep` branch):
  if e.pending: next = clearedIn(key, batch) ? (dropped) : e; continue
  base = clearedIn(key, batch) ? e without `streak` : e      // rule 2 reset; rule 3 unchanged
  then today's branches, operating on `base`
```

Update the file's header comment with one paragraph on the gate (gated list, pending entries, immediate sites, rule 4 on repeats).

- [ ] **Step 7: Adapt existing tests that relied on a gated key sending at first presence.** Where the test is not about the gate, substitute an ungated key of the same family (guard family: `offair-corrupt`; clock family: `lead-low`) so its intent is unchanged; the redaction test `a WafError carrying the zone, ruleset and rule ids ...` instead dispatches its `waf-api` condition three times one minute apart and checks the third invocation's messages (redaction on the gated path). Do not weaken any assertion.

- [ ] **Step 8: Run the antenna suite and typecheck**

Run: `cd antenna && npm test && npx tsc --noEmit`
Expected: all pass; tsc clean. Transmitter suite unchanged (no Python touched).

- [ ] **Step 9: Commit**

```bash
git add antenna/src/alerts.ts antenna/src/conditions.ts antenna/src/metronome-core.ts antenna/src/clock.ts antenna/src/guard.ts antenna/test/alerts.test.ts antenna/test/metronome-core.test.ts antenna/test/clock-metronome.test.ts antenna/test/guard.test.ts
git commit -m "antenna: gate every-minute alerts at 3 consecutive failing invocations"
```

---

### Task 2: antenna relay (ntfy removed)

**Files:**
- Modify: `antenna/src/alerts.ts` (remove `ntfyChannel`, `refusal`, `NTFY_*`; add the relay; `dispatchAlerts`, `channelsFromEnv`, `alertSink`)
- Modify: `antenna/src/index.ts` (`alertSink` call)
- Modify: `antenna/wrangler.jsonc` (the alerts comment: email only, plus the relay object)
- Test: `antenna/test/alerts.test.ts`, `antenna/test/clock.test.ts` and `antenna/test/clock-metronome.test.ts` (drop `NTFY_URL`/`NTFY_TOKEN` from `noSecrets`), `antenna/test/wrangler-config.test.ts`

**Interfaces:**
- Consumes: Task 1's `planAlerts`, `GATED_KEYS`, `AlertEntry`.
- Produces (Task 5 reads the document; its shape is the contract):
  - `export const RELAY_KEY = "state/alert-relay.json";` `export const RELAY_RING = 50;` `export const RELAY_TIMEOUT_MS = 10_000;`
  - `export interface RelayMessage { seq: number; at: string; key: string; kind: "alert" | "repeat" | "resolved"; priority: Priority; title: string; message: string }` (`at` = ISO of the invocation's `nowMs`; `seq` integer, strictly increasing within a stream, starting at 1).
  - `export interface RelayDoc { stream: string; ring: RelayMessage[] }` (the last `RELAY_RING` messages, ascending seq).
  - `export function relayDocProblem(value: unknown): string | null` (non-null when: not an object; `stream` not a string; `ring` not an array; any entry without an integer `seq`).
  - `export type RelaySink = (messages: Outgoing[], nowMs: number) => Promise<boolean>;`
  - `export function relaySink(bucket: BucketLike, secrets: readonly string[], newStream: () => string = () => crypto.randomUUID(), timeoutMs = RELAY_TIMEOUT_MS): RelaySink` (never throws; false on failure, timeout or a second lost race, each logged `{ event: "alert-relay-failed", error }`).
  - `export function secretsFromEnv(env: AlertEnv): string[]` (the four `CF_*` values, as `channelsFromEnv` computes today).
  - `channelsFromEnv(env: AlertEnv, now: () => number, Message?: typeof EmailMessage): Channel[]` (email only; `fetchFn` parameter removed).
  - `dispatchAlerts(bucket, channels, conditions, nowMs, repeatMs, batch = COMPLETE, relay?: RelaySink)`.
  - `alertSink(bucket: BucketLike, env: AlertEnv, now: () => number)` (builds `relaySink(bucket, secretsFromEnv(env))`; `fetchFn` parameter removed).
  - `AlertEnv` loses `NTFY_URL` and `NTFY_TOKEN`.

- [ ] **Step 1: Write the failing tests** in `antenna/test/alerts.test.ts` (new `describe("the relay", ...)`; use `MemoryBucket`; `ok`/`broken` channels as in the file; `fixed = () => "stream-1"`):

```ts
it("one write per invocation carrying every message, after the emails", async () => {
  const bucket = new MemoryBucket();
  const putsAtSend: number[] = [];
  const email = { name: "email", send: async () => { putsAtSend.push(bucket.puts(RELAY_KEY)); } };
  await dispatchAlerts(bucket, [email], [cond("tripped-spend"), cond("lead-low")], T0, REPEAT, undefined,
                       relaySink(bucket, [], fixed));
  expect(putsAtSend).toEqual([0, 0]);
  expect(bucket.puts(RELAY_KEY)).toBe(1);
  const doc = bucket.json(RELAY_KEY);
  expect(doc.stream).toBe("stream-1");
  expect(doc.ring.map((m: RelayMessage) => [m.seq, m.key, m.kind, m.priority])).toEqual(
    [[1, "tripped-spend", "alert", "high"], [2, "lead-low", "alert", "high"]]);
  expect(doc.ring[0].at).toBe(new Date(T0).toISOString());
});

it("an invocation that sends nothing neither reads nor writes the relay", async () => { /* bucket.log has no RELAY_KEY entry */ });

it("seq increases across invocations and the ring keeps the last 50", async () => {
  // 60 invocations each sending one distinct ungated once-key -> ring length 50, seqs 11..60, stream unchanged
});

it("title and message are redacted before they are written", async () => {
  // condition text carrying "/zones/zz9/rulesets/rs7" and a configured secret "acct-secret-77";
  // relaySink(bucket, ["acct-secret-77"]) -> JSON text of RELAY_KEY contains neither "zz9", "rs7" nor "acct-secret-77"
});

it("the first write is create-only; a store that refuses the precondition gets an unconditional put", async () => {
  // record options.onlyIf of puts to RELAY_KEY: first is { etagDoesNotMatch: "*" }, second invocation { etagMatches: <string> };
  // a bucket whose put THROWS when onlyIf has etagDoesNotMatch: the doc still exists after one invocation
});

it("a lost race re-reads and retries once, then fails: at most 2 PUTs, logged", async () => {
  // bucket.put returns null for RELAY_KEY always -> relaySink resolves false, bucket.puts(RELAY_KEY) === 2,
  // console.error saw { event: "alert-relay-failed" }; a bucket losing only the first race succeeds with the
  // racer's messages kept and ours appended after them
});

for (const [what, body] of [["unparseable", "{nope"], ["stream not a string", { stream: 5, ring: [] }],
                            ["ring not an array", { stream: "s", ring: {} }],
                            ["a non-integer seq", { stream: "s", ring: [{ seq: 1.5 }] }]] as const) {
  it(`a corrupt object (${what}) is overwritten conditionally on its etag with a fresh stream, logged`, async () => {
    // seed RELAY_KEY with body; one invocation -> onlyIf { etagMatches: <the seeded etag> }, doc.stream === "stream-1",
    // ring seqs start at 1; console.error saw { event: "alert-relay-corrupt" }
  });
}

it("a hung relay write times out and never delays the email of a spend alert", async () => {
  const bucket = new MemoryBucket();
  const put = bucket.put.bind(bucket);                        // R2 binding with no timeout of its own:
  bucket.put = (k, v, o) => (k === RELAY_KEY ? new Promise(() => {}) : put(k, v, o));   // hang the relay only
  const got: string[] = [];
  const email = { name: "email", send: async (o: Outgoing) => { got.push(o.key); } };
  const r = await dispatchAlerts(bucket, [email], [cond("tripped-spend")], T0, REPEAT, undefined,
                                 relaySink(bucket, [], fixed, 5));
  expect(got).toEqual(["tripped-spend"]);
  expect(r).toEqual({ sent: 1, failed: 0 });
});

it("delivered = email OR relay", async () => {
  // email fails, relay ok -> { sent: 1, failed: 0 } and the next minute sends nothing;
  // email ok, relay put throws -> { sent: 1, failed: 0 };
  // both fail -> { sent: 0, failed: 1 } and the next minute sends it again
});

it("a gated alert whose email and relay both failed is retried the next minute, not re-gated", async () => {
  // waf-api present at minutes 0, 1, 2 with a broken email and a relay whose put throws -> minute 2 failed: 1;
  // minute 3 with working email and relay -> the alert goes out at minute 3 (got === ["waf-api"])
});
```

Also:
- Replace the two `ntfy:` tests in `describe("channels")` with `channelsFromEnv builds email only; ntfy is gone`: `channelsFromEnv({ ...fullEmailEnv, NTFY_URL: "https://n/t" } as AlertEnv, () => T0, FakeMessage as never).map((c) => c.name)` equals `["email"]`; and `expect(ntfyChannel)` is gone (remove it from the import list).
- The redaction test `... reaches neither ntfy nor email` becomes `... reaches neither the relay nor email`: dispatch with `relaySink(bucket, secretsFromEnv(env))`, check the email text and the `RELAY_KEY` JSON text for every id.
- `alertSink passes the batch through` keeps its assertions, reading the relay ring's titles instead of ntfy calls (`alertSink(bucket, {}, () => T0)`).
- `wrangler-config.test.ts`: `expect(wranglerText).not.toMatch(/NTFY/)`.

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/alerts.test.ts test/wrangler-config.test.ts`
Expected: FAIL (`RELAY_KEY`, `relaySink`, `secretsFromEnv` not exported; wrangler comment mentions NTFY).

- [ ] **Step 3: Implement the relay in `alerts.ts`.** A shared `withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T>` (the `Promise.race` + `clearTimeout` pattern `emailChannel` uses today; `emailChannel` switches to it). `relaySink` = `withTimeout(writeRelay(...), timeoutMs, "relay")` inside a try that logs and returns false. `writeRelay` algorithm (at most two attempts, so at most 2 PUTs):

```
for attempt in 1..2:
  read = readJsonDoc(bucket, RELAY_KEY)
  msgs(start) = messages.map((o, i) => ({ seq: start + i, at: iso(nowMs), key: o.key, kind: o.kind,
                                          priority: o.priority, title: redact(o.title, secrets),
                                          message: redact(o.message, secrets) }))
  if read.kind === "absent":  ok = createRelay({ stream: newStream(), ring: msgs(1) })   // createJson, on throw putJson unconditional
  else if read.kind === "corrupt" || relayDocProblem(read.value):
                              log { event: "alert-relay-corrupt", error }
                              ok = putJson(bucket, RELAY_KEY, { stream: newStream(), ring: msgs(1) }, read.etag)
  else:                       ring = [...doc.ring, ...msgs(lastSeq + 1)].slice(-RELAY_RING)
                              ok = putJson(bucket, RELAY_KEY, { stream: doc.stream, ring }, read.etag)
  if ok: return true
log { event: "alert-relay-failed", error: "lost the write race twice" }; return false
```

(`lastSeq` = the ring's last `seq`, or 0 for an empty ring.)

- [ ] **Step 4: Rework `dispatchAlerts`.** Per message: log line, then email channels as today, recording `emailOk` per message. Then, only if `send.length > 0 && relay`, `relayOk = await relay(send, nowMs)`. Then for each message: `delivered = (channels.length === 0 && !relay) || emailOk || relayOk`, followed by today's undelivered handling unchanged. `alerts.json` is still written last. Remove `ntfyChannel`, `refusal`, `NTFY_BODY_CHARS`, `NTFY_PRIORITY`, `NTFY_TAGS`, the `NTFY_*` env fields; `channelsFromEnv` builds email only; `alertSink(bucket, env, now)` passes `relaySink(bucket, secretsFromEnv(env))`. Update `index.ts` (`alertSink(bucket, env, now)`). Rewrite the header comment's first paragraph: channels are email; every sending invocation also appends its messages to `state/alert-relay.json`, which hugo relays to ntfy; delivered = email or relay.

- [ ] **Step 5: `wrangler.jsonc`.** Replace the "Cloud alerts: ntfy (secrets NTFY_URL, optional NTFY_TOKEN) and email" comment with: cloud alerts go by email through `ALERT_EMAIL` and are appended to `state/alert-relay.json`, which hugo relays to its ntfy (the Worker sends no ntfy). Drop `NTFY_URL`/`NTFY_TOKEN` from both `noSecrets` helpers in `clock.test.ts` and `clock-metronome.test.ts`.

- [ ] **Step 6: Run the antenna suite and typecheck**

Run: `cd antenna && npm test && npx tsc --noEmit && npx wrangler deploy --dry-run`
Expected: all pass; tsc clean; the dry run builds (it needs no secrets).

- [ ] **Step 7: Commit**

```bash
git add antenna/src/alerts.ts antenna/src/index.ts antenna/wrangler.jsonc antenna/test/alerts.test.ts antenna/test/clock.test.ts antenna/test/clock-metronome.test.ts antenna/test/wrangler-config.test.ts
git commit -m "antenna: relay alerts to hugo through state/alert-relay.json; drop the Worker's ntfy"
```

---

### Task 3: transmitter 3-consecutive gate

**Files:**
- Modify: `packages/transmitter/src/transmitter/alerts.py` (constants, `Dispatcher` lock, streaks, observations, wrappers, module docstring)
- Modify: `packages/transmitter/src/transmitter/service.py` (`Runner._step` returns whether it observed; `Runner.tick` declares steps and ends its observation in a `finally`)
- Test: `packages/transmitter/tests_transmitter/test_alerts.py`, `packages/transmitter/tests_transmitter/test_service.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (Tasks 4-5 rely on these), all in `alerts.py`:
  - `GATE = 3`
  - `GATED_CODES = frozenset({"prune", "publish", "publish-state", "station-root", "plan", "render", "dead-clock-check"})`
  - `TICK = "tick"`, `MONITOR = "monitor"`
  - `STEP_CODES: dict[str, frozenset[str]] = {"plan": {"plan", "station-root"}, "render": {"render", "station-root"}, "publish": {"publish", "prune"}, "lead": {"publish-state"}, "dead-clock-check": {"dead-clock-check"}}` (frozensets)
  - `OBSERVER_STEPS: dict[str, frozenset[str]] = {TICK: {"plan", "render", "publish", "lead"}, MONITOR: {"dead-clock-check"}}`
  - `Dispatcher.end_observation(self, observer: str, steps: Iterable[str]) -> None` (raises `ValueError` for an unknown observer or a step not in `OBSERVER_STEPS[observer]`)
  - module-level `end_observation(observer: str, steps: Iterable[str]) -> None` (no-op without a dispatcher; never raises, logs a WARNING with `exc_info`)
  - `Dispatcher._lock: threading.Lock` (held by `fire`, `resolve`, `active`, `end_observation`)
  - in-process `Dispatcher._streak: dict[str, int]` and `Dispatcher._fired: dict[str, set[str]]` (per observer)

- [ ] **Step 1: Write the failing tests in `test_alerts.py`** (use the file's `Recorder` and `_dispatcher`; `obs = lambda d, *steps: d.end_observation(alerts.TICK, steps)`):

```python
def test_gated_codes_are_exactly_the_approved_list():
    assert alerts.GATE == 3
    assert alerts.GATED_CODES == {"prune", "publish", "publish-state", "station-root", "plan", "render", "dead-clock-check"}
    assert frozenset().union(*alerts.STEP_CODES.values()) == alerts.GATED_CODES
    assert frozenset().union(*alerts.OBSERVER_STEPS.values()) == set(alerts.STEP_CODES)
    for code in ("put-budget", "frame-count-drift", "monitor-stalled", "dead-clock", "guard-stale", "horizon-held"):
        assert code not in alerts.GATED_CODES

@pytest.mark.parametrize("code", ["put-budget", "frame-count-drift", "monitor-stalled", "dead-clock", "guard-stale", "horizon-held"])
def test_each_ungated_code_sends_on_its_first_fire(tmp_path, code):
    rec = Recorder(); d, _ = _dispatcher(tmp_path, rec)
    d.fire(code, "m")
    assert [s[0] for s in rec.sent] == [f"llama radio: {code}"]

def test_a_gated_code_sends_only_on_the_third_consecutive_observation(tmp_path):
    rec = Recorder(); d, clock = _dispatcher(tmp_path, rec)
    for _ in range(2):
        d.fire("publish", "PUT failed"); obs(d, "lead", "publish"); clock["t"] += 60
        assert rec.sent == [] and d.active() == [] and "publish" not in (read_json(tmp_path / "alerts.json", {}) or {})
    d.fire("publish", "PUT failed"); obs(d, "lead", "publish")
    assert [s[0] for s in rec.sent] == ["llama radio: publish"] and "3 consecutive" in rec.sent[0][1]
    assert d.active() == ["publish"]

def test_an_observation_where_a_declaring_step_ran_without_the_code_resets_its_streak(tmp_path):
    # fire+obs twice, then obs(d, "lead", "publish") with no fire, then fire+obs once -> nothing sent; two more -> sent

def test_an_observation_where_no_declaring_step_ran_neither_advances_nor_resets(tmp_path):
    # plan fired + obs("lead","plan","render","publish") twice; obs("lead","publish") (idle tick); plan fired + full obs -> sent

def test_repeated_fires_within_one_observation_count_once(tmp_path):
    # two observations each firing "publish" twice -> no send; third observation fires twice -> exactly one send

def test_the_send_decision_is_made_at_the_first_fire_with_its_message(tmp_path):
    # third observation: fire("publish", "A") then fire("publish", "B") -> rec.sent[0][1].startswith("A")

def test_ending_one_observer_never_touches_the_other_observers_codes(tmp_path):
    # dead-clock-check fired + end_observation(MONITOR, ["dead-clock-check"]) twice;
    # end_observation(TICK, ["lead","plan","render","publish"]); then dead-clock-check fired -> sent

def test_a_single_blip_inside_an_active_episode_never_sends_a_repeat(tmp_path):
    # reach an active publish episode (3 obs); clock += 6 H exactly (a repeat is due, the event code not yet expired);
    # obs(d,"lead","publish") with no fire (reset);
    # fire publish + obs -> no send, d.active() == ["publish"], alerts.json["publish"]["last_fired_at"] == clock["t"]

def test_a_gated_level_code_still_resolves_and_says_so(tmp_path):
    # station-root fired + obs("lead","plan") x3 -> sent; d.resolve("station-root") -> "llama radio: resolved: station-root"

def test_after_a_restart_an_active_episode_continues_without_a_send_until_the_streak_rebuilds(tmp_path):
    # d1 reaches an active publish episode (3 obs); clock += 6 H exactly; d2 = fresh Dispatcher on the same path (a restart);
    # without advancing the clock: d2 fire+obs twice -> no send, d2.active() == ["publish"]; third -> one "repeat" send ("more since the last message")

def test_the_dispatcher_serialises_fire_under_its_lock(tmp_path):
    rec = Recorder(); d, _ = _dispatcher(tmp_path, rec)
    d._lock.acquire()
    t = threading.Thread(target=d.fire, args=("put-budget", "m")); t.start(); t.join(0.2)
    assert t.is_alive() and rec.sent == []
    d._lock.release(); t.join(2)
    assert len(rec.sent) == 1

def test_the_module_level_wrappers_never_raise(tmp_path, caplog):
    rec = Recorder(); d, _ = _dispatcher(tmp_path, rec); alerts.configure(d)
    alerts.end_observation("nobody", ["plan"])                      # unknown observer: logged, not raised
    alerts.end_observation(alerts.TICK, ["dead-clock-check"])       # another observer's step: logged, not raised
    assert "end_observation" in caplog.text
```

- [ ] **Step 2: Write the failing service tests in `test_service.py`:**

```python
def test_station_root_from_plan_survives_a_render_that_succeeds_without_scanning(tmp_path, monkeypatch):
    # the spec's required test: plan_step raises StationRootError, render_step is a no-op that succeeds
    # (monkeypatch pipeline.render_step to lambda *a, **k: None); Dispatcher with _Rec configured
    # tick 1 -> alerts._dispatcher._streak["station-root"] == 1 and rec.sent == []
    # ticks 2, 3 -> rec.sent == ["llama radio: station-root"]

def test_the_tick_ends_its_observation_on_every_path(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(alerts, "end_observation", lambda o, steps: seen.append((o, set(steps))))
    # filling tick -> (TICK, {"lead","plan","render","publish"}); idle tick (lead above low water) -> (TICK, {"lead","publish"});
    # damaged publish.json (as test_an_unreadable_publish_state_alerts_and_fails_the_tick_closed) -> (TICK, {"lead"})

def test_a_publish_locked_step_neither_advances_nor_resets(tmp_path, monkeypatch):
    # publish_all raises PublishLocked -> the recorded steps exclude "publish"

def test_status_cloud_line_omits_a_pending_antenna_entry(tmp_path):
    # pin: cloud_lines over alerts.json {"waf-api": {"active": False, "pending": True, "streak": 2, ...}} -> "alerts     cloud: none"
```

- [ ] **Step 3: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_alerts.py packages/transmitter/tests_transmitter/test_service.py -q`
Expected: FAIL (`GATE`, `end_observation`, `_lock` missing; gated codes send at first fire).

- [ ] **Step 4: Implement in `alerts.py`.** `Dispatcher` gains `_lock` (`field(default_factory=threading.Lock, init=False, repr=False)`), `_streak`, `_fired` (`{TICK: set(), MONITOR: set()}`). `fire` (under the lock), for a code in `GATED_CODES` only:

```
observer = MONITOR if code in STEP_CODES["dead-clock-check"] else TICK
if code in self._fired[observer]: return                 # counted once per observation; alert() already logged it
self._fired[observer].add(code); self._streak[code] = self._streak.get(code, 0) + 1
gate_ok = self._streak[code] >= GATE
episode_starts = not entry.get("active") or _expired(code, entry, now, self.repeat_s)
if episode_starts and not gate_ok: return                # pending: nothing written, not active
... today's path, except: a due send happens only if gate_ok; the first message of a gated episode
    (last is None and the episode started at this fire) appends f"\n\n(alerted after {GATE} consecutive failures)"
```

Ungated codes take today's path unchanged. `end_observation(observer, steps)` (under the lock): validate; `codes = union(STEP_CODES[s] for s in steps)`; set `_streak[c] = 0` for each `c in codes - _fired[observer]`; clear `_fired[observer]`. `resolve` and `active` take the lock. Module docstring: one paragraph on the gate and observations. Add module-level `end_observation` beside `alert`/`resolve`.

- [ ] **Step 5: Implement in `service.py`.** `_step(...) -> bool`: True unless the step raised `PublishLocked`. `tick` collects `ran: set[str]`: `"lead"` once the first `_read_lead` ran; `"plan"`/`"render"` when filling and the step observed; `"publish"` when it observed. Wrap the body in `try`/`finally: alerts.end_observation(alerts.TICK, ran)` so the failed-lead-read early return ends it too. (The monitor still runs inside `tick` until Task 4; leave that call as it is.)

- [ ] **Step 6: Adapt existing tests that relied on a gated code sending at first fire** (`test_first_occurrence_is_sent_then_deduped_until_the_repeat_window`, the failing-channel and cool-down tests, `test_a_successful_step_resolves_its_level_codes`, `test_a_monitor_that_raises_alerts_the_event_code_not_the_level_code`, and any other the run turns up): where the test is about dedupe, channels or cool-down, use the ungated `put-budget` (event) and, for level semantics, a gated level code reached through three observations (a helper `_gated(d, code, step)` that fires and ends the observation three times). Do not weaken an assertion.

- [ ] **Step 7: Run the transmitter suite**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: all pass. Antenna unchanged.

- [ ] **Step 8: Commit**

```bash
git add packages/transmitter/src/transmitter/alerts.py packages/transmitter/src/transmitter/service.py packages/transmitter/tests_transmitter/test_alerts.py packages/transmitter/tests_transmitter/test_service.py
git commit -m "transmitter: gate every-minute alert codes at 3 consecutive observations"
```

---

### Task 4: transmitter dead-clock monitor on its own thread

**Files:**
- Create: `packages/transmitter/src/transmitter/monitor.py`
- Modify: `packages/transmitter/src/transmitter/publish.py` (extract `guard_view`)
- Modify: `packages/transmitter/src/transmitter/r2.py` (`make_client` timeout keywords)
- Modify: `packages/transmitter/src/transmitter/deadclock.py` (`check` takes a guard-view callable, called after the fetch)
- Modify: `packages/transmitter/src/transmitter/alerts.py` (`LEVEL_CODES` gains `monitor-stalled`)
- Modify: `packages/transmitter/src/transmitter/service.py` (`make_reader_client`, `open_monitor`, `Runner` monitor wiring, `run_once`, `monitor-stalled`)
- Modify: `packages/transmitter/src/transmitter/cli.py` (`run --once` uses `run_once`)
- Modify: `packages/transmitter/src/transmitter/sdnotify.py` (docstring: the monitor thread never pings)
- Test: create `packages/transmitter/tests_transmitter/test_monitor.py`; modify `test_publish.py`, `test_deadclock.py`, `test_r2.py`, `test_service.py`, `test_cli.py`

**Interfaces:**
- Consumes: Task 3's `alerts.MONITOR`, `alerts.end_observation`, `GATED_CODES` (`dead-clock-check`).
- Produces (Task 5 plugs the relay into these):
  - `publish.guard_view(get_json: Callable[[str], dict | None]) -> dict` with exactly the keys `blocked`, `error`, `guard_evaluated_at`, `offair`; never raises; a failed guard read gives `blocked=True`, `error=str(exc)`; the offair rules are today's.
  - `publish.guard_blocks_publishing(...)`: signature and cache document unchanged (`{"checked_at": now_s, **guard_view(uploader.get_json)}`); still the only writer of `guard_cache_path`.
  - `r2.make_client(cfg: PublishConfig, *, connect_timeout: float = 10, read_timeout: float = 60)`.
  - `deadclock.DeadClockMonitor.check(self, now_us: int, guard_view: Callable[[], dict | None]) -> None`.
  - `monitor.py`: `MONITOR_INTERVAL_S = 60.0`, `MONITOR_STALL_S = 300.0`, `MONITOR_JOIN_S = 5.0`, `READER_CONNECT_TIMEOUT_S = 5`, `READER_READ_TIMEOUT_S = 10`;
    `class R2Reader: __init__(self, client, bucket: str); get_json(self, key: str) -> dict | None` (None on `NoSuchKey`/`404`; any other error and `json.loads` errors propagate, as `Uploader.get_json`; no other public method);
    `class MonitorLoop: __init__(self, deadclock: DeadClockMonitor | None, reader: R2Reader, relay=None, *, clock: Callable[[], int] = <wall clock in µs, `time.time_ns() // 1000`; monitor.py must not import service>, monotonic: Callable[[], float] = time.monotonic, interval_s: float = MONITOR_INTERVAL_S)`; `run_pass(self, *, relay: bool = True) -> None` (never raises); `start(self) -> None`; `stop(self, timeout_s: float = MONITOR_JOIN_S) -> None`; `started: bool`; `stalled(self) -> str | None` (the alert message, or None). `relay` is any object with `run_pass() -> None` (Task 5's `Relay`).
  - `service.make_reader_client(cfg: TransmitterConfig)` (= `r2.make_client(cfg.publish, connect_timeout=5, read_timeout=10)`; monkeypatchable like `make_client`).
  - `service.open_monitor(st: pipeline.Station) -> MonitorLoop | None` (in this task: a loop when `[antenna] site_url` is set, else None with today's warning; Task 5 extends the condition).
  - `Runner(..., monitor: MonitorLoop | None = None, ...)`; `Runner.run(max_ticks=None)` starts/stops the thread; `Runner.run_once() -> None`.

- [ ] **Step 1: Write the failing tests.**
  - `test_publish.py`:
    - `test_guard_view_never_raises_and_fails_closed`, parametrized over a `get_json` that raises `RuntimeError("boom")` for every key → `{"blocked": True, "error": "boom", "guard_evaluated_at": None, "offair": None}`; returns a list for `GUARD_KEY` → `blocked is True` and `error` set; returns `{"tripped": False, "evaluated_at": "X"}` / `None` → `blocked False`, `guard_evaluated_at` "X", `offair False`.
    - `test_guard_blocks_publishing_is_the_only_cache_writer`: after one call, `read_json(ws.guard_cache_path) == {"checked_at": 1000.0, **publish.guard_view(p.uploader.get_json)}`; text pin: of `src/transmitter/*.py`, only `publish.py` matches `re.search(r"write_json\([^)]*guard_cache_path", text)`.
  - `test_r2.py`, `test_client_timeouts_are_keywords`: `r2.make_client(cfg).meta.config.connect_timeout == 10` and `read_timeout == 60`; with `connect_timeout=5, read_timeout=10` → 5 and 10.
  - `test_deadclock.py`:
    - `test_the_playlist_is_fetched_before_the_guard_view_is_built`: a fetch and a guard callable appending to one list → `["fetch", "guard"]`.
    - `test_a_failing_guard_read_cannot_stop_the_playlist_check`: guard callable returns `{"blocked": True, "error": "boom", "guard_evaluated_at": None, "offair": None}`; two stale 200 reads → `("alert", "dead-clock", ...)` fired; `m.guard_error_since_us == now` after the first.
    - Mechanically wrap every existing `m.check(now, X)` as `m.check(now, lambda: X)`.
  - `test_monitor.py` (new; `fired` fixture as in `test_deadclock.py`, plus recording `alerts.end_observation`; `FakeBucket` from helpers):
    - `test_a_pass_runs_the_check_and_ends_the_monitor_observation`: a fake deadclock records `check`; after `run_pass()` → one check, `end_observation` called with `(alerts.MONITOR, ["dead-clock-check"])`.
    - `test_a_raising_check_fires_dead_clock_check_and_the_loop_goes_on`: check raises → `("alert", "dead-clock-check", ...)`; `last_pass` advanced; a second `run_pass()` runs the check again.
    - `test_a_raising_relay_is_a_warning_only`: relay `run_pass` raises → caplog WARNING, no `alerts.alert` call.
    - `test_run_pass_without_relay_never_calls_the_relay`: `run_pass(relay=False)` → relay untouched.
    - `test_the_monitor_only_reads_r2_never_touches_the_guard_cache_and_never_notifies` (strict surface): a real `DeadClockMonitor` with a fake fetch, `R2Reader(FakeBucket with guard/offair docs, "b")`; `monkeypatch.setattr(sdnotify, "notify", rec)`; two passes → every `bucket.log` op is `"get"`; `ws.guard_cache_path` does not exist (and, pre-seeded in a second case, its bytes are unchanged); `rec` saw nothing; `not hasattr(MonitorLoop(...), "notify")`.
    - `test_r2_reader_exposes_only_get_json`: public attributes of `R2Reader` other than `client`/`bucket` are exactly `{"get_json"}`; `NoSuchKey` → None; bad JSON → `json.JSONDecodeError`.
    - `test_the_thread_is_a_daemon_passes_every_interval_and_stops`: `interval_s=0.01`; `start()`; wait (an Event set by the fake check on its 2nd call, timeout 5 s); the thread is `daemon`; `stop()` → thread not alive within `MONITOR_JOIN_S`.
    - `test_stalled_counts_from_the_start_until_the_first_pass`: injected monotonic; a check blocking on an Event; `start()` at mono 0; at mono 299 → `stalled() is None`; at 301 → message names "5 minutes"/the age; release, the pass completes, at 302 → None.
    - `test_a_dead_thread_is_stalled`: `run_pass` monkeypatched to raise `SystemExit`; after the thread ends, `stalled()` mentions "not running".
  - `test_service.py`:
    - `test_tick_no_longer_runs_the_monitor`: a fake monitor recording `run_pass`, not started → after `tick(NOW)` nothing recorded. (Replaces `test_the_runner_runs_the_dead_clock_check_every_tick_with_the_guard_cache` and `test_a_monitor_that_raises_alerts_the_event_code_not_the_level_code`, whose subjects move to `test_monitor.py`.)
    - `test_monitor_stalled_fires_at_once_and_resolves_when_passes_are_fresh`: Dispatcher with `_Rec`; a started fake monitor whose `stalled()` returns a message then None; tick → `rec.sent == ["llama radio: monitor-stalled"]` (one tick: ungated); next tick → `"llama radio: resolved: monitor-stalled"`.
    - `test_monitor_stalled_is_checked_on_the_failed_lead_read_path`: damaged publish.json + stalled monitor → `monitor-stalled` fired.
    - `test_no_started_monitor_means_no_monitor_stalled_check`: monitor None, and a monitor not started → `stalled` never called.
    - `test_run_starts_the_monitor_and_stops_it_when_the_loop_raises`: fake monitor recording `start`/`stop`; `tick` monkeypatched to raise `KeyboardInterrupt` → `run()` raises, recorded `["start", "stop"]`, and `STOPPING=1` was still notified.
    - `test_run_once_checks_once_on_the_main_thread_without_relay_or_thread`: `threading.active_count()` unchanged; fake monitor saw `run_pass(relay=False)` once, in `threading.main_thread()`, after the tick's publish (record order); `start` never called.
    - `test_open_monitor_needs_site_url` updated: None without `site_url`; with it, a `MonitorLoop` whose `deadclock` has today's url/120.0/2700.0/17; `make_reader_client` (monkeypatched to record `threading.current_thread()`) was called on the main thread, before any `start()`.
  - `test_cli.py`, `test_run_once_end_to_end`: unchanged assertions still pass (no `site_url` → no monitor, no reader client).

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: FAIL (`guard_view`, `monitor` module, `run_once`, keyword timeouts missing; `check` takes a dict).

- [ ] **Step 3: Implement `publish.guard_view`** by moving the read half of `guard_blocks_publishing` (both `try` blocks, unchanged semantics, the guard read's `except Exception` covering a non-dict document) into it; `guard_blocks_publishing` keeps the cache read, the interval test and the only `write_json(ws.guard_cache_path, ...)`.

- [ ] **Step 4: Implement `r2.make_client` keywords, `DeadClockMonitor.check(now_us, guard_view)`** (fetch first; `guard_cache = guard_view()` right after the fetch, then `blocked` and the rest exactly as today) **and `monitor.py`.** `run_pass(relay=True)`:

```
if self.deadclock is not None:
    try: self.deadclock.check(self.clock(), lambda: publish.guard_view(self.reader.get_json))
    except Exception as exc: log.exception(...); alerts.alert("dead-clock-check", f"{type(exc).__name__}: {exc}")
    finally: alerts.end_observation(alerts.MONITOR, ["dead-clock-check"])
if relay and self.relay is not None:
    try: self.relay.run_pass()
    except Exception: log.warning("alert relay pass failed", exc_info=True)
self.last_pass = self.monotonic()
```

The loop body wraps `run_pass` in a catch-all WARNING and waits on the stop event for `max(0, interval_s - elapsed)`. `start()` sets `started`, `last_pass = monotonic()` and starts `threading.Thread(target=..., name="transmitter-monitor", daemon=True)`. `stalled()`: `"the dead-clock monitor thread is not running"` when started and not alive; `f"the dead-clock monitor has completed no pass for {age / 60:.0f} minutes"` when `age > MONITOR_STALL_S`; else None. Nothing in `monitor.py` imports or calls `sdnotify`. The Dispatcher's lock is taken only inside `alerts.alert`/`resolve`/`end_observation` (their own sends, as today); the playlist fetch, the guard reads and the relay never run under it.

- [ ] **Step 5: Wire `service.py`, `alerts.py`, `cli.py`.** `LEVEL_CODES` adds `"monitor-stalled"`. `open_monitor(st)`: build the `DeadClockMonitor` exactly as today when `site_url` is set (else warn and return None); otherwise `MonitorLoop(deadclock, monitor.R2Reader(make_reader_client(st.cfg), st.cfg.publish.bucket))`. `Runner.tick`: remove the dead-clock step; in its `finally`, before `end_observation`, `self._check_monitor()`: only when `self.monitor is not None and self.monitor.started`, `msg = self.monitor.stalled()` → `alerts.alert("monitor-stalled", msg)` or `alerts.resolve("monitor-stalled")`. `Runner.run`: `READY=1`, `monitor.start()` if present, loop, `finally`: `monitor.stop()` then `STOPPING=1`. `run_once()`: `self.tick(self.clock())`, then `self.monitor.run_pass(relay=False)` if present. `cli.run`: build the `Runner`, then `runner.run_once()` if `--once` else `runner.run()`. `sdnotify.py` docstring: WATCHDOG=1 comes from the main loop only; the monitor thread never pings.

- [ ] **Step 6: Run the transmitter suite**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add packages/transmitter/src/transmitter/monitor.py packages/transmitter/src/transmitter/publish.py packages/transmitter/src/transmitter/r2.py packages/transmitter/src/transmitter/deadclock.py packages/transmitter/src/transmitter/alerts.py packages/transmitter/src/transmitter/service.py packages/transmitter/src/transmitter/cli.py packages/transmitter/src/transmitter/sdnotify.py packages/transmitter/tests_transmitter/
git commit -m "transmitter: run the dead-clock check on its own thread with a fresh guard view"
```

---

### Task 5: transmitter relay reader

**Files:**
- Create: `packages/transmitter/src/transmitter/relay.py`
- Modify: `packages/transmitter/src/transmitter/alerts.py` (`NtfyChannel.send` gains `tags`)
- Modify: `packages/transmitter/src/transmitter/workspace.py` (`relay_cursor_path`)
- Modify: `packages/transmitter/src/transmitter/service.py` (`open_monitor` builds the relay; the thread runs with site_url OR ntfy)
- Test: create `packages/transmitter/tests_transmitter/test_relay.py`; modify `test_alerts.py`, `test_service.py`

**Interfaces:**
- Consumes: Task 2's document contract (`RelayDoc`, `RelayMessage`, `relayDocProblem`'s rule); Task 4's `MonitorLoop(relay=...)`, `R2Reader.get_json`, `make_reader_client`.
- Produces:
  - `NtfyChannel.send(self, subject: str, body: str, priority: int, tags: str | None = None) -> None` (None keeps today's rule).
  - `Workspace.relay_cursor_path -> Path` (`root / "alert-relay-cursor.json"`, content `{"stream": str, "seq": int}`).
  - `relay.py`: `RELAY_KEY = "state/alert-relay.json"`, `RELAY_MAX_AGE_S = 3600.0`, `RELAY_PASS_BUDGET_S = 30.0`, `PRIORITY = {"urgent": 5, "high": 4, "default": 3}`, `TAGS = {"urgent": "rotating_light", "high": "warning", "default": "information_source"}`, `RESOLVED_TAGS = "white_check_mark"`;
    `doc_problem(doc: object) -> str | None` (antenna's `relayDocProblem` rule);
    `format_message(m: dict, station: str) -> tuple[str, str, int, str]` (subject, body, priority, tags);
    `class Cursor(NamedTuple): stream: str; seq: int`;
    `class Relay: __init__(self, get_json: Callable[[str], dict | None], channel: NtfyChannel, station: str, cursor_path: Path, *, now: Callable[[], float] = time.time, monotonic: Callable[[], float] = time.monotonic)`; `run_pass(self) -> None`; `cursor: Cursor | None` (in memory, authoritative).

- [ ] **Step 1: Write the failing tests in `test_relay.py`** (a `FakeNtfy` with `send(subject, body, priority, tags)` recording, and a configurable failure per call: `urllib.error.HTTPError(url, code, "x", {}, None)`, `URLError`, `OSError`; `doc(stream, *msgs)` builds a document; `msg(seq, at_s, kind="alert", priority="high", title="T", message="M")`; `NOW = 1_800_000_000.0`):

```python
def test_relay_key_matches_antenna():
    src = (Path(__file__).resolve().parents[3] / "antenna" / "src" / "alerts.ts").read_text()
    assert f'RELAY_KEY = "{relay.RELAY_KEY}"' in src

def test_messages_above_the_cursor_are_sent_once_in_seq_order(tmp_path):
    # doc("s", msg(2, NOW-60), msg(1, NOW-120), msg(3, NOW-10)) -> sent subjects in seq order 1,2,3; cursor ("s", 3);
    # a second pass on the same doc sends nothing; the cursor file holds {"stream": "s", "seq": 3}

@pytest.mark.parametrize("kind, priority, subject, prio, tags", [
    ("alert", "urgent", "llama radio: T", 5, "rotating_light"),
    ("repeat", "high", "llama radio: T", 4, "warning"),
    ("alert", "default", "llama radio: T", 3, "information_source"),
    ("resolved", "default", "llama radio: resolved: T", 3, "white_check_mark"),
    ("resolved", "urgent", "llama radio: resolved: T", 3, "white_check_mark")])
def test_formatting_title_priority_and_tags(kind, priority, subject, prio, tags):
    s, body, p, t = relay.format_message(msg(1, NOW, kind=kind, priority=priority), "llama radio")
    assert (s, p, t) == (subject, prio, tags) and body.startswith("M") and "antenna" in body

def test_no_cursor_sends_only_messages_younger_than_max_age_and_logs_each_skip_once(tmp_path, caplog):
    # msg(1, NOW-7200), msg(2, NOW-3599) -> only seq 2 sent; one log line naming seq 1; a second pass logs nothing new

def test_a_stream_change_restarts_at_seq_0_in_the_new_stream(tmp_path):
    # cursor file {"stream": "old", "seq": 500}; doc("new", msg(1, NOW-30), msg(2, NOW-20)) -> both sent, cursor ("new", 2)

def test_a_4xx_refusal_other_than_429_is_logged_with_its_status_and_skipped(tmp_path, caplog):
    # seq 1 refused 400, seq 2 ok -> WARNING mentions 400, seq 2 sent, cursor ("s", 2)

@pytest.mark.parametrize("failure", [http_error(429), http_error(503), urllib.error.URLError("down"), OSError("ntfy: HTTP 302")])
def test_429_5xx_or_transport_stop_the_pass_and_the_next_pass_retries_from_that_message(tmp_path, failure):
    # seq 1 ok, seq 2 fails, seq 3 never attempted; cursor ("s", 1); next pass (no failure) sends 2 then 3

def test_the_pass_stops_after_its_30_s_budget(tmp_path):
    # monotonic advances 20 s per send; five fresh messages -> two sent, cursor at 2; next pass continues at 3

def test_a_missing_object_is_nothing_to_relay_and_keeps_the_cursor(tmp_path):
    # get_json -> None; nothing sent; cursor unchanged; cursor file not rewritten

@pytest.mark.parametrize("bad", ["raise", [], {"stream": 5, "ring": []}, {"stream": "s", "ring": {}},
                                 {"stream": "s", "ring": [{"seq": 1.5}]}, {"stream": "s", "ring": [{"seq": True}]}])
def test_an_unreadable_or_malformed_document_is_a_warning_never_an_alert(tmp_path, caplog, monkeypatch, bad):
    # monkeypatch alerts.alert to record; WARNING logged; nothing sent; no alert recorded; cursor unchanged

def test_an_at_in_the_future_is_sent_and_an_unparseable_at_is_skipped_and_advanced(tmp_path, caplog):
    # msg(1, at="not a time"), msg(2, NOW+120) -> seq 1 WARNING and skipped, seq 2 sent, cursor ("s", 2)

def test_the_cursor_file_is_read_once_at_startup_and_a_bad_one_is_one_warning(tmp_path, caplog):
    # cursor file "{" -> one WARNING at construction, cursor None; later passes never re-read the file (delete it: no change)

def test_a_failed_cursor_write_is_a_warning_and_never_causes_a_resend(tmp_path, caplog):
    # cursor_path is a directory: pass 1 sends seq 1 and warns; pass 2 sends nothing

def test_the_relay_bypasses_the_dispatcher(tmp_path):
    # alerts.configure(Dispatcher with Recorder); a relay pass -> the Dispatcher's Recorder saw nothing; alerts.json absent
```

In `test_alerts.py`, `test_ntfy_channel_takes_explicit_tags`: `send("s", "b", 3, tags="information_source")` → header `Tags == "information_source"`; without `tags` the existing priority rule holds (`4` → `warning`, `3` → `white_check_mark`).

In `test_service.py`:
- `test_open_monitor_with_ntfy_only_relays_without_a_dead_clock_check`: `alerts.ntfy_url` set, no `site_url` → a `MonitorLoop` with `deadclock is None` and a `Relay` whose channel is a `NtfyChannel` with that url, a distinct instance from any Dispatcher channel (`dispatcher_from_config(...).channels`), carrying `NTFY_TOKEN` from the env mapping passed in.
- `test_no_ntfy_means_no_relay_and_one_warning`: `site_url` set, no `ntfy_url` → `relay is None`, caplog has exactly one "not relayed" warning.
- `test_neither_site_url_nor_ntfy_means_no_monitor`: None, and `make_reader_client` never called.

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_relay.py packages/transmitter/tests_transmitter/test_alerts.py packages/transmitter/tests_transmitter/test_service.py -q`
Expected: FAIL (no `relay` module, no `tags` parameter, `open_monitor` ignores ntfy).

- [ ] **Step 3: Implement `NtfyChannel.send(..., tags=None)` and `Workspace.relay_cursor_path`.**

- [ ] **Step 4: Implement `relay.py`.** Construction reads the cursor file once (`read_json`; anything but `{"stream": str, "seq": int}` → one WARNING, `cursor = None`). `run_pass` algorithm (the cursor rule is the spec's Part 2 hugo side, verbatim in behaviour):

```
try: doc = get_json(RELAY_KEY) except Exception: WARNING; return
if doc is None: return
if (p := doc_problem(doc)) is not None: WARNING(p); return
start_seq = cursor.seq if cursor and cursor.stream == doc["stream"] else 0
handled = start_seq; started = monotonic()
for m in sorted((m for m in doc["ring"] if m["seq"] > start_seq), key=seq):
    if monotonic() - started >= RELAY_PASS_BUDGET_S: break
    at = parse ISO m["at"] (fails, or a text field not a str -> WARNING naming seq; handled = seq; continue)
    if now() - at >= RELAY_MAX_AGE_S: INFO "skipped relayed alert <seq> (<key>): older than 1 h"; handled = seq; continue
    try: channel.send(*format_message(m, station))  -> handled = seq
    except HTTPError e with 400 <= e.code < 500 and e.code != 429: WARNING with e.code; handled = seq
    except Exception: WARNING "relay stopped at <seq>: ..."; break          # 429, 5xx, transport, ntfy 3xx
new = Cursor(doc["stream"], handled)
if new != cursor: cursor = new; try write_json(cursor_path, ...) except OSError: WARNING
```

`format_message`: subject `f"{station}: {'resolved: ' if kind == 'resolved' else ''}{title}"`; body `f"{message}\n\n-- relayed from antenna ({at})"`; priority 3 and `RESOLVED_TAGS` for `resolved`, else `PRIORITY`/`TAGS` by `priority` (an unknown priority string → 3, `information_source`). Module docstring: what the relay is, the cursor rule, why `RELAY_MAX_AGE_S`.

- [ ] **Step 5: Extend `service.open_monitor(st, env: Mapping[str, str] = os.environ)`.** `relay_on = bool(cfg.alerts.ntfy_url)`; without it warn once (`[alerts] ntfy_url is not set: antenna alerts are not relayed to ntfy`). Return None when neither `site_url` nor `ntfy_url` is set (before creating any client). Otherwise create the reader client on the calling (main) thread, then `Relay(reader.get_json, NtfyChannel(cfg.alerts.ntfy_url, env.get("NTFY_TOKEN") or None), cfg.antenna.station_name, st.ws.relay_cursor_path)` when `relay_on`.

- [ ] **Step 6: Run the transmitter suite**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add packages/transmitter/src/transmitter/relay.py packages/transmitter/src/transmitter/alerts.py packages/transmitter/src/transmitter/workspace.py packages/transmitter/src/transmitter/service.py packages/transmitter/tests_transmitter/test_relay.py packages/transmitter/tests_transmitter/test_alerts.py packages/transmitter/tests_transmitter/test_service.py
git commit -m "transmitter: relay antenna's alerts from state/alert-relay.json to hugo's ntfy"
```

---

### Task 6: the plan step feeds the watchdog

**Files:**
- Modify: `packages/transmitter/src/transmitter/pipeline.py` (`Station.notify`, `frames_of`)
- Modify: `packages/transmitter/src/transmitter/service.py` (`Runner.__init__` wires it)
- Test: `packages/transmitter/tests_transmitter/test_pipeline.py`, `packages/transmitter/tests_transmitter/test_service.py`

**Interfaces:**
- Consumes: `Runner(notify=...)` (existing).
- Produces: `Station.notify: Callable[[str], object] | None = None` (last dataclass field); `Station.frames_of(show)` pings `notify("WATCHDOG=1")` after each `engine.analyze` call, also when it raised (`try`/`finally`); `plan_step`'s signature is unchanged.

- [ ] **Step 1: Write the failing tests.**
  - `test_pipeline.py`, `test_plan_step_pings_the_watchdog_after_each_analysis`: `make_station(tmp_path, n_packages=3)`, `st.notify = pings.append`; `pipeline.plan_step(st, NOW)` → `pings.count("WATCHDOG=1") == len(st.engine.analyzed) >= 1`.
  - `test_render_steps_replan_path_pings_too`: call `st.extend([], st.scan_now(NOW), NOW, start_frame=0, run_start=True)` with `st.notify` set → one ping per analysis.
  - `test_a_failed_analysis_still_pings`: an engine whose `analyze` raises `RenderError` for one slug → that show is skipped (existing `on_skip`) and the ping count still equals the analyze calls.
  - `test_frames_of_without_notify_is_unchanged`: `notify` None → no error, same frame count as before.
  - `test_service.py`, `test_the_runner_wires_its_notify_into_the_station`: `Runner(st, p, notify=rec)` → `st.notify is rec`; a `Station` that already has a notify keeps it.

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_pipeline.py packages/transmitter/tests_transmitter/test_service.py -q`
Expected: FAIL (`Station` has no `notify`).

- [ ] **Step 3: Implement** `Station.notify` and the `frames_of` ping; `Runner.__init__`: `if st.notify is None: st.notify = notify`. Leave `service.row_analysis` as is (its docstring already records the gap).

- [ ] **Step 4: Run the transmitter suite**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter/src/transmitter/pipeline.py packages/transmitter/src/transmitter/service.py packages/transmitter/tests_transmitter/test_pipeline.py packages/transmitter/tests_transmitter/test_service.py
git commit -m "transmitter: ping the watchdog after each show analysis in the plan step"
```

---

### Task 7: docs

**Files:**
- Modify: `docs/playout-setup.md` (§6.1, §6.2 item 6, §6.3, §7, §7.1, §8)
- Modify: `docs/playout-incident-runbook.md`
- Modify: `CLAUDE.md`
- Read (input): `docs/superpowers/2026-10-23-playout-phase2-verification.md` (the §8 corrections K, J, B2, A2, C1 and the phase-1 corrections it lists)

**Interfaces:**
- Consumes: the names and constants of Tasks 1-6 (`GATE`, `GATED_KEYS`, `GATED_CODES`, `state/alert-relay.json`, `~/.transmitter/alert-relay-cursor.json`, `RELAY_MAX_AGE` 1 h, `monitor-stalled` 5 min).
- Produces: nothing code depends on.

- [ ] **Step 1: `docs/playout-setup.md`.**
  - §6.1: `[alerts] ntfy_url` is now also what carries antenna's pushes (via the relay); `NTFY_TOKEN` in the env file covers both.
  - §6.2 item 6: remove the ASCII requirement for `STATION_NAME` (the Worker sends no ntfy); say relayed push titles use hugo's `[antenna] station_name`.
  - §6.3: replace `npx wrangler secret put NTFY_URL` / `NTFY_TOKEN` with: a new deploy sets no ntfy secret; an existing deploy deletes them after this release (`npx wrangler secret delete NTFY_URL`, `npx wrangler secret delete NTFY_TOKEN`).
  - §7 **Alerts** bullet: cloud alerts are emailed by the Worker and pushed by hugo's relay (up to ~1 min after the email); the 3-consecutive gate in one sentence; point to §7.1.
  - §7.1: add a **Gate** column (or list) to the cloud table and the hugo list: gated at 3 (the spec's lists), sent at once (with the two immediate raise sites named: `metronome-down` from the stall branch, `guard-unknown` from the post-unblock re-check), unchanged (`guard-reading-failing`, `lead-low`, `offair-without-fallback`, `dead-clock`, `guard-stale`, `horizon-held`). Add `monitor-stalled` (level, sent at once, 5-min threshold). Add a **Relay** paragraph (`state/alert-relay.json`, ring of 50, stream + seq, hugo's cursor file, `RELAY_MAX_AGE` 1 h, 30 s per pass, missing/malformed object = WARNING only). Add a **Limits** list with every item of the spec's "Limits" section, verbatim in substance (alternate-minute failures; rotating symptoms; ticks not minutes ~50 min; R2 write/read outages; ~1 min push lag; hugo down; lost cursor re-sends up to an hour once) plus the operator ruling (the five playlist keys stay gated; hugo's `dead-clock` ~3-4 min is the cover).
  - §8: fold in K (edit → restart → STOP; `sudo journalctl`; expect ~2.5 min; a `systemctl edit` `WatchdogSec` drop-in does not reach a running service), J (`dead-clock` ~17-18 min after cron actually stops plus up to ~15 min dashboard propagation), B2 (test something only the off-air `index.html` carries, not `off the air`), A2 (Worker requests on the billing page, ~1 day lag; no Workers & Pages graph), C1 (unmeasurable until phase 3); check the phase-1 corrections listed in the verification doc are present (Free plan rate limit path-only, workers.dev prerequisite, Cache Rule labels, dashboard paths) and fold in any missing. Change "urgent ntfy and email" / "(email + ntfy)" wording to the relay. Add relay verification items: (a) one antenna alert (e.g. the `LEAD_FLOOR_HOURS:30` item) reaches the phone via hugo within ~2 min of its email, tagged as relayed from antenna; (b) a gated key does not page on a single failure (one bad minute of `CF_WAF_TOKEN` restored within the minute sends nothing; three minutes send one alert noting 3 consecutive failures).
  - The "Deploys" order from the spec (Worker dry-run + deploy + secret deletes; hugo update + restart; order does not matter) goes at the end of §6.3 or as a short §6.4.

- [ ] **Step 2: `docs/playout-incident-runbook.md`.** For each gated key (cloud and hugo) add "pages only after 3 consecutive failing minutes (cloud) / ticks or monitor passes (hugo); a single failure is logged, not sent". Add `### monitor-stalled (level, has "resolved")` under §4 (meaning, first look: `journalctl` for the `transmitter-monitor` thread, R2 latency; the main loop is still alive, the watchdog is unaffected; a restart clears it). In §1/§2 say antenna pushes now come through hugo (no push while hugo is down: check email). In §6 procedures, the secret list drops `NTFY_URL`, `NTFY_TOKEN`.

- [ ] **Step 3: `CLAUDE.md`** (the transmitter and antenna paragraphs under Commands and "What this is"):
  - antenna secrets list: drop `NTFY_URL`, `NTFY_TOKEN (optional)`.
  - one line for the gate: every-minute alert keys (antenna `GATED_KEYS`, transmitter `GATED_CODES`) send only after 3 consecutive failing observations; spend/off-air keys and one-shot keys never; two immediate raise sites.
  - one line for the relay: antenna appends sent alerts to `state/alert-relay.json`; hugo's monitor thread relays them to its ntfy (cursor `~/.transmitter/alert-relay-cursor.json`, 1 h max age); the Worker sends no ntfy.
  - transmitter paragraph: the dead-clock check and the relay run on a daemon monitor thread every 60 s with its own get-only R2 reader (never writes, never touches `guard-cache.json`, never pings the watchdog); `monitor-stalled` fires when its last pass is over 5 min old; `run --once` checks once on the main thread and does not relay; the plan step pings the watchdog after each show analysis.

- [ ] **Step 4: Verify** that no doc still tells the operator to set `NTFY_URL`/`NTFY_TOKEN` as Worker secrets:

Run: `grep -n "secret put NTFY\|NTFY_URL" docs/playout-setup.md docs/playout-incident-runbook.md CLAUDE.md`
Expected: only the delete instructions match.

- [ ] **Step 5: Run both suites** (docs only, but the antenna `wrangler-config` test and transmitter tests must still pass):

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && (cd antenna && npm test)`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add docs/playout-setup.md docs/playout-incident-runbook.md CLAUDE.md
git commit -m "docs: alert gate, the hugo ntfy relay, the monitor thread, and the section 8 corrections"
```

---

### Final gate (orchestrator, after Task 7)

- [ ] `cd antenna && npm test && npx tsc --noEmit && npx wrangler deploy --dry-run` — all pass, build succeeds.
- [ ] `./.venv/bin/python -m pytest -q` from the worktree root (the whole repo suite: llama, emcee, herder, transmitter, scripts) — all pass.
- [ ] `packages/transmitter/scripts/test-in-debian12.sh` — transmitter's tests pass on Python 3.11 + ffmpeg 5.1 (needs docker; if docker is unavailable, say so in the report and leave it for the operator).
- [ ] Whole-branch review on Opus against the spec and this plan's Global Constraints. Deploys are the operator's (spec "Deploys").
