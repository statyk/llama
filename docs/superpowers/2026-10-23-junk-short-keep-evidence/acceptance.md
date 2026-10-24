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
