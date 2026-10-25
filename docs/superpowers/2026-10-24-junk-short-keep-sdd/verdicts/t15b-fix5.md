# t15b-fix5 handback: DONE

Commit `9e35b0d` on held-backlog-junk-filter (parent cc37a3a): `fix(replay): absence heads take every inflection, bare no, hyphen and apostrophe forms`.
- Files changed: `packages/llama/src/llama/replay.py` and `packages/llama/tests/test_replay.py`. junk.py is untouched.
- Log: `t15b-fix5.log` in this directory.

## Design, per finding

1. **R1, the include and list inflections.**
   - `not included`'s head is now `includ(?:e|es|ed|ing)\b`. No noun is spelled "include", so this cannot rename a first hit.
   - The list verb forms could not stay in `not listed`. A bare `list` head would take the first hit of the existing cases "The reprise did not appear on the list." and "is not appearing in the list." from `does not appear`, which comes after `not listed`. The reviewer's lookbehind guard (`set `/`track `/`song `) does not cover "the list". So, per the direction's fallback, the verb heads `list(?:s|ed|ing)?` and `contain(?:s|ed|ing)?` (item 6) went into a new term `not included or listed`, appended after `not found`: `{NEG}{w5}(?:list…|contain…)\b`.
2. **R2, a bare "no".** The new last term `no … listed` (with U+2026 in the name) is `\bno{w3}(?:listed|included|present|appear(?:s|ed|ing)?|found)\b`.
3. **R3, the hyphen.** `_TOKEN` no longer joins words on `-`. But a hyphen-split copy alone LOST 7 corpus labels in the first re-measure, because a hyphenated word now counts as several window words. Real claims among them:
   - "the show data has no separate return-to-astronaut track" (discobiscuits-2005-12-30)
   - "is not in the set-break data"
   - "does not appear in any best-of lists"

   So `_normalised(text)` returns TWO copies: one with the hyphen as a separator (`_TOKEN = \w+(?:['’]\w+)*`), and one with the hyphen as a joiner (`_TOKEN_HYPHENATED = \w+(?:['’-]\w+)*`, as in r4). A normalised pattern fires on either copy, so the result is a superset of r4 and of the hyphen-split reading. After the change, 0 labels are lost. The list-noun patterns are back to `[ -]?` so they work on both copies.
4. **R4, apostrophe look-alikes.** `_APOSTROPHES` folds `` ` `` (U+0060), `´` (U+00B4), `ʼ` (U+02BC), `‘` (U+2018) and `′` (U+2032) to `'` before tokenising.
5. **R5.** `not tracked separately`'s head is now `track(?:ed|ing)\b`, so "not tracking as a separate track" fires it.
6. **R7, "contain".** It is in `not included or listed`, as item 1 describes.
7. **The plain-word terms.** Entries are now `(term, raw, normalised)`, either one possibly None, and a term fires in the first field where any of its patterns match.
   - `implausibly short` and `too short` keep their raw pattern and add the same words on the normalised copies, so "too—short" fires.
   - `left out` adds `\b(?:left|leaves?|leaving){w2}(?:out|off)\b` on the normalised copies. "left (entirely) out" needs one window word.
   - The `place` arm is unchanged, per the controller's ruling.

Term names and order are unchanged. The two new terms are appended last.

## Patterns verbatim

```python
_NEG = r"(?:\bnot|\bnever|n['’]t|\bcannot|\bno longer|\bnowhere|\bneither|\bnor)"
_SEP = " "
_WORD = r"[^ ]+"
_TOKEN = re.compile(r"\w+(?:['’]\w+)*")
_TOKEN_HYPHENATED = re.compile(r"\w+(?:['’-]\w+)*")
_APOSTROPHES = str.maketrans({"`": "'", "´": "'", "ʼ": "'", "‘": "'", "′": "'"})
def _normalised(text) -> (split, joined)   # both " ".join(findall) over text.translate(_APOSTROPHES)
def _window(n, word=_WORD): return rf"(?:{_SEP}{word}){{0,{n}}}?{_SEP}"

