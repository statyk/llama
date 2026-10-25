### Finding Verdicts

- **F1. Match the negation-proximity terms against a punctuation-normalised copy with a word window; keep `track count` and the other punctuation terms on the raw text; keep `_SEP`/`_WORD` disjoint; re-run a timing probe** — ADDRESSED.
  - The building blocks are at replay.py:265-278:
    - `_TOKEN = \w+(?:['’-]\w+)*`
    - `_normalised(text) = " ".join(_TOKEN.findall(text))`
    - `_SEP = " "` and `_WORD = [^ ]+`, which are disjoint.
  - Each entry is a `(term, pattern, normalised)` triple, and replay.py:377-379 picks the text it reads per term.
  - The 11 negation terms are flagged True. `track count` and the plain-word terms are flagged False and read the raw text as before.
  - Probes, through `briefing_reusable` with the test helpers (`llama.__file__` resolved to the worktree):
    - These fire: the em dash, straight and curly quotes, brackets, semicolon and colon forms.
    - "not — strictly speaking — listed" fires `not listed`.
  - My timing probe ran six adversarial inputs at 250k, 500k and 1M characters:
    - The inputs were dense `_NEG` alternation, nested in/on/show/up heads, track-prefixed words for the `not a track` lookaheads, apostrophe/hyphen chains for the normaliser, a negation before 20k-character words, and `n't` inside one long token.
    - Every input scales exactly linearly. The worst is 1.03 s per 1M characters for the whole gate, about 0.18 s for the slowest single pattern.
    - The normaliser takes at most 0.022 s per 1M.
    - There is no backtracking risk.
- **F2. A window between the negation and every following head word, the preposition included** — ADDRESSED.
  - `not in the setlist` (replay.py:321) is `{NEG}{w3}(?:in|on){w3}…list…`.
  - `not part of` (replay.py:297) is `{NEG}{w3}part{w3}of`.
  - `not found`'s in/on and `show … up` arms (replay.py:329) also carry the inner windows.
  - Probe: "is not actually in the setlist" and "is not even on the setlist" both fire `not in the setlist`.
- **F3. `not a track` gets a bounded window** — ADDRESSED. It is at replay.py:303-304.
  - Probe: "not even a separate track", "never a separate track" and "not really a track" all fire `not a track`.
  - Deviation check: window 5, the `track…`-word exclusion and the `in`/`on` exclusion on the `track list` alternative. See the deviations below.
- **F4. `_NEG` gains `no longer` and `nowhere`** — ADDRESSED. They are at replay.py:265.
  - Probe: "is no longer present" fires `not present`, "is no longer included" fires `not included`, "is nowhere listed" fires `not listed`, and "is nowhere in the data" fires `not found`.
- **F5. A new last term named exactly `not found` with the five paraphrases** — ADDRESSED.
  - It is at replay.py:329-331 and is the last entry.
  - Probe: all five fire `not found`: "does not show up in the data", "isn't on the tape", "cannot be found", "is nowhere in the data" and "has no place in the listing".
- **F6. Every existing case keeps its first-hit term; one case per quoted form; RED first** — ADDRESSED.
  - The diff only adds cases, at test_replay.py:1112-1139. No existing expectation changed, and the parametrized test asserts the exact reason string.
  - Focused GREEN on HEAD: `-k "absence_wording or restored or reus"` gave 146 passed.
  - RED, independently replicated: `git archive 16003b7` into scratch, plus HEAD's test_replay.py, with PYTHONPATH shadowing. The scratch `llama.__file__` was printed. Result: `25 failed, 225 passed`, and the 25 are exactly the new non-pin cases. The (pin) "not a track list entry" passes on 16003b7.
  - Every quoted form in the direction has its own case.
- **F7. Re-measure Part C into 15b-r4** — ADDRESSED.
  - `dump.jsonl` is byte-identical to 15a's. `final_15b.py` differs from r3's only in its out dir.
  - Refused is 1014/1014 and 901/901.
  - The first-hit distribution is identical to r3. r3 against r4 `final.json`: 0 rows changed reason, and 0 labels were lost per row, so on the corpus the new gate is a row-wise superset of r3's.
- **F8. Commit message** — ADDRESSED. cc37a3a carries the exact subject. The full-suite claim is 5226 passed, 1 skipped, 8 deselected, with the command; I did not re-run it.

Implementer deviations (requested check):
- **`neither`/`nor` in `_NEG`.** It refuses only more. `\bnor` and `\bneither` need a space next, because the window starts with `_SEP`, so `normal` and `manor` cannot hit. Corpus cost: "neither track" ×3 now hit `not a track`. Acceptable.
- **`not found`'s in/on location set** (tape, recording, data, listing, list, file). It is a superset of "on the (tape|recording)", and "isn't in the data" is a real claim. Dropping `from`/archive/source was correct: those were instructions. Acceptable.
- **`not a track` window 5 with its exclusions.** It is a superset of the 16003b7 pattern on every form I constructed: "not tracks", "not as a separate track", "not its own track", "not a track list entry", "not its own track-list", "not tracks, list".
  - The implementer claims every span the exclusions decline is fired by a later term. Measured on the corpus: of 88 spans that `{NEG}{w5}tracks?` matches and `not a track` declines, all 88 have a later normalised term firing in the same field, so 0 are lost.
  - A constructed escape exists: "The drums are not tracking as a separate track." fires nothing. Corpus 0. It is design (a), Minor; see Residuals.
- **The `part … of` window.** It refuses only more, and `part` must end a word, so `partly` cannot hit. Acceptable.
- **The first hit of every pre-existing case:** kept, as F6 shows.

### New Breakage in the Fix Diff

