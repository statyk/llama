# t15-fix1
IMPORTANT 1: README item 9 now has the pre-downgrade config steps (remove [tts.mlx_audio]/[tts.verify]/[tts.voxtral]/[tts.elevenlabs]; hosted key back to [tts] api_key or env; restore [tts] backend and drop voice_clone_text if house moved; pins harmless).
Minors 1-7 all done (README: shape sentence exception, dropped stale clause, "points you there", "(see Memory, item 6)", trailing space removed; CLAUDE.md: ~2.6 s, three long lines re-wrapped, wording unchanged).
Test: ./.venv/bin/pytest -q -> 2900 passed, 1 skipped, 8 deselected.
