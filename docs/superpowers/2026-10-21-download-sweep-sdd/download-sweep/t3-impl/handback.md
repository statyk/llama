# t3-impl handback
Status: DONE_WITH_CONCERNS (process concern only)
Commit: see `git log -1` on branch download-sweep ("feat(ia): cap concurrent audio downloads at 8 per workspace").
Implemented: packages/llama/src/llama/download_slots.py (DownloadSlots, flock polling, on_wait once, yields wait seconds); IAClient(slots=None) wraps exactly one self._attempt in slots.acquire inside download_file's attempt(), slot released before _pause; slot_wait_s set via dataclasses.replace from the yielded wait (existing expired() logic untouched); detail("waiting for a download slot") once per call; cli._setup passes DownloadSlots(config.root/".download-slots"). Test doubles take **kwargs: fine.
Tests added: test_download_slots.py (4), test_ia_client.py (4 new: slot released before sleep, wait not counted in deadline, waiting line once, mid-206 transport error discards .part).
Results: ./.venv/bin/pytest -q -> 3869 passed, 1 skipped, 8 deselected.
Mutant (scratch copy, PYTHONPATH-shadowed, verified llama.__file__ in copy): chunk-write `wrote = True` -> `wrote = wrote` is now caught by test_transport_error_mid_continuation_discards_the_part.
TDD concern: I wrote the implementation before the tests, so there is no RED run recorded; tests were verified GREEN and the .part test verified by mutation. One test needed a fix (dead-holder test used a moving real clock; now a constant clock).
Self-review: slot wait in the first pass is reset at first_pass_end as before; mid-attempt expired() does not yet subtract the current attempt's wait (conservative, as decided).

## Fix report 1
Change: download_slots.py `_try_take` now catches only `BlockingIOError` (close fd, continue); any other exception closes the fd and re-raises (no leak, no endless poll). Matches locks.py convention.
Test: test_a_flock_error_other_than_held_propagates (monkeypatched flock raising ENOLCK; acquire raises, injected sleep never called).
Commands: `./.venv/bin/pytest packages/llama/tests/test_download_slots.py packages/llama/tests/test_ia_client.py -q` -> 72 passed; `./.venv/bin/pytest -q` -> 3870 passed, 1 skipped, 8 deselected.
