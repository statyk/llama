# antenna metronome Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single Durable Object (`Metronome`) writes `live.m3u8` from an alarm re-armed at every 10.24 s grid boundary, under a 15-minute lease that the cron clock renews every minute. Cron's own write loop runs only as the fallback when the object looks dead, and the cost guard prices the object's three billed meters.

**Architecture:** Cron keeps the guard, `index.html` and its inputs. It then calls `renew(lease | null)` over RPC on every path, with the lease the spec's table names. A healthy object writes the playlist from then on and cron writes nothing. The object's logic is a pure module (`metronome-core.ts`) plus a sequencing engine over a port (`metronome-engine.ts`); both are tested with a fake clock and a fake bucket. The Durable Object (`metronome.ts`) only binds that engine to storage, alarms, R2 and env. The build-and-PUT body of a playlist write moves into `live.ts`, which both writers share. Only the exact string `METRONOME = "on"` enables any of it; anything else is today's cron loop, unchanged.

**Tech Stack:** TypeScript, wrangler 4.149.0, `@cloudflare/vitest-plugin` 1.4.0 with vitest 5.0.3 (workerd), Durable Objects (SQLite-backed, KV API, alarms, RPC), Cloudflare GraphQL Analytics API. No new npm dependency.

**Spec:** `docs/superpowers/specs/2026-10-14-antenna-metronome-design.md`, approved by the operator 2026-10-14. Its Stakes section governs. Its review record, `docs/superpowers/2026-10-14-metronome-spec-review/` (`decisions-r1.md`, `decisions-r2.md`), explains why each rule is what it is. Do not re-open a settled rule there. The parent design is `docs/superpowers/specs/2026-10-09-playout-design.md` (sections "antenna" and "Cost guard"). `CLAUDE.md`'s antenna paragraph describes the as-built code this plan extends.

## Stakes (from the spec; they govern)

Money and on-air continuity are at risk. Data is not.

**Spend is the strict surface.** Cloudflare has no account spending cap. This plan adds a new billed product (Durable Objects) and a new writer of a billed R2 object (`live.m3u8`: one Class A operation per PUT). Treat the metronome's PUT bound, its lease expiry and the guard's new meters with the rigor of a migration:

