### Finding Verdicts

- **1. Window the un-windowed negation terms (`does not appear`, `not present`, `not represented`, `not part of`, and `not a track` if it is a plain negation pattern)** — NOT ADDRESSED. The four named terms are fixed; `not a track` is not.
  - Fixed: replay.py:280, 283, 284 and 299 are now `{_NEG}{_window(3)}present`, `…represented`, `…part\s+of` and `{_NEG}{_window(5)}appear(?:s|ed|ing)?`.
  - Probed against the shipped `_RESTORED_WORDING`. All four required forms fire, and so does "is not really part of the data": "does not even appear", "doesn't actually appear", "is not actually present", "is not even represented".
  - Cases are at test_replay.py:1094-1098.
  - Still open: `not a track` (replay.py:285-286) is unchanged: `\bnot\s+(?:a\s+|as\s+(?:a\s+)?|its\s+own\s+)?(?:separate\s+|titled\s+|distinct\s+|individual\s+)?tracks?\b`.
    - That is a plain negation followed by a hard-coded list of optional modifiers, which is exactly the shape this round replaced.
    - The fix report's reason, "not plain negation", does not hold.
    - Probed as firing no term anywhere in `_RESTORED_WORDING`: "The drums are not even a separate track.", "The drums are never a separate track.", "The drums are not really a track."
    - These are false claims that a restored piece is absent, the strict surface: Important.
  - Fix: `("not a track", rf"{_NEG}{_window(3)}tracks?\b")`, which also takes `never`. It is a superset of today's pattern, so every existing case is kept. It over-matches things like "not among the playable tracks", which errs toward refusing.
- **2. Add `never` to the negation of every windowed term** — ADDRESSED.
  - `_NEG = (?:\bnot|\bnever|n['’]t|\bcannot)` is at replay.py:260. Every windowed term uses it (lines 280, 283, 284, 297-299, 302 and 306) except `no separate track`, which is `no|without` by design.
  - Probe hits: "was never included", "is never listed", "never appeared in the data", "has never been listed", "is never present", "is never in the setlist", "are never tracked".
  - Cases are at test_replay.py:1099-1103 and 1108.
- **3. Let the window cross a comma or parentheses** — ADDRESSED.
  - `_SEP = r"[\s,()]+"` is at replay.py:261, and `_window(n)` is `(?:{_SEP}{_WORD}){0,n}?{_SEP}`.
  - Probe hits: "is not, however, listed", "not (yet) listed", "should not, in fact, have been included", "is not, however, present", "not, as it happens, tracked separately", "no (separate) track".
  - Cases are at test_replay.py:1104-1110.
  - The window was widened to 5 words for included/listed/appear because "should not, in fact, have been included" needs 4. It is still bounded.
  - A residual in the same class is listed under New Breakage.
- **4. (Minor) Make the comment above the terms accurate for every term it covers** — ADDRESSED.
  - replay.py:290-296 now names the windowed terms, including `not present`, `not represented` and `not part of` above it.
  - It also lists the negation alternation and the separators, and says `unlisted` is a plain word.
  - The per-term comments above `not in the setlist`, `no separate track` and `not tracked separately` match their patterns.
  - It no longer claims a window for anything it does not window. It is silent on `not a track`, which is the open item under finding 1.

Checks run:
- **Shadowing.** The probes ran from a scratch cwd with the worktree's `.venv/bin/python -I` and PYTHONDONTWRITEBYTECODE=1. `llama.__file__` resolved to the worktree. Nothing in the tree was mutated: it is clean and HEAD is still 16003b7.
- **RED confirmed independently.** I loaded d14e54c's replay.py (via `git show`, into scratch) beside HEAD's and ran every one of the 17 new cases through both. On d14e54c, none of the 17 fires any term. On HEAD, each fires the term its test expects. That matches the report's "17 failed" and its GREEN count of 224 = 207 + 17. I did not run the suite.
- **Re-measure ~/.llama-harness/piece4/ckb/15b-r3.**
  - `dump.jsonl` is byte-identical to 15b-r2's, and `final_15b.py` differs only in its out dir.
  - Refused is 1014/1014 and 901/901, and nothing is still reusable.
  - The first-hit distribution line is unchanged from r2, as reported.
  - The per-term rows grew as reported: does not appear 157->190, not included 23->25, not listed 26->34, not part of 139->167, not present 199->213, not represented 8->9, no separate track 80->86.
  - One change the fix report does not list: the `excluded` sole-hit count went from 3 to 2. A row that only `excluded` refused is now also hit by a widened term, which is the refusing direction.
