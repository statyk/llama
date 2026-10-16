# Task 5 handback (t5-impl)

**Status:** DONE

## Commit
- `9960cf3` feat(emcee): resolve each package once and record profile, source and TTS in dj_audio

## What was implemented (per task-5-brief.md, verbatim values)
- `models.py`: new `DJClips` (set_intros, outro), `TTSRecord` (backend, model, voice; all required), `DJAudioBlock(DJClips)` with `presenter=None` plus required default-free `profile`, `profile_source: Literal["move","artist","llama"]`, `tts: TTSRecord`.
- `audio.py`: `_synthesize_dj_audio -> DJClips`; `interleave_broadcast`/`broadcast_m3u_text` annotated `DJClips`; import and module docstring updated.
- `process.py`: module docstring replaced; `resolve_assignment(config, profile)` (effective profile, not manifest); new `Voicing` dataclass, `resolve_voicing(config, moves, manifest)` (raises `EmceeError(move_target_problem)` first), `_speech_from`, `speech_for` (signature unchanged, for `emcee say`), `speech_for_voicing`; `process_package(..., *, voicing)` uses `voicing.presenter/title`, renames the synth result `clips`, builds `DJAudioBlock` with profile/profile_source/`TTSRecord(backend=resolution.backend, model=speech.model, voice=speech.voice)`. `_repair` loop and its comment kept as-is.
- `cli.py`: imports swapped to `resolve_voicing, speech_for_voicing` and the three `manifest_*` accessors; `_process_one(config, moves, pkg, force, fresh=())` resolves once and passes `voicing=`; `run` passes `moves`; `voice_cmd` loads moves first, and calls `moves.require_present(...)` when the manifest's `profile_source == "move"`.
- `scripts/backfill_voiced_by.py`: raw-JSON update via `package_io.atomic_write` (no model round trip); docstring updated.
- `tests/helpers.py`: `voicing_for(config, pkg)`.
- Test call sites updated per Step 6 (test_process, test_audio, test_quality, test_verify, test_package_io, test_run_cmd, test_voice_cmd, test_mlx_wiring). New `tests/test_recording.py` (11 tests) and the backfill unknown-keys test, copied verbatim from the brief.

## TDD evidence
RED: `./.venv/bin/python -m pytest packages/emcee/tests/test_recording.py scripts/test_backfill_voiced_by.py -q`
```
E   ImportError: cannot import name 'DJClips' from 'emcee.models'
ERROR packages/emcee/tests/test_recording.py
```
and `./.venv/bin/python -m pytest scripts/test_backfill_voiced_by.py -q`:
```
E         Right contains 1 more item:
E         {'future_key': {'x': 1}}
FAILED scripts/test_backfill_voiced_by.py::test_apply_is_a_raw_update_that_keeps_unknown_keys
1 failed, 7 passed
```
Both exactly as the brief predicted (no DJClips yet; model round trip drops `future_key`).

GREEN:
- `./.venv/bin/python -m pytest packages/emcee/tests/test_recording.py -q` -> 11 passed
- `./.venv/bin/python -m pytest scripts/test_backfill_voiced_by.py -q` -> 8 passed
- `./.venv/bin/python -m pytest packages/emcee scripts -q` -> 893 passed, 1 deselected
- Full: `./.venv/bin/python -m pytest -q` -> **3069 passed, 1 skipped, 8 deselected** (3057 baseline + 12 new). Warnings are the pre-existing llama fork() DeprecationWarnings only.
- Step 8 grep `grep -n "resolve_assignment(config, manifest\|speech_for(config, presenter)" packages/emcee/src/emcee/cli.py` -> no output.

## Files changed
packages/emcee/src/emcee/{audio,cli,models,process}.py; packages/emcee/tests/{helpers,test_audio,test_mlx_wiring,test_package_io,test_process,test_quality,test_run_cmd,test_verify,test_voice_cmd}.py; new packages/emcee/tests/test_recording.py; scripts/backfill_voiced_by.py; scripts/test_backfill_voiced_by.py.

## Self-review / small additions beyond the literal brief
- In the four `resolve_assignment` tests, the now-dead `manifest = Package(build_package(...)).manifest()` lines were removed (they were unused once the profile is passed directly), and one comment reworded ("The profile has no [assign.profiles.*] entry").
- test_run_cmd's comment block above `_hoist_probe_setup` described the OLD mutant shape (alice's voice + bob's own re-derived bed); updated to the new shape (whole first-presenter voicing: voice AND bed), matching the rewritten test's assertion `("alice-voice", "alice.wav")`.
- `_process_one` docstring keeps the "fresh holds already-validated, de-duplicated clip stems" note from the old docstring and lists "an invalid move target" among config-only failures.
- Overlong `process_package(..., voicing=voicing_for(config, pkg))` lines in test_process/test_quality were wrapped.
- No brief/code disagreements found: every Task 2-4 interface named in the brief exists with the stated signature.

## Concerns (minor, none blocking)
- `models.py` module docstring still says emcee's blocks are "shape-identical to llama's `DJNotes` and `DJAudio`". emcee's `DJAudioBlock` now has three more fields than llama's `DJAudio` (packages/llama/src/llama/models.py:262). llama's model is a plain `BaseModel` (extra ignored), so llama still parses these manifests; only the docstring/passthrough documentation is stale. The brief did not touch it; a later docs task may want to.
- `voice_cmd`'s `--fresh` help text ("a re-voice always resolves the voice fresh from config + presenter assignment") is still accurate, but it does not mention moves or artist rules.
