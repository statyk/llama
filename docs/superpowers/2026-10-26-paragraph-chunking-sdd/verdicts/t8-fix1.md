t8-fix1 DONE. See commit below. I1 fixed (\\[tts] in --chunk help and say docstring, new text only); rendered `say --help` lines:
 chunks (up to [tts] chunk_chars)
 `[tts] chunk_chars` and never end inside a sentence; exact-silence gaps
 are filled with the clip's own room tone (`[tts] room_tone`). Chunked and
 bedded renders are loudness-normalized; `--no-chunk` without a bed ships
Minors done: _synthesize_dj_audio key docs (chunks=<digest>, tone= only when room_tone on, via _render_key), quality.py wording, say docstring reflow, README memory caveat.
Tests: packages/emcee 1017 passed.
