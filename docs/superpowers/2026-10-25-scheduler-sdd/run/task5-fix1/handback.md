# task5-fix1 handback
Status: DONE. Command: ./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q -> 663 passed, 1 skipped.
Tests written first; RED (before impl, full run): 3 failed / 660 passed: test_announcements_notes_a_missing_interstitials_folder, test_relative_interstitials_dir_raises_config_error_on_load (test_config), test_relative_interstitials_dir_is_a_config_error (test_interstitials). The other new tests (live clock no last-good copy, invalid live clock note, --clock bad exits 1, OSError skips one file, directory named id-x.mp3, needed() span bound) pass on current behaviour; they pin surviving mutants (I did not re-run mutants).
1. test_cli: live-clock invocation without --clock, clock at <TRANSMITTER_ROOT>/clock.toml, asserts listing and no clock.last-good.toml; invalid live clock pins `note:`.
2. InterstitialsConfig.dir validator rejects relative paths (ConfigError on load via load_config).
3. scan: one p.stat() for S_ISREG/size/mtime; key and sizes from station.file_set_key_and_sizes (which stats again internally; meta sizes now come from it, consistent with the key). Two stats per clip, not three.
4. Tests added as listed. 5. announcements prints one stderr `note: no interstitials folder (...)` when folder is None or not a dir; scan stays quiet.
