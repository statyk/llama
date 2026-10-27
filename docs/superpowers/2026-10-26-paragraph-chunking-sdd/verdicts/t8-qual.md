Spec compliance: not judged here (separate seat). Code-quality review of 6d964b94 (docs, help text and wording only; base 675d16e5).

### Strengths
- Every changed sentence checks out against the code at 6d964b94. `audio.py:47-53` header, `_synthesize_chunked` (`audio.py:256-262`) and the README/CLAUDE.md packing sentences match `plan_chunks` (`audio.py:121-160`: paragraphs, greedy to the ceiling, a lone over-ceiling sentence stays whole). "50-1000, default 250" matches `config.py:117` (`StrictInt`, `ge=50, le=1000`). "Room tone default on" matches `config.py:118`. The fallback wording (CLAUDE.md:952-956, `render_speech_mp3` docstring `audio.py:353-358`, raise comment `audio.py:366`) matches `_narrow_chunk` (`audio.py:188-207`): it raises the first refused piece, else returns the passing takes, and re-raises a one-piece chunk.
- CLAUDE.md:956 now limits "re-run with `[tts] chunk = true`" to `chunk = false`. That fixes a statement that would otherwise have become false (spec §5(b)).
- `config.py:82,348` "per chunk request" and `quality.py:9` "the chunk when chunked" are accurate, minimal edits.
- The config template (`config.py:357-369`), the README config block (`README.md:368-370`) and the `say` paragraph (`README.md:499-505`) all say the same thing with the same numbers.
- Leftover-wording sweep (check I ran): grep at HEAD for sentence-by-sentence / per sentence / per-sentence / each sentence / across sentences / sentence request / sentence-level / between sentences / sentence/segment over `packages/emcee/src`, `README.md` and `CLAUDE.md`. Remaining hits:
  - `audio.py:194` and `:296` correctly describe `_narrow_chunk` and `_locate_block`.
  - `verify.py:6` and `scriptwrite.md:4` are unrelated.
  - `CLAUDE.md:956` is now correctly scoped to `chunk = false`.
  - `README.md:682` is a dated measurement (Minor 3).
  No contradiction is left in the touched files.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. `packages/emcee/src/emcee/cli.py:672-673` (the `--chunk` help) and `cli.py:701-704` (the `say` docstring CHUNKING paragraph): the new `[tts] chunk_chars` / `[tts] room_tone` references do not render. Typer 0.27.3 runs help through rich markup, so `[tts]` is swallowed as a tag. I rendered `emcee say --help` from the app object at HEAD (output in t8-qual.log). It shows "Synthesize in paragraph-packed chunks (up to  chunk_chars)", "up to ` chunk_chars`" and "(` room_tone`)". A user reading `--help` cannot tell these are `[tts]` config keys, and the fix needs to land wherever the new key is named.
   - The defect is pre-existing and file-wide. The same file renders "the house ` voice`", "` bed`" and "`` backend", with about 8 option helps and several docstring spots affected. This change adds three more instances, in the one place the brief asks the help to describe the new key.
   - Fix: in the new text, write `\[tts]` (rich escape; in a non-raw string, `"\\[tts]"`). I checked this in a scratch typer script: `r"\[tts] chunk_chars"` renders as `[tts] chunk_chars`. File the file-wide escape (or `rich_markup_mode=None` on the Typers) as a separate follow-up rather than widening this docs task.

#### Minor (Nice to Have)
1. `audio.py:420` is a 130-character line. The appended sentence was not reflowed into the docstring, whose other lines sit under 100.
2. `audio.py:417-420`: "the 'chunk' part of the key also carries the planned-chunk digest and `tone=`" is not quite right. `_render_key` (`audio.py:383-396`) appends `chunks=` and `tone=` after the bed and loud parts, not inside `chunk=`. "Changing chunk_chars ... re-renders the affected clips" is right, but only clips whose plan changes are re-rendered, as `_render_key`'s own docstring says. Pointing at `_render_key` would be more precise than restating it.
3. `README.md:679-683`: the mlx memory figure ("6.6-7.0 GB between sentences ... spikes of 10-12 GB") was measured under one-sentence chunks. With 250-character chunks each generation is longer, so the peak may differ, and the acceptance step already plans to re-check the mlx memory peak. Add a "(measured with sentence-sized chunks)" qualifier, or update it after acceptance.
4. `cli.py:704-705`: the reflow leaves the short line "bedded renders are loudness-normalized;". Typer keeps docstring line breaks, so the ragged line shows in `--help`.
5. `quality.py:9` "the chunk when chunked" skips the narrowing case: a refused chunk's sentence takes are each a separate retried unit (`_narrow_chunk` calls `speech.synthesize` per piece). Optional: "the chunk (or, when a refused chunk is narrowed, each sentence) when chunked".

Implementer report: claims are accurate against the diff (6 files, wording only, config.py edits included). No tests were changed and the brief asked for no mutations, so the mutation-prediction rule does not apply. The full-suite transmitter failure is out of scope, as the dispatch notes.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The wording is accurate to the code and consistent across CLAUDE.md, README, the config template and the docstrings, and no stale sentence-level claims are left. But the new user-facing `--help` text loses `[tts]` to rich markup and names a bare `chunk_chars`, so the help does not render correctly. Escape the three new instances; the file-wide pre-existing cases are a follow-up.
