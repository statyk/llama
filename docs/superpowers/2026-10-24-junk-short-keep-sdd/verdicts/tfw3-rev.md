# tfw3-rev: review of FW3 (eacad39..8162620)

### Spec Compliance

- ✅ (A) matches the brief. `packages/llama/src/llama/stages/gather.py:930-937`: the donor candidates are now `p.source != "setlist.fm" and any(i.segue for i in p.parsed.items)`. With no such parse, `rank_parses` gets `[]`, `best_lma` is None, and `blend_segues(canonical, None)` returns the winner unchanged (`structure.py:578`). Things the diff leaves alone:
  - `best = rank_parses(parses, ...)`, `rank_parses`, `blend_segues` and align(): the diff has no hunk in `structure.py`.
  - The no-setlist.fm path: the edit sits inside `if best is not None and best.source == "setlist.fm"`.
  - Every global-constraint name: I grepped the diff for them and none appears.
- ✅ The three tests the brief asks for sit beside build_canonical's corroboration tests (`test_stage_gather.py:2397-2459`):
  - Test 1 fails first on the old code. The chosen parse has 7 items, so |7-7|=0 and it wins the count against the sibling's 8 items, but it carries no segue. The assertion is on the exact segued titles.
  - Tests 2 and 3 are pins, as the brief specifies: test 2 has no segue-bearing LMA parse, test 3 has the segue-bearing parse already best by count.
- ✅ (B) matches the brief. `replay.py:278` adds `ʻ`/`ʹ` to `_APOSTROPHES`, and the comment and docstring are updated (`replay.py:261`, `:284-286`). The test is parametrized over both marks and asserts the split copy and the exact refusal string (`test_replay.py:1197-1206`).
- ✅ (B) can only refuse more. `_normalised` has one call site, `_restored_mentions` (`replay.py:428`), which only collects hits that refuse. Before the fold, U+02BB and U+02B9 (category Lm) are `\w` characters, so the fold can only:
  - split a token at the mark (copy 3), or
  - trim the mark off a token's edge (copies 1 and 2), or
  - drop a token that was nothing but the mark.

  In each case a negation, window or head that matched before still matches: copies 1 and 2 keep the same token boundaries apart from the trimmed edges, and a term fires on any copy. New readings can be added (`notʻlisted`, `canʻt`, `ʻnot`), but none is lost. The implementer's corpus re-measure agrees: `fw3/gate_fw3.txt` shows 1014/1014 refused, a reuse arm of 901 and 0 rows changed.
- ✅ The implementer's row-diff claim holds. `fw3/rowdiff.py` compares every key of every row. 71 rows differ, only in `segues`, `segue_changes`, `outcome` (clean -> clean-changed) and `briefing` (reuse -> fresh). No other field differs: 0 UNEXPLAINED.
- ⚠️ I did not re-run the suite. I am taking the implementer's 5447 passed / 1 skipped / 8 deselected as reported, per my instructions.

### Strengths

- (A) is the minimal change the brief asked for: one filter on the donor list, with a comment that names the defect and the exemplar show.
- The pins are built so that they would catch a regression in the frozen behaviour, rather than asserting nothing.
- (B)'s test asserts the end-to-end refusal string, not just the normalised text.
- The measurement work is careful and honest about its own bias:
  - A mechanism check asserts on all 71 shows that the replay's segues equal cand-d's.
  - A second, notating-only vote is reported alongside the t22-seg vote.
  - The 7 last-track marks and the 36 pooled transfers are flagged unprompted.

### Measured effect of (A) on shipped output (my own checks)

