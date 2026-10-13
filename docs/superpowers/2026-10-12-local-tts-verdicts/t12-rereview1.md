### Finding Verdicts

**[A] Dropped-g fold and re-derivation** — ADDRESSED
- **The fold.** It is at verify.py:51 (`_DROPPED_G`), applied in `comparable_words` before apostrophes are stripped (verify.py:58), so it acts on both the script and the transcript. `_joined` adds X + "in" → "Xing" (verify.py:100-104).
- **Tests.** test_verify.py:163-176 covers goin'/going and feelin'/feeling both ways, including the curly ’. It also covers "throw in" → "Throwin'" and "begin", "in", "within", 'within' and "in'".
- **Re-scoring.** I re-scored every saved transcript in the committed data file with the worktree's verify.py (`emcee.__file__` resolves inside the worktree). That is 63 units × 2 STT models, and none disagrees with the stored words/missing/extra.
- **Re-derivation.** I re-derived using the brief's `recommend` rules (brief:336-341):
  - Whisper gives 2 / 0.15 / 4 / 0.25. The worst long unit is #39 at 3/32 = 0.094; 1.5 × 0.094 = 0.141, which rounds up to 0.15, the floor. Next come #31 at 0.08 and #21/#23 at 0.053.
  - Parakeet also gives 2 / 0.15 / 4 / 0.25.
- **The new value agrees everywhere.** `verify.MISS_FRACTION` is 0.15 (verify.py:31). `recommendation.thresholds` in the data file is 2/0.15/4/0.25. The doc's adopted table matches (doc:160, :164).
- **Step 3 checks still hold.**
  - Clean failures: none, under either model.
  - Leave-one-out: no unit fails, #21 included. The data shows `loo_all_derivation` at 0/53.
  - Qwen 0.6B runaway: "only 19 of the script's 23 words were heard". It is still not None, and with 57 words heard for a 23-word script the extra check would fail it too.
  - Chatterbox: "only 1 of the script's 4 words were heard".
  - Ceilings: MISS_FRACTION 0.15 ≤ 0.4, EXTRA_FRACTION 0.25 ≤ 1.0, MISS_FLOOR 2 is within 2-3, EXTRA_FLOOR 4 ≤ 6. `test_measured_thresholds_tolerate_a_wrong_word_or_two` pins all four.
- **Step 6 tables are verbatim.** `CLEAN_TRANSCRIPTS` equals the data's top-3 missing/words units (39, 31, 21) followed by the top-3 extra/words units (5, 54, 59), in that order. #21 and #23 tie at 1/19, and the stable index order picks #21. `RUNAWAY_TRANSCRIPTS` is also verbatim.
- **Known limits.** These are listed at doc:196-207: Wharfrat/Wharf Rat → "Warfrat", Shugaree → "sugary", Drumz → "drums", plus the proper nouns and spelling variants. They match the residual Whisper `missing_words` in the data.
- **Can the fold credit a word that was not said?** I probed this directly. Only the script side can mis-fold, which makes it a false alarm, not a false credit.
  - A bare "in" and "in'" stay "in". "begin" is never touched. A single quoted word ('within', 'win', 'Terrapin') is unchanged.
  - A heard "in" beside a heard X can credit a script "Xing" only after exact matching has run. The exact pass first takes every script "in", so a heard "in" the script needs cannot be stolen. In one probe, "Playing in the band" heard as "Play in the band" credits 3 of 4, not 4.
  - The X+"in" ↔ "Xing" pairs are the same acoustic-homophone class the doc already accepts: "go in" / "going", "even in" / "evening".
  - **Real corpus.** I ran the regex over the 129 delivered `dj-notes.md` files. It matched 210 times, and every match was a genuine dropped g: truckin', playin', lovin', goin', dancin', lightnin', feelin', knockin', walkin', throwin', sittin', dozin'.
  - The one quoted-phrase edge is filed below as Minor.

**[B] Memory gate, option (a)** — ADDRESSED
- doc:331-338 says that swap growth made decision 8 a gate. It is resolved as option (a): no code change, close tabs and other apps for voicing runs, and verification stays off by default (`[tts.verify] backends = []`). The runbook is left to Task 15.
- doc:387 adds the open item "memory headroom on the 16 GB mini — measured, tight" under "What this does not show".

**[C] Labels** — ADDRESSED
- The exact label "llama-9b decision while Shawn away, pending his review" appears 4 times: doc:139 (the fold), :164 (the adopted thresholds), :331 (memory option (a)) and :351 (recommendations item 3).
- **MISS_FRACTION 0.15**, the only value that differs from 2/0.25/4/0.25, is recorded as pending his review at doc:164-168. That passage also records the history: the operator approved 0.25 under option B.

