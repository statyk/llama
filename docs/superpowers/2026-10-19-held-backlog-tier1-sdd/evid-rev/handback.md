VERDICT: CHANGES REQUIRED

evid-rev (Opus), read-only fact check of 82fc3a3..699f766 (docs only: CLAUDE.md +2/-1, new docs/superpowers/2026-10-19-held-backlog-tier1-evidence.md, 147 lines). Snapshot: git archive 699f766 into $TMPDIR/evid-rev-snap-OHrwVP (removed at the end); shadowing proven (llama.__file__ -> snapshot). No worktree file changed, no commit.

Every finding below is a doc-text fix. Nothing in the doc loosens code. The tables are mostly right, but four claims are wrong or misattributed.

## Spec compliance (evid-brief.md)

| Item | Status | Where |
|---|---|---|
| 1 Purpose and scope (3-5 lines, survey ~1,073, spec + plan paths) | ✅ (see m3) | doc:3-12 |
| 2 Method (arms, compare, repro gate, lists tied to sha+fp, hand-checks, pre-screen, pilot, waves) | ❌ two wrong claims (I3, I4) | doc:14-30 |
| 3 Per-checkpoint table A-G with Recorded-at authority + discrepancies noted | ✅ numbers; ❌ C row wording (I2), G attribution (I4) | doc:32-45 |
| 4 Apply: verbatim numbers (125 = 103+22; 30 = 5+6+19 (13+6); 11 not applied; pilot 10/10 02:24-02:45; waves 37/37/36+retry; 121/125; 4 held with causes; 0/0/0/0; meter; G7 166 = 125+11+30, 41 identical; amendments by the operator via llama-45) | ✅ (m1, m2) | doc:47-84 |
| 5 Fix-wave table, shas, review outcomes, census/harness numbers, final suite 3803/1/8 | ✅ except the commit count (I1) | doc:86-102 |
| 6 Deferred minors ≤15 lines | ✅ 14 lines | doc:104-119 |
| 7 Operator follow-ups | ✅ (adds traceable extras, see m6) | doc:121-135 |
| 8 Sources + `.superpowers/` copy-out note | ✅ | doc:137-147 |
| CLAUDE.md pointer in the Tier 1 bullet's first sentence | ✅ (m4 wrap) | CLAUDE.md:512-513 |
| No other "evidence-doc pointer" placeholder left | ✅ grep of CLAUDE.md, README.md, plan, spec: the plan's Finish line 3360 already names the path; nothing else | — |
| One commit, docs only | ✅ 699f766, 2 files | — |
| Do-not-retune names | n/a, no code in the diff | — |

## Findings

### Critical
None.

### Important (wrong or misattributed claims)

**I1. Fix-wave commit count: "19 commits" should be 18.** doc:86 (`## 5. Post-apply fix wave (4cd1ebc..82fc3a3, 19 commits)`). `git log --oneline 4cd1ebc..82fc3a3 | wc -l` = **18**: fw4 1, fw5 2, fw1 1, fw6 2, fw2 3, fw3 1, fw7a 3, fw7b 5. The writer copied the orch-r4 ledger's 11:29:45 line ("19 commits"), and that line is itself wrong. Fix: "18 commits". The ledger can't be corrected because it's out of git, so cite git as the source.

**I2. The Checkpoint C row puts the false-positive classes on the 3 true conflicts.** doc:38 says "newly held 45 clean shows, 3 of them true conflicts (country name vs code, suburb vs metro, comma-less `City ST`, venue text in the city field, identical venues with incomparable cities)". The plan's Recorded-at-C says "of which only 3 were true conflicts. **The rest were false:** country name vs code, …". So the parenthetical lists why the other **42** were false. The orch-r1 ledger (18:28:38) agrees: 3 TRUE (ginblossoms-2003-01-24, stuallenandmarshotel-2012-11-11, ryanadams-2007-06-06), 42 FALSE. Fix: "…newly held 45 clean shows; 3 were true conflicts, the other 42 false (country name vs code, …)".

