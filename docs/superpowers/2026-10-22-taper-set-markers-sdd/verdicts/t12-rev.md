### Spec Compliance — ❌ (2 Important, both cheap to fix); ⚠️ cannot verify the gate2 rows one by one (I checked the headline numbers only)

I reviewed the diff 67291bd..5a5343f in two passes. Pass 1 was `taper.py`, the docs, and the probe and its tests. Pass 2 was the test file, read where a risk pointed at it. I re-ran the reader over all 15,607 cached `md_*.json` files at 3d1c1e7 (before R-ITEM), 025e713 (after R-ITEM) and HEAD, using scratch `git archive` copies shadowed through `PYTHONPATH` (I checked `llama.__file__` each time). I ran one mutant in a scratch copy. The worktree, index and HEAD were not touched: HEAD is still 5a5343f and `git status` is clean.

**Mandated checks**
- **(a) Protected names: ✅.** Grepping the +/- lines of the diff for `normalize_song`, `DEFAULT_ALIASES`, `is_real_title`, `_TRACK_NUM_PREFIX`, `_STRUCTURE_PREFIX`, `_FILLER`/`is_filler`, `_ENCORE_MARKER`, `closer_contradictions`, and every do-not-retune constant name gives 0 hits. `is_filler` and `_ENCORE_MARKER` appear only as unchanged context. Only `taper.py` changed under `packages/llama/src`.
- **(b) setlist.py: ✅.** `git diff main -- packages/llama/src/llama/setlist.py` is empty (rc 0). So are `structure.py`, `songs.py`, `titles.py` and `jerrybase.py`.
- **(c) Amendments vs the operator's words: ❌.** The rulings and the amendments differ in these places:
  1. **Ruling (b) names only `(duration|time)`.** The amendment also admits `...`/`…` and attributes it to the operator. Spec §1 says "…in parentheses, `(50:28)` or `(9:30PM - 10:46PM)`, **or by `...`**". The plan's Global Constraints say "a `(duration)`, a `(time range)` **or `...`**", and so does the module docstring. cpa-decl had proposed `...` (and `word`), and the operator kept only `(duration|time)`. The `...` is load-bearing: about 20 cached header lines are headers only because of it (`Set 2 cont...`, `Set II Cont...`, `Disc 1 - Set I...`, `Disc 3-Set 2 cont...`). All of them are genuine headers, so the behaviour is benign, but the operator did not rule it.
  2. **"`Disc`, `Disk` and `CD` are interchangeable in these shapes and in `Disc N (Set M)`, `Disc N - Set M` and `Disc N / Set M`"** is the implementer's call (handback judgment call 6), written into the operator-ruling paragraph. It widens the original spec forms too: `CD 2 (Set 2)` and `Disk 2 - Set 2` are now set headers.
  3. **Spec-listed shapes that are not in cpa-decl's family.** `Disc 1, Set 1` (a comma separator) and `Set 1-Disk 1` are tested and admitted, but I found neither in cpa-decl's handback or its `q2_rows.jsonl` N-FORM/R-FORM evidence. Real `Disc R, Set R` lines do exist in the cache (about 20, all genuine), so this is a wording and attribution problem, not a behaviour problem.
  4. **Ruling (d) says "an encore *boundary* after the taper's last placed numbered break".** The amendment says "an `encore` label on any track after" it (`today_sets[b:]`). That also vetoes an encore boundary at the break itself (the test "starting right at it") and an encore that starts before the break and runs past it. Both own less, so it is conservative, but it is a broader operationalisation than the ruling's words and should be marked as such.
  5. **One shape in cpa-decl's listed family is excluded: `Set I (Disc 1)`** (discobiscuits-2007-05-27). The test labels it "not in the ruling's list", but the ruling admits "the same family cpa-decl listed", and the dispatch excluded only `Set 1/2` and `(Start Set N)`. Its yield is 0: cpa-decl says that row would decline anyway. It is safe-direction, but it is still a deviation (Minor below).

  Everything else in the amendments matches the rulings, and nothing outside the inserted paragraphs changed.

