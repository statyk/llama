# t14-fix1 (commit 48dd265)
IMPORTANT 1: message now "a clone reference (the house [tts] voice_clone, a presenter's voice_clone, or say --clone) resolves to the elevenlabs backend"; substring kept. Test: test_tts.py::test_factory_elevenlabs_clone_error_names_the_house_voice_clone.
M1: test_transcribe_declined_leaves_the_file_untouched asserts deletes. M2: unpinned show pinned exactly ("Roy  (male)  voice=roy-preset\ncharacter:\nx\n"). M4: exit_code==0 added.
Command: ./.venv/bin/pytest -q -> 2900 passed, 1 skipped, 8 deselected (covering four files: 111 passed).
