VERDICT: CHANGES REQUIRED

evid-rr1 (Opus) re-reviewed 699f766..d206516 (docs only: CLAUDE.md, evidence doc). Read-only. Snapshot `git archive d206516` was at $TMPDIR/evid-rr1-snap-vBdvWk and has been removed. Shadowing proven: llama.__file__ resolved into the snapshot. I changed no worktree file and made no commit.

Every content correction (I1-I4, m1-m3, m5) lands, and I re-checked each against the cited sources. Two problems remain, both trivial text fixes:
- the fix introduced a broken sentence (N1);
- the m4 re-wrap made the line longer instead of shorter (m4 NOT ADDRESSED).

## Findings vs evid-rev

| Item | Status | Re-verification |
|---|---|---|
| I1 18 commits | ADDRESSED (doc:91) | `git log --oneline 4cd1ebc..82fc3a3 \| wc -l` = 18 |
| I2 Checkpoint C 3 true / 42 false | ADDRESSED (doc:40) | orch-r1 18:28:38: 45 newly held, 3 TRUE |
| I3 quiet-library wording | ADDRESSED (doc:17-21) | All four sources match: orch ledger CHECKPOINT A 16:03:53; orch-r1 17:03:57 "no llama process"; orch-r1 21:02:05; orch-r2 21:44:27 "0 writes under ~/.llama/shows\|runs in the last 25 min" |
| I4 G rejections attribution | ADDRESSED in the G row (doc:44) and in Method; Method text broken (N1) | — |
| m1 t01 run + first retry, t09 second retry; amendment during wave 2 | ADDRESSED (doc:75, 88) | orch-r4 06:52:08, 08:23:10, 10:09:45. The amendment is 07:57:22 and wave 2 ended 08:21:31 |
| m2 GO attribution | ADDRESSED, with one overclaim (n2) | orch-r4 02:49:17 (pre-authorization); 06:42:31 and 07:57:22 tagged "(operator decision)" |
| m3 slice 0 / slice 7 | ADDRESSED (doc:7-9) | — |
| m4 CLAUDE.md re-wrap | **NOT ADDRESSED.** CLAUDE.md:514 is now **97** chars (was 83). The surrounding lines are ≤78 | — |
| m5 155 vs 112 | ADDRESSED (doc:49-50) | matches replay_holds `_newly_cleared` semantics (CLEARING = clears, needs-brief) |

## New findings

### Critical / Important
None.

### Minor

**N1. Broken sentence in the Method, doc:28-29.** The text reads "…classed every list row `routine` or `flagged`; the\n  at B-F the operator read…". The old "the" was left dangling.

Fix: "…`routine` or `flagged`. At B-F the operator read every flagged row plus a fixed 20-row sample per list; at G, rows flagged by the pre-screen were dropped under the operator's pre-authorization, relayed by llama-45."

**m4 (still open). CLAUDE.md:513-516.** Re-wrap to ≤78 with the wording unchanged, e.g.:
```
  `docs/superpowers/2026-10-19-held-backlog-tier1-evidence.md`).
  Each removes false holds only where the harness can enumerate the
  effect, and **sits beside the protected predicate, never loosening
  it** (`is_real_title`,
```
Then fold the remainder as needed. Alternatively, restore the original text, as long as each line is ≤78 chars.

**n2. "waves 2-3 and the retries as explicit operator decisions", doc:31-32, overclaims the second retry round.**
- The first retry was an operator decision (orch-r4 07:57:22).
- The second round (09:22:23: 1991-10-31 plus another 1985-06-16 re-run) is logged as "llama-45:" with no "(operator decision)" tag.
- doc:75 itself says the second retry was "ordered by llama-45".

Fix: "waves 2-3 and the first retry as explicit operator decisions, the second retries ordered by llama-45".

**n3. doc:88 dropped "once" from the amendment.** The 07:57:22 rule was "retry ONLY that row … a repeat DOWNLOAD failure on the retry → record retryable". "retried once and, if it repeats, recorded as retryable" was the accurate wording. The later extra retry was a separate order, not the rule. Fix: restore "once".

**n4 (cosmetic, optional).** The new prose lines overflow the doc's ~110-column wrap: doc:9 (160), 29 (214), 31 (129), 32 (183), 75 (150). Re-wrap.

No new false numeric claim was introduced. No code changed. No do-not-retune names were touched.

## Mutation
Skipped per brief (doc fix).

## Suite
d206516 snapshot, PYTHONPATH-shadowed, private PYTHONPYCACHEPREFIX: `python -m pytest -q -p no:cacheprovider` → **3803 passed, 1 skipped, 8 deselected, 26 warnings in 125.02s**.
