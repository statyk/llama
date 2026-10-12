Task 5 fix1: DONE.
Changed station.py: evaluate() now wraps _evaluate() and maps OSError/RuntimeError/UnicodeDecodeError to Ineligible(slug, ("changing: <exc>",)); require_root maps OSError on is_dir/marker check to StationRootError naming the root.
Tests added (6): m3u read FileNotFoundError, invalid-UTF-8 m3u, ESTALE on exists, symlink-loop RuntimeError, require_root ESTALE, scan survives one vanishing package. RED: 6 failed before fix.
Results: 3.14 transmitter 86 passed; 3.11 transmitter 86 passed; full repo 2235 passed, 7 deselected.
