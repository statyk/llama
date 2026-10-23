### Spec Compliance
- ✅ Spec compliant. The default `read_numbered` now treats a line matching `taper._ENCORE_HEADER` or the lone-line `_ENCORE_ONLY_LINE` as an `encore` boundary (desc_list.py:183-196; the default is True on both `_header_kind` and `read_numbered`). `taper._ENCORE_HEADER` is only read: `git diff f062b85 dda31c7 -- taper.py` is empty. The probe's `alt_encore_restart` still means something: `admits_new` = admitted by the default reader but not by the narrow one (title_hygiene_probe.py:449-456). There are pinning tests with the three slugs (test_desc_list.py `test_r16_clarification_real_descriptions`). A grep of the diff for every protected name in Global Constraints finds nothing.
- ⚠️ Cannot verify from the diff: the RED run (2 failed) is the implementer's claim, and so is the full-suite count (4725 passed). I re-ran neither, per the rubric. The default flip makes RED plausible: under the old default, `Encore 2:` read as "non-contiguous at 1".

**Named risk 3 (the measurement ran the scratch source, and gate 0 holds): verified on disk.**
- I rebuilt `git archive 89fd787` and applied `git diff f062b85 dda31c7` to it (~/.llama-harness/piece3/scratch/t15b-rev/ref). `diff -rq` against the implementer's ~/.llama-harness/piece3/scratch/t15b/tree reports no differences, with `__pycache__`, `*.egg-info` and `.pytest_cache` excluded.
- Line 2 of t15b.log records `llama: /Users/shawn/.llama-harness/piece3/scratch/t15b/tree/packages/llama/src/llama/__init__.py`.
- Both sha256 values match the report: dump 2df10e2c…7a6, table 108cf2b8…2d4.
- I counted gate 0 in gate-r16/dump.jsonl myself: `gate0` True 3983/3983 and `gate0_as_is` True 3983/3983.
- Diffing the two gate tables gives exactly the three lines claimed: the header, R10 61→62, and non-contiguous 428→424.
- I also diffed the two dumps per show, field by field. Only these differ: `desc` (94 shows), `alt_encore_fold` (4), `alt_hygiene_all_entries` (3), `alt_check2_cleaned` (1) and `arms` (1, assemblyofdust-2004-12-31, with paths identical in every arm). That matches the report.
- R16 newly admits 4 shows, 3 of them count-matched (assemblyofdust, mogwai, railroadearth; maxcreek is not count-matched). I confirmed this independently by running default against narrow over the corpus descriptions with the scratch source, my probe's `llama.__file__` printing the scratch path.

**Named risk 2 (callers that relied on the old default):** `grep -rn "read_numbered|_header_kind|encore_header"` finds one production caller, desc_list.py:378 `read_numbered(desc)`. It now gets the broader grammar, which is what the clarification asks for. The other callers are test files (test_title_hygiene.py:439, test_lossless_titles.py:157,328), which read fixed descriptions and are covered by the claimed green suite, and the probe, which passes `encore_header=False` on purpose. No caller depends on the old narrow default.

**Named risk 1 (a song on the `Encore:` header line):** this is real, and no test pins it. I probed the worktree's `read_numbered`:
- `"1. A\n2. B\nEncore: Bertha\n1. C"`: the default admits it as `('A','B','C')`, blocks `(0,0,1)`, boundaries `('encore',)`, and `Bertha` is silently dropped. The narrow reader returns "non-contiguous at 1". So the clarification makes this restart admissible with the header-line song missing from the list.
- `Encore - Bertha` followed by `1. C` behaves the same way.
- With continuation numbering (`Encore: Bertha\n3. C`), both readers admit the list. The default only adds an `encore` boundary.
- `Encore: 1. Bertha\n2. C` is rejected by both readers.

Corpus impact, scanned over all 3983 gate descriptions:
- Admissions: no new admission comes through a song-bearing header. All 4 new admissions have a bare header (`Encore 1:`, `(encore)`) or a disc-label rest (`Encore: Disc 3:`, `Encore - Disc 4/...`).
- Relabels: 90 already-admitted lists are relabelled. In every one, the sequence of non-`encore` boundaries is unchanged (I counted 0 replaced), so `block_size_mismatch`, which folds `encore` blocks, sees the same blocks.
- One relabel is a wrong label. In blindmelon-2008-06-24, `Encore: Mouthful Of Cavaties, The Pusher` sits between a `1: Walk, I Wonder, …` summary blob and the `d01t01…` list, so the whole main list becomes an `encore` block. This is harmless today: 20 entries against 19 tracks, so it is not count-matched, and its arms are unchanged.

