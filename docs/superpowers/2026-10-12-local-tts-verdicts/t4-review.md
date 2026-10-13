### Spec Compliance
- ✅ Spec compliant. All four files match the brief exactly, apart from the controller-ruled test strengthening.
  - `ModelCalibration` has the fields in the brief's order, with all four `__post_init__` invariants (calibration.py:17-39).
  - `CALIBRATED_MODELS: dict[str, ModelCalibration] = {}` is EMPTY in production code (calibration.py:44).
  - `TTSResolution` has the fields in the brief's order: backend, model, api_key, key_sources, presenter, pinned (resolve.py:34-41).
  - `TTSResolutionError(EmceeError)` is at resolve.py:30. `DEFAULT_MODELS` is built from absolute submodule imports (resolve.py:23-26).
  - All three exact error substrings are present (resolve.py:52, :60, :64).
  - `tests/mlx_helpers.py` exports `TEST_MODEL`, `TEST_MODEL_B`, `TEST_CAL` and `calibrate_test_model` with the brief's values (mlx_helpers.py:10-20).
  - The resolver matches spec §1 "Resolution" rule by rule (spec lines 145-162):
    - A pin beats the house backend.
    - An unpinned presenter under an mlx house is an error.
    - The mlx model is chosen as presenter.tts_model, then [tts.mlx_audio] model, then an error; an uncalibrated model is also an error.
    - For hosted backends, the subtable wins. The legacy [tts] model/api_key is used only when the backend is the house backend; otherwise the provider default applies.
  - It is pure: no file or network access and no provider construction (resolve.py:44-74).
- ✅ Controller ruling met (test_resolve.py:169-176). `test_test_calibration_is_registered_only_inside_a_test` now checks three things:
  1. TEST_MODEL is absent before registration, so a leak into calibration.py fails here.
  2. It is present after `calibrate_test_model`.
  3. It is absent again after `monkeypatch.undo()`.
  The companion test `test_test_models_are_never_production_entries` (:30-34) covers both TEST_MODEL and TEST_MODEL_B.
- ⚠️ Cannot verify from the diff, because these are cross-task:
  - The `emcee presenter edit {pid} --tts voxtral` hint in the unpinned-under-mlx error (resolve.py:53) points at a command that Task 13 builds. The spec does name it (spec:312), so the hint is correct once Task 13 lands.
  - Once Task 5 makes `emcee/tts/__init__.py` import `resolve`, its import-cycle safety depends on voxtral.py and elevenlabs.py importing only `emcee.tts.provider`. I checked this: today they do (voxtral.py:10, elevenlabs.py:7), so it is fine as it stands.

### Strengths
- The resolver code is small and readable; each spec rule maps to one branch (resolve.py:44-74).
- Error messages name the subject (`presenter 'phil'` or `the house voice`) and the config key to set. The uncalibrated error also lists the calibrated models, or "none yet" when there are none (resolve.py:62-65). That is the right operator signal while the table is empty before Task 12.
- `key_sources` lists only the locations that actually apply, so a later missing-key error cannot point the operator at a `[tts] api_key` that would be ignored. This is pinned by test_resolve.py:121-125 and :128-131.
- The tests compare whole `TTSResolution` values where the field set matters (:55-58, :82-84, :161-163), which locks in field order and values for the later tasks that consume them.
- Calibration invariant tests check one invariant per case, each matched by message (:37-45).

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **test_resolve.py (whole file): no test covers a pinned presenter under an mlx_audio house.** Spec:128-130 says an mlx house "voices only packages with no presenter", so pinned presenters must still resolve.
   - What I checked: every `resolve_tts` call that uses `backend="mlx_audio"` passes either `None` (:81, :88, :94) or an unpinned `host()` (:114).
   - Why it matters: a plausible regression would go undetected. If someone hoisted the check at resolve.py:51 above the pin branch, or dropped `presenter.tts is not None` from its condition, every presenter would fail under an mlx house and no test would go red.
   - Fix: add one test, for example `resolve_tts(cfg(backend="mlx_audio", mlx_audio={"model": TEST_MODEL}), host(tts="voxtral"))` should give `("voxtral", True)` and `key_sources == ("[tts.voxtral] api_key",)`, with `calibrate_test_model` registered.
   - Severity: Minor under the rubric ("coverage could be broader"), but this is the cheapest missing pin in the file.
2. **Handback: the RED evidence was produced after the fact.** The implementer wrote the code alongside the tests, then showed RED by moving resolve.py aside. The result (collection `ModuleNotFoundError`) is the same as the brief's Step 3, so nothing here is untrusted. It is a process note only.
3. **No test asserts `CALIBRATED_MODELS == {}` in production.** I am noting this so nobody adds one: Task 12 must add an entry, so pinning emptiness would be wrong. The two absence checks for the test-only models are the right guard.

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation matches the brief verbatim and spec §1 rule by rule. It is pure, the production calibration table is empty, and the controller's strengthened leak test is in place. The only gap is a missing test for a pinned presenter under an mlx_audio house, which is coverage polish rather than a defect.

Named-risk checks performed:
- HOSTED_BACKENDS vs. subtable attributes, since `getattr` at resolve.py:68 would fail on a mismatch: config.py:63 gives ("voxtral", "elevenlabs"), and the subtables are at config.py:111-112.
- Whether `tts_model` can be silently ignored on a hosted pin: no. The Presenter validator rejects `tts_model` unless `tts == "mlx_audio"` (presenters.py:44-49).
- Import-cycle exposure for Task 5: voxtral.py and elevenlabs.py import only `emcee.tts.provider`.
- The rules against spec text lines 145-162.
No tests were re-run, since the report's evidence and the code answered every doubt.
