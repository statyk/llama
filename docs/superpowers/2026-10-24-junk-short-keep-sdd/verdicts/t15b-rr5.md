### Finding Verdicts

- **1. (R1) The `not included` and `not listed` heads take every inflection, guarded or in a new last term** — ADDRESSED.
  - `not included` is now `includ(?:e|es|ed|ing)\b` (replay.py:327).
  - The verb heads `list(?:s|ed|ing)?` went into the fallback term `not included or listed`, appended after `not found` (replay.py:348). This is the fallback the direction allows. `not listed` keeps `listed\b` (replay.py:328).
  - The deviation is justified. A bare `list` head in `not listed` would take the first hit from the existing cases at test_replay.py:1034 ("did not appear on the list") and test_replay.py:1037 ("is not appearing in the list"). Both belong to `does not appear`, and the set/track/song lookbehind does not cover "the list".
  - Probe: all three corpus sentences fire, as do "doesn't include it", "didn't list", "is not listing" and "never lists".
- **2. (R2) A bare `no` before a head, as a new last term named exactly `no … listed`** — ADDRESSED.
  - It is at replay.py:350, using U+2026 and the exact pattern from the direction.
  - Probe: "No encore is listed.", "No reprise is included." and "No intro appears." fire it. So do "no encore listed", "no encore found" and "There is no reprise listed in the data.".
- **3. (R3) Drop `-` from `_TOKEN`'s joiners; `set-list` and `track-list` still fire** — ADDRESSED.
  - `_TOKEN` is at replay.py:271.
  - Probe: these fire: "not separately-tracked", "not officially-listed", "a not-included reprise", "is not-listed", "the not-tracked jam", and "not on the set-list"/"not on the track-list" as `not in the setlist`.
  - The implementer deviated by also scanning a hyphen-joined copy (replay.py:272, 280). Judgment on that is below.
- **4. (R4) Fold `` ` ``, `´` and `ʼ` to `'` before tokenising** — ADDRESSED.
  - The fold is at replay.py:273 and 279. "isn`t", "isn´t", "isnʼt", plus `‘` and `′`, all fire `not listed`.
  - The fold has one side effect; see New Breakage N1.
- **5. (R5) "The drums are not tracking as a separate track." fires some term** — ADDRESSED.
  - The head is now `track(?:ed|ing)` (replay.py:338), and the sentence fires `not tracked separately`.
- **6. (R7) `not contain`** — ADDRESSED.
  - `contain(?:s|ed|ing)?` is in `not included or listed` (replay.py:348).
  - "this recording does not contain" and "never contained" both fire.
- **7. `left out`, `too short` and `implausibly short` also match the normalised text; names and positions kept** — ADDRESSED.
  - The changes are at replay.py:298-301. Names and order are unchanged; the diff only adds a third element.
  - "left — out" and "left (entirely) out" fire `left out`. "too—short" and "implausibly—short" also fire.

Requested checks:
- **Pre-existing first hits are kept.**
  - The test diff only adds lines; no existing expectation changed. The parametrized test asserts the exact reason string.
  - Focused GREEN on HEAD: `-k "absence_wording or neither_still_reuses or anywhere"` gave 150 passed.
  - RED replicated independently: `git archive cc37a3a` src, plus HEAD's tests, with PYTHONPATH shadowing (`llama.__file__` printed the scratch path). Result: 19 failed. These are exactly the 19 non-pin forms. The 2 hyphen-joined pins pass on cc37a3a.
