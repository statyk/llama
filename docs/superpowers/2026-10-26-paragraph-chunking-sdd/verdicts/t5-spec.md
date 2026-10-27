# Task 5 spec-compliance review (6623bae5..21db2638)

Verdict: Needs fixes. One Important finding is a missing pin for a requirement; the other needs a ruling from the controller.

## What was done well
- `_chunked_pcm` follows the brief: one call per `plan_chunks(text, chunking.ceiling)` chunk, neighbour chunks passed as `previous_text`/`next_text`, each chunk normalized, the 180 ms joins unchanged, and `fill_room_tone(pcm, framerate, channels, seed_text=text)` applied last and only when `room_tone` is set. The bed path (`_segment_pcm` calls `_chunked_pcm`) and the no-bed path (`_synthesize_chunked` calls `_chunked_pcm`) both get it, as spec section 3 requires ("whether or not a bed is mixed").
- `_render_key`: the unchunked string is byte-identical to the old inline formula. The chunked key adds `"\nchunks=" + sha256(_CHUNK_SEP.join(plan_chunks(...)))[:16]`, computed outside any f-string, then `\ntone=<ROOM_TONE_VERSION>` only when room tone is on. `_CHUNK_SEP = "\x1f"` is a module constant. `_synthesize_dj_audio` uses the new function.
- The unchunked collapse sits at the top of `render_speech_mp3`, before `_render` and before `_locate_block`. It is skipped on the chunked path. The key is computed upstream from the uncollapsed `spoken`, which "Settled at the builder check" allows.
- All 9 tests the brief names exist. The existing tests were updated with their intent kept (`SENTENCES` where a test is about one sentence per chunk; a rename plus the packed assertion for the say default test).
- Addition (B) is covered end to end through `process_package` (`test_process_package_forwards_configured_chunk_chars_and_room_tone`) and through the real `emcee say` CLI (`test_say_forwards_chunk_chars_and_room_tone`). Both check the ceiling (50 gives 2 calls where 250 gives 1) and the room-tone flag. Mutation E shows these tests catch a hard-coded `TTSConfig.chunking`.
- Mutation evidence: A-E each have a prediction logged before running (t5-impl.log line 302 onward), and each observed failure follows plausibly from its edit.
- The Task-6 skip of `test_render_chunked_block_needs_no_locating` is justified. PASSAGE now packs into one chunk, so its sentence-level `ei.value.text` assertion has to fail. The brief allows that skip.

## Spec Compliance
- ❌ Issues found:
  - Under-pinned requirement: the "collapse before `_locate_block`" requirement is not actually tested. `test_audio.py::test_unchunked_collapses_whitespace_before_send_and_locate` (diff lines 536-543) has the right name but its second half cannot fail.
  - Ruling needed: orchestrator addition (A) and plan Review Focus 2 forbid an empty provider call, but `test_chunked_empty_text_is_one_call_as_before` (diff lines 482-487) pins exactly one empty call for whitespace-only text.
- ⚠️ Cannot verify from diff: nothing material. I read `_segment_pcm`, `_synthesize_chunked` and `plan_chunks` at HEAD only to confirm the bed path and the empty-text behaviour (named risks below).

## Issues (spec only)

### Critical (Must Fix)
None.

### Important (Should Fix)

1. **The "collapse before `_locate_block`" requirement is unpinned.**
   - The rule comes from "Settled at the builder check" and the brief: the collapse happens "before both the provider call and `_locate_block`, so narrowing probes and error text match what was sent". The brief's test bullet is "`_locate_block`'s probe calls contain no "\n"".
   - The test's text is `f"{P1}\n\n{P2}"`. Its only newlines follow a period, and `_split_sentences` splits on `(?<=[.!?])\s+`, so the sentence probes are newline-free whether or not `_locate_block` received collapsed text. The probe-half assertion (`all("\n" not in c for c in blocked.calls)`) is vacuous.
   - Named risk checked: a mutant that collapses for `_render` but passes the original text to `_locate_block`. I ran it in a scratch copy under scratchpad/t5m, after proving the shadowing (`emcee.__file__` resolved inside the copy). The whole emcee suite passes on it: 1004 passed, 1 skipped.
   - The implementer's Mutation C does not catch this. Its edit (collapse only inside the `except`) differs from the brief's wording ("move the collapse after the `_locate_block` call"), and both variants are caught only by the send-half assertion.
   - A discriminating input exists. A probe with a mid-sentence wrap (`"...Portland in the\nspring of 1974. ... \n\nListen for the long jam..."`, `block="long jam"`) gives a probe call containing `"\n"` under the mutant, and none at HEAD.
   - Fix: use a mid-sentence single-newline wrap in the blocked half of the test, and/or assert that `ei.value.text` has no `"\n"`.

2. **Ruling needed: whitespace-only chunked text still makes one empty provider call, and a test now pins it.**
   - Addition (A) reads "whitespace-only or empty text must not produce an empty provider call — keep today's behaviour or safer, and pin it". Plan Review Focus 2 also says whitespace-only text "must produce no empty chunk and no empty provider call".
   - `test_chunked_empty_text_is_one_call_as_before` asserts `speech.calls == [""]` for `"  \n "` with `CHUNKED`. `plan_chunks`' own docstring says "whitespace-only text returns `[""]`".
   - The implementer's reading is factually right about today's behaviour. I confirmed that at base: `_split_sentences` returns `sentences or [text.strip()]`, which is `[""]`. So this is not a regression. The two halves of (A) conflict, and the implementer picked "keep today's" over the explicit "must not".
   - Reachability is low. `emcee say` refuses an empty file after strip (cli.py about line 716). `ScriptNotes.outro`/`set_intros` values have no minimum length, though, so an empty DJ segment can still reach the renderer, as before.
   - Controller decision: (a) accept and record the ruling, keeping the test; or (b) make it safer. For (b), `_chunked_pcm` would raise a `SpeechError` (or skip the call) on an empty plan rather than sending `""`, and the test would be inverted.

### Minor (Nice to Have)
- Stale docstrings, which the quality reviewer may also raise:
  - `_synthesize_chunked` still says "Sentence-by-sentence synthesis ... silence between sentences" (audio.py, about line 226).
  - `_synthesize_dj_audio`'s docstring still lists the key as "text + voice + model + chunk [+ bed] [+ loud]", without `chunks=`/`tone=`.
  - Inside `_chunked_pcm` the loop variable is still named `sentences`/`sentence` although it now holds chunks.
- `test_process_package_forwards_configured_chunk_chars_and_room_tone` is absent from the RED run: 13 failed + 991 passed = 1004, and GREEN is 1004 + 1 skip. It was written after the implementation, so it has no RED evidence of its own. Mutations B and E do show it bites, so this is about evidence, not coverage.
- In the test helper, `_key(text, chunking, monkeypatch=None)` has an unused `monkeypatch` parameter.

## Assessment
**Spec compliance:** Needs fixes. Fix 1 (a discriminating input for the locate half of the collapse test). For 2, a controller ruling (accept as recorded, or make empty text safer). Everything else matches the brief, the global constraints, and spec sections 2, 3 and 6.

Evidence: the scratch mutant and the probe output are in $D/t5-spec/t5-spec.log. The live worktree was not touched (`git status --porcelain` is empty).
