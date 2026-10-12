Task 5 fix2: DONE.
Changes (station.py): scan guards entry.is_dir()/manifest exists per entry (OSError -> skipped Ineligible "changing: ..."), iterdir OSError -> StationRootError; RuntimeError narrowed to _inside's resolve() (converted to OSError ELOOP), evaluate wrapper catches OSError only; UnicodeDecodeError on m3u -> "unreadable broadcast.m3u: ...".
Tests: 4 new/changed RED (invalid-utf8 reason, manifest-exists ESTALE, is_dir ESTALE in scan, listing failure); require_root is_dir arm test added (already passed, pins it).
Results: 3.14 transmitter 90 passed; 3.11 90 passed; full repo 2239 passed, 7 deselected.
