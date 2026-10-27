# t5-qual: Task 5 code-quality review (6623bae5..f105fb96)

Verdict: **Approved.** No Critical or Important findings; four Minor ones below.

### Strengths
- `_render_key` (audio.py:350-363) is a clean extraction. The unchunked string is built by the same expression as before, so it stays byte-identical. The chunked additions are appended only under `chunking is not None`, and the digest is computed outside the f-string with the 3.11 reason in a comment. `_synthesize_dj_audio` now has one call site for it (diff lines 211-212), so the key and the render cannot drift.
- The key and the render hash and send the same thing. `_synthesize_dj_audio` passes the same `spoken` to `_render_key` and `render_speech_mp3`. The chunked branch does not collapse text before `_render`, and `plan_chunks` collapses internally (audio.py:132), so the digest covers exactly the chunk texts the provider receives, on the bed path too (`_segment_pcm` → `_chunked_pcm`).
- The separator is injective in fact, not just by convention. `"\x1f".isspace()` is True (checked), so `plan_chunks`' `str.split()` collapse removes any U+001F from the text, and it cannot occur inside a chunk.
- Room tone is applied once, to the joined PCM, after normalization and joins (diff lines 107-110). Seeding it with the whole segment text matches the spec. The recorder test's call count would catch a per-chunk-application mutant (2 calls on a 2-chunk text).
- The unchunked collapse (diff lines 147-150) sits at the one fork point, before both `_render` and `_locate_block`. The fix round's mid-sentence wrap (`"in the\nspring"`, `"long\njam"`) is what actually distinguishes the collapse-before-locate mutant: a break after a period is split away anyway. That test is now real (test_audio.py diff lines 537-550).
- Cache-key tests are oracle-independent. `_expected_key`/`_chunk_digest` hard-code `"\x1f"` and the string layout rather than importing `_CHUNK_SEP`. `test_cache_key_tone_part` pins the exact pre-hash string with no `tone=`. `ROOM_TONE_VERSION` is monkeypatched on `emcee.audio`, where the key reads it.
- Mutation evidence is in order. Predictions are logged before the runs (t5-impl.log:302, t5-fix1.log:3), and each observed set plausibly follows from its edit: A also breaking the two exact-key tests, B also breaking both forwarding tests. Mutation E (config forwarding) goes beyond the brief.
- The fix to `_write_config` (test_say_cmd.py diff lines 588-592) writes TOML-valid lowercase booleans. The old path would have written `True`, which is invalid TOML.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **audio.py:372-373, stale cache-key docstring.** `_synthesize_dj_audio` still says the key is "text + voice + model + chunk [+ bed] [+ loud]". It now also carries the chunk digest and `tone=`. This is the key's documented formula, not "sentence" wording, so name it explicitly for Task 8's wording pass, or fix it here in one line ("... [+ loud] [+ chunks digest] [+ tone]").
2. **test_audio.py diff lines 560-565, obscure fixture paths.** `test_process_package_forwards_configured_chunk_chars_and_room_tone` builds directories from `str(len(seen)) / str(tts)`. That gives names like `0/{'chunk_chars': 50, 'room_tone': False}`, with spaces, quotes, colons and braces. It works on POSIX, but the paths are unique only by accident of the dict repr. The `(seen.append(...), pcm)[1]` lambda is also clever where a small def is plainer. Fix: give `calls()` a `name` argument and pass explicit names (`"default"`, `"c50"`), and use a named recorder like the one in `test_room_tone_applied_only_when_enabled`.
3. **test_audio.py diff line 460, mid-module aliased import.** `from emcee.config import Chunking as _Chunking` sits mid-module, and `_chunk_digest`/`_key` import `plan_chunks`/`_render_key` inside function bodies. The module already imports from `emcee.config` and `emcee.audio` at the top (test_audio.py:32-35). Add `Chunking`, `plan_chunks` and `_render_key` to those import lists.
4. **test_audio.py diff lines 491-503, recorder checks little beyond the seed.** `test_room_tone_applied_only_when_enabled`'s recorder discards `pcm`, `framerate` and `channels`. A mutant that passed one chunk's PCM, or the wrong channel count, would still pass the seed check. Optional: also record `len(pcm)` and `channels`, and assert that the length equals the returned clip's PCM length (two chunks plus one 180 ms gap) and that `channels == 1`.

### Named-risk checks (outside the diff)
- **Risk: stereo PCM with room_tone on raises.** Checked `tts/room_tone.py:32-39`: `channels != 1` returns the PCM unchanged. The fill is a no-op, not an error. Every fake-provider test also runs it on all-zero PCM, which hits the empty-pool early return (room_tone.py:60-61).
- **Risk: the unchunked collapse alters deliberate Unicode whitespace (NBSP) from `normalize_for_speech`.** Grepped speech_text.py for `\xa0`/` `/` `/`\u200x`: none emitted. The chunked path already collapses the same way (audio.py:132), so both paths agree.
- **Risk: the unchunked key goes stale after the collapse.** The spec already settled this ("Settled at the builder check": 593/593 delivered segments have no newline). Not a finding.
- **Test output.** The implementer's logs show only the expected RED/mutant failures and clean `1004 passed, 1 skipped, 1 deselected` runs. No warnings appear in the logs.

No tests or mutants were run. Nothing in the code raised a doubt that the existing runs leave open.

### Assessment

**Task quality:** Approved

**Reasoning:** `_render_key` keeps the unchunked key byte-identical, and on the chunked path it hashes exactly the chunk texts that get sent, so a stale hit cannot ship old audio for new chunking. Room tone runs once on the joined PCM behind its flag, and the unchunked collapse sits at the single fork point. The tests pin each rule with mutation evidence whose predictions were logged first. The remaining items are a stale key docstring and test-hygiene polish.
