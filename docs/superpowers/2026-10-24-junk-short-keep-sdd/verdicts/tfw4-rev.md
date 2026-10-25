### Spec Compliance

- ✅ Spec compliant with the brief's code requirements, checked item by item:
  - **G5 (gather.py:882-898, 965).** It clears a donor item's segue when the next donor item `is_filler` or when there is no next item. It runs on the ranked donor only, after `rank_parses` (gather.py:965), so the donor choice is unchanged. `is_filler`/`_FILLER`, `blend_segues` and `rank_parses` are not in the diff (it touches only gather.py and test_stage_gather.py).
  - **Item 2 (gather.py:986-1009, 1795).**
    - `donor_segues` aligns the G5'd, cleaned donor (gather.py:979) to the same final tracks with the same `align()` call and aliases.
    - It takes the matched donor item's segue by position and falls back to the pooled segue elsewhere (gather.py:1006).
    - It changes only `segues`. It is threshold-free and adds no constant.
    - It is called only on the deterministic (non-override) branch.
  - Frozen names: grep over the diff finds no edit to `align`, `_window_match`, `is_filler`, `_FILLER`, `rank_parses`, `blend_segues`, `TAUTOLOGICAL_TITLE_SOURCES` or any junk/title-hygiene constant.
  - Tests (a)-(f) are present at test_stage_gather.py:2504, 2528, 2545, 4827, 4851, 4879, 4916 and 4923. They are built from verbatim cached descriptions.
- ⚠️ **Cannot verify from the diff.** On the LLM realignment branch (gather.py ~1873-1902), `align_structure`'s result replaces `result` wholesale. Item 2's segues are then lost, and the pooled marks reach that prompt. The replay cannot measure this path. The controller should treat it as unmeasured, not as covered.

### Strengths
- G5 is placed narrowly: on the ranked donor, before the blend. Item 2 reuses the same G5'd donor, so `Ripple > Outro` cannot come back through the donor's own alignment. test_stage_gather.py:4939 pins this.
- `donor_segues` is small, pure and deterministic. Leaving sets, `matched`, coverage and conflicts with the canonical alignment is the right boundary (gather.py:986-1009).
- `CanonicalBuild.segue_donor` is a defaulted field at the end of the NamedTuple. **Named risk:** positional construction or unpacking at call sites. **Checked:** I grepped every `build_canonical(`/`CanonicalBuild(` call site in packages/ and scripts/. All use keywords or attribute access.
- The measurement is unusually thorough: an exact G5-only/item-2 decomposition, three donor variants, and a per-show table. The row diff confirms no title, set, break, filename or flag change.

### Issues

#### Critical (Must Fix)
None in the code as an implementation of the brief.

#### Important (Should Fix)

**1. Item 2 adds a class of false segues that the reported votes undercount.**
Location: gather.py:1006, the gain side of `donor_segues`. The mechanism is align()'s frozen fuzzy matching applied to raw LMA parses.

What happens:
- `align()` accepts a single-title hit by subphrase (`_window_match` -> `fuzzy_title_eq`).
- Two parse shapes then put a `>` on a track that does not flow into the next one:
  - **Run-on blob.** The parser merges a one-line description's set-1 closer with the set-2 opener into one item, for example `The Music Never Stopped Touch Of Gray->`. The closer's track matches that item and takes the `->` that belongs after the opener.
  - **First-component-only hit.** A multi-song track (`Rock On [Essex] > Zero (tease)`) matches only its first item and takes that item's internal `>`.
- Pooling never transferred these, because it matches exact `normalized` titles.

Measured with my read-only probe (`~/.llama-harness/piece4/tfw4-rev/which.py`, `cls3.py`, `minority.py`, `cls.py`). The probe replays every item-2 show and records which donor item each changed track matched, by encoding each item's index in its `set` field.

**Cross-set gains: 79.**
- 44 have no `>` in the track's own title.
- 26 lose the all-parses vote (k*2<n, n>=3). 24 of those are on delivered shows, almost all Grateful Dead.
- 28 gains match a two-song blob that names the next track (25 delivered). 21 of them cross a set break.
- I verified these by description:

