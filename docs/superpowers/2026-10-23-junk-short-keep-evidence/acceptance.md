# Junk short-keep: acceptance (Task 9, Checkpoint A)

Measured 2026-10-24 by the peer orchestrator (orch-r1), under `~/.llama-harness/piece4/`. Spec
section 6 is the yardstick. Everything here is read-only against the library; no migration had run.

## Arms

| arm | tree | sha | ran (EDT) | output sha256 |
|---|---|---|---|---|
| base | `~/.llama-harness/piece4/base-e37f670` (detached worktree, own venv) | `e37f67024eb3df6ae7fad19357ef3c8a1f84b34c` | 04:40:03-04:40:52 | `base.json` b8ea3d048d6cd12e… |
| candidate | this branch, `--rekey-overrides` | `76c18307bad6da8d3dd2a8d1de960c16ba1424e2` (clean) | 04:40:52-04:41:52 | `cand.json` 31ec0a03797a2615… |

Back to back, same `config_fingerprint` (3f1af9a8…). Each run's `llama.__file__` resolved inside
its own tree. The candidate has 0 `rekey_error` rows and 0 unreplayable rows. The commits after
76c1830 touch only `scripts/short_keep_probe.py`, which the arms do not import.

## Gates

- **`compare` repro gate: failed, then skipped on an operator ruling.** `replay_holds.py compare`
  exited 3: `baseline reproduces 127/148 held shows that are not needs-LLM (< 99%)`. The 21 held
  drift rows are in `~/.llama-harness/piece4/compare/drift-held.txt` (sha256 c1b92ec1…). Operator
  ruling (Shawn, 2026-10-24 ~11:25, relayed by llama-db), verbatim: **"--no-repro-gate
  approved"**. The basis llama-db put to him: all 21 rows are shows whose stored `show.json` was
  written 2026-09-05..10-21, before pieces 1-3 were applied to the library. The drift is therefore
  in the stored inputs, not in the branch, and base and candidate read the same inputs.
  `compare --no-repro-gate` then ran with rc 0.
- **Overrides-validation refusal:** none. No arm was refused, and no row is unreplayable.
- **Apply lists:** none written, since the candidate arm is re-keyed (as designed).
- **`BLOCKS MERGE`:** 0 lines (`short_keep_probe.py arms`, `~/.llama-harness/piece4/arms/arms.md`,
  sha256 36e88763…).
- **Base consistency** (did the library move since the reference ran?): 0.

## Tallies against 6(a)

| measure | spec | candidate |
|---|---|---|
| shows changed | 1,537 | 1,536 |
| files added | 2,649 | 2,648 |
| holds cleared | 20 | 20 |
| holds added | 34 | 34 |

**The one reference-reproduction difference** accounts for both -1s:

- **What happened.** `soundtribesector9-2005-02-07` `sts9-2005-02-07d1t1.mp3` is a 26 s untagged
  file listed twice, once at the top level and once under `sts9-2005-02-07.flac/`. The reference
  harness ran its interior test before the dedupe and kept the file (`keep-untagged`). The
  branch derives play order over one copy per listing, so the file is the tape's first track and
  drops as an edge.
- **Cause.** This is the case Task 1's ruling predicted ("interior over the deduped pool", spec 2.4,
  ruling 4).
- **Verdict.** Explained; the branch is right.

**needs-LLM:** net +1 (base 653, candidate 654).
- 6 shows move in: deadandcompany-2015-10-29, discobiscuits-2001-09-08, mountaingoats-2018-04-13,
  ratdog-2007-08-12, soundtribesector9-2004-05-01, stringcheeseincident-2005-03-25.
- 5 move out: darkstarorchestra-2015-07-11, joerussosalmostdead-2017-08-31, radiators-2008-12-06,
  stuallenandmarshotel-2014-12-30, yondermountainstringband-2006-08-26.

Each of the movers is one of the 6(b) "low confidence remains" or "positional rung lost" shows, or
a cleared show.

## Holds added, by class (6(b))

| class | spec | candidate |
|---|---|---|
| new unresolved track | 18 | 18 |
| long single-set show crosses 150 min | 6 | 6 |
| positional rung lost | 4 | 4 |
| low confidence remains | 3 | 3 |
| jerrybase closer not at a break | 2 | 2 |
| other | 1 | 1 (`robertwalters20thcongress-2004-01-02`) |

There is no class outside the table and none larger than the spec's count. The 34 shows and the 20
cleared ones are listed in `arms.md`.

## Overrides (6(d)) and positional fills (6(e))

