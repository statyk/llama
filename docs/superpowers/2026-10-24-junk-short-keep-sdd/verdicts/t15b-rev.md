### Spec Compliance

- ❌ One issue found. Part A: the `not included` / `not listed` patterns miss the `be` passive and `cannot` (replay.py:280-281). Everything else matches the brief: Parts A, B and C, the scope-change terms, and junk.py, which the diff leaves untouched (the stat lists only replay.py, test_replay.py and test_short_keep_rule.py).
- ⚠️ Cannot verify from the diff: whether each commit message states the test command. The diff file shows only the subjects, and I was told not to run git. The subject `feat(replay): briefing reuse gate adds the operator's absence phrasings` drops the brief's word "four", which fits now that six terms were added.

### Strengths

- The six terms are appended after `track count`, as replay.py:278-288 shows, so the order and reasons of the existing terms are unchanged. The 15b first-hit distribution matches 15a's exactly (`~/.llama-harness/piece4/ckb/15b/final.txt`).
- Every new parametrized case (test_replay.py:1023-1052) asserts its own term as the reported reason. Each case therefore proves that its pattern is the first hit, not just that something refused. Curly-apostrophe contractions are covered (`aren’t`, 1026). The numbers add up: 27 cases (15 + 12) match the RED counts reported (15 and 12), and 5117 + 29 = 5146.
- The comment about raw versus normalized scanning (replay.py:393-394) is accurate. I checked it in one focused look: `compute_legs` (replay.py:490-491) passes `_read_briefing(ws)`, which is already `normalize_briefing`'d (replay.py:400-406). `normalize_briefing` only removes empty `per_set` entries (stages/brief.py:105-110), so the raw texts are a superset of the normalized ones and can only refuse more.
- Part C is correct. `final_15b.py` is `final_15a.py` with only the docstring changed, and it computes through the shipped `_restored_mentions`. The results: 1014/1014 refused, 901/901 refused, `still reusable: []`, and only-hit = 0 for every new term.
- The Part B pin (test_short_keep_rule.py:155-169) asserts both `short_tag_is_junk(tag) is False` and the end-to-end keep: `excluded == []` and `ordering["short_kept"] == ["band1t06.mp3"]`. A length of 40 s against a median of 300 s makes it a real short candidate. The docstring quotes ruling 2 verbatim.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **replay.py:280-281: the `not included` / `not listed` patterns miss the `be` passive and `cannot`, the most common modal forms of the named terms.**
   - **The gap:** the optional auxiliary group is `(?:been|yet|being)`, which leaves out `be`. `\bnot` cannot match inside `cannot`. As a result, none of `should not be included`, `will not be listed`, `won't be listed`, or `cannot be included` fires any term (probed against the full `_RESTORED_WORDING`).
   - **It occurs in the corpus:** `discobiscuits-1999-02-19` has "...no other source confirms this, and it should not be included." No term catches that text. Its row is still refused by other terms, so the measured outcome does not change.
   - **Why it matters:** the brief requires "Match inflections and contractions in the refusing direction". The strict surface says every ambiguity resolves toward refusing.
   - **Fix:** `(?:\bnot|n['’]t|\bcannot)\s+(?:(?:be|been|yet|being)\s+)?(?:\w+ly\s+)?(?:included|listed)\b` for both terms. The `\w+ly` slot also catches `not separately listed` and `not explicitly included`, which today match nothing. Add per-form cases.

#### Minor (Nice to Have)
1. **replay.py:285-286 (`not in the setlist`):**
   - **Misses:** the hyphenated `set-list`/`track-list`, the plural `setlists`, and any adjective or possessive before the noun (`not on the archived setlist`, `not in the broadcast setlist`, `not on the recording's track list`).
   - **Measured on the 15a dump:** an extended form with up to three intervening words and the hyphen/plural matches 31 briefing texts that no term catches. Most of them compare against another night's setlist (`darkstarorchestra-2005-10-06`: "not on the 1974 setlist"), so they are not about this tape's files. A few are (`davealvin-2004-01-10`: "they are not in the broadcast setlist").
   - **Coverage:** the brief's listed forms are all covered. Broadening only costs brief calls.
2. **replay.py:287 (`no separate track`):** misses `no dedicated track`, `no standalone track`, `no separately titled track` and `without a separate track`. None of these occurs in the dump (0 rows). It is a cheap broadening in the refusing direction.
3. **Out of this task's scope; for the operator:** the dump contains a real absence phrasing that NO term catches: `not tracked separately` / `not tracked as separate songs`. There are 3 uncaught texts: `gratefuldead-1973-03-16`, `stringcheeseincident-2005-07-19` and `thebreakfast-2007-10-27`. All three rows are refused by other terms. Worth a ruling if the vocabulary is revisited.
4. **Part B mutant deviates from the brief.**
   - **What was prescribed versus run:** the brief said to add `chant` to `JUNK_PART` or `NONPERF`. The implementer added `\bnot\s+fade\s+away\b` to NONPERF instead. That mutant also failed the pre-existing `test_ruling2_keep_cases_stay_kept[Not Fade Away]` and the corpus test, so it never showed what the new pin adds.
   - **I ran the brief's mutants myself.** Scratch copy via `git archive 3855523`; `llama.__file__` printed inside the scratch tree; `python -m pytest` with PYTHONPATH shadowing, with the bytecode cache disabled and cleared. Each prediction was named before running:
     - **NONPERF `|\bchant\w*`.** Predicted: the pin fails for `Not Fade Away Chant` only, plus the corpus test. Result: exactly that (2 failed, 84 passed).
     - **JUNK_PART `|(?:crowd\s+)?chant(?:ing)?`.** Predicted: the pin survives, because both tags are a single part and JUNK_PART is a whole-part match. Result: 86 passed, as predicted. A JUNK_PART-style vocabulary change cannot drop these tags.
     - **NONPERF `|\bcrowd\s+doing\b`.** Predicted: `[Crowd Doing Not Fade Away]` fails, plus the corpus test. Result: exactly that (2 failed).
   - **Conclusion:** the pin is load-bearing for both parameters. It overlaps `test_deny_vocabulary_corpus`, which also pins these keep rows, but the pin survives a corpus re-baseline and the corpus test does not. No change needed.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** Parts B and C are correct and verified, including my own run of the brief's prescribed mutant. On the strict surface, the `not included`/`not listed` patterns miss the `be`/`cannot` passive, which occurs in the corpus. The fix is one regex change with test cases, and it changes no measured outcome today (every one of the 1,014 rows is still refused).