**I hand-checked 50 marks the t22-seg vote calls "wrong".** These are all of the "wrong" marks on 9 shows, plus 1 each from 2 more (bobweir-2012-04-27, deadandcompany-2015-11-20, deadandcompany-2017-06-09, radiators-2010-10-29, warrenzevon-1976-10-13, furthur-2011-07-28, gratefuldead-1990-12-12, buckethead-2006-03-10, furthur-2010-02-12 King Solomon's Marbles, gratefuldead-1986-03-24 High Time). I read them against every cached description of the show, read-only, using `~/.llama-harness/piece4/tfw3-rev/desc.py`.

- **26 are plausibly right.**
  - bobweir 10/10: one careful taper (`Jack Straw >`, `Lost Sailor >`, `Playing > Dark Star > Josephine > Other One > Days Between >`), and the siblings carry no notation at all.
  - D&C 2017-06-09 9/9: one notating taper, with no description contradicting it.
  - D&C 2015 set 2, 7 marks (Eyes > Let It Grow > Terrapin > Drums > Space > Wheel > Looks Like Rain).
- **20 are truly false.**
  - D&C 2015 3: `Music Never Stopped > Outro`, `Sugar Magnolia > Crowd` and `Ripple > Outro`, all set closers.
  - radiators 3, buckethead 3 and warrenzevon-1976 3: medley tracks whose mark contradicts the selected recording's own description.
  - furthur-2011-07-28 5: the donor puts `>` after every set-2 item, and the official SBD and another taper contradict it with commas.
  - gratefuldead-1990-12-12 2: `Looks Like Rain >` (3 of 12 notating parses), and `Not Fade Away >` running into the encore.
  - King Solomon's Marbles 1: `> drums` within the track, while 6 descriptions write `,`.
- **4 are contested**: D&C 2015 Shakedown and Brown-Eyed Women, gratefuldead-1990 Rider (7 descriptions mark it, others use commas), and gratefuldead-1986 High Time (7 mark it against comma lists).

**The implementer's mechanical verdict rule is not sound as a correctness measure.**
- The t22-seg "wrong" bucket is only about 40% truly false. A description with no `>` anywhere counts as a "no" vote, which inflates "wrong".
- The notating-only "wrong/wrong" bucket is reliable: of its 24 marks I checked 18, and 17 are false with 1 contested. But it misses false marks that sit in its "unclear" bucket:
  - the 3 D&C 2015 closers;
  - 4 on warrenzevon-2000-04-22, graded "unclear" on both votes: `Excitable Boy > Banter` and similar, a song running into banter within one track, shipped as a segue into the next song.
- My estimate is about 32-40 false marks out of 328 gained (about 10-12%), of which about 20-25 are on delivered shows, against about 190-290 real segues restored. These 71 shows today ship with none of their segues.

**Four cheap guards, measured in memory on the 71 shows** (`~/.llama-harness/piece4/tfw3-rev/guards*.py` and `guards*/`). Each one monkeypatches `blend_segues` in the probe's own process only; nothing in the tree changed.

| guard | gained marks removed | right/right removed | false (wrong/wrong) removed | verdict |
|---|---|---|---|---|
| G1: donor and winner title must each be unique | 24 | 12 | 6 | net loss |
| G1b: decline when the donor's flags for a title disagree | 11 | 7 | 2 | net loss |
| G2: the successor titles must match | 85 | 22 (38 right-ish) | 12 | net loss |
| G3: no mark on the setlist.fm canonical's last item of a set | 19 | about 8 right | 9 | poor: setlist.fm's set labels differ from the tape's |
| G5: no transfer from a donor item followed by `is_filler` or by nothing | 9 | 0 | about 8 false (D&C 2015 x3, furthur `Johnny B Goode`, warrenzevon-2000 x4) | the only clean one |

- G5 removes 1 real mark: D&C 2015 Terrapin > `Drums Intro`.
- G5 is threshold-free, and it could be applied to the donor inside `build_canonical` without touching `blend_segues`.
- G5 also changes shows outside the 71, where the old donor already carried segues. It therefore needs its own whole-library arm and review, and is not a bolt-on to FW3.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None in the code. (A) as built adds false marks at a rate I would ship (see Assessment), so the measured effect is not Important.

#### Minor (Nice to Have)

1. **Steering-worst class, filed rather than fixed: pooling contradicts the selected recording's own notes.** `structure.py:580-587`, which is frozen, pools marks by exact title.
   - On 11 gained marks (5 shows: buckethead x3, derektrucksband-2007-07-21 x1, joerussosalmostdead-2019-03-02 x1, radiators x3, warrenzevon-1976 x3; 8 of the 11 on delivered shows), the donor IS the chosen description. Its own alignment matches the track and places no mark, yet a mark ships from another occurrence of a repeated title such as `Crazy Mona`, `Turbin`, `[interview]` or `Excitable Boy`.
   - Example: radiators #4 `Crazy Mona>Break On Through>Crazy Mona` is followed by a plain `5. This Wheel's On Fire`.
   - This is pre-existing `blend_segues` behaviour that (A) newly reaches. The natural guards G1 and G1b cost more right marks than they save.
   - The operator has no per-track segue override, and a structure override loses every segue, so these cannot be hand-corrected one by one. A follow-up design should probably prefer the chosen description's own alignment wherever it matches the track.
2. **Filed: donor marks into filler or into nothing** (`> Outro`, `> Crowd`, `> Banter`, a final `>`). G5 above fixes about 8 of them for 1 real mark lost. The same false class already ships on the no-setlist.fm path wherever such a parse wins the canonical, so a fix there needs scoping by the operator.
3. **Nit**: `replay.py:261` (108 chars) and `test_replay.py:1206` (106 chars) are longer than their neighbours. No line-length limit is configured, so this is cosmetic.

### Assessment

**Task quality:** Approved.

**Reasoning:** Both changes match the brief exactly. (B) can only refuse more, by construction and by the corpus re-measure. (A)'s measured effect is strongly net positive: about 190-290 real segues restored on 71 shows that currently ship with none, against about 32-40 false marks (10-12%). The t22-seg vote overstates the false marks: only about 40% of its "wrong" marks are truly false.

**Recommendation: ship (A) as is, together with (B).**
- Do not revert. Reverting keeps the confirmed real losses (gratefuldead-1988-06-23 regains 4 of its 5 marks, as the brief required; Space stays missing, as expected) on dozens of delivered shows.
- Do not bolt a guard onto FW3. Of the five guards measured, only G5 (no transfer from a donor item followed by filler or by nothing; no new constant) is clean, and it fixes about 8 of the roughly 35 false marks. It also changes shows beyond the 71, so it needs its own whole-library arm.
- File G5 and the pooling self-contradiction class (Minor 1) as follow-ups.
- If the operator wants the steering-worst marks gone before the bulk apply, run G5 plus a chosen-own-alignment rule for pooled titles as one small measured task.

Probe files are all read-only and under `~/.llama-harness/piece4/tfw3-rev/`: `desc.py`, `idx.json`, `closers.py`, `guards.py`, `guards1b.py`, `guards5.py`, and the outputs in `guards/`, `guards1b/` and `guards5/`.