**I3. Method: not every checkpoint had a quiet library, and the quiet test was narrower than stated.** doc:18-19 says "Every checkpoint re-ran all arms in the same sitting, with a quiet library (no llama process, no writes under `~/.llama` for 25 min)". This is wrong on three counts:
- (a) Checkpoint A's arms ran **while the operator's `llama run resume 2026-10-18-dead-tribute-11` was live** (orch ledger, CHECKPOINT A 16:03:53: "live during the arms (read-only harness; self-compare unaffected)").
- (b) The 25-minute write check starts at D (orch-r2 21:44:27). At B and C the check was "no llama process" (orch-r1 17:03:57), and at C2 it was llama-45's "LIBRARY QUIET" (orch-r1 21:02:05).
- (c) The check covered `~/.llama/shows|runs` only, not all of `~/.llama`.

Fix: "From B on, arms were recorded with no llama process running. From D on, the check was also 0 writes under `~/.llama/shows` and `~/.llama/runs` in 25 min. Checkpoint A's self-compare ran beside a live operator `llama run resume`, which a read-only self-compare tolerates."

**I4. Checkpoint G's rejections are credited to the operator, but neither the reading nor the dropping was the operator's.**
- doc:26-27 says that at B-G "the operator read every flagged row plus a fixed 20-row sample per list".
- doc:42 puts "Rejected 19 (rejected-G)" in the "Operator decision" column with no attribution.

At G the operator read nothing:
- The 13 pre-screen-flagged rows were dropped unread, under llama-45's pre-authorized rule 2 ("Any row the G pre-screen flags that was not already approved at B–F: DROP it … Do not wait on the operator"; orch-r3 01:41:52 and HANDOFF).
- The 6 encore-inside-last-set rows were dropped by an **orchestrator ruling** (orch-r3 02:23:06 "Ruling: rejected-G = …"). `~/.llama-harness/rejected-G.txt` says the same: "dropped by orchestrator ruling on Checkpoint F's encore-release precedent".

Fix:
- Method: "at B-F the operator read …; at G, rows flagged by the pre-screen were dropped under the operator's pre-authorization, relayed by llama-45."
- G row: "Rejected 19: 13 flagged rows dropped under the operator's pre-authorized rule (via llama-45), plus 6 encore-inside-last-set rows dropped by orchestrator ruling (Checkpoint F precedent)."

### Minor

- **m1.** gratefuldead-1985-06-16, doc:70: "t01 twice, then t09 **on the retry**". There were two retries. t01 failed on the wave-2 run and on retry 1 (08:22). t09 failed on retry 2 (10:01-10:08), which llama-45 ordered at 09:22 (orch-r4 08:23:10, 09:22:23, 10:09:45). Also, doc:83 says the download-retry amendment came "after wave 2". It came during wave 2 (07:57; wave 2 ended 08:21), and 1985-06-16 was then retried twice, not once. Suggest: "t01 on the run and the first retry, t09 on a second retry ordered by llama-45".
- **m2.** doc:29-30 says each apply step ran "behind an explicit go-ahead relayed from the operator by llama-45". The pilot and wave 1 GOs were llama-45's, under the operator's pre-authorization (orch-r3 02:24:03; orch-r4 02:49:17). Waves 2 and 3 and the retries were explicit operator decisions (06:42, 07:57, 09:22). One clause fixes it.
- **m3.** Purpose, doc:7-9: the spec names the replay harness slice 0 (spec:269) and `--untitled` slice 7 (spec:925). The doc leaves the harness unnumbered and omits slice 7, though fw1 and the follow-ups depend on it. Suggest "slice 0 … slices 1-5 … slice 6 … and the `--untitled` resolution (slice 7)".
- **m4.** CLAUDE.md:513 is 83 characters. The surrounding lines are at most 78. Re-wrap: move "Each removes false" to the next line.
- **m5.** Optional: one line about the writer's "112 vs 155" concern (judged below), so a reader doesn't credit all 121 clears to Tier 1 code.
- **m6.** Operator follow-ups (doc:130-131) adds items that aren't in the deferred file's last section: re-brief the 5 rejected-D shows, moe-2002-06-22, littlefeat-1970-01-01, and the gratefuldead-1970-06-24-e2 re-split. All four trace to the plan's Recorded-at-D/E blocks and orch-r2's HANDOFF "Post-run items". Keeping them is right. No change needed.

