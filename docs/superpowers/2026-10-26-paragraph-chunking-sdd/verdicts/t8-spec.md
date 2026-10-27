# Task 8 spec-compliance review (675d16e5..6d964b94)

### Spec Compliance
- ✅ Spec compliant. All five files the brief lists have their hunks: `cli.py` (`--chunk` help, the CHUNKING paragraph in `say`), `tts/quality.py`, `audio.py` (section header, `_chunked_pcm`, `_synthesize_chunked`, `render_speech_mp3`, `_synthesize_dj_audio`), the repo-root `README.md` and `CLAUDE.md`. `config.py` (`timeout_s`, "per chunk request", in both the field and the template) is the brief's Step 1 `timeout_s` item.
- The orchestrator's extra wording items are all present: the comment on the chunked `raise` is reworded and the `render_speech_mp3` docstring now covers chunked narrowing and fallback. `_synthesize_dj_audio` now names `TTSConfig.chunking(...)` with chunk/chunk_chars/room_tone, plus the planned-chunk digest and the tone key. The `_synthesize_chunked` and `_chunked_pcm` docstrings describe packed chunks. In CLAUDE.md, the "re-run with `[tts] chunk = true`" sentence is now limited to `chunk = false`, and it says the chunked path narrows and falls back.
- **No executable code changed.** I read every `+`/`-` line of the `.py` diff (`git diff 675d16e5 6d964b94 -- '*.py'`). Each one is a comment, a docstring or the `--chunk` help string literal. There are no tests in the diff.
- **Every changed sentence checked against the code at 6d964b94:**
  - Packing follows paragraphs up to `chunk_chars`, default 250, and never ends inside a sentence: `plan_chunks` at audio.py:120-150 and spec §2.3.
  - The 50-1000 range and the defaults are right: config.py:117-118.
  - `say` reads `chunk_chars` and `room_tone`: cli.py:736 calls `config.tts.chunking(enabled=chunk)`. `process.py:307` builds it the same way, so "built by `TTSConfig.chunking(...)`" is accurate.
  - Room tone fills exact-zero runs on the chunked path only, with the clip's own quietest frames: audio.py:249-250 and room_tone.py.
  - Narrowing raises the refused sentence or keeps the passing takes, and a one-piece chunk is re-raised: `_narrow_chunk`, audio.py:188-207.
  - The cache-key digest and the tone key: `_render_key`, audio.py:383-396.
  - The scriptwriter writes paragraphs: prompts/scriptwrite.md:40-41 and the `\n` unescape in scriptwrite.py:198.
  - The mlx `timeout_s` is a per-request timeout, now per chunk.
  - Spec §5 says "`render_speech_mp3`'s chunked re-raise stays as is". Its behaviour is unchanged; only the comment changed, as the orchestrator asked.
- **Grep run myself** (`grep -rn -i "sentence-by-sentence\|sentence by sentence\|per sentence\|each sentence\|across sentences\|sentence request" packages/emcee/src README.md CLAUDE.md`). None of the remaining hits describes the chunked synthesis path:
  - audio.py:194 is `_narrow_chunk`'s "across sentences", which is correct.
  - audio.py:296 is `_locate_block`, correctly left alone.
  - tts/verify.py:6 ("per sentence" ASR tolerance) is unrelated.
  - prompts/scriptwrite.md:4 is unrelated.
  - CLAUDE.md:956 is now qualified "with `[tts] chunk = false`", which is correct.
  - A wider sweep for "sentence" in README/CLAUDE found only README:682. That is the historical mlx memory measurement ("6.6-7.0 GB between sentences"), a record of a past measurement and not a behaviour description, so leaving it is fine.
- ⚠️ Cannot verify from the diff alone: the config template and `TTSConfig` field comments for `chunk`, `chunk_chars` and `room_tone` (config.py:113-118, 355-369), and the template test markers. Those landed in earlier tasks. I checked them as they stand at HEAD: accurate, and `test_default_config_template_mentions_every_section` lists `chunk_chars` and `room_tone` (test_config.py:274). The Acceptance "Docs and templates" bullet is therefore met across the branch.

### Issues (spec only)
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **The tone key is described as unconditional** (audio.py:417-420, the `_synthesize_dj_audio` docstring). It says the key "also carries the planned-chunk digest and `tone=<ROOM_TONE_VERSION>`". The code adds `tone=` only when `chunking.room_tone` is on (audio.py:394; spec §6 "When `room_tone` is on"). Suggest "...the planned-chunk digest and, when room_tone is on, `tone=<ROOM_TONE_VERSION>`". The "re-renders the affected clips" clause is still true, since toggling room_tone changes the key either way.
2. **The retried unit in quality.py:9** reads "the chunk when chunked". On a blocked multi-sentence chunk, each narrowing sentence take is also a separate `synthesize` call, and so its own quality-retried and verified unit (spec §5 Known limits, first bullet). Suggest an optional "(or each sentence take when a blocked chunk is narrowed)".
3. **Rich markup swallows `[tts]` in the new help text.** This was found by rendering `say --help` through `CliRunner`, and the file already had the defect. The new strings render as "up to  chunk_chars" and "(` room_tone`)": the `[tts]` disappears. The same pattern already existed in the file ("as ` chunk` does", "default  bed_gain_db"), so it is not introduced by this task, and the text is still readable. Escaping as `\[tts]` would fix every instance. That belongs to a follow-up or the code-quality reviewer, not this wording task.

### Assessment
**Spec compliance:** Approved

The wording is plain and matches the brief's Step 2 wording almost exactly. The `render_speech_mp3` docstring and the CLAUDE.md block sentence describe the narrow-then-fall-back behaviour precisely. The rest of each edit stays within what the code does. On the implementer's report: no mutations were required for a docs-only task. The transmitter failure it reports (`test_schedule_lists_missing_announcement_audio`) is the wall-clock test the orchestrator already reproduced on the base commit. I did not run the suite. The only command I ran was a read-only `CliRunner` render of `emcee say --help` in the live venv (`emcee.__file__` confirmed inside the worktree).