- **Override tracks on a different file:** 0. **Override-path structures moved:** 0.
- **Positional fills lost:** 10 shows, as 6(e) predicts:
  - `ratdog-2007-08-12` 19;
  - `derektrucksband-2004-11-20` 12;
  - `belafleckandtheflecktones-2003-04-12` 2;
  - 7 shows at 1.
- **Positional fills gained:** 12 shows, including `darkstarorchestra-2015-07-11` (12).

## Hand check (6(c))

- **Packet.** `short_keep_probe.py packets --seed 47` wrote `~/.llama-harness/piece4/hc/packet.jsonl`
  (60 rows, sha256 c242c54ee5ee47ac…). Every stratum is at its spec size.
- **Checkers.** Two Sonnet checkers each took half: rows 1-30 (`answers-1.jsonl` b7691c26…) and rows
  31-60 (`answers-2.jsonl` 69e648ef…).
- **Merged answers.** `answers.jsonl`, **sha256
  77fe89b3e0909bdd086d2717148fb6c805954a7f72809a48139675695723c018**.
- **Score.** `~/.llama-harness/piece4/hc-score/score.md` (sha256 48995b04…): **PASS, 57 right, 3
  wrong of 60 (95.0%)**.
  - 0 kept spam or non-performance.
  - 0 dropped music.
  - 0 missing answers.
- **For the operator.** `first10.md` holds rows 1-10 without the graders' answers (premise 2). Those
  answers are in `first10-answers.md`.

The Opus pre-screen classified each wrong row (full text in the SDD record,
`t9-pre/handback.md`, sha256 6c1daf27…):

| row | file | rule | checker | class |
|---|---|---|---|---|
| 25 | `stevekimockband-2004-09-24` `skb2004-09-24d1t01.mp3`, 80 s, untagged, first track | drop (edge) | keep | **checker error.** The checker read the description's `Tuning/Introduction`, but the tag is the file's own title (spec 2.2). |
| 46 | `loslobosmusic-2024-06-14` `01 Intro.mp3`, 19 s, untagged, first track | drop (edge) | keep | **checker error.** Spec 2.4 lets a filename only drop a file, never keep it. |
| 36 | `gratefuldead-1973-10-29` `gd73-10-29d2t01_vbr.mp3`, length `00:00`, 1,017 bytes | keep | drop | **defect.** An audio-less stub. See open item 1. |

So the rule was right on 59 of 60 rows.

**Not covered by the sample:** the packet's kept strata (`music`, `music-fragment`, `spoken`,
`mixed-with-tuning`) never draw the 16 rows the reference kept with census kind `crowd` (13),
`non-performance` (2) or `spoken-broadcast` (1). The bar's "zero kept non-performance" therefore
tests only rows of other kinds.

## Premise 3: the sibling vocabulary look

`sibvocab` (`~/.llama-harness/piece4/sibvocab/sibvocab.txt`, sha256 5d1b381f…) found 630 of 5,024
kept sibling short tags matching the crowd/tuning/broadcast grep. 5,024 is the figure spec 8
gives. The pre-screen sorted them:

| group | rows |
|---|---|
| already dropped-shaped (0 by construction; the port agrees with the reference on all 9,487 tagged sibling drops) | 0 |
| mixed or spoken tags the rulings keep | 354 |
| music matching by accident (`Not Fade Away`, `Terrapin Station`) | 54 |
| junk or non-performance the rule keeps | 222 |

The 222 break down as:
- 9 non-performance plus 3 possible;
- about 200 crowd/tuning variants: chants, typos, plurals, set labels, annotations, and taper or
  filename residue.

**Verdict (pre-screen):**
- **`JUNK_PART`:** no change. The crowd/tuning misses are seconds of junk, the cheaper error under
  the operator's direction. Proposed as a section 7 limitation.
- **`NONPERF`:** a ruling item (open item 2). The rule keeps non-performance in the library itself.

## Open items for the operator's Checkpoint A rulings

1. **Row 36: audio-less stubs are kept.**
   - **What happens.** `length_seconds("00:00")` returns 0.0, not `None`, so the `missing duration`
     arm does not fire. The short rule then keeps the file (its tag, `Promised Land \>`, is not
     junk). `read_duration` returns `None` on a file with no MPEG frames, so no duration flag is
     raised and the manifest records 0.0 s.
   - **Effect downstream.** transmitter's `analyze_show` fails on the file and the whole show
     silently leaves rotation.
   - **How many.** Two such stubs are kept: `gratefuldead-1973-10-29` (packaged) and
     `gratefuldead-1974-09-11` (delivered).
   - **Section 7.** Its "about 6 kept files under 5 s" includes these two, and reads as "a few
     seconds of audio".
   - **Proposed fix.** In `junk._apply_short_rule`, a zero duration does not enter the short rule:
     `... or not e["duration_sec"]: continue`. It only ever drops, and it re-marks 3 corpus rows.
