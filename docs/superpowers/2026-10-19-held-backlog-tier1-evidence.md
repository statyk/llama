# Held-backlog Tier 1: evidence record (checkpoints A-G, apply, fix wave)

## 1. Purpose and scope

On 2026-10-19 a survey of the ~1,073 held shows in the live library found mostly guard misfires (see
`docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md`). Tier 1 is the deterministic,
LLM-free part of the fix: a read-only replay harness (`scripts/replay_holds.py`,
`llama/replay.py`; slice 0), guard changes (slices 1-5), `llama reapply` (slice 6), which
re-processes held shows in place, and the `fix --untitled` resolution (slice 7). Plan:
`docs/superpowers/plans/2026-10-19-held-backlog-tier1.md`; its "Recorded at Checkpoint B-F"
blocks are the authority for the checkpoint decisions below. This document summarises the per-checkpoint
numbers, the apply to the live library (2026-10-20) and the post-apply fix wave. It records what was
measured and decided; it does not restate the design.

## 2. Method

- **Arms.** `base` is the slice-0 commit (`tier1-base`, `0038589`: main's gather/vet/brief plus the harness),
  `prev` the previous checkpoint's commit, `cand` the commit under test. Every checkpoint re-ran all arms in
  the same sitting, because the live library drifts and `compare` exits 2 when digests differ. From B on, arms
  were recorded with no llama process running; from D on the check was also 0 writes under `~/.llama/shows`
  and `~/.llama/runs` in 25 min. Checkpoint A's self-compare ran beside a live operator `llama run resume`,
  which a read-only self-compare tolerates.
- **Reproduction gate.** `compare` exits 3 below 99% reproduction of the stored flags of held, not-needs-LLM
  shows (`--no-repro-gate` only for `-prev` arms, added at C). Needs-LLM shows are counted apart and never
  as drift; a show whose gather would reach an LLM call stays held.
- **Lists tied to code.** `predicted_list.json`, `structure_changed_list.json` and `pilot_list.json` carry the
  arm's `sha`, `config_fingerprint` and per-row input digests; `reapply --from-list` refuses a list whose
  sha or fingerprint differs from the running code, and skips a row whose digests changed.
- **Operator hand-checks.** At B-G an Opus pre-screen classed every list row `routine` or `flagged`.
  At B-F the operator read every flagged row plus a fixed 20-row sample per list; at G, rows flagged
  by the pre-screen were dropped under the operator's pre-authorization, relayed by llama-45.
  Approved rows went to `$H/approved-<X>.txt`, rejected slugs to `$H/rejected-<X>.txt` (`H=~/.llama-harness`).
- **Apply.** Dry run (writes nothing), a 10-show pilot, then waves, each behind an explicit go-ahead
  from llama-45: the pilot and wave 1 under the operator's pre-authorization, waves 2-3 and the first
  retry as explicit operator decisions, the second retry round ordered by llama-45; the pacing gate
  and the 3-consecutive-LLM-failure stop were live throughout.

## 3. Checkpoints A-G

| CP | Commit | Measured | Operator decision |
|---|---|---|---|
| A | `tier1-base` `0038589` | Held arm 1,073 shows: needs-brief 43, needs-LLM 492, still-held 538, unreplayable 0. Reproduction 581/581; briefing guard reproduces 55/55; held drift 0. All arm 3,468 shows: clean 2,038, needs-LLM 844, newly-held 4; 5 non-held drifts (aquariumrescueunit-2005-01-08, gratefuldead-1971-04-29, -1977-05-09, -1985-06-24, yondermountainstringband-2005-12-31 unreplayable). Cache/setlist.fm misses 0. | Passed. Baseline accepted; drift list and needs-LLM 492 match expectations. |
| B | `127dd45`; re-measured `tier1-cp-B2` `9b74164` | Slice 2 (2a/2b/2c): cand-held needs-brief 66, needs-LLM 494, still-held 506, structure-changed 7; newly cleared 23; notes 2a 91, 2b 511, 2c 78, format-sibling-tagged 36. Packaged exposure 5 expected shows plus gracepotterandthenocturnals-2009-07-26 (track 5 `2:22` killed by the timestamp arm). Setlist-gap re-adopted demoted placeholders (zachdeputy-2008-12-06 tracks 1,2,3,8,14; infamousstringdusters-2010-10-15 tracks 3,9). B2: needs-brief 66, needs-LLM 495, still-held 505, structure-changed 7; 11b changed 8 shows. | Slice 2 approved (717 rows). Check (a) read as the residue class only (ryanadams-2006-07-20 `6040` is the 60/40 matrix ratio, correctly demoted). Known limitation: the real song `2:22` is demoted, shows stay held (`llama fix --set-title`). Task 11b added (placeholders refused by the `setlist`, `setlist-gap` and `sibling-align` rungs; 2a/2c cosmetic strips). |
| C | `88f087a`; re-measured `tier1-cp-C2` `b6f353a` | Slice 1 (1a-1d): first measurement cleared 60 held shows but newly held 45 clean shows; 3 were true conflicts, the other 42 false (country name vs code, suburb vs metro, comma-less `City ST`, venue text in the city field, identical venues with incomparable cities). C2: 54 cleared, 4 newly held (ryanadams-2007-06-06 true; beneventorusso-2005-08-27, gratefuldead-1978-09-16, smashingpumpkins-1997-06-28 false). | Slice 1 approved as narrowed (13b: 1d only when the venues are not equivalent; step 1 city check only for pairs 1b newly made equivalent; 13c `--no-repro-gate`). Limitation left: `Cornell University`/`Cornell College`, `Capitol`/`Capital Theatre` count as one hall (0 library pairs). The operator fixed 6 shows' venue/city live, re-delivered 5, staged 2 overrides; later checkpoints treat these as expected drift. approved-C 92 rows. |
| D | `tier1-cp-D` `b9ae699` (PREV C2) | Slice 3 (briefing guard) alone: 34 stored verdicts changed (3a 11, 3b 15, 3c 8); 27 held shows moved to clears by reuse; 21 suppressed set-count/ordinal matches (the prototype's ~68 fell once 3c's negation windows were clipped at clause punctuation and field boundaries); clean briefings newly firing 0. | Approved as measured (72 rows). **Rejected 5** (stay held, dropped at G): smashingpumpkins-1996-04-27, wacobrothers-2005-12-22, warrenzevon-1988-11-30, thewaybacks-2006-04-29, deadandcompany-2015-11-20 (prose asserts encore/segue detail the guard does not check). furthur-2011-02-12 harmless; moe-2002-06-22 stays held. 9 of the 27 stored `briefing.md` carry an empty `## Encore` heading, so reapply's re-render is load-bearing. |
| E | `tier1-cp-E` `3928398`; re-measured `tier1-cp-E2` `e59a6d8` (PREV D) | Slice 4: 32 outcomes changed (25 from 4a, 7 from 4b/4c), 0 newly held. The 4a band (`0.5 <= ratio < 2/3`) held 18 rows, no wrong-show research; moving to `2/3` would have lost 8 of the 25 4a clears. 4c "exactly ryanadams-2008-11-16 changes" did not hold: billycorgan-1991-09-01 (research date `1991-09-00`). E2 differs from E in exactly that show. | **`RIGHT_SHOW_MIN_TAPE_FRACTION` stays 0.5.** Approved (95 rows). **Rejected 6**: gratefuldead-1970-06-24-e2 (tape merges both events), soulive-2001-07-20 (other same-date performance's venue), littlefeat-1973-07-19, littlefeat-1975-01-20, minutemen-1983-12-16, minutemen-1985-11-30 (4b clears on a disputed adjacent date). A day-00 date is a "day unknown" assertion and keeps flagging (Task 16b); `compare` closest-calls fix (16c). littlefeat-1970-01-01's date revert accepted. |
| F | `tier1-cp-F` `a92dd72`; re-measured `tier1-cp-F2` `098c2b2` (PREV E2) | Slice 5. First: 0 `set_breaks` changes on the 636 stored-jerrybase shows; 5a cleared 2 (railroadearth-2007-09-13, yondermountainstringband-2000-11-02), both right; 5c.1 6/6 and 5c.3 8/8 clean. 5c.2 produced 5 wrong structures (gratefuldead-1971-04-29 delivered, deadandcompany-2018-06-16, gratefuldead-1980-10-31, gratefuldead-1970-05-14, ratdog-2003-05-01) and released 9 holds with an encore left in the last numbered set. F2: 39 shows differ from first F; 36 return exactly to E2, 3 carry a 5c.1 note instead of a hard closer flag (darkstarorchestra-2008-08-31, philleshandfriends-2001-11-17, -2008-07-06); hard check 1 passes again. F2 cand-held: clears 27, needs-brief 128, needs-LLM 495, still-held 406, structure-changed 11. | 5a approved. **5c.2 rejected and dropped** (Task 18b `098c2b2`; do not re-add); 5c.1 and 5c.3 kept. Approved 21 rows; no `rejected-F`. |
| G | `tier1-cp-G` `030caa7`, then `tier1-cp-G2` `4cd1ebc` | G == F2 in every field of every show (delta 0). predicted_list 155 rows (27 clears/reuse + 128 needs-brief/fresh), pilot 10, structure_changed 11; packaged exposure 0 on the held arm. Pre-screen (Opus): 13 apply rows flagged (6 with no B-F approval, 7 whose slice clear was approved but which carry an unapproved structure/title defect), 6 encore-inside-last-set rows noted. G2 re-measure after the I1 fix: delta 0 against G. | **Rejected 19** (rejected-G): 13 flagged rows dropped unread under the operator's pre-authorized rule (via llama-45), plus 6 encore-inside-last-set rows dropped by orchestrator ruling (Checkpoint F precedent). With D 5 and E 6, 30 slugs dropped: 155 -> 125 rows. Final-review I1 (`_SCOPE_AFTER` crossed the briefing-field boundary) fixed before the apply (`4cd1ebc`); I2-I5 deferred to the fix wave. |

Count note: predicted_list's 155 rows are every cand row that clears. The harness's `newly cleared: 112` counts only
those not already clears/needs-brief on base (155 - 43), i.e. attributable to Tier 1's code.

Plan/ledger note: the plan's G1 says `PREV=tier1-cp-F`; F had been re-measured, so PREV was `tier1-cp-F2`.
Plan Checkpoint C calls 1d a note; the Contracts make it a flag, and the plan's Contracts win.

## 4. The apply (G5 pilot, G6 waves)

Lists: `predicted_list` 125 rows (103 needs-brief/fresh + 22 clears/reuse) after dropping the 30 rejected
slugs (D 5, E 6, G 19 = 13 pre-screen-flagged + 6 encore-inside-last-set). `structure_changed_list` 11 rows
were NOT applied. Dry run (02:22, 4cd1ebc, clean): 125 rows, 103 fresh briefs, 125 first-time downloads
(~175 MB each, ~21.4 GB); every `would:` verdict equalled its list outcome; nothing written.

| Step | Rows | Result |
|---|---|---|
| Pilot (02:24-02:45, 2026-10-20) | 10 (8 fresh, 2 reuse) | 10/10 cleared as predicted; 187 downloads, ~1.8 GB; meter 5h 8% -> 9% |
| Wave 1 | 38 (34 fresh, 4 reuse) | 37 cleared, 1 held (smashingpumpkins-1994-04-17) |
| Wave 2 | 38 (33 fresh, 5 reuse) | 37 cleared, 1 download failure (gratefuldead-1985-06-16) |
| Wave 3 | 39 (28 fresh, 11 reuse) | 36 cleared, 2 held, 1 download failure (gratefuldead-1991-10-31) that cleared on retry |

Totals: **121 of 125 cleared** (pilot 10, wave 1 37, wave 2 37, wave 3 36, plus the 1991-10-31 retry). Four held:

- smashingpumpkins-1994-04-17: fresh brief held by `briefing mentions unknown song: Girl Named Sandoz`, a
  merged-tease title the guard did not split (fixed by fw5).
- soundtribesector9-2006-06-11: fresh brief held by `briefing claims 2 sets but structure has 1`.
- darkstarorchestra-2012-05-19: fresh brief held by 21 unknown-song flags. Cause: tag titles carry joined
  track numbers (`01-Hell In A Bucket`), not a bad brief (fixed by fw6). The show had never been briefed
  (held at gather by a blank jerrybase venue that 1a removed); an earlier ledger premise that an old
  briefing had passed was wrong.
- gratefuldead-1985-06-16: archive.org HTTP 500 on track downloads (t01 on the run and on the first
  retry, t09 on a second retry ordered by llama-45), retryable; `show.json` never committed.

Cost and safety: 0 new LLM failures (`llm-failures` stayed at 100), 0 usage refusals or pauses, 0 writes
outside the lists, 0 re-deliver lines. Meter: 5h window 10% -> 14% over wave 1 and 0% -> 9% over waves 2-3 in
the next window; weekly 3% -> 5%.

G7 post-run harness (read-only, 4cd1ebc, 166 slugs = 125 + 11 + 30): the 121 applied shows are
packaged, clean, reproduce, with 0 field changes and 0 flags; the 4 held are as above; all 41 excluded rows
(11 structure-changed + 30 rejected) are identical to their G2 rows in every field, digests included.

Operator rule amendments made during the waves (by the operator, relayed by llama-45): after wave 1 stopped on
the first mismatch, a needs-brief/fresh show held solely by the briefing guard (every flag starts with
`briefing `) became an allowed known non-match; during wave 2, a download failure is retried once and, if it
repeats, recorded as retryable and left held while the waves continue.

## 5. Post-apply fix wave (`4cd1ebc..82fc3a3`, 18 commits)

| Task | What | Commits | Review |
|---|---|---|---|
| fw4 | Set-count `(?!\s+of\b)` lookahead no longer crosses the field boundary (both regex copies, vague branch too, operator ruling) | `b7147e0` | Approved |
| fw5 | Comma-merged track titles contribute their parts to the known-song set; narrowed in review to the G2b gate (split only when every part ends in its own parenthetical: 3 titles library-wide vs 694 for the first version) | `09d50fd`, `1089b76` | Changes required (I1), then approved |
| fw1 | `fix --untitled` clears a pre-existing `encore_after`, returns a status | `0c916da` | Approved |
| fw6 | Strip a hyphen/underscore-joined track number on enumerated tapes (own vote, once, note; tags and sibling-format only). Census: 8 of 13,339 cached items change. Harness (3,468 shows): exactly 5 shows change, 137 titles, 0 newly cleared; mountaingoats-2017-06-02 (delivered) proposed set breaks move [12,15,23] -> [11,15,23] vs stored [10,15,23] | `3c75471`, `33f44b4` | Changes required (tests only), then approved |
| fw2 | `reapply`: `--allow-structure-change` (names and list forms), `skipped: structure changed` retryable, failure lines name the exception type, dry-run counts purged-audio downloads | `c106103`, `00b0c6e`, `9d5884b` | Critical C1 in review (list form ignored the flag), fixed, approved |
| fw3 | A held reapply drops a briefing (and the stale package manifest) written against older titles | `e7a029e` | Approved |
| fw7a | siblings `tmp >` refusal checks the stripped form; `_date_flags` `day_unknown` required; 16b pins | `19af9de`..`c255ca7` | Approved |
| fw7b | Docs, comments, dry-run structure-changed skip, test hygiene (imports moved in 8 modules) | `b30bed5`..`82fc3a3` | Approved after one fix round |

Final suite at `82fc3a3`: 3803 passed, 1 skipped, 8 deselected. The final whole-branch review (Fable,
`030caa7`) found 0 Critical and 5 Important (I1-I5): I1 was fixed pre-apply, I2-I5 are fw1/fw2/fw3/fw7a.
Its recommendation 4 (skip a `reapply` row when `classify` disagrees with the row's outcome) was not taken: it
would have skipped the legitimate needs-brief -> clears retry seen in the waves.

## 6. Deferred minors

Full list: `orch-r4/deferred-minors.md`. None is Critical or Important. Behavioural ones, each needing its
own measurement or an operator ruling:

- fw6 does not cover `1.02 - ` (disc.track) or `1-002` forms (davealvin-2018-12-09); ryanadams-2017-05-06
  stays prefixed (vote 0.72 < 0.8); a real `7-Up`-style title on an enumerated tape loses its number (0 in the cache).
- fw7a M-a: `hygienic_title` sees the unstripped donor title (`Foo: >` adopted as `Foo:`); M-b: one round of `>` strip.
- fw3: the stale-briefing drop uses `shipped_diff`, wider than `briefing_reusable` (safe direction, may cost one brief).
- fw4 m3: two other `\s+` can still cross the field boundary (negligible).
- `cities_compatible("York, PA", "New York")` is True (spec containment, a loosening; worth an operator note).
- Left as ruled: `_SHIPPED_TAIL` keeps `-@^~`; `encore_lost` whole-tape membership; three duplicated walks
  (`_filler_excused`, `_second_closer_candidates`, `_short_track_arm`); strict `notes.json` read in vet.
- fw2 m4: `needs_audio_download({"tracks": []})` reports no download (pinned, not a safety choice).

Test and code hygiene minors from tasks T1-T20 are listed in that file, not here.

## 7. Operator follow-ups (not code)

- Of the 6 shipped shows with numbered titles, fw6 changes 3 (theblacklillies-2014-04-20,
  mountaingoats-2017-06-02, mountaingoats-2019-05-08): after merge, `llama redo <show> --from gather` and
  re-deliver; hand-check mountaingoats-2017-06-02's set breaks (proposed [11,15,23], stored [10,15,23]).
  Unchanged by fw6: ryanadams-2017-05-06, davealvin-2018-12-09, mountaingoats-2019-05-07. Held and changed:
  darkstarorchestra-2012-05-19, mountaingoats-2012-06-27.
- Re-brief the 3 fresh-guard holds: smashingpumpkins-1994-04-17 (now passes the guard),
  darkstarorchestra-2012-05-19 (fresh brief on the stripped titles), soundtribesector9-2006-06-11 (unchanged).
- Re-brief the 5 rejected-D shows after the merge; fix moe-2002-06-22's structure (its `E:` encore tracks
  are labelled set 3); hand-check littlefeat-1970-01-01's date; hand re-split gratefuldead-1970-06-24-e2.
- gratefuldead-1985-06-16: archive.org 500s on t01/t09, retryable (re-run the wave-2 list); see the open
  `llama-download-retry-followup` TODO.
- The 11 structure-changed shows are unapplied: `llama reapply --from-list structure_changed_list.json
  --allow-structure-change` after hand-checks, against a list regenerated at the merged sha.

## 8. Sources

- Plan (Checkpoint A-G sections and "Recorded at" blocks): `docs/superpowers/plans/2026-10-19-held-backlog-tier1.md`;
  spec: `docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md`.
- SDD ledgers, cited by role (`.superpowers/sdd/tier1/orch/ledger.md` through `orch-r4/ledger.md`): orch
  (A, slice 0), orch-r1 (B, C), orch-r2 (D, E, F first measurement), orch-r3 (F2, G1-G5), orch-r4 (waves, G7, fix wave).
- Harness outputs (read-only): `~/.llama-harness/cmp-G2-held/summary.txt`, `~/.llama-harness/cmp-fw6-all/summary.txt`,
  `~/.llama-harness/G7-scoped.json`, `$H/approved-*.txt`, `$H/rejected-*.txt`.
- Final review: `.superpowers/sdd/tier1/final-rev/handback.md`; deferred list: `orch-r4/deferred-minors.md`;
  DSO diagnosis: `dso-diag/handback.md`.
- `.superpowers/` is gitignored: copy the ledgers out before the worktree is removed (plan "Finish"); keep `$H`.
