# t15b-fix4 handback: DONE

Commit `cc37a3a` on held-backlog-junk-filter, parent 16003b7: `fix(replay): absence phrasings match a punctuation-normalised text with one bounded window`. Files changed: `packages/llama/src/llama/replay.py` and `packages/llama/tests/test_replay.py`. junk.py is untouched. Full log: `t15b-fix4.log` in this directory.

## Design

- **Normalised text.** `_normalised(text)` is `" ".join(_TOKEN.findall(text))`, with `_TOKEN = \w+(?:['’-]\w+)*`.
  - A word is a run of word characters joined by single interior apostrophes or hyphens (`isn't`, `aren’t`, `set-list`).
  - Everything else is a separator: em/en dash, `--`, straight and curly quotes, brackets, braces, `;:,()/…`, newlines and tabs.
  - Quotes at the edge of a word drop out without any special-casing.
- **Window.** `_SEP = " "` and `_WORD = [^ ]+` are disjoint, so a window splits one way only.
  - `_window(n, word=_WORD)` is `(?: word){0,n}? `.
  - Its optional `word` argument lets `not a track` exclude some words from its window.
- **Which text each term reads.** `_RESTORED_WORDING` entries are now `(term, compiled, normalised)`.
  - `_restored_mentions` matches the 11 negation terms against the normalised text.
  - Every other term, including `track count` (which needs `tracks 3–5`) and the plain-word terms, matches the raw lowercased text as before.
  - Term names and order are unchanged, and `not found` is appended last.
  - The `final_15b.py` script calls only `_restored_mentions`, `_briefing_texts` and `_name_patterns`; their interfaces are unchanged.
- **Negation.** `_NEG = (?:\bnot|\bnever|n['’]t|\bcannot|\bno longer|\bnowhere|\bneither|\bnor)`.
  - The direction asked for `no longer` and `nowhere`.
  - I also added `neither` and `nor`. The probe found "Neither reprise is listed." fired no term. Adding them only refuses more, and no existing case contains either word.
- **A window before every head word.**
  - `not part of` became `part{window(3)}of`.
  - `not in the setlist` became `{NEG}{window(3)}(?:in|on){window(3)}<list noun>`, which fires on "is not actually in the setlist" and "is not even on the setlist".
- **`not a track`.** The rr3 suggestion, `{NEG}{window(3)}tracks?`, would have broken existing first hits: "not in the track list" and "not on the recording's track list" would have been named `not a track` instead of `not in the setlist`, and "aren't tracked as separate tracks" would have been named `not a track` instead of `not tracked separately`. So it has two alternatives:
  1. `{NEG}{window(5) of words not starting with "track"}tracks?\b(?![ -]?list(?:ing)?s?\b)`.
  2. The same window with `in`/`on` also excluded, then `tracks?[ -]?list(?:ing)?s?`. This keeps the 16003b7 coverage of "not a track list entry", pinned as a test case.
  - Every phrase it now declines fires a later term, so the exclusions only decide which reason is named. It is a superset of the old pattern.
  - The window is 5 rather than 3 because "is not, in fact, a separate track" and "isn't, strictly speaking, its own track" need 4 words.
- **`not found`, the new last term.** The direction named `on the (tape|recording)`. I generalised that to in/on plus up to 2 words plus a noun from the set tape, recording, data, listing, list or file, any plural. "isn't in the data" was a real absence claim that fired nothing before, and appears 25 times in the corpus.
  - My first draft also took `from` and the nouns `archive` and `source`. I dropped them, because the corpus showed they hit instructions ("not from a source", 22 rows) rather than absence claims.
- **Is the normalised match a superset of the old raw match?** I believe so, apart from absurd tokens like `x'-'y` or `a--b`: the old pattern read each as one word and the new one reads two, so a window can need one more word.

## Patterns verbatim (replay.py)

```python
_NEG = r"(?:\bnot|\bnever|n['’]t|\bcannot|\bno longer|\bnowhere|\bneither|\bnor)"
_SEP = " "
_WORD = r"[^ ]+"
_TOKEN = re.compile(r"\w+(?:['’-]\w+)*")
def _normalised(text): return " ".join(_TOKEN.findall(text))
def _window(n, word=_WORD): return rf"(?:{_SEP}{word}){{0,{n}}}?{_SEP}"

("not present", rf"{_NEG}{_window(3)}present\b", True),
("not represented", rf"{_NEG}{_window(3)}represented\b", True),
("not part of", rf"{_NEG}{_window(3)}part{_window(3)}of\b", True),
("not a track", rf"{_NEG}{_window(5, r'(?!track)[^ ]+')}tracks?\b(?![ -]?list(?:ing)?s?\b)"
                rf"|{_NEG}{_window(5, r'(?!track|(?:in|on) )[^ ]+')}tracks?[ -]?list(?:ing)?s?\b", True),
("not included", rf"{_NEG}{_window(5)}included\b", True),
("not listed", rf"{_NEG}{_window(5)}listed\b", True),
("does not appear", rf"{_NEG}{_window(5)}appear(?:s|ed|ing)?\b", True),
("not in the setlist", rf"{_NEG}{_window(3)}(?:in|on){_window(3)}(?:set|track)[ -]?list(?:ing)?s?\b", True),
("no separate track", rf"\b(?:no|without){_window(3)}tracks?\b", True),
("not tracked separately", rf"{_NEG}{_window(3)}tracked\b", True),
("not found", rf"{_NEG}{_window(3)}(?:show(?:s|ed|n|ing)?{_window(2)}up|found"
              rf"|(?:in|on){_window(2)}(?:tape|recording|data|listing|list|file)s?)\b"
              rf"|(?:{_NEG}|\bno){_window(3)}place\b", True),
```