- **Corpus.** `dump.jsonl` is byte-identical to 15a's, and `final_15b.py` differs from r4's only in its out dir.
  - Refused 1014/1014 and 901/901.
  - Compared row by row with r4: 0 rows lose a label, and exactly 1 changes its reason. stevekimockband-2004-08-21 goes from `absent` in cautions to `left out` in per_set ("leaves it out", via item 7's 2-word window; `left out` comes before `absent`). That shift is explained and correct.
- **Deviation: the hyphen is read both ways.** Accepted.
  - Each normalised pattern fires on either copy, so the result is a superset of both the hyphen-split and the hyphen-joined readings. On the hyphen axis it can only refuse more.
  - The two corpus pins ("no separate return-to-astronaut track", "not in the set-break data") show the joined copy is load-bearing.
  - The cost is two scans per pattern, measured below as negligible.
- **Deviation: the verb forms are in the new term `not included or listed`.** Accepted, as justified under item 1.
- **Timing probe** (scratchpad rr5/timing.py, results in the log).
  - It ran 9 adversarial generators at 200k, 400k and 800k characters, every pattern on both copies plus the raw text, with no short-circuit:
    - dense `no`, `no` with no head, chained `left`
    - `not list-contain`, long hyphen chains, a chain of apostrophe look-alikes
    - near-miss windows, nested `not found` heads, and a 20k-character word
  - Scaling is exactly linear on every input. The worst is 1.31 s per 800k characters for all terms, and 0.22 s for the slowest single pattern (`not a track`).
  - Normalising both copies takes at most 0.045 s.
  - There is no catastrophic-backtracking risk. `_SEP` and `_WORD` stay disjoint, and every window is bounded and lazy.

### New Breakage in the Fix Diff

- **N1 (a), Minor (strict surface, regression, corpus 0): the apostrophe fold glues a head word or a negation to a quote-like character that touches it with no space.**
  - The fold is at replay.py:273 and 279. `‘`, `` ` ``, `´` and `′` used to be separators; now they are folded into the joiner `'`.
  - "the reprise is not‘listed’", "not`listed`" and "not´listed" fired `not listed` at cc37a3a, and "not‘included" fired `not included`. At 9e35b0d they fire nothing. Measured in a scratch copy of cc37a3a against the live HEAD (log).
  - The same shape with `’` already failed at cc37a3a, so that part is pre-existing.
  - So the fold breaks the "strict superset of r4" claim in general, although it holds on the corpus. There is no glued `‘`, `` ` ``, `´`, `ʼ` or `′` between word characters in any of the 1,014 rows.
  - The case needs a typo'd glued quote, so it is Minor. One-line fix: fold only in the contraction slot, e.g. `re.sub(r"(?<=n)[`´ʼ‘′](?=t\b)", "'", text)` in place of the global translate. Or keep an unfolded reading as one more copy.

Nothing else. Every rewritten pattern is a superset of the one it replaced, apart from N1.

Residuals and the class judgment. Over its own vocabulary, the structural design (two punctuation-normalised copies, plus one bounded window before every head word) now closes the separator class: punctuation, the hyphen read both ways, and apostrophe look-alikes, apart from N1. It also closes the inflection class and the bare-`no` class. Every remaining residual is window overflow, a typo, or wording outside the vocabulary.

- **N1 (a), Minor.** Above. Corpus 0.
- **"too (very) short" (a), Minor.** The plain-word terms `too short` and `implausibly short` take no window on the normalised copies, though `left out` does. Corpus 0 for `too\W+\w+\W+short`.
- **Window overflow (b), inherent to a bounded window.** Example: "isn't – as far as we can tell – included".
  - Corpus upper bound: 374 spans in 182 rows put `_NEG`, then 6-8 words, then a head, with no in-window head.
  - Sampled spans are unrelated co-occurrences, not asides ("not name or add any songs beyond the 13 listed"; "not quite match the archive page the page lists").
- **The typo "isn' t" (b).** Corpus 0.
- **Verb, then `no` (b).** "The data lists no reprise", "the tape contains no reprise". The head comes before the negation, which is outside every term's shape.
  - Incidence: 506 spans in 363 rows overall, mostly "has no flags/reviews".
  - With a data subject (data/tape/recording/list/tracks), excluding "flags": 100 spans in 96 rows.
  - The clearest piece-absence claim is "the show data lists no encore" (billystrings-2017-08-29). Most others are "lists no set breaks" or "has no reviews".
- **`lack(s|ed|ing)` (b).** 57 spans in 50 rows; with a data subject, 6 in 6.
  - Real piece-absence claims:
    - "the page lists entries the track data lacks: a return to one rabbit race" (brotherspast-2006-11-17)
    - "segments the show data's track list lacks: a jam…" (joerussosalmostdead-2018-03-10)
    - "his tape lacks the intro" (belafleckandtheflecktones-1995-08-25)
    - "the taperjeff tape lacks" (thetravelinmccourys-2014-05-24)
  - These are the strongest (b) residual on the strict surface. A `lacks` plain-word term (about 50 rows, over-refusing on "lacking in top end") is the controller's call.
- **Other wording outside the vocabulary (b):**
  - "not available"/"unavailable": 6 rows, none a piece-absence claim.
  - "not recorded": 10 spans in 9 rows. Among them, "the first two songs of the night were not recorded" (hayescarll-2006-01-21 ×2, meatpuppets-1988-02-06, greenskybluegrass-2012-03-21) is about songs that are not on the tape.
  - "cut from": 5 rows, including "the show's first two songs were cut from the recording" (greenskybluegrass-2010-03-26).
  - "did not make": 3 rows, none a claim.
  - "nowhere to be", "gone from" and "nothing … survives": 0.
- In this batch, every row carrying a (b) residual is refused by some other term: 1014/1014, and no term except `absent` and `excluded` has a sole hit. In production, a briefing whose only absence wording is one of these would still be reused.

### Out-of-Scope Observations

- Over-matching keeps growing. `no … listed` hits 345 rows ("no, the encore is listed" also fires), `not included or listed` 315, `not included` 106 (was 27). Each costs one brief call per affected reuse, as the stakes accept. This is an observation, not a defect.

### Verdict

**Fix round:** All findings are addressed (1-7). The fix introduced no Critical or Important breakage.

- **New breakage:** one new Minor (a), N1, the apostrophe-fold glue regression. Corpus 0; the fix is one line.
- **Class:** closed over the gate's vocabulary.
- **Residuals for the controller:**
  - (a) Minor: N1 and "too (very) short", both corpus 0.
  - (b): window overflow; verb-then-`no` (1 clear claim); `lacks` (4 clear claims in 4 rows, the strongest residual); "not recorded"/"cut from" (about 5 claims about songs not on the tape); the "isn' t" typo.

Checks run, all logged in t15b-rr5.log:
- shadowing (`llama.__file__` in the worktree, and in scratch for the base)
- the RED replication on cc37a3a
- the focused GREEN
- 57 probe phrasings
- the cc37a3a glue probe
- the r4 against r5 row diff
- four corpus sweeps
- the timing probe

The live tree is untouched: HEAD is 9e35b0d and `git status` is clean.
