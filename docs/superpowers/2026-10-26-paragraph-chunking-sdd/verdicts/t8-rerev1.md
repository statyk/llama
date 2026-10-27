### Finding Verdicts

- **I1: ADDRESSED.** The two new instances are escaped: `packages/emcee/src/emcee/cli.py:672` (`--chunk` help, `"\\[tts] chunk_chars"`) and cli.py:703-704 in the `say` docstring (`\\[tts] chunk_chars`, `\\[tts] room_tone`). I rendered `emcee say --help` with the worktree interpreter (`emcee.__file__` resolves inside the worktree; CliRunner exit 0, COLUMNS=100). The docstring now shows `` `[tts] chunk_chars` `` and `` (`[tts] room_tone`) ``. The `--chunk` row shows `(up to [tts]` / `chunk_chars)`, wrapped by the table column, with the text intact. Python is correct: all three changed files compile under `-W error` with no SyntaxWarning. `"\\["` is a normal escaped backslash that yields `\[`, which rich un-escapes to `[`.
- **M1: ADDRESSED.** The new docstring at `packages/emcee/src/emcee/audio.py:418-422` matches `_render_key` (audio.py:383-395) exactly:
  - The base key is `...chunk={bool}{bed_key}{loud_key}`.
  - On the chunked path the key then gains a separate `\nchunks=<16-hex digest of plan_chunks>`.
  - `\ntone=<ROOM_TONE_VERSION>` is added only when `chunking.room_tone`.
  - The claim that only clips whose planned chunks or tone change re-render is also accurate.
  - The 130-character line is gone. The longest line in the paragraph is now 83 characters (audio.py:422). No line-length lint is configured, and the file already has 13 lines over 88.
- **M2: ADDRESSED.** `packages/emcee/src/emcee/tts/quality.py:9-10` now reads "the chunk (or, when a refused chunk is narrowed, each sentence) when chunked". I checked this against `_narrow_chunk` (audio.py:188-207): each sentence piece goes through `speech.synthesize(piece, fmt="wav")`, which is the quality-wrapped provider, so each sentence is its own retried and verified unit.
- **M3: ADDRESSED.** cli.py:703-706 is reflowed evenly; the ragged "bedded renders are loudness-normalized;" line is gone. The rendered help confirms this.
- **M4: ADDRESSED.** README.md:681-682 now includes "(measured with sentence-sized chunks)".

### New Breakage in the Fix Diff
None. The diff changes only docstrings, a help-string literal, a module docstring and README prose; no executable code is touched. The implementer reports 1017 emcee tests passing. I did not re-run the suite because no code changed.

### Out-of-Scope Observations
- Several `[tts]` references that were already in cli.py before this task are still swallowed in rendered help. For example, the `say` CHUNKING paragraph renders "as ` chunk` does for DJ clips", and the `--bed`/`--no-bed`/`--bed-gain` help is affected the same way. This is the follow-up the brief already noted as separate.
- README.md:682 leaves a short source line ("sentence-sized chunks) kept the server at"). It is only raggedness in the Markdown source and does not show when rendered.

### Verdict: all findings addressed
