# t8-review — Task 8 (docs), combined spec + quality seat, commit a35208b

### Spec Compliance
- ✅ Spec compliant, with two Minor deviations (below). All three files in the brief have their hunks, and nothing outside them changed.
- Check (script): section 9 + 9.1 are byte-identical to the brief's ```` block and sit at EOF of docs/playout-setup.md:496-557. The step-5 sentence (:215), step 7 (:237), the 7.1 row (:447), the Commands-bullet sentence (CLAUDE.md:174) and both parent-spec insertions (2026-10-09-playout-design.md:512, :556) all match the brief verbatim.
- Check: the parent-spec paragraph sits at the end of `### antenna (phase 1 minimal, phase 4 full)` (heading :374), immediately before `### Spend budget` (:514). The cost-guard bullet directly follows the A5 bullet ending ``cache hits on `live.m3u8`.)*`` and stays in that list.
- Check: the 7.1 row is inside the clock-alerts table, right after `clock-failed`. clock.ts:266 raises `metronome-down` as `priority: "high", resolvable: true`, so the row is accurate.
- ⚠️ Cannot verify from diff: the reported test run (372 passed, typecheck rc=0) was not re-run (docs-only, per rules). 372 vs 364 is known and legitimate.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. CLAUDE.md:301: the text is not verbatim. The brief has `- ≤ 10 PUTs and ≤ 12 alarms per rolling minute;`, but the commit has `- at most 10 PUTs and at most 12 alarms per rolling minute;`. The meaning is the same. The handback's claim "Insert text is verbatim from the brief" is false for this line. Fix: restore the brief's wording, or record the deviation.
2. CLAUDE.md:300: the brief asks for "a new paragraph", but `**The metronome**` follows line 299 (`` `docs/superpowers/2026-10-12-playout-phase2-sdd/`. ``) with no blank line. Markdown therefore renders it as a continuation of the preceding transmitter/antenna paragraph. The list at :301 still renders, because a `-` list can interrupt a paragraph. A side effect is that `transmitter must stay Python 3.11-compatible` (:308) now becomes its own paragraph, which is harmless. Fix: insert one blank line before :300.

### Verdict
**Spec compliance:** Pass

---

### Strengths
- Every number the docs state matches antenna/src as built (named risk 1). One focused check per constant:
  - metronome-core.ts:13 `METRONOME_LEASE_MS = 15*60_000`
  - :15 `METRONOME_STALE_MS = 30_000`
  - :19 `MAX_DO_PUTS_PER_MINUTE = 10`
  - :21 `MAX_ALARMS_PER_MINUTE = 12`
  - :24 `DO_PUT_TIMEOUT_MS = 5_000`
  - :26 `RENEW_TIMEOUT_MS = 15_000`
  - :28 `ALARM_SLACK_MS = 25` (boundary + 25 ms, :165)
  - :199-200 `STORAGE_KEYS` is exactly 8 keys
  - fallbackReason (metronome-core.ts:300-313) covers renew error/timeout, a play lease not accepted or not written, and stalls >= STALLS_FALLBACK
  - meter.ts:153 error text contains `the metronome is on but the recent window reads doRequests=` verbatim, and fails on doRequests==0 OR doRowsWritten==0, which matches the parent-spec bullet's "requests or rows written"
  - pricing.ts:32-34 matches the 1M/$0.15, 400k/$12.50, 50M/$1.00 in the parent-spec bullet
  - the off switch deletes the alarm (metronome-engine.ts:81-82, :248-249)
  - guard.ts:91 and index.ts:28 enable only on `=== "on"`
- Cross-references resolve:
  - wrangler.jsonc:47 → section 4 step 7 (docs/playout-setup.md:237), which → section 9 (:496)
  - binding `METRONOME_DO` / class `Metronome` / migration `v1 new_sqlite_classes` match wrangler.jsonc:57-58
  - the test names in CLAUDE.md exist (test/metronome*.test.ts, clock-metronome.test.ts)
  - the real-DO test file does `reset()` in afterEach (metronome.test.ts:35-37)
  - hugo's `dead_clock_seconds` 120 and `guard_stale_minutes` 45 match transmitter/config.py:106,111
- Rendering (named risk 2):
  - The section 9 step-1 fenced block is indented 3 spaces under `1. `, so it stays inside the list item.
  - Step 7 continues section 4's numbered list.
  - The 7.1 row sits inside its table.
  - The parent-spec paragraph is blank-line separated, and the new bullet continues the Cost guard list.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
- Same two items as above (CLAUDE.md:300 missing blank line → not a separate paragraph; CLAUDE.md:301 wording deviates from the brief). Neither is stale or inaccurate.

### Assessment
**Task quality:** Approved
**Reasoning:** The docs are accurate against the built code on every stated constant, string and cross-reference, and they render as intended. The only nits are a missing blank line and one non-verbatim line in CLAUDE.md.
