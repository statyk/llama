### Finding Verdicts

All mutants were run independently in a scratch copy of 3aa6d279 (`git archive | tar -x`), from an empty cwd, with PYTHONPATH shadowing. `emcee.__file__` and `herder.__file__` resolved inside the copy. The scratch baseline is 1021 passed, 1 deselected. Predictions were written to final-rerev.log before any mutant ran. After every mutant the file was restored and the suite re-run green.

- **I1: ADDRESSED.** Tests: `packages/emcee/tests/test_audio.py:952` `test_script_paragraph_breaks_reach_the_packer` (at the `_synthesize_dj_audio` level, ceiling 110, `set_intros={}`, asserts `speech.calls == [PX, PY]`) and `packages/emcee/tests/test_say_cmd.py:161` `test_say_keeps_script_paragraph_breaks` (`chunk_chars=110`). `test_audio.py:197` asserts the fixture discriminates: plain packing does not give `[PX, PY]`.
  - Predicted: both tests fail under M23. Observed: M23 (`speech_text.py:67` -> `" ".join(text.split())`) gave exactly those 2 failures.
  - A second collapse mutant, M23b (`re.sub(r"\s{2,}", " ", text)`), also gave exactly those 2 failures.
- **M1: ADDRESSED.** Test: `test_audio.py:196` `test_plan_chunks_paragraph_break_forms_split_where_packing_would_not`. It runs separators `\n\n`, `\r\n\r\n`, `\n \n`, `\n\n\n` and `\r\n \r\n` at ceiling 110 and asserts no `\r` in any chunk.
  - Predicted: fails under M8. Observed: M8 (`audio.py:133` split on `r"\n\n"`) killed it.
  - M8b (split on `r"\n[ \t]*\n"`, no `\r` handling) also killed it.
  - A per-separator probe under M8 shows `\r\n\r\n`, `\n \n` and `\r\n \r\n` each discriminate on their own.
  - A strip-only normalisation mutant leaves `\r` in the chunks on both CRLF separators, so the no-`\r` assertion is live too.
  - The old `test_plan_chunks_crlf_breaks_and_no_carriage_returns` (line 188) is kept. It is still vacuous, but harmless.
- **M2: ADDRESSED.** `test_say_cmd.py:150` now uses an 8-sentence passage, asserts it is longer than 250 characters, and asserts a single call. Predicted and observed: M11 (`cli.py:736` `enabled=True`) kills it.
- **M3: ADDRESSED.** `packages/emcee/src/emcee/tts/room_tone.py:85` now reads `np.clip(np.rint(out), -32768, 32767).astype("<i2")`, and `ROOM_TONE_VERSION` stays "v1".
  - The pin is `packages/emcee/tests/test_room_tone.py:194`. Pool frames alternate +3/-3, so the crossfades sweep through zero. The implementer measured a 40-sample zero run under truncation and 20 under rounding; the test's threshold is 24.
  - Predicted and observed: reverting `np.rint` fails exactly this test.
- **M5: ADDRESSED.** Comment-only edits:
  - `tts/loudness.py:3` "the sentence chunks" -> "the chunks".
  - `tts/provider.py:79` "concatenate sentences" -> "concatenate chunks".
  - The `_chunked_pcm` loop-variable names stay, per the Task 8 ruling.

**Strict path untouched (confirmed from the diff's file list).** The only production files changed are `room_tone.py` (one line), `loudness.py` (a docstring) and `provider.py` (a comment). The diff does not touch `audio.py` (`_locate_block`, `_narrow_chunk`/`_chunked_pcm` narrowing and fallback, `_render_key`), `process.py` or `speech_text.py`. So the content-filter recovery path and the cache-key formula are byte-identical to 99a9e6da.

**Process slips** (none affects the final state):
1. Commit 278c1757 was made with a failing test, `test_script_paragraph_breaks_reach_the_packer`: `make_notes`' default `set_intros` were also sent. That breaks mandate 4 (commit only green states). The implementer disclosed it and fixed it in 3aa6d279.
2. The implementer's log shows no scratch-copy creation and no proof of `emcee.__file__` shadowing for its mutants. Its "1 file changed" lines are `git diff --stat` output, and it reports "restored, status clean". Both suggest the mutants may have been applied in the live worktree, against mandate 5.
   - I cannot confirm this either way. The live worktree is clean at 3aa6d279 now.
   - My independent scratch-copy re-run reproduces every result the implementer claimed, so the evidence stands regardless.

### New Breakage in the Fix Diff

None. Suite at 3aa6d279 (scratch copy): emcee 1021 passed, 1 deselected.

- **Cosmetic:** `test_audio.py:42` adds `from emcee.config import Chunking` as a second line beside line 34's `from emcee.config import EmceeConfig, TTSConfig`. The existing `from emcee.config import Chunking as _Chunking` alias at line 992 is still used (lines 1045-1112). The diff renamed four `_Chunking(...)` call sites to `Chunking(...)`, which is unneeded churn, and the file now uses two names for one class. No functional effect.

### Out-of-Scope Observations

- **Stale room-tone clips under the same key.** The rounding changes room-tone output by at most ±1 LSB while the cache key keeps `tone=v1`. Any clip rendered with room tone on by a pre-fix build of this branch (for example the listening harness, if it wrote into a real `dj-audio/` cache) would be served stale. The difference is inaudible, and the final review ruled to keep v1 because nothing has shipped. If the upcoming listening check reuses an existing cache, use `--force` or a fresh station root to hear post-fix audio.
- M4 (the silent fallback) and M6 (the boundary-length abbreviation suffix) remain deferred, as the final review triaged them.

### Verdict: all findings addressed
