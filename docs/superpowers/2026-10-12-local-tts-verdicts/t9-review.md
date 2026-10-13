### Spec Compliance
- ✅ Spec compliant. `_mlx_provider` and the `mlx_audio` dispatch (`packages/emcee/src/emcee/tts/__init__.py:16-44,79-81`) match the brief's Step 4 code exactly. The three exact house-voice substrings are present. The provider is built from `config.tts.mlx_audio.url`/`timeout_s`, `resolution.model` and `CALIBRATED_MODELS[resolution.model]`, and the class is referenced through the module global, so the `emcee.tts.MlxAudioProvider` patch works. `install_mlx` (`tests/mlx_helpers.py:74-82`) and `test_mlx_wiring.py` match the brief verbatim.
- Controller rulings verified:
  - (a) `calibration.py:71-72`: `seconds <= 0` is checked first. Test: `test_mlx_audio.py:84-90`, which covers 0.0 and -1.0 rejected and 0.5 s accepted.
  - (b) `test_mlx_audio.py:121-134`: `~` is sent expanded and absolute.
  - (c) `test_voice_cmd.py:597-620`: a provider whose preflight fails is still closed.
  - (d) `cli.py:461`: the docstring is updated.
- Plan Review Focus (4): `test_repinning_a_presenter_changes_the_cache_key` (fake → mlx → fake) asserts the keys are disjoint and that the original keys come back.
- Plan Review Focus (5): `test_run_continues_other_presenters_when_mlx_is_down` asserts exit 1, `error: a: …not reachable`, `voiced: b`, `a`'s manifest bytes unchanged and `b`'s `dj_audio` set.
- ⚠️ Cannot verify from diff: the presenter-pin validation (Task 4 `Presenter`) that makes the presenter-worded branches of `_mlx_provider` unreachable in practice. The `say` "no preflight" behaviour comes from Task 7. Both are cross-task.

### Strengths
- Strict surface 1 is tested where it counts. `_forbid_hosted` patches the hosted classes' `__init__` rather than a module's name for them, so a fallback built through any import path is caught. The test runs across all three commands, under both a voxtral house with an mlx presenter and an mlx house voice, with `MISTRAL_API_KEY` set, so a fallback would actually be reachable (`test_mlx_wiring.py:166-200`).
- Strict surface 2 is pinned on both destructive paths: the manifest clear (`_process_one`, `test_mlx_wiring.py:221-231`) and the `--fresh` unlink (`:234-247`). Both also assert no scriptwrite call (`tasks == []`).
- The empty-clip guard sits ahead of the cap/long/short checks, and its docstring says why: the short bound floors at 0 s (`calibration.py:67-72`).
- The implementer's mutation evidence is plausible and matches the code.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. `test_mlx_wiring.py:250-268` (Review Focus 5) does not pin preflight ordering for the mlx package. Its "manifest untouched" assertion is weak because package `a` starts pending with null blocks, so a premature `rewrite_manifest(dj_notes=None, dj_audio=None)` can leave its bytes unchanged. It also installs an untracked `provider_for` lambda, so nothing checks that `a` spent no scriptwrite call. The implementer said so (mutant m2). I judged it acceptable: named risk "is `run` covered by the ordering tests at all?". I checked `cli.py:404` and `cli.py:495`: `run` and `voice` both go through `_process_one`. So `test_dead_server_leaves_a_voiced_package_untouched` (which calls `_process_one` directly) pins the ordering for `run` too. Cheap hardening if wanted: use `_arm_llm`-style task tracking and assert that exactly one scriptwrite happened, for `b`. This is a plan-verbatim test, so it is not a blocker.
2. The presenter-worded error branches of `_mlx_provider` (`__init__.py:27,31,36`) have no test. They are defensive: `Presenter` validation should make them unreachable. Polish only.

Named risk checked: `emcee.tts` binds `CALIBRATED_MODELS` by name at import (`__init__.py:2`), so a test that replaced the dict would leave the factory with a stale binding and a `KeyError`. Checked `tests/mlx_helpers.py:26`: `calibrate_test_model` uses `monkeypatch.setitem` on the same dict object, so the binding is shared. `resolve.py:61` rejects uncalibrated models before the factory runs, so the factory's `KeyError` can only come from a hand-built `TTSResolution`. No issue.

### Assessment
**Task quality:** Approved
**Reasoning:** The factory branch, the house-voice errors and the four controller rulings are implemented exactly as specified. Strict surfaces 1 and 2 are pinned end to end through `run`/`voice`/`say`. Review Focus (5)'s own test is weak on ordering, but the dead-server tests on the shared `_process_one` path cover it.