The raw-text terms are unchanged (excluded, implausibly short, too short, left out, omitted, absent, missing, dropped, track count, unlisted). They now carry the flag `False`.

## RED (on 16003b7) and GREEN

I added 26 cases to `test_each_absence_wording_refuses`:
- The direction's forms:
  - "is not actually in the setlist"
  - "is not even on the setlist"
  - "not even a separate track"
  - "never a separate track"
  - "not really a track"
  - "is no longer present"
  - "is no longer included"
  - "is nowhere listed"
  - the five `not found` paraphrases
- rr3's punctuation forms: em dash, straight and curly quotes around the adverb, quotes around "listed", single curly quotes, brackets and the semicolon. Plus a colon form.
- Four probe-driven forms:
  - "not, in fact, a separate track"
  - "isn't, strictly speaking, its own track"
  - "Neither reprise is listed."
  - "Nor is the reprise listed."
- One (pin), "The reprise is not a track list entry." -> `not a track`, as on 16003b7.

**RED** ran the final test file against 16003b7's source, in a scratch `git archive 16003b7` with `PYTHONPATH` shadowing (`llama.__file__` printed the scratch path):
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<scratch>/packages/llama/src:<scratch>/packages/herder/src <worktree>/.venv/bin/python -m pytest -q -p no:cacheprovider packages/llama/tests/test_replay.py`
-> `25 failed, 225 passed`. The 25 failures are exactly the new non-pin cases, each returning None. The pin passes. An earlier RED in the live worktree, before any code change and with the first 21 cases (`-k absence_wording`), gave `21 failed, 101 passed`.

**GREEN:**
- `./.venv/bin/python -m pytest -q -p no:cacheprovider packages/llama/tests/test_replay.py` -> `250 passed`.
- Every existing case still names its existing term as the first hit, because the parametrized test asserts the exact reason.
- `llama.__file__` resolves inside the worktree.

**Full suite:** `./.venv/bin/python -m pytest -q -p no:cacheprovider` -> `5226 passed, 1 skipped, 8 deselected, 26 warnings in 40.25s`.

## Adversarial probe

The probe is `scratchpad/fix4/probe.py`, run through `briefing_reusable` with `_restored_pair` and a caution. Full output is in the log. 52 of 66 phrasings fire.

**Fires:**
- all of rr3's forms;
- "is, sadly, not — at least officially — part of the recording";
- "not…listed", "not...listed", "not/listed", "{yet}", "<yet>", "«officially»";
- "wasn't ever really, truly included";
- "Drums: not separately tracked.";
- "never got a track of its own";
- "never shows up on the tape", "hasn't shown up in any listing", "can't be found anywhere", "could not be found in the files";
- "not on the recording", "isn't in the data", "doesn't feature in the recording" (via in-recording);
- "not captured on the tape";
- "not among the tracks", "isn't counted as a track";
- "NOT LISTED";
- "not\nlisted", "not\tlisted", "not—listed", "not--listed";
- "not in the show's official setlist", "not on any of the setlists".

**Fires none (14):**
- Window overflow, by design: "The reprise isn’t – as far as we can tell – included." puts 6 words between the negation and the head, against a window of 5.
- Vocabulary outside every term, for the operator rather than this loop:
  - "not available", "unavailable here", "cut from the tape", "lacking from the tape", "The tape lacks the reprise", "did not make the tape", "wasn't recorded", "nowhere to be heard", "No reprise appears here", "The tape contains no reprise", "Nothing of the reprise survives", "gone from the tape".
  - Bare `no` is not in `_NEG`. Adding it would rename existing first hits, for example "There's no track for the jam" from `no separate track` to `not a track`.
- A typo: "isn' t listed".

## Timing probe

The probe is `scratchpad/fix4/timing.py`. It ran every pattern over 16 adversarial inputs of about 200k characters, each pattern on both the normalised and the raw text:
- "not " repeated; never plus separator runs; n't before a 200k-character word; "not a-a-a…"; not before a run of `’`; "no " repeated; chained negation-and-words; not plus 200k spaces; a mixed "isn't (yet), (really)" input;
- "no longer nowhere neither nor" repeated; "not track"; "not show show show"; "not in the in the on from";
- an apostrophe chain, a hyphen chain, and a realistic sentence ×500.

Results:
- Slowest single pattern: 0.040 s (`not a track` on "not x").
- Slowest whole input: 0.21 s, all terms plus normalisation. Normalisation itself takes at most 0.005 s.
- Doubling the input doubles the time (neg+words chain 0.150/0.299/0.600 s; mixed 0.123/0.238/0.468 s; "not x" 0.214/0.433/0.869 s), so growth is linear.
- The whole gate over a four-field briefing of about 800k characters took 0.54 s.
- There is no backtracking risk: separator and word classes are disjoint, and every window is bounded.

## Re-measure (~/.llama-harness/piece4/ckb/15b-r4/)

`final_15b.py` was copied from 15b-r3 with only its out dir changed. `dump.jsonl` was copied from 15a and is byte-identical to r3's. Outputs are `final.txt`, `final.json` and `samples.txt`, the top matched spans for three terms.

- **Refused:** 1014 of 1014, and 901 of the arm's 901. Nothing is still reusable.
- **First-hit distribution:** identical to r3. The reason changed in 0 rows (r3 versus r4 `final.json`).
  `names <file>` 406, `excluded` 389, `implausibly short` 133, `left out` 49, `too short` 25, `track count` 5, `absent` 3, `not part of` 2, `missing` 1, `not present` 1.
- **Per term, rows hit (of 1014 / of 901), with r3 in brackets.** Every sole-hit count is 0 unless a "sole" figure is given.

| Term | r4 (1014 / 901) | r3 |
|---|---|---|
| absent | 66 / 61, sole 1 | sole 1 |
| does not appear | 218 / 193 | 190 / 169 |
| dropped | 89 / 79 | |
| excluded | 677 / 607, sole 2 | sole 2 |
| implausibly short | 788 / 711 | |
| left out | 437 / 387, sole 1 | sole 3 |
| missing | 180 / 161 | |
| no separate track | 101 / 90 | 86 / 76 |
| not a track | 261 / 230 | 22 / 15 |
| not found (new) | 330 / 298 | |
| not in the setlist | 185 / 167 | 92 / 83 |
| not included | 27 / 22 | 25 / 20 |
| not listed | 44 / 41 | 34 / 31 |
| not part of | 168 / 143 | 167 / 142 |
| not present | 229 / 209 | 213 / 193 |
| not represented | 9 / 9 | |
| not tracked separately | 4 / 4 | |
| omitted | 45 / 39 | |
| too short | 55 / 46 | |
| track count | 886 / 792 | sole 1 |
| unlisted | 15 / 12 | |

- The arm-a name hits are unchanged: filename 84 / 76, stem 44 / 40, tail 279 / 254.
- Sole hits fell for `left out` (3 to 1) and `track count` (1 to 0). Rows that only those terms refused are now also hit by a widened term, which is the refusing direction.

**What the large jumps match:**
- `not found`: real claims such as "not found" (35), "not be found" (26), "not in the show data" (25), "not on this recording" (10); also instructions such as "do not place" (10), "not a cold dead place" (5).
- `not in the setlist`: "not in the setlist"/"track list"/"show data's track list".
- `not a track`: "not a separate track" (9), "not part of the track list" (7), and over-matches such as "do not stop on the tracks" (5), "not match any track" (3), "neither track" (3).

## Concerns

1. **Over-matching rises sharply** (`not a track` 22 -> 261, `not found` new at 330), much of it on instruction prose such as "do not stop on the tracks" and "do not place". It costs nothing in this batch, which was already refused 1014/1014. In future runs it applies only to briefings of shows with a restored file, at one brief call each, which the stakes paragraph accepts. The `place` head is the noisiest arm. The direction asked for it with any bounded negation; restricting it to `no place` would cut about 15 rows if the controller prefers that.
2. **Deviations from the literal direction, all in the refusing direction:**
   - `_NEG` also takes `neither` and `nor`.
   - The `not found` locations generalise "on the (tape|recording)" to in/on plus up to 2 words plus tape, recording, data, listing, list or file.
   - `not a track` uses window 5 with the `track`-word and `track list` exclusions, rather than rr3's `window(3)`, so that existing first hits keep their term.
   - `not part of` also takes a window between `part` and `of`.
3. **Residuals:**
   - A bounded window always has an N+1 aside ("isn’t – as far as we can tell – included" needs 6).
   - Bare `no` before a verb is not covered ("No reprise appears here").
   - Absence vocabulary outside every term, listed above, is for the operator.
4. The plain-word raw terms (`left out`, `too short`, `implausibly short`) still use `\s+` on the raw text, so "left — out" does not match them. They are outside this round's class and unchanged.
