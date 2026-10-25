# tfw1-rev: review of FW1 (a693878..bcfeef4), I-1 format choice + I-2 one derivative per original

### Spec Compliance

- ❌ Issues found. Every brief requirement has its hunk, and the legacy path is verbatim. But the I-2 copy choice is wrong where the two copies sit at different play positions (Critical C-1 below), and the copy choice ignores the operator's excludes (Important I-1 below). Requirement by requirement:
  - I-1, running-time choice with ties to preference order and the fallback unchanged: ✅ `junk.py:453-485` (`secs > best[0]` at :480 is strict, so an earlier format wins a tie; the fallback is the first format with audio, :476-477/:484-485).
  - I-2 as a new named step, `duplicate derivative` defined once, the preference in one named place: ✅ `junk.py:396-450` (`DUPLICATE_DERIVATIVE_REASON`, `PREFER_VBR_DERIVATIVE` :403, `_derivative_preference` :406, `_dedupe_derivatives` :414).
  - A file with no `original` is never grouped: ✅ `junk.py:431` (`source == "derivative" and original`).
  - `_dedupe_duplicate_listings` byte-identical: ✅ the diff touches it only in context lines.
  - Step placement (after both dedupes, before readmit): ✅. A dropped copy sits in `excluded`, so `readmit` returns it (diff readmit block). Pinned by `test_include_re_admits_a_dropped_duplicate`.
  - `ordering["short_kept"]` never names a dropped copy: ✅. It is `kept ∩ short_kept` (diff, after readmit). A dropped copy is in `kept` only once the operator re-admits it, and then it is no longer dropped.
  - `short_keep=False` byte-identical to v2.17.0: ✅. The `else` arm in `filter_files` is a693878's removed lines verbatim (I compared them line by line), with only `deriv_dropped = []` added. So `order_nums == nums` there. The `_apply_short_rule` hunk is comment-only. The two new pins compare against `fixtures/junk_v2_17_0.py`, and `test_short_keep_false_reproduces_today` now covers three more fixtures.
  - Tests and fixtures from real cache captures (tsp, sci, jrad), with no `~/.llama` path: ✅.
- ⚠️ Cannot verify from the diff:
  - Title and structure effects on the 23 changed shows were not measured. M2 measured kept lists only. On a de-doubled show the delivered kept set can now form the filename-stem bijection that `sibling_format_titles` needs, which `X_vbr.mp3` with no flac partner used to block. So sibling-format recovery and slice-3 C can start firing (`gather.py:405-420`, `lossless_titles.py:115-127`). The same applies to sibling-align and correspondence over de-doubled sibling recordings (`correspondence.py:305`). The re-taken cand/arms replay should be read for these shows before the bulk apply.
  - Brief gap for the controller: this review prompt carries stale text from another task's template ("Spec: section 4.3 `--snapshot`…" and Review Focus items 1-6: Tasks 1/3/4/12/13). I judged against `fw1-brief.md` only.

### Strengths

- The legacy path really is untouched. Splitting `filter_files` on `short_keep`, rather than threading flags through a shared loop, makes "v2.17.0 byte-identical" visible from the diff alone.
- Play order is preserved by construction, not just as measured. `order_nums` (`junk.py:608`) counts every dropped, non-re-admitted copy. A dropped copy shares its winner's `original` and therefore its tag (`_track_number` :84-89). So the order-source decision equals the decision with no step at all. In both branches (`sorted` is stable, and filename order is input order) the new `kept` is a subsequence of a693878's order.
- The jrad finding (the first cut reordered a real show) was caught by measuring and is pinned by a test. That test's guard (the tags DO reorder once the stale copy is gone) proves the test is not vacuous.
- I-1 measures running time after both dedupes, so a format listed twice cannot win on doubled time. Its docstring explains why.
- The measurements are careful:
  - The old arm is loaded from a saved a693878 `junk.py`, and the interpreter location is asserted (`common.py`).
  - M2's "originals left with no copy" check is the right check for the last-copy hazard, and it reads 0.
  - The cache-wide duration check confirms the default is safe. I re-ran it (below): of 1,970 drops, 48 differ by more than 2 s from the kept copy, and the kept copy is never the shorter one.

