### Spec Compliance

- ✅ Spec compliant. Every Step 3-7 item is present with the brief's exact signatures and bodies:
  - models.py:35-69 has `DJClips`, `TTSRecord` and `DJAudioBlock(DJClips)`; `profile`, `profile_source` and `tts` are required with no defaults (diff 365-402).
  - audio.py:21, 275, 355, 373, 393 switch to `DJClips` (diff 52-140).
  - process.py has `resolve_assignment(config, profile)`, the frozen `Voicing`, `resolve_voicing` (move_target_problem first, then effective_profile, assignment and resolve_tts), `_speech_from`, `speech_for` (signature unchanged), `speech_for_voicing`, and `process_package(..., *, voicing)` building the whole block from `voicing` plus `speech.model`/`speech.voice` (diff 476-690).
  - cli.py `_process_one(config, moves, pkg, force, fresh)`: resolves once, then preflight, `--fresh` unlink, manifest clear and `process_package` in the strict order (diff 190-248). `run` passes `moves` (diff 271). In `voice_cmd`, `load_moves` comes before package resolution and `require_present` runs when `profile_source == "move"`, all before `--fresh` validation and any work (diff 292-299).
  - backfill script: a raw-dict update through `atomic_write`, in the same `indent=2` + newline format as `rewrite_manifest`, plus the docstring change (diff 1961-2021).
  - Step 6 call sites: every listed file has its hunk (test_process, test_audio, test_quality:159, test_verify:462/482/547, test_package_io:85, test_run_cmd including the rewritten hoist test and both dry-run patch targets, test_voice_cmd:559/619, test_mlx_wiring:224/434).
- Check: `packages/emcee/tests/test_recording.py` matches the brief's Step 1 block byte for byte. I extracted brief lines 37-270 and ran `diff` against the file: IDENTICAL.
- Check: `git grep` at 9960cf3 for `resolve_assignment` / `process_package(` / `_process_one(` / `speech_for(` / `DJAudioBlock` outside tests. No caller is left unmigrated. The only `speech_for` callers left are `ad_hoc_speech` (process.py:167, 175), i.e. `emcee say`, as intended.
- Check, named risk "the record step raises AttributeError after all TTS spend": every concrete provider sets `.voice` and `.model`.
  - fake.py:40-41, voxtral.py:69/83/87, elevenlabs.py:31-32, mlx_audio.py:69-70, and the QualitySpeech wrapper quality.py:42-43.
  - None of them can produce a `None` voice: voxtral and elevenlabs raise first when no voice is set (tts/__init__.py:80-94).
- Check, named risk "a legacy dj_audio is round-tripped through the now-strict model somewhere else": the only `DJAudioBlock` construction in src is process.py:321. `rewrite_manifest` only dumps a block it is given (package_io.py:66-82), and the backfill no longer validates.
- ⚠️ Cannot verify from this diff:
  - `emcee run`'s per-package error row for an invalid move target, with other packages proceeding (spec §3). The code path exists: `resolve_voicing` raises inside `run`'s per-package `try` (cli.py:400). This task has no `run`-side test for it; the plan's Task 7 pins it (plan lines ~3390/3411 assert `error: moved: move target "southern" ...`). The controller should confirm Task 7 lands that.
  - Spec §4 also asks for llama's `DJAudio` to gain the three fields as optional fields, `tts` in `status --json`, and the CLAUDE.md:643 text, which still says `resolve_assignment` is "keyed off `manifest["source"]["profile"]`". The plan assigns these to Tasks 8 and 9, not this task.

### Strengths

- The single resolution is structural, not conventional. `process_package` no longer has any path to `resolve_assignment` (process.py:308 reads `voicing.presenter`/`voicing.title`), and `resolve_assignment` now takes a profile, so it cannot be keyed on a manifest.
- `test_process_one_resolves_the_assignment_exactly_once` patches the module global, which `resolve_voicing` looks up at call time. A re-resolution inside `process_package` would therefore be caught.
- The recorded fields are pinned against realistic mutants:
  - recording llama's profile instead of the effective one: caught by `test_voice_persona_title_bed_and_record_all_follow_the_effective_profile`, which expects `southern`/`artist`;
  - taking `model` from the resolution instead of the provider: caught by `tagged-model` and `fake-model`;
  - taking `voice` from the presenter's field instead of `speech.voice`: caught by the clone-hash test, which expects `clone:<sha256[:16]>`.
- Strict surface 2 for `voice` is tested on both arms.
  - The truncated and wrong-shape files assert `EmceeError` names the path and the manifest bytes are unchanged.
  - The missing-file test asserts the exception TYPE (`EmceeError`, not `SystemExit`). So dropping the `require_present` call is caught: without it, the `forbid_spend` failure would surface inside `voice_cmd`'s broad catch as an Exit, not an `EmceeError`.
- The hoist-probe comment and test were rewritten honestly to the new mutant shape (voice and bed both from the first presenter), rather than left asserting a pairing that can no longer occur (test_run_cmd.py diff 1637-1743).
- The backfill's raw update preserves unknown keys. The new test pins it, and its RED showed `future_key` being dropped.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. cli.py:226 (`speech, _bed = speech_for_voicing(config, voicing)`) and process.py:312 (`bed = _resolve_bed(config, presenter)`): the bed is computed twice from the same `voicing.presenter`, and the production caller throws the first copy away.
   - It is consistent today: both copies derive from one presenter, so the hoist hazard is gone.
   - But `speech_for_voicing`'s bed half is dead output in its only production caller.
   - Plan-mandated return type, so leave it; worth one line in the Task 9 or final review if anyone wants `speech_for_voicing` to return the provider alone.
2. models.py:1-10, the module docstring, still calls emcee's blocks "shape-identical to llama's `DJNotes` and `DJAudio`". After this commit emcee's `DJAudioBlock` has three fields llama's model lacks. That is only true again once Task 9 adds them as optional on llama's side. The implementer flagged it.
   - Fix (Task 9): reword as "shape-compatible (llama's copy carries the newer fields as optional)".
3. tts/provider.py:72 (unchanged code): the `SpeechProvider` Protocol still does not declare `voice: str` / `model: str | None`, though the render cache and now the recorded `TTSRecord` both depend on them.
   - Pre-existing gap that this task leans on harder.
   - Adding the two attributes to the Protocol would make the contract explicit.
4. The implementer's full-suite run reports "pre-existing llama fork() DeprecationWarnings". That noise is not from this task, but the output is not pristine. Recorded per the template.
5. Spec-level observation, not a defect of this diff: `voice_cmd`'s missing-file guard keys on the recorded `dj_audio.profile_source`. `_process_one` clears `dj_audio` to null before `process_package` (cli.py:246). So if a re-voice of a move-voiced package fails mid-pipeline, the "move" record goes with it, and a later lost `moves.json` would not be refused for that package.
   - This needs two independent failures and sits inside the spec's acknowledged strict-surface-2 limit.
   - Flagged only so the final review can decide whether it deserves a line in the runbook.

### Assessment

**Task quality:** Approved

**Reasoning:** The diff implements the brief verbatim: one `Voicing` per package, threaded through and recorded from that same resolution and provider instance. The `voice` strict-surface-2 checks run before any work and are pinned by tests that distinguish the error type. The findings are documentation and dead-output polish, plus run-side coverage that the plan places in Task 7.