2. **`NONPERF` misses broadcast and PA tags, and the library keeps 6 such files** (5 of them on
   delivered shows):
   - `joerussosalmostdead-2020-02-21`: `Rock and Roll (Played over PA - fades in)`;
   - `railroadearth-2006-02-18`: `Mardi Gras Celebration (Hey Pocky Way on PA)`;
   - `guster-2006-07-28`: `WXRT Intro`;
   - `theotherones-2002-08-03`: `Host #03`, `#12` and `#16`, a WXRT DJ.

   Spec 6(c)'s "zero kept non-performance" is a strict surface. The pre-screen measured a narrow
   addition: on/over the PA, closing/exit/outro music, a case-sensitive call sign plus the existing
   qualifiers, and `host #N`. On the library it newly drops exactly these 6 files and loses no
   music; on the siblings it drops 20, all broadcast or PA.

   The alternative is to accept the misses as a section 7 limitation and list the 6 files for
   `fix --exclude`.
3. **`JUNK_PART` vocabulary:** accept about 200 crowd/tuning variants as a section 7 limitation
   (recommended), or widen the regexes (corpus-gated).
4. **Sample coverage:** the kept strata draw none of the 16 reference crowd, non-performance and
   spoken-broadcast keeps (above).
5. **Pre-existing, outside piece 4, and severe: doubled derivatives.**
   - **What happens.** Some Grateful Dead items carry two `VBR MP3` derivatives of every original
     (`X.mp3` and `X_vbr.mp3`). Both pass every filter arm, because the dedupe keys on (basename,
     duration).
   - **Why those items get picked.** `select_recording` rewards their doubled track count.
   - **How many.** 20 shows ship every song twice: 17 delivered and on the station, unvoiced; 1
     packaged (1973-10-29); 2 held (1972-11-18, 1991-06-25).
   - **Checked.** The orchestrator read `/Volumes/media/lma-radio/delivered/gratefuldead-1974-09-11/manifest.json`
     read-only: 45 tracks, `Scarlet Begonias` twice, then `Mexicali Blues` twice, and so on.
   - **Delivered shows:** gratefuldead-1966-12-01, 1968-10-13, 1969-04-21, 1974-05-25, 1974-09-11,
     1978-12-30, 1987-06-30, 1987-07-06, 1988-03-27, 1988-06-23, 1989-07-18, 1989-08-19,
     1990-03-16, 1990-07-14, 1991-04-05, 1991-10-31, 1995-03-18.
   - **Suggested fix (a separate decision):** keep one derivative per original within the winning
     format.

## Checkpoint A rulings

Operator ruling (Shawn, 2026-10-24 ~12:30, relayed by llama-db), verbatim: **"Recommendations
accepted"**. llama-db put the recommendations to him as follows (verbatim):

1. Row 36 audio-less stubs: FIX — in junk._apply_short_rule a zero duration does not enter the short rule (only ever drops; re-marks 3 corpus rows).
2. NONPERF: FIX — add the pre-screen's measured narrow addition (on/over the PA, closing/exit/outro music, case-sensitive call sign + existing qualifiers, `host #N`); it must newly drop exactly the 6 library files and lose no music (re-measure and show it).
3. JUNK_PART crowd/tuning variants (~200): ACCEPT as a spec section 7 limitation; record it there.
4. Sample coverage: run ONE Sonnet checker over just the 16 reference crowd(13)/non-performance(2)/spoken-broadcast(1) keeps (after the item-2 fix, against the candidate), report the result at Checkpoint B.
5. Doubled _vbr derivatives (20 GD shows): NOT in this branch — a separate small fix after piece 4 (keep one derivative per original within the winning format). Correction to your report: they are not on air — transmitter requires broadcast.m3u and all 17 are unvoiced; the risk is a future `emcee run`. Leave them alone; just list them in the record as a known follow-up.

Open item 5 above is corrected accordingly: the 17 delivered shows are unvoiced, so they are not
on air. The risk is a future `emcee run`.

## After the rulings (Task 10, `cbd35c5`)

- **Code.** Rulings 1-2 are in `junk.py`. Ruling 3 and the doubled-derivative follow-up are in
  spec 2.3 and section 7.
