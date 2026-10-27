# Task 4 handback: DONE
Commit 6623bae5 refactor(emcee): one required chunking argument; [tts] chunk_chars and room_tone
Tests: ./.venv/bin/python -m pytest packages/emcee -q -> 992 passed, 1 deselected. No existing assertion changed; only call args and fake signatures (test_recording/test_run_cmd fakes: chunk=False -> chunking=None).
Implemented: Chunking dataclass above TTSConfig; chunk_chars StrictInt 50-1000 (250), room_tone bool; TTSConfig.chunking(enabled=); required kw-only `chunking` through render_speech_mp3, _render, _segment_pcm, _synthesize_dj_audio, _chunked_pcm/_synthesize_chunked (Chunking, non-None); process.py and cli.py say pass config.tts.chunking(enabled=...). Cache key still chunk={chunking is not None}; behaviour unchanged (_chunked_pcm ignores ceiling/room_tone). Template comments + [tts] chunk comment reworded. helpers: CHUNKED, SENTENCES. New tests in test_config.py and test_audio.py (test_chunking_has_no_default).
TDD note: I implemented before running the new tests red (did not capture a RED run); the mutations below demonstrate the tests bite.
Mutations (predictions written to log first; first attempt used BSD sed which did not apply, runs discarded and redone via python):
A: render_speech_mp3 `chunking: Chunking | None = None` -> predicted test_chunking_has_no_default; observed exactly that (1 failed, 991 passed). Restored.
B: `chunk_chars: StrictInt` -> `int` -> predicted ...rejects_non_strict_ints...["250"]; observed that plus [250.0] and test_chunk_chars_bad_value_in_config_toml_is_a_load_error (3 failed). Restored; git status clean.
No background processes left running.