- an unknown verdict is never treated as unblocked;
- spend must not depend on cron being alive (the lease expires on the object's own clock);
- every DO meter is either priced by the guard or bounded by construction.

**The goal is continuity:** no playlist freeze over ~45 s in normal operation. iOS drops audio once `live.m3u8` stops advancing for ~60–75 s.

**This repo is public.** No committed file may carry an account ID, zone ID, token or email address. A test enforces this for `wrangler.jsonc`.

## Global Constraints

- **Scope:** `antenna/` and docs only. transmitter, hugo, llama, emcee and herder are untouched, so the Python 3.11 constraint does not apply.
- **No new npm dependency.** Installed and used as-is: wrangler 4.149.0, `@cloudflare/vitest-plugin` 1.4.0, vitest 5.0.3, typescript ^5.9.3.
- **Tests:** every task runs `cd antenna && npm test` (which first checks that `src/pages.ts` is fresh, then runs vitest in workerd) and `cd antenna && npm run typecheck`, from the worktree. Both must pass at the end of every task.
- **No deploys and no Cloudflare API calls by any implementer.** `npx wrangler deploy` may run only with `--dry-run`. The only live steps are Task 9's, and the operator runs them.
- **Constants, verbatim from the spec:**
  - `METRONOME_LEASE_MS` = 15 min;
  - `METRONOME_STALE_MS` = 30 s; cron falls back at `stalls >= 2`;
  - `MAX_DO_PUTS_PER_MINUTE` = 10 per rolling 60 s, renew's write included;
  - at most 12 `alarm()` invocations per rolling 60 s;
  - R2 PUT timeout 5 s; cron's renew timeout 15 s;
  - alarm target = first `startMs(n) + 25 ms` strictly after `max(now, lastTarget)`;
  - the off-air notice in the DO is numbered with `offairSeqMs = now + 75 s`;
  - one instance, `idFromName("metronome")`;
  - only the exact string `"on"` enables the metronome.
- **Cron's existing spend bounds are unchanged:** `MAX_PUTS = 10`, the `d ≠ 10.24` refusal and the 75 s loop clamp.
- **Fail closed.** Expiry is written negated (`!(now < expiresAt)`). NaN or missing values trip, never pass.
- **The DO's storage is a fixed key set** (`STORAGE_KEYS`, 8 keys) and never grows.
- **Commits:** one per task, on branch `antenna-metronome`. End each message with the attribution lines your session's system reminder gives. Never name a file `REPORT*`, `SUMMARY*`, `FINDINGS*` or `ANALYSIS*`.
- **Model hints** (orchestrator assigns; reviewers stay on Opus, the final branch reviewer on Fable per the spec's review mode): sonnet for mechanical 1–2-file tasks with complete code; opus for the lease and acceptance logic, `alarm()` and its caps, the cron fallback decision, and the guard's new meters.

## Verified while writing this plan (2026-10-14/15, read-only or in a scratch copy)

- **The plan's code was verified in a scratch copy of `antenna/`, at its final state.** Tasks 4 and 5 were verified together there, and some tests were added at the end. Result: `npm run typecheck` clean, 364 tests green (236 at baseline), `node scripts/build-pages.mjs --check` ok. `npx wrangler deploy --dry-run` bundles 84.48 KiB and lists `env.METRONOME_DO (Metronome)` as a Durable Object binding and `env.METRONOME ("off")`.
- **The per-task boundaries were then re-run (2026-10-15).** A fresh copy of the baseline was built from this plan's text, task by task, each step applied as written. Every boundary held, with typecheck and the pages check clean at each: 240, 252, 278, 304, 329, 342, 364. The result was byte-identical to the verified final state. The per-task counts are still expected values, not guarantees: if yours differ, report the difference rather than assume it is yours, and do not "fix" the plan's code.
- **Migration syntax** (wrangler 4.149.0). A scratch copy of `wrangler.jsonc` was dry-run in both forms:
  - `"migrations": [{ "tag": "v1", "new_sqlite_classes": ["Metronome"] }]`;
  - `"exports": { "Metronome": { "type": "durable-object", "storage": "sqlite" } }`.

  Both pass `npx wrangler deploy --dry-run`, with no warning. The installed schema (`node_modules/wrangler/config-schema.json`) says the two are **mutually exclusive**. **This plan uses `migrations` + `new_sqlite_classes`.** It is the form the `alarm-probe` Worker actually deployed to this account with this same wrangler (`~/lma-radio-ops/do-alarm-probe/wrangler.jsonc`, 2026-10-13). The vitest plugin's bundled config reader accepts both forms too.
- **What `cloudflare:test` exposes** (`node_modules/@cloudflare/vitest-plugin/types/cloudflare-test.d.ts`): `runInDurableObject`, `runDurableObjectAlarm`, `evictDurableObject`, `listDurableObjectIds`, `reset`, `abortAllDurableObjects`, `evictAllDurableObjects`, `createExecutionContext`, `createScheduledController`, `waitOnExecutionContext`. Three behaviours were measured in a scratch project:
  - **DO storage is NOT isolated per test** in 1.4.0. State carries over between tests in a file. Files that touch the DO call `await reset()` in `afterEach`, which clears DO storage, alarms, R2 and instances.
  - An instance's `env` can be swapped in a test with `runInDurableObject(stub, (o) => { o.env = {...} })`. The swap lasts until the object is evicted or reset. That is how tests turn the switch on: the committed var is `"off"`.
  - **Real alarms fire on time in the test runtime.** A lease whose epoch puts `now` exactly on a boundary arms an alarm 25 ms away, which races the test's assertions. This was measured as a flaky failure under the full suite. Runtime tests therefore build horizons that put `now` 3 s into a segment, so the alarm is ~7 s away.
- **No wrangler config is needed in `vitest.config.ts`.** The plugin reads `wrangler.jsonc`, so the DO binding and the migration there are what the tests run against. The DO class must be exported from `src/index.ts` (the `main` module).
- **GraphQL fields and filters** are the ones the spec author's read-only query used against this account on 2026-10-14:
  - `durableObjectsInvocationsAdaptiveGroups(filter: { datetime_geq, datetime_leq }) { sum { requests } }`;
  - `durableObjectsPeriodicGroups(filter: { datetimeMinute_geq, datetimeMinute_leq }) { sum { duration rowsWritten } }`;
  - with `$x: Time!` variables and `.000Z` timestamps, as in the existing `USAGE_QUERY`.
- **DO prices, Workers Paid** (read 2026-10-14 from https://developers.cloudflare.com/durable-objects/platform/pricing/ via WebFetch, whose tool summarizes; the quotes it returned match the spec's research):
  - requests: "1 million / month, + $0.15/million", which "Includes HTTP requests, RPC sessions, WebSocket messages, and alarm invocations";
  - duration: "400,000 GB-s / month, + $12.50/million GB-s";
  - SQLite rows written: "First 50 million / month included + $1.00 / million rows";
  - rows read: "First 25 billion / month included + $0.001 / million rows";
  - stored data: "5 GB-month, + $0.20/ GB-month";
  - "Each setAlarm() is billed as a single row written".

  Task 9's checkpoint has the operator eyeball the page once more before the deploy.
- **`worker-configuration.d.ts`** is already stale (it lists `PLAYLIST_WINDOW: "6"`). The code types its env through `src/env.ts` (`AntennaEnv`), so this plan does **not** regenerate it.
- **The probe teardown commands** come from `~/lma-radio-ops/do-alarm-probe/README.md` (Task 9).

## Spec readings (where the spec left a choice; each picks the spend-strict, fail-closed reading)

1. **Binding name `METRONOME_DO`.** `METRONOME` is the spec's switch var, so the namespace binding needs another name.
2. **The lease type is a discriminated union**, `PlayLease | HoldLease`. That is the spec's `Lease` with its "play only" fields made required on `play`. The DO stores it as a **JSON string**, so "an unparseable stored lease" is a real, testable case. A stored lease with no numeric `expiresAt` loads as expired.
3. **Three modules instead of two.** `metronome-core.ts` is pure (spec J2). `metronome-engine.ts` sequences `renew`/`alarm` over a port. `metronome.ts` is the thin DO. The serialized section (an in-object promise chain) lives in the engine, so the spec's interleave test can use a fake bucket whose PUT resolves on demand.
4. **Keys are written when they change, and `stalls` on every renew.** The spec's renew step 2 says "Update `stalls`", so every renew writes it, changed or not: a healthy object then writes at least one row a minute, which the guard's "empty is not zero" check (reading 10) relies on for `doRowsWritten`. The other keys stay absent until first set (`lastAlarmGoodAt` until the first tick, for example). The key-set tests pin "always within `STORAGE_KEYS`" and "exactly `STORAGE_KEYS` after a full cycle".
5. **"Logged once"** is a per-anomaly episode mark held in memory, as the spec's known limitation says. An episode starts on the first occurrence and ends when the condition clears. `metronome-null-build` and `offair-without-fallback` are once per lease.
   - Three log names are added for paths the spec implies but does not name: `metronome-alarm-error`, the catch-all that keeps `alarm()` from throwing, `metronome-null-build`, and `metronome-duplicate` (reading 9).
6. **`metronome-down`** (priority `high`, resolvable, clock family) is raised on **every** trigger. That includes the paths where the fallback loop may not write: the guard is unknown and renew throws, or a hold goes unanswered. The DO being unreachable is worth an alert even when cron cannot stand in for it.
7. **`renew` answers `applied: "off"` with `lease: "none"`.** While off, the object acts on no lease.
8. **A capped `alarm()`** (13th in 60 s) is not recorded in the window, and it does not advance `lastAlarmGoodAt`.
9. **A duplicate alarm is one that finds an alarm still pending.** While `alarm()` runs, `getAlarm()` "returns null unless setAlarm() was called after the handler started" (the Cloudflare docs, as quoted in `docs/superpowers/2026-10-14-metronome-spec-review/do-research-sonnet.md`), so a genuine delivery sees none. When `alarm()` finds one pending after its lease check, it is a duplicate or retried delivery and is idempotent, as the spec requires ("A duplicate or retried alarm rebuilds the same bytes and skips the PUT"): it builds for `now` and PUTs only if the bytes differ (normally they are identical, a confirmed tick); it does not re-arm, leaves `lastTarget` alone and is not counted against the alarm cap; it logs `metronome-duplicate` once per episode. The rule rests on the docs and on the test double (`FakePort`, whose `deliver` consumes the alarm and `deliverDuplicate` leaves it set); Task 6 checks it in workerd, and Task 9 on the real runtime.
10. **The guard's "empty is not zero" check** runs in `guardStep`, after `readUsage` and before pricing, behind `GuardConfig.metronomeOn` (exactly `"on"`). It is `meter.ts` `assertMetronomeMetered`: a recent window with `doRequests` 0 or `doRowsWritten` 0 is a failed reading.
11. **Cron computes `offairWithoutFallback` before issuing the lease**, in both modes. Off-mode behaviour is unchanged, because the first write follows at once; the existing clock tests pin it. The loop keeps its once-per-invocation guard.
12. **The renew client builds the stub inside each `renew`.** A missing binding (or anything else) then rejects into trigger (a) instead of throwing before `runClock` starts, which would also skip the guard.
13. **`wrangler.jsonc` commits `"METRONOME": "off"`.** Rollout step 3 is a one-line commit to `"on"`. The rollback is the reverse, or the immediate `npx wrangler deploy --var METRONOME:off`. A test pins the value to exactly `"on"` or `"off"`, so a typo cannot pass for either.

## Review Focus

The five input classes or failure modes most likely to bite, which the spec implies but its test list does not exercise. Each has a test in the task named:

1. **A deploy while an alarm is pending** (the docs are silent). Expected: the lease and the pending alarm survive the object's restart, the next alarm ticks and re-arms, and otherwise the next renew repairs the chain within a minute. Test: eviction keeps the lease and the pending alarm, and the chain goes on (Task 6). Measured live in Task 9.
2. **An epoch change (new `epoch_id`) while the chain ticks.** Expected: the next renew writes the new epoch's playlist at once, and the next alarm re-aims to the new grid, with no burst and no hot loop. Test: Task 5, "alarm: an epoch change".
3. **A cron isolate whose clock runs ahead issues a future-dated `verdictAt`.** Expected: newer unblocked leases are superseded until real time passes it, but a blocked lease or a hold is still accepted at once, and expiry is still 15 min by the DO's own clock. Test: Task 3, "a future-dated verdictAt never keeps a blocked lease out".
4. **The binding is missing while `METRONOME` is `"on"`.** This can happen with a `--var METRONOME:on` deploy from a config without the DO. Expected: the renew rejects inside the client (trigger a), cron runs its own loop and alerts, and the guard still runs. Test: Task 6, "a missing binding rejects inside renew"; Task 7, "(a) renew throws". A persistent `metronome-down` while `METRONOME` is `"on"` (the object absent or broken) also fails every guard reading (`doRequests` = 0) and trips the station blind after 6 h, so the runbook rolls back with `--var METRONOME:off` rather than ride it out (Task 8, section 9 "Rollback").
5. **A duplicate alarm delivered right after a completed tick** (spec reading 9). Expected: it sees the re-armed alarm still pending, rebuilds the same bytes and skips the PUT; it neither re-arms nor moves `lastTarget`; a renew later in the same segment writes nothing, and `MEDIA-SEQUENCE` never goes backwards. Tests: Task 5, "duplicates after a completed tick" and "a duplicate, then a renew in the same segment"; Task 6, "the alarm ticks and re-arms" (a genuine delivery in workerd sees no pending alarm).

## File structure

```
antenna/
  src/live.ts                 NEW  the one playlist write: renderLive (build + off-air-without-fallback), putLive   [T1]
  src/clock.ts                MOD  uses live.ts [T1]; METRONOME in ClockEnv [T2]; GRID_D from grid.ts [T3];
                                   lease table, renew, fallback decision, metronome-down, MetronomeLine [T7]
  src/pricing.ts              MOD  three DO meters, prices, OpCounts, evaluateSpend                               [T2]
  src/meter.ts                MOD  DO datasets in USAGE_QUERY, parsing, assertMetronomeMetered                    [T2]
  src/latch.ts                MOD  stored(): every meter in guard.json                                            [T2]
  src/guard.ts                MOD  metronomeOn (METRONOME read via ClockEnv), the empty-is-zero check            [T2]
  src/grid.ts                 MOD  GRID_D moves here (core must not import clock.ts)                              [T3]
  src/metronome-core.ts       NEW  pure: Lease, validation, ordering, expiry, targets, windows, stalls, state,
                                   fallbackReason, MetronomeStatus, MetronomeClient                                [T3]
  src/metronome-engine.ts     NEW  MetronomeEngine over MetronomePort: renew [T4], alarm [T5]
  src/metronome.ts            NEW  the Metronome Durable Object + metronomeClient (fixed name, 15 s timeout)      [T6]
  src/env.ts                  MOD  METRONOME_DO                                                                    [T6]
  src/index.ts                MOD  export Metronome [T6]; metronome client wired behind the switch [T7]
  src/alerts.ts               MOD  metronome-down in CLOCK_KEYS                                                    [T7]
  wrangler.jsonc              MOD  DO binding, migration v1, METRONOME "off", observability comment               [T6]
  test/live.test.ts           NEW                                                                                  [T1]
  test/support.ts             MOD  usageResponse carries the DO datasets                                           [T2]
  test/pricing.test.ts        REWRITE  (every Usage/OpCounts literal gains the DO meters)                          [T2]
  test/meter.test.ts, guard.test.ts, latch.test.ts, conditions.test.ts   MOD                                       [T2]
  test/metronome-core.test.ts NEW                                                                                  [T3]
  test/metronome-support.ts   NEW  FakePort, lease(), engineAt() [T4]; deliver(), deliverDuplicate() [T5]
  test/metronome-renew.test.ts NEW                                                                                 [T4]
  test/metronome-alarm.test.ts NEW                                                                                 [T5]
  test/metronome.test.ts      NEW  runtime plumbing: runInDurableObject / runDurableObjectAlarm                    [T6]
  test/wrangler-config.test.ts MOD binding, migration, switch value                                                [T6]
  test/clock-metronome.test.ts NEW lease table, triggers, scheduled handler                                        [T7]
  test/alerts.test.ts         MOD  metronome-down is clock-family                                                  [T7]
docs/playout-setup.md                                       section 4 step 7, section 7.1 row, new section 9       [T8]
CLAUDE.md                                                   antenna paragraph                                      [T8]
docs/superpowers/specs/2026-10-09-playout-design.md          as-built notes (antenna, cost guard)                  [T8]
docs/superpowers/2026-10-1x-metronome-verification.md        the live record (operator + parent)                   [T9]
```

## Tasks

| # | Task | Model hint |
|---|---|---|
| 0 | Worktree and baseline | sonnet |
| 1 | `live.ts`: the shared playlist write | sonnet |
| 2 | Cost guard: the Durable Object meters | opus |
| 3 | `metronome-core.ts`: lease, ordering, expiry, targets, caps, stalls, state | opus |
| 4 | `metronome-engine.ts`: `renew` (serialized, capped, bounded PUT) | opus |
| 5 | `metronome-engine.ts`: `alarm()` (re-arm first, caps, never throws) | opus |
| 6 | The Durable Object, its binding, migration and switch | sonnet |
| 7 | Cron: the lease table, the fallback decision, `metronome-down` | opus |
| 8 | Docs: runbook, CLAUDE.md, parent spec as-built | sonnet |
| 9 | Rollout and verification day — **HUMAN CHECKPOINT** | sonnet |

**Dependencies:** strictly sequential, 0 → 9. Task 2 is independent of Tasks 3–6 and could run in parallel with Task 3. It is ordered early because rollout step 2 deploys the meters before the switch is flipped.

**Review gate after Task 7.** That completes the whole spend path: meters, caps, lease, fallback. The orchestrator reports to the parent before Task 8. The final branch review (Fable, per the spec's review mode) happens before Task 9's deploy.

---

### Task 0: Worktree and baseline

**Model hint:** sonnet

**Files:** none changed except the plan file, which is copied in, and committed only if it differs from `main`'s.

**Interfaces:**
- Produces: `.claude/worktrees/antenna-metronome` on branch `antenna-metronome` from `main`, with `antenna/node_modules`.

- [ ] **Step 1: Create the worktree and install**

```bash
cd /Users/shawn/projects/llama
git worktree add .claude/worktrees/antenna-metronome -b antenna-metronome main
cp docs/superpowers/plans/2026-10-15-antenna-metronome.md .claude/worktrees/antenna-metronome/docs/superpowers/plans/
cd .claude/worktrees/antenna-metronome/antenna && npm ci
```

- [ ] **Step 2: Baseline is green**

Run: `cd /Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/antenna && npm test && npm run typecheck`
Expected: `Tests  236 passed (236)`, and tsc prints nothing.

- [ ] **Step 3: Commit the plan, only if it differs from `main`'s**

`main` already carries the plan, so the copy differs only if the plan was edited after it was committed there. Staging first makes the check also catch a plan `main` lacks.

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/antenna-metronome
git -C "$W" add docs/superpowers/plans/2026-10-15-antenna-metronome.md
git -C "$W" diff --cached --quiet main -- docs/superpowers/plans/2026-10-15-antenna-metronome.md ||
  git -C "$W" commit -m "docs(antenna): metronome implementation plan"
```

All later paths are relative to the worktree's `antenna/` unless they start with `docs/` or `CLAUDE.md`. Run steps (`cd antenna && ...`) run from the worktree root; commit steps name it with `git -C "$W"`, so they work from anywhere.

---

### Task 1: `live.ts` — the shared playlist write

**Model hint:** sonnet

The spec ("Playlist contents") says: "the per-write body of `runClock` (build, detect off-air-without-fallback, compare bytes, cap, PUT) moves into a shared module used by the cron loop and the DO". The byte comparison and the cap stay with each writer, because each keeps its own state for them. Build, detection and PUT move. This is a pure refactor: every existing clock test must pass unchanged.

**Files:**
- Create: `src/live.ts`, `test/live.test.ts`
- Modify: `src/clock.ts` (imports; `LIVE_KEY` and `offairWithoutFallback` move out; the `write` closure uses `renderLive`/`putLive`)

**Interfaces:**
- Consumes: `playlist.ts` `buildPlaylist`, `isOffair`, `usableFallback`, `FallbackIndex`, `PlaylistConfig`; `grid.ts` `Horizon`; `bucket.ts` `BucketLike`.
- Produces (`src/live.ts`):
  - `LIVE_KEY = "live.m3u8"`;
  - `interface LiveSource { horizon: Horizon; fallback: FallbackIndex | null; offair: boolean }`;
  - `offairWithoutFallback(src: LiveSource, nowMs: number, cfg: PlaylistConfig): string | null`;
  - `renderLive(src, nowMs, offairSeqMs, cfg): { body: string | null; offairWithoutFallback: string | null }`;
  - `putLive(bucket: BucketLike, body: string, liveMaxAge: number): Promise<void>` (max-age at least 1).
  - `clock.ts` keeps exporting `LIVE_KEY` (re-export).

- [ ] **Step 1: Write the failing test** — `test/live.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { LIVE_KEY, offairWithoutFallback, putLive, renderLive } from "../src/live";
import { MemoryBucket } from "./support";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const CFG = { window: 6, grace: 3, offairAfterMs: 86_400_000, lookahead: 12, holdBack: 5 };
const H = { epoch_id: "e1", epoch: new Date(E).toISOString(), d: 10.24, first: 0, last: 1_000_000,
            published_at: new Date(E).toISOString(), container: "adts", fallback_version: "v1" };
const FB = { len: 7, notice: "fallback/v1/notice.aac" };

describe("renderLive", () => {
  it("builds the live playlist on air, with no off-air reason", () => {
    const r = renderLive({ horizon: H, fallback: FB, offair: false }, E + 50 * D, E + 50 * D, CFG);
    expect(r.body).toContain("seg/e1/62.aac"); // 50 + lookahead 12
    expect(r.offairWithoutFallback).toBeNull();
  });

  it("numbers the off-air notice from offairSeqMs (offairSequence)", () => {
    const r = renderLive({ horizon: H, fallback: FB, offair: true }, E + 50 * D, E + 60 * D, CFG);
    expect(r.body).toContain("#EXT-X-MEDIA-SEQUENCE:73"); // indexAt(60 d) + 12 + 1
    expect(r.body).toContain("fallback/v1/notice.aac");
  });

  it("is null before the epoch, and says why off air has no notice", () => {
    expect(renderLive({ horizon: H, fallback: FB, offair: false }, E - 1, E - 1, CFG).body).toBeNull();
    const r = renderLive({ horizon: H, fallback: null, offair: true }, E + 10 * D, E + 10 * D, CFG);
    expect(r.body).toContain("#EXT-X-ENDLIST");
    expect(r.offairWithoutFallback).toMatch(/blocked.*fallback\/v1\/index\.json is missing/);
    expect(offairWithoutFallback({ horizon: H, fallback: FB, offair: true }, E, CFG)).toBeNull();
  });
});

describe("putLive", () => {
  it("writes live.m3u8 with its content type and a max-age of at least 1 s", async () => {
    const b = new MemoryBucket();
    await putLive(b, "#EXTM3U\n", 5);
    expect(b.objects.get(LIVE_KEY)).toMatchObject({ body: "#EXTM3U\n", contentType: "application/vnd.apple.mpegurl",
                                                    cacheControl: "public, max-age=5" });
    await putLive(b, "#EXTM3U\n", 0);
    expect(b.objects.get(LIVE_KEY)!.cacheControl).toBe("public, max-age=1");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/live.test.ts`
Expected: FAIL. The import of `../src/live` cannot be resolved.

- [ ] **Step 3: Create `src/live.ts`**

```ts
/** The one implementation of a live.m3u8 write, shared by the cron loop
 * (clock.ts) and the metronome (metronome-engine.ts): build the body, detect
 * off-air without a usable fallback, and PUT it with its headers. What each
 * writer adds around it (its PUT cap, its identical-bytes memory, its timing)
 * stays with that writer. */

import type { BucketLike } from "./bucket";
import type { Horizon } from "./grid";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export const LIVE_KEY = "live.m3u8";

/** What a playlist is built from: the horizon, its fallback index, and the
 * blocked verdict (true = the off-air playlist). */
export interface LiveSource {
  horizon: Horizon;
  fallback: FallbackIndex | null;
  offair: boolean;
}

/** Why off-air is in force at nowMs and no usable fallback exists, or null. */
export function offairWithoutFallback(src: LiveSource, nowMs: number, cfg: PlaylistConfig): string | null {
  const inp = { nowMs, horizon: src.horizon, fallback: src.fallback, offair: src.offair };
  if (!isOffair(inp, cfg) || usableFallback(inp) !== null) return null;
  const h = src.horizon;
  const cause = src.offair
    ? "the station is blocked (tripped or state/offair.json)"
    : `horizon is stale (now is more than ${cfg.offairAfterMs / 1000} s past the end of segment ${h.last})`;
  const missing =
    h.fallback_version === null || h.fallback_version === ""
      ? "horizon.fallback_version is null"
      : src.fallback === null
        ? `fallback/${h.fallback_version}/index.json is missing or unreadable`
        : `fallback/${h.fallback_version}/index.json has len < 1`;
  return `off-air (${cause}) but no usable fallback (${missing}): live.m3u8 written as an ENDLIST-only playlist (no notice), so players stop`;
}

/** The body to write at nowMs (null = write nothing: before the epoch, or no
 * usable fallback for a loop entry), with the off-air-without-fallback reason
 * when that applies. offairSeqMs numbers the off-air notice
 * (playlist.offairSequence). */
export function renderLive(src: LiveSource, nowMs: number, offairSeqMs: number,
                           cfg: PlaylistConfig): { body: string | null; offairWithoutFallback: string | null } {
  return {
    body: buildPlaylist({ nowMs, horizon: src.horizon, fallback: src.fallback, offair: src.offair, offairSeqMs }, cfg),
    offairWithoutFallback: offairWithoutFallback(src, nowMs, cfg),
  };
}

/** PUT live.m3u8 with its content type and max-age (at least 1 s). */
export async function putLive(bucket: BucketLike, body: string, liveMaxAge: number): Promise<void> {
  await bucket.put(LIVE_KEY, body, {
    httpMetadata: { contentType: "application/vnd.apple.mpegurl",
                    cacheControl: `public, max-age=${Math.max(1, Math.floor(liveMaxAge))}` },
  });
}
```

- [ ] **Step 4: Point `src/clock.ts` at it** (four edits)

(a) Imports. Replace

```ts
import { reconcileIndex } from "./indexpage";
import { buildPlaylist, type FallbackIndex, isOffair, type PlaylistConfig, usableFallback } from "./playlist";

export { type BucketLike, r2Bucket, type StoredObject } from "./bucket";
```

with

```ts
import { reconcileIndex } from "./indexpage";
import { type LiveSource, putLive, renderLive } from "./live";
import type { FallbackIndex, PlaylistConfig } from "./playlist";

export { type BucketLike, r2Bucket, type StoredObject } from "./bucket";
export { LIVE_KEY } from "./live";
```

(b) Delete the line `export const LIVE_KEY = "live.m3u8";` and the blank line after it.

(c) Delete the whole function `offairWithoutFallback` (its doc comment `/** Why off-air is in force at nowMs and no usable fallback exists, or null. */` through its closing `}`).

(d) In `runClock`, replace

```ts
    const write = async (force: boolean) => {
      const nowMs = deps.now();
      // The off-air number comes from max(scheduledTime + loopMs, nowMs) plus
      // lookahead + 1 (playlist.offairSequence): constant within an on-time
      // invocation, and above every live segment listed so far even when this
      // invocation runs later than its own loop.
      const body = buildPlaylist({ nowMs, horizon, fallback: inputs.fallback, offair: inputs.offair,
                                   offairSeqMs: deps.scheduledTime + config.loopMs }, config);
      // Ruling: off-air without a usable fallback writes the ENDLIST-only
      // playlist through the normal path below (cap and identical-bytes skip
      // apply), but stays loud: the notice is missing. Once per invocation.
      if (result.offairWithoutFallback === null) {
        const reason = offairWithoutFallback(inputs, horizon, nowMs, config);
        if (reason !== null) {
```

with

```ts
    const src: LiveSource = { horizon, fallback: inputs.fallback, offair: inputs.offair };
    const write = async (force: boolean) => {
      const nowMs = deps.now();
      // The off-air number comes from max(scheduledTime + loopMs, nowMs) plus
      // lookahead + 1 (playlist.offairSequence): constant within an on-time
      // invocation, and above every live segment listed so far even when this
      // invocation runs later than its own loop.
      const { body, offairWithoutFallback: reason } = renderLive(src, nowMs, deps.scheduledTime + config.loopMs, config);
      // Ruling: off-air without a usable fallback writes the ENDLIST-only
      // playlist through the normal path below (cap and identical-bytes skip
      // apply), but stays loud: the notice is missing. Once per invocation.
      if (result.offairWithoutFallback === null) {
        if (reason !== null) {
```

and replace

```ts
      await bucket.put(LIVE_KEY, body, {
        httpMetadata: { contentType: "application/vnd.apple.mpegurl", cacheControl: `public, max-age=${config.liveMaxAge}` },
      });
```

with

```ts
      await putLive(bucket, body, config.liveMaxAge);
```

- [ ] **Step 5: Run everything**

Run: `cd antenna && npm test && npm run typecheck`
Expected: `Tests  240 passed (240)`, tsc silent. Every clock test passes unchanged; the 4 new ones in `test/live.test.ts` pass.

- [ ] **Step 6: Commit**

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/antenna-metronome
git -C "$W" add antenna/src/live.ts antenna/src/clock.ts antenna/test/live.test.ts
git -C "$W" commit -m "refactor(antenna): live.ts, the one playlist build-and-PUT both writers share"
```

---

### Task 2: Cost guard — the Durable Object meters

**Model hint:** opus (spend path)

Spec "Cost guard: Durable Object meters". The guard gains three meters:

| Meter | Included / month | Overage | GraphQL (account-scoped) |
|---|---|---|---|
| `doRequests` | 1,000,000 | $0.15 / M | `durableObjectsInvocationsAdaptiveGroups` `sum.requests`, all types and statuses |
| `doDurationGbS` | 400,000 | $12.50 / M | `durableObjectsPeriodicGroups` `sum.duration` (GB-s) |
| `doRowsWritten` | 50,000,000 | $1.00 / M | the same dataset, `sum.rowsWritten` |

Prices: see "Verified while writing this plan" (read 2026-10-14). Rows read and stored bytes are bounded by construction and not metered (spec). The touch points the spec lists:

- `METERS`, `Usage`, `OpCounts`, `Reading`;
- `evaluateSpend`'s literals;
- `meter.ts` parsing;
- `latch.ts` `stored()`.

Plus "empty is not zero" while `METRONOME` is `"on"`. **Only these three meters and that check.** Do not touch the latch rules, the thresholds or the blind rule.

`transmitter` reads `guard.json` and checks only `evaluation.{at, actual_usd, projected_usd, budget_usd}` (`packages/transmitter/src/transmitter/cloudstate.py`). The extra `period_to_date` keys are therefore invisible to hugo, and transmitter needs no change.

**Files:**
- Modify: `src/pricing.ts`, `src/meter.ts`, `src/latch.ts`, `src/guard.ts`, `src/clock.ts` (the switch in `ClockEnv`)
- Modify (tests): `test/support.ts`, `test/meter.test.ts`, `test/guard.test.ts`, `test/latch.test.ts`, `test/conditions.test.ts`
- Rewrite (test): `test/pricing.test.ts`

**Interfaces:**
- Produces:
  - `pricing.ts`: `type Meter` gains `"doRequests" | "doDurationGbS" | "doRowsWritten"`; `METERS` has 7 entries; `OpCounts` gains `doRequests`, `doDurationGbS`, `doRowsWritten` (numbers); `PRICES.meters` carries the three.
  - `meter.ts`: `USAGE_QUERY` gains the aliases `doToDate`, `doRecent`, `doPeriodicToDate`, `doPeriodicRecent`; `assertMetronomeMetered(r: Reading): void` throws `analytics: the metronome is on but ...`.
  - `clock.ts`: `ClockEnv.METRONOME?: string`, the switch's only declaration (`AntennaEnv` extends `ClockEnv`);
  - `guard.ts`: `guardConfigFromEnv(env: GuardEnv & Pick<ClockEnv, "METRONOME">)`; `GuardConfig.metronomeOn: boolean` (`env.METRONOME === "on"`).
  - `test/support.ts`: `type DoUsage = [requests, durationGbS, rowsWritten]`; `usageResponse({... dos?: DoUsage | null; dosRecent?: DoUsage | null })`. The defaults are `[90_000, 600, 150_000]` and `[1_250, 8, 2_000]`; `null` means the API's `[]`.

- [ ] **Step 1: Write the failing tests**

(a) `test/support.ts`: replace the whole `usageResponse` function (from its doc comment `/** A canned account-scoped response, shaped as the API returns it. */` to the end of the file) with:

```ts
/** Durable Object usage for usageResponse: [requests, duration GB-s, rowsWritten]. */
export type DoUsage = [number, number, number];

/** A canned account-scoped response, shaped as the API returns it. The DO
 * defaults are a metronome's: ~9 days in, inside every allowance. A DO range
 * with no activity is `[]` in the API (`null` here). */
export function usageResponse(o: { workers?: number; workersRecent?: number; ops?: Record<string, number>;
                                   opsRecent?: Record<string, number>; buckets?: [number, number][];
                                   dos?: DoUsage | null; dosRecent?: DoUsage | null } = {}) {
  const ops = (m: Record<string, number>) =>
    Object.entries(m).map(([actionType, requests]) => ({ sum: { requests }, dimensions: { actionType } }));
  const inv = (d: DoUsage | null) => (d === null ? [] : [{ sum: { requests: d[0] } }]);
  const per = (d: DoUsage | null) => (d === null ? [] : [{ sum: { duration: d[1], rowsWritten: d[2] } }]);
  const dos = o.dos === undefined ? [90_000, 600, 150_000] as DoUsage : o.dos;
  const dosRecent = o.dosRecent === undefined ? [1_250, 8, 2_000] as DoUsage : o.dosRecent;
  return {
    data: { viewer: { accounts: [{
      workersToDate: [{ sum: { requests: o.workers ?? 40_000 } }],
      workersRecent: [{ sum: { requests: o.workersRecent ?? 180 } }],
      r2ToDate: ops(o.ops ?? { PutObject: 200_000, GetObject: 300_000, DeleteObject: 80_000 }),
      r2Recent: ops(o.opsRecent ?? { PutObject: 3_000, GetObject: 4_000 }),
      storage: (o.buckets ?? [[1.4e9, 2e6]]).map(([payloadSize, metadataSize], i) =>
        ({ max: { payloadSize, metadataSize }, dimensions: { bucketName: `b${i}` } })),
      doToDate: inv(dos),
      doRecent: inv(dosRecent),
      doPeriodicToDate: per(dos),
      doPeriodicRecent: per(dosRecent),
    }] } },
    errors: null,
  };
}
```

(b) `test/latch.test.ts` and `test/conditions.test.ts`: in each, replace

```ts
const usage = { workersRequests: 0, r2ClassA: 0, r2ClassB: 0, r2StorageGbMonth: 0 };
```

with

```ts
const usage = { workersRequests: 0, r2ClassA: 0, r2ClassB: 0, r2StorageGbMonth: 0, doRequests: 0, doDurationGbS: 0,
                doRowsWritten: 0 };
```

(c) Replace `test/pricing.test.ts` entirely with:

```ts
import { describe, expect, it } from "vitest";
import { applyAttempt, freshGuardDoc } from "../src/latch";
import { evaluateSpend, METERS, type OpCounts, overThreshold, PRICES, priceUsage, type Reading,
         type Usage } from "../src/pricing";

const DAY = 86_400_000;
const PERIOD = { startMs: Date.parse("2026-10-11T00:00:00Z"), endMs: Date.parse("2026-11-11T00:00:00Z") };
const NO_DO = { doRequests: 0, doDurationGbS: 0, doRowsWritten: 0 };
const zero: OpCounts = { workersRequests: 0, r2ClassA: 0, r2ClassB: 0, ...NO_DO };
const usage = (u: Partial<Usage>): Usage =>
  ({ workersRequests: 0, r2ClassA: 0, r2ClassB: 0, r2StorageGbMonth: 0, ...NO_DO, ...u });

describe("priceUsage", () => {
  it("is the $5 base while every meter is inside its allowance", () => {
    expect(priceUsage(usage({ workersRequests: 9_999_999, r2ClassA: 1_000_000, r2ClassB: 10_000_000, r2StorageGbMonth: 10,
                              doRequests: 1_000_000, doDurationGbS: 400_000, doRowsWritten: 50_000_000 })).totalUsd)
      .toBe(5);
  });

  it("prices only the usage beyond each allowance", () => {
    const r = priceUsage(usage({ workersRequests: 12_000_000, r2ClassA: 3_000_000, r2ClassB: 20_000_000, r2StorageGbMonth: 30 }));
    expect(r.perMeterUsd.workersRequests).toBeCloseTo(0.6, 10);
    expect(r.perMeterUsd.r2ClassA).toBeCloseTo(9.0, 10);
    expect(r.perMeterUsd.r2ClassB).toBeCloseTo(3.6, 10);
    expect(r.perMeterUsd.r2StorageGbMonth).toBeCloseTo(0.3, 10);
    expect(r.totalUsd).toBeCloseTo(5 + 0.6 + 9 + 3.6 + 0.3, 10);
  });

  it("prices each Durable Object meter through its allowance", () => {
    const r = priceUsage(usage({ doRequests: 3_000_000, doDurationGbS: 600_000, doRowsWritten: 60_000_000 }));
    expect(r.perMeterUsd.doRequests).toBeCloseTo(2 * 0.15, 10); // 2M over at $0.15/M
    expect(r.perMeterUsd.doDurationGbS).toBeCloseTo(0.2 * 12.5, 10); // 200k GB-s over at $12.50/M
    expect(r.perMeterUsd.doRowsWritten).toBeCloseTo(10 * 1.0, 10); // 10M over at $1.00/M
    expect(r.totalUsd).toBeCloseTo(5 + 0.3 + 2.5 + 10, 10);
  });

  it("carries the published prices", () => {
    expect(PRICES.baseUsd).toBe(5);
    expect(PRICES.meters.r2ClassA).toEqual({ included: 1_000_000, usdPerUnit: 4.5e-6 });
    // Durable Objects, Workers Paid (checked 2026-10-14).
    expect(PRICES.meters.doRequests).toEqual({ included: 1_000_000, usdPerUnit: 0.15e-6 });
    expect(PRICES.meters.doDurationGbS).toEqual({ included: 400_000, usdPerUnit: 12.5e-6 });
    expect(PRICES.meters.doRowsWritten).toEqual({ included: 50_000_000, usdPerUnit: 1e-6 });
  });

  it("prices every meter: a positive, finite price and a finite allowance (no meter is free by omission)", () => {
    expect(METERS).toHaveLength(7);
    expect(new Set(METERS).size).toBe(7);
    expect(Object.keys(PRICES.meters).sort()).toEqual([...METERS].sort());
    for (const m of METERS) {
      const { included, usdPerUnit } = PRICES.meters[m];
      expect([m, Number.isFinite(usdPerUnit) && usdPerUnit > 0]).toEqual([m, true]);
      expect([m, Number.isFinite(included) && included >= 0]).toEqual([m, true]);
      // One unit past the allowance costs money, on its own.
      expect([m, priceUsage(usage({ [m]: included + 1_000_000 })).totalUsd > 5]).toEqual([m, true]);
    }
  });
});

describe("evaluateSpend", () => {
  it("projects each meter from the recent rate through the allowances, not a dollar average", () => {
    const now = PERIOD.startMs + 10 * DAY; // 21 days left
    const r: Reading = {
      periodToDate: { ...zero, workersRequests: 100_000, r2ClassA: 500_000 },
      recent: { ...zero, r2ClassA: 30_000 }, // 10k Class A per hour
      recentMs: 3 * 3_600_000, storageBytes: 0, unknownActionTypes: [],
    };
    const e = evaluateSpend(r, PERIOD, now, 15);
    expect(e.actualUsd).toBe(5); // 0.5M Class A is inside the 1M allowance
    // 500k + 10k/h * 504 h = 5.54M Class A: 4.54M billable * $4.50/M
    expect(e.projected.r2ClassA).toBeCloseTo(5_540_000, 3);
    expect(e.projectedUsd).toBeCloseTo(5 + 4.54 * 4.5, 6);
  });

  it("projects every op meter from its own recent rate", () => {
    const now = PERIOD.startMs + 10 * DAY; // 504 h left
    const r: Reading = {
      periodToDate: { ...zero, workersRequests: 100_000, r2ClassA: 500_000 },
      // distinct per-hour rates: Workers 400k, Class A 10k, Class B 200k
      recent: { ...zero, workersRequests: 1_200_000, r2ClassA: 30_000, r2ClassB: 600_000 },
      recentMs: 3 * 3_600_000, storageBytes: 0, unknownActionTypes: [],
    };
    const e = evaluateSpend(r, PERIOD, now, 15);
    expect(e.projected.workersRequests).toBeCloseTo(100_000 + 400_000 * 504, 3); // 201.7M
    expect(e.projected.r2ClassA).toBeCloseTo(500_000 + 10_000 * 504, 3); // 5.54M
    expect(e.projected.r2ClassB).toBeCloseTo(200_000 * 504, 3); // 100.8M
    // every meter past its allowance, so the total depends on each projection
    expect(e.projectedUsd).toBeCloseTo(5 + 191.7 * 0.3 + 4.54 * 4.5 + 90.8 * 0.36, 6);
  });

  it("projects each Durable Object meter from its own recent rate", () => {
    const now = PERIOD.startMs + 10 * DAY; // 504 h left
    const r: Reading = {
      periodToDate: { ...zero, doRequests: 100_000, doDurationGbS: 1_000, doRowsWritten: 200_000 },
      // per hour: 3k requests, 20 GB-s, 5k rows
      recent: { ...zero, doRequests: 9_000, doDurationGbS: 60, doRowsWritten: 15_000 },
      recentMs: 3 * 3_600_000, storageBytes: 0, unknownActionTypes: [],
    };
    const e = evaluateSpend(r, PERIOD, now, 15);
    expect(e.periodToDate).toMatchObject({ doRequests: 100_000, doDurationGbS: 1_000, doRowsWritten: 200_000 });
    expect(e.projected.doRequests).toBeCloseTo(100_000 + 3_000 * 504, 3);
    expect(e.projected.doDurationGbS).toBeCloseTo(1_000 + 20 * 504, 3);
    expect(e.projected.doRowsWritten).toBeCloseTo(200_000 + 5_000 * 504, 3);
    expect(e.projectedUsd).toBeCloseTo(5 + 0.612 * 0.15, 6); // only requests pass their allowance: 1.612M
  });

  it("never projects below period-to-date once the period is over", () => {
    const r: Reading = {
      periodToDate: { ...zero, workersRequests: 11_000_000, r2ClassA: 2_000_000 },
      recent: { ...zero, workersRequests: 1_000_000, r2ClassA: 1_000_000 },
      recentMs: 3_600_000, storageBytes: 0, unknownActionTypes: [],
    };
    const e = evaluateSpend(r, PERIOD, PERIOD.endMs + DAY, 15);
    expect(e.projected.workersRequests).toBe(11_000_000);
    expect(e.projected.r2ClassA).toBe(2_000_000);
    expect(e.projectedUsd).toBeCloseTo(e.actualUsd, 10);
    expect(e.projectedUsd).toBeCloseTo(5 + 0.3 + 4.5, 10);
  });

  it("holds the peak storage over the elapsed and the whole period", () => {
    const now = PERIOD.startMs + 15 * DAY;
    const e = evaluateSpend({ periodToDate: zero, recent: zero, recentMs: 3_600_000, storageBytes: 60e9,
                              unknownActionTypes: [] }, PERIOD, now, 15);
    expect(e.periodToDate.r2StorageGbMonth).toBeCloseTo(30, 10); // 60 GB * 15/30
    expect(e.projected.r2StorageGbMonth).toBeCloseTo(62, 10); // 60 GB * 31/30
  });

  it("has nothing left to project at the period's end", () => {
    const e = evaluateSpend({ periodToDate: zero, recent: { ...zero, r2ClassA: 1e9 }, recentMs: 1, storageBytes: 0,
                              unknownActionTypes: [] }, PERIOD, PERIOD.endMs, 15);
    expect(e.projectedUsd).toBe(5);
  });

  it("every meter is finite in periodToDate, projected and the stored guard.json evaluation", () => {
    const now = PERIOD.startMs + 10 * DAY;
    const r: Reading = { periodToDate: { workersRequests: 1, r2ClassA: 2, r2ClassB: 3, doRequests: 4, doDurationGbS: 5.5,
                                         doRowsWritten: 6 },
                         recent: { workersRequests: 1, r2ClassA: 1, r2ClassB: 1, doRequests: 1, doDurationGbS: 0.25,
                                   doRowsWritten: 1 },
                         recentMs: 3_600_000, storageBytes: 1e9, unknownActionTypes: [] };
    const e = evaluateSpend(r, PERIOD, now, 15);
    const doc = applyAttempt(freshGuardDoc(now), { ok: true, evaluation: e, period: PERIOD, baseBudgetUsd: 15 });
    for (const m of METERS) {
      expect([m, Number.isFinite(e.periodToDate[m])]).toEqual([m, true]);
      expect([m, Number.isFinite(e.projected[m])]).toEqual([m, true]);
      expect([m, Number.isFinite(doc.evaluation!.period_to_date[m])]).toEqual([m, true]);
      expect([m, Number.isFinite(doc.evaluation!.projected[m])]).toEqual([m, true]);
    }
    expect(Object.keys(doc.evaluation!.period_to_date).sort()).toEqual([...METERS].sort());
    expect(doc.evaluation!.period_to_date.doDurationGbS).toBe(5.5); // fractional, not rounded away
  });
});

describe("overThreshold", () => {
  it("trips at actual >= 90% or projected >= 100%", () => {
    expect(overThreshold({ actualUsd: 13.49, projectedUsd: 14.99, budgetUsd: 15 })).toBe(false);
    expect(overThreshold({ actualUsd: 13.5, projectedUsd: 13.5, budgetUsd: 15 })).toBe(true);
    expect(overThreshold({ actualUsd: 5, projectedUsd: 15, budgetUsd: 15 })).toBe(true);
  });

  it("fails closed: any NaN trips", () => {
    expect(overThreshold({ actualUsd: 5, projectedUsd: 5, budgetUsd: Number.NaN })).toBe(true);
    expect(overThreshold({ actualUsd: 5, projectedUsd: Number.NaN, budgetUsd: 15 })).toBe(true);
    expect(overThreshold({ actualUsd: Number.NaN, projectedUsd: 5, budgetUsd: 15 })).toBe(true);
  });

  it("fails closed on a NaN or missing Durable Object reading", () => {
    const now = PERIOD.startMs + 10 * DAY;
    for (const bad of [Number.NaN, undefined]) {
      const r = { periodToDate: { ...zero, doDurationGbS: bad }, recent: zero, recentMs: 3_600_000, storageBytes: 0,
                  unknownActionTypes: [] } as unknown as Reading;
      expect(overThreshold(evaluateSpend(r, PERIOD, now, 15))).toBe(true);
    }
  });
});
```

(d) `test/meter.test.ts`. First replace its import line with

```ts
import { assertMetronomeMetered, GRAPHQL_URL, LAG_MS, parseUsage, readUsage, RECENT_MS, ROW_LIMIT, USAGE_QUERY,
         usageVariables } from "../src/meter";
```

then replace the two expectations

```ts
    expect(r.periodToDate).toEqual({ workersRequests: 40_000, r2ClassA: 11, r2ClassB: 7 });
    expect(r.recent).toEqual({ workersRequests: 180, r2ClassA: 3_000, r2ClassB: 4_000 });
```

with

```ts
    expect(r.periodToDate).toEqual({ workersRequests: 40_000, r2ClassA: 11, r2ClassB: 7, doRequests: 90_000,
                                     doDurationGbS: 600, doRowsWritten: 150_000 });
    expect(r.recent).toEqual({ workersRequests: 180, r2ClassA: 3_000, r2ClassB: 4_000, doRequests: 1_250,
                               doDurationGbS: 8, doRowsWritten: 2_000 });
```

then insert, immediately before `  it("treats a malformed (non-list) errors field as a failed reading, not as no errors", () => {`:

```ts
  it("queries both Durable Object datasets over the period and the recent window", () => {
    expect(USAGE_QUERY).toContain("doToDate: durableObjectsInvocationsAdaptiveGroups(limit: 10000, filter: { datetime_geq: $start, datetime_leq: $now }) { sum { requests } }");
    expect(USAGE_QUERY).toContain("doRecent: durableObjectsInvocationsAdaptiveGroups(limit: 10000, filter: { datetime_geq: $recentStart, datetime_leq: $recentEnd }) { sum { requests } }");
    expect(USAGE_QUERY).toContain("doPeriodicToDate: durableObjectsPeriodicGroups(limit: 10000, filter: { datetimeMinute_geq: $start, datetimeMinute_leq: $now }) { sum { duration rowsWritten } }");
    expect(USAGE_QUERY).toContain("doPeriodicRecent: durableObjectsPeriodicGroups(limit: 10000, filter: { datetimeMinute_geq: $recentStart, datetimeMinute_leq: $recentEnd }) { sum { duration rowsWritten } }");
  });

  it("sums Durable Object rows across groups, and reads an empty range ([]) as zero", () => {
    const r = usageResponse();
    r.data.viewer.accounts[0].doToDate = [{ sum: { requests: 5 } }, { sum: { requests: 7 } }];
    expect(parseUsage(r).periodToDate.doRequests).toBe(12);
    const empty = parseUsage(usageResponse({ dos: null, dosRecent: null }));
    expect(empty.periodToDate).toMatchObject({ doRequests: 0, doDurationGbS: 0, doRowsWritten: 0 });
    expect(empty.recent).toMatchObject({ doRequests: 0, doDurationGbS: 0, doRowsWritten: 0 });
  });

  it("fails the reading on a missing, truncated or malformed Durable Object dataset", () => {
    type Acct = Record<string, unknown[]>;
    for (const name of ["doToDate", "doRecent", "doPeriodicToDate", "doPeriodicRecent"]) {
      const missing = usageResponse();
      delete (missing.data.viewer.accounts[0] as unknown as Acct)[name];
      expect(() => parseUsage(missing), name).toThrow(new RegExp(`${name} missing`));
      const truncated = usageResponse();
      (truncated.data.viewer.accounts[0] as unknown as Acct)[name] =
        Array.from({ length: ROW_LIMIT }, () => ({ sum: { requests: 1, duration: 1, rowsWritten: 1 } }));
      expect(() => parseUsage(truncated), name).toThrow(/truncated/);
    }
    const cases: [string, (a: Acct) => void][] = [
      ["requests", (a) => { a.doToDate = [{ sum: { requests: -1 } }]; }],
      ["duration NaN", (a) => { a.doPeriodicToDate = [{ sum: { duration: Number.NaN, rowsWritten: 1 } }]; }],
      ["duration missing", (a) => { a.doPeriodicRecent = [{ sum: { rowsWritten: 1 } }]; }],
      ["rowsWritten", (a) => { a.doPeriodicToDate = [{ sum: { duration: 1, rowsWritten: "many" } }]; }],
      ["sum missing", (a) => { a.doRecent = [{}]; }],
    ];
    for (const [what, mutate] of cases) {
      const r = usageResponse();
      mutate(r.data.viewer.accounts[0] as unknown as Acct);
      expect(() => parseUsage(r), what).toThrow(/not a count/);
    }
  });

```

and append at the end of the file:

```ts

describe("assertMetronomeMetered (empty is not zero)", () => {
  it("fails a reading whose recent window has no DO requests or no rows written", () => {
    expect(() => assertMetronomeMetered(parseUsage(usageResponse()))).not.toThrow();
    expect(() => assertMetronomeMetered(parseUsage(usageResponse({ dosRecent: null })))).toThrow(/metronome is on/);
    expect(() => assertMetronomeMetered(parseUsage(usageResponse({ dosRecent: [0, 1, 5] })))).toThrow(/doRequests=0/);
    expect(() => assertMetronomeMetered(parseUsage(usageResponse({ dosRecent: [5, 1, 0] })))).toThrow(/doRowsWritten=0/);
  });
});
```

(e) `test/guard.test.ts`: insert immediately before `describe("guardConfigFromEnv", () => {`:

```ts
describe("guardStep with the metronome on (empty is not zero)", () => {
  const ON = { ...ENV, METRONOME: "on" };

  it("an empty recent Durable Object window is a failed reading while METRONOME is on, and fine while off", async () => {
    const empty = usageResponse({ dosRecent: null });
    const on = new MemoryBucket();
    await step(on, cloud({ usage: empty }), T0, ON);
    expect(on.json(GUARD_KEY)).toMatchObject({ last_success: null, last_error: expect.stringMatching(/metronome is on/) });
    const off = new MemoryBucket();
    await step(off, cloud({ usage: empty }), T0, ENV);
    expect(off.json(GUARD_KEY)).toMatchObject({ last_success: new Date(T0).toISOString(), last_error: null });
  });

  it("only the exact string \"on\" counts", () => {
    expect(guardConfigFromEnv(ON).metronomeOn).toBe(true);
    for (const v of [undefined, "off", "On", "on ", "1", "true"]) {
      expect(guardConfigFromEnv({ ...ENV, METRONOME: v }).metronomeOn).toBe(false);
    }
  });

  it("stores all seven meters in guard.json", async () => {
    const bucket = new MemoryBucket();
    await step(bucket, cloud(), T0, ON);
    const ev = bucket.json(GUARD_KEY).evaluation;
    expect(Object.keys(ev.period_to_date).sort()).toEqual(["doDurationGbS", "doRequests", "doRowsWritten", "r2ClassA",
                                                          "r2ClassB", "r2StorageGbMonth", "workersRequests"]);
    expect(ev.period_to_date).toMatchObject({ doRequests: 90_000, doDurationGbS: 600, doRowsWritten: 150_000 });
  });
});

```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/pricing.test.ts test/meter.test.ts test/guard.test.ts`
Expected: FAIL. Among the failures: `PRICES.meters.doRequests` is undefined, `assertMetronomeMetered is not a function`, `USAGE_QUERY` lacks `doToDate`, and `metronomeOn` is undefined.

- [ ] **Step 3: Implement `src/pricing.ts`** (four edits)

Replace the file's opening doc comment with:

```ts
/** The guard's price table and spend arithmetic (spec "Cost guard"). Prices
 * and allowances are Cloudflare's published ones (Workers Paid, R2 Standard),
 * checked 2026-10-11; the Durable Objects meters (Workers Paid) were checked
 * 2026-10-14 on developers.cloudflare.com/durable-objects/platform/pricing/
 * (metronome spec, "Cost guard: Durable Object meters"). The $5 Workers Paid
 * base is part of every total, so monthly_budget_usd includes it. Not metered,
 * each bounded by design instead: Workers CPU time (the dataset exposes it only
 * as percentiles), DO rows read and DO stored bytes (the metronome's fixed key
 * set and capped invocations; `durableObjectsStorageGroups` returns no rows for
 * this account). */
```

Replace

```ts
export type Meter = "workersRequests" | "r2ClassA" | "r2ClassB" | "r2StorageGbMonth";
export const METERS: Meter[] = ["workersRequests", "r2ClassA", "r2ClassB", "r2StorageGbMonth"];
```

with

```ts
export type Meter = "workersRequests" | "r2ClassA" | "r2ClassB" | "r2StorageGbMonth" | "doRequests" | "doDurationGbS" |
  "doRowsWritten";
export const METERS: Meter[] = ["workersRequests", "r2ClassA", "r2ClassB", "r2StorageGbMonth", "doRequests",
                                "doDurationGbS", "doRowsWritten"];
```

Replace

```ts
    r2StorageGbMonth: { included: 10, usdPerUnit: 0.015 },
  },
```

with

```ts
    r2StorageGbMonth: { included: 10, usdPerUnit: 0.015 },
    // Durable Objects (requests include RPC sessions and alarm invocations).
    doRequests: { included: 1_000_000, usdPerUnit: 0.15 / 1_000_000 },
    doDurationGbS: { included: 400_000, usdPerUnit: 12.5 / 1_000_000 },
    doRowsWritten: { included: 50_000_000, usdPerUnit: 1.0 / 1_000_000 },
  },
```

Replace the `OpCounts` interface (with its doc comment) with:

```ts
/** Counts from the analytics read (R2 storage is reported separately). */
export interface OpCounts {
  workersRequests: number;
  r2ClassA: number;
  r2ClassB: number;
  doRequests: number;
  /** GB-s (the dataset's `duration`: activeTime x 0.128 GB, measured 2026-10-14). */
  doDurationGbS: number;
  doRowsWritten: number;
}
```

In `evaluateSpend`, replace the `periodToDate` and `projected` literals with:

```ts
  const periodToDate: Usage = {
    workersRequests: r.periodToDate.workersRequests,
    r2ClassA: r.periodToDate.r2ClassA,
    r2ClassB: r.periodToDate.r2ClassB,
    r2StorageGbMonth: (gb * elapsedMs) / STORAGE_MONTH_MS,
    doRequests: r.periodToDate.doRequests,
    doDurationGbS: r.periodToDate.doDurationGbS,
    doRowsWritten: r.periodToDate.doRowsWritten,
  };
  const projected: Usage = {
    workersRequests: periodToDate.workersRequests + rate("workersRequests") * remainingMs,
    r2ClassA: periodToDate.r2ClassA + rate("r2ClassA") * remainingMs,
    r2ClassB: periodToDate.r2ClassB + rate("r2ClassB") * remainingMs,
    r2StorageGbMonth: (gb * (period.endMs - period.startMs)) / STORAGE_MONTH_MS,
    doRequests: periodToDate.doRequests + rate("doRequests") * remainingMs,
    doDurationGbS: periodToDate.doDurationGbS + rate("doDurationGbS") * remainingMs,
    doRowsWritten: periodToDate.doRowsWritten + rate("doRowsWritten") * remainingMs,
  };
```

- [ ] **Step 4: Implement `src/meter.ts`** (six edits)

Replace the file's opening doc comment with:

```ts
/** Usage read from Cloudflare's GraphQL Analytics API, account-scoped (all
 * Workers, buckets and Durable Objects), with an Account Analytics: Read token.
 * The adaptive datasets are sampled estimates; operations lag ~1-2 min and
 * storage ~45 min (measured 2026-10-11), the Durable Object datasets under
 * 1 min (measured 2026-10-14), so the recent window ends LAG_MS before now. Any
 * failure -- HTTP, GraphQL errors, a missing account, a truncated result --
 * throws: the guard counts it as a failed reading. */
```

Replace the doc comment above `USAGE_QUERY` with:

```ts
/** One query covers the whole period to date. Each dataset accepts a range of up
 * to 32 days (maxDuration 2,764,800 s) within the last 90 days (notOlderThan
 * 7,776,000 s), and a billing period is at most 31 days. Measured for this
 * account 2026-10-12, when this exact query (`.000Z` timestamps, `$account:
 * string!`) succeeded over 31- and 32-day ranges. The Durable Object datasets
 * (`durableObjectsInvocationsAdaptiveGroups` filtered on `datetime`,
 * `durableObjectsPeriodicGroups` on `datetimeMinute`) were measured 2026-10-14:
 * 31- and 32-day ranges accepted, totals matching the alarm probe's counts, and
 * a range with no DO activity returns `[]` (indistinguishable from zero: see
 * assertMetronomeMetered). `sum.requests` counts every invocation type and
 * status (alarms, RPC); `sum.duration` is GB-s. */
```

In `USAGE_QUERY`, after the `storage: r2StorageAdaptiveGroups(...)` line, add these four lines (same indentation):

```
      doToDate: durableObjectsInvocationsAdaptiveGroups(limit: ${ROW_LIMIT}, filter: { datetime_geq: $start, datetime_leq: $now }) { sum { requests } }
      doRecent: durableObjectsInvocationsAdaptiveGroups(limit: ${ROW_LIMIT}, filter: { datetime_geq: $recentStart, datetime_leq: $recentEnd }) { sum { requests } }
      doPeriodicToDate: durableObjectsPeriodicGroups(limit: ${ROW_LIMIT}, filter: { datetimeMinute_geq: $start, datetimeMinute_leq: $now }) { sum { duration rowsWritten } }
      doPeriodicRecent: durableObjectsPeriodicGroups(limit: ${ROW_LIMIT}, filter: { datetimeMinute_geq: $recentStart, datetimeMinute_leq: $recentEnd }) { sum { duration rowsWritten } }
```

Replace

```ts
type Rows = { sum?: { requests?: unknown }; max?: Record<string, unknown>; dimensions?: Record<string, unknown> }[];
```

with

```ts
type Rows = { sum?: Record<string, unknown>; max?: Record<string, unknown>; dimensions?: Record<string, unknown> }[];
```

Replace

```ts
function sumRequests(rs: Rows, what: string): number {
  return rs.reduce((t, r) => t + count(r?.sum?.requests, what), 0);
}
```

with

```ts
function sumField(rs: Rows, field: string, what: string): number {
  return rs.reduce((t, r) => t + count(r?.sum?.[field], what), 0);
}

function sumRequests(rs: Rows, what: string): number {
  return sumField(rs, "requests", what);
}

function doCounts(acct: Record<string, unknown>, invocations: string, periodic: string):
    Pick<OpCounts, "doRequests" | "doDurationGbS" | "doRowsWritten"> {
  const p = rows(acct, periodic);
  return { doRequests: sumRequests(rows(acct, invocations), "durable object requests"),
           doDurationGbS: sumField(p, "duration", "durable object duration"),
           doRowsWritten: sumField(p, "rowsWritten", "durable object rowsWritten") };
}
```

In `parseUsage`, replace

```ts
  const periodToDate = { workersRequests: sumRequests(rows(acct, "workersToDate"), "workers requests"),
                         ...r2Counts(rows(acct, "r2ToDate"), unknown) };
  const recent = { workersRequests: sumRequests(rows(acct, "workersRecent"), "workers requests"),
                   ...r2Counts(rows(acct, "r2Recent"), unknown) };
```

with

```ts
  const periodToDate = { workersRequests: sumRequests(rows(acct, "workersToDate"), "workers requests"),
                         ...r2Counts(rows(acct, "r2ToDate"), unknown),
                         ...doCounts(acct, "doToDate", "doPeriodicToDate") };
  const recent = { workersRequests: sumRequests(rows(acct, "workersRecent"), "workers requests"),
                   ...r2Counts(rows(acct, "r2Recent"), unknown),
                   ...doCounts(acct, "doRecent", "doPeriodicRecent") };
```

Insert immediately before `export async function readUsage(`:

```ts
/** Empty is not zero: a range with no Durable Object activity reads as `[]`.
 * While the metronome is on, cron renews it every minute and every renew writes
 * at least one row (`stalls`), so a recent window with no DO requests or no rows
 * written cannot be true: the dataset is not serving it, and the reading fails
 * rather than price the meters at zero. A reading taken within LAG_MS of
 * METRONOME being flipped on fails this way, and guard.json shows it until the
 * next evaluation (<= ~20 min); harmless, since the blind rule needs 6 h. */
export function assertMetronomeMetered(r: Reading): void {
  if (r.recent.doRequests === 0 || r.recent.doRowsWritten === 0) {
    throw new Error(`analytics: the metronome is on but the recent window reads doRequests=${r.recent.doRequests}, ` +
                    `doRowsWritten=${r.recent.doRowsWritten}: the Durable Object datasets are not serving it`);
  }
}

```

- [ ] **Step 5: Implement `src/latch.ts`** (two edits)

Replace

```ts
import { type Evaluation, overThreshold, PRICES, type Usage } from "./pricing";
```

with

```ts
import { type Evaluation, type Meter, METERS, overThreshold, PRICES, type Usage } from "./pricing";
```

In `stored()`, replace

```ts
  const usage = (u: Usage): Usage => ({ workersRequests: Math.round(u.workersRequests), r2ClassA: Math.round(u.r2ClassA),
                                        r2ClassB: Math.round(u.r2ClassB), r2StorageGbMonth: r4(u.r2StorageGbMonth) });
```

with

```ts
  // Every meter, so guard.json shows all of them: counts rounded to integers,
  // the fractional meters (GB-month, GB-s) to 4 places.
  const fractional: ReadonlySet<Meter> = new Set<Meter>(["r2StorageGbMonth", "doDurationGbS"]);
  const usage = (u: Usage): Usage =>
    Object.fromEntries(METERS.map((m) => [m, fractional.has(m) ? r4(u[m]) : Math.round(u[m])])) as Usage;
```

- [ ] **Step 6: Declare the switch in `src/clock.ts`, and implement `src/guard.ts`** (one edit, then five)

In `src/clock.ts`, in `ClockEnv`, replace

```ts
  LEAD_FLOOR_HOURS?: string;
}
```

with

```ts
  LEAD_FLOOR_HOURS?: string;
  /** The metronome's rollback switch: only the exact string "on" enables it; anything else is off. */
  METRONOME?: string;
}
```

This is its only declaration: `AntennaEnv` extends `ClockEnv`, and the guard reads it through `Pick<ClockEnv, "METRONOME">`.

In `src/guard.ts`, replace

```ts
import { type BucketLike, createJson, type JsonRead, putJson, readJsonDoc } from "./bucket";
```

with

```ts
import { type BucketLike, createJson, type JsonRead, putJson, readJsonDoc } from "./bucket";
import type { ClockEnv } from "./clock";
```

Replace

```ts
export function guardConfigFromEnv(env: GuardEnv): GuardConfig {
```

with

```ts
export function guardConfigFromEnv(env: GuardEnv & Pick<ClockEnv, "METRONOME">): GuardConfig {
```

In `GuardConfig`, replace

```ts
  /** Why the kill switch cannot be reconciled. */
  wafProblems: string[];
}
```

with

```ts
  /** Why the kill switch cannot be reconciled. */
  wafProblems: string[];
  /** METRONOME is exactly "on": an empty Durable Object reading is a failed one. */
  metronomeOn: boolean;
}
```

In `guardConfigFromEnv`, replace

```ts
    accountId, zoneId, analyticsToken, wafToken, meterProblems, wafProblems,
  };
```

with

```ts
    accountId, zoneId, analyticsToken, wafToken, meterProblems, wafProblems,
    metronomeOn: env.METRONOME === "on",
  };
```

Replace the import `import { readUsage } from "./meter";` with `import { assertMetronomeMetered, readUsage } from "./meter";`. Then, in `guardStep`, replace

```ts
        const reading = await readUsage(deps.fetch, { accountId: cfg.accountId, token: cfg.analyticsToken }, p, nowMs);
```

with

```ts
        const reading = await readUsage(deps.fetch, { accountId: cfg.accountId, token: cfg.analyticsToken }, p, nowMs);
        if (cfg.metronomeOn) assertMetronomeMetered(reading);
```

(It sits inside the existing `try`, so a throw is a failed reading, the same as any other analytics failure.)

- [ ] **Step 7: Run everything**

Run: `cd antenna && npm test && npm run typecheck`
Expected: `Tests  252 passed (252)`, tsc silent.

- [ ] **Step 8: Commit**

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/antenna-metronome
git -C "$W" add antenna/src/pricing.ts antenna/src/meter.ts antenna/src/latch.ts antenna/src/guard.ts antenna/src/clock.ts \
                antenna/test/support.ts antenna/test/pricing.test.ts antenna/test/meter.test.ts antenna/test/guard.test.ts \
                antenna/test/latch.test.ts antenna/test/conditions.test.ts
git -C "$W" commit -m "feat(antenna): the cost guard prices Durable Object requests, duration and rows written"
```

---
### Task 3: `metronome-core.ts` — lease, ordering, expiry, targets, caps, stalls, state

**Model hint:** opus (the lease and acceptance logic: strict surface)

The spec's pure module (J2). It has no IO and no clock of its own: every function takes `nowMs`. It covers these spec sections:

- "The lease": validation, ordering, expiry;
- "Metronome (the DO)": the stored key set, alarm-confirmed ticks, live, the re-arm target;
- "Spend bounds": the rolling windows;
- "Fallback (new)": cron's triggers (a)–(c), as the pure `fallbackReason`.

`GRID_D` moves to `grid.ts`, so this module never imports `clock.ts`; `clock.ts` will import this module in Task 7.

**Files:**
- Create: `src/metronome-core.ts`, `test/metronome-core.test.ts`
- Modify: `src/grid.ts` (add `GRID_D`), `src/clock.ts` (import and re-export `GRID_D` from `grid.ts`)

**Interfaces:**
- Consumes: `grid.ts` `Grid`, `gridOf`, `Horizon`, `indexAt`, `startMs`; `playlist.ts` `FallbackIndex`, `isOffair`, `PlaylistConfig`.
- Produces (`src/metronome-core.ts`), used by Tasks 4–7:
  - Constants: `METRONOME_LEASE_MS` (900_000), `METRONOME_STALE_MS` (30_000), `STALLS_FALLBACK` (2), `MAX_DO_PUTS_PER_MINUTE` (10), `MAX_ALARMS_PER_MINUTE` (12), `CAP_WINDOW_MS` (60_000), `DO_PUT_TIMEOUT_MS` (5_000), `RENEW_TIMEOUT_MS` (15_000), `ALARM_SLACK_MS` (25), `LATE_LOG_MS` (2_000), `METRONOME_NAME` ("metronome").
  - Types:
    - `PlayLease { kind: "play"; verdictAt; validUntil; blocked: boolean; horizon: Horizon; fallback: FallbackIndex | null }`;
    - `HoldLease { kind: "hold"; verdictAt; validUntil }`;
    - `Lease = PlayLease | HoldLease`;
    - `StoredLease = Lease & { expiresAt: number }`;
    - `LeaseKind = "play" | "blocked" | "hold" | "none"`;
    - `MetronomeStatus` (the spec's, field for field);
    - `MetronomeClient { renew(lease: Lease | null): Promise<MetronomeStatus> }`;
    - `MetronomeState`;
    - `STORAGE_KEYS` and `StorageKey`.
  - Functions:
    - `validateLease(raw)`;
    - `storedLease(lease, nowMs)`, `expired(l, nowMs)`, `currentLease(l, nowMs)`, `leaseKind(l, nowMs)`;
    - `decideLease(current, incoming, nowMs)`, `isLive(l, nowMs, cfg)`;
    - `nextTarget(g, afterMs)`;
    - `inWindow(times, nowMs)`, `capAllows(times, nowMs, cap)`, `recordTime(times, nowMs, keep)`;
    - `stalledFor(wasLive, lastAlarmGoodAt, playSince, nowMs)`, `nextStalls(prev, stalledMs)`;
    - `parseStoredLease(raw)`, `serializeLease(l)`, `readState(raw)`, `stateChanges(prev, next)`, `EMPTY_STATE`;
    - `playLease(verdictAt, issuedAt, blocked, horizon, fallback)`, `holdLease(verdictAt, issuedAt)`;
    - `fallbackReason(sent, { status } | { error })`.
  - `grid.ts` exports `GRID_D = 10.24`; `clock.ts` still exports `GRID_D`.

- [ ] **Step 1: Write the failing test** — `test/metronome-core.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { gridOf } from "../src/grid";
import { ALARM_SLACK_MS, capAllows, currentLease, decideLease, EMPTY_STATE, expired, fallbackReason, holdLease,
         inWindow, isLive, type Lease, leaseKind, METRONOME_LEASE_MS, type MetronomeStatus, nextStalls, nextTarget,
         parseStoredLease, playLease, readState, recordTime, serializeLease, stalledFor, stateChanges, STORAGE_KEYS,
         storedLease, validateLease } from "../src/metronome-core";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const T = E + 1_000 * D; // a moment well inside the epoch
const CFG = { window: 16, grace: 3, offairAfterMs: 86_400_000, lookahead: 12, holdBack: 12 };
const H = { epoch_id: "e1", epoch: new Date(E).toISOString(), d: 10.24, first: 0, last: 1_000_000,
            published_at: new Date(E).toISOString(), container: "adts", fallback_version: "v1" };
const FB = { len: 7, notice: "fallback/v1/notice.aac" };
const play = (verdictAt: number, blocked = false, over: Record<string, unknown> = {}) =>
  ({ kind: "play", verdictAt, validUntil: verdictAt + METRONOME_LEASE_MS, blocked, horizon: H, fallback: FB, ...over });
const status = (s: Partial<MetronomeStatus>): MetronomeStatus =>
  ({ applied: "accepted", lease: "play", wrote: true, lastAlarmGoodAt: T, stalledMs: 0, stalls: 0, leaseVerdictAt: T, ...s });

describe("validateLease", () => {
  it("accepts a well-formed play or hold lease", () => {
    expect(validateLease(play(T))).toEqual({ ok: true, lease: play(T) });
    expect(validateLease({ kind: "hold", verdictAt: T, validUntil: T + 1, extra: 1 }))
      .toEqual({ ok: true, lease: { kind: "hold", verdictAt: T, validUntil: T + 1 } });
  });

  it("rejects every invalid shape", () => {
    const bad: [string, unknown][] = [
      ["null", null], ["array", []], ["string", "play"],
      ["kind", play(T, false, { kind: "go" })],
      ["blocked missing", play(T, false, { blocked: undefined })],
      ["blocked string", play(T, false, { blocked: "false" })],
      ["verdictAt NaN", play(T, false, { verdictAt: Number.NaN })],
      ["verdictAt missing", { kind: "hold", validUntil: T }],
      ["validUntil Infinity", play(T, false, { validUntil: Number.POSITIVE_INFINITY })],
      ["horizon missing", play(T, false, { horizon: undefined })],
      ["d 10.25", play(T, false, { horizon: { ...H, d: 10.25 } })],
      ["d string", play(T, false, { horizon: { ...H, d: "10.24" } })],
      ["epoch unparseable", play(T, false, { horizon: { ...H, epoch: "nonsense" } })],
      ["epoch number", play(T, false, { horizon: { ...H, epoch: E } })],
      ["first float", play(T, false, { horizon: { ...H, first: 0.5 } })],
      ["last string", play(T, false, { horizon: { ...H, last: "9" } })],
      ["epoch_id number", play(T, false, { horizon: { ...H, epoch_id: 7 } })],
      ["fallback_version number", play(T, false, { horizon: { ...H, fallback_version: 1 } })],
    ];
    for (const [what, raw] of bad) expect([what, validateLease(raw).ok]).toEqual([what, false]);
  });

  it("a malformed fallback becomes null, never an invalid lease", () => {
    for (const fallback of [{ len: "7", notice: "n" }, { len: 7 }, "x", [], { len: Number.NaN, notice: "n" }]) {
      const v = validateLease(play(T, false, { fallback }));
      expect(v.ok && v.lease.kind === "play" && v.lease.fallback).toBeNull();
    }
    const v = validateLease(play(T, false, { fallback: null }));
    expect(v.ok && v.lease.kind === "play" && v.lease.fallback).toBeNull();
  });
});

describe("expiry", () => {
  it("expiresAt = min(validUntil, now + 15 min): a far-future validUntil still expires at 15 min", () => {
    expect(storedLease({ kind: "hold", verdictAt: T, validUntil: T + 60_000 }, T).expiresAt).toBe(T + 60_000);
    expect(storedLease({ kind: "hold", verdictAt: T, validUntil: T + 86_400_000 }, T).expiresAt).toBe(T + METRONOME_LEASE_MS);
  });

  it("is written negated: NaN or missing is expired", () => {
    expect(expired({ expiresAt: T + 1 }, T)).toBe(false);
    expect(expired({ expiresAt: T }, T)).toBe(true);
    expect(expired({ expiresAt: Number.NaN }, T)).toBe(true);
    expect(expired({} as { expiresAt: number }, T)).toBe(true);
    expect(currentLease({ ...(play(T) as Lease), expiresAt: Number.NaN }, T)).toBeNull();
  });

  it("names the lease kind, none when expired", () => {
    const s = (l: Record<string, unknown>) => storedLease(l as unknown as Lease, T);
    expect(leaseKind(s(play(T)), T)).toBe("play");
    expect(leaseKind(s(play(T, true)), T)).toBe("blocked");
    expect(leaseKind(s({ kind: "hold", verdictAt: T, validUntil: T + 1 }), T)).toBe("hold");
    expect(leaseKind(s(play(T)), T + METRONOME_LEASE_MS)).toBe("none");
    expect(leaseKind(null, T)).toBe("none");
  });
});

describe("decideLease (ordering)", () => {
  const cur = storedLease(play(T) as Lease, T);
  it("supersedes an unblocked play lease whose verdictAt is not strictly newer, equal included", () => {
    expect(decideLease(cur, play(T - 1) as Lease, T)).toBe("superseded");
    expect(decideLease(cur, play(T) as Lease, T)).toBe("superseded");
    expect(decideLease(cur, play(T + 1) as Lease, T)).toBe("accepted");
  });

  it("accepts blocked play and hold whatever their verdictAt (blocking is fail-closed)", () => {
    expect(decideLease(cur, play(T - 60_000, true) as Lease, T)).toBe("accepted");
    expect(decideLease(cur, holdLease(T - 60_000, T), T)).toBe("accepted");
  });

  it("a future-dated verdictAt (a cron clock running ahead) never keeps a blocked lease out", () => {
    const ahead = storedLease(play(T + 3_600_000) as Lease, T); // an hour ahead
    expect(decideLease(ahead, play(T + 60_000) as Lease, T)).toBe("superseded");
    expect(decideLease(ahead, play(T + 60_000, true) as Lease, T)).toBe("accepted");
    expect(decideLease(ahead, holdLease(T + 60_000, T), T)).toBe("accepted");
    expect(storedLease(play(T + 3_600_000) as Lease, T).expiresAt).toBe(T + METRONOME_LEASE_MS); // the DO's clock
  });

  it("an older unblocked lease cannot supersede a newer blocked one, but is accepted with no current lease", () => {
    const blocked = storedLease(play(T, true) as Lease, T);
    expect(decideLease(blocked, play(T - 1) as Lease, T)).toBe("superseded");
    expect(decideLease(null, play(T - 1) as Lease, T)).toBe("accepted");
    expect(decideLease(cur, play(T - 1) as Lease, T + METRONOME_LEASE_MS)).toBe("accepted"); // current expired
  });
});

describe("isLive", () => {
  it("only an unexpired unblocked play lease that is not off air", () => {
    const s = (l: Record<string, unknown>) => storedLease(l as unknown as Lease, T);
    expect(isLive(s(play(T)), T, CFG)).toBe(true);
    expect(isLive(s(play(T, true)), T, CFG)).toBe(false);
    expect(isLive(s({ kind: "hold", verdictAt: T, validUntil: T + 1 }), T, CFG)).toBe(false);
    expect(isLive(s(play(T)), T + METRONOME_LEASE_MS, CFG)).toBe(false);
    // a horizon more than offairAfterMs stale is off air
    const late = E + 11 * D + CFG.offairAfterMs + 1;
    const stale = storedLease(play(late, false, { horizon: { ...H, last: 10 } }) as unknown as Lease, late);
    expect(isLive(stale, late, CFG)).toBe(false);
    expect(isLive(stale, late - 2, CFG)).toBe(true);
  });
});

describe("nextTarget", () => {
  const g = gridOf(H);
  it("is the first boundary + 25 ms strictly after the given time", () => {
    expect(nextTarget(g, E + 5 * D)).toBe(E + 5 * D + ALARM_SLACK_MS);
    expect(nextTarget(g, E + 5 * D + 24)).toBe(E + 5 * D + ALARM_SLACK_MS);
    expect(nextTarget(g, E + 5 * D + 25)).toBe(E + 6 * D + ALARM_SLACK_MS); // strictly after
    expect(nextTarget(g, E + 5 * D + 9_000)).toBe(E + 6 * D + ALARM_SLACK_MS);
  });

  it("skips missed boundaries instead of bursting", () => {
    expect(nextTarget(g, E + 50 * D + 100)).toBe(E + 51 * D + ALARM_SLACK_MS);
  });
});

describe("rolling windows", () => {
  it("just over 60 s after the oldest timestamp is allowed, just under is not", () => {
    const ts = Array.from({ length: 10 }, (_, i) => T + i * 1_000);
    expect(capAllows(ts, T + 59_999, 10)).toBe(false);
    expect(capAllows(ts, T + 60_001, 10)).toBe(true);
    expect(inWindow(ts, T + 60_001)).toHaveLength(9);
  });

  it("records into a fixed-size list", () => {
    let ts: number[] = [];
    for (let i = 0; i < 30; i++) ts = recordTime(ts, T + i, 12);
    expect(ts).toHaveLength(12);
    expect(ts.at(-1)).toBe(T + 29);
    expect(recordTime([T - 120_000], T, 12)).toEqual([T]); // old entries drop out
  });
});

describe("stalls", () => {
  it("measures from the later of the last alarm tick and playSince, and only while live", () => {
    expect(stalledFor(true, T - 40_000, T - 10_000, T)).toBe(10_000);
    expect(stalledFor(true, T - 5_000, T - 90_000, T)).toBe(5_000);
    expect(stalledFor(true, null, T - 45_000, T)).toBe(45_000);
    expect(stalledFor(false, T - 600_000, null, T)).toBe(0);
  });

  it("counts consecutive stalls over 30 s and resets otherwise", () => {
    expect(nextStalls(0, 30_001)).toBe(1);
    expect(nextStalls(1, 31_000)).toBe(2);
    expect(nextStalls(2, 30_000)).toBe(0);
  });
});

describe("stored state", () => {
  it("round-trips a lease and reads anything else as empty defaults", () => {
    const l = storedLease(play(T) as Lease, T);
    const { state, leaseInvalid } = readState({ lease: serializeLease(l), stalls: 2, putTimes: [1, "x", 3],
                                                lastBody: "#EXTM3U\n", lastTarget: Number.NaN });
    expect(leaseInvalid).toBeNull();
    expect(state).toEqual({ ...EMPTY_STATE, lease: l, stalls: 2, putTimes: [1, 3], lastBody: "#EXTM3U\n" });
  });

  it("an unparseable or invalid stored lease is invalid (no lease)", () => {
    expect(parseStoredLease("{nope").invalid).toMatch(/not JSON/);
    expect(parseStoredLease(42).invalid).toMatch(/not a string/);
    expect(parseStoredLease(JSON.stringify({ ...play(T), horizon: { ...H, d: 1 }, expiresAt: T })).invalid).toMatch(/d/);
    expect(parseStoredLease(undefined)).toEqual({ lease: null, invalid: null });
  });

  it("a stored lease whose expiresAt is missing loads as expired", () => {
    const { lease } = parseStoredLease(JSON.stringify(play(T)));
    expect(lease).not.toBeNull();
    expect(currentLease(lease, T)).toBeNull();
  });

  it("writes only the keys that changed, a removed lease as undefined", () => {
    const l = storedLease(play(T) as Lease, T);
    const before = { ...EMPTY_STATE, lease: l, stalls: 1 };
    expect(stateChanges(before, { ...before, stalls: 0, lastBody: "b" })).toEqual({ stalls: 0, lastBody: "b" });
    expect(stateChanges(before, { ...before, lease: null })).toEqual({ lease: undefined });
    expect(Object.keys(stateChanges(EMPTY_STATE, { ...before, lastTarget: 1 })).sort()).toEqual(["lastTarget", "lease", "stalls"]);
  });

  it("the key set is fixed", () => {
    expect([...STORAGE_KEYS].sort()).toEqual(["alarmTimes", "lastAlarmGoodAt", "lastBody", "lastTarget", "lease",
                                              "playSince", "putTimes", "stalls"]);
    expect(Object.keys(EMPTY_STATE).sort()).toEqual([...STORAGE_KEYS].sort());
  });
});

describe("lease builders", () => {
  it("issue a lease valid for 15 min from issue, ordered by verdictAt", () => {
    expect(playLease(T - 3_000, T, true, H, FB)).toEqual({ kind: "play", verdictAt: T - 3_000,
                                                          validUntil: T + METRONOME_LEASE_MS, blocked: true,
                                                          horizon: H, fallback: FB });
    expect(holdLease(T - 3_000, T)).toEqual({ kind: "hold", verdictAt: T - 3_000, validUntil: T + METRONOME_LEASE_MS });
  });
});

describe("fallbackReason (cron's triggers)", () => {
  const p = playLease(T, T, false, H, FB);
  const b = playLease(T, T, true, H, FB);
  const hold = holdLease(T, T);
  it("(a) renew threw or timed out", () => {
    expect(fallbackReason(p, { error: "renew timed out after 15000 ms" })).toMatch(/renew failed: renew timed out/);
    expect(fallbackReason(null, { error: "boom" })).toMatch(/boom/);
  });

  it("(b) a play lease not accepted, or its write failed, unless superseded", () => {
    for (const lease of [p, b]) {
      expect(fallbackReason(lease, { status: status({}) })).toBeNull();
      expect(fallbackReason(lease, { status: status({ wrote: null }) })).toBeNull(); // cap, identical, nothing to build
      expect(fallbackReason(lease, { status: status({ wrote: false }) })).toMatch(/wrote=false/);
      expect(fallbackReason(lease, { status: status({ applied: "invalid", wrote: null }) })).toMatch(/invalid/);
      expect(fallbackReason(lease, { status: status({ applied: "off", wrote: null }) })).toMatch(/off/);
      expect(fallbackReason(lease, { status: status({ applied: "superseded", wrote: false }) })).toBeNull();
    }
    // (b) is about play leases only.
    expect(fallbackReason(hold, { status: status({ applied: "off", wrote: null }) })).toBeNull();
    expect(fallbackReason(null, { status: status({ applied: null, wrote: false }) })).toBeNull();
  });

  it("(c) two consecutive stalls; a single stall is not a trigger", () => {
    expect(fallbackReason(p, { status: status({ stalls: 1, stalledMs: 40_000 }) })).toBeNull();
    expect(fallbackReason(p, { status: status({ stalls: 2, stalledMs: 40_000 }) })).toMatch(/stalled on 2/);
    expect(fallbackReason(null, { status: status({ applied: null, stalls: 3 }) })).toMatch(/stalled/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/metronome-core.test.ts`
Expected: FAIL. `../src/metronome-core` cannot be resolved.

- [ ] **Step 3: Move `GRID_D` to `grid.ts`**

In `src/grid.ts`, insert immediately before `export interface Grid {`:

```ts
/** The grid constant transmitter always writes: 441 * 1024 / 44100 s. A
 * horizon with any other d is refused (the clock's spend bounds) and is never
 * part of a metronome lease. */
export const GRID_D = 10.24;

```

In `src/clock.ts`, replace

```ts
import { type Grid, type Horizon, gridOf, indexAt, startMs } from "./grid";
```

with

```ts
import { GRID_D, type Grid, type Horizon, gridOf, indexAt, startMs } from "./grid";
```

and replace

```ts
/** The grid constant transmitter always writes: 441 * 1024 / 44100 s. */
export const GRID_D = 10.24;
```

with

```ts
export { GRID_D };
```

- [ ] **Step 4: Create `src/metronome-core.ts`**

```ts
/** The metronome's pure logic (metronome spec, docs/superpowers/specs/
 * 2026-10-14-antenna-metronome-design.md): the lease, its validation, ordering
 * and expiry, the alarm target, the rolling caps, the stall count, the stored
 * state's fixed key set, and the cron side's fallback decision. No IO and no
 * clock of its own: every function takes `nowMs`. metronome-engine.ts
 * sequences these over storage, alarms and R2; metronome.ts is the Durable
 * Object around the engine. */

import { GRID_D, type Grid, gridOf, type Horizon, indexAt, startMs } from "./grid";
import { type FallbackIndex, isOffair, type PlaylistConfig } from "./playlist";

/** Lease lifetime (Decision 3): a lease the DO accepts plays for at most this long. */
export const METRONOME_LEASE_MS = 15 * 60_000;
/** A renew that finds no alarm-confirmed tick for longer than this counts a stall. */
export const METRONOME_STALE_MS = 30_000;
/** Cron falls back at this many consecutive stalls (trigger c). */
export const STALLS_FALLBACK = 2;
/** At most this many DO playlist PUTs in a rolling CAP_WINDOW_MS, renew's included. */
export const MAX_DO_PUTS_PER_MINUTE = 10;
/** At most this many alarm() invocations in a rolling CAP_WINDOW_MS. */
export const MAX_ALARMS_PER_MINUTE = 12;
export const CAP_WINDOW_MS = 60_000;
/** Each DO R2 PUT is bounded by this (Promise.race, as alerts.ts bounds its sends). */
export const DO_PUT_TIMEOUT_MS = 5_000;
/** Cron's bound on one renew RPC: over two PUT timeouts, plus slack. */
export const RENEW_TIMEOUT_MS = 15_000;
/** Alarms aim this far past a boundary, as the cron loop sleeps to it. */
export const ALARM_SLACK_MS = 25;
/** An alarm later than this past its target logs metronome-late. */
export const LATE_LOG_MS = 2_000;
/** The single instance: cron addresses it as idFromName(METRONOME_NAME). */
export const METRONOME_NAME = "metronome";

export interface PlayLease {
  kind: "play";
  /** When the issuing cron's guard step began (its state reads started): the ordering key. */
  verdictAt: number;
  /** Date.now() at issue + METRONOME_LEASE_MS. Never trusted alone: see storedLease. */
  validUntil: number;
  blocked: boolean;
  horizon: Horizon;
  fallback: FallbackIndex | null;
}

export interface HoldLease {
  kind: "hold";
  verdictAt: number;
  validUntil: number;
}

export type Lease = PlayLease | HoldLease;

/** A validated lease as the DO stores it, with the expiry it computed itself. */
export type StoredLease = Lease & { expiresAt: number };

export type LeaseKind = "play" | "blocked" | "hold" | "none";

/** What renew() returns to cron (the spec's MetronomeStatus). */
export interface MetronomeStatus {
  /** null: renew(null). */
  applied: "accepted" | "superseded" | "invalid" | "off" | null;
  /** The DO's lease after this call; "none" = absent or expired (and always when off). */
  lease: LeaseKind;
  /** This call's write succeeded; false = it failed or timed out; null = no write due
   * (no play lease, identical body, cap, nothing to build). */
  wrote: boolean | null;
  lastAlarmGoodAt: number | null;
  /** As it stood before this call (0 unless the stored lease's playlist was live). */
  stalledMs: number;
  /** Consecutive renews that found stalledMs > METRONOME_STALE_MS; cron falls back at >= 2. */
  stalls: number;
  leaseVerdictAt: number | null;
}

/** What cron calls: the DO's renew over RPC, bounded (metronome.ts metronomeClient). */
export interface MetronomeClient {
  renew(lease: Lease | null): Promise<MetronomeStatus>;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function horizonProblem(h: unknown): string | null {
  if (!isObj(h)) return "horizon is not an object";
  if (h.d !== GRID_D) return `horizon.d is ${JSON.stringify(h.d)}, not ${GRID_D}`;
  if (typeof h.epoch_id !== "string") return "horizon.epoch_id is not a string";
  if (typeof h.epoch !== "string") return "horizon.epoch is not a string";
  if (!Number.isInteger(h.first) || !Number.isInteger(h.last)) return "horizon.first/last are not integers";
  if (!(h.fallback_version === null || typeof h.fallback_version === "string")) {
    return "horizon.fallback_version is not a string or null";
  }
  try {
    gridOf(h as unknown as Horizon);
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
  return null;
}

/** A fallback index the playlist may use, or null: anything but null or
 * {len: finite number, notice: string} becomes null, which usableFallback
 * already treats as "no usable fallback". A bad fallback never invalidates a lease. */
function fallbackOrNull(f: unknown): FallbackIndex | null {
  return isObj(f) && finite(f.len) && typeof f.notice === "string" ? { len: f.len, notice: f.notice } : null;
}

/** Validate a lease (data from another isolate, or from storage): on apply and on every load. */
export function validateLease(raw: unknown): { ok: true; lease: Lease } | { ok: false; reason: string } {
  if (!isObj(raw)) return { ok: false, reason: "lease is not an object" };
  if (!finite(raw.verdictAt) || !finite(raw.validUntil)) return { ok: false, reason: "verdictAt/validUntil not finite" };
  if (raw.kind === "hold") return { ok: true, lease: { kind: "hold", verdictAt: raw.verdictAt, validUntil: raw.validUntil } };
  if (raw.kind !== "play") return { ok: false, reason: `kind is ${JSON.stringify(raw.kind)}` };
  if (typeof raw.blocked !== "boolean") return { ok: false, reason: "blocked is not a boolean" };
  const problem = horizonProblem(raw.horizon);
  if (problem !== null) return { ok: false, reason: problem };
  return { ok: true, lease: { kind: "play", verdictAt: raw.verdictAt, validUntil: raw.validUntil, blocked: raw.blocked,
                              horizon: raw.horizon as unknown as Horizon, fallback: fallbackOrNull(raw.fallback) } };
}

/** The lease as stored on accept: expiry computed by the DO's own clock, never
 * later than METRONOME_LEASE_MS from now whatever validUntil says. */
export function storedLease(lease: Lease, nowMs: number): StoredLease {
  return { ...lease, expiresAt: Math.min(lease.validUntil, nowMs + METRONOME_LEASE_MS) };
}

/** Written negated, so a NaN or missing expiresAt is expired (pricing.ts overThreshold's idiom). */
export function expired(l: { expiresAt: number }, nowMs: number): boolean {
  return !(nowMs < l.expiresAt);
}

/** The lease if it is present and unexpired, else null. */
export function currentLease(l: StoredLease | null, nowMs: number): StoredLease | null {
  return l !== null && !expired(l, nowMs) ? l : null;
}

export function leaseKind(l: StoredLease | null, nowMs: number): LeaseKind {
  const c = currentLease(l, nowMs);
  if (c === null) return "none";
  if (c.kind === "hold") return "hold";
  return c.blocked ? "blocked" : "play";
}

/** Ordering. A blocked play lease or a hold is accepted unconditionally
 * (blocking is fail-closed); an unblocked play lease only when there is no
 * current lease or its verdictAt is strictly newer than the current one's. */
export function decideLease(current: StoredLease | null, incoming: Lease, nowMs: number): "accepted" | "superseded" {
  if (incoming.kind === "hold" || incoming.blocked) return "accepted";
  const c = currentLease(current, nowMs);
  return c === null || incoming.verdictAt > c.verdictAt ? "accepted" : "superseded";
}

/** The lease's playlist is live: an unexpired unblocked play lease that is not
 * off air at nowMs (a horizon more than offairAfterMs stale is). Only then does
 * the alarm chain tick. */
export function isLive(l: StoredLease | null, nowMs: number, cfg: PlaylistConfig): boolean {
  const c = currentLease(l, nowMs);
  if (c === null || c.kind !== "play" || c.blocked) return false;
  return !isOffair({ nowMs, horizon: c.horizon, fallback: c.fallback, offair: false }, cfg);
}

/** The first boundary + ALARM_SLACK_MS strictly after afterMs. The target comes
 * from the wall clock, never "previous target + d": lateness never accumulates
 * and missed boundaries are skipped, never written in a burst. */
export function nextTarget(g: Grid, afterMs: number): number {
  return startMs(g, indexAt(g, afterMs - ALARM_SLACK_MS) + 1) + ALARM_SLACK_MS;
}

/** The timestamps inside the rolling window ending at nowMs: just over
 * CAP_WINDOW_MS old is outside, just under is inside. */
export function inWindow(times: readonly number[], nowMs: number): number[] {
  return times.filter((t) => nowMs - t < CAP_WINDOW_MS);
}

export function capAllows(times: readonly number[], nowMs: number, cap: number): boolean {
  return inWindow(times, nowMs).length < cap;
}

/** Record nowMs, keeping at most `keep` timestamps (a fixed-size list). */
export function recordTime(times: readonly number[], nowMs: number, keep: number): number[] {
  return [...inWindow(times, nowMs), nowMs].slice(-keep);
}

/** How long the chain has gone without an alarm-confirmed tick, measured from
 * the later of the last one and the moment the current unblocked play lease
 * was first accepted. 0 unless the stored lease's playlist was live. */
export function stalledFor(wasLive: boolean, lastAlarmGoodAt: number | null, playSince: number | null,
                           nowMs: number): number {
  if (!wasLive) return 0;
  return Math.max(0, nowMs - Math.max(lastAlarmGoodAt ?? 0, playSince ?? 0));
}

export function nextStalls(prev: number, stalledMs: number): number {
  return stalledMs > METRONOME_STALE_MS ? prev + 1 : 0;
}

/** The DO's storage: a fixed set of keys that never grows (how stored bytes
 * are bounded; they cannot be metered). A test pins it. */
export const STORAGE_KEYS = ["lease", "playSince", "lastAlarmGoodAt", "lastTarget", "lastBody", "putTimes", "alarmTimes",
                             "stalls"] as const;
export type StorageKey = (typeof STORAGE_KEYS)[number];

export interface MetronomeState {
  lease: StoredLease | null;
  /** When the current unblocked play lease was accepted after no, blocked, hold or expired lease. */
  playSince: number | null;
  /** The last alarm-confirmed tick: only alarm() advances it. */
  lastAlarmGoodAt: number | null;
  /** The last armed alarm time. */
  lastTarget: number | null;
  /** The last successfully written playlist (null after a failed or timed-out PUT). */
  lastBody: string | null;
  /** The last MAX_DO_PUTS_PER_MINUTE PUT times and MAX_ALARMS_PER_MINUTE alarm() times. */
  putTimes: number[];
  alarmTimes: number[];
  stalls: number;
}

export const EMPTY_STATE: MetronomeState = { lease: null, playSince: null, lastAlarmGoodAt: null, lastTarget: null,
                                             lastBody: null, putTimes: [], alarmTimes: [], stalls: 0 };

const numOrNull = (v: unknown) => (finite(v) ? v : null);
const times = (v: unknown, keep: number) => (Array.isArray(v) ? v.filter(finite).slice(-keep) : []);

/** The stored lease: a JSON string written by serializeLease. Anything that
 * does not parse or validate is `invalid` (the engine deletes it: no lease). */
export function parseStoredLease(raw: unknown): { lease: StoredLease | null; invalid: string | null } {
  if (raw === undefined || raw === null) return { lease: null, invalid: null };
  if (typeof raw !== "string") return { lease: null, invalid: "stored lease is not a string" };
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { lease: null, invalid: "stored lease is not JSON" };
  }
  const v = validateLease(parsed);
  if (!v.ok) return { lease: null, invalid: `stored lease: ${v.reason}` };
  const expiresAt = isObj(parsed) && typeof parsed.expiresAt === "number" ? parsed.expiresAt : Number.NaN;
  return { lease: { ...v.lease, expiresAt }, invalid: null };
}

export function serializeLease(l: StoredLease): string {
  return JSON.stringify(l);
}

/** The state from the raw stored values (a missing or malformed value reads as
 * its empty default), plus why the stored lease was invalid, if it was. */
export function readState(raw: Partial<Record<StorageKey, unknown>>): { state: MetronomeState; leaseInvalid: string | null } {
  const { lease, invalid } = parseStoredLease(raw.lease);
  const stalls = raw.stalls;
  return {
    state: {
      lease,
      playSince: numOrNull(raw.playSince),
      lastAlarmGoodAt: numOrNull(raw.lastAlarmGoodAt),
      lastTarget: numOrNull(raw.lastTarget),
      lastBody: typeof raw.lastBody === "string" ? raw.lastBody : null,
      putTimes: times(raw.putTimes, MAX_DO_PUTS_PER_MINUTE),
      alarmTimes: times(raw.alarmTimes, MAX_ALARMS_PER_MINUTE),
      stalls: Number.isInteger(stalls) && (stalls as number) >= 0 ? (stalls as number) : 0,
    },
    leaseInvalid: invalid,
  };
}

/** The stored value of each key of `next` that differs from `prev` (lease as
 * its JSON string; a removed lease is `undefined`: the engine deletes the key). */
export function stateChanges(prev: MetronomeState, next: MetronomeState): Partial<Record<StorageKey, unknown>> {
  const out: Partial<Record<StorageKey, unknown>> = {};
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  for (const k of STORAGE_KEYS) {
    if (same(prev[k], next[k])) continue;
    out[k] = k === "lease" ? (next.lease === null ? undefined : serializeLease(next.lease)) : next[k];
  }
  return out;
}

/** A play lease issued by cron from a known verdict and an accepted horizon. */
export function playLease(verdictAt: number, issuedAt: number, blocked: boolean, horizon: Horizon,
                          fallback: FallbackIndex | null): PlayLease {
  return { kind: "play", verdictAt, validUntil: issuedAt + METRONOME_LEASE_MS, blocked, horizon, fallback };
}

/** A hold: a known blocked verdict whose inputs are unusable, or a refused horizon. */
export function holdLease(verdictAt: number, issuedAt: number): HoldLease {
  return { kind: "hold", verdictAt, validUntil: issuedAt + METRONOME_LEASE_MS };
}

/** Why cron must fall back (run its loop where the lease table allows, and
 * raise metronome-down), or null when the DO is healthy:
 * (a) renew threw or timed out;
 * (b) cron sent a play lease (blocked or not), it was not superseded, and it
 *     was not accepted or its write failed;
 * (c) STALLS_FALLBACK consecutive renews found the chain stalled. */
export function fallbackReason(sent: Lease | null,
                               r: { status: MetronomeStatus } | { error: string }): string | null {
  if ("error" in r) return `renew failed: ${r.error}`;
  const s = r.status;
  if (sent?.kind === "play" && s.applied !== "superseded" && (s.applied !== "accepted" || s.wrote === false)) {
    return `renew answered applied=${s.applied}, wrote=${s.wrote} to a ${sent.blocked ? "blocked " : ""}play lease`;
  }
  if (s.stalls >= STALLS_FALLBACK) return `alarm chain stalled on ${s.stalls} consecutive renews (${s.stalledMs} ms)`;
  return null;
}
```

- [ ] **Step 5: Run everything**

Run: `cd antenna && npm test && npm run typecheck`
Expected: `Tests  278 passed (278)` (26 new), tsc silent.

- [ ] **Step 6: Commit**

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/antenna-metronome
git -C "$W" add antenna/src/metronome-core.ts antenna/src/grid.ts antenna/src/clock.ts antenna/test/metronome-core.test.ts
git -C "$W" commit -m "feat(antenna): metronome-core, the lease, its ordering and expiry, targets, caps and stalls"
```

---

### Task 4: `metronome-engine.ts` — `renew`

**Model hint:** opus (lease acceptance, PUT cap, serialization: strict surface)

The spec's `renew(lease | null)` steps 1–6, with the spend bounds that apply to renew's write:

- the PUT cap is a rolling window, its slot reserved and its storage write awaited before the PUT;
- the PUT is bounded at 5 s, and a timeout clears `lastBody`;
- the identical-body skip compares against `lastBody`;
- the whole call runs inside one serialized section.

The engine works over a `MetronomePort`, so a fake clock and a `MemoryBucket` test every rule. Task 6 binds the port to the Durable Object.

**Files:**
- Create: `src/metronome-engine.ts`, `test/metronome-support.ts`, `test/metronome-renew.test.ts`

**Interfaces:**
- Consumes: Task 3's `metronome-core.ts` (everything it imports below), `clock.ts` `ClockConfig` and `MAX_LOOP_MS`, `live.ts` `renderLive`, `grid.ts` `gridOf`.
- Produces:
  - `interface MetronomePort`:
    - `now(): number`;
    - `switchOn(): boolean`;
    - `config(): ClockConfig`;
    - `load(): Promise<Partial<Record<StorageKey, unknown>>>`;
    - `save(changes): Promise<void>` (an `undefined` value deletes the key);
    - `getAlarm()`, `setAlarm(atMs)`, `deleteAlarm()`;
    - `putLive(body, liveMaxAge): Promise<void>`;
    - `timer(ms): { done: Promise<void>; clear(): void }`;
    - `log(event, fields)`.
  - `class MetronomeEngine { constructor(port); renew(lease: unknown): Promise<MetronomeStatus> }`. Task 5 adds `alarm(): Promise<void>`.
  - `test/metronome-support.ts`: `E`, `D`, `CFG`, `HORIZON`, `FALLBACK`, `lease(nowMs, {blocked?, hold?, verdictAt?, horizon?, fallback?})`, `class FakePort`, `engineAt(t)`, `settle()`, `seqOf`, `lastListed`. Task 5 adds `deliver` and `deliverDuplicate`.

- [ ] **Step 1: Write the test support** — `test/metronome-support.ts` (not a test file: vitest only collects `*.test.ts`):

```ts
import type { ClockConfig } from "../src/clock";
import { putLive } from "../src/live";
import { type Lease, METRONOME_LEASE_MS } from "../src/metronome-core";
import { MetronomeEngine, type MetronomePort } from "../src/metronome-engine";
import { MemoryBucket } from "./support";

export const E = Date.parse("2026-10-10T12:00:00.000Z");
export const D = 10_240;
/** The deployed playlist config (wrangler.jsonc). */
export const CFG: ClockConfig = { window: 16, lookahead: 12, holdBack: 12, grace: 3, offairAfterMs: 86_400_000,
                                  loopMs: 75_000, liveMaxAge: 5, leadFloorMs: 16 * 3_600_000 };
export const HORIZON = { epoch_id: "e1", epoch: new Date(E).toISOString(), d: 10.24, first: 0, last: 1_000_000,
                         published_at: new Date(E).toISOString(), container: "adts", fallback_version: "v1" };
export const FALLBACK = { len: 7, notice: "fallback/v1/notice.aac" };

/** A lease as cron issues it at nowMs (verdictAt = nowMs unless given). */
export function lease(nowMs: number, o: { blocked?: boolean; hold?: boolean; verdictAt?: number;
                                          horizon?: Record<string, unknown>; fallback?: unknown } = {}): Lease {
  const verdictAt = o.verdictAt ?? nowMs;
  if (o.hold) return { kind: "hold", verdictAt, validUntil: nowMs + METRONOME_LEASE_MS };
  return { kind: "play", verdictAt, validUntil: nowMs + METRONOME_LEASE_MS, blocked: o.blocked ?? false,
           horizon: { ...HORIZON, ...o.horizon }, fallback: (o.fallback === undefined ? FALLBACK : o.fallback) } as Lease;
}

/** An in-memory MetronomePort: a settable clock, a Map for storage, one alarm
 * slot, a MemoryBucket, timers that fire only when asked, and an optional gate
 * that holds every PUT until released. */
export class FakePort implements MetronomePort {
  t: number;
  on = true;
  cfg: ClockConfig = CFG;
  store = new Map<string, unknown>();
  alarmAt: number | null = null;
  bucket = new MemoryBucket();
  logs: Record<string, unknown>[] = [];
  /** Every storage, alarm and PUT operation in order: "save k1,k2", "setAlarm t", "deleteAlarm", "put". */
  ops: string[] = [];
  failSetAlarm = false;
  failLoad = false;
  private gate: Promise<void> | null = null;
  private fires: (() => void)[] = [];

  constructor(t: number) {
    this.t = t;
  }

  now() { return this.t; }
  switchOn() { return this.on; }
  config() { return this.cfg; }
  async load() {
    if (this.failLoad) throw new Error("injected load failure");
    return Object.fromEntries(this.store);
  }
  async save(changes: Record<string, unknown>) {
    this.ops.push(`save ${Object.keys(changes).sort().join(",")}`);
    for (const [k, v] of Object.entries(changes)) {
      if (v === undefined) this.store.delete(k);
      else this.store.set(k, structuredClone(v));
    }
  }
  async getAlarm() { return this.alarmAt; }
  async setAlarm(t: number) {
    if (this.failSetAlarm) throw new Error("injected setAlarm failure");
    this.ops.push(`setAlarm ${t}`);
    this.alarmAt = t;
  }
  async deleteAlarm() {
    this.ops.push("deleteAlarm");
    this.alarmAt = null;
  }
  async putLive(body: string, liveMaxAge: number) {
    this.ops.push("put");
    if (this.gate) await this.gate;
    await putLive(this.bucket, body, liveMaxAge);
  }
  timer(_ms: number) {
    let fire!: () => void;
    const done = new Promise<void>((r) => { fire = r; });
    this.fires.push(fire);
    return { done, clear: () => {} };
  }
  log(event: string, fields: Record<string, unknown>) {
    this.logs.push({ event, ...fields });
  }

  /** Hold every PUT until the returned function is called. */
  holdPuts(): () => void {
    let release!: () => void;
    this.gate = new Promise<void>((r) => { release = r; });
    return () => { this.gate = null; release(); };
  }
  /** Fire every pending timer (a PUT timeout). */
  fireTimers() {
    for (const f of this.fires.splice(0)) f();
  }
  events(name: string) {
    return this.logs.filter((l) => l.event === name);
  }
  puts() {
    return this.bucket.puts("live.m3u8");
  }
  body() {
    return this.bucket.objects.get("live.m3u8")?.body ?? null;
  }
}

export function engineAt(t: number) {
  const port = new FakePort(t);
  return { port, engine: new MetronomeEngine(port) };
}

/** Let queued microtasks run (for interleaving tests). */
export const settle = () => new Promise<void>((r) => setTimeout(r, 0));

export const seqOf = (body: string) => Number(/#EXT-X-MEDIA-SEQUENCE:(\d+)/.exec(body)![1]);
export const lastListed = (body: string) =>
  seqOf(body) + body.split("\n").filter((l) => l !== "" && !l.startsWith("#")).length - 1;
```

- [ ] **Step 2: Write the failing test** — `test/metronome-renew.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { ALARM_SLACK_MS, fallbackReason, holdLease, METRONOME_LEASE_MS, STORAGE_KEYS } from "../src/metronome-core";
import { CFG, D, E, engineAt, HORIZON, lastListed, lease, seqOf, settle } from "./metronome-support";

const T = E + 1_000 * D + 3_000; // 3 s into segment 1000

describe("renew: the switch", () => {
  it("off: deletes the alarm, writes and stores nothing, answers applied off", async () => {
    const { port, engine } = engineAt(T);
    port.on = false;
    port.alarmAt = T + 5_000;
    const st = await engine.renew(lease(T));
    expect(st).toEqual({ applied: "off", lease: "none", wrote: null, lastAlarmGoodAt: null, stalledMs: 0, stalls: 0,
                         leaseVerdictAt: null });
    expect(port.alarmAt).toBeNull();
    expect(port.puts()).toBe(0);
    expect(port.store.size).toBe(0);
  });
});

describe("renew: a play lease", () => {
  it("accepts, writes the live playlist at once, arms the next boundary, records playSince", async () => {
    const { port, engine } = engineAt(T);
    const st = await engine.renew(lease(T));
    expect(st).toMatchObject({ applied: "accepted", lease: "play", wrote: true, stalledMs: 0, stalls: 0,
                               leaseVerdictAt: T, lastAlarmGoodAt: null });
    expect(port.puts()).toBe(1);
    expect(port.body()).toContain("seg/e1/1012.aac"); // 1000 + lookahead 12
    expect(port.alarmAt).toBe(E + 1_001 * D + ALARM_SLACK_MS);
    expect(port.store.get("lastTarget")).toBe(port.alarmAt);
    expect(port.store.get("playSince")).toBe(T);
    expect(port.store.get("lastBody")).toBe(port.body());
    for (const k of port.store.keys()) expect(STORAGE_KEYS as readonly string[]).toContain(k);
  });

  it("renew(null) leaves the lease untouched and still writes from a current play lease", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    port.t = T + 2 * D;
    const st = await engine.renew(null);
    expect(st).toMatchObject({ applied: null, lease: "play", wrote: true, leaseVerdictAt: T });
    expect(port.puts()).toBe(2);
  });

  it("an identical body is not written again (wrote null), and is not a failure", async () => {
    const { port, engine } = engineAt(T);
    const l = lease(T);
    await engine.renew(l);
    const st = await engine.renew(lease(T + 1, { verdictAt: T + 1 }));
    expect(st).toMatchObject({ applied: "accepted", wrote: null });
    expect(port.puts()).toBe(1);
    expect(fallbackReason(l, { status: st })).toBeNull();
  });

  it("does not re-arm when an alarm is already pending", async () => {
    const { port, engine } = engineAt(T);
    port.alarmAt = T + 999;
    await engine.renew(lease(T));
    expect(port.alarmAt).toBe(T + 999);
  });
});

describe("renew: validation", () => {
  it("an invalid lease is applied invalid: logged, the stored lease and the alarm deleted, nothing written", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    expect(port.alarmAt).not.toBeNull();
    port.t = T + 1_000;
    const st = await engine.renew(lease(T + 1_000, { horizon: { d: 10.25 } }));
    expect(st).toMatchObject({ applied: "invalid", lease: "none", wrote: null, leaseVerdictAt: null });
    expect(port.store.has("lease")).toBe(false);
    expect(port.alarmAt).toBeNull();
    expect(port.puts()).toBe(1);
    expect(port.events("metronome-lease-invalid")).toEqual([expect.objectContaining({ source: "renew" })]);
  });

  it("an unparseable stored lease is deleted on load: no write, no re-arm", async () => {
    const { port, engine } = engineAt(T);
    port.store.set("lease", "{not json");
    port.alarmAt = T + 5_000;
    const st = await engine.renew(null);
    expect(st).toMatchObject({ applied: null, lease: "none", wrote: null });
    expect(port.store.has("lease")).toBe(false);
    expect(port.alarmAt).toBeNull();
    expect(port.puts()).toBe(0);
    expect(port.events("metronome-lease-invalid")).toEqual([expect.objectContaining({ source: "storage" })]);
  });

  it("a stored lease that no longer validates (say, after a deploy) is deleted, and the fresh one is accepted", async () => {
    const { port, engine } = engineAt(T);
    port.store.set("lease", JSON.stringify({ ...lease(T - 60_000), horizon: { ...HORIZON, d: 1 }, expiresAt: T + 1 }));
    const st = await engine.renew(lease(T));
    expect(st).toMatchObject({ applied: "accepted", lease: "play", wrote: true });
  });

  it("a malformed fallback plays as no usable fallback, not an invalid lease", async () => {
    const { port, engine } = engineAt(T);
    const st = await engine.renew(lease(T, { fallback: { len: "7" } }));
    expect(st.applied).toBe("accepted");
    expect(port.body()).toContain("seg/e1/1012.aac"); // on air inside the horizon: no loop entry needed
  });
});

describe("renew: ordering", () => {
  it("an older or equal unblocked play lease is superseded (logged once), the newer one stays", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    for (const v of [T - 1, T, T - 2]) {
      const st = await engine.renew(lease(T, { verdictAt: v }));
      expect(st).toMatchObject({ applied: "superseded", lease: "play", leaseVerdictAt: T });
    }
    expect(port.events("metronome-lease-superseded").length).toBeGreaterThanOrEqual(1);
    expect(port.events("metronome-lease-superseded").length).toBeLessThanOrEqual(3);
  });

  it("a lagging older blocked lease is accepted (fail-closed) until a newer unblocked one", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    expect((await engine.renew(lease(T, { verdictAt: T - 60_000, blocked: true }))).lease).toBe("blocked");
    // older than the blocked lease now current: superseded, the DO stays blocked
    expect((await engine.renew(lease(T, { verdictAt: T - 90_000 }))).applied).toBe("superseded");
    expect((await engine.renew(lease(T, { verdictAt: T + 60_000 }))).lease).toBe("play");
    expect(port.alarmAt).not.toBeNull();
  });
});

describe("renew: blocked, hold, expiry", () => {
  it("blocked: writes the off-air notice, leaves no alarm pending", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    const st = await engine.renew(lease(T + 1, { verdictAt: T + 1, blocked: true }));
    expect(st).toMatchObject({ applied: "accepted", lease: "blocked", wrote: true });
    expect(port.body()).toContain("fallback/v1/notice.aac");
    expect(port.body()).toContain("#EXT-X-ENDLIST");
    expect(port.alarmAt).toBeNull();
  });

  it("the notice is numbered above every live segment listed and never decreases across renews", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    const live = port.body()!;
    const seqs: number[] = [];
    for (let i = 1; i <= 4; i++) {
      port.t = T + i * 60_000;
      await engine.renew(lease(port.t, { blocked: true }));
      seqs.push(seqOf(port.body()!));
    }
    expect(seqs[0]).toBeGreaterThan(lastListed(live));
    // indexAt(now + 75 s) + lookahead + 1, above indexAt(now) + lookahead
    expect(seqs[0]).toBeGreaterThan(Math.floor((T + 60_000 - E) / D) + CFG.lookahead!);
    expect([...seqs].sort((a, b) => a - b)).toEqual(seqs);
    expect(port.puts()).toBe(5); // about one PUT per minute while blocked, as today
  });

  it("hold: no PUT, no pending alarm, logged once", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    for (const dt of [1, 2]) {
      port.t = T + dt * 60_000;
      const st = await engine.renew(holdLease(port.t, port.t));
      expect(st).toMatchObject({ applied: "accepted", lease: "hold", wrote: null });
    }
    expect(port.puts()).toBe(1);
    expect(port.alarmAt).toBeNull();
    expect(port.events("metronome-hold")).toHaveLength(1);
  });

  it("expiry: past 15 min the DO writes nothing and disarms; a new lease restarts it", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T, { verdictAt: T }));
    port.t = T + METRONOME_LEASE_MS;
    const st = await engine.renew(null);
    expect(st).toMatchObject({ applied: null, lease: "none", wrote: null, stalledMs: 0 });
    expect(port.alarmAt).toBeNull();
    expect(port.puts()).toBe(1);
    expect(port.events("metronome-expired")).toHaveLength(1);
    const again = await engine.renew(lease(port.t));
    expect(again).toMatchObject({ applied: "accepted", lease: "play", wrote: true });
    expect(port.alarmAt).not.toBeNull();
    expect(port.store.get("playSince")).toBe(port.t);
  });

  it("renew(null) and a superseded lease never extend it: 15 min after acceptance nothing is written or armed", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    for (const min of [5, 10]) {
      port.t = T + min * 60_000;
      expect((await engine.renew(null)).lease).toBe("play");
    }
    port.t = T + 12 * 60_000;
    expect((await engine.renew(lease(port.t, { verdictAt: T }))).applied).toBe("superseded");
    port.t = T + METRONOME_LEASE_MS;
    const puts = port.puts();
    expect(await engine.renew(null)).toMatchObject({ lease: "none", wrote: null });
    expect(port.puts()).toBe(puts);
    expect(port.alarmAt).toBeNull();
  });

  it("a far-future validUntil still expires 15 min after acceptance", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew({ ...lease(T), validUntil: T + 86_400_000 });
    port.t = T + METRONOME_LEASE_MS;
    expect((await engine.renew(null)).lease).toBe("none");
  });
});