| show | track | marked flow | parse that carries the mark |
|---|---|---|---|
| gratefuldead-1987-03-27 | #8 | Music Never Stopped -> Touch of Grey | the selected one-line description `... The Music Never Stopped Touch Of Gray->`; 1/17 parses mark it |
| gratefuldead-1978-12-31 | #18 | Around And Around -> Dark Star | 1/16 |
| gratefuldead-1981-09-12 | #10 | I Know You Rider -> Scarlet Begonias | 2/17 |
| gratefuldead-1990-07-08 | #9 | Let It Grow -> Samson | 1/16 |
| gratefuldead-1989-10-09 | #9 | MNS -> Playin' | 3/27 |

- `verdict.py` rates 17 of these 26 "unclear", not "wrong". It counts `ch=True` as own-yes, but `ch` reads the same blob. So the reported 26/34 "wrong" and the 92% "carries the chosen's own mark" both undercount this class.
- 30 of the 33 suspect gains (the 26 cross-set minority plus the 7 last-track) are not in today's stored show.json. They would be new false output, not restored output.

**Last-track gains: 7, all wrong.** Each is a segue into nothing. 5 are on delivered shows:
- gratefuldead-1967-10-22 #7
- greenskybluegrass-2016-10-31 #17 (`Freebird Intro > Rocky Top`, one track)
- smashingpumpkins-2000-02-05 #13
- smashingpumpkins-2007-06-06 #33
- warrenzevon-2000-05-29 #11

The other 2 are on held shows: gratefuldead-1979-02-03 #12 (a blob) and robertrandolphandthefamilyband-2005-02-20 #14. Every one is a first-component or blob hit. I read the descriptions for 1967-10-22, gsbg, smashingpumpkins-2000 and warrenzevon.

**The bulk of the gains is right.**
- I drew 16 random interior gains on delivered shows (`tfw4-rev/sample.txt`, seed 20261025). All 16 check out against the cached descriptions:
  - read in full against every description: jeffaustinband-2018-04-28 #4, gratefuldead-1989-07-02 #19, furthur-2010-11-12 #16, gratefuldead-1968-12-07 #5, yondermountainstringband-1999-10-02 #12, thedead-2015-07-03 #14;
  - checked against the selected description: ymsb-2004-06-11 #12, sci-2000-05-05 #9, plf-2005-12-10 #13, jrad-2016-02-12 #12, dac-2016-07-15 #2, gd-1991-09-04 #16, gd-1985-09-07 #18, db-2007-10-31 #12, sci-2007-07-28 #23, db-2006-12-30 #8.
- With the implementer's 12-row sample, that is 28/28 interior gains right.
- So the false class sits almost entirely in last-track and cross-set positions. My estimate is about 35-60 false gains of 2124, against roughly 1900+ right ones.

**2. G5 costs 5 real marks; the stated cost is 1** (gather.py:893-895).
- The docstring still says "Measured cost: one real mark". The measured cost is 5:
  - joerussosalmostdead-2016-02-11 #5 Eyes --> `Cumberland Blues (Band Intros)`
  - littlefeat-1975-09-01 #6 `Dixie Chicken >` `Tripe Face Boogie / crowd`
  - railroadearth-2013-07-12 #17 `The Forecast> River Intro Jam>`
  - kellerwilliams-2005-02-12 #23
  - deadandcompany-2015-11-20 #11 (Terrapin)
- I confirmed the first three as real against the cached descriptions.
- Four of the five come from `is_filler` matching a word inside a real title. That predicate is frozen, so no narrow fix exists without a new G5-local predicate.
- The loss is small (4 delivered shows). I would accept it, and correct the docstring.

