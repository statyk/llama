Status: DONE
Commit: 105b0b7 feat(transmitter): fallback loop and off-air notice render + upload
Files: packages/transmitter/src/transmitter/fallback.py, packages/transmitter/tests_transmitter/test_fallback.py
Tests: 10 in test_fallback (brief's 6 + whole-ADTS-frame test x2 params + high_water skip + high_water==last rewrite).
Gates: 3.14 repo 2409 passed; 3.11 transmitter 260 passed; debian12 script 260 passed (ffmpeg 5.1.9-0+deb12u1, Python 3.11.2). transmitter.__file__ resolves in worktree.
Rulings: (1) upload_fallback skips horizon PUT when high_water > last (logs; version recorded locally; state never saved/moved); both branches tested. (2) _encode_exact runs require_station_format on every frame (plus exact count); test checks each segment/notice tiles into exactly 441 whole station-format frames, with and without notice. (3) E-based helpers, unused imports dropped (json, Path import kept as used).
Brief-vs-code differences: none needing change; brief's listing used as written (state/publish APIs matched).
Concerns: none.