- **Catastrophic-backtracking timing probe.** All 23 patterns ran over ten ~200k-character adversarial inputs:
  - The inputs were: "not " repeated; "never" with separator runs; "n't" before a 200k-character word; "not a-a-a…"; "not" before a run of `’`; "no " repeated; chained negation-and-words; "not" plus 200k spaces; mixed "isn't (yet), (really)"; and a realistic sentence ×500.
  - The slowest single pattern took 0.029 s and the slowest whole input 0.19 s. Growth is linear, because `_SEP` `[\s,()]` and `_WORD` `[\w'’-]` are disjoint classes (each separator/word split is unique) and the window is bounded `{0,n}`.
  - No backtracking risk.
- **Scope.** The diff touches only replay.py and test_replay.py, junk.py is untouched, and every term keeps its name and position.

### New Breakage in the Fix Diff

Nothing the fix introduced breaks behaviour: every new pattern is a superset of the one it replaced. There are two residual gaps in the same class on the lines this diff rewrote:

- **Important (strict surface): `not in the setlist`, replay.py:302.** It is `{_NEG}{_SEP}(?:in|on){_window(3)}…list…`. The window sits only between in/on and the noun, not between the negation and the preposition, which is the same adverb-interruption class finding 1 closed.
  - Probed as firing no term: "The reprise is not actually in the setlist.", "The reprise is not even on the setlist."
  - The comment at 290-296 groups this term with the windowed ones.
  - Fix: `rf"{_NEG}{_window(2)}(?:in|on){_window(3)}(?:set|track)[\s-]?list(?:ing)?s?\b"`.
- **Important-weight under the stakes paragraph, measured absent from the corpus: `_SEP` stops at punctuation other than `,()`.** Each of these fires no term:
  - an em dash: "is not — strictly speaking — listed" (the ASCII "--" form does fire, via `-` in `_WORD`);
  - quotes: 'is not "officially" listed', "is not “officially” listed", 'is not officially "listed"', "is not ‘listed’";
  - brackets: "is not [yet] listed";
  - a semicolon: "not; listed".
  - Em dashes and curly quotes are common in LLM prose.
  - A corpus sweep of the 15b-r3 dump with a separator class widened to `"“”‘’—–[];:` found 32 extra matches, and none was an absence claim (e.g. 'not read the asterisks aloud as part of'). The batch is unaffected.
  - Fix: `_SEP = r"[\s,()\[\]\"“”‘—–;:]+"`. Keep `'` and `’` out of it, because they are in `_WORD`. Overlapping classes would make the split ambiguous and reintroduce backtracking. A closing `’` already ends a word as part of `_WORD`, so "‘listed’" needs only `‘` in `_SEP`, plus `\b` already ends "listed". Re-run the timing probe after the change.

### Out-of-Scope Observations

- Minor: "is no longer present" and "no longer included" fire nothing, since `no` is not in `_NEG`. These are low relevance, because a briefing stored before the restoration would not normally say "no longer".
- Vocabulary, for the operator rather than this loop: these paraphrases fire no term: "does not show up", "isn't on the tape", "cannot be found", "is nowhere in the data", "has no place in the listing".

### Verdict

**Fix round:** Findings remain open.
- Finding 1, for its `not a track` part: "not even a separate track", "never a separate track" and "not really a track" fire no term. Important on the strict surface; the one-line fix is above.
- Findings 2, 3 and 4 are ADDRESSED.
- No new breakage. Two residual gaps in the same class sit on the touched lines: the `not in the setlist` negation-to-preposition window (Important), and `_SEP` punctuation beyond `,()` (Important-weight, 0 corpus instances).