- **Corpus re-measure** (3,547 reference rows). Exactly 9 decisions change, all keep → drop:
  - ruling 1: `bluegroundundergrass-2008-04-04` trk04 (0.17 s), `gd73-10-29d2t01_vbr.mp3`,
    `gd74-09-11v3d2t03_vbr.mp3`;
  - ruling 2:
    - `guster-2006-07-28` `WXRT Intro`;
    - `joerussosalmostdead-2020-02-21` `Rock and Roll (Played over PA - fades in)`;
    - `railroadearth-2006-02-18` `Mardi Gras Celebration (Hey Pocky Way on PA)`;
    - `theotherones-2002-08-03` `Host #03`, `HOST #12` and `Host #16`.
- **Census kinds.** Three of the ruling-2 rows carry census kind `music` or `music-fragment`:
  - the two PA playbacks;
  - the `HOST #12` intermission.

  The rulings class them as non-performance. No other row changed.
- **The task review** (Opus) re-measured independently, over 13,202 short drops and all 75,277
  library track titles. Only the ruled rows change, and every new hit is broadcast or PA material.
- **Candidate re-run `cand-a2.json`.**
  - Arm: `cbd35c55819e`, clean, 12:35:40-12:36:47, sha256 e7976e25….
  - `compare --no-repro-gate`: rc 0.
  - `arms` (`~/.llama-harness/piece4/arms-a2/arms.md`, sha256 f8906564…): changed 1,531, files
    added 2,639, cleared 20, added 34.
  - Both hold lists are identical to `cand.json`'s: 0 `BLOCKS MERGE`, 0 override moves,
    positional fills 10 lost / 12 gained.
  - `cand-a2` differs from `cand` on exactly 7 shows and 9 files, all removals, all ruled.
  - The 40 reference-reproduction lines are those 7 shows plus `soundtribesector9-2005-02-07`,
    5 fields each.
- **Ruling 4 check** (for Checkpoint B).
  - Packet: `~/.llama-harness/piece4/hc-a4/packet.jsonl`, sha256 7f5051ef…. It holds the 16
    reference keeps of census kind crowd (13), non-performance (2) and spoken-broadcast (1).
    `cand-a2` still keeps all 16.
  - One Sonnet checker (answers sha256 975be688…): **10 of 16 agree with the rule.**
  - The 6 it would drop are all crowd-only:
    - `deadandcompany-2015-11-17` `Not Fade Away Chant`;
    - `discobiscuits-2004-11-27` `crowd/tuning jam` (edge);
    - `thebrew-2008-04-12` `Unity College chanting`;
    - `thedead-2015-07-05` `Crowd Doing Not Fade Away` (121 s and 46 s);
    - `umphreysmcgee-2006-10-07` `crowd/1812 Overture` (low confidence).
  - It agreed with keeping both non-performance-census rows (`Banter Promote CD`, `banter -
    promoting the new CD`: band talk) and the spoken-broadcast one (`Stage Banter: Consummation
    Station`).
  - The pre-screen had leaned keep on the crowd chants (a Deadhead tradition), as an optional
    operator ruling.

## Checkpoint B (Task 15, after Tasks 11-14, `a756350`)

