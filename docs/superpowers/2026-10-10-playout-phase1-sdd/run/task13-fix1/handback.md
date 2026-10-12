Status: DONE. Commit: 8ce9aed fix(transmitter): fallback upload checks epoch before any PUT; returns whether horizon was written
IMPORTANT: check_epoch(state, p.epoch) now runs right after load_publish_state, before any PUT (test written first, red; asserts PublishError, puts()==[], no local version recorded).
MINOR 1: exact Cache-Control asserted per key (segments, notice, index.json immutable; horizon no-store).
MINOR 2: upload_fallback returns bool (True horizon written; False deferred by high-water rule or no horizon); docstring updated; asserted in branch tests.
Gates: 3.14 repo 2410 passed; 3.11 transmitter 261 passed. Debian-12 not rerun (per instruction).
