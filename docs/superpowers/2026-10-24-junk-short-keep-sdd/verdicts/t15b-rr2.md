### Finding Verdicts

- **1. (Important) `not included`/`not listed` miss two-word auxiliaries** — ADDRESSED. At replay.py:283-284 the slot is now `(?:\bnot|n['’]t|\bcannot)(?:\s+[\w'’-]+){0,3}?\s+(included|listed)\b`.
  - Probed against the shipped `_RESTORED_WORDING`. These all fire: "should not have been included", "has not yet been included", "would not have been listed", "has not yet been listed", "is not even listed".
  - The earlier forms still fire: "isn't included", "can't be listed", "cannot be included", "won't be listed", and a bare "not included"/"not listed".
  - Cases for each quoted form are at test_replay.py:1080-1084.
- **2. (Important, rr1 breakage) `not in the setlist` regressed the one-word "tracklisting"** — ADDRESSED. The noun at replay.py:286-287 is now `(?:set|track)[\s-]?list(?:ing)?s?\b`.
  - Probe hits: "not in the tracklisting", "not in this tracklisting", "not in the track-listing", "not in the tracklistings", "not on the set-lists", "not in the set listing", and "not in the tape's set list".
  - The new noun is a superset of the old alternation (`set[\s-]?lists?|track[\s-]?lists?|track\s+listings?`), so every earlier case is kept.
  - Cases are at test_replay.py:1085-1087.
- **3. (Minor) `no separate track`: "without its own track", "no separately-titled track"** — ADDRESSED. replay.py:289 is now `\b(?:no|without)\s+(?:[\w'’-]+\s+){0,3}?tracks?\b`.
  - Both named forms fire, and so does "without a separate track".
  - The new pattern is a superset of the old optional-modifier list.
  - Cases are at test_replay.py:1088-1089.
- **4. (Minor) `not tracked separately`: "as a separate song", "separately tracked", "individually"** — ADDRESSED. replay.py:292 is now `(?:\bnot|n['’]t)\s+(?:[\w'’-]+\s+){0,2}?tracked\b`.
  - All three named forms fire, as do "aren't tracked as separate tracks" and "hasn't been tracked separately". The pattern now fires on a bare "not tracked", which is broader and errs toward refusing.
  - Cases are at test_replay.py:1090-1092.
- **5. (Minor) the comment at replay.py:278-279 is stale** — ADDRESSED. replay.py:278-282 now describes a negation plus a bounded N-word window, plus a per-term comment at 285, 288 and 290-291. One residual imprecision is listed under New Breakage.

Checks run:
- `llama.__file__` resolves to the worktree. The probe ran from the scratch cwd with PYTHONDONTWRITEBYTECODE=1 and 37 phrasings. After the probe the tree is clean and HEAD is still d14e54c.
- RED count: by hand, all 13 new cases fail on the ea664f3 patterns, which matches the reported "13 failed". I did not run the suite. The report shows test_replay.py at 207 passed and the full suite at 5183 passed.
- Re-measure ~/.llama-harness/piece4/ckb/15b-r2:
  - `dump.jsonl` is byte-identical to 15a's and 15b-r1's, and `final_15b.py` differs from r1 only in its out dir.
  - `final.txt` differs from r1 only in four rows, each of which grew: no separate track 37/31->80/70, not included 16/13->23/19, not listed 14/13->26/23, not tracked separately 3/3->4/4.
  - Refused is 1014/1014 and 901/901, the first-hit distribution is unchanged, sole-hit is 0 for every widened term, and nothing is still reusable.
- The diff touches only replay.py and test_replay.py, and every term keeps its name and position.

### New Breakage in the Fix Diff

- Minor: replay.py:278-282. The new comment says "each class is closed by a negation ... followed by a BOUNDED window", and it sits above `does not appear` (replay.py:285, `(?:\bnot|n['’]t)\s+appear`) and `unlisted`. Neither of those is windowed, so a reader would wrongly take "does not even appear" as covered (see Out-of-Scope). Fix: scope the sentence to the terms that do carry a window, or window `does not appear` too.

### Out-of-Scope Observations

- Important under the stakes paragraph (no batch impact): the bounded-window treatment was not carried to the other negation terms, which were outside the findings and untouched by the diff.
  - Probed as firing nothing anywhere in `_RESTORED_WORDING`: "does not even appear", "doesn't actually appear" (`does not appear`, replay.py:285), "is not actually present" (`not present`, :268) and "is not even represented" (`not represented`, :271). These are the same adverb-interruption class finding 1 closed.
  - Also unmatched: the negation `never` ("was never included", "is never listed") and comma or parenthesis interruptions ("is not, however, listed", "not (yet) listed", "should not, in fact, have been included"), because `[\w'’-]+` stops at punctuation.
  - Corpus grep of the 15b-r2 dump: "never appeared" 3, "not yet appeared" 1, other "not X appear" 20. Every row is already refused by other terms, so the batch is unaffected.
  - Candidate for the final review: window `does not appear`, `not present` and `not represented` the same way, and add `never` to the negation alternation.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. The one new Minor is comment scope (replay.py:278-282). The out-of-scope Important-weight gap in the un-windowed negation terms needs a ledger entry for the final review.