describe("renew: stalls", () => {
  it("renew's own write never confirms a tick: two renews over a dead chain count 1 then 2", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    port.alarmAt = null; // the chain broke silently
    port.t = T + 40_000;
    const one = await engine.renew(lease(port.t));
    expect(one).toMatchObject({ stalls: 1, stalledMs: 40_000, wrote: true });
    expect(one.lastAlarmGoodAt).toBeNull();
    expect(fallbackReason(lease(port.t), { status: one })).toBeNull(); // a single stall: no fallback
    // ... that renew re-armed, but the alarm never comes either:
    port.alarmAt = null;
    port.t = T + 80_000;
    const two = await engine.renew(lease(port.t));
    expect(two).toMatchObject({ stalls: 2, stalledMs: 80_000 });
    expect(fallbackReason(lease(port.t), { status: two })).toMatch(/stalled on 2/);
  });

  it("counts from playSince when the play lease is newer than the last alarm tick", async () => {
    const { port, engine } = engineAt(T);
    port.store.set("lastAlarmGoodAt", T - 600_000);
    await engine.renew(lease(T)); // first play lease: playSince = T
    port.t = T + 20_000;
    expect((await engine.renew(null)).stalledMs).toBe(20_000);
  });

  it("every renew writes stalls, unchanged or not, so a healthy DO writes a row every minute", async () => {
    const absent = engineAt(T);
    await absent.engine.renew(null);
    expect(absent.port.ops).toEqual(["save stalls"]);
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    port.t = T + METRONOME_LEASE_MS; // expired
    port.ops.length = 0;
    await engine.renew(null);
    expect(port.ops).toEqual(["deleteAlarm", "save stalls"]);
  });

  it("is 0, and resets the count, when the stored lease was not live", async () => {
    const { port, engine } = engineAt(T);
    port.store.set("stalls", 5);
    const st = await engine.renew(holdLease(T, T));
    expect(st).toMatchObject({ stalledMs: 0, stalls: 0 });
  });
});