- **Candidate re-run `cand-b.json`** (Step 1).
  - Arm: `b5b6d49`, clean, 14:01:58-14:03:07, rc 0, sha256 93705021…. Tallies equal `cand-a2`'s.
  - Per row against `cand-a2`, only `briefing` differs (901 rows, Task 11's reuse rule).
    Filenames, titles and flags are identical.
  - `arms` (`~/.llama-harness/piece4/arms-b/`) is identical to `arms-a2` as JSON: changed 1,531,
    files added 2,639, cleared 20, added 34.
- **Briefing reuse count** (Step 1; spec 5.3).
  - 1,410 changed shows have a `briefing.json`.
  - Under the hold gate, the arm reuses 901.
  - With the gate ignored, as spec 5.3 measured it:
    - 1,014 reusable;
    - 391 `broadcast fields changed`;
    - 5 `briefing guard`.
  - Script: `held_reuse.py`; output: `~/.llama-harness/piece4/ckb/brcount/held_reuse.json`.
  - Against spec 5.3's 1,017 of 1,415, the 5 shows of difference are exactly the 5 that Checkpoint
    A rulings 1-2 (Task 10) stopped changing:
    - `gratefuldead-1973-10-29`;
    - `gratefuldead-1974-09-11`;
    - `guster-2006-07-28`;
    - `joerussosalmostdead-2020-02-21`;
    - `railroadearth-2006-02-18`.
  - All 5 have a briefing, so 3 of them were reusable at the spec's measurement. That figure is
    inferred from the reconciled counts, not checked per show.
- **Reuse check** (Step 2; premises 6-8). Run at `a756350` with `cand-b`, sample 20, seed 47. Output:
  `~/.llama-harness/piece4/ckb/reuse/reuse_check.md`, sha256 0c4daeda…. The station share stayed
  mounted throughout.
  - 1,025 delivered, unvoiced shows change. Excluded from that count:
    - 1,197 with no station copy;
    - 1,541 whose track list is unchanged;
    - 220 with a voiced station copy;
    - 0 metadata misses;
    - 0 without a size.
  - **Premise 6:** 2,559,121,449 bytes (2.56 GB) is not covered by reuse.
    - The figure is structural: the new files, plus every file of a show whose station copy does
      not pair.
    - It ignores library-side audio, so it errs high.
  - **Premise 7:** all 20 sampled shows pair.
    - 357 station files pass the duration check, and 0 paired files fall back.
    - All 31 fallbacks are `not paired`, i.e. the new short-kept files, which must download.
  - **Premise 8:** wall time per show over SMB averages 0.58 s, with a maximum of 1.27 s. It covers
    `plan_reuse` plus the duration reads.
- **Premise 4: FAILS** (Step 3).
  - The reader (Opus) read 10 of the 37 voiced-severe briefings, sampled with seed 47. Packet:
    `~/.llama-harness/piece4/ckb/p4/packet.json`, sha256 f63d65d0…. Verdict:
    `.superpowers/sdd/junk-short-keep/t15-p4read/handback.md`, sha256 1a67957b….
  - **All 10 stored briefings claim that a restored file is absent, excluded or not a track.**
  - The cause is structural. `run_brief` passes the whole `show.json` to the LLM, including
    `excluded_files` (`implausibly short`) and `structure.conflicts`. So each briefing carries a
    caution about the gap, and that caution is false once the piece is restored. `briefing_guard`
    does not check claims about which files are present.
  - Also made wrong: 4 track counts (e.g. "Thirteen tracks") and 4 sequence or segue claims.
  - Three voiced `dj-notes.md` carry a now-false absence claim: `gratefuldead-1968-10-12`,
    `gratefuldead-1977-11-06` and `gratefuldead-1985-06-24`.
  - Sizing: I grepped the library's `briefing.md` read-only
    (`~/.llama-harness/piece4/ckb/brcount/absence_proxy.txt`).
    - Of the 1,014 reusable briefings, 992 name a short-kept file's stem or say `excluded`,
      `implausibly short` or `left out`.
    - Of the arm's 901 reuse rows, 886 do.
  - Spec 5.3's reuse, as built, would ship false absence claims on almost every restored show.
    **This is the operator's decision at Checkpoint B.**
- **Task 13's wrong-audio fix** (for the spec text).
  - Spec 5.4's "the index pairing with equal titles ties each file to its source" holds only
    within one archive item. A re-selection to another item that shares filenames would have
    shipped the old item's audio under the new identifier (138 of 288 multi-item GD dates share
    mp3 filenames).
  - The branch now pairs a library or station manifest only when its `source.identifier` equals
    `show.json`'s identifier. `build_package` re-checks this at package time.

### Operator ruling on premise 4 (Shawn, 2026-10-24 ~14:25, relayed by llama-db)

Verbatim: "2". Option 2 as it was put to him, verbatim: "Reuse only when the briefing provably doesn't mention the change: llama checks first and writes a fresh briefing whenever the stored one names a restored file or uses the 'excluded'/'implausibly short' wording. Deterministic; keeps reuse wherever it's safe; ~98% regenerate in practice; bulk-apply plan budgets ~1,000 fresh briefings." Rejected: (1) a fresh brief for every restored show unconditionally; (3) editing stored briefings. Built as Task 15a (below); the spec 5.3 text change is queued for Task 23.

### Task 15a (`49f9274`): the premise-4 gate, and the re-measure

- `replay.briefing_reusable` refuses a briefing when two things hold:
  - The new show has a **restored** file: a `short_kept` file that is not among the stored show's
    tracks. Already-included short files do not count.
  - The stored briefing mentions it. The check runs over every text field of `Briefing`,
    case-insensitively, by filename, stem or disc/track tail, or by any of the exclusion or absence
    wording, which can appear anywhere in the briefing.
- The reason it gives starts `briefing mentions a restored file`.
- Measured over the 1,014 reusable rows (implementer's outputs:
  `~/.llama-harness/piece4/ckb/15a/`):
  - **refused 1,014 of 1,014, and all 901 of the arm's.** None stays reusable.
  - The wording arm fires on all of them. The name arm fires on 406, and never alone.
  - Dropping the term `track count` would give back 5 rows, 3 of them the arm's. One of those,
    `gratefuldead-1970-06-07`, has a genuinely stale "nine tracks".
