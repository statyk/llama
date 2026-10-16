# Task 9 report
Status: DONE. Commit: see `git log -1` (docs: profile moves, artist rules, the run plan, and the recorded dj_audio shape).

Implemented: llama `DJAudioTTS` + `DJAudio` optional fields (profile, profile_source, tts); new test in test_the_cut.py; transmitter station.py docstring only; docs/station-brief.md, README.md, CLAUDE.md, docs/playout-incident-runbook.md per brief. Extra in-scope fixes: emcee models.py docstring "shape-identical" -> "shape-compatible (llama's copy carries the newer fields as optional)"; CLAUDE.md `resolve_assignment` sentence now says resolve_voicing / effective profile.

TDD: RED `./.venv/bin/python -m pytest packages/llama/tests/test_the_cut.py -q` -> 1 failed (AssertionError, round trip dropped fields); GREEN after model change -> 9 passed.
Full suite: `./.venv/bin/python -m pytest -q` -> 3137 passed, 1 skipped, 8 deselected.
Debian-12 docker script skipped (docstring-only change).
Brief vs code: checked run/move CLI wording (Proceed? [y/N], --yes, exit 1 with no TTY, skip message, --delivered/--clear/--list, resolve_voicing, effective_profile, DJAudioBlock) against cli.py/process.py/station.py; no disagreements. Minor: README says "emcee run --dry-run ... never asks"; matches code. README line about "a missing one does too while any package was voiced under a move" taken from brief, consistent with cli require_present.
Concerns: none.

## Fix round 1
Changes (docs only): CLAUDE.md emcee-run bullet (~l.108-110): `--profile`/`--assigned` now select by EFFECTIVE profile (move > artist rule > llama's); "only problem is missing track audio" reworded to "a pending package with missing track audio is skipped ..., whatever else is wrong with it". CLAUDE.md ~l.216: `[assign]` "keyed off the effective profile (source.profile unless a move or [assign.artists] rule overrides it)". README ~l.316: parenthetical pointing at "Moving shows between profiles". README had no missing-audio claim.
Verified against cli.py: help text 412-417 (effective profile, move/rule counts); `if status.missing_tracks:` skip at ~487 sits after the ready check and before dry-run/voicing, so any pending package with missing tracks is skipped.
Command: `./.venv/bin/python -m pytest -q` -> all passed (see log).