describe("renew: the PUT cap and the PUT timeout", () => {
  it("the 11th write in 60 s is skipped and logged; a cap-skipped write is wrote null, not a failure", async () => {
    const { port, engine } = engineAt(T);
    // A flapping verdict: blocked and unblocked leases alternate, so every body differs.
    const flap = (i: number) => lease(T + i * 1_000, { blocked: i % 2 === 0, verdictAt: T + i });
    const statuses = [];
    for (let i = 0; i < 11; i++) {
      port.t = T + i * 1_000;
      statuses.push(await engine.renew(flap(i)));
    }
    expect(port.puts()).toBe(10);
    expect(statuses[10]).toMatchObject({ applied: "accepted", wrote: null });
    expect(fallbackReason(flap(10), { status: statuses[10] })).toBeNull();
    expect(port.events("metronome-cap")).toHaveLength(1);
    port.t = T + 59_999; // just under 60 s after the oldest: still capped
    expect((await engine.renew(flap(11))).wrote).toBeNull();
    port.t = T + 60_001; // just over
    expect((await engine.renew(flap(12))).wrote).toBe(true);
  });

  it("reserves the cap slot in storage before the PUT is issued", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    const put = port.ops.indexOf("put");
    expect(port.ops.slice(0, put).some((o) => o.startsWith("save ") && o.includes("putTimes"))).toBe(true);
  });

  it("a PUT that does not settle within 5 s is a failed write and clears lastBody; the next identical body is written", async () => {
    const { port, engine } = engineAt(T);
    await engine.renew(lease(T));
    expect(port.store.get("lastBody")).toEqual(expect.any(String));
    port.t = T + 2 * D;
    const release = port.holdPuts();
    const pending = engine.renew(null);
    await settle();
    port.fireTimers();
    const st = await pending;
    expect(st).toMatchObject({ wrote: false });
    expect(port.store.get("lastBody")).toBeNull();
    expect(port.events("metronome-put-failed")).toEqual([expect.objectContaining({ error: "timed out after 5000 ms" })]);
    expect(fallbackReason(lease(T), { status: st })).toMatch(/wrote=false/);
    release();
    await settle();
    const before = port.puts();
    expect((await engine.renew(null)).wrote).toBe(true); // same moment, same body: not skipped
    expect(port.puts()).toBe(before + 1);
  });

  it("a PUT that throws is a failed write", async () => {
    const { port, engine } = engineAt(T);
    port.bucket.failPuts.add("live.m3u8");
    expect((await engine.renew(lease(T))).wrote).toBe(false);
  });
});