- Review: Approved (Opus). The reviewer also checked that a held show followed by a later overrule
  cannot ship a stale briefing.
  - Its one strict-surface Minor: the vocabulary misses some measured phrasings, such as
    `not included`, `not listed` and `does not appear`.
  - Exposure today is 0: the wording arm alone refuses every restored row, and the 45 library
    briefings that pass the wording arm have no `excluded_files`.
- **Re-measure, `cand-b2.json`** (`49f9274`, clean, rc 0, sha256 1c493890…).
  - Against `cand-b`, only `briefing` differs: exactly 901 rows, `reuse` → `fresh`, all inside the
    1,410 changed shows with a briefing.
  - Over those 1,410: 1,112 `fresh`, 298 `none` (held), 0 `reuse`.
  - The 1,685 reuses that remain are all on shows with no restored file.
  - In practice the ruling's "~98% regenerate" is **100%** on today's library.

## Checkpoint B rulings (Shawn, 2026-10-24 ~20:30, relayed by llama-db)

Verbatim:

1. "Go ahead and add them" — the Task 15a deferred Minor: add the measured phrasings "not included", "not listed", "does not appear", "unlisted" to the briefing-reuse gate before merge (strict surface). Built as Task 15b, with the gate counts re-measured.
2. "An NFA chant should absolutely not be dropped; other crowd chants could go either way but inclusion is safer." — the 6 crowd-chant keeps (NFA Chant, 2x 'Crowd Doing Not Fade Away', Unity College chanting, crowd/tuning jam, crowd/1812 Overture) STAY KEPT. No vocabulary change. A pin test holds a Not Fade Away crowd-chant tag kept by the short rule (Task 15b); the spec section 7 text is queued for Task 23.
3. "Confirmed" — `REKEY_MIN_VERSION = 2.18.0`.

Plus "Go for the next tasks" (Tasks 16-21, then Checkpoint C).

## Checkpoint C (Task 22, at `65be006`, after the final review and both fix waves)

Measured 2026-10-25 03:04-03:18 EDT by the peer orchestrator (orch-r5), under
`~/.llama-harness/piece4/`. Read-only against the library; no migration has run. A preliminary
Task 22 at `a693878` (orch-r4, before the fix waves) is superseded by this section: its `cand-c`
rows equalled `cand-b2` on every field, and its dry run equals the one below.

### Final review, fix waves and rulings

- **Final whole-branch review** (Opus, `.superpowers/sdd/junk-short-keep/tfin-rev/handback.md`), then one fix wave, run as two
  dispatches in llama-db's order: FW1 (`a693878..1bcccd1`, I-1 + I-2, one fix round, review clean)
  and FW2 (`1bcccd1..65be006`, review items 3-15 + N-1, N-2, m-1; Opus review: Approved, 0
  Critical/Important, 4 Minors deferred).
- **Operator rulings (Shawn, 2026-10-25 ~01:00, relayed by llama-db), verbatim.** On I-1:
  "\"first format with at least one file left\" seems like the problem. What's the logic of that?
  Why would we pick a format with 1 file for a concert containing many songs?" On I-2: "Yes, fix
  it in this branch."