Harm would need a coincidental count match, for example a tape missing the song the header line names. See Minor 1.

### Strengths
- The change is small and well placed: one default flip, plus a kept `encore_header=False` that the probe uses for its baseline. The comment at desc_list.py:176-179 states both meanings.
- The probe's semantics were re-derived correctly. On a tree without the clarification `admits_new` reports False, and the new probe test pins `narrow == "admitted"` / `not admits_new` on the numbered fixture (test_title_hygiene_probe.py:208-210).
- test_desc_list.py:131-140 covers the clarification's named forms (`Encore 2:`, `Encore 1:`, `(encore)`, `Encore: Disc 3:`, `1st Encore:`) and pins the narrow baseline in both directions.
- The full real descriptions of the three pinned shows are admitted by the worktree reader. Entry counts and boundaries: aod 21, `('disc','disc','encore','encore')`; mogwai 15, `('encore',)`; rre 20, `('set','encore')`. These match the dump.
- The measurement discipline is clean: a scratch tree byte-identical to 89fd787 plus the diff, a shadow proof, and a before/after table diff that is fully accounted for.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **desc_list.py:191 / test_desc_list.py: header-line songs are dropped, and a restart after them is admitted, with no pin.**
   - What happens: `taper._ENCORE_HEADER` has a `rest` group that the taper treats as songs. Reader (i) discards that group and still licenses a restart, so `Encore: Bertha` then `1. C` yields an admitted list missing `Bertha`.
   - Why it is Minor: the measured population is zero new admissions, and count-matching plus Checkpoint B's hand-check of every R16 admission guard it. But the behaviour is unpinned and diverges from how the taper reads the same line.
   - Fix, either of:
     - Pin today's behaviour with a test, so the gap is a recorded decision.
     - Make a non-empty `rest` that is not a `taper._DISC_LABEL` / parenthetical license only continuation, not a restart. Re-check the 4 R16 shows: `Encore: Disc 3:` and `Encore - Disc 4/...` must stay admitted.

   The blindmelon-2008-06-24 mislabel (the main list labelled `encore`) is the same class. Worth a line for Checkpoint B.
2. **scripts/title_hygiene_probe.py:453: the `encore_header` key is redundant.** It now always equals `default`, and nothing in the probe reads it (the gate reads `admits_new` / `count_matched`). Kept "for compatibility", but with no reader it is dead data that test_title_hygiene_probe.py:457 has to fabricate. Drop it, or note that it is legacy.
3. **R16 heading wording in the gate table is stale.** The gate-r16 table still says "Lists inadmissible only because a numbering restart follows an `Encore` header". At this tree those lists are admitted by the default reader; the row now means "admitted by default, not by the narrow reader". A Checkpoint B reader could misread it. Reword the row text in the probe's gate renderer.
4. **test_desc_list.py:143-149: the aod excerpt is not verbatim, its comment is wrong, and the assertions are weak.**
   - The comment says "the 4a/4b lines omitted", but the 8a/8b lines are omitted too.
   - Omitting them was unnecessary: the full real description is admitted (21 entries), and the brief asks for a verbatim excerpt.
   - The assertions check only `raws[-1]` and the last two boundaries. A regression that dropped or merged entries before the encores would pass.
   - Fix: embed the verbatim text and assert the full `boundaries` and `len(raws)` (21 for aod; mogwai and rre likewise).
5. **desc_list.py:183:** `_header_kind` gained a default (`= True`), but its only caller (desc_list.py:213) always passes the argument. This is harmless, but it is a second place stating the default. Optional.

### Assessment
**Task quality:** Approved
**Reasoning:** The change does exactly what the clarification asks. The measurement is verified on disk: the scratch tree is byte-identical to 89fd787 plus the diff, `__file__` resolved to the scratch tree, gate 0 is 3983/3983 on both views, and the R16 result is 4 shows, 3 count-matched. Every remaining item is Minor. The most notable is that the unpinned case of a song on the `Encore:` header line is now admissible on a restart, but no admission in the corpus comes through it.
