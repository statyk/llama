# t3-impl handback
Status: DONE. Implemented `_shipped` + `_venue_changes` in scripts/replay_holds.py, `venue_changes.txt` in OUTPUT_FILES, written in compare next to packaged_exposure, summary line added.
RED: `./.venv/bin/python -m pytest scripts/test_replay_holds.py -q -k venue_changes` -> 2 failed (no venue_changes.txt).
GREEN: same file 55 passed; full suite `./.venv/bin/python -m pytest -q` -> 3988 passed, 1 skipped, 8 deselected.
Row shape verified (venue/city = {old,new} or null via _pair; state; outcome). No mismatch. Unreplayable detected as outcome == "unreplayable" (no helper existed). Brief tests used verbatim.
Note: header line "skipped N unreplayable show(s) (fields absent)" counts all unreplayable shows, changed or not.