#### Minor (Nice to Have)
- test_stage_gather.py:4879 and :4916 assert subsets (`<=`). They pin that the fallback and regained marks survive, but not that nothing extra is added. The moe test also silently accepts the known #5 `Bullet ->` loss; a comment naming it would keep it from looking like an oversight.
- No test pins "G5 after ranking, never before the segue-bearing filter". That would be a donor emptied by G5 that must not be swapped for another parse. The claim holds in the code (gather.py:960-966); the pin is missing.
- Pooled marks still feed `correspondence._merge_legal` and the `align_structure` prompt via the blended canonical (gather.py:966). Item 2 corrects only the shipped `segues`. This is acceptable for the scope, but the residue should be noted.
- The six item-2 real losses come from the donor's own alignment landing on the wrong occurrence. I spot-checked discobiscuits-2006-12-31 #15: the second `Basis for a Day` (next item `Caterpillar`) was taken for a track followed by `Bazaar Escape`. Confirmed real and lost.

### Recommendation, with cost per option (from the evidence; where marked, not re-measured)

1. **Ship FW4 as built.**
   - Real marks lost: 6 (item 2) + 5 (G5).
   - About 1900+ right marks gained. This includes 489 that today's stored show.json ships and that cand-d would otherwise drop.
   - Also ships about 31 new false marks on delivered shows: 24 cross-set minority-vote and 5 last-track, plus a few more first-component hits. These are concentrated on Grateful Dead shows and reach the briefing LLM.
   - +383 fresh briefs.
2. **G5 + item 2 remove-only.**
   - Real marks lost: 6 + 5. No false gains.
   - Gives up about 1900 right gains, including the 489 currently-shipped marks. The bulk apply would remove those from shows that air today, so this is worse for shipped output than option 1.
   - Fresh briefs: at most about 38. This is my estimate from rowdiff-e: shows with item-2 removals or G5 that flip reuse to fresh, 23 + 9 + 4 + 2. Not measured.
3. **Ship with a named narrow fix (RECOMMENDED).** The own alignment may ADD a mark only when both hold, in `donor_segues` (gather.py:1006); removals stay as built:
   - (a) the track is not the show's last track;
   - (b) the track's canonical-alignment set (`result.sets[k]`) equals the next track's, or the track's own title ends in `>`/`->`.
   - Both conditions are structural. There is no tuned constant.
   - From the evidence:

| rule | gains it drops | judgment |
|---|---|---|
| (a) | 7 | all wrong |
| (b) | 44 untagged cross-set | 26 minority-vote, likely false; 13 majority, 5 thin |

   - Among (b)'s 13 majority-vote drops: gd-1987-04-19 NFA>Brokedown 11/11, gd-1974-07-29 WRS>He's Gone 8/8, gd-1973-11-21 6/6, gd-1971-12-15 Lovelight>OMSN 5/5. In each, the shipped set labels already contradict the mark.
   - Real marks lost stay 6 + 5. The fresh-brief count falls by up to a few dozen from 383; estimated, not measured.
   - This needs one arm (cand-f) and a row diff against cand-e before Task 23.
   - A more precise but heuristic alternative to (b) is "decline when the matched donor item also names the next track". My substring version catches 16 of the 26 cross-set minority gains and misses spelling variants (Gray/Grey, Playin'/Playing).
4. **Revert item 2, keep G5.** This loses the 11 targeted marks the ruling asked for, plus every gain. It is not recommended.

### Assessment

**Task quality:** Needs fixes.

**Reasoning:** The code faithfully implements the brief and is clean and well-pinned. But the measured effect of item 2's gain side ships a systematic false-segue class on delivered Grateful Dead shows. That class is run-on-parse blobs and first-component hits, landing across set breaks and on last tracks. The reported vote undercounts it because `ch` reads the same blob. Add the two structural add-guards (option 3), measure them, and correct G5's stated cost (gather.py:893) before Task 23. If no further measurement is wanted, option 1 beats option 2 on shipped correctness.

Checks run (all read-only; scratch output in ~/.llama-harness/piece4/tfw4-rev/):
- which.py replayed 1055 shows in-process under the live worktree code (shadow workspaces in scratch). It recorded each changed track's matched donor item.
- cls.py, cls2.py, cls3.py, minority.py and stored.py classify gains by position, by match type, by vote, and against stored show.json.
- sample.py drew the random sample. I ran near.py reads of the cached descriptions for 26 shows.