- **llama-db's rulings on them, verbatim.**
  - I-1 (replaces the reviewer's narrow fix): "the format choice picks the format whose KEPT files
    have the greatest total running time; FORMAT_BY_AUDIO preference order breaks ties only (and
    keep the existing fallback for \"no format keeps anything\", so `excluded` still explains)."
  - I-2 generalized (overrides Checkpoint A ruling 5's "not in this branch"): "within the winning
    format, keep at most one derivative per `original` across ALL kept files, long and short ...
    Which copy: the plain X.mp3 (the newer re-derivation ...). Put the preference in one named
    place — Shawn may still flip it to _vbr ... Dropped copies go to `excluded` with their own
    reason (e.g. \"duplicate derivative\")."
  - Both supersede the plan's Global Constraint on `filter_files`' format choice and CLAUDE.md's
    "first format whose kept set is non-empty" (queued for Task 23).
- **FW1 measurements** (`1bcccd1`; lists under `~/.llama-harness/piece4/fw1/`):
  - Cache, 15,607 items: under mp3, 0 format flips; under flac, 31 flips, all to `24bit Flac`
    with more tracks and running time. Under mp3, 111 items lose 1,970 duplicate copies and
    nothing else changes. In the 23 non-`_vbr` copy groups, the copy kept is the one named after
    its original (23/23), which is also the newer file (23/23).
  - Library, 3,983 shows: 23 shows / 414 files change, every one a `_vbr` dropped as
    `duplicate derivative`. Nothing else drops, adds or reorders, and no song loses its last copy.
  - Selected recording: changes on 20 GD dates (`fw1/m3_changed-r1.json`). Those re-gather and
    re-research in the bulk apply.
- **FW2 measurements** (`~/.llama-harness/piece4/fw2/`, by its implementer):
  - The briefing-reuse gate over `dump.jsonl` refuses 1014/1014, and the reuse arm 901/901. No row
    loses a term or changes reason.
  - The A/B copy-choice changes leave the 179 library shows that have includes/excludes unchanged.

### Arms

| arm | sha | ran (EDT) | output sha256 |
|---|---|---|---|
| base (Checkpoint A, unchanged) | `e37f67024eb3df6ae7fad19357ef3c8a1f84b34c` | 2026-10-24 04:40 | `base.json` b8ea3d048d6cd12e… |
| candidate `cand-c2` (`--rekey-overrides`) | `65be006d19bafefead24dadb69f0e284ca3b2947` (clean) | 03:04-03:05:51 | `cand-c2.json` f502c0c5dac8d050… |

The `config_fingerprint` is the same on both (3f1af9a8…), and the candidate's `llama.__file__` is
inside the worktree. There are 0 `rekey_error` rows.

### Gates

- **`compare`:** with `--no-repro-gate` (operator ruling 2026-10-24 ~11:25, "--no-repro-gate
  approved"), rc 0, and the baseline reproduces 127/148 as at Checkpoint A.
  `~/.llama-harness/piece4/compare-c2/`.
- **`arms`:** rc 0. **`BLOCKS MERGE (0)`** (`arms-c2/arms.md`, sha256 c154d3aa75d21743…). Counts:
  changed 1545, files added 2624, same 1447, unchanged 2438, flags-changed 43, added 34,
  cleared 21. The pre-fix-wave `arms-c` had changed 1531, files added 2639, added 34, cleared 20.
- **Tallies:** clean 1653, clean-changed 1308, needs-brief 4, needs-llm 654, newly-held 220,
  still-held 135, still-held-package 1, structure-changed 8. Against `cand-c`: clean -11,
  clean-changed +11, the rest equal.

### What the fix waves moved (cand-c vs cand-c2)

Exactly 23 rows differ, and they are FW1 M2's 23 de-doubled shows, set-equal
(`ckc2/c_vs_c2_rowdiff.json`, `ckc2/dedoubled23.txt` sha256 b22ea0d9e4eb564a…).

- **Titles and structure on the kept files.**
  - Unchanged: titles, title sources and set labels.
  - Play order is kept on 23/23 shows, and every set break lands on the same song (now the plain
    copy).
  - 0 non-`_vbr` files are dropped.
  - This closes the Checkpoint C question r4 left unmeasured (sibling-format / slice-3 C /
    sibling-align could have fired).
- **Outcomes.**
  - 11 shows go `clean` → `clean-changed`, because the track list changed.
  - `stringcheeseincident-1999-12-31` goes `clean-changed` → `clean`, because it was hand-repaired
    to the single list.
  - Briefing goes `reuse` → `fresh` on 12 GD shows (`briefing_reusable` refuses: the stored list is
    the doubled one) and `none` → `fresh` on `gratefuldead-1989-07-18`; `fresh` → `reuse` on sci.
    That is 13 fresh briefs at apply.
- **Segue marks move on 9 GD shows** (read-only investigation t22-seg, Opus,
  `.superpowers/sdd/junk-short-keep/t22-seg/handback.md`; evidence under `~/.llama-harness/piece4/t22-seg/`).
  - **The cause is not FW1's rule and not `align()`.** `gather.build_canonical` ranks the LMA parses
    by `target_count=len(kept)` to pick the segue donor for `blend_segues` (and the canonical
    itself when there is no setlist.fm). The doubled count steered that choice arbitrarily.
    - Patching only `junk._dedupe_derivatives` to a no-op reproduces cand-c's segues exactly, on
      18/18 arm-rows.
  - **Song-level result** over the 9 shows: 33 marks change, 21 gained and 12 lost.
    - The de-doubled arm is right on 18, wrong on 9, unclear on 6.
    - Agreement with the description majority over 179 voted tracks: doubled 153, de-doubled 156.
  - **The doubled arm's "right" marks sit on the wrong transition** ("Bird Song > Bird Song"
    across the `_vbr` twin).
  - **Worst case: `gratefuldead-1988-06-23`** (delivered) loses 5 real marks (He's Gone > Drums >
    Space > I Need A Miracle >, Watchtower >; 8/9-8/8 of descriptions). The new donor is the chosen
    recording's description, which has no `>` at all.
  - **The wrong ones fall into three pre-existing classes:**
    - (A) a donor that carries no segues;
    - (B) run-on chosen descriptions (parse_setlist's documented merge);
    - (C) `blend_segues` pooling by exact title (`Space` vs `Jam`).
  - **Fix (A), tested in memory only:** rank the donor only among LMA parses that carry a segue.
    It restores 4 of 1988-06-23's 5 marks and changes nothing on the other 8 shows (agreement
    160/179). Its effect on the rest of the library is unmeasured. It is not built: it is a
    Checkpoint C question.
- **Flags:**
  - `gratefuldead-1972-11-18` (needs-llm both arms) surfaces 15 `research asserts unknown song`.
    The 4a gate's `asserted` count had been doubled (16 vs 15); now it is 9 vs 15. The tape is 1
    set of 9 songs against jerrybase's 2, so the flags are accurate.
  - `gratefuldead-1990-07-14` and `gratefuldead-1989-07-18` lose `low-confidence structure
    alignment`, because coverage doubles (0.47 → 0.95, 0.5 → 1.0). 1990-07-14 gains a jerrybase
    closer flag that the doubled ambiguity had hidden. Both stay needs-llm (stored alignment
    `llm`).

### Migration dry run (read-only, real library)

`./.venv/bin/python scripts/rekey_overrides.py`, rc 0, at 03:07: **606 to rekey, 0 refused, 0
already migrated, 3377 without positional keys.** The output equals the Checkpoint C preliminary
(`ckc/dryrun.out`), timestamps aside: 3,203 titles / 427 breaks / 365 encore keys, which is spec
4.3 "Measured today" exactly. The process check printed `llama processes running: none` plus the
interactive-loop note. Checked afterwards: no `~/.llama/.rekey.lock`, and nothing under `~/.llama`
newer than the marker. Output `~/.llama-harness/piece4/ckc2/dryrun.out` (sha256 0efd271c5cf4495e…).
As expected, the de-doubling does not move it, because the dry run judges legacy `show.json` with
`short_keep=False`, which stays v2.17.0 byte-identical.

### Suite

`./.venv/bin/python -m pytest -q -p no:cacheprovider` at `65be006`: **5442 passed, 1 skipped, 8
deselected, 26 warnings in 52.39s**, rc 0. `llama.__file__` was inside the worktree. The 26
warnings are the pre-existing Python 3.14 `multiprocessing` fork() DeprecationWarnings
(test_atomic_write / concurrency / ledger_concurrency / locks / sessions), at the same count as
every task since the baseline.

### Mutation record

`docs/superpowers/2026-10-24-junk-short-keep-sdd/mutation.md` (Task 21): 21 mutants, 20 caught by
a predicted test, 1 survived the predicted test ((j): a plan prediction error, ruled, no gap), and
0 hangs. The fix waves came after it and carry their own scratch mutants: FW1, 6 + 3; FW2, 9; each
red as predicted (implementer reports).

### Checkpoint C rulings (Shawn, 2026-10-25 ~09:05, relayed by llama-db)

Verbatim: **"Go on both. Recommendations accepted on all points"**.

llama-db's reading, verbatim: "your recommendation stands on every question — Q1 no _vbr flip; Q2
keep "named after its original"; Q3 let the bulk apply surface gd1970-05-06 / gd1985-11-10, fix by
hand; Q4 accept the 20 re-selections; Q5 leave stale _vbr excludes; Q6 BUILD fix (A) in this branch
(Opus implementer, Opus review, whole-library replay arm vs cand-c2, STOP and report on any
unexplained move); Q7 no code change, one runbook line in Task 23; Q8 accept; Q9 M1 rides with (A),
M2 left."

The questions, as put (orch-r5's Checkpoint C report): Q1 flip the copy preference to `_vbr`; Q2
the copy pick in the 23 non-`_vbr` groups; Q3 the 2 re-selections that orphan operator overrides;
Q4 the 20 selected-recording changes; Q5 the stale `_vbr` excludes on the 5 hand-repaired shows;
Q6 fix (A), the segue donor; Q7 `--restore`'s mtime "re-delivered" listing; Q8 FW2's refuse-more
concerns; Q9 FW2 review Minors M1 (apostrophe look-alikes) and M2 (a both-excluded pair counted
twice).