describe("renew: serialization", () => {
  it("overlapping renews run one after the other: one PUT, consistent cap and lastBody", async () => {
    const { port, engine } = engineAt(T);
    const release = port.holdPuts();
    const a = engine.renew(lease(T));
    const b = engine.renew(lease(T, { verdictAt: T + 1 }));
    await settle();
    expect(port.ops.filter((o) => o === "put")).toHaveLength(1); // b has not started
    release();
    const [sa, sb] = await Promise.all([a, b]);
    expect(sa.wrote).toBe(true);
    expect(sb.wrote).toBeNull(); // identical body
    expect(port.puts()).toBe(1);
    expect(port.store.get("putTimes")).toEqual([T]);
    expect(port.store.get("lastBody")).toBe(port.body());
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/metronome-renew.test.ts`
Expected: FAIL. `../src/metronome-engine` cannot be resolved.

- [ ] **Step 4: Create `src/metronome-engine.ts`** (renew only; the import list and `confirms` already name what Task 5's `alarm()` uses)

```ts
/** The metronome's sequencing (metronome spec, "Metronome (the DO)"): renew()
 * and alarm() over a port (storage, alarm, R2, clock, logs), so every rule is
 * tested with a fake clock and a fake bucket; metronome.ts binds the port to a
 * Durable Object. State lives in storage, memory is a cache only (the object is
 * evicted between alarms): every call loads the fixed key set and writes back
 * what changed, plus `stalls` on every renew.
 *
 * Spend is the strict surface. The bounds this file enforces, whatever its
 * inputs: at most one PUT per call; at most MAX_DO_PUTS_PER_MINUTE PUTs in a
 * rolling minute, renew's included, the slot reserved (its storage write
 * awaited) before the PUT is issued; each PUT bounded by DO_PUT_TIMEOUT_MS; at
 * most MAX_ALARMS_PER_MINUTE alarm() invocations re-arm per rolling minute; the
 * chain ticks only while the lease's playlist is live; an expired, held,
 * blocked or absent lease never re-arms. */

import { type ClockConfig, MAX_LOOP_MS } from "./clock";
import { gridOf } from "./grid";
import { renderLive } from "./live";
import { ALARM_SLACK_MS, capAllows, currentLease, decideLease, DO_PUT_TIMEOUT_MS, isLive, LATE_LOG_MS, leaseKind,
         MAX_ALARMS_PER_MINUTE, MAX_DO_PUTS_PER_MINUTE, type MetronomeState, type MetronomeStatus, nextStalls,
         nextTarget, type PlayLease, readState, recordTime, stalledFor, stateChanges, type StorageKey, storedLease,
         validateLease } from "./metronome-core";

export interface MetronomePort {
  now(): number;
  /** env.METRONOME is exactly "on". Read on every call: the rollback switch reaches the DO directly. */
  switchOn(): boolean;
  /** The playlist config (configFromEnv), read on every call. */
  config(): ClockConfig;
  /** The stored values of the fixed key set (missing keys absent). */
  load(): Promise<Partial<Record<StorageKey, unknown>>>;
  /** Write these keys; a value of `undefined` deletes the key. */
  save(changes: Partial<Record<StorageKey, unknown>>): Promise<void>;
  getAlarm(): Promise<number | null>;
  setAlarm(atMs: number): Promise<void>;
  deleteAlarm(): Promise<void>;
  /** PUT live.m3u8 (live.ts putLive). */
  putLive(body: string, liveMaxAge: number): Promise<void>;
  /** A timer that resolves `done` after ms; `clear` cancels it. */
  timer(ms: number): { done: Promise<void>; clear(): void };
  /** One structured anomaly line. */
  log(event: string, fields: Record<string, unknown>): void;
}

/** One call's view: what storage holds, and what this call will leave there. */
interface Tx {
  stored: MetronomeState;
  s: MetronomeState;
}

type WriteResult = "put" | "identical" | "null" | "cap" | "failed";

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));
/** An alarm-confirmed tick: a PUT, an identical body, or nothing to build by rule. */
const confirms = (r: WriteResult) => r === "put" || r === "identical" || r === "null";
const copy = (s: MetronomeState): MetronomeState => ({ ...s, putTimes: [...s.putTimes], alarmTimes: [...s.alarmTimes] });

export class MetronomeEngine {
  /** Every write path runs inside this one promise chain (spec "Serialized sections"). */
  private chain: Promise<unknown> = Promise.resolve();
  /** "Logged once" marks, per anomaly: memory only, so an evicted object may log a persisting anomaly again. */
  private readonly marks = new Map<string, string>();

  constructor(private readonly port: MetronomePort) {}

  /** Cron's call, every minute (`null` leaves the lease alone: a health check). */
  renew(lease: unknown): Promise<MetronomeStatus> {
    return this.serial(() => this.renewSteps(lease ?? null));
  }

  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const run = this.chain.then(fn, fn);
    this.chain = run.catch(() => undefined);
    return run;
  }

  /** Log `event` when an episode of `key` starts (or its `id` changes); a later call with active=false ends it. */
  private episode(key: string, active: boolean, id: string, event: string, fields: Record<string, unknown>): void {
    if (!active) {
      this.marks.delete(key);
      return;
    }
    if (this.marks.get(key) === id) return;
    this.marks.set(key, id);
    this.port.log(event, fields);
  }

  private async begin(): Promise<Tx> {
    const { state, leaseInvalid } = readState(await this.port.load());
    if (leaseInvalid !== null) {
      // An invalid or unparseable stored lease is deleted on load: no lease.
      this.port.log("metronome-lease-invalid", { reason: leaseInvalid, source: "storage" });
      await this.port.save({ lease: undefined });
    }
    return { stored: copy(state), s: copy(state) };
  }

  /** Write back what changed; `withStalls` writes `stalls` even when unchanged. */
  private async flush(tx: Tx, withStalls = false): Promise<void> {
    const changes = stateChanges(tx.stored, tx.s);
    if (withStalls) changes.stalls = tx.s.stalls;
    if (Object.keys(changes).length > 0) await this.port.save(changes);
    tx.stored = copy(tx.s);
  }

  private async disarm(): Promise<void> {
    if ((await this.port.getAlarm()) !== null) await this.port.deleteAlarm();
  }

  /** The PUT, bounded by DO_PUT_TIMEOUT_MS; never throws. */
  private async boundedPut(body: string, liveMaxAge: number): Promise<"ok" | string> {
    const t = this.port.timer(DO_PUT_TIMEOUT_MS);
    try {
      return await Promise.race([
        this.port.putLive(body, liveMaxAge).then(() => "ok"),
        t.done.then(() => `timed out after ${DO_PUT_TIMEOUT_MS} ms`),
      ]);
    } catch (e) {
      return msg(e);
    } finally {
      t.clear();
    }
  }

  /** Build the playlist for buildAtMs from a play lease and write it, unless
   * the body equals lastBody, the cap is reached or nothing can be built. */
  private async write(tx: Tx, lease: PlayLease, buildAtMs: number, now: number, cfg: ClockConfig,
                      source: "renew" | "alarm"): Promise<WriteResult> {
    const src = { horizon: lease.horizon, fallback: lease.fallback, offair: lease.blocked };
    // The off-air notice is numbered from now + 75 s (offairSequence), the cron
    // loop's max(scheduledTime + loopMs, now) shape: strictly above every live
    // segment either writer has listed, and never decreasing across renews.
    const { body, offairWithoutFallback } = renderLive(src, buildAtMs, now + MAX_LOOP_MS, cfg);
    this.episode("offair-without-fallback", offairWithoutFallback !== null, String(lease.verdictAt),
                 "offair-without-fallback", { reason: offairWithoutFallback, epoch_id: lease.horizon.epoch_id, source });
    if (body === null) {
      // Before the epoch, or no usable fallback for a loop entry: nothing by rule. Once per lease.
      this.episode("null-build", true, String(lease.verdictAt), "metronome-null-build",
                   { verdictAt: lease.verdictAt, at: buildAtMs, source });
      return "null";
    }
    this.episode("null-build", false, "", "", {});
    if (body === tx.s.lastBody) return "identical";
    if (!capAllows(tx.s.putTimes, now, MAX_DO_PUTS_PER_MINUTE)) {
      this.episode("cap", true, "cap", "metronome-cap", { cap: MAX_DO_PUTS_PER_MINUTE, source });
      return "cap";
    }
    this.episode("cap", false, "", "", {});
    // Reserve the slot, its storage write awaited, before the PUT is issued.
    tx.s.putTimes = recordTime(tx.s.putTimes, now, MAX_DO_PUTS_PER_MINUTE);
    await this.flush(tx);
    const r = await this.boundedPut(body, cfg.liveMaxAge);
    if (r !== "ok") {
      // The bytes in R2 are unknown now: the next write is never skipped as identical.
      tx.s.lastBody = null;
      this.episode("put-failed", true, "put-failed", "metronome-put-failed", { error: r, source });
      return "failed";
    }
    this.episode("put-failed", false, "", "", {});
    tx.s.lastBody = body;
    return "put";
  }

  private async renewSteps(raw: unknown): Promise<MetronomeStatus> {
    // 1. The rollback switch.
    if (!this.port.switchOn()) {
      await this.port.deleteAlarm();
      return { applied: "off", lease: "none", wrote: null, lastAlarmGoodAt: null, stalledMs: 0, stalls: 0,
               leaseVerdictAt: null };
    }
    const now = this.port.now();
    const cfg = this.port.config();
    // 2. Load (an invalid stored lease is deleted), then the stall count as it
    //    stood. `stalls` is written on every renew, changed or not, so a healthy
    //    DO writes at least one row a minute (the guard's empty-is-not-zero check).
    const tx = await this.begin();
    const s = tx.s;
    const stalledMs = stalledFor(isLive(s.lease, now, cfg), s.lastAlarmGoodAt, s.playSince, now);
    s.stalls = nextStalls(s.stalls, stalledMs);
    // 3. Apply the lease, if given.
    let applied: MetronomeStatus["applied"] = null;
    if (raw !== null) {
      const v = validateLease(raw);
      if (!v.ok) {
        // Stores nothing from it; deletes its stored lease and alarm: idle.
        this.port.log("metronome-lease-invalid", { reason: v.reason, source: "renew" });
        s.lease = null;
        await this.flush(tx, true);
        await this.disarm();
        return { applied: "invalid", lease: "none", wrote: null, lastAlarmGoodAt: s.lastAlarmGoodAt, stalledMs,
                 stalls: s.stalls, leaseVerdictAt: null };
      }
      applied = decideLease(s.lease, v.lease, now);
      this.episode("superseded", applied === "superseded", String(v.lease.verdictAt), "metronome-lease-superseded",
                   { verdictAt: v.lease.verdictAt, currentVerdictAt: s.lease?.verdictAt ?? null });
      if (applied === "accepted") {
        const wasPlay = leaseKind(s.lease, now) === "play";
        s.lease = storedLease(v.lease, now);
        if (leaseKind(s.lease, now) === "play" && !wasPlay) s.playSince = now;
      }
    }
    const cur = currentLease(s.lease, now);
    this.episode("expired", s.lease !== null && cur === null, String(s.lease?.verdictAt), "metronome-expired",
                 { verdictAt: s.lease?.verdictAt ?? null, source: "renew" });
    this.episode("hold", cur?.kind === "hold", "hold", "metronome-hold", { verdictAt: cur?.verdictAt ?? null });
    // 4. Write once now under an unexpired play lease: the live playlist, or the off-air notice.
    let wrote: boolean | null = null;
    if (cur !== null && cur.kind === "play") {
      const r = await this.write(tx, cur, now, now, cfg, "renew");
      wrote = r === "put" ? true : r === "failed" ? false : null;
    }
    // 5. Arm only while live and none is pending; otherwise delete any pending alarm.
    if (cur !== null && cur.kind === "play" && isLive(s.lease, now, cfg)) {
      if ((await this.port.getAlarm()) === null) {
        const target = nextTarget(gridOf(cur.horizon), Math.max(now, s.lastTarget ?? Number.NEGATIVE_INFINITY));
        await this.port.setAlarm(target);
        s.lastTarget = target;
      }
    } else {
      await this.disarm();
    }
    await this.flush(tx, true);
    return { applied, lease: leaseKind(s.lease, now), wrote, lastAlarmGoodAt: s.lastAlarmGoodAt, stalledMs,
             stalls: s.stalls, leaseVerdictAt: currentLease(s.lease, now)?.verdictAt ?? null };
  }
}
```

- [ ] **Step 5: Run everything**

Run: `cd antenna && npm test && npm run typecheck`
Expected: `Tests  304 passed (304)` (26 new), tsc silent. (Unused imports are not a tsc error under this `tsconfig.json`.)

- [ ] **Step 6: Commit**

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/antenna-metronome
git -C "$W" add antenna/src/metronome-engine.ts antenna/test/metronome-support.ts antenna/test/metronome-renew.test.ts
git -C "$W" commit -m "feat(antenna): metronome engine renew: lease apply, capped bounded write, arm while live"
```

---

### Task 5: `metronome-engine.ts` — `alarm()`

**Model hint:** opus (`alarm()` structure and its caps: strict surface)

The spec's `alarm()` steps 1–6, in this order:

1. the switch;
2. load and validate; not a current unblocked play lease → delete any pending alarm, no re-arm;
   - 2b. an alarm still pending → a duplicate or retried delivery (spec reading 9): build for `now`, PUT only if the bytes differ, no re-arm, `lastTarget` unchanged, not counted, `metronome-duplicate` once per episode;
3. count the invocation (12 per rolling 60 s, else no re-arm and `metronome-alarm-cap`);
4. **re-arm first**, only while live, to the first boundary + 25 ms strictly after `max(now, lastTarget)`, in its own try/catch (`metronome-rearm-failed`);
5. build for the due boundary `max(now, lastTarget − 25 ms)` (`lastTarget` as it stood before step 4) and PUT unless identical, capped and bounded;
6. update storage (alarm-confirmed tick: a PUT, an identical body, or a null build).

Nothing in `alarm()` ever throws to the runtime.

**Files:**
- Modify: `src/metronome-engine.ts` (add `alarm()` and `alarmSteps()`), `test/metronome-support.ts` (add `deliver`, `deliverDuplicate`)
- Create: `test/metronome-alarm.test.ts`

**Interfaces:**
- Consumes: Task 4's engine internals (`serial`, `episode`, `begin`, `flush`, `disarm`, `write`).
- Produces: `MetronomeEngine.alarm(): Promise<void>`, which never rejects; `deliver(port, engine, t?)` (the runtime consumes the alarm, then runs `alarm()`) and `deliverDuplicate(port, engine, t)` (the alarm stays pending) in `test/metronome-support.ts`.

- [ ] **Step 1: Add `deliver` and `deliverDuplicate` to `test/metronome-support.ts`**

Insert immediately before `/** Let queued microtasks run (for interleaving tests). */`:

```ts
/** Deliver the pending alarm at time t: the runtime consumes it, then runs alarm(). */
export async function deliver(port: FakePort, engine: MetronomeEngine, t = port.alarmAt!) {
  port.t = t;
  port.alarmAt = null;
  await engine.alarm();
}

/** Deliver the alarm again at time t while the re-armed one is still pending
 * (at-least-once delivery): the pending alarm stays set. */
export async function deliverDuplicate(port: FakePort, engine: MetronomeEngine, t: number) {
  port.t = t;
  await engine.alarm();
}

```

- [ ] **Step 2: Write the failing test** — `test/metronome-alarm.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { ALARM_SLACK_MS, holdLease, METRONOME_LEASE_MS, STORAGE_KEYS } from "../src/metronome-core";
import { CFG, D, deliver, deliverDuplicate, E, engineAt, lease, seqOf, settle } from "./metronome-support";

const T = E + 1_000 * D + 3_000; // 3 s into segment 1000
const target = (n: number) => E + n * D + ALARM_SLACK_MS;

/** A DO that accepted an unblocked play lease at T: alarm pending at boundary 1001. */
async function playing() {
  const r = engineAt(T);
  await r.engine.renew(lease(T));
  return r;
}

describe("alarm: the tick", () => {
  it("re-arms first to the next boundary, then writes, then confirms the tick", async () => {
    const { port, engine } = await playing();
    expect(port.alarmAt).toBe(target(1001));
    port.ops.length = 0;
    await deliver(port, engine);
    expect(port.alarmAt).toBe(target(1002));
    expect(port.ops.indexOf(`setAlarm ${target(1002)}`)).toBeLessThan(port.ops.indexOf("put"));
    expect(port.body()).toContain("seg/e1/1013.aac");
    expect(port.store.get("lastTarget")).toBe(target(1002));
    expect(port.store.get("lastAlarmGoodAt")).toBe(target(1001));
    expect(port.puts()).toBe(2);
  });

  it("runs on the grid: one PUT per boundary, no drift", async () => {
    const { port, engine } = await playing();
    for (let n = 1001; n <= 1010; n++) {
      expect(port.alarmAt).toBe(target(n));
      await deliver(port, engine, target(n) + 7); // a few ms late, every time
    }
    expect(port.puts()).toBe(11);
    expect(port.alarmAt).toBe(target(1011));
  });

  it("a late alarm skips missed boundaries rather than bursting", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) + 25_000); // 2 boundaries missed
    expect(port.alarmAt).toBe(target(1004));
    expect(port.puts()).toBe(2);
    expect(port.events("metronome-late")).toEqual([expect.objectContaining({ lateMs: 25_000 })]);
  });

  it("an alarm delivered before the DO's clock passes its boundary builds for that boundary and moves on", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) - 40); // 15 ms before boundary 1001 starts
    expect(port.body()).toContain("seg/e1/1013.aac"); // boundary 1001's playlist, not 1000's
    expect(port.alarmAt).toBe(target(1002)); // never the same target again: no hot loop
  });

  it("a second delivery for the same boundary rebuilds identical bytes: no PUT, still a confirmed tick", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) + 3);
    const puts = port.puts();
    port.store.set("lastTarget", target(1001)); // the same boundary again (at-least-once delivery)
    await deliver(port, engine, target(1001) + 9);
    expect(port.puts()).toBe(puts);
    expect(port.store.get("lastAlarmGoodAt")).toBe(target(1001) + 9);
  });

  it("duplicates after a completed tick (an alarm still pending): no PUT, no re-arm, lastTarget unchanged", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) + 3);
    const puts = port.puts();
    port.ops.length = 0;
    for (const dt of [5, 9, 2_000]) await deliverDuplicate(port, engine, target(1001) + dt);
    expect(port.puts()).toBe(puts);
    expect(port.ops.filter((o) => o !== "save lastAlarmGoodAt")).toEqual([]);
    expect(port.alarmAt).toBe(target(1002));
    expect(port.store.get("lastTarget")).toBe(target(1002));
    expect(port.store.get("lastAlarmGoodAt")).toBe(target(1001) + 2_000); // identical bytes: a confirmed tick
    expect(port.events("metronome-duplicate")).toHaveLength(1);
  });

  it("a duplicate, then a renew in the same segment: no extra PUT, MEDIA-SEQUENCE never goes backwards", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine, target(1001) + 3);
    const puts = port.puts();
    const seqs = [seqOf(port.body()!)];
    await deliverDuplicate(port, engine, target(1001) + 5);
    seqs.push(seqOf(port.body()!));
    port.t = target(1001) + 4_000; // still segment 1001
    expect((await engine.renew(lease(port.t))).wrote).toBeNull();
    seqs.push(seqOf(port.body()!));
    expect(port.puts()).toBe(puts);
    expect([...seqs].sort((a, b) => a - b)).toEqual(seqs);
    await deliver(port, engine); // boundary 1002, on time
    expect(seqOf(port.body()!)).toBeGreaterThan(seqs[2]);
  });
});

describe("alarm: an epoch change", () => {
  it("the next renew writes the new epoch at once, and the next alarm re-aims to the new grid", async () => {
    const { port, engine } = await playing();
    await deliver(port, engine);
    const E2 = E + 1_001 * D + 4_000; // a re-render: a new epoch 4 s after boundary 1001
    port.t = E2 + 100 * D + 1_000;
    const newEpoch = { epoch_id: "e2", epoch: new Date(E2).toISOString() };
    const st = await engine.renew(lease(port.t, { horizon: newEpoch }));
    expect(st).toMatchObject({ applied: "accepted", wrote: true });
    expect(port.body()).toContain("seg/e2/112.aac"); // 100 + lookahead 12 on the new grid
    // The pending alarm is long past: deliver it now; it re-arms on the new grid.
    await deliver(port, engine, port.t + 10);
    expect(port.alarmAt).toBe(E2 + 101 * D + ALARM_SLACK_MS);
    await deliver(port, engine);
    expect(port.alarmAt).toBe(E2 + 102 * D + ALARM_SLACK_MS);
  });
});

describe("alarm: when it must not tick", () => {
  it("switch off: deletes the alarm, writes nothing", async () => {
    const { port, engine } = await playing();
    port.on = false;
    port.alarmAt = target(1001); // pending
    await engine.alarm();
    expect(port.alarmAt).toBeNull();
    expect(port.puts()).toBe(1);
  });

  for (const [what, setup] of [
    ["no lease", async (e: Awaited<ReturnType<typeof playing>>) => { e.port.store.delete("lease"); }],
    ["a hold", async (e: Awaited<ReturnType<typeof playing>>) => { await e.engine.renew(holdLease(T + 1, T + 1)); }],
    ["a blocked lease", async (e: Awaited<ReturnType<typeof playing>>) => {
      await e.engine.renew(lease(T + 1, { blocked: true, verdictAt: T + 1 }));
    }],
    ["an expired lease", async (e: Awaited<ReturnType<typeof playing>>) => { e.port.t = T + METRONOME_LEASE_MS; }],
    ["a lease renewed only by renew(null) and a superseded lease", async (e: Awaited<ReturnType<typeof playing>>) => {
      for (const min of [5, 10]) {
        e.port.t = T + min * 60_000;
        await e.engine.renew(null);
      }
      e.port.t = T + 12 * 60_000;
      await e.engine.renew(lease(e.port.t, { verdictAt: T }));
      e.port.t = T + METRONOME_LEASE_MS;
    }],
    ["an unparseable stored lease", async (e: Awaited<ReturnType<typeof playing>>) => { e.port.store.set("lease", "{"); }],
  ] as const) {
    it(`${what}: an alarm delivered anyway writes nothing and does not re-arm`, async () => {
      const p = await playing();
      await setup(p);
      const puts = p.port.puts();
      p.port.alarmAt = null;
      await p.engine.alarm();
      expect(p.port.puts()).toBe(puts);
      expect(p.port.alarmAt).toBeNull();
    });
  }

  it("a horizon over 24 h stale under an unblocked lease: the off-air body once, no re-arm, no stall", async () => {
    const late = E + 11 * D + CFG.offairAfterMs + 1;
    const { port, engine } = engineAt(late - 20_000);
    await engine.renew(lease(late - 20_000, { horizon: { last: 10 } })); // still live, 20 s before the cut-over
    await deliver(port, engine, late);
    expect(port.body()).toContain("#EXT-X-ENDLIST");
    expect(port.alarmAt).toBeNull();
    port.t = late + 60_000;
    const st = await engine.renew(lease(port.t, { horizon: { last: 10 } }));
    expect(st).toMatchObject({ stalls: 0, stalledMs: 0 });
    expect(port.alarmAt).toBeNull();
  });

  it("a null build (before the epoch) is a confirmed tick, logged once per lease", async () => {
    const before = E - 5 * D;
    const { port, engine } = engineAt(before);
    await engine.renew(lease(before));
    expect(port.puts()).toBe(0);
    await deliver(port, engine);
    await deliver(port, engine);
    expect(port.puts()).toBe(0);
    expect(port.store.get("lastAlarmGoodAt")).toBe(port.t);
    expect(port.events("metronome-null-build")).toHaveLength(1);
    expect(port.alarmAt).not.toBeNull();
  });

  it("a fallback loop entry with no usable fallback is a null build too", async () => {
    const { port, engine } = engineAt(T);
    // the horizon ended 5 segments ago (past grace): the window needs loop entries
    await engine.renew(lease(T, { horizon: { last: 995 }, fallback: null }));
    await deliver(port, engine);
    expect(port.puts()).toBe(0);
    expect(port.store.get("lastAlarmGoodAt")).toBe(port.t);
  });
});

describe("alarm: caps and failures", () => {
  it("the 13th alarm() in 60 s does not re-arm and logs metronome-alarm-cap; just over 60 s later it does", async () => {
    const { port, engine } = await playing();
    for (let i = 0; i < 12; i++) await deliver(port, engine, T + 1_000 + i * 100);
    expect(port.alarmAt).not.toBeNull();
    await deliver(port, engine, T + 1_000 + 59_999); // 13th, just under 60 s after the first
    expect(port.alarmAt).toBeNull();
    expect(port.events("metronome-alarm-cap")).toHaveLength(1);
    await deliver(port, engine, T + 1_000 + 60_001); // just over: the oldest left the window
    expect(port.alarmAt).not.toBeNull();
  });

  it("the PUT cap holds across alarms and renews, and the chain still re-arms over it", async () => {
    const { port, engine } = await playing();
    // a flapping verdict between ticks: 10 PUTs within the minute
    for (let i = 1; i <= 9; i++) {
      port.t = T + i * 1_000;
      await engine.renew(lease(port.t, { blocked: i % 2 === 1, verdictAt: T + i }));
    }
    expect(port.puts()).toBe(10);
    await engine.renew(lease(T + 9_500, { verdictAt: T + 10 })); // back on air
    await deliver(port, engine, target(1001) + 30_000);
    expect(port.puts()).toBe(10);
    expect(port.events("metronome-cap").length).toBeGreaterThanOrEqual(1);
    expect(port.alarmAt).not.toBeNull();
  });

  it("a failed re-arm logs metronome-rearm-failed and returns without writing", async () => {
    const { port, engine } = await playing();
    port.failSetAlarm = true;
    await deliver(port, engine);
    expect(port.events("metronome-rearm-failed")).toHaveLength(1);
    expect(port.puts()).toBe(1);
  });

  it("an exception anywhere in alarm() never propagates", async () => {
    const { port, engine } = await playing();
    port.failLoad = true;
    await expect(deliver(port, engine)).resolves.toBeUndefined();
    expect(port.events("metronome-alarm-error")).toEqual([expect.objectContaining({ error: "injected load failure" })]);
  });

  it("a failed PUT leaves the chain armed, the tick unconfirmed and lastBody cleared", async () => {
    const { port, engine } = await playing();
    port.bucket.failPuts.add("live.m3u8");
    await deliver(port, engine);
    expect(port.alarmAt).toBe(target(1002));
    expect(port.store.get("lastAlarmGoodAt") ?? null).toBeNull();
    expect(port.store.get("lastBody")).toBeNull();
    expect(port.events("metronome-put-failed")).toHaveLength(1);
  });
});

describe("alarm and renew interleaved", () => {
  it("a renew during an alarm's slow PUT waits for it: the cap and lastBody stay consistent", async () => {
    const { port, engine } = await playing();
    const release = port.holdPuts();
    port.alarmAt = null;
    port.t = target(1001);
    const tick = engine.alarm();
    await settle();
    const renewed = engine.renew(lease(port.t, { verdictAt: port.t }));
    await settle();
    expect(port.ops.filter((o) => o === "put")).toHaveLength(2); // the first renew and the alarm: the new renew waits
    release();
    const [, st] = await Promise.all([tick, renewed]);
    expect(st.wrote).toBeNull(); // the same moment, the same body: skipped against the alarm's lastBody
    expect(port.puts()).toBe(2);
    expect((port.store.get("putTimes") as number[]).length).toBe(2);
    expect(port.store.get("lastBody")).toBe(port.body());
  });
});

describe("storage", () => {
  it("the stored keys are always within the fixed set, and a full cycle uses exactly it", async () => {
    const { port, engine } = await playing();
    const within = () => { for (const k of port.store.keys()) expect(STORAGE_KEYS as readonly string[]).toContain(k); };
    for (let i = 0; i < 20; i++) {
      await deliver(port, engine);
      within();
    }
    port.alarmAt = null; // a silent chain break: the next renew counts a stall
    port.t += 40_000;
    await engine.renew(lease(port.t));
    await deliver(port, engine);
    await engine.renew(lease(port.t + 1, { verdictAt: port.t + 1 }));
    within();
    expect([...port.store.keys()].sort()).toEqual([...STORAGE_KEYS].sort());
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/metronome-alarm.test.ts`
Expected: FAIL with `engine.alarm is not a function` (and `npm run typecheck` reports `Property 'alarm' does not exist on type 'MetronomeEngine'`).

- [ ] **Step 4: Add `alarm()` to `src/metronome-engine.ts`**

Insert immediately before `  private serial<T>(fn: () => Promise<T>): Promise<T> {`:

```ts
  /** The alarm chain's tick. Never throws to the runtime: an escaping
   * exception would hand the chain to the platform's 6-retry backoff. */
  async alarm(): Promise<void> {
    try {
      // 1. The rollback switch.
      if (!this.port.switchOn()) {
        await this.port.deleteAlarm();
        return;
      }
      await this.serial(() => this.alarmSteps());
    } catch (e) {
      this.port.log("metronome-alarm-error", { error: msg(e) });
    }
  }

```

Insert immediately before `  private async renewSteps(raw: unknown): Promise<MetronomeStatus> {`:

```ts
  private async alarmSteps(): Promise<void> {
    const now = this.port.now();
    const cfg = this.port.config();
    // 2. Not a current unblocked play lease (none, hold, blocked, expired):
    //    delete any pending alarm and stop. The next renew restarts the chain.
    const tx = await this.begin();
    const s = tx.s;
    const cur = currentLease(s.lease, now);
    this.episode("expired", s.lease !== null && cur === null, String(s.lease?.verdictAt), "metronome-expired",
                 { verdictAt: s.lease?.verdictAt ?? null, source: "alarm" });
    if (cur === null || cur.kind !== "play" || cur.blocked) {
      await this.disarm();
      await this.flush(tx);
      return;
    }
    // 2b. A duplicate or retried delivery: an alarm is still pending, which a
    //     genuine delivery never sees while its handler runs (getAlarm() is null
    //     then, unless setAlarm ran since). Idempotent: build for now and PUT
    //     only if the bytes differ; no re-arm, lastTarget unchanged, not counted.
    const pending = await this.port.getAlarm();
    this.episode("duplicate", pending !== null, "duplicate", "metronome-duplicate", { pending });
    if (pending !== null) {
      if (confirms(await this.write(tx, cur, now, now, cfg, "alarm"))) s.lastAlarmGoodAt = now;
      await this.flush(tx);
      return;
    }
    // 3. Count the invocation; at the cap, do not re-arm.
    if (!capAllows(s.alarmTimes, now, MAX_ALARMS_PER_MINUTE)) {
      this.episode("alarm-cap", true, "alarm-cap", "metronome-alarm-cap", { cap: MAX_ALARMS_PER_MINUTE });
      await this.flush(tx);
      return;
    }
    this.episode("alarm-cap", false, "", "", {});
    s.alarmTimes = recordTime(s.alarmTimes, now, MAX_ALARMS_PER_MINUTE);
    const prevTarget = s.lastTarget;
    const lateMs = prevTarget === null ? 0 : now - prevTarget;
    this.episode("late", lateMs > LATE_LOG_MS, "late", "metronome-late", { lateMs, target: prevTarget });
    // 4. Re-arm first, only while live, to the first boundary + 25 ms strictly
    //    after max(now, lastTarget): no hot loop when an alarm arrives before
    //    the DO's clock passes its boundary.
    if (isLive(s.lease, now, cfg)) {
      const target = nextTarget(gridOf(cur.horizon), Math.max(now, prevTarget ?? Number.NEGATIVE_INFINITY));
      try {
        await this.port.setAlarm(target);
      } catch (e) {
        this.port.log("metronome-rearm-failed", { error: msg(e), target });
        await this.flush(tx);
        return;
      }
      s.lastTarget = target;
    }
    // 5. Build for the due boundary (an early alarm builds for its own
    //    boundary) and write unless identical, capped and bounded.
    const due = Math.max(now, (prevTarget ?? now) - ALARM_SLACK_MS);
    const r = await this.write(tx, cur, due, now, cfg, "alarm");
    // 6. Alarm-confirmed ticks: a PUT, an identical body, or nothing to build by rule.
    if (confirms(r)) s.lastAlarmGoodAt = now;
    await this.flush(tx);
  }

```

- [ ] **Step 5: Run everything**

Run: `cd antenna && npm test && npm run typecheck`
Expected: `Tests  329 passed (329)` (25 new), tsc silent.

- [ ] **Step 6: Commit**

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/antenna-metronome
git -C "$W" add antenna/src/metronome-engine.ts antenna/test/metronome-support.ts antenna/test/metronome-alarm.test.ts
git -C "$W" commit -m "feat(antenna): metronome engine alarm: re-arm first, rolling caps, never throws"
```

---
### Task 6: The Durable Object, its binding, migration and switch

**Model hint:** sonnet (thin binding of a fully specified engine; config mechanics)

The Durable Object binds the engine's port to `ctx.storage` (KV API on the SQLite backend), the alarm API, the R2 binding and `this.env`. `this.env` is read on **every** call, so a deploy of the switch reaches the object directly (spec H2). The client gives cron the single instance by its fixed name, with a 15 s bound per renew. `wrangler.jsonc` gains:

- the binding;
- the migration (form verified above: `migrations` + `new_sqlite_classes`);
- `"METRONOME": "off"`;
- the observability comment the spec asks for.

**Files:**
- Create: `src/metronome.ts`, `test/metronome.test.ts`
- Modify: `src/env.ts`, `src/index.ts` (export the class only; the wiring is Task 7), `wrangler.jsonc`, `test/wrangler-config.test.ts`

**Interfaces:**
- Consumes: `MetronomeEngine` and `MetronomePort` (Tasks 4–5); `metronome-core` `Lease`, `MetronomeClient`, `METRONOME_NAME`, `MetronomeStatus`, `RENEW_TIMEOUT_MS`, `STORAGE_KEYS`, `StorageKey`; `clock.ts` `configFromEnv`; `live.ts` `putLive`; `bucket.ts` `r2Bucket`.
- Produces:
  - `class Metronome extends DurableObject<AntennaEnv>` with `renew(lease: Lease | null): Promise<MetronomeStatus>` and `alarm(): Promise<void>`;
  - `interface MetronomeNamespace { idFromName(name): DurableObjectId; get(id): unknown }`;
  - `metronomeClient(ns: MetronomeNamespace | undefined, timeoutMs = RENEW_TIMEOUT_MS): MetronomeClient`, which rejects inside `renew` on a missing binding or a timeout;
  - `AntennaEnv.METRONOME_DO: DurableObjectNamespace<Metronome>` (the switch, `METRONOME`, comes from `ClockEnv`, Task 2);
  - `src/index.ts` re-exports `Metronome`.

- [ ] **Step 1: Write the failing tests**

(a) `test/metronome.test.ts`:

```ts
import { env, evictDurableObject, listDurableObjectIds, reset, runDurableObjectAlarm,
         runInDurableObject } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AntennaEnv } from "../src/env";
