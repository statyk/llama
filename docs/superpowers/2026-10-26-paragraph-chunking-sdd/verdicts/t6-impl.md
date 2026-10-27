# Task 6 handback: DONE
Commit 2cb14e34 feat(emcee): narrow a blocked packed chunk to its sentence; fall back to the passing takes
Tests: ./.venv/bin/python -m pytest packages/emcee -q -> 1012 passed, 1 deselected (baseline 1006+6 new... all green, no skips left).
RED (before impl): `-k "block or repair"` -> 6 failed (narrows, cross-sentence, bed, 3 process tests); `-k "fallback or one_piece"` -> 2 failed (fallback audio, neighbours), one_piece passed (existing behaviour, pin only).
Impl: audio.py `_narrow_chunk(chunk, speech, blocked) -> list[bytes]` + `_chunked_pcm` catches SpeechBlocked per chunk, takes loop with 180 ms between takes and chunks; neighbours never re-sent.
Context choice: narrowing calls pass NO neighbour context (previous/next_text): the brief says "alone", mirrors _locate_block, and a context-triggered refusal should not be re-fed the context. Cost: fallback takes lose cross-chunk prosody hints on ElevenLabs only.
Test edits: removed skipped test_render_chunked_block_needs_no_locating; added 6 audio tests + 2 process tests, extended repair test with `blocked: "{BLOCKED_S2}"`. Note: in the reblocked-twice test the prompt legitimately contains the whole segment, so I assert on the feedback line only (the text after "also blocked") not containing CLEAN_S1.
Mutations (predictions in t6-impl.log before running; script scratchpad mut.py; restored with git checkout, status clean each time):
A re-raise whole chunk up front: predicted narrows test; observed that first (-x), full run 8 failed incl. process blocked: assertion.
B all-pass re-synthesizes pieces (return fresh synth list): predicted cross_sentence (7 calls); observed it.
C drop one-piece guard: predicted one_piece test; observed it.
D all-pass raises whole_passage=True: predicted cross_sentence + process no_rephrase; full run 5 failed incl. both.
E truncate sentences list after a fallback chunk (`sentences = sentences[:i+1]`): predicted neighbours test; observed it.
No mutant survived. Nothing running. Concern: none.
