### Finding Verdicts

- **1. (Important) `not included`/`not listed` miss the be-passive and `cannot`**: NOT ADDRESSED (partial). replay.py:280-281 now catches every form the finding names ("should not be included", "will not be listed", "won't be listed", "cannot be included", plus "not separately listed"/"not explicitly included"). Each has a case at test_replay.py:1051-1058. But the auxiliary slot `(?:(?:be|been|yet|being)\s+)?` still takes ONE word, so any two-word passive still fires nothing, and these are the be-passive the finding is about. Measured end to end through `briefing_reusable` with the test module's `_restored_pair`/`_with_caution`: "The reprise should not have been included." -> `None` (reusable), and "The reprise has not yet been listed." -> `None`. The same miss covers "would not have been listed", "has not yet been included" and "is not even listed". This is the strict surface, so the residual is Important. Corpus incidence is 0 (grep over the 1,014-row dump), so the batch is unaffected. Suggested fix: `(?:(?:have|be|been|yet|being|even|ever)\s+){0,3}` in place of the single optional slot, with a case per form.
- **2. (Minor) `not in the setlist` variants (hyphen, plural, up to 3 intervening words)**: ADDRESSED for the named forms. replay.py:285-286 has `(?:[\w'’-]+\s+){0,3}?` and `set[\s-]?lists?|track[\s-]?lists?`. Cases are at test_replay.py:1060-1066. The rewrite also introduced a regression, listed under New Breakage.
- **3. (Minor) `no separate track` variants (dedicated, standalone, separately titled, without a separate track)**: ADDRESSED. replay.py:287-288; cases at test_replay.py:1068-1072. Minor residual, not blocking: "without its own track" fires nothing, because `its` is not admitted after `without`. "no separately-titled track" (hyphenated) also fires nothing. Both were measured via the regex probe; corpus incidence is 0.
- **4. (Minor) new term `not tracked separately`, appended last**: ADDRESSED. replay.py:289-291 is appended after `no separate track` and named exactly `not tracked separately`; cases at test_replay.py:1074-1077. The named forms ("not tracked separately", "not tracked as separate songs/tracks") refuse. Minor residual: the singular "not tracked as a separate song", the word order "not separately tracked" and "not tracked individually" all still fire nothing, measured through `briefing_reusable`. In the corpus, the 7 "separately tracked" hits are all presence claims, not absences.

Checks run:
- `llama.__file__` resolves to the worktree (packages/llama/src/llama/__init__.py).
- Regex probe of 28 phrasings over the shipped `_RESTORED_WORDING`, plus 6 end-to-end `briefing_reusable` calls. These ran from the scratch cwd with PYTHONDONTWRITEBYTECODE=1, and the working tree is still clean at ea664f3.
- Diffed the re-measure: 15b vs 15b-r1 `final.txt` differ only in the `not in the setlist` (51->92 / 44->83) and `not included` (15->16 / 12->13) rows and the new `not tracked separately` row (3/3). The first-hit distribution is unchanged, refused is 1014/1014 and 901/901, sole-hit is 0 for every new or extended term, the dump is byte-identical to 15a's, and the script differs only in its out dir.
- The diff touches only replay.py and test_replay.py. junk.py is untouched, existing terms keep their order and reasons, and the 24 new cases match the claimed RED count.

### New Breakage in the Fix Diff

- **Important: replay.py:285-286 narrows `not in the setlist`.** The old pattern `track\s?list(?:ing)?` matched the one-word "tracklisting". The new alternatives `track[\s-]?lists?` (the `\b` fails after "tracklist" before "ing") and `track\s+listings?` (which needs whitespace) do not.
  - Measured: the old regex matches "not in the tracklisting" and "not in this tracklisting"; the new one matches neither.
  - End to end: "The reprise is not in the tracklisting." -> `briefing_reusable(...) is None`, so the briefing is reused. At 3855523 this sentence refused.
  - "track-listing" and "tracklistings" are missed too (the old pattern missed them as well).
  - No test pins the one-word form. The existing case at test_replay.py:1046 is "this track listing", two words, so the suite stays green over the regression.
  - Corpus incidence is 0.
  - Fix: `track[\s-]?list(?:ing)?s?`, plus cases for "tracklisting" and "track-listing".
- Minor: the comment at replay.py:278-279 ("the four measured phrasings, with not/n't, perfect and progressive inflections") no longer describes the terms, which now also take `cannot`, the be-passive and adverbs.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** Findings remain open.
- Finding 1 is still open: two-word passive auxiliaries ("should not have been included", "has not yet been listed") remain reusable.
- New Important breakage: the one-word "tracklisting" regression at replay.py:285-286.
- Minor residuals on findings 3 and 4 ("without its own track", "not tracked as a separate song", "not separately tracked") are non-blocking. They are worth folding into the same fix, since every one resolves toward refusing.
- None of these has corpus incidence: the re-measured batch still refuses 1014/1014.