("excluded", r"\bexclu(?:de|ded|des|ding|sion|sions)\b", None),
("implausibly short", r"\bimplausibl[ey]\s+short\b", r"\bimplausibl[ey] short\b"),
("too short", r"\btoo\s+short\b", r"\btoo short\b"),
("left out", r"\b(?:left|leaves?|leaving)\s+(?:out|off)\b", rf"\b(?:left|leaves?|leaving){_window(2)}(?:out|off)\b"),
("omitted", r"\bomi(?:t|ts|tted|tting|ssion|ssions)\b", None),
("absent", r"\babsen(?:t|ce)\b", None),
("not present", None, rf"{_NEG}{_window(3)}present\b"),
("missing", r"\bmissing\b", None),
("dropped", r"\bdropp(?:ed|ing)\b", None),
("not represented", None, rf"{_NEG}{_window(3)}represented\b"),
("not part of", None, rf"{_NEG}{_window(3)}part{_window(3)}of\b"),
("not a track", None, rf"{_NEG}{_window(5, r'(?!track)[^ ]+')}tracks?\b(?![ -]?list(?:ing)?s?\b)"
                      rf"|{_NEG}{_window(5, r'(?!track|(?:in|on) )[^ ]+')}tracks?[ -]?list(?:ing)?s?\b"),
("track count", <unchanged, raw>, None),
("not included", None, rf"{_NEG}{_window(5)}includ(?:e|es|ed|ing)\b"),
("not listed", None, rf"{_NEG}{_window(5)}listed\b"),
("does not appear", None, rf"{_NEG}{_window(5)}appear(?:s|ed|ing)?\b"),
("unlisted", r"\bunlisted\b", None),
("not in the setlist", None, rf"{_NEG}{_window(3)}(?:in|on){_window(3)}(?:set|track)[ -]?list(?:ing)?s?\b"),
("no separate track", None, rf"\b(?:no|without){_window(3)}tracks?\b"),
("not tracked separately", None, rf"{_NEG}{_window(3)}track(?:ed|ing)\b"),
("not found", None, <unchanged from cc37a3a>),
("not included or listed", None, rf"{_NEG}{_window(5)}(?:list(?:s|ed|ing)?|contain(?:s|ed|ing)?)\b"),
("no … listed", None, rf"\bno{_window(3)}(?:listed|included|present|appear(?:s|ed|ing)?|found)\b"),
```

## RED (cc37a3a) and GREEN

There are 21 new cases in `test_each_absence_wording_refuses`, 19 of them one per quoted form of the direction:
- the three corpus include/list sentences
- "This recording does not contain the reprise."
- "No encore is listed.", "No reprise is included." and "No intro appears."
- the four hyphen forms
- isn`t, isn´t and isnʼt
- "not tracking as a separate track"
- "left — out" and "left (entirely) out"
- "too—short" and "implausibly—short"

The other 2 are (pin) corpus sentences that only the hyphen-joined copy keeps: "no separate return-to-astronaut track" and "not in the set-break data".

- **RED, live tree, tests only, before any code change on cc37a3a:** `./.venv/bin/python -m pytest -q -p no:cacheprovider packages/llama/tests/test_replay.py` gave `19 failed, 250 passed`.
- **RED, final test file against cc37a3a's source:** this ran in a scratch `git archive cc37a3a`, with `PYTHONPATH` shadowing; `llama.__file__` printed the scratch path. Result: `19 failed, 252 passed`. The two pins pass on cc37a3a.
- **GREEN:** `test_replay.py` gave `271 passed`. The parametrized test asserts the exact reason string, so every existing case keeps its first-hit term.
- **Full suite:** `./.venv/bin/python -m pytest -q -p no:cacheprovider` gave `5247 passed, 1 skipped, 8 deselected, 26 warnings in 41.09s`.

## Adversarial probe

The probe is `probe.py` in the scratchpad (round-4 list plus 35 round-5 phrasings); full output is in the log. **85 of 101 phrasings fire.**

New forms that fire:
- the include and list sentences; "never contained"; "isn't including"; "doesn't actually list it"
- "No encore was ever found."; "No reprise, sadly, is present."; "No encore appearing here."; "There is no reprise listed."
- every hyphen form, and "Not-included: the reprise."
- all five apostrophe look-alikes
- "left, sadly, off"
- "not on the set-list" and "not on the track-list"

**16 fire none:**
- **Window overflow by design (2):** "isn’t – as far as we can tell – included" and "not—as far as the data goes—included", each a 6-word aside.
- **Typo (1):** "isn' t listed".
- **Not windowed (1):** "too (very) short". `too short` takes no window on the normalised copies; only `left out` was asked for.
- **Absence vocabulary outside every term, for the operator (12):**
  - "not available", "unavailable"
  - "cut from the tape", "lacking from the tape", "The tape lacks the reprise"
  - "did not make the tape", "wasn't recorded", "nowhere to be heard"
  - "The tape contains no reprise", "The data lists no reprise" (verb first, then `no`)
  - "Nothing … survives", "gone from the tape"