## Fact-check record (every claim checked; ✅ = matches the cited source)

- **A:** 1,073 shows; 43/492/538/0; 581/581; 55/55; held drift 0; all arm 3,468 with 2,038/844/4; the 5 drifts named; misses 0. Source: orch ledger CHECKPOINT A. ✅
- **B:**
  - 66/494/506/7; newly cleared 23; notes 91/511/78/36. Source: orch-r1 17:06:36. ✅
  - Packaged exposure 5 shows + gracepotter-2009-07-26. ✅
  - zachdeputy tracks 1,2,3,8,14 and stringdusters tracks 3,9. ✅
  - B2: 66/495/505/7; 8 shows changed by 11b. Source: 17:43:39 and the 11b delta line. ✅
  - approved-B 717 lines. ✅ Check (a), the `2:22` limitation and 11b match plan Recorded-at-B. ✅
- **C:**
  - 60 cleared / 45 newly held / 3 true. ✅ (wording: I2)
  - C2 54 cleared / 4 newly held with the named shows. ✅
  - 13b V+S and 13c. ✅
  - Cornell/Capitol limitation, 0 pairs. ✅
  - Operator fixes: 6 fixed, 5 re-delivered, 2 staged. Source: plan. ✅
  - approved-C 92 lines. ✅
- **D:**
  - 34 verdicts (11/15/8); 27 → clears by reuse; 21 suppressed (~68 prototype); 0 newly firing. ✅
  - 5 rejected slugs and reason. ✅
  - furthur-2011-02-12 and moe-2002-06-22. ✅
  - 9 of 27 empty `## Encore` headings. ✅
  - approved-D 72; rejected-D holds 5 slugs (10 lines: 5 headers + 5 guard rows). ✅
- **E:**
  - 32 changes (25 from 4a / 7 from 4b-4c); 0 newly held. ✅
  - 18 band rows; 8 of 25 would be lost at 2/3. ✅
  - Constant stays 0.5. ✅
  - 6 rejected with reasons. ✅
  - billycorgan, 16b/16c, littlefeat-1970-01-01. ✅
  - E2 differs in exactly 1 show. ✅
  - approved-E 95. ✅
- **F:**
  - 636 stored-jerrybase shows, 0 changes; 5a 2 clears; 5c.1 6/6, 5c.3 8/8. ✅
  - 5 wrong 5c.2 structures named; 9 releases. ✅
  - F2: 39 differ, 36 back to E2, 3 notes named. ✅
  - F2 cand-held 27/128/495/406/11. Source: orch-r3 01:07:24. ✅
  - approved-F 21 rows (+1 header line); no rejected-F. ✅
- **G:**
  - G == F2, delta 0; 155 = 27 + 128; pilot 10; structure-changed 11; held exposure 0. Source: orch-r3 02:07:04. ✅
  - 13 flagged = 6 + 7 (slugs match rejected-G.txt); 6 encore rows. ✅
  - I1 fixed at 4cd1ebc; G2 delta 0. ✅
  - 155 → 125. ✅ (attribution: I4)
