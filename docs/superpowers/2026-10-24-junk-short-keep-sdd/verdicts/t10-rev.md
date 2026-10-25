### Spec Compliance

- ✅ Spec compliant. All three rulings are implemented as written.
  - Ruling 1: junk.py:217.
  - Ruling 2: junk.py:126-133 (the four alternatives match the brief's text; the call letters are scoped `(?-i:[KW][A-Z]{2,3})` inside `re.I`).
  - Ruling 3: spec 2.3 code block, the bullets at spec:182-197, and section 7 at spec:778-789.
  - The corpus fixture re-marks exactly the six ruled rows (guster WXRT; jrad Played over PA; rre on PA; theotherones d2t03/d2t14/d4t08). The count arithmetic (2822/685 -> 2816/691) checks out.
- ⚠️ Cannot verify from the diff: the full-suite claim (5012 passed). I did not re-run it, per instructions. The focused file passes in a scratch copy: 84 passed.

Checks run:
- **Spec 2.3 = junk.py.** I extracted the `NONPERF = re.compile(...)` block from both files and diffed them: IDENTICAL, 9 lines. Every other line of the 2.3 code block appears verbatim in junk.py. The only differences are the three `def` signature lines (type annotations); those are pre-existing and not touched by this diff.
- **Global-constraint names.** The diff touches only `NONPERF` and one line of `_apply_short_rule`'s first loop. `SHORT_FRACTION_OF_MEDIAN`, `MIN_MEDIAN_SAMPLE`, `MIN_PLAUSIBLE_SEC`, the two-pass floor (junk.py:297-336), `missing duration`, `_dedupe_duplicate_listings`, `_stem`, `_track_number` and `filter_files` appear only as context.
- **Zero-duration skip (named risk: does it change the median feed, or a neighbour's decision?).**
  - The floor and median are computed in `_keep_and_exclude` before `_apply_short_rule` runs, so the skip cannot move them. A 0.0 still feeds the median, as before.
  - `e["duration_sec"]` is always set on every excluded entry (junk.py:332), so there is no KeyError risk.
  - A `None` duration never reaches the skip: its reasons are `["missing duration"]`, and the existing guard already excludes it.
  - Taking a stub out of `base` can only shrink `lo..hi`, so it can only turn an untagged interior file into edge. It never keeps anything.
  - The implementer's re-measure used the reference `pos` and did not recompute interior status, so I checked that blind spot directly. The three affected shows (gratefuldead-1973-10-29, gratefuldead-1974-09-11, bluegroundundergrass-2008-04-04) have no untagged short candidates in r1_files.jsonl. No neighbour effect is possible.
- **Call sign: corpus probe** (old 2c95825 vs new cbd35c5 `short_tag_is_junk` and `short_filename_is_junk`, scratch copies, `llama.__file__` printed to prove shadowing). I ran it over all 13,202 rows: the 3,547 r1_files.jsonl rows plus every r1_sibs.json drop.
  - Library: exactly the 6 ruled files change.
  - Siblings: 20 change, every one broadcast or PA material. They match the pre-screen's 2 + 2 + 16: `KUSF show intro`, `WXRT Intro`, `KDHX ID` x3, eight KBFH intro/outro rows, `WMMR Tuning Intro`, `WMMS Intro` x2, `Crowd/Closing Music`, `Outro Music`, and both jrad `played over PA` rows.
  - The filename-junk verdict changed on no row.
- **Call sign: library-wide title scan.** I ran the four new alternatives over all 75,277 track titles in `~/.llama/shows/*/show.json` (read-only), any length, not just short files. Every hit is genuine broadcast or PA material: WXRT/KSAN/KPFA/WXTR, the theotherones HOST tracks, `music over PA system`, and two `outro music` tags. No song title matched.
- **Mutants** (scratch copy, `.venv/bin/python -m pytest` with PYTHONPATH shadowing proven by `llama.__file__`, `PYTHONDONTWRITEBYTECODE=1`, a fresh copy per mutant, prediction stated first). Seven of nine were caught:

  | Mutant | Predicted to fail | Result |
  |---|---|---|
  | M1: drop `or not e["duration_sec"]` | `test_ruling1_zero_duration_stub_is_not_kept` | CAUGHT, exactly that test |
  | M2: make the call letters case-insensitive | `keep_cases[kdhx intro]`, `[wake intro]` | CAUGHT, those two plus `[Wake Up Intro]` and the corpus test |
  | M3: drop the qualifier lookahead | `keep_cases[WAR]` | CAUGHT, exactly that |
  | M4: drop `host\s*#\s*\d` | the three Host additions | CAUGHT, plus the corpus test |
  | M5: drop the PA alternative | the two PA additions | CAUGHT, plus the corpus test |
  | M6: drop PA's `(?=\W|$)` | (I predicted it would survive) | CAUGHT by the corpus test |
  | M7: `or e["duration_sec"] < 1` (a threshold) | none | SURVIVED (see Minor) |
  | M8: drop `exit` | `additions_drop[exit music]` | CAUGHT |
  | M9: drop `wrap\w*` | none | SURVIVED (see Minor) |

### Strengths

- The case-sensitivity is done the clean way. A scoped `(?-i:...)` keeps one pattern in the spec's code block, with no second compiled regex to keep in sync, and the corpus plus the keep-case tests pin it. It works in the repo's Python (`requires-python >= 3.11`).
- The keep-case tests (test_short_keep_rule.py:123-131) go beyond the brief: `Wake Up Intro`, `Hostile`, `Host`, `Sgt. Pepper's PA/crowd`.
- The zero-duration test (test_short_keep_rule.py:134-143) fails on the old code. Its 4 s companion pins that real short files are still kept.
- The implementer surfaced the census-kind tension honestly instead of hiding it.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **spec:204 is stale.** "651 junk and 34 non-performance drops, no music among them" is the pre-ruling count. The corpus now has 691 junk drops (651 + 40 non-performance; test_short_keep_rule.py:76). Three of the six newly dropped rows carry census kind `music`/`music-fragment` (`Mardi Gras Celebration (Hey Pocky Way on PA)`, `Rock and Roll (Played over PA ...)`, `HOST #12 ...`), ruled non-performance. The sentence sits inside 2.3, which this task edited. Update it to the new counts and say that those 3 census-music rows are ruled PA playback or broadcast host talk.
2. **spec:189-191 is muddled.** "...with no song, segue or fragment among the rows newly dropped by any other path" is vacuous: there are no other newly dropped rows. Read beside the brief's bar, it also invites the "0 music lost" misreading the implementer warned about. Suggested wording: "exactly those 6 files newly drop; 3 carry census kind music/music-fragment, each ruled non-performance; no other row changes."
3. **The call-sign false-positive class is not recorded in section 7.** The term fires on any 3-4 capital K/W word next to a qualifier. Probed on synthetic tags:
   - all-caps titles: `KING BEE INTRO`, `WALK TALKING BLUES`, `WIND INTRO`, `WEIR TALK`;
   - band abbreviations with an intro: `WSP intro`, `WAR Intro`, `KVHW banter`-type;
   - a bare `WRAP`;
   - separately, the ruled `exit music` group drops the song `Exit Music (For a Film)`.

   Each of these drops only when the file is short. This was measured at 0 over 13,202 short drops and 75,277 library titles, and the ruling accepts it. Still, it belongs in section 7 beside the `Ardmore, PA` note, so a future false drop is a documented limitation and not a surprise (one line: "a K/W band abbreviation or all-caps title beside a qualifier reads as a call sign; measured 0").
4. **"Exact test, no threshold" is not pinned below 4 s.** M7 (`< 1`) survives. A one-line pin would catch a future "tidy" into a threshold: a tagged `length="1"` file is still kept.
5. **The ruled `wrap\w*` qualifier has no test** (M9 survives). Add e.g. `"KBFH Wrap-Up"` to `test_ruling2_nonperf_additions_drop`.
6. **A spam-shaped zero-duration file now records `implausibly short` instead of `spam-shaped name or tag`**, because the skip runs before the tripwire. It is dropped either way, so this is drop-only, but the reason a reader sees changes. Either note it in the 2.3 zero-duration bullet or leave it; it is harmless.
7. **Spec section 1 ("The rule") and 2.1/2.5 still describe the rule's domain as every file whose only reason is `implausibly short`.** Only the 2.3 bullet carries the zero-duration exception. A cross-reference in section 1's "unless" list ("or its duration is zero, 2.3") would keep the top-level statement true.

### Assessment

**Task quality:** Approved

**Reasoning:** The code is a minimal, exact port of the three rulings. Spec 2.3 matches junk.py character for character. The corpus changes are exactly the ruled rows, and an independent re-measure over 13,202 short drops and 75,277 library titles finds no unintended drop. The remaining items are spec-text accuracy and two unpinned corners, none blocking.