## Timing probe

The probe is `timing5.py` in the scratchpad. It ran 21 adversarial inputs of about 200k characters. The new inputs were "no encore is" repeated, "left left left", a backtick chain, "not-a-b-c-d" words, and "not list contain". Every normalised pattern ran on both copies, and every pattern also ran on the raw text.
- The slowest single pattern took 0.078 s (`not a track` on "not x").
- The slowest whole input took 0.45 s.
- Normalisation, making both copies, took at most 0.006 s.
- Scaling is linear on every input: x1/x2/x4 gave 0.31/0.63/1.25 s (neg+words), 0.46/0.91/1.83 s ("not x"), 0.26/0.53/1.07 s (no+words) and 0.31/0.62/1.25 s (not list).
- The whole gate over a four-field briefing of about 800k characters took 1.09 s. Real briefings are a few KB.
- Reading two copies roughly doubles round 4's cost. The windows are bounded, and `_SEP`/`_WORD` are disjoint on both copies.

## Re-measure (~/.llama-harness/piece4/ckb/15b-r5/)

- **Inputs:** `final_15b.py` was copied from r4, with only its out dir changed. `dump.jsonl` was copied from 15a.
- **Refused:** 1014 of 1014, and 901 of 901. Nothing is still reusable.
- **First-hit distribution:** names <file> 406, excluded 389, implausibly short 133, left out 50, too short 25, track count 5, absent 2, not part of 2, missing 1, not present 1.
- **One row shifted**, absent to left out: stevekimockband-2004-08-21. Its per_set says "the track list leaves it out as a song because of its short length". That is a genuine absence claim the raw `left out` missed ("leaves it out"), and the new 2-word window catches it. `left out` comes before `absent` in the check order, so it is now the first hit.
- **No labels lost:** compared row by row with r4, 0 rows lose a label.

Per term, rows hit (of 1014 / of 901). Sole hits are 0 for every term except absent and excluded.

| Term | r5 | r4 |
|---|---|---|
| absent (sole 1) | 66 / 61 | |
| does not appear | 218 / 193 | |
| dropped | 89 / 79 | |
| excluded (sole 2) | 677 / 607 | |
| implausibly short | 788 / 711 | |
| left out | 472 / 417 | 437 / 387 |
| missing | 180 / 161 | |
| no separate track | 101 / 90 | |
| no … listed (new) | 345 / 311 | |
| not a track | 262 / 231 | 261 |
| not found | 331 / 298 | 330 |
| not in the setlist | 185 / 167 | |
| not included | 106 / 95 | 27 / 22 |
| not included or listed (new) | 315 / 285 | |
| not listed | 44 / 41 | |
| not part of | 168 / 143 | |
| not present | 229 / 209 | |
| not represented | 9 / 9 | |
| not tracked separately | 5 / 5 | 4 |
| omitted | 45 / 39 | |
| too short | 55 / 46 | |
| track count | 886 / 792 | |
| unlisted | 15 / 12 | |

Name hits are unchanged: filename 84/76, stem 44/40, tail 279/254.
- The sole hit for `left out` went from 1 to 0, because that row is now also hit by a new term.
- `not a track`'s +1, `not found`'s +1 and `not tracked separately`'s +1 come from the hyphen-split copy.

## Concerns

1. **The hyphen is read two ways.** The direction said to drop `-` from the joiners. Doing only that lost 7 corpus labels, real absence claims among them, so both copies are scanned. This is strictly a superset, and costs twice the scan time, which is negligible at briefing size.
2. **`list` and `contain` sit in a new term** (`not included or listed`), not in `not listed`. The direction's fallback allows this: no guard keeps "did not appear on the list" with `does not appear`.
3. **Over-matching keeps growing:**
   - `no … listed` hits 345 rows; it also fires on instructions like "no … found".
   - `not included or listed` hits 315 rows, including "do not list him".
   - `left out` adds 35 rows.

   On the gate's population this costs one brief call per affected row, as the stakes allow.
4. **Residuals:**
   - window overflow (6-word asides)
   - "too (very) short" (no window on `too short`)
   - verb-then-`no` ("The data lists no reprise")
   - the operator-vocabulary list above
