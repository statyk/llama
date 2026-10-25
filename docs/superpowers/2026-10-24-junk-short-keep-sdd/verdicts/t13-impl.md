# t13-impl report
Status: DONE_WITH_CONCERNS

Implemented: run_package(reuse=), process_show(audio_reuse=), _redo_show_locked computes plan_reuse (delivery_path/<slug> as station) before drop_stage_artifacts and passes it (redo, fix, triage via the unit). reapply_show: discard leftover aside, plan, record audio names, try/except BaseException cleanup (delete unrecorded audio, delete a manifest differing from the recorded one, put_back, re-raise), discard_aside after the commit marker. Dry-run returns earlier, deletes nothing.

TDD: five tests written first; RED run: 5 failed, 1 passed (-k "reuses or never_reuses or leftover_aside"): redo downloads ['s.mp3','a.mp3','b.mp3'] vs ['s.mp3']; fix station downloads ['a.mp3','b.mp3'] vs []; held-then-overrule inherited old audio by name (no downloads, duration-mismatch flags); reapply failure left new audio; dry-run test failed on the non-dry aside deletion. GREEN: the three files, 247 passed.
Full suite: ./.venv/bin/python -m pytest -q -p no:cacheprovider -> 5054 passed, 1 skipped, 8 deselected.

Files: cli.py, pipeline.py, stages/package.py, reapply.py; tests helpers.py (reuse_gd73, stub_stages), test_redo_cmd.py, test_fix.py, test_reapply.py (two existing build_package fakes gained reuse=None).

Concerns:
- reapply's aside deletion + plan sit just before the first write (after needs-llm/skip/dry-run returns and fresh brief), not literally right after the still-held check; nothing writes in between, and it keeps "writes nothing" paths untouched.
- Reapply failure does not restore the old manifest dropped by drop_stage_artifacts (brief only says delete a manifest this call wrote), so a rerun after failure downloads rather than reuses.
- fix --untitled second pass (from brief) after a held first pass has no library manifest, so it pairs only the station copy; the library audio is set aside and re-downloaded.