None. The fix introduced no regression. Every rewritten pattern is a superset of the pattern it replaced on the probed forms and, row-wise, on the corpus (0 labels lost from r3 to r4).

Residuals in the class (not introduced by this fix, but on the lines it rewrote). This is the structural judgment the round-4 prompt asked for. The design closes the separator class and the adverb-window class, but the class is NOT closed: two defects of kind (a) remain.

- **R1 (a), Important (strict surface): head-word inflection gap in `not included` (replay.py:315) and `not listed` (replay.py:316).**
  - These heads take only the past participle, while `does not appear` (replay.py:317) takes `appear(s|ed|ing)`. The task brief required these terms to match inflections in the refusing direction.
  - The present and active forms fire NO term. Each of these is a corpus sentence and fires nothing:
    - "The recording does not include the song that opened the show."
    - "The track data does not include that return as a separate entry."
    - "The track data does not list the jam separately."
  - Corpus incidence in 15a/dump.jsonl:
    - `(not|n't) include`: 52 spans in 47 rows. At least about 10 are explicit claims about the recording or track data ("this recording does not include", "the show data does not include it", "the show data's track list does not include", "this recording's track list does not include as a separate track").
    - `(not|n't) list(s)`: 71 spans in 63 rows, mixing absence claims ("the show data does not list", "the track data does not list the jam separately") with instructions ("do not list him").
    - Every one of these rows is refused in this batch by some other term. In production, a briefing carrying only this wording would be reused.
  - Fix for `not included`: change the head to `includ(?:e|es|ed|ing)\b`.
  - Fix for `not listed`: add `lists?`. A bare `list` head would rename `not in the setlist`'s first hits, because "not in the track list" would hit `not listed` first. So either guard it, e.g. `(?:listed|(?<!set )(?<!track )(?<!song )lists?)\b`, or put the verb forms in the last term.
- **R2 (a), Important (strict surface): a bare `no` negator before a vocabulary head word.**
  - "No encore is listed." fires no term.
  - The implementer kept `no` out of `_NEG`, because adding it there renames first hits. A term appended last cannot rename, though. For example: `\bno{w3}(?:listed|included|present|appear(?:s|ed|ing)?|found)\b` over the normalised text.
  - Corpus incidence: `no … (is listed|appears|is included|is present)` has 42 spans in 40 rows. These include "frog legs … is the last track in the show data. no encore is listed" (discobiscuits-2002-12-26) and "no encore is listed" ×6, which are absence claims that a restored encore would falsify.
  - "No drums track appears" already fires `no separate track`.
- **R3 (a), Minor: a head or negation joined by a hyphen.**
  - `-` is a word joiner in `_TOKEN` (replay.py:268), so a head after a hyphen never starts a word.
  - Each of these fires nothing: "not separately-tracked", "not officially-listed", "a not-included reprise", "is not-listed".
  - Corpus: 0 joined heads, and 3 `not-x`/`never-x` tokens (not-yet, not-too, not-great), none an absence claim.
  - Fix: drop `-` from `_TOKEN`'s joiners. The list-noun patterns already accept `[ -]?`, so `set-list` becomes `set list` and still matches. The cost is one more window word per hyphenated word.
- **R4 (a), Minor: apostrophe-likes other than `'` and `’`.**
  - In "isn`t", "isn´t" and "isnʼt" (U+02BC) the `n't` is lost: the first two split into `isn t`, and U+02BC is `\w`. All fire nothing.
  - Corpus 0.
  - Fix: fold those characters to `'` before tokenising.
- **R5 (a), Minor: the `not a track` exclusion.** "The drums are not tracking as a separate track." fires nothing, because the track-prefixed window word blocks the window and no later term covers `tracking`. Corpus 0, as measured above.
- **R6 (b): window overflow** (N+1 words of aside), e.g. "isn't – as far as we can tell – included". It is inherent to a bounded window.
- **R7 (b): vocabulary outside every term.**
  - `(not|n't) contain(s)`: 8 spans in 8 rows, including "this recording does not contain" and "a return to saint stephen that the supplied track list does not contain".
  - Also "lacks", "unavailable", "wasn't recorded", "cut from the tape". These are the implementer's list, which I did not re-measure.

Checks run, all logged in t15b-rr4.log:
- shadowing (`llama.__file__` in the worktree for probes, in scratch for RED);
- the RED replication;
- the focused GREEN;
- 40 probe phrasings;
- four corpus sweeps (incidence, contexts, `not a track` exclusion loss, r3 versus r4 row diff);
- the timing probe.

The live tree is untouched: `git status` is clean and HEAD is cc37a3a.

### Out-of-Scope Observations

- The raw plain-word terms `left out`, `too short` and `implausibly short` still use `\s+` on the raw text, so "left — out" and "left (entirely) out" miss them. This was already noted by the implementer. Minor.
- Over-matching on instruction prose has risen: `not a track` went from 22 to 261 rows, with "do not stop on the tracks"; `not found` is new at 330 rows, with "do not place". This costs one brief call per affected reuse, as the stakes paragraph accepts. The controller may want to narrow `place` to `no place` (about 15 rows).

### Verdict

**Fix round:** All findings addressed (F1-F8), and the fix itself introduced no Critical or Important breakage.

The structural design does not yet close the CLASS. Two residuals of kind (a) are Important on the strict surface:
- **R1:** the `not included`/`not listed` heads lack `include/includes/including` and `list/lists`. 47 and 63 corpus rows, with real recording-data absence claims among them.
- **R2:** bare `no` before a vocabulary head ("No encore is listed."). 40 corpus rows.

Both are closable without renaming any existing first hit: extend the heads (guarding `list`), and append a `no …` term last.

R3-R5 are (a) Minor with 0 corpus incidence. R6 and R7 are (b).