**[D1] Same-word guards pinned** — ADDRESSED. **1 is the correct value.**
- **The test.** It is at test_verify.py:138-142.
  - `found("Bye bye.", "Bye byebye.")`: exact matching takes one "bye". That leaves w = {bye: 1} and h = {byebye: 1}. The pass-1 guard needs w["bye"] ≥ 2, so the result is 1.
  - The heard-side mirror: w = {byebye: 1} and h = {bye: 1}. The pass-2 guard blocks it, so the result is 1.
- **I re-verified the mutants myself** (scratch copy, loaded by path, `PYTHONDONTWRITEBYTECODE=1`).
  - Without the pass-1 guard, the first assertion gives **3**: found exceeds n = 2, which is the over-credit the guard exists to prevent.
  - Without the pass-2 guard, the mirror gives **2**.
  - The unmutated copy gives 1 and 1. Each assertion catches exactly one guard, so both guards are pinned.
- **Why 2 was not achievable.** The controller's suggested 2 cannot come from this algorithm: it matches exactly first, then pairs. 2 would be the *ideal* score for the first case, since both script "bye"s were spoken. So 1 is a conservative under-credit, not an over-credit; it can only cause a false alarm, never a false pass.
  - The mirror's 1 is semantically right: only one heard "bye" is left for "byebye".
- **Nit, non-blocking.** `== 1` also freezes the under-credit, and an assertion of `<= 2` (found ≤ n) would pin both guards without doing that.

**[D2] Narrowness tests and the homophone sentence** — ADDRESSED
- test_verify.py:145-146: "L b a." heard as "La." gives 0. It is a genuine adjacency pin: an any-pair mutant would fold (l, a) into "la".
- :149-151: show/snow gives 0. "Here is the show." heard as "Here's the snow." gives 3.
- :154-156: a 15-word script heard as "Here's you're." fails ("only 4 of the script's 15 words were heard").
- doc:135-137 has the homophone sentence: "band is" ↔ "bands", "we are" ↔ "were".

**[D3] Unit comments** — ADDRESSED. test_calibration_measured.py:22-24: unit 0 is the shortest text and the highest seconds per character, unit 26 is second-highest, and unit 30 is third-highest.

**[D5] Kokoro port** — ADDRESSED. doc:271 reads "(port 8766 → 8782: the brief's 8766 is reserved for an unrelated operator process)".

**[D-⚠️] "6 have exactly 3"** — ADDRESSED. doc:222 now cites only the 1 sentence with ≤ 2 comparable words, with the data key `text_source.sentences_le_2_comparable_words`. The data holds `{count: 1, examples: ["Some background first."]}`, which matches.

### New Breakage in the Fix Diff
- **Minor — verify.py:51, and the doc's claim at doc:143-145.**
  - **The problem.** A multi-word phrase in single quotes whose last word ends in "in" is folded, because the closing quote is read as a dropped-g apostrophe. 'Fire on the Mountain' becomes [fire, on, the, mountaing], and ‘Box of Rain’ becomes […, raing].
  - **The effect.** On the script side, this costs one spurious miss per such title against a transcript of "mountain", which is a false alarm and never a false credit. Before the fix it was "mountain".
  - **The doc.** It says the untouched cases "have no closing apostrophe". That is inaccurate: a quoted 'within' does have one; it is the opening quote that protects it, and only for a single quoted word.
  - **Exposure, measured.** There was 1 single-quoted span in the 129 delivered scripts ('Twenty Years So Far'), and 0 regex over-matches in 210 hits.
  - **Fix, non-blocking.** Exclude a closing quote whose phrase was opened by ' or ‘. Or just correct the doc sentence and list this as a known limit.

### Out-of-Scope Observations
- At MISS_FRACTION 0.15, a sentence of 8-19 comparable words tolerates only 2 misses, and one of 20-26 words tolerates 3. One sentence carrying two lexicon spellings and a misheard proper noun would therefore re-render. The doc says so ("A sentence dense in these is where a spurious re-render would come from"). The measured margin is fine: no clean unit sits at its allowance, and the nearest is #39 at 3 of an allowed 4. Shawn should still weigh this when he reviews the 0.15.
- The doc still recommends enabling verification for mlx_audio when Phil goes live (doc:345-350). It qualifies that with "weigh the memory finding" alongside option (a). That is consistent, but Shawn's review of option (a) decides it.
- Minors 6 and 7 from the previous review are deferred, as reported.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage. There is one new Minor (the quoted-phrase over-fold at verify.py:51, plus a doc sentence), and it is non-blocking. MISS_FRACTION 0.15 agrees across verify.py, the data file's recommendation, the doc and the test tables. It is labelled pending Shawn's review.
