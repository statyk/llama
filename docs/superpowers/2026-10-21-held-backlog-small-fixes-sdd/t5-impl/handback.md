# t5-impl handback
Status: DONE. Commit: see `git log -1` (feat(redo): every redo is a restoring unit...).
Implemented: cli._redo_show (show_unit(entry.ws, None) wrapper) + cli._redo_show_locked (no lock; reads provenance.json itself; ShowChanged "the show was removed; nothing changed" if absent and entry.provenance was set, else the old LlamaError); _execute._process except tuple now (TaskFailed, HerderError, LlamaError) below the RateLimited arm; helpers.packaged_gd73; CLAUDE.md two sentences.
RED: `./.venv/bin/python -m pytest packages/llama/tests/test_redo_cmd.py packages/llama/tests/test_pace_loop.py packages/llama/tests/test_reapply.py -q -k "restores or leftover or removed_while or inside_the_show_lock or refusing_its_overrides or refused_overrides"` -> 7 failed, 2 passed (the two passes are the (pin) tests), as the brief predicted.
GREEN: same files, 187 passed; full suite `./.venv/bin/python -m pytest -q` -> 4014 passed, 1 skipped, 8 deselected.
Verified: IAError(LlamaError), IADownloadError(IAError) in ia_client.py; test_pipeline.fake_providers/FakeIA exist; no existing test changed outcome.
Concerns: none. Brief's `import shutil` etc. added; test_reapply import added as `from llama.models import Overrides, Briefing, ...`.