**Items 1–7 against the dispatch:** 1 ✅, 2 ✅, 3 ✅, 4 ❌ (comma rule, see Important #1), 5 ✅ (apart from the `...` wording above), 6 ✅ (apart from the wording above and the `Set I (Disc 1)` miss), 7 ✅. Step 3 is ✅: gate2's headline numbers match the handback verbatim (77/186 = 0.414; 42/54; 53/54 including filler-only; library 648 owned, encore folded 0; delta in-scope identical: True).

### Strengths
- **Ruling (d) does what it is meant to.** Library "encore folded" goes from 31 to 0, and all 28 C-RULE folds become "computed as today". It runs only after a successful placement, so placement-decline reasons are kept.
- **The new header shapes did not let prose or lineage in (risk 1).** Across the whole cache, items 5–6 add 1,004 header lines and remove 0. Grouped by shape, every one is a disc/set/cont/time header. `Set 1 (acoustic)`, `Set I (45:00) is Bobby…`, `Set 1 (50:28) Bertha`, `Disc 1 set in Boston`, `Disc 1 Set 1 (taper: Joe)`, `Set 1 cd 1 lineage: …`, `Disk 3: Encore` and `CD2 Set 2 Part1` all stay song lines (constructed probe).
- **The single-prefix strip mostly repairs real titles (risk 2).** Of 176 "number kept" changes over the cache, almost all fix real numeric titles: `32 Things`, `40 Miles From Denver`, `44 Blues`, `13 Days`, `20 Eyes`, `99 Year Blues`, `986 Foot Tall Trees`, `3 Dimes Down`, `100 Years from Now`. 2,161 `sNtNN`/`NN:` strips were all prefix removals. Disco Biscuits' song `42` is newly kept.
- **`None` detection does not catch other titles (risk 5).** `Nonesuch` and `Noneofyourbusiness` pass. Only a title starting with the word `None` voids (`None of Us Are Free`), which is pinned as accepted collateral and is safe-direction.
- **The set-and-encore pre-split (risk 6) is sound.** `Set 2: Scarlet, Fire, Sugar Magnolia, E: Baby Blue` (with or without the comma) still starts the encore at Baby Blue. `Set 2 & Encore: Scarlet > Fire, E: Baby Blue` keeps the header whole and still splits the `E:`. The implementer was right to keep the split over joined lines (the ratdog-2007-11-03 finding) and to pin it.
- **The (d) boundary index is right (risk 4).** `boundaries` are 1-based "after track b", so `today_sets[b:]` is exactly the tracks after the last break. A `b-1` mutant is caught by the three-set test.
- **The tests are clean.** The focused tests (62, including `scripts/test_taper_probe.py`) pass with no warnings. RED/GREEN discipline is visible commit by commit, and the real-case literals are verbatim.
- **The probe is reproducible.** The new `delta` subcommand makes the gate2 comparison re-runnable, and the in-scope set is proven identical.

### Issues

**Critical:** none.

**Important**

1. **The comma rule merges two real songs on one numbered line, and that defeats placement's merged-track guard** (`taper.py` `_song_titles`, the `enumerated and numbered` branch, `_TITLE_COMMA`). The answer to risk 3 is no: the dispatch asked to keep commas on numbered *one-title* lines, but the code has no one-title test, so every numbered line on an enumerated text becomes one item.
   - **Real merges from the cache:**
     - `05 - Native End, Open E` (sts9-2005-02-15): two STS9 songs;
     - `10. TUG > Mama's Boy (Ending), Anesthetic Highway > …` (DBB1998-05-29);
     - `Bill talks, Silver Screen ^^ 6:13`;
     - `5. Phil says "Take a Step Back", Technical Problems`.
   - **Why it matters.** `fuzzy_title_eq` tolerates a dropped tail (`"jack straw ripple"` equals `"jack straw"`), so a merged boundary item matches its first song. Usually the "non-filler between" check then declines, but not always. I built this case:
     - Text: `Set 1 / 1. Bertha / 2. Sugaree / 3. Jack Straw, Ripple / Set 2 / 4. Scarlet Begonias / 5. Fire on the Mountain`.
     - Tape: `…, Jack Straw, "Ripple > Scarlet Begonias", Fire on the Mountain`.
     - HEAD owns `('1','1','1','2','2')` and labels Ripple (taper set 1) as set 2.
     - 3d1c1e7 declined ("songs out of order").

     The merged item hides `Ripple` from the left side, so the "a merged track spans the boundary" check never fires. That is a moved break.
   - **It also makes the reader stricter where it used to be right.** With the songs on separate tracks, HEAD declines (`non-filler track 'Ripple' between the songs`), where 3d1c1e7 owned correctly.
   - **Exposure today.** None of the 648 owned library rows has a two-song merged boundary item; every owned comma item I checked is one real title (`Signs, High Times`, `Farewll, solong, Goodby`, `Elizabeth, You Were Born…`, `Kick To The Head, Burrito On The Floor`, which matches the tape tag). The hazard is latent, but nothing structural prevents it, and A2 recorded that there is no clean discriminator for this comma class.
   - **Fix, local to taper.py:** keep the merged title for matching, but also carry its comma parts.
     - In `_place_boundary`, add each kept-comma part to `left_norms`/`right_norms`, both for the "also occurs on the other side" check and for the merged-span check.
     - Simplest alternative: decline when a boundary song contains a kept comma and a part other than the first matches a different track, or the same track's component.
     - Add the constructed case above as a test.

2. **The amendment wording attributes non-ruled forms to the operator** (spec §1 and §2 inserts, plan Global Constraints, the `taper.py` module docstring). These are items (c)1–4 above: `...`, Disc/Disk/CD interchangeability including the original three forms, `Disc 1, Set 1` / `Set 1-Disk 1`, and (d)'s "label on any track after" reading. Every reviewer of this spec relies on "Operator ruling" meaning the operator said it.
   - **Fix:** move these into "(My call: …)" sentences, the convention the spec already uses, or get the operator to confirm them.
   - **For `...`:** either ask, or drop it from `_ANNOT`. Dropping it loses the ~20 `Set N cont...`/`Disc 1 - Set I...` headers, which only means the taper owns less.

**Minor**

1. **`Set I (Disc 1)` is excluded** (`test_taper.py` disc-and-set negatives, "not in the ruling's list"). It is in cpa-decl's N-FORM family, and the yield is 0. Either admit it, or record it as a narrowing the operator should confirm, and fix the test comment.
2. **The (d) index is only half pinned.** In a scratch copy, the mutant `today_sets[placed.boundaries[-1] + 1:]` survives all 265 tests in `test_taper.py`; `b-1` is caught. Add a case where today's encore is the single track right after the taper's last break (for example a taper whose last set is one song and today `[…, "encore"]` on that track).
3. **The single strip regresses double-numbered lines.** `02. 02 FRIEND OF THE DEVIL` (DSO2010-12-31, about 30 items) and `18. 18 WhartRat` (DSO2011-07-20) now keep a junk number. It only declines, and it is the price of the `44 Blues` fix. A refinement would strip a second number when it equals the first.
4. **The `_split_set_and_encore` shape test strips `_NUM_PREFIX` unconditionally, but `_scan` strips it only on enumerated text.** So `3 Set II & Encore:` on a non-enumerated text is held as a header, then classified as a song line: the junk item `3 Set II & Encore:` gets `encore_like`. It is safe-direction. Either strip `_NUM_PREFIX` the same way in both places, or note why they differ.
5. **Header-rest junk survives.** `set 1 - disc 1 - Bertha` gives the item `disc 1 - Bertha`: `_SET_HEADER`'s dash tail matches before `_SET_DISC_HEADER`, and `_DISC_LABEL` only drops a lone label. `CD#1: First set: 23 tracks 79:33` (cvb2003-02-28) gives a `tracks 79:33` item. Both only decline.
6. **`_ANNOT` accepts more than the ruling's examples:** a `~` range separator, `?` after a time, and an annotation inside and after a bracketed disc core. All are benign. Mention them in the "(My call)" note.

### Assessment
**Task quality:** Needs fixes.
**Reasoning:** The round closes the veto gap, removes every encore fold through ruling (d), adds no prose headers across the whole cache, and leaves `setlist.py` and the protected names alone. But the comma rule merges real two-song lines, and in a constructed case that defeats the merged-track guard and moves a break. The amendments also label several of the implementer's own extensions, `...` among them, as operator rulings. Both fixes are small and local.
