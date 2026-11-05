### Spec Compliance

- ✅ Spec compliant. Every file in the brief has its hunk. `DJAudioBlock.title` is declared last and always serialized (emcee/models.py:75), `process_package` passes `title=voicing.title` (process.py:476), llama has `DJAudio.title` (llama/models.py:325), the docs sentence is in packages/emcee/CLAUDE.md:126, and all five named tests exist (test_process.py:317-346, test_the_cut.py:89-96, scripts/test_dj_audio_handshake.py). Exact-dict asserts were updated in test_audio.py:448 and test_process.py:231.
- ⚠️ Cannot verify from diff: Task 8's raw writer must append `title` last on a block that lacks the key. That is Task 8's to pin.

### Strengths
- The title is resolved in one place, `resolve_voicing` (process.py:106-108, `resolve_assignment(config, effective.profile)`). The voiced title therefore follows the same resolution as the presenter, which matches the spec's "The title" section.
- The tests assert key position as well as value (`list(dj_audio)[-1] == "title"`). That is the property Task 8 depends on.
- The handshake test sits in `scripts/`, so emcee's no-llama-imports rule stays intact.

### Named-risk checks
1. **Effective profile, not requested profile.** I checked process.py:97-108. `title` comes from `resolve_assignment(config, effective.profile)`, after `effective_profile(config, moves, manifest)`. `test_title_follows_the_effective_profile` (test_process.py:335) requests `prime-dead`, which has no assignment, and an `[assign.artists]` rule moves it to the titled `bluegrass`. A title taken from the requested profile would be None, so the test discriminates. Holds.
2. **llama parse and rewrite.** llama's `DJAudio`/`Manifest` use pydantic's default extra policy, `ignore`. Before this change a titled block parsed and the title was silently dropped; now it is kept (llama/models.py:325). The only `Manifest(...)` construction is in llama/manifest.py:27, which builds library manifests with `dj_audio` null. Station manifests are handled as raw dicts (station_mark.py:6-7, cli.py:2516/2654/2938 only read `dj_audio`), so no llama path drops or reorders the field. Holds.
3. **Other emcee builders.** grep finds one `DJAudioBlock(` construction, process.py:469. `--keep-script` and re-voice both reach that same `process_package` construction. The other `rewrite_manifest` calls (process.py:462, cli.py:359) write `dj_audio=None` (the clear). `rewrite_manifest` serializes with `model_dump()` and no `exclude_none` (package_io.py:82), so a null title is written. The `scripts/backfill_*` one-offs edit raw dicts and touch only their own key. Holds.

### Would the new tests have failed before the change? (no RED was recorded)
- `test_voicing_records_the_program_title`: before the change there is no `title` key, so the test raises KeyError. With the field added but no argument passed, the title is None, not "Gravel & Steel". It fails in both cases.
- `test_voicing_by_default_or_house_records_null_title`: before the change, `"title" in block` is False, so it fails. It would pass with the field alone; the test above covers the missing argument.
- `test_title_follows_the_effective_profile`: discriminating, as in risk 1.
- llama `test_llama_dj_audio_parses_a_block_with_title_and_without`: the extra key is ignored, so `.title` raises AttributeError and the test fails.
- `scripts/test_dj_audio_handshake.py`: without llama's field, AttributeError. Without emcee's field, emcee's default extra is `ignore`, so `title` is dropped and `"Gravel & Steel" != None`. It fails either way, and `scripts` is in `testpaths` (pytest.ini:2), so it is collected.
- Check run: `./.venv/bin/pytest packages/emcee/tests/test_process.py packages/llama/tests/test_the_cut.py scripts/test_dj_audio_handshake.py -q -k "title or handshake or dj_audio"`: 9 passed, clean output.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- packages/emcee/CLAUDE.md:126 and packages/emcee/src/emcee/models.py:74 say "Task 8's raw backfill" / "Task 8's raw writer". Plan task numbers mean nothing after merge. Name the backfill subcommand once Task 8 exists, or say "the title backfill".
- test_the_cut.py:94: the brief says "model_dump round-trips". The test checks only `model_dump()["title"]`, not the full dict. The updated `test_dj_audio_doc_model_accepts_emcees_recorded_profile_and_tts` (test_the_cut.py:82) and the handshake test do full-dict round trips, so coverage is adequate.
- The implementer did not record a RED run (process gap). The analysis above shows each new test discriminates.

### Assessment

**Task quality:** Approved

**Reasoning:** The field is added in both models, recorded once at the single `DJAudioBlock` construction site from the effective profile's assignment, and serialized last. None of llama's paths parse-and-rewrite a station manifest. Each new test would have failed without the change.