### Issues

#### Critical (Must Fix)

**C-1. `junk.py:406-411`, `_derivative_preference`: in non-`_vbr` groups, name order can keep the stale, misplaced copy and drop the one at the song's real position. A song then airs only at the wrong place.**
- **Latent today:** no library show is affected (M2: 0). But both items below are candidate recordings in `~/.llama/shows/gratefuldead-1984-04-13/provenance.json` and `…/gratefuldead-1985-07-01/provenance.json`. They ship this way if one is ever selected, for example after a re-select or `get`.
- I rate it Critical because the brief makes wrong play order on air a strict surface.
- **The pattern:** in all 23 non-`_vbr` groups (`m1b_group_shapes.json`), exactly one copy's `basename_without_extension` equals its `original`'s. Name order picks that copy in 12 and the stale copy in 11.
- **Checked, read-only, with the FW1 vs a693878 filter on the cached items (`order.py` in my scratchpad):**
  - `gd1984-04-13.132772.Sennheiser-holbrook.flac24`:
    - FW1 drops `…d2t01.mp3` (Scarlet > Fire, set 2's opener) and keeps the stale `gd1984-04-13(24Bit48khz)d2t01.mp3`, which sorts to **track 1, before set 1**.
    - FW1 drops `…d2t11.mp3` "U.S. Blues" (the encore) and keeps the stale `…d1t11.mp3`, which plays at **the end of set 1** under the residue title `gd1984-04-13(24Bit48khz)d1t11`.
    - At a693878 each song played at both positions. Now each plays only at the wrong one.
  - `gd1985-07-01.176684.senn.nd41.strizak.flac2448`: FW1 drops `s2t12 Baby Blue` (the encore, last) and keeps `s2t012 Baby Blue`, which plays as **set 2's second track**.
- Mp3 is the production format, so this sits on the live path.
- **Why the preference misses it:** the "drop-only" ordering is right for `_vbr` pairs, which are adjacent by name. Here the two copies sit at different positions, and the preference decides which position survives.
- **Fix:** add a component to the key, `(vbr != PREFER_VBR_DERIVATIVE, basename_without_extension(f["name"]) != basename_without_extension(f["original"]), f["name"])`. It chooses the copy named after its original in 23/23 groups. It changes nothing for plain/`_vbr` pairs, and the `_vbr` flip stays one line because the vbr component ranks first. Pin it with a test on the gd1984 shape: both stale pairs; Scarlet must not be track 1, and U.S. Blues must be last.

#### Important (Should Fix)

**I-1. `junk.py:398-403` (the preference comment) and `junk.py:414-438` (`_dedupe_derivatives`): the copy choice ignores `overrides.exclude`, so an operator exclude of the winning copy silently removes the song.**
- **Mechanism:** `final_kept` applies the exclude after the filter (`gather.py:1063-1074`). If the exclude names the copy the dedupe kept, the other copy is already gone.
- **Checked in memory from a scratch cwd (`flip.py`, no file edited):**
  - `_doubled()` with `Overrides(exclude=["x1t03.mp3"])` ships 6 tracks with no x1t03. At a693878 its `_vbr` played.
  - The sci fixture with its own SCI_EXCLUDE/SCI_INCLUDE ships **25 tracks** at `PREFER_VBR_DERIVATIVE = False` and **10** at `True`: 20 more songs gone, with no hold or message beyond the "matched no file" warnings.
- So the comment's claim "Set True to keep the `_vbr` copy instead; nothing else needs to change" is false. Five library shows hold `_vbr` excludes (sci, jrad, ttb2022, gd1970-05-06, gd1985-11-10, per the implementer's concern 4). Following the comment as written would drop songs on air.
- The default is measured safe: M2 shows 0 originals left with no copy, so nothing ships wrong today. This is a hazard behind the one-line change the ruling says Shawn may make.
- **Fix, preferred:** pass the operator's exclude set into the filter. `final_kept` gives `frozenset(overrides.exclude)` and other callers give nothing. `_dedupe_derivatives` then never drops a copy in a group whose other copy the operator excluded, or more simply leaves operator-excluded copies out of grouping, so the exclude drops them later as `operator-excluded`. That fixes the flip hazard and the plain-exclude case, and removes concern 4's "matched no file" noise.
- **Fix, minimum:** correct the comment to say a flip needs those overrides cleared or re-pointed first. Add a loud check in `final_kept`: warn, or hold, when an exclude removes the last copy of an original whose other copy was `duplicate derivative`-dropped.

