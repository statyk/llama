# t2-impl handback
Status: DONE. Commit: see `git log -1` on held-backlog-tier1 (feat(replay): cache-only clients...).
Implemented per brief: setlistfm.cache_key (client uses it), replay.py (CacheMiss, CacheOnlyIA, CacheOnlySetlistFM, input_digests, setlistfm_configured, setlistfm_client, config_fingerprint, code_identity), capture_fixture.py --from-cache [--cache DIR] with main(argv).
Rulings applied: config_fingerprint uses "audio_format": config.audio_format; setlistfm test uses make(tmp_path, handler).
TDD: RED = ModuleNotFoundError llama.replay on collection; GREEN after impl. Full suite: ./.venv/bin/python -m pytest -q -> 3171 passed, 1 skipped, 8 deselected (+8 tests).
Files: packages/llama/src/llama/{setlistfm,replay}.py, scripts/capture_fixture.py, tests test_replay.py, test_setlistfm.py, scripts/test_capture_fixture.py.
Deviation: capture_fixture's slim projection factored into _slim() shared by both paths (same shape). Not exercised against real ~/.llama cache. Concerns: none.