import { type Lease, METRONOME_LEASE_MS, METRONOME_NAME, STORAGE_KEYS } from "../src/metronome-core";
import { type Metronome, metronomeClient } from "../src/metronome";

const D = 10_240;
const e = env as unknown as AntennaEnv;
const stub = () => e.METRONOME_DO.get(e.METRONOME_DO.idFromName(METRONOME_NAME));

/** The test env carries wrangler.jsonc's METRONOME ("off"); switch this
 * instance's env, as a deploy of the var would. Lasts until the object is
 * evicted or reset. */
const setSwitch = (value: string) =>
  runInDurableObject(stub(), (o: Metronome) => {
    const self = o as unknown as { env: AntennaEnv };
    self.env = { ...self.env, METRONOME: value };
  });

/** A play lease 3 s into a segment, so the alarm it arms is ~7 s away: the
 * runtime fires real alarms on time, and one 25 ms away would race the test. */
function playLease(nowMs: number): Lease {
  const epoch = new Date(nowMs - 100 * D - 3_000).toISOString();
  return { kind: "play", verdictAt: nowMs, validUntil: nowMs + METRONOME_LEASE_MS, blocked: false,
           horizon: { epoch_id: "e1", epoch, d: 10.24, first: 0, last: 1_000_000, published_at: epoch, container: "adts",
                      fallback_version: "v1" },
           fallback: { len: 7, notice: "fallback/v1/notice.aac" } };
}

const storedKeys = () =>
  runInDurableObject(stub(), async (_o: Metronome, state) => [...(await state.storage.list()).keys()].sort());
const pendingAlarm = () => runInDurableObject(stub(), (_o: Metronome, state) => state.storage.getAlarm());

afterEach(async () => {
  vi.restoreAllMocks();
  await reset(); // storage, alarms, R2 and instances: DO storage is not isolated per test otherwise
});

describe("the Metronome Durable Object", () => {
  it("is off as committed: renew answers off, arms nothing, stores nothing", async () => {
    const st = await stub().renew(playLease(Date.now()));
    expect(st.applied).toBe("off");
    expect(await pendingAlarm()).toBeNull();
    expect(await storedKeys()).toEqual([]);
    expect(await e.BUCKET.get("live.m3u8")).toBeNull();
  });

  it("on: renew writes live.m3u8 through the R2 binding, stores within the fixed key set and arms the alarm", async () => {
    await setSwitch("on");
    const st = await stub().renew(playLease(Date.now()));
    expect(st).toMatchObject({ applied: "accepted", lease: "play", wrote: true });
    const obj = await e.BUCKET.get("live.m3u8");
    expect(obj!.httpMetadata).toMatchObject({ contentType: "application/vnd.apple.mpegurl",
                                              cacheControl: "public, max-age=5" });
    expect(await obj!.text()).toContain("seg/e1/");
    expect(await pendingAlarm()).toEqual(expect.any(Number));
    for (const k of await storedKeys()) expect(STORAGE_KEYS as readonly string[]).toContain(k);
  });

  it("the alarm ticks and re-arms; a full cycle stores exactly the fixed key set", async () => {
    const logs = vi.spyOn(console, "error").mockImplementation(() => {});
    await setSwitch("on");
    const s = stub();
    await s.renew(playLease(Date.now()));
    const armed = await pendingAlarm();
    expect(await runDurableObjectAlarm(s)).toBe(true);
    // The handler saw no pending alarm (getAlarm() is null while it runs), so it
    // ticked as a genuine delivery and re-armed later, not as a duplicate.
    expect(await pendingAlarm()).toBeGreaterThan(armed!);
    expect(logs.mock.calls.flat().join("\n")).not.toContain("metronome-duplicate");
    // A stall (no alarm-confirmed tick for > 30 s): the next renew counts it.
    await runInDurableObject(s, (_o: Metronome, state) => state.storage.put("lastAlarmGoodAt", Date.now() - 60_000));
    await runInDurableObject(s, (_o: Metronome, state) => state.storage.put("playSince", Date.now() - 60_000));
    expect((await s.renew(null)).stalls).toBe(1);
    expect(await storedKeys()).toEqual([...STORAGE_KEYS].sort());
  });

  it("state lives in storage: after eviction (as at a deploy) the lease and the pending alarm are still there", async () => {
    await setSwitch("on");
    await stub().renew(playLease(Date.now()));
    const armed = await pendingAlarm();
    await evictDurableObject(stub());
    expect(await pendingAlarm()).toBe(armed);
    await setSwitch("on"); // the override was memory only
    expect((await stub().renew(null)).lease).toBe("play");
    expect(await runDurableObjectAlarm(stub())).toBe(true);
    expect(await pendingAlarm()).toEqual(expect.any(Number)); // the chain goes on
  });

  it("switched off with an alarm pending: the alarm writes nothing and is not re-armed", async () => {
    await setSwitch("on");
    const s = stub();
    await s.renew(playLease(Date.now()));
    await e.BUCKET.delete("live.m3u8");
    await setSwitch("off");
    expect(await runDurableObjectAlarm(s)).toBe(true);
    expect(await pendingAlarm()).toBeNull();
    expect(await e.BUCKET.get("live.m3u8")).toBeNull();
  });

  it("only the exact string \"on\" enables it", async () => {
    for (const v of ["On", "on ", "1", "true", ""]) {
      await setSwitch(v);
      expect((await stub().renew(playLease(Date.now()))).applied).toBe("off");
    }
  });
});

describe("metronomeClient", () => {
  it("addresses the single instance by its fixed name", async () => {
    await setSwitch("on");
    const client = metronomeClient(e.METRONOME_DO);
    await client.renew(playLease(Date.now()));
    await client.renew(null);
    const ids = await listDurableObjectIds(e.METRONOME_DO);
    expect(ids).toHaveLength(1);
    expect(ids[0].equals(e.METRONOME_DO.idFromName("metronome"))).toBe(true);
  });

  it("asks idFromName for \"metronome\" and nothing else", async () => {
    const names: string[] = [];
    const ns = { idFromName: (n: string) => { names.push(n); return {} as DurableObjectId; },
                 get: () => ({ renew: async () => ({ applied: null }) }) };
    await metronomeClient(ns).renew(null);
    expect(names).toEqual(["metronome"]);
  });

  it("a missing binding rejects inside renew (cron's trigger a), never at construction", async () => {
    const client = metronomeClient(undefined);
    await expect(client.renew(null)).rejects.toThrow(/METRONOME_DO binding is missing/);
  });

  it("a renew that does not answer within the timeout rejects", async () => {
    const ns = { idFromName: () => ({}) as DurableObjectId, get: () => ({ renew: () => new Promise(() => {}) }) };
    await expect(metronomeClient(ns, 20).renew(null)).rejects.toThrow(/renew timed out after 20 ms/);
  });
});
```

(b) `test/wrangler-config.test.ts`: insert immediately before `describe("wrangler.jsonc playlist vars (amendment A4, amended 2026-10-12)", () => {`:

```ts
describe("wrangler.jsonc: the metronome (metronome spec)", () => {
  it("binds one SQLite-backed Durable Object class, Metronome, created by migration v1", () => {
    expect(config.durable_objects).toEqual({ bindings: [{ name: "METRONOME_DO", class_name: "Metronome" }] });
    expect(config.migrations).toEqual([{ tag: "v1", new_sqlite_classes: ["Metronome"] }]);
    expect(config).not.toHaveProperty("exports"); // mutually exclusive with migrations
    const ns = (env as unknown as { METRONOME_DO?: { idFromName?: unknown } }).METRONOME_DO;
    expect(typeof ns?.idFromName).toBe("function");
  });

  it("carries the switch as exactly \"on\" or \"off\" (a typo would silently mean off)", () => {
    expect(["on", "off"]).toContain(config.vars.METRONOME);
  });

  it("is still driven by one cron trigger, every minute", () => {
    expect(config.triggers).toEqual({ crons: ["* * * * *"] });
  });
});

```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/metronome.test.ts test/wrangler-config.test.ts`
Expected: FAIL. `../src/metronome` cannot be resolved, and `config.durable_objects` is undefined.

- [ ] **Step 3: Create `src/metronome.ts`**

```ts
/** The metronome Durable Object (metronome spec): one instance, addressed by
 * cron as idFromName(METRONOME_NAME), writes live.m3u8 on the grid from an
 * alarm chain under the lease cron renews every minute. This file only binds
 * MetronomeEngine (metronome-engine.ts) to the object's storage, alarm, R2
 * binding and env; every rule lives in the engine and metronome-core.ts. */

import { DurableObject } from "cloudflare:workers";
import { r2Bucket } from "./bucket";
import { configFromEnv } from "./clock";
import type { AntennaEnv } from "./env";
import { putLive } from "./live";
import { type Lease, type MetronomeClient, METRONOME_NAME, type MetronomeStatus, RENEW_TIMEOUT_MS, STORAGE_KEYS,
         type StorageKey } from "./metronome-core";
import { MetronomeEngine } from "./metronome-engine";

export class Metronome extends DurableObject<AntennaEnv> {
  private readonly engine: MetronomeEngine;

  constructor(ctx: DurableObjectState, env: AntennaEnv) {
    super(ctx, env);
    const storage = ctx.storage;
    this.engine = new MetronomeEngine({
      now: () => Date.now(),
      // this.env is read on every call: deploying METRONOME != "on" reaches the object directly.
      switchOn: () => this.env.METRONOME === "on",
      config: () => configFromEnv(this.env),
      load: async () => Object.fromEntries(await storage.get<unknown>([...STORAGE_KEYS])) as
        Partial<Record<StorageKey, unknown>>,
      save: async (changes) => {
        const puts: Record<string, unknown> = {};
        const deletes: string[] = [];
        for (const [k, v] of Object.entries(changes)) {
          if (v === undefined) deletes.push(k);
          else puts[k] = v;
        }
        if (Object.keys(puts).length > 0) await storage.put(puts);
        if (deletes.length > 0) await storage.delete(deletes);
      },
      getAlarm: () => storage.getAlarm(),
      setAlarm: (atMs) => storage.setAlarm(atMs),
      deleteAlarm: () => storage.deleteAlarm(),
      putLive: (body, liveMaxAge) => putLive(r2Bucket(this.env.BUCKET), body, liveMaxAge),
      timer: (ms) => {
        let id: ReturnType<typeof setTimeout> | undefined;
        const done = new Promise<void>((resolve) => { id = setTimeout(resolve, ms); });
        return { done, clear: () => { if (id !== undefined) clearTimeout(id); } };
      },
      log: (event, fields) => console.error(JSON.stringify({ event, ...fields })),
    });
  }

  /** Cron's RPC, every minute (metronome spec, "renew(lease | null)"). */
  async renew(lease: Lease | null): Promise<MetronomeStatus> {
    return this.engine.renew(lease);
  }

  async alarm(): Promise<void> {
    await this.engine.alarm();
  }
}

/** The namespace surface the client needs (a DurableObjectNamespace, or a test fake). */
export interface MetronomeNamespace {
  idFromName(name: string): DurableObjectId;
  get(id: DurableObjectId): unknown;
}

/** The single instance, addressed by its fixed name; each renew bounded by
 * timeoutMs (RENEW_TIMEOUT_MS: over two 5 s PUT timeouts, plus slack). The
 * stub is made inside renew, so anything that fails -- a missing binding
 * included -- rejects there, and cron treats it as trigger (a), like a timeout. */
export function metronomeClient(ns: MetronomeNamespace | undefined, timeoutMs = RENEW_TIMEOUT_MS): MetronomeClient {
  return {
    async renew(lease) {
      let id: ReturnType<typeof setTimeout> | undefined;
      try {
        if (ns === undefined) throw new Error("the METRONOME_DO binding is missing");
        const stub = ns.get(ns.idFromName(METRONOME_NAME)) as MetronomeClient;
        return await Promise.race([
          stub.renew(lease),
          new Promise<never>((_, reject) => {
            id = setTimeout(() => reject(new Error(`renew timed out after ${timeoutMs} ms`)), timeoutMs);
          }),
        ]);
      } finally {
        if (id !== undefined) clearTimeout(id);
      }
    },
  };
}
```

- [ ] **Step 4: `src/env.ts`** — replace the whole file with:

```ts
import type { AlertEnv } from "./alerts";
import type { ClockEnv } from "./clock";
import type { GuardEnv } from "./guard";
import type { Metronome } from "./metronome";

/** Everything the Worker reads from its environment: wrangler vars, Worker
 * secrets (account details and tokens, never in the repo) and bindings. */
export interface AntennaEnv extends ClockEnv, GuardEnv, AlertEnv {
  BUCKET: R2Bucket;
  /** The metronome Durable Object (one instance, idFromName("metronome")). */
  METRONOME_DO: DurableObjectNamespace<Metronome>;
}
```

- [ ] **Step 5: `src/index.ts`** — the class must be exported from the `main` module. Replace

```ts
import { guardConfigFromEnv, guardStep } from "./guard";
```

with

```ts
import { guardConfigFromEnv, guardStep } from "./guard";

export { Metronome } from "./metronome";
```

- [ ] **Step 6: `wrangler.jsonc`** (three edits; whole-line `//` comments only, no trailing commas: `test/wrangler-config.test.ts` parses it that way)

Replace

```jsonc
    "ALERT_REPEAT_HOURS": "6",
    "STATION_NAME": "llama radio"
  },
```

with

```jsonc
    "ALERT_REPEAT_HOURS": "6",
    "STATION_NAME": "llama radio",
    // The rollback switch (metronome spec): only the exact string "on" enables
    // the metronome. Anything else is off: cron runs its own loop exactly as
    // before, and the Durable Object deletes its alarm and writes nothing.
    // docs/playout-setup.md section 4 step 7 has the rollout and the rollback.
    "METRONOME": "off"
  },
```

Insert immediately before the line `  // Alert email (Email Routing). Unrestricted on purpose: a send_email binding`:

```jsonc
  // The metronome (docs/superpowers/specs/2026-10-14-antenna-metronome-design.md):
  // a SQLite-backed Durable Object that writes live.m3u8 on the grid from an
  // alarm chain under a lease cron renews every minute. One instance, addressed
  // as idFromName("metronome"). Migration form: `migrations` with
  // `new_sqlite_classes`, the form the alarm probe deployed with this wrangler
  // (4.149.0); the declarative `exports` field is the newer alternative, and the
  // two are mutually exclusive. Both pass `wrangler deploy --dry-run`.
  "durable_objects": { "bindings": [{ "name": "METRONOME_DO", "class_name": "Metronome" }] },
  "migrations": [{ "tag": "v1", "new_sqlite_classes": ["Metronome"] }],
```

Replace

```jsonc
  // One log line per invocation (~1,440/day) stays inside the free allowance.
  "observability": { "enabled": true }
```

with

```jsonc
  // Workers Logs: one clock line per cron invocation (~1,440/day), plus the
  // metronome's: each Durable Object invocation (alarm or renew) is itself a
  // log event (~10k/day), and the object logs only anomalies, once per episode.
  // All far inside the included allowance.
  "observability": { "enabled": true }
```

- [ ] **Step 7: Run everything, and dry-run the bundle**

Run: `cd antenna && npm test && npm run typecheck`
Expected: `Tests  342 passed (342)` (13 new), tsc silent. Run the full suite **twice**: a test that races a real alarm shows up as an intermittent failure under full-suite load, never in a single file.

Run: `cd antenna && npx wrangler deploy --dry-run --outdir /tmp/antenna-dryrun`
Expected: the binding table lists `env.METRONOME_DO (Metronome)  Durable Object` and `env.METRONOME ("off")`, then `--dry-run: exiting now.` No warning about migrations or exports.

- [ ] **Step 8: Commit**

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/antenna-metronome
git -C "$W" add antenna/src/metronome.ts antenna/src/env.ts antenna/src/index.ts antenna/wrangler.jsonc \
                antenna/test/metronome.test.ts antenna/test/wrangler-config.test.ts
git -C "$W" commit -m "feat(antenna): the Metronome Durable Object, its binding, migration v1 and the METRONOME switch (off)"
```

---

### Task 7: Cron — the lease table, the fallback decision, `metronome-down`

**Model hint:** opus (the cron fallback decision: strict surface)

The spec's "Cron invocation (every minute)" steps 4–6, its lease table, the `runClock` contract, and the rollback switch on cron's side. Every path through `runClock` calls `renew` exactly once, with the argument the table names:

| Cron outcome | `renew` argument | Fallback loop |
|---|---|---|
| guard verdict unknown, or guard crashed | `renew(null)` | never writes |
| verdict known unblocked; inputs read threw, horizon missing/unreadable, or no grid | `renew(null)` | never writes |
| verdict known blocked; inputs unusable | `renew(hold)` | never writes |
| horizon refused (`d` ≠ 10.24) | `renew(hold)` | never writes |
| verdict known, horizon accepted | `renew(play{blocked, horizon, fallback})` | may run |

The fallback (cron's own loop) runs only on the last row, and only when `fallbackReason` names a trigger. Any trigger raises `metronome-down`. `complete` is still set only at the end of the normal path. With the metronome off (`deps.metronome` absent), nothing changes: no renew, and the loop as today.

**Files:**
- Modify: `src/clock.ts`, `src/index.ts`, `src/alerts.ts`, `test/alerts.test.ts`
- Create: `test/clock-metronome.test.ts`

**Interfaces:**
- Consumes: `metronome-core` `fallbackReason`, `holdLease`, `playLease`, `Lease`, `MetronomeClient`, `MetronomeStatus`; `live.ts` `offairWithoutFallback`; Task 6's `metronomeClient`.
- Produces:
  - `ClockDeps.metronome?: MetronomeClient`;
  - `ClockResult.metronome: MetronomeLine | null`, with `MetronomeLine { sent: "play" | "blocked" | "hold" | null; status: MetronomeStatus | null; error: string | null; fallback: string | null }`. It goes on the clock line as `metronome`;
  - `CLOCK_KEYS` gains `metronome-down`.

- [ ] **Step 1: Write the failing tests**

(a) `test/alerts.test.ts`: replace

```ts
                   "offair-without-fallback", "clock-inputs", "clock-failed"];
```

with

```ts
                   "offair-without-fallback", "clock-inputs", "clock-failed", "metronome-down"];