#### Minor (Nice to Have)

- **M-1.** `m1_cache_format_scan.py` flags `same_set_reordered` only when nothing was dropped or added, so it cannot see a reorder alongside drops. The M1 claim "0 reorders" for the 111 mp3 items therefore rests on construction, not on that scan. The construction holds (see Strengths), so this is a wording issue in the report only.
- **M-2.** `test_the_preference_is_the_plain_copy` pins `PREFER_VBR_DERIVATIVE is False`. A flip must also edit this test and the pair tests. That is acceptable as a tripwire, but it is not a "one-line change".
- **M-3.** A preference by name alone can keep a truncated copy over a whole one. This is measured not to happen at the default (48 mismatched pairs, kept never shorter). It would happen in all 48 if the preference were flipped (the implementer's concern 2, confirmed cache-wide). If Shawn flips it, the same change should add a duration tie-break, or a refusal when the copies differ by more than a tolerance.

### Implementer concerns, judged

1. **31 flac flips:** accepted. All flips move to more tracks and more runtime. Production is mp3 with a single format, so there is no effect. Never-union is unchanged.
2. **Truncated `_vbr` if flipped:** confirmed cache-wide (48 pairs). See M-3 and I-1.
3. **23 non-`_vbr` groups fall to name order:** this is a defect, not a judgement call. See C-1. Name order keeps the copy NOT named after its original in 11 of 23, and in two items that moves a song's only airing to the wrong position. "Durations agree" was the wrong test: the copies are the same audio, and what differs is their position.
4. **Operator `_vbr` excludes match nothing:** harmless at the default. But the same entries are what make the flip destructive (I-1).
5. **2 re-selections orphan overrides:** this fails loudly, not silently. The `set_breaks`/`encore_after` on gd1985-11-10 would hit the dangling refusal at gather. Excludes only warn. The operator's call for the bulk apply.
6. **Docs:** agreed. CLAUDE.md's "first format whose kept set is non-empty" and the plan's Global Constraint need Task 23 updates.
7. **The slim fixture drops `track`:** agreed. The jrad test carries the tags explicitly.

### Checks run (read-only; scratch cwd; worktree interpreter, `llama.__file__` printed inside the worktree)

- `pairdur.py`: cache-wide, the kept copy against each dropped copy for every `duplicate derivative` drop. 111 items, 1,970 drops, 48 differ by more than 2 s, and the kept copy is shorter in 0.
- `stale.py`: for each of the 23 non-`_vbr` groups, whether the kept or the dropped copy is named after its `original`. Kept 12, dropped 11; exactly one copy matches in every group.
- `order.py`: the play order of gd1984-04-13 Sennheiser-holbrook and gd1985-07-01.176684 under a693878 and FW1 (C-1).
- `flip.py`: an in-memory patch of `PREFER_VBR_DERIVATIVE` on the sci fixture, plus a plain-copy exclude on `_doubled()` (I-1).
- No test suite run. No file in the live tree was touched. The scripts are under `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-junk-filter/7126b474-f234-4170-a8db-fad15e5c02e0/scratchpad/rev/`.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** I-1 and the legacy byte-identity are right, and so is the I-2 placement. The drop-only ordering is sound for adjacent `_vbr` pairs. But the copy choice keeps a misplaced stale copy in 11 of 23 non-`_vbr` groups, which moves a song's only airing to the wrong slot in two cached GD candidates. It also ignores operator excludes, so the advertised one-line flip silently drops 20 songs from the sci show. Both are small fixes inside `_derivative_preference` / `_dedupe_derivatives` plus pins.
