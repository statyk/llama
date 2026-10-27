# Task 5 handback: DONE
Commit 21db2638 feat(emcee): voice chunks packed by paragraph at [tts] chunk_chars, with room tone.
Tests: ./.venv/bin/python -m pytest packages/emcee -q -> 1004 passed, 1 skipped (test_render_chunked_block_needs_no_locating, "rewritten in Task 6"), 1 deselected.

Implemented (audio.py): _chunked_pcm uses plan_chunks(text, chunking.ceiling), neighbour chunks as context, per-chunk normalize, 180ms joins, fill_room_tone(seed_text=text) last when room_tone. New _CHUNK_SEP="\x1f" and _render_key (unchunked string byte-identical; chunked adds "\nchunks="+digest[:16] computed outside f-string, plus "\ntone=<ROOM_TONE_VERSION>" when room_tone); _synthesize_dj_audio uses it. render_speech_mp3 collapses whitespace when chunking is None, before _render and _locate_block.

TDD RED: before implementing, 13 failed / 991 passed (all new tests + updated expected key; log has output).
GREEN: 1004 passed.

Ruling A: today's _split_sentences("") is [""] (one empty call); plan_chunks("") is also [""], so empty text is unchanged (pinned by test_chunked_empty_text_is_one_call_as_before). Trailing blank paragraphs give no empty call (test_chunked_trailing_blank_paragraph_makes_no_empty_call).
Ruling B: test_process_package_forwards_configured_chunk_chars_and_room_tone (test_audio.py) and test_say_forwards_chunk_chars_and_room_tone (test_say_cmd.py); chunk_chars=50 gives 2 calls vs 1 at default; room_tone=false means fill_room_tone not called. test_say_cmd._write_config now writes bools lowercase (TOML).
Existing tests changed: multi_sentence/neighbor_context/render_speech_mp3_chunked/normalizes_each_sentence use SENTENCES; test_chunk_true_synthesizes_via_chunked_path now expects 3 calls; say default test renamed test_say_chunks_by_packed_chunks_by_default, asserts one call; _expected_key gained chunks=/tone=. New: test_say_hard_wrapped_file_is_one_paragraph and the brief's list.

Mutations (predictions logged before running; each restored via git checkout, porcelain clean):
A drop the chunks= line from _render_key -> predicted test_cache_key_chunked_changes_with_planned_chunks; observed it plus test_cache_key_chunked_carries_the_loudness_version and test_cache_key_tone_part failing (3).
B `if chunking.room_tone:` -> `if True:` -> predicted test_room_tone_applied_only_when_enabled; observed that plus both forwarding tests (3).
C removed the collapse at top of render_speech_mp3, collapsing only inside the except before _locate_block -> predicted test_unchunked_collapses_whitespace_before_send_and_locate; observed exactly that (1).
D `tone={ROOM_TONE_VERSION}` -> literal `tone=v1` -> predicted test_cache_key_changes_with_room_tone_version; observed exactly that (1).
E TTSConfig.chunking returns Chunking(250, True) -> predicted the two forwarding tests; observed both plus test_config.py::test_tts_chunking_helper (3).
Concerns: none. No background processes.
