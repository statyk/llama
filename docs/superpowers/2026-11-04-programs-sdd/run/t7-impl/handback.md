Status: DONE_WITH_CONCERNS
Commit: c4a1916f emcee: record the program title in dj_audio; llama's DJAudio copy carries it
Implemented: DJAudioBlock.title (last field, always serialized), process_package passes title=voicing.title, llama DJAudio.title, docs line in packages/emcee/CLAUDE.md, scripts/test_dj_audio_handshake.py, 3 emcee tests, 1 llama test; updated exact-dict asserts in test_process.py, test_audio.py, test_the_cut.py.
Full suite: 6726 passed, 1 skipped.
Concern: TDD RED not recorded; I wrote implementation and tests together then ran green (187 passed in focused run).
