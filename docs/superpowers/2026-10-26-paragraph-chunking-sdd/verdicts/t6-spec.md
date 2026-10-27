# Task 6 spec-compliance review (f105fb96..2cb14e34)

### Spec Compliance
- ✅ Spec compliant. Spec §5 (a) narrow first, (b) fall back without failing, the one-piece re-raise, §7 (no change to `_locate_block` or the chunked re-raise), and the Acceptance bullets for the strict path are all met by `_narrow_chunk` (audio.py:187-206) and the per-chunk catch in `_chunked_pcm` (audio.py:226-247).
- ⚠️ Cannot verify from the diff: none that block this task. The spec's known limit says narrowing takes go through `[tts.verify]`. They do because `_narrow_chunk` calls the same `speech` object as every normal chunk, which is the `QualitySpeech` wrapper when quality applies (tts/quality.py:37-45). No test covers verification of fallback takes specifically. The spec does not ask for one.

### What was done well
- `_narrow_chunk` does what the brief's Interfaces block says, item for item:
  - It splits with `_split_sentences(chunk)`.
  - When there is one piece or fewer it uses `raise blocked` and makes no call.
  - Each piece is synthesized alone with `fmt="wav"`, and the takes are kept.
  - It uses `raise located from blocked` on the first refused piece, so later pieces are never sent.
  - When every piece passes it returns the takes in order and makes no further call.
- The loop condition `j < len(takes) - 1 or i < len(sentences) - 1` (audio.py:245) puts 180 ms between takes and between chunks, and none after the last. Each take is `normalize_speech`-ed (audio.py:243). Neighbouring chunks are never re-sent. Room tone still runs once over the whole PCM.
- The handback states the context choice the brief asked for: the narrowing calls send no `previous_text`/`next_text`. The code matches (audio.py:202).
- Mutation evidence complies with the binding rubric. The predictions for A to E were written in t6-impl.log (line 278) before the runs. Each observed first failure is the predicted test, and each follows plausibly from its edit. A and D were also run as full `packages/emcee` runs: A failed 8 tests, including the process-level `blocked:` assertion; D failed 5, including `test_chunked_cross_sentence_block_needs_no_rephrase`. `git status` was clean after each run.

### Checks I ran
1. **Bed path (Review Focus 5), traced in the code, not only the test:**
   - Call chain: `render_speech_mp3` (audio.py:328) → `_render` → `bed_pcm is not None` → `_segment_pcm` (audio.py:274) → `chunking is not None` → `return _chunked_pcm(...)` (audio.py:281).
   - So the bed path runs the same per-chunk loop and the same `_narrow_chunk` as the bedless path (`_render` → `_synthesize_chunked` → `_chunked_pcm`). There is no second bed-specific synthesis loop that could skip narrowing.
   - A located `SpeechBlocked` raised inside `_chunked_pcm` leaves `_segment_pcm` before the rate and mono checks and the mix. `render_speech_mp3`'s `except SpeechBlocked` then re-raises it unchanged, because `chunking is not None` (audio.py:362-363).
   - On the fallback path the takes are ordinary PCM frames, so the existing rate and mono checks and `mix_bed` apply to them unchanged.
   - `test_chunked_block_with_bed_narrows_and_falls_back` (test_audio.py, new) asserts the same `speech.calls` as the bedless tests:
     - `[PASSAGE, S1, S2]` with `whole_passage False` when blocked on "climax";
     - `[PASSAGE, S1, S2, S3]` with the MP3 returned when blocked on "here. The climax".
   - The second case returns `\xff…` bytes, so the mix and encode actually completed with a matching bed rate.
2. **`_locate_block` and the chunked re-raise are unchanged.** I extracted `_locate_block` through the end of `render_speech_mp3` at f105fb96 and at HEAD and diffed them: identical. The diff touches only `_narrow_chunk` (new) and `_chunked_pcm`.
3. **The rephrase task receives the single sentence:**
   - `_repair` (process.py:218-262) passes `blocked.text` to `rephrase_segment` and prints the same `blocked.text` in `detail(f'  blocked: "{blocked.text}"')`. So the new assertion `f'blocked: "{BLOCKED_S2}"' in out` is the text the rephrase task received.
   - The assertion tells the two cases apart. SEG2 (`CLEAN_S1 + " " + BLOCKED_S2`, about 76 characters) is one chunk at ceiling 250. Before the change, the printed line would be `blocked: "China Cat…"`, which does not contain `blocked: "The climax…`.
   - In `test_chunked_reblocked_twice_raises_and_names_the_sentence`, the feedback line (process.py:229, `also blocked: "{blocked.text}"`) is checked to exclude CLEAN_S1, and the sentence is checked to be quoted.
   - The implementer's log (t6-impl.log:266-270) shows `blocked: "The climax lands early tonight."` as the sentence alone.
4. **The brief's test list, item by item:**
   - narrows ✓ (replaces the skipped `test_render_chunked_block_needs_no_locating`; no skip remains)
   - cross-sentence fallback ✓ (MP3 bytes, exactly `[PASSAGE, S1, S2, S3]`)
   - fallback audio length ✓ (`(3*7200 + 2*4320) * 2` bytes)
   - neighbours on both sides ✓. P1 is 75 characters and M about 84, so P1+M and M+P2 are each over 100 and make three chunks. The calls are `[P1, M, M1, M2, P2]` and the length is `4*take + 3*gap`.
   - one-piece re-raise ✓
   - bed ✓
   - the three unchunked tests unchanged ✓
   - process tests: the extended repair test ✓ (it already built its config with `TTSConfig(chunk=True)`); reblocked-twice ✓, with the manifest byte-identical; cross-sentence needs no rephrase ✓ (`"two. The climax"` spans SEG2's sentence boundary, SEG2 is unchanged, no `rephrase` call, and `set2-intro.mp3` exists).
5. **Fake provider semantics:** `FakeSpeechProvider.synthesize` (tts/fake.py:51-60) matches `block` against `text` only, never against the context. So the cross-sentence fixtures do model "passes alone, refused together".

### Issues (spec only)
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. `test_chunked_block_narrows_to_the_refused_sentence` uses the shared `CHUNKED` (`Chunking(250, room_tone=True)`, tests/helpers.py:17), not the brief's `Chunking(250, False)`. There is no behavioural effect, because the raise happens before room tone. Leave it as is or switch it to `_C` for consistency.
2. `test_chunked_reblocked_twice_raises_and_names_the_sentence` checks `'"The climax lands early tonight."' in rephrase.calls[1][1]` against the whole prompt. That quoted sentence can be satisfied by the prompt's blocked-sentence field alone. The feedback line is checked only for the absence of CLEAN_S1. The brief's wording ("the text quoted after it is the single reworded sentence") is met more tightly by checking that `'"The climax lands early tonight."' in feedback`. This is optional: the current pair of assertions already rejects whole-chunk quoting.
3. Mutants B, C and E were run over `packages/emcee` with `-x`, so only the first failure was recorded (90, 114 and 117 passed before the stop). That complies with "over packages/emcee", and the predicted test was the first failure each time. Only A and D have full-run lists.

### Assessment
**Spec compliance:** Approved