```

(b) `test/clock-metronome.test.ts`:

```ts
import { createExecutionContext, createScheduledController, env, reset, runInDurableObject,
         waitOnExecutionContext } from "cloudflare:test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type AlertBatch, type ClockConfig, runClock } from "../src/clock";
import type { AlertCondition } from "../src/conditions";
import type { AntennaEnv } from "../src/env";
import type { GuardOutcome } from "../src/guard";
import worker from "../src/index";
import type { Metronome } from "../src/metronome";
import { type Lease, METRONOME_LEASE_MS, METRONOME_NAME, type MetronomeClient,
         type MetronomeStatus } from "../src/metronome-core";
import { fakeTime, MemoryBucket } from "./support";

const E = Date.parse("2026-10-10T12:00:00.000Z");
const D = 10_240;
const CFG: ClockConfig = { window: 6, grace: 3, offairAfterMs: 86_400_000, loopMs: 75_000, liveMaxAge: 5,
                           leadFloorMs: 16 * 3_600_000 };
const AT = E + 50 * D + 300;

const guardSays = (blocked: boolean | null, tripped = false) =>
  async (): Promise<GuardOutcome> => ({ blocked, tripped: blocked === null ? null : tripped,
                                        offair: blocked === null ? null : blocked && !tripped, doc: null, conditions: [] });

function horizonDoc(epochMs: number) {
  const iso = new Date(epochMs).toISOString();
  return { epoch_id: "e1", epoch: iso, d: 10.24, first: 0, last: 1_000_000, published_at: iso, container: "adts",
           fallback_version: "v1" };
}
const FALLBACK = { len: 7, notice: "fallback/v1/notice.aac" };

function station(bucket = new MemoryBucket()) {
  bucket.seed("state/horizon.json", horizonDoc(E));
  bucket.seed("fallback/v1/index.json", FALLBACK);
  return bucket;
}

const healthy = (s: Partial<MetronomeStatus> = {}): MetronomeStatus =>
  ({ applied: "accepted", lease: "play", wrote: true, lastAlarmGoodAt: AT, stalledMs: 0, stalls: 0, leaseVerdictAt: AT,
     ...s });

/** A metronome stand-in: records every lease it is sent and answers `answer(lease)`. */
function fakeMetronome(answer: (l: Lease | null) => MetronomeStatus | Promise<MetronomeStatus> =
                         (l) => healthy({ applied: l === null ? null : "accepted" })) {
  const sent: (Lease | null)[] = [];
  const client: MetronomeClient = { renew: async (l) => { sent.push(l); return answer(l); } };
  return { client, sent };
}

type Run = { r: Awaited<ReturnType<typeof runClock>> | null; error: unknown; batch: AlertBatch | null; keys: string[];
             bucket: MemoryBucket; clock: ReturnType<typeof fakeTime> };

async function run(o: { guard?: () => Promise<GuardOutcome>; bucket?: MemoryBucket; metronome?: MetronomeClient;
                        at?: number }): Promise<Run> {
  const bucket = o.bucket ?? station();
  const at = o.at ?? AT;
  const clock = fakeTime(at + 40);
  const out: Run = { r: null, error: null, batch: null, keys: [], bucket, clock };
  try {
    out.r = await runClock({ bucket, ...clock, scheduledTime: at, config: CFG, guard: o.guard ?? guardSays(false),
                             metronome: o.metronome,
                             alerts: async (cs: AlertCondition[], _n, b) => { out.keys = cs.map((c) => c.key); out.batch = b; } });
  } catch (e) {
    out.error = e;
  }
  return out;
}

const playlistPuts = (b: MemoryBucket) => b.puts("live.m3u8");

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the lease table: what cron passes to renew, by its own outcome", () => {
  it("guard unknown or crashed: renew(null), and the fallback never writes", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    for (const guard of [guardSays(null), async (): Promise<GuardOutcome> => { throw new Error("x"); }]) {
      const m = fakeMetronome(() => { throw new Error("dead"); }); // even with the DO dead
      const out = await run({ guard, metronome: m.client });
      expect(m.sent).toEqual([null]);
      expect(playlistPuts(out.bucket)).toBe(0);
      expect(out.keys).toContain("metronome-down");
    }
  });

  it("verdict known unblocked, inputs unusable (read threw, missing, unreadable, bad epoch): renew(null), no cron PUT", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const threw = station();
    threw.failGets.add("state/horizon.json");
    const missing = new MemoryBucket();
    const corrupt = new MemoryBucket();
    corrupt.seed("state/horizon.json", "{not json");
    const badEpoch = station();
    badEpoch.seed("state/horizon.json", { ...horizonDoc(E), epoch: "nonsense" });
    for (const bucket of [threw, missing, corrupt, badEpoch]) {
      const m = fakeMetronome(() => { throw new Error("dead"); });
      await run({ bucket, metronome: m.client });
      expect(m.sent).toEqual([null]);
      expect(playlistPuts(bucket)).toBe(0);
    }
  });

  it("verdict known blocked, inputs unusable: renew(hold), no cron PUT", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const threw = station();
    threw.failGets.add("state/horizon.json");
    const missing = new MemoryBucket();
    const badEpoch = station();
    badEpoch.seed("state/horizon.json", { ...horizonDoc(E), epoch: "nonsense" });
    for (const bucket of [threw, missing, badEpoch]) {
      const m = fakeMetronome(() => { throw new Error("dead"); });
      await run({ bucket, guard: guardSays(true, true), metronome: m.client });
      expect(m.sent).toEqual([{ kind: "hold", verdictAt: AT + 40, validUntil: AT + 40 + METRONOME_LEASE_MS }]);
      expect(playlistPuts(bucket)).toBe(0);
    }
  });

  it("horizon refused: renew(hold) blocked or not, no cron PUT", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    for (const guard of [guardSays(false), guardSays(true, true)]) {
      const bucket = station();
      bucket.seed("state/horizon.json", { ...horizonDoc(E), d: 1 });
      const m = fakeMetronome(() => { throw new Error("dead"); });
      await run({ bucket, guard, metronome: m.client });
      expect(m.sent.map((l) => l?.kind)).toEqual(["hold"]);
      expect(playlistPuts(bucket)).toBe(0);
    }
  });

  it("verdict known, horizon accepted: a play lease with the verdict, horizon and fallback, ordered by the guard's start", async () => {
    for (const blocked of [false, true]) {
      const m = fakeMetronome();
      const clock = fakeTime(AT + 40);
      await runClock({ bucket: station(), ...clock, scheduledTime: AT, config: CFG, metronome: m.client,
                       guard: async () => { await clock.sleep(2_000); return guardSays(blocked, blocked)(); } });
      expect(m.sent).toEqual([{ kind: "play", verdictAt: AT + 40, validUntil: AT + 2_040 + METRONOME_LEASE_MS,
                                blocked, horizon: horizonDoc(E), fallback: FALLBACK }]);
    }
  });

  it("renews exactly once per invocation, on every path", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const refused = station();
    refused.seed("state/horizon.json", { ...horizonDoc(E), d: 1 });
    const threw = station();
    threw.failGets.add("state/horizon.json");
    const cases = [{ guard: guardSays(null) }, { bucket: new MemoryBucket() }, { bucket: refused }, { bucket: threw },
                   {}, { guard: guardSays(true, true) }];
    for (const c of cases) {
      const m = fakeMetronome();
      await run({ ...c, metronome: m.client });
      expect(m.sent).toHaveLength(1);
    }
  });
});

describe("a healthy metronome", () => {
  it("cron writes no playlist, the batch is complete, the clock line carries the status", async () => {
    const m = fakeMetronome();
    const out = await run({ metronome: m.client });
    expect(playlistPuts(out.bucket)).toBe(0);
    expect(out.batch).toEqual({ complete: true, guardComplete: true });
    expect(out.r!.metronome).toEqual({ sent: "play", status: healthy(), error: null, fallback: null });
    expect(out.keys).not.toContain("metronome-down");
  });

  it("a blocked lease that the DO wrote: no cron PUT either", async () => {
    const m = fakeMetronome(() => healthy({ lease: "blocked" }));
    const out = await run({ guard: guardSays(true, true), metronome: m.client });
    expect(m.sent[0]).toMatchObject({ kind: "play", blocked: true });
    expect(playlistPuts(out.bucket)).toBe(0);
  });

  it("guard unknown with a healthy renew(null) stays incomplete: no guard-family key resolves", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const out = await run({ guard: guardSays(null), metronome: fakeMetronome().client });
    expect(out.batch).toEqual({ complete: false, guardComplete: false });
  });

  it("offair-without-fallback is raised by cron from its own inputs even though the DO writes", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = new MemoryBucket();
    bucket.seed("state/horizon.json", horizonDoc(E)); // no fallback index
    const out = await run({ bucket, guard: guardSays(true, true), metronome: fakeMetronome().client });
    expect(out.keys).toContain("offair-without-fallback");
    expect(out.r!.offairWithoutFallback).toMatch(/ENDLIST-only/);
    expect(playlistPuts(bucket)).toBe(0);
  });

  it("a single stall: no fallback, no alert, stalledMs on the clock line", async () => {
    const out = await run({ metronome: fakeMetronome(() => healthy({ stalls: 1, stalledMs: 41_000 })).client });
    expect(playlistPuts(out.bucket)).toBe(0);
    expect(out.keys).not.toContain("metronome-down");
    expect(out.r!.metronome!.status!.stalledMs).toBe(41_000);
  });

  it("superseded: no fallback (the DO keeps a newer lease)", async () => {
    const out = await run({ metronome: fakeMetronome(() => healthy({ applied: "superseded", wrote: null })).client });
    expect(playlistPuts(out.bucket)).toBe(0);
    expect(out.keys).not.toContain("metronome-down");
  });
});

describe("the fallback: cron's own loop, and metronome-down", () => {
  const triggers: [string, () => MetronomeStatus | Promise<MetronomeStatus>][] = [
    ["(a) renew throws", () => { throw new Error("RPC failed"); }],
    ["(b) invalid", () => healthy({ applied: "invalid", lease: "none", wrote: null })],
    ["(b) off (version skew)", () => healthy({ applied: "off", lease: "none", wrote: null })],
    ["(b) wrote false", () => healthy({ wrote: false })],
    ["(c) stalls >= 2", () => healthy({ stalls: 2, stalledMs: 70_000 })],
  ];
  for (const [what, answer] of triggers) {
    it(`${what}: the legacy loop runs (as many PUTs as today), metronome-down is raised, the batch is complete`, async () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      const out = await run({ metronome: fakeMetronome(answer).client });
      expect(out.r!.puts).toBe(8); // immediate + boundaries 51..57, exactly the off-mode count
      expect(out.keys).toContain("metronome-down");
      expect(out.r!.metronome!.fallback).toEqual(expect.any(String));
      expect(out.batch).toEqual({ complete: true, guardComplete: true });
    });
  }

  it("a blocked lease the DO did not write: cron writes the off-air playlist", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const out = await run({ guard: guardSays(true, true),
                            metronome: fakeMetronome(() => healthy({ lease: "blocked", wrote: false })).client });
    expect(playlistPuts(out.bucket)).toBe(1);
    expect(out.bucket.objects.get("live.m3u8")!.body).toContain("#EXT-X-ENDLIST");
  });

  it("a hold the DO did not answer: metronome-down, but the fallback never writes", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const bucket = station();
    bucket.seed("state/horizon.json", { ...horizonDoc(E), d: 1 });
    const out = await run({ bucket, metronome: fakeMetronome(() => { throw new Error("dead"); }).client });
    expect(out.keys).toEqual(expect.arrayContaining(["horizon-refused", "metronome-down"]));
    expect(playlistPuts(bucket)).toBe(0);
  });
});

describe("scheduled handler with the metronome", () => {
  const noSecrets = (metronome: string) =>
    ({ ...env, METRONOME: metronome, LOOP_SECONDS: "0", CF_ACCOUNT_ID: undefined, CF_ZONE_ID: undefined,
       CF_ANALYTICS_TOKEN: undefined, CF_WAF_TOKEN: undefined, NTFY_URL: undefined, NTFY_TOKEN: undefined,
       ALERT_EMAIL: undefined, ALERT_EMAIL_FROM: undefined, ALERT_EMAIL_TO: undefined }) as unknown as AntennaEnv;
  const e = env as unknown as AntennaEnv;
  const clockLine = (spy: { mock: { calls: unknown[][] } }) =>
    spy.mock.calls.map((c) => { try { return JSON.parse(String(c[0])); } catch { return null; } })
      .find((o) => o?.event === "clock");
  const seed = async () => {
    // 3 s into a segment, so the DO's first alarm is ~7 s away and cannot race the test.
    await e.BUCKET.put("state/horizon.json", JSON.stringify(horizonDoc(Date.now() - 100 * D - 3_000)));
    await e.BUCKET.put("fallback/v1/index.json", JSON.stringify(FALLBACK));
  };
  const fire = async (environment: AntennaEnv) => {
    const ctx = createExecutionContext();
    await worker.scheduled!(createScheduledController({ scheduledTime: Date.now(), cron: "* * * * *" }), environment, ctx);
    await waitOnExecutionContext(ctx);
  };

  afterEach(async () => {
    await reset();
  });

  it("METRONOME on, the DO on too: the DO writes live.m3u8, cron does not, the clock line has the status", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in tests"));
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    await seed();
    await runInDurableObject(e.METRONOME_DO.get(e.METRONOME_DO.idFromName(METRONOME_NAME)), (o: Metronome) => {
      const self = o as unknown as { env: AntennaEnv };
      self.env = { ...self.env, METRONOME: "on" };
    });
    await fire(noSecrets("on"));
    const line = clockLine(log);
    expect(line.puts).toBe(0);
    expect(line.metronome).toMatchObject({ sent: "play", status: { applied: "accepted", wrote: true }, fallback: null });
    expect(await (await e.BUCKET.get("live.m3u8"))!.text()).toContain("seg/e1/");
  });

  it("METRONOME on for cron but off in the DO (version skew): cron falls back and raises metronome-down", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in tests"));
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    await seed();
    await fire(noSecrets("on"));
    const line = clockLine(log);
    expect(line.metronome).toMatchObject({ status: { applied: "off" }, fallback: expect.stringMatching(/applied=off/) });
    expect(line.puts).toBe(1);
    expect(line.alerts).toContain("metronome-down");
  });

  it("METRONOME off (as committed): cron's loop exactly as before, no renew", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in tests"));
    const log = vi.spyOn(console, "log").mockImplementation(() => {});
    await seed();
    await fire(noSecrets(String(e.METRONOME)));
    const line = clockLine(log);
    expect(line.metronome).toBeNull();
    expect(line.puts).toBe(1);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd antenna && npx vitest run test/clock-metronome.test.ts test/alerts.test.ts`
Expected: FAIL. `m.sent` is `[]` (`runClock` ignores `metronome`), `out.r!.metronome` is undefined, and `CLOCK_KEYS` lacks `metronome-down`.

- [ ] **Step 3: `src/alerts.ts`** — replace

```ts
  "clock-inputs", "clock-failed",
]);
```

with

```ts
  "clock-inputs", "clock-failed", "metronome-down",
]);
```

- [ ] **Step 4: `src/clock.ts`** (fourteen edits, in order; each `old` text is exactly as Tasks 1–3 left it)

(1) Replace

```ts
import { type LiveSource, putLive, renderLive } from "./live";
import type { FallbackIndex, PlaylistConfig } from "./playlist";
```

with

```ts
import { type LiveSource, offairWithoutFallback, putLive, renderLive } from "./live";
import { fallbackReason, holdLease, type Lease, type MetronomeClient, type MetronomeStatus,
         playLease } from "./metronome-core";
import type { FallbackIndex, PlaylistConfig } from "./playlist";
```

(2) In `ClockDeps`, replace

```ts
  alerts?: (conditions: AlertCondition[], nowMs: number, batch: AlertBatch) => Promise<void>;
}
```

with

```ts
  alerts?: (conditions: AlertCondition[], nowMs: number, batch: AlertBatch) => Promise<void>;
  /** The metronome (metronome spec), given only when METRONOME is exactly "on".
   * It is renewed every invocation, on every path, with the lease the lease
   * table names; cron's own loop then runs only as the fallback, and only with
   * a known verdict and an accepted horizon. Absent: cron's loop exactly as
   * before. */
  metronome?: MetronomeClient;
}
```

(3) In `ClockResult`, replace

```ts
  /** Keys of the alert conditions raised this invocation. */
  alerts: string[];
}
```

with

```ts
  /** Keys of the alert conditions raised this invocation. */
  alerts: string[];
  /** The renew this invocation made (the clock line's `metronome`), or null
   * when the metronome is off. */
  metronome: MetronomeLine | null;
}

/** One invocation's renew, for the clock line. */
export interface MetronomeLine {
  /** What cron passed: a play lease (blocked or not), a hold, or null (a health check). */
  sent: "play" | "blocked" | "hold" | null;
  /** The DO's answer; null when renew threw or timed out. */
  status: MetronomeStatus | null;
  error: string | null;
  /** Why cron fell back (metronome-core fallbackReason), or null. */
  fallback: string | null;
}
```

(4) Replace

```ts
  const result: ClockResult = { puts: 0, skipped: 0, offairWithoutFallback: null, refused: null, blocked: null,
                                guardMs: null, index: "skipped", alerts: [] };
```

with

```ts
  const result: ClockResult = { puts: 0, skipped: 0, offairWithoutFallback: null, refused: null, blocked: null,
                                guardMs: null, index: "skipped", alerts: [], metronome: null };
```

(5) Replace

```ts
  try {
    // 1. The guard, first: it decides blocked and reconciles the kill switch.
    const startedMs = deps.now();
```

with

```ts
  /** Renew the metronome (a no-op when it is off) and say whether cron must
   * fall back. Never throws: a failed or timed-out renew is trigger (a). Every
   * return path below calls it first, with the lease the lease table names. */
  const renew = async (lease: Lease | null): Promise<string | null> => {
    if (!deps.metronome) return null;
    const sent = lease === null ? null : lease.kind === "hold" ? "hold" : lease.blocked ? "blocked" : "play";
    let r: { status: MetronomeStatus } | { error: string };
    try {
      r = { status: await deps.metronome.renew(lease) };
    } catch (e) {
      r = { error: e instanceof Error ? e.message : String(e) };
    }
    const fallback = fallbackReason(lease, r);
    result.metronome = { sent, status: "status" in r ? r.status : null, error: "error" in r ? r.error : null, fallback };
    if (fallback !== null) {
      console.error(JSON.stringify({ event: "metronome-down", reason: fallback, scheduled: deps.scheduledTime }));
      conditions.push({ key: "metronome-down", priority: "high", resolvable: true, title: "Metronome down",
                        message: `The metronome looks dead (${fallback}). The clock's own loop writes live.m3u8 ` +
                                 "this minute when the verdict is known and the horizon accepted." });
    }
    return fallback;
  };
  try {
    // 1. The guard, first: it decides blocked and reconciles the kill switch.
    const startedMs = deps.now(); // the lease's verdictAt: when this guard step's state reads began
```

(6) Replace

```ts
      // Unknown: change nothing (players stall on a stale playlist, toward zero cost).
      console.error(JSON.stringify({ event: "guard-unknown", scheduled: deps.scheduledTime }));
      return result;
```

with

```ts
      // Unknown: change nothing (players stall on a stale playlist, toward zero
      // cost). The metronome keeps its current lease, to its expiry.
      console.error(JSON.stringify({ event: "guard-unknown", scheduled: deps.scheduledTime }));
      await renew(null);
      return result;
```

(7) Replace

```ts
    // 3. The playlist.
    const failedInputs = (e: unknown) => {
```

with

```ts
    // 3. The playlist. Lease table (metronome spec): unusable inputs pass on a
    // known blocked verdict as a hold, and an unblocked one as no lease at all.
    const unusable = () => (blocked ? holdLease(startedMs, deps.now()) : null);
    const failedInputs = (e: unknown) => {
```

(8) Replace

```ts
    try {
      inputs = await readInputs(bucket, blocked);
    } catch (e) {
      throw failedInputs(e);
    }
```

with

```ts
    try {
      inputs = await readInputs(bucket, blocked);
    } catch (e) {
      await renew(unusable());
      throw failedInputs(e);
    }
```

(9) Replace

```ts
                                 "Either nothing is on air yet (transmitter has not published) or the object is corrupt." });
      return result;
```

with

```ts
                                 "Either nothing is on air yet (transmitter has not published) or the object is corrupt." });
      await renew(unusable());
      return result;
```

(10) Replace

```ts
      conditions.push({ key: "horizon-refused", priority: "urgent", resolvable: true, title: "Horizon refused",
                        message: result.refused });
      return result;
```

with

```ts
      conditions.push({ key: "horizon-refused", priority: "urgent", resolvable: true, title: "Horizon refused",
                        message: result.refused });
      await renew(holdLease(startedMs, deps.now())); // a spend refusal, not a transient: the DO stops at once
      return result;
```

(11) Replace

```ts
    try {
      g = gridOf(horizon);
    } catch (e) {
      throw failedInputs(e);
    }
```

with

```ts
    try {
      g = gridOf(horizon);
    } catch (e) {
      await renew(unusable());
      throw failedInputs(e);
    }
```

(12) Replace

```ts
    const cap = putCap(config, g.dMs);
    let lastBody: string | null = null;
    const src: LiveSource = { horizon, fallback: inputs.fallback, offair: inputs.offair };
    const write = async (force: boolean) => {
```

with

```ts
    const src: LiveSource = { horizon, fallback: inputs.fallback, offair: inputs.offair };
    // Ruling: off-air without a usable fallback writes the ENDLIST-only
    // playlist (cap and identical-bytes skip apply), but stays loud: the notice
    // is missing. Raised by cron from its own inputs, once per invocation:
    // before the lease is issued, and again by the loop if it starts later on.
    const noteOffairWithoutFallback = (reason: string | null) => {
      if (result.offairWithoutFallback !== null || reason === null) return;
      result.offairWithoutFallback = reason;
      console.error(JSON.stringify({ event: "offair-without-fallback", reason, epoch_id: horizon.epoch_id,
                                     fallback_version: horizon.fallback_version, scheduled: deps.scheduledTime }));
      conditions.push({ key: "offair-without-fallback", priority: "high", resolvable: true,
                        title: "Off-air without a notice", message: reason });
    };
    noteOffairWithoutFallback(offairWithoutFallback(src, deps.now(), config));
    // 4. The lease: a known verdict and an accepted horizon. A healthy DO writes
    // the playlist from here on; cron's loop runs only when it looks dead.
    if (deps.metronome && (await renew(playLease(startedMs, deps.now(), blocked, horizon, inputs.fallback))) === null) {
      complete = true;
      return result;
    }
    const cap = putCap(config, g.dMs);
    let lastBody: string | null = null;
    const write = async (force: boolean) => {
```

(13) In the `write` closure, replace

```ts
      const { body, offairWithoutFallback: reason } = renderLive(src, nowMs, deps.scheduledTime + config.loopMs, config);
      // Ruling: off-air without a usable fallback writes the ENDLIST-only
      // playlist through the normal path below (cap and identical-bytes skip
      // apply), but stays loud: the notice is missing. Once per invocation.
      if (result.offairWithoutFallback === null) {
        if (reason !== null) {
          result.offairWithoutFallback = reason;
          console.error(JSON.stringify({ event: "offair-without-fallback", reason, epoch_id: horizon.epoch_id,
                                         fallback_version: horizon.fallback_version, scheduled: deps.scheduledTime }));
          conditions.push({ key: "offair-without-fallback", priority: "high", resolvable: true,
                            title: "Off-air without a notice", message: reason });
        }
      }
      if (body === null) return;
```

with

```ts
      const { body, offairWithoutFallback: reason } = renderLive(src, nowMs, deps.scheduledTime + config.loopMs, config);
      noteOffairWithoutFallback(reason);
      if (body === null) return;
```

(14) In `runClock`'s doc comment, replace

```ts
 * Overlapping invocations are harmless: the playlist is a pure function of the
 * clock and the inputs.
```

with

```ts
 * Overlapping invocations are harmless: the playlist is a pure function of the
 * clock and the inputs. With the metronome on (deps.metronome), the playlist
 * is the Durable Object's: cron renews its lease on every path (metronome
 * spec, lease table) and runs that loop only as the fallback.
```

- [ ] **Step 5: `src/index.ts`** — wire the client behind the switch. Replace

```ts
import { guardConfigFromEnv, guardStep } from "./guard";

export { Metronome } from "./metronome";
```

with

```ts
import { guardConfigFromEnv, guardStep } from "./guard";
import { metronomeClient } from "./metronome";

export { Metronome } from "./metronome";
```

and replace

```ts
        alerts: alertSink(bucket, env, fetchFn, now),
      });
