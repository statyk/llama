VERDICT: APPROVED

### Findings

#### Critical
None.

#### Important
None.

#### Minor

1. **antenna/src/bucket.ts:58-63 (`putJson`): no create-if-absent mode, and the condition is keyed on etag truthiness.** With `etag` undefined (or `""`) the PUT is unconditional. Task 6 depends on this. `task-6-brief.md:576` passes `undefined` when `guard.json` is absent, and `persist` then writes unconditionally. Two overlapping invocations that both find `guard.json` absent therefore race with no protection: a non-trip document can overwrite a trip, against the rule that "a lost race never loses a trip". In practice the damage is bounded. It can only happen on the very first creation of `guard.json`, or after an operator deletes it. Spend is monotonic within a period, so the next evaluation (at most 15 min later) trips again. A blind trip cannot occur at creation. So this is a narrow seam gap, not a hole in Task 1. Fix options, which need measurement first: add an "only if absent" option to `PutOptions`, if the R2 binding supports one (for example an `etagDoesNotMatch: "*"` / `If-None-Match: *` precondition; unverified in workerd/miniflare); or have Task 6 accept and document the first-write window. Either way, use `etag !== undefined` instead of truthiness. Raised for the Task 6 reviewer (see ⚠️).

2. **antenna/test/bucket.test.ts:7-14: nothing pins that a `corrupt` read carries the etag.** Task 6 (`task-6-brief.md:576`) uses `guardRead.etag` for the corrupt case too. If a later edit to `readJsonDoc` dropped `etag` from the corrupt branch, the overwrite of a corrupt `guard.json` would silently become unconditional, and every test would stay green. The `ok` branch's etag is pinned only by the R2 test (`typeof etag === "string"`). Fix: `toMatchObject({ kind: "corrupt", etag: expect.any(String) })`, and the same for `ok` on the MemoryBucket path.

3. **antenna/src/period.ts:15-33: `nowMs` is not validated.** `billingPeriod(NaN, 11)` returns `{startMs: NaN, endMs: NaN}` instead of throwing. Under R3 ("new billing period = the evaluation's period start differs from the latch's"), a NaN start compares unequal to everything, so it would read as a new period and could clear a spend latch. Production `now` is `Date.now()`, so this is latent. A one-line `Number.isFinite(nowMs)` check that throws would make it fail closed, consistent with the `day` refusal.

4. **antenna/test/support.ts:79-81 (`fakeFetch`): when `input` is a `Request`, its method, headers and body are ignored.** Only `init` is read, so `fetch(new Request(url, {method: "POST", body}))` is recorded as a GET with a null body and could match a GET route. Non-string `init.body` (URLSearchParams, Uint8Array) is also recorded as `null`. The briefs for Tasks 3 and 5 call `fetchFn(url, init)` with string bodies, so this is latent. A one-line doc comment ("call as fetch(url, init) with a string body") would do.

5. **antenna/test/support.ts:20-42 (`MemoryBucket`): small fidelity and ergonomics gaps.** `failGets` also fails `head`, so a test cannot fail the R8 `index.html` HEAD alone. `puts(key)` counts conditional PUTs that failed their precondition, because the log line is pushed before the `onlyIf` check. That is the right count for spend, but a test asserting "wrote nothing" with `puts()` would be misled, so it is worth a comment. Whether real R2 returns `null` for `onlyIf.etagMatches` on an absent key, as MemoryBucket does, is not covered by the R2-binding test.

6. **antenna/test/clock.test.ts:29: duplicated helper.** `playlistPuts` duplicates `MemoryBucket.puts("live.m3u8")`. The brief said nothing else in the file changes, so this is cleanup for later.

7. **antenna/test/period.test.ts: two minor gaps.** There is no leap-year case (day 29/30/31 in February 2028, clamping to the 29th), and the refusal test uses `Date.now()`. The latter is harmless (it throws before using it) but is the one non-fixed input in the file.

### ⚠️ Cannot verify from diff
- **Task 6, `persist` / first creation of `guard.json` (Minor 1):** the Task 6 reviewer should decide whether the unprotected absent→create race is acceptable and documented, or closed with a create-if-absent precondition. Also, `task-6-brief.md:521` ignores the result of the second `putJson` after a merge, so a second lost race is silent. That belongs to Task 6, but it is worth a look there.
- That Cloudflare's actual billing-period semantics for days 29-31 match "clamp to the month's last day" is a spec fact; the code does what its docstring says. Periods tile contiguously by construction, since `end(m) == start(m+1)` comes from the same function.

### Strengths
- `readJsonDoc` keeps the three states that matter for the spend surface apart: absent, corrupt and unreadable. A read error propagates rather than collapsing to absent, and a test pins that.
- The conditional PUT is proven against the real workerd R2 binding (`bucket.test.ts:32-45`), not just the in-memory fake. That covers etag presence, a stale etag returning `null`, the winner's body surviving, and `head` returning `customMetadata` and `null` for a missing key. This is the right test to have before Task 6 builds race logic on it.
- The stale-etag test would fail if `putJson` dropped the precondition (the `{v:3}` write would return true and the body check would fail).
- `MemoryBucket.get` snapshots the body at read time, as R2 does. Seeded objects get etags, so conditional-put tests are meaningful on seeded state.
- `fakeFetch` throws on any unmatched call, which enforces the "no test reaches the network" constraint.
- `clock.ts` keeps its public surface through re-exports. The clock's spend bounds are untouched, and `clock.ts` never inspects the result of `put` (`src/clock.ts:184`), so the fake's return value changing from `null` to `{etag}` cannot change clock behaviour.
- The implementer's one deviation (dropping the now-unused `type BucketLike` import in `clock.test.ts`) is correct and needed for a clean strict type check.
- Public-repo hygiene is clean: no account or zone IDs, tokens, keys or addresses in the diff.

### Checks run
- **Risk: does the clock depend on `put`'s return value, which the new fake changes from `null` to `{etag}`?** Grepped `src/*.ts` for `put(`. The only call is `src/clock.ts:184`, and it is awaited and its result discarded. No impact.
- **Risk: do later tasks rely on an etag from absent or corrupt reads in a way the seam cannot honour?** Grepped the task briefs for `putJson`/`etag`. `task-6-brief.md:513-521,576` showed that an absent read means an unconditional create (Minor 1), and that a corrupt read relies on the etag (Minor 2).
- **Risk: R2 test keys leak across test files.** Checked `vitest.config` (no isolation option) and `clock.test.ts`. The existing clock tests already share `env.BUCKET` without cleanup, and the new keys (`state/test.json`, `h`) collide with no clock key. Not a finding.
- **Risk: does `fakeFetch` mis-record the calls later tasks make?** Grepped the briefs for injected fetch calls. Tasks 3 and 5 call `fetchFn(url, init)` and nothing passes a `Request`, so the gap is latent (Minor 4).
- **Risk: `billingPeriod` edge cases.** Traced December→January wrap, day-31 clamping across January, February and March, the anniversary instant, and NaN/Infinity/fractional days. All are correct except NaN `nowMs` (Minor 3).
- I ran no tests: none of the doubts above needed execution, and the implementer reports 51/51 passing and a clean `tsc`. I tried no mutants.
