# t5-fix1: DONE
Commit f105fb96 test(emcee): pin collapse-before-locate with a mid-sentence wrap.
Test change (tests/test_audio.py only): the blocked half of test_unchunked_collapses_whitespace_before_send_and_locate uses a text with a wrap mid-sentence ("...in the\nspring...", "long\njam"), asserts >1 calls, no "\n" in any call and none in ei.value.text. Removed unused monkeypatch param from _key.
Suite: ./.venv/bin/python -m pytest packages/emcee -q -> 1004 passed, 1 skipped, 1 deselected.
Mutation (predicted the strengthened test fails; logged first): render_speech_mp3 collapses text for _render but passes the original to _locate_block. Observed: exactly that test failed (1 failed, 1003 passed). Restored with git checkout; porcelain clean.