```

with

```ts
        alerts: alertSink(bucket, env, fetchFn, now),
        // The rollback switch: only the exact string "on" (metronome spec).
        metronome: env.METRONOME === "on" ? metronomeClient(env.METRONOME_DO) : undefined,
      });
```

- [ ] **Step 6: Run everything (twice), the page check and a dry-run**

Run: `cd antenna && npm test && npm test && npm run typecheck`
Expected: `Tests  364 passed (364)` both times, tsc silent. Every pre-existing clock test passes unchanged: that is the "switch off ⇒ today's loop" guarantee.

Run: `cd antenna && npx wrangler deploy --dry-run --outdir /tmp/antenna-dryrun`
Expected: as in Task 6 (about 84 KiB), `env.METRONOME_DO (Metronome)` listed, `--dry-run: exiting now.`

- [ ] **Step 7: Commit**

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/antenna-metronome
git -C "$W" add antenna/src/clock.ts antenna/src/index.ts antenna/src/alerts.ts antenna/test/alerts.test.ts \
                antenna/test/clock-metronome.test.ts
git -C "$W" commit -m "feat(antenna): cron renews the metronome on every path and falls back only when it looks dead"
```

**Review gate:** the spend path is complete. The orchestrator reports to the parent before Task 8. The report lists each dispatch with its model.

---

### Task 8: Docs — runbook, CLAUDE.md, parent spec as-built

**Model hint:** sonnet

**Files:**
- Modify: `docs/playout-setup.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-10-09-playout-design.md`

**Interfaces:** none (docs). `wrangler.jsonc`'s new comments (Task 6) already point at `docs/playout-setup.md` section 4 step 7.

- [ ] **Step 1: `docs/playout-setup.md`, section 4**

Append to step 5 (the clock's spend bounds), as its last sentence:

> With the metronome on (step 7), the Durable Object adds bounds of its own: at most 10 playlist PUTs and 12 alarm invocations per rolling minute, a 5 s bound on each PUT, a fixed set of 8 storage keys, and no alarm chain except while the playlist is live (never while blocked, held, or past its 15-minute lease).

Add step 7 after step 6:

> 7. **The metronome** (`docs/superpowers/specs/2026-10-14-antenna-metronome-design.md`). With `"METRONOME": "on"` in `wrangler.jsonc`, a Durable Object (`Metronome`, one instance) writes `live.m3u8` at every grid boundary from an alarm chain, under a 15-minute lease that the clock renews every minute with the guard's verdict, the horizon and the fallback. The object never reads R2 and never decides blocked. The clock's own loop runs only when the object looks dead (a renew that fails or times out, a play lease not accepted or not written, or two consecutive renews that find the chain stalled), and then raises `metronome-down`. **Any other value is the rollback:** the clock's loop exactly as before, and the object deletes its alarm at its next invocation. Consequences of the lease: while cron is dead, the station keeps playing for up to 15 minutes on the last verdict, and `transmitter offair on` cannot take effect in that window (the WAF kill switch still can). Rollout, rollback and verification are in section 9.

- [ ] **Step 2: `docs/playout-setup.md`, section 7.1** — add a row after `clock-failed`:

```
| `metronome-down` | clock | high | resolvable |
```

- [ ] **Step 3: `docs/playout-setup.md`, append section 9** (at the end of the file):

````markdown
## 9. The metronome: rollout, rollback, verification

Spec: `docs/superpowers/specs/2026-10-14-antenna-metronome-design.md` (Rollout). Record results in `docs/superpowers/<date>-metronome-verification.md`. Run from the main checkout's `antenna/` with `.env` loaded (`set -a; . ./.env; set +a`: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_ANALYTICS_TOKEN`). `.env` is gitignored, so a worktree has none.

1. **Tear down the alarm probe** (its Durable Object would otherwise appear in the account-wide DO meters). From `~/lma-radio-ops/do-alarm-probe`:
   ```
   npx wrangler deploy --var STOP:1     # cron deletes the alarm; alarms stop re-arming
   # wait ~1 min; confirm no new "event":"alarm" lines arrive in tail.jsonl, then:
   pkill -f 'cli.js tail alarm-probe'
   npx wrangler delete                  # removes the Worker (name from its wrangler.jsonc)
   ```
   If `wrangler delete` refuses because of the Durable Object class, add `{ "tag": "v2", "deleted_classes": ["Probe"] }` to the probe's `migrations`, remove its `durable_objects` binding and its `ensure` call, `npx wrangler deploy`, then `npx wrangler delete`.
2. **Deploy with `"METRONOME": "off"`** (as committed): `npm ci && npm test && npm run typecheck`, `npx wrangler deploy --dry-run` (it lists `env.METRONOME_DO (Metronome)` and `env.METRONOME ("off")`), then `npx wrangler deploy` (its output ends with `schedule: * * * * *`). The class now exists, and the guard reads the three DO meters. **Pass** only when, at the guard's next evaluation (within 15 min), `npx wrangler r2 object get lma-radio/state/guard.json --remote --pipe | python3 -m json.tool` shows `last_error: null` and `evaluation.period_to_date` carrying all seven meters (`workersRequests`, `r2ClassA`, `r2ClassB`, `r2StorageGbMonth`, `doRequests`, `doDurationGbS`, `doRowsWritten`). Nothing on air changes: the clock's loop writes as before.
3. **Flip on:** set `"METRONOME": "on"` in `wrangler.jsonc`, commit, `npx wrangler deploy`. Within two minutes, `npx wrangler tail antenna --format pretty` shows clock lines with `"metronome":{"sent":"play","status":{"applied":"accepted",...},"fallback":null}` and `"puts":0`, and Durable Object alarm events about every 10 s. The guard's first evaluation after the flip may fail with `the metronome is on but the recent window reads doRequests=0`, and `guard.json` shows that failure until the next evaluation (≤ ~20 min): expected, and harmless (the blind rule needs 6 h).
4. **Verification day:** a 24 h `wrangler tail antenna` and `live.m3u8` poller, including a weekday daytime (section 9.1 below). Deploy twice during the day (`npx wrangler deploy`, no change) and note the times.

**Rollback.** Immediate: `npx wrangler deploy --var METRONOME:off`. The next cron invocation runs its own loop, and the object's next alarm reads `off`, deletes its alarm and writes nothing. A `--var` lasts only until the next plain deploy, so make it durable by committing `"METRONOME": "off"`. If the Worker itself is broken, section 4 step 4's broken-Worker order applies unchanged. Roll back the same way, rather than ride it out, when `metronome-down` persists while `METRONOME` is `"on"` (the object absent or broken): with no Durable Object activity, every guard reading also fails (`doRequests=0`), and the station trips blind after 6 h.

**A dead cron, now.** The object keeps the station playing for at most 15 minutes on its lease, then stops writing and re-arming. The playlist freezes, and hugo's `dead-clock` check alerts (newest segment older than `dead_clock_seconds`, 120 s, on two checks a minute apart); independently hugo alerts `guard-stale` once `guard.json`'s evaluation is older than `guard_stale_minutes` (45). A cron outage is therefore detected ~17-18 minutes after the last renew, against ~3-4 minutes before the metronome. Accepted (spec, Decision 3).

**Known limitations.** An alarm chain that breaks with no error freezes the playlist until the next renew, up to one cron gap (≤ ~200 s on a bad day). It shows on the clock line as `metronome.status.stalledMs` with no alert; two in a row fall back and alert. During a fallback minute both writers may write, and their off-air MEDIA-SEQUENCE can differ (cosmetic: both end in ENDLIST). The object's "logged once" marks are memory only and the object is evicted between ticks, so a persisting anomaly may log every tick (inside the Workers Logs allowance).

### 9.1 Verification-day capture and pass criteria

```
mkdir -p ~/lma-radio-ops/metronome-tail
nohup npx wrangler tail antenna --format json > ~/lma-radio-ops/metronome-tail/tail.jsonl \
  2> ~/lma-radio-ops/metronome-tail/tail.err < /dev/null &
```

Alongside it, an independent poller fetches `live.m3u8` as a listener does, every ~5 s, and logs the fetch time, `MEDIA-SEQUENCE` and the last `PROGRAM-DATE-TIME`. Freezes are measured from it: the Durable Object logs anomalies only once per episode, so its lines are diagnostic, not a freeze record.

```
cat > ~/lma-radio-ops/metronome-tail/poll.py <<'EOF'
import datetime as dt, os, re, time, urllib.request
URL = "https://listen.lma-radio.com/live.m3u8"
OUT = os.path.expanduser("~/lma-radio-ops/metronome-tail/poll.tsv")
while True:
    t0 = time.time()
    try:
        req = urllib.request.Request(URL, headers={"user-agent": "metronome-verification-poller"})
        body = urllib.request.urlopen(req, timeout=10).read().decode()
        seq = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", body)
        pdt = re.findall(r"#EXT-X-PROGRAM-DATE-TIME:(\S+)", body)
        row = f"{seq.group(1) if seq else '-'}\t{pdt[-1] if pdt else '-'}"
    except Exception as e:
        row = f"error\t{type(e).__name__}: {e}"
    with open(OUT, "a") as f:
        f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds')}\t{row}\n")
    time.sleep(max(0.0, 5 - (time.time() - t0)))
EOF
nohup python3 ~/lma-radio-ops/metronome-tail/poll.py > ~/lma-radio-ops/metronome-tail/poll.err 2>&1 < /dev/null &
```

`poll.tsv` has one row per fetch: UTC fetch time, `MEDIA-SEQUENCE`, last `PROGRAM-DATE-TIME` (or `error` and the reason). A freeze is a run of fetches with the same `MEDIA-SEQUENCE`, from the first fetch that shows it to the first that shows the next; normal is ~10 s, give or take the 5 s poll and the 5 s `max-age`.

The capture holds three kinds of event: cron invocations (`executionModel: "stateless"`, `event.cron`, with the `clock` line in `logs`); Durable Object alarms (`executionModel: "durableObject"`, `event.scheduledTime`, `outcome`); and renew RPCs (`executionModel: "durableObject"`, `event.rpcMethod: "renew"`). **Pass:**

- no playlist freeze over 45 s in `poll.tsv` outside a reported `metronome-down`, except silent chain breaks: at most 1-2 in the day, each tied to a single stall on the clock line (provisional: the probe's handler did no R2 PUT);
- the DO meters in `guard.json` (`evaluation.period_to_date.doRequests`, `doDurationGbS`, `doRowsWritten`) agree with the dashboard's billable usage for the period;
- playlist PUTs at most ~one per boundary plus one per renew (≈ 7/min, ≈ 10k/day), counted from the DO and clock lines; below the cron-only rate is expected;
- after each deliberate deploy, the alarm chain continues within ~10 s, or the next renew repairs it within a minute.
````

- [ ] **Step 4: `CLAUDE.md`, the antenna part of "What this is"**

The paragraph that begins `` `transmitter` (dist `llama-transmitter`, CLI `transmitter`) is the playout side `` runs on through the cost guard and the playlist hold-back. Insert the following as a new paragraph at the end of that block, immediately before the line that begins `transmitter must stay Python 3.11-compatible`:

> **The metronome** (`antenna/src/metronome{,-core,-engine}.ts`; spec `docs/superpowers/specs/2026-10-14-antenna-metronome-design.md`). With the var `METRONOME` exactly `"on"`, one SQLite-backed Durable Object (`Metronome`, `idFromName("metronome")`, binding `METRONOME_DO`, migration v1 `new_sqlite_classes`) writes `live.m3u8` from an alarm re-armed at every boundary + 25 ms. It works under a 15-minute lease that cron renews every minute over RPC (`renew(play | hold | null)`), carrying the guard's verdict, the horizon and the fallback. The object never reads R2 and never decides blocked. It accepts a blocked lease or a hold unconditionally, and an unblocked one only when it is strictly newer by `verdictAt`; it computes expiry on its own clock. Cron's own loop runs only as the fallback, raising `metronome-down`: when renew throws or times out (15 s), when a play lease is not accepted or not written, or when two consecutive renews find the chain stalled for over 30 s. Its own spend bounds:
> - ≤ 10 PUTs and ≤ 12 alarms per rolling minute;
> - a 5 s bound on each PUT;
> - a fixed 8-key storage set;
> - the chain ticks only while the playlist is live (never blocked, held or expired).
>
> Anything but `"on"` is the rollback: cron's loop exactly as before, and the object deletes its alarm. The cost guard prices three DO meters (requests, duration in GB-s, rows written); while the switch is `"on"`, an empty recent DO window is a failed reading. Tests: `antenna/test/metronome*.test.ts` and `clock-metronome.test.ts`. **`@cloudflare/vitest-plugin` 1.4.0 does not isolate DO storage per test**, so DO tests `reset()` after each test. Real alarms fire on time in tests, so leases put `now` mid-segment. Rollout and rollback: `docs/playout-setup.md` section 9.

In the Commands section's antenna bullet, append: `` The metronome's switch is the var `METRONOME` (`"on"` enables it; rollback `npx wrangler deploy --var METRONOME:off`, then commit `"off"`): `docs/playout-setup.md` section 9. ``

- [ ] **Step 5: The parent spec's as-built notes** (`docs/superpowers/specs/2026-10-09-playout-design.md`)

At the end of the "antenna (phase 1 minimal, phase 4 full)" section, immediately before the heading `### Spend budget`, add this paragraph:

> *(As built, 2026-10-15, the metronome: `docs/superpowers/specs/2026-10-14-antenna-metronome-design.md`. With `METRONOME = "on"`, a Durable Object writes `live.m3u8` at every grid boundary from an alarm chain under a 15-minute lease that the cron invocation renews every minute; the loop above runs only as the fallback when the object looks dead, raising `metronome-down`. Every playlist rule above is unchanged; one shared module (`antenna/src/live.ts`) builds and PUTs for both writers.)*

In "Cost guard (phase 2)", directly after the bullet that ends `` hugo's dead-clock check are cache hits on `live.m3u8`.)* ``, add a new bullet:

> - *(As built, 2026-10-15, metronome spec: three Durable Object meters, `doRequests` (1M included, $0.15/M), `doDurationGbS` (400k GB-s, $12.50/M) and `doRowsWritten` (50M, $1.00/M), read from `durableObjectsInvocationsAdaptiveGroups` and `durableObjectsPeriodicGroups`. DO rows read and stored bytes are bounded by construction (a fixed key set, capped invocations) and not metered; `durableObjectsStorageGroups` returns no rows for this account. While `METRONOME` is `"on"`, a recent window with zero DO requests or rows written is a failed reading, never zero.)*

- [ ] **Step 6: Check, and commit**

Run: `cd antenna && npm test && npm run typecheck`
Expected: unchanged (364 passed). Docs only; the run confirms that nothing else moved.

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/antenna-metronome
git -C "$W" add docs/playout-setup.md CLAUDE.md docs/superpowers/specs/2026-10-09-playout-design.md
git -C "$W" commit -m "docs: the metronome rollout, rollback and verification; CLAUDE.md and the parent spec as built"
```

---

### Task 9: Rollout and verification day — HUMAN CHECKPOINT

**Model hint:** sonnet (orchestration only; the operator deploys, the parent session analyses)

**The orchestrator stops here and escalates to the parent.** No implementer deploys or calls a Cloudflare API. Prerequisites:

- Tasks 0–8 are merged into `main`, or the operator deploys from the branch, at the operator's choice;
- the final branch review (Fable) has passed.

- [ ] **Step 1 (operator, before any deploy): two read-only checks**

(a) Eyeball https://developers.cloudflare.com/durable-objects/platform/pricing/ (Workers Paid). The plan's figures are requests 1M + $0.15/M, duration 400k GB-s + $12.50/M, rows written 50M + $1.00/M (read 2026-10-14). If any differs, stop: `PRICES` and the pricing test change first.

(b) Run the guard's exact query once, read-only, against the account (the same check the spec author ran on 2026-10-14, now with the shipped `USAGE_QUERY`). Run it from the main checkout's `antenna/`, because `.env` is gitignored and the worktree has none; `METER_TS` reads the query from the branch (once merged, `src/meter.ts`):

```bash
cd /Users/shawn/projects/llama/antenna
set -a; . ./.env; set +a
METER_TS=/Users/shawn/projects/llama/.claude/worktrees/antenna-metronome/antenna/src/meter.ts python3 - <<'EOF'
import datetime as dt, json, os, re, urllib.request
src = open(os.environ["METER_TS"]).read()
q = re.search(r"USAGE_QUERY = `(.*?)`;", src, re.S).group(1).replace("${ROW_LIMIT}", "10000")
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%S.000Z")
start = now.replace(day=11, hour=0, minute=0, second=0) if now.day >= 11 else \
        (now.replace(day=1, hour=0, minute=0, second=0) - dt.timedelta(days=1)).replace(day=11)
rend = now - dt.timedelta(minutes=5)
v = {"account": os.environ["CLOUDFLARE_ACCOUNT_ID"], "start": iso(start), "now": iso(now),
     "recentStart": iso(rend - dt.timedelta(hours=3)), "recentEnd": iso(rend)}
req = urllib.request.Request("https://api.cloudflare.com/client/v4/graphql",
                             data=json.dumps({"query": q, "variables": v}).encode(),
                             headers={"authorization": "Bearer " + os.environ["CLOUDFLARE_ANALYTICS_TOKEN"],
                                      "content-type": "application/json"})
r = json.load(urllib.request.urlopen(req))
print("errors:", r.get("errors"))
acct = r["data"]["viewer"]["accounts"][0]
for k in ("doToDate", "doRecent", "doPeriodicToDate", "doPeriodicRecent"):
    print(k, json.dumps(acct[k])[:200])
EOF
```

**Pass:** `errors: None`, and all four DO aliases are present as lists. They may be `[]` (no DO activity) or carry the probe's rows. Any GraphQL error fails the check: fix the query before deploying, because a broken query fails every evaluation and trips the guard blind after 6 h.

- [ ] **Step 2 (operator): rollout steps 1–2.** Follow `docs/playout-setup.md` section 9 steps 1 (probe teardown) and 2 (deploy with `"off"`). Report:
  - the teardown output (the `STOP:1` deploy, the last alarm line's time, the `wrangler delete` result);
  - the deploy output's binding table;
  - `guard.json`'s `last_error` and `evaluation.period_to_date` at the first evaluation after the deploy.

  **Gate:** do not continue unless `last_error` is `null` and all seven meters are present.

- [ ] **Step 3 (operator): rollout step 3, flip on.** Commit `"METRONOME": "on"` in `wrangler.jsonc` and deploy. Start the 24 h capture and the `live.m3u8` poller (`docs/playout-setup.md` 9.1, both commands) **before** this deploy, so the transition is captured. Report the deploy time, the first two clock lines after it, and whether Durable Object alarm events arrive about every 10 s. Alarms only about once a minute would mean genuine deliveries are being taken for duplicates (spec reading 9): each would skip its re-arm, leaving only the next renew to restart the chain. Roll back at once if so.

- [ ] **Step 4 (operator): verification day.** Leave the capture running ≥ 24 h, including a weekday daytime (10:00-18:00 EDT, where cron lagged worst). Deploy twice with no change, at noted times. At the end, also record `guard.json`'s DO meters and the dashboard's billable Durable Objects usage for the same period (Workers & Pages → Durable Objects, or Billing → Billable usage).

- [ ] **Step 5 (parent session): analyse the capture.** Read `~/lma-radio-ops/metronome-tail/tail.jsonl` (concatenated JSON objects; decode with `json.JSONDecoder().raw_decode` in a loop, as `~/lma-radio-ops/do-alarm-probe/summarize.py` does) and compute:

  1. **Write times.** Collect three kinds of write:
     - each DO alarm event (`executionModel == "durableObject"` and `event.scheduledTime`) with `outcome == "ok"` and no `metronome-put-failed`, `metronome-cap` or `metronome-rearm-failed` in its logs (each such alarm writes one boundary);
     - each renew whose clock line shows `metronome.status.wrote == true`, timed by its cron event's timestamp;
     - each cron fallback write: `puts > 0` on a clock line; its writes run from `started` at about every d up to `scheduled + 75 s`.
  2. **Freezes**, from the poller's `~/lma-radio-ops/metronome-tail/poll.tsv` (9.1): runs of fetches with the same `MEDIA-SEQUENCE`. Count runs over 45 s, 60 s and 75 s, and count fetch errors separately. For each run over 45 s, say whether a `metronome-down` falls inside it, and whether the next clock line shows a single stall (`metronome.status.stalls == 1`, with `stalledMs`): that marks a silent chain break. The write times from (1) explain a freeze; they do not define one.
  3. **Alarm lateness:** `eventTimestamp − Date.parse(event.scheduledTime)`. Report the median, p99 and max, separately for weekday daytime :00-:02 and :30-:32. Also count `canceled` alarm events.
  4. **PUT rate per minute and per day**, from (1). Expect ≈ 6-7/min (≈ 10k/day) and at most ≈ one per boundary plus one per renew.
  5. **Fallbacks:** every `metronome-down` (clock line `metronome.fallback`), with its reason and duration. **Stalls:** the distribution of `metronome.status.stalls` and `stalledMs`.
  6. **The two deliberate deploys.** For each, the gap between the last alarm before it and the first after, and whether the chain survived (alarm events continue within ~10 s) or the next renew repaired it (a single stall, then alarms again).
  7. **Meters:** `guard.json` versus the dashboard, for `doRequests`, `doDurationGbS` and `doRowsWritten` (expect `doDurationGbS` far under the 400k allowance, and `rowsWritten` ~4-6 per tick).
  8. **Anomaly lines by event name:** `metronome-late`, `-expired`, `-hold`, `-lease-invalid`, `-lease-superseded`, `-cap`, `-alarm-cap`, `-null-build`, `-duplicate`, `-alarm-error`, and `offair-without-fallback`.
  9. **Duplicates.** Each `metronome-duplicate` line (once per episode) should sit on an alarm event whose `event.scheduledTime` repeats an earlier event's: a real redelivery. The rule that a pending alarm marks a duplicate (spec reading 9) comes from the docs and the test double, and Task 6's workerd test; this capture is its check on the real runtime. A `metronome-duplicate` on a fresh `scheduledTime`, or alarms arriving about once a minute rather than every ~10 s, refutes it.

  **Pass** (spec, Rollout step 4):
  - no freeze over 45 s in `poll.tsv` outside a reported `metronome-down`, except at most 1-2 silent chain breaks, each tied to a logged single stall;
  - meters agree with the dashboard;
  - PUTs within ~one per boundary plus one per renew;
  - the duplicate check (item 9) holds.

  Write the results to `docs/superpowers/<date>-metronome-verification.md`, with the numbers and the pass/fail per criterion, and commit it. On a fail, the operator decides between rollback (`docs/playout-setup.md` section 9, Rollback) and a fix.

- [ ] **Step 6 (operator): record and close.** Once the verification passes, update the memory file `llama-playout.md` (the operator's own step at session end). Confirm that the alarm-probe Worker no longer appears in the account (`npx wrangler deployments list --name alarm-probe` errors, or the dashboard no longer lists it).

---

## Self-Review (run by the plan author against the spec, 2026-10-15)

**Spec coverage**, section by section:

- **Stakes:** Global Constraints and Review Focus.
- **Decisions 1–4:**
  - the DO is the only writer, with fallback (T7);
  - the lease carries everything (T3, T7);
  - 15 min, on the DO's own clock (T3 `storedLease`);
  - expiry writes nothing (T4 "expiry", T5 "an expired lease").
- **Architecture:**
  - one class, `idFromName("metronome")` (T6 client, test);
  - no routes (T6 config test);
  - cron steps 1–3 unchanged; step 4, renew every invocation with a 15 s timeout (T6 client, T7);
  - step 5, triggers (a)–(c) (T3 `fallbackReason`, T7 tests);
  - the scenario list: accepted, invalid, off, a deploy-invalidated stored lease, a lagging blocked lease, superseded (T3, T4, T7);
  - step 6, alerts after the last write (unchanged; `flush` stays in the `finally`).
- **The lease table:** all five rows (T7 tests), and "every early return calls renew" (T7 "renews exactly once ... on every path").
- **The `runClock` contract:** `offairWithoutFallback` computed before the lease (T7); `complete` set only at the end of the normal path (T7 tests).
- **The rollback switch:** only `"on"` (T2 guard, T6 DO, T7 index); the DO reads `env` itself (T6); `renew` answers `off` (T4, T6).
- **The lease:** the validation list (T3); a bad fallback becomes null (T3, T4); invalid deletes the lease and the alarm (T4); invalid on load is deleted (T3, T4, T5); ordering (T3, T4); expiry negated (T3); persisted (T6 eviction test).
- **The DO's state:** the fixed key set (T3, T5, T6 tests); alarm-confirmed ticks (T5); live (T3); serialized sections (T4, T5 interleave); the PUT timeout clears `lastBody` (T4).
- **renew 1–6 and alarm 1–6:** T4 and T5, step by step. The re-arm try/catch, "never throws", and idempotent duplicates (spec reading 9): T5, with the workerd check in T6.
- **Spend bounds:**
  - one PUT per call (structure);
  - 10 per rolling 60 s, renew's included (T4, T5);
  - 12 alarms (T5);
  - the 5 s timeout (T4);
  - live-only ticking (T4 blocked, T5 stale);
  - refused `d` (T3 validation, T7 hold);
  - duration (meter, T2);
  - the fixed keys (T3, T5, T6);
  - the combined worst case: cron's cap is unchanged (existing tests) and the DO's is capped (T4).
- **Playlist contents:** the shared module (T1), off-air numbering at `now + 75 s` (T4 test), unchanged rules (existing playlist tests).
- **Cost guard:** three meters, prices, the touch points, empty-is-zero for requests and rows, a NaN trips, truncation (T2).
- **Observability:** the anomaly logs (T4, T5), the clock line's `metronome` (T7), the observability comment (T6).
- **Failures and alerts:**
  - `metronome-down` is clock-family (T7);
  - the DO sends no alerts (no channel in `metronome.ts`);
  - the dead-cron behaviour and the known limitations (T8 docs).
- **Rollout 1–4 and the docs:** T8, T9.
- **Testing list:** each bullet maps to a test named in T3–T7. "The existing clock tests keep passing in this mode": T7 step 6.
- **Non-goals:** respected; the guard, WAF, `index.html` and alerts stay in cron.
- **Open question (migration syntax):** answered under "Verified while writing this plan".

**Placeholder scan:** none. Every code step carries its code, every run step its command and expected output.

**Type consistency:** these names are identical across Tasks 3–7:

- `Lease`/`PlayLease`/`HoldLease`/`StoredLease`, `MetronomeStatus`, `MetronomeClient`;
- `MetronomePort` and `MetronomeEngine.renew`/`alarm`;
- `metronomeClient(ns | undefined, timeoutMs)`;
- `ClockDeps.metronome`, `ClockResult.metronome: MetronomeLine | null`;
- `fallbackReason(sent, { status } | { error })`;
- `playLease(verdictAt, issuedAt, blocked, horizon, fallback)`, `holdLease(verdictAt, issuedAt)`;
- `STORAGE_KEYS`;
- `renderLive`/`putLive`/`offairWithoutFallback`.

The scratch run compiled them together.

**Review Focus:** five lines, each with its test in the owning task (T6, T5, T3, T6/T7, T5/T6).
