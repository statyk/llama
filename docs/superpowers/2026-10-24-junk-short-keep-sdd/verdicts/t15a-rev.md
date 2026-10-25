### Spec Compliance

- ✅ Spec compliant against task-15a-brief.md, requirement by requirement:
  - **Req 1, the restored set.** replay.py:390-391: `restored = [t.filename for t in n.tracks if t.short_kept and t.filename not in stored_names]`.
    - With no restored file, `_restored_file_mention` returns None at replay.py:330, so the function returns exactly what it returned after Task 11. Pinned by `test_no_restored_file_is_todays_rule`.
    - A short file the stored show already kept does not count. Pinned by `test_an_already_kept_short_file_does_not_trigger_the_gate`.
  - **Req 2, the reason text and the fields.** The reason starts `briefing mentions a restored file` (replay.py:335).
    - Every text field is scanned, per_set keys included (replay.py:283-292).
    - The field list is pinned against `Briefing.model_fields` minus `narration` and `non_attendee_sentiment`. I checked it against models.py:245-258 and it matches.
    - Matching is case-insensitive because every text is lowercased at replay.py:292.
  - **Req 2a, names.** The basename, the stem (`junk.basename_without_extension`) and the disc/track tail are all matched (replay.py:295-309).
  - **Req 2b, wording.** The wording arm fires anywhere in the briefing (the conservative choice). It covers the minimum terms plus every "consider" term (replay.py:258-276).
  - **Req 3, the measurement.** It is present: `~/.llama-harness/piece4/ckb/15a/final.txt` matches the report's numbers (1,014 of 1,014 refused, 901 of 901, `still reusable: []`).
  - **Req 4, the tests.** Every listed case is there (test_replay.py, section "Task 15a"): cautions, shorthand, every term, neither (pin), already kept (pin), no restored file (pin), case.
  - **Req 5, suite and commit.**
    - The suite reads 5117 = 5076 + 41.
    - The 26 warnings are pre-existing: the baseline line `5076 passed, 1 skipped, 8 deselected, 26 warnings` appears in an earlier task's handback.
    - The commit message carries the test command and the trailer (`git log -1 --format=%B 49f9274`).
- ✅ **Global constraints.** The diff touches only replay.py and test_replay.py, and it names none of the byte-identical items. Its one import from junk is `basename_without_extension` (replay.py:24), which the spec names.
- ⚠️ **Cannot verify from the diff:**
  - The spec 5.3 text is not yet updated for this rule. The brief defers that to Task 23; the controller should check it there.
  - The implementer's concern 2 belongs to the Review Focus 2 / Task 1 owner, and the whole-branch review should check it. `gratefuldead-1970-06-07` short-keeps both `gd70-06-07d1t03.mp3` and `gd70-06-07d1t03_vbr.mp3`, both titled "My Dog Has No Nose", which looks like a duplicate listing that would air twice. It is outside this task, and I did not verify it.

### Strengths
- The rule is checked last, so every earlier reason is unchanged and still comes first (tested at test_replay.py, `test_no_restored_file_is_todays_rule`). The one caller, `compute_legs` (replay.py:479), needed no change.
- `BRIEFING_TEXT_FIELDS` has a two-sided pin: one side against the model, one against what `_briefing_texts` actually reads. A field added later cannot go unread.
- The mutants were predicted beforehand and run in a scratch copy. M1 drops the stored-filename filter and M2 drops a term. Each was caught by exactly the predicted test.
- The vocabulary was widened each time a hand-read let-through row turned out to carry a real false claim (TTB `left off`, GD 1970 `nine tracks`). The variants table (`variants.txt`) lets the operator see the cost of every lever.

### Checks I ran (read-only; output only in my scratchpad)

**Named risk 1: a held show keeps a stale briefing on disk, and a later `fix --overrule` ships it.** This path does not go through the gate.
- reapply.py:165-177 drops the brief artifacts when the show is held and `shipped_diff` is non-empty.
- `shipped_diff` (replay.py:203-213) reports every index whenever the track count changes, and a restored file always changes the track count.
- The other route is a `redo --from gather` / `fix` re-gather. It drops the brief artifacts through `drop_stage_artifacts` (workspace.py:103-112; pipeline.py:132-133).
- Verdict: covered.

**Named risk 2: a stored `briefing.md` ships text the gate never read.**
- reapply.py:161-164 re-renders `briefing.md` from the model on reuse and never copies the stored one.
- Verdict: covered.

**Named risk 3: the vocabulary misses absence wording the LLM actually uses.** The library uses absence phrasings the vocabulary lacks, sometimes about exactly these short files:
- `delmccouryband-2002-05-24`: "three short files … are not included in the track list";
- `bernieworrell…-1996-12-31`: "three short archive segments are not in the setlist";
- `antibalasmusic-2007-04-15`: "not listed in the show data";
- 150 rows say "does not appear".

Exposure today is still zero:
- The wording arm alone refuses all 396 rows of `held_reuse.json` that carry a non-null reason. These are the restored-file shows the 15a measurement did not cover, and I read their stored briefings read-only from `~/.llama/shows/`.
- Over all 3,654 library briefings, 45 pass the wording arm. Every one of the 45 has 0 `excluded_files`, so none can have a restored file.

The gap is therefore latent (see Minor 1).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The vocabulary misses measured LLM absence phrasings** (replay.py:258-276). Terms such as `not included`, `not listed`, `not in the setlist/track list`, `does not appear`, `unlisted` and `no (separate) track` appear in the corpus with exactly this meaning.
   - Today the briefings that use them are caught only by other terms that happen to fire (often `track count` or `implausibly short`).
   - That makes the operator lever the report offers, dropping `track count`, riskier than "5 rows, hand-read" suggests for any future population.
   - Exposure in the current library is zero (check 3).
   - Suggested fix: add these terms. They cost nothing measurable, because every restored-file row is already refused.
2. **Two shorthand forms do not match** (replay.py:305-307). The tail patterns miss "track 4 of disc 3" and stems with no `t` (`ph1997-11-22d1_01`, read as `d1_01`). The wording arm backstops both (0 rows fired arm (a) alone), so this is polish.
3. **`_restored_file_mention` scans the briefing as passed** (replay.py:392), while the guard scans `normalize_briefing(briefing)` (replay.py:385). The two are identical in `compute_legs` (`_read_briefing` normalises), and the raw form is a superset. Still, a one-line comment at the call would stop a later reader from "fixing" the asymmetry.

### Assessment

**Task quality:** Approved

**Reasoning:**
- The gate does what the ruling asks.
- It errs toward refusing reuse: it refuses every one of the 1,014 restored-file rows, and the wording arm alone refuses the 396 rows the task did not measure.
- Its earlier checks are untouched, its callers needed no change, and the paths I checked around it (held drop:brief, the briefing.md re-render, redo dropping the brief artifacts) leave no unchecked way to ship a stale briefing.
- The remaining vocabulary gap is latent and is Minor.
- Flag for the operator: in practice the ruling's "~98% regenerate" is 100% on today's library.