- **Commits** checked against tags in the ledger HANDOFFs: tier1-base 0038589, B 127dd45, B2 9b74164, C 88f087a, C2 b6f353a, D b9ae699, E 3928398, E2 e59a6d8, F a92dd72, F2 098c2b2, G 030caa7, G2 4cd1ebc. ✅
- **Dry run** (02:22, 125 rows / 103 fresh / 125 downloads ~21.4 GB, every `would:` equal to its outcome). Source: orch-r3 02:23:06. ✅
- **Pilot** (8 fresh / 2 reuse, 187 downloads ~1.8 GB, 5h 8→9%). Source: orch-r3 02:47:21. ✅
- **Waves:**
  - Sizes 38 (34/4), 38 (33/5), 39 (28/11). Source: orch-r4 02:49:17. ✅
  - Outcomes and the 4 held with causes; darkstarorchestra premise correction. Sources: orch-r4 TOTALS and the dso-diag line. ✅
  - 0 failures/pauses/outside writes/re-deliver; llm-failures 100. ✅
  - Meter 10→14 (wave 1), 0→9 (waves 2-3), weekly 3→5. ✅
  - G7 166 / 121 / 4 / 41. Source: orch-r4 10:22:18. ✅
- **Fix wave:**
  - Every sha is in `git log`. ✅
  - Review outcomes: fw5 I1 → G2b (3 vs 694 titles); fw6 tests-only CR; fw2 C1; fw7b one fix round. ✅
  - fw6 census 8 of 13,339; harness 5 shows / 137 titles / 0 newly cleared (cmp-fw6-all/summary.txt "newly cleared: 0"); mountaingoats-2017-06-02 breaks. ✅
  - 3803/1/8 at 82fc3a3. Source: orch-r4 11:27:01. ✅
  - Fable review at 030caa7: 0 Critical, I1-I5; I2→fw1, I3→fw2, I4→fw3, I5→fw7a; rec 4 not taken. Sources: final-rev/handback.md, orch-r4 10:24:43. ✅
  - Commit count ❌ (I1).
- **Deferred minors and operator follow-ups** match orch-r4/deferred-minors.md. ✅
- **The writer's two noted discrepancies:** both are real and handled correctly.
  - (1) The plan's G1 says `PREV=tier1-cp-F`, but the actual PREV was F2. Source: orch-r3 Ruling after 01:41:52, "G1's PREV is tier1-cp-F2". The plan is the authority for what was planned, and the doc records what ran. Correct.
  - (2) Checkpoint C item 4 calls 1d a "note", while the Contracts make it a flag. Source: orch-r1 Ruling "Checkpoint C item 4 calls 1d a note; it is a FLAG (Contracts)". A plan-internal inconsistency, and the stated resolution is right.
- **Missed plan-vs-ledger discrepancies:** none found. Every Recorded-at block number matches its ledger line.

## The "newly cleared: 112 vs 155 rows" concern (cmp-G2-held/summary.txt)

The two numbers count different things in `scripts/replay_holds.py` `compare`:
- `_newly_cleared(base, cand)` (replay_holds.py:331-333) counts shows whose **cand** outcome is in `CLEARING = ("clears", "needs-brief")` **and whose base outcome is not**. These are the clears that Tier 1's code changes produced.
- `predicted_list.json` (replay_holds.py:758) takes **every** cand row whose outcome is in `CLEARING`, whatever base said.

I checked this against `G2-base-held.json` / `G2-cand-held.json`:
- 155 cand rows clear.
- 43 of them were already `needs-brief` in the base arm. These are the 43 base needs-brief shows from Checkpoint A, which main's code would clear given a fresh brief.
- 155 − 43 = **112**.

Those 43 split in cand into **27 clears/reuse** (all 27 D reuse clears were base needs-brief, because slice 3 made their stored briefing pass) and 16 still needs-brief. So both numbers are correct, and the doc's 155 is the right figure for the list.

If the doc wants a Tier-1-attributable number, it is 112 of 155 before the drop. 13 of the 43 base-needs-brief rows are among the 30 rejected slugs. Optional sentence (m5): "155 = 112 cleared by Tier 1's changes + 43 that were already needs-brief on main (`compare`'s 'newly cleared' counts only the former)."

## Mutation spot-check
Skipped per brief (fact-check review).

## Suite
Snapshot of 699f766, PYTHONPATH-shadowed, private PYTHONPYCACHEPREFIX: `python -m pytest -q -p no:cacheprovider` → **3803 passed, 1 skipped, 8 deselected, 26 warnings in 102.50s**.
