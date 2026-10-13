# Task 12 fix round 1 — fix report

**Status: DONE_WITH_CONCERNS.** Every requested item is done. The concern: the re-derived `MISS_FRACTION` changed from 0.25 to **0.15**. It was pre-approved and is within every STOP ceiling, but it is tighter and is labelled pending Shawn's review.

## Commits (base 531b75f)
- `076089d` feat(emcee): verification reads a dropped g ("goin'") as its -ing form; MISS_FRACTION 0.15
- `05f3436` docs(emcee): calibration evidence for the dropped-g fold, MISS_FRACTION 0.15 and the memory gate

## Suite
`./.venv/bin/pytest -q` gives **2852 passed, 1 skipped, 8 deselected**. No live server was used this round, and none is running: 8781 and 8782 are free.

## A. Dropped-g fold (llama-9b decision while Shawn away, pending his review)
**What changed.** `comparable_words` now reads an apostrophe-spelled dropped g as its "-ing" form, before the apostrophe is stripped:
- The regex is `(?<![\w'‘’`])([^\W\d_]+in)['’](?!\w)`, replaced with `\1g`. So "goin'" becomes "going" and "feelin’" becomes "feeling". It applies on both sides, script and transcript.
- What it leaves alone:
  - "begin", "in" and "within", because they have no apostrophe;
  - a bare "in'", because at least one letter must precede "in";
  - a quoted 'within', because the lookbehind rejects an opening quote.
- `_joined` also accepts X + "in" as "Xing", so a heard "throw in" still matches "Throwin'". Without this, that previous match would have been lost.

**RED.** The command was `./.venv/bin/pytest packages/emcee/tests/test_verify.py -q`:
- **Failed (1):** `test_a_dropped_g_matches_the_ing_form_both_ways`. This was the expected failure: `comparable_words` returned `goin`, not `going`.
- **Passed already (44):**
  - The two over-match guard tests (`test_words_that_merely_end_in_in_are_not_g_dropped`, `test_a_dropped_g_heard_as_two_words_still_matches`) passed before the change, because they pin behaviour that already held.
  - The review-pin tests pin existing behaviour too; mutation proves them (D1 below).

**GREEN.** `test_verify.py` plus `test_calibration_measured.py`: **61 passed**.

**Re-derivation.** Command: `--reuse --rescore --artefacts 2,3,53 --max-s-per-char 0.09`. It re-scored 130 transcripts, loaded no model, and ran with no server.

| model | derivation | MISS_FLOOR | MISS_FRACTION | EXTRA_FLOOR | EXTRA_FRACTION |
|---|---|---|---|---|---|
| Whisper | all | 2 | **0.15** | 4 | 0.25 |
| Whisper | mlx only | 2 | 0.15 | 4 | 0.25 |
| Whisper | Voxtral only | 2 | 0.15 | 4 | 0.25 |
| Parakeet | all / mlx / Voxtral | 2 | 0.15 | 4 | 0.25 |

- **The thresholds changed:** `MISS_FRACTION` went from 0.25 to 0.15, and the other three are unchanged. No ceiling was exceeded. `verify.py` is updated.
- **Why it changed.** #21's misses fell from 3 to 1 (only "wharfrat"/"warfrat" is left). The worst long-unit fraction is now #39, at 3/32 = 0.094:
  - text: "After Drumz and the Jam, the band charged through The Other One, Jerry sang Wharf Rat for all he was worth, and Bob Weir hollered the set home with Turn On Your Lovelight."
  - transcript: "After drums and the jam, the band charged through the other one. Jerry sang Warfrat for all he was worth. And Bob Weir hollered the set home with Turn On Your Love Light."
  - 1.5 × 0.094 rounds up to 0.15, which is also the rule's floor.
- **Step 3 checks under Whisper** (all pass):
  - clean_failures = [];
  - 0.6B runaway: "only 19 of the script's 23 words were heard";
  - Chatterbox: "only 1 of the script's 4 words were heard";
  - defects_passing = [].
- **Guard at 0.09 is unchanged:** no clean failure, and Chatterbox, the 0.6B cap row and the 0.6B long-limit row all fail. At 0.15 Parakeet now also catches both runaways.
- **#21 leave-one-out now PASSES.** Leave-one-out is 0/53 for mlx and 0/10 for Voxtral. Interim and cross-backend checks are also 0.
- **Test tables.** `CLEAN_TRANSCRIPTS` was re-selected by the Step 6 rules and copied verbatim: the same six units in a new order (39, 31, 21, 5, 54, 59). `CLEAN_EDGES` and `RUNAWAY_TRANSCRIPTS` are unchanged.
- **Kokoro clip.** The transcript still passes at 0.15.

**Known limits** (recorded in the doc, not chased word by word):
- Wharfrat / Wharf Rat is heard as "Warfrat" (#21, #39).
- Shugaree is heard as "sugary" (#23).
- Drumz is heard as "drums" (#39).
- Proper nouns are misheard: Godchaux, Kezar, Porcelina, Saint → Santa.
- Spelling variants: grey/gray, Eddy/Eddie.

## B and C. Memory option (a) (llama-9b decision while Shawn away, pending his review)
- The Memory section records that swap growth made decision 8 a gate, and that it is resolved as option (a): Shawn closes tabs and other apps for voicing runs, and verification stays off by default. There is no code change.
- "Memory headroom on the 16 GB mini: measured, tight" is added as an open item under "What this does not show".
- Every A and B item carries the exact label "llama-9b decision while Shawn away, pending his review" (4 occurrences).

## D. Review minors
- **D1, same-word guards.** I added `test_a_repeated_word_pairs_only_with_two_unmatched_copies`.
  - **Deviation from the requested value:** with the guard in place the correct value is `found("Bye bye.", "Bye byebye.") == 1`, not 2. The exact match takes one "bye", and the lone residual copy cannot pair with itself. Getting 2 would require changing the algorithm, for example to pair before exact-matching.
  - The test therefore asserts 1, plus the heard-side mirror `found("Bye byebye.", "Bye bye.") == 1`.
  - **Mutants:** I ran them in scratch `git archive HEAD` copies, one fresh copy per mutant, with `PYTHONDONTWRITEBYTECODE=1`, a scratch cwd and PYTHONPATH shadowing proven via `emcee.__file__`. I predicted the new test would fail for both.
    - base: 10 passed.
    - m1 (pass-1 guard removed): **FAILED** `test_a_repeated_word_pairs_only_with_two_unmatched_copies`.
    - m2 (pass-2 guard removed): **FAILED**, the same test.
- **D2, narrowness.** Three tests added:
  - `test_only_adjacent_script_words_fold`: "L b a." heard as "La." gives found 0.
  - `test_an_unrelated_heard_word_is_not_credited`: show/snow gives 0, and "Here is the show." heard as "Here's the snow." gives 3.
  - `test_a_long_script_heard_as_a_few_contractions_still_fails`.

  The doc's contraction paragraph now notes the accepted homophone folds ("band is" ↔ "bands", "we are" ↔ "were").
- **D3.** Fixed the comments: unit 0 is both the shortest and the highest seconds per character, unit 26 is second-highest, and unit 30 is third.
- **D5.** The doc now states that 8766 → 8782 for Kokoro.
- **⚠️ "6 have exactly 3".** Reworded. The doc now cites only the data file's ≤ 2 count (`text_source.sentences_le_2_comparable_words`).
- Minors 6 and 7 are deferred and were not touched.
