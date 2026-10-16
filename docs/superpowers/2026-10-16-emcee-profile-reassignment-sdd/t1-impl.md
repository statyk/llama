# t1-impl report
Status: DONE. Commit ba15aa4 "feat(emcee): [assign.artists] rules with loose artist-name matching".
Implemented: emcee/artists.py normalize_artist; config.py ArtistRule + AssignConfig.artists (shorthand before-validator, after-validator for empty key / duplicate normalized key / empty from / missing profile entry); DEFAULT_CONFIG_TOML block; tests per brief (+ "[assign.artists]" marker).
RED: `./.venv/bin/python -m pytest packages/emcee/tests/test_artists.py packages/emcee/tests/test_config.py -q` -> ImportError cannot import name 'ArtistRule' (module artists absent), collection errors, as expected.
GREEN: same command -> 79 passed. Full: `./.venv/bin/python -m pytest -q` -> 2976 passed, 1 skipped, 8 deselected (baseline 2953 + 23 new).
Files: packages/emcee/src/emcee/artists.py (new), config.py, tests/test_artists.py (new), tests/test_config.py.
Self-review: ArtistRule sets model_config = ConfigDict(populate_by_name=True, extra="forbid"); extra="forbid" is redundant with the base (a tidy sed failed on BSD sed; left as is, harmless). Existing warnings (os.fork) pre-existing.
Concerns: none.
