# Pre-flight conflict scan: local-tts plan (HEAD 3f3bc7f)

Scope: I read the whole plan (6,591 lines) and the spec, and checked every task's "modify" instructions and test assumptions against the source at HEAD. I ran no tests and did not touch the venv. Line numbers given as "L####" are plan lines.

**Bottom line:** I found nothing that blocks execution. Every cross-task interface, meaning names, signatures, message substrings, helper names and fixture shapes, matches. Every task's tests should pass against that task's own code. No task leaves the full suite red. The conflicts below are all review-loop or cosmetic.

Things I checked against the source (all OK):
- **Line references:** cli.py:226/276/361/448, process.py:87-147, voxtral.py:54-73, elevenlabs.py:22-37, audio.py:25/342-344, test_tts.py:147-214, test_process.py:116-178, test_run_cmd.py:318/430/548 all match what the plan says is there.
- **Click output capture:** `result.output` includes stderr, and existing tests already rely on that. `result.stderr` is also available.
- **Packages and bundling:** `emcee.data` already exists, and `packaging/emcee.spec` bundles it. `*.wav` is not gitignored.
- **Silent test audio:** `normalize_speech` returns silent PCM unchanged, so the silent WAVs the tests use are safe.
- **Clip stems and cache file:** `segments.json` maps stem to a str key. Stems are `set1-intro`, `set2-intro`, `99-outro`. `scan` sorts its output.
- **Imports:** there is no circular import across `emcee.tts.__init__`, `resolve`, `presenters`, `config`, `quality` and `verify`.
- **Live presenters:** all 5 live presenter files and `~/.emcee/config.toml` use only known keys.
- **Bake-off data for Task 12:** `~/tts-bakeoff` matches what Task 12 expects. qwen 0.6B set1 has 16 sentences and 16 calls, and the longest is index 5 at 320.0 s. Chatterbox set2 has 10 and 10, and "Here is Morning Dew." is index 9 at 10.1 s. `uv`, `ffmpeg` and `footprint` are all installed.
- **Guard arithmetic:** SENTENCE has n=63, giving max_tokens 195, a 15.6 s cap and a 10.93 s long limit.
- **Task 11 thresholds survive Task 12:** every comparison test in Task 11 still holds at any measured thresholds inside Task 12's STOP ceilings (MISS_FLOOR 2-3, EXTRA_FLOOR ≤6, MISS_FRACTION ≤0.4, EXTRA_FRACTION ≤1.0).

## Table A: task pairs that share a file or an interface

| Pair | Earlier task produces → later task consumes | Finding |
|---|---|---|
| 1→8 | Probe rows `midstream_exception`, `wave_reads_server_wav`, `nframes_header_matches`, `max_tokens_truncates_silently` → Task 8 "Before coding" gates | Consistent. Row names match the doc template (L469-482). `exc_facts` records `httpx.X` because httpx sets `__module__="httpx"`. |
| 1→11/12/15 | Probe row `stt_model` → Task 12 `--stt-model`, the live test, Task 15's template and runbook (Task 11 tests use `stt/test-model`) | Consistent |
| 2→4 | `Presenter.tts/tts_model/voice_clone_text`, `.id` → `resolve_tts` | Consistent |
| 2→5 | `voice_clone_text` → `speech_for`/`ad_hoc_speech` pass it as `clone_text`; test_process `_presenter(...)` kwargs | Consistent (`_presenter` id "waldo", preset by default) |
| 2→6 | Strict base, so `tts_modle` raises PresenterError → `[invalid ...]` marker | Consistent. `load_presenter` lets UnicodeDecodeError and IsADirectoryError through, and Task 6 catches both as `OSError`/`ValueError`. |
| 2→9/10/11 | Presenter constructor rules (mlx needs a clip and a transcript) → test fixtures `_phil`, `_mlx_presenter`, `mlx_host` | Consistent |
| 2→13 | Validation messages "clone-only", "needs voice_clone_text", `tts_model is allowed only with tts = "mlx_audio"`, "tts must be one of"; `save_presenter` returns the path → `presenter edit` tests and the "saved:" line | Consistent. Rule order puts "clone-only" before the transcript check, as `test_an_invalid_merged_edit...` expects. |
| 2→14 | "clone-only" → `presenter add` invalid-pin test | Consistent |
| 3→4 | `HOSTED_BACKENDS`, `HostedTTSConfig`, `MlxAudioConfig.model`, legacy `[tts] api_key/model` → resolve | Consistent. Every config in Task 4's tests passes Task 3's validator. |
| 3→5 | `TTSConfig(voice_clone_text=...)`, `[tts.voxtral]` dicts → factory and process tests | Consistent |
| 3→9 | `mlx_audio.url` and `timeout_s` → `_mlx_provider` | Consistent (`timeout.read == 42`) |
| 3→11 | `verify.backends` and `mlx_audio.stt_model` (required when the list is non-empty) → `_quality` and test configs | Consistent. Every verify config in the tests sets `stt_model`. |
| 3→13 | `stt_model`, `url`, `timeout_s`, `verify.backends` → `_draft_transcript` | Consistent |
| 3→14 | `tts.backend` → `say`'s `house_mlx` | Consistent |
| 3→15 | Template line at L1055 → Task 15's exact replacement at L6353 | Consistent (byte-identical, spacing included) |
| 4→5 | `resolve_tts`, `TTSResolution` field order, `key_sources` → `speech_provider_for`, `key_hint`, the positional `TTSResolution(...)` in a test | Consistent |
| 4→6 | `TTSResolutionError` texts "presenter 'roy': pin tts explicitly…" and "…not calibrated for the runaway guard", `.pinned`, `.model` → `_dry_run_marker` | Consistent. `_selection_station`'s house is **fake**, so the `vox` pin resolves to `VOX_DEFAULT` as the test expects. |
| 4→8 | `calibration.py` (empty table) → Task 8 appends `import math` and the guard math | Consistent |
| 4→9/11 | `CALIBRATED_MODELS`, `calibrate_test_model`, `TEST_MODEL` → factory lookup and all mlx tests | Consistent |
| 4→12 | Empty table and its comment → Task 12 replaces both with `QWEN3_TTS_1_7B_BASE` | Consistent. No earlier test assumes the table is empty: they all use `other/model` or `other/uncalibrated`. |
| 4 mlx_helpers→8→9→11 | Task 4 creates the file; 8 appends `wav_bytes`, `plausible_seconds`, `MlxServer`; 9 appends `install_mlx`; 11 replaces `MlxServer` and `install_mlx` | Consistent. Task 11's `MlxServer` is a superset (same `down`, `speech_bodies`, `connect_attempts`, `transport()`). Its `install_mlx` patches `emcee.tts.SttClient`, which Task 11 Step 6 adds. |
| 5→7 | Keyword-only factory signature → `_arm_failing_preflight`, the `Spy` lambda, the TaggedProvider lambda | Consistent |
| 5→9 | `_who`, the branch structure, "insert before the final raise" → `_mlx_provider` | Consistent |
| 5→10/11 | The hosted branch bodies → wrapped in `QualitySpeech`/`_quality` | Consistent (Task 11 L4692-4699 repeats Task 5's constructor args exactly) |
| 5→14 | `ad_hoc_speech(..., clone_text=...)` → `say` | Consistent. test_say's `fake_ad_hoc_speech(config, **kwargs)` accepts the new key. |
| 5 conftest→all | Autouse fixture deletes `MISTRAL_API_KEY`/`ELEVENLABS_API_KEY` → missing-key tests | Consistent. test_voxtral.py:61 and test_tts.py:104 already say "conftest guarantees…" but no emcee conftest exists today, so Task 5 makes those comments true. |
| 6↔7 | Both edit cli.py: 6 changes `_presenter_file*` and the dry-run branch; 7 changes `_process_one` and `voice_cmd` | No overlap. Consistent. |
| 7→8 | `preflight()` in the runtime_checkable Protocol → mlx `preflight`; Task 8's `isinstance(..., SpeechProvider)` | Consistent. test_voxtral's `isinstance` keeps passing because Task 7 gives Voxtral `preflight`. |
| 7→9/11 | `_process_one(config, pkg, force, fresh=())` with order preflight → unlink → clear → process → strict-surface tests and the matrix (`fresh=["set1-intro"]`) | Consistent |
| 7→10/11 | `preflight()` delegation → `QualitySpeech.preflight` | Consistent |
| 8→9 | `MlxAudioProvider(*, url, model, clone_ref, clone_text, calibration, timeout_s, transport, sleep)` → `_mlx_provider` and `partial(...)` in `install_mlx` | Consistent. The factory looks the class up as a module global at call time, so the patch takes effect. |
| 8→10 | `SpeechDefect(backend, *, text, reason, transcript)`, `.segment` → `_retrying`, audio.py annotation | Consistent |
| 8→11 | `PREFLIGHT_TEXT`, `wav_to_mp3`, `preflight_wav()` → quality.py | Consistent |
| 8→12 | Private `_post`/`_read_wav`, plus `text_units`, `max_tokens_for`, `cap_seconds`, `guard_problem` → calibration script | Consistent |
| 9→10 | `_mlx_provider`, test helper `_inner` (looks through `.inner`) → Task 10 wraps the provider | Consistent |
| 9→11 | test_mlx_wiring helpers `_phil`, `_forbid_hosted`, `_arm_llm`, `_VOXTRAL_HOUSE`, `_ASSIGN_DEAD`, `runner` → appended matrix | Consistent |
| 10→11 | `_attempt`, `_retrying(text, attempt)`, `preflight`, `close` → replaced or extended | Consistent |
| 11→12 | Interim thresholds, `PREFLIGHT_CLIP`, `preflight_clip_wav` → measured values and the bundled WAV | Consistent. Before Task 12 the clip is missing, and every test that reaches it patches `preflight_clip_wav`. |
| 11→13 | `SttClient.transcribe/unload/close`, `MlxServer(transcript=, stt_down=)` → `_draft_transcript` and the edit tests | Consistent |
| 11→14 | `install_mlx`, `MlxServer` → say tests | Consistent |
| 13→14 | `_usage`, `_abs_clip`, `_draft_transcript`, cli imports `ValidationError`, `NoReturn`, `SttClient` → `presenter add`, `say` | Consistent (but see conflict C2: duplicated blocks) |
| 2/13/14→15 | Command and key names → README/CLAUDE.md text | Consistent. See C6 for wrapped replacement anchors. |

## Table B: does each task agree with itself?

| Task | Tests vs code | Files vs later touches | Stated Produces vs actual code |
|---|---|---|---|
| 1 | Live; the probe script is self-consistent (checks, rows and the doc template agree). Another agent is running it now. | OK | All 12 rows are in the doc template |
| 2 | Pass. Error strings match. `"tts" not in text` is safe for the `make()` fixture. | OK | OK (field order, `TTS_PINS`, `save_presenter` re-validates) |
| 3 | Pass. Exact substrings match. `LIVE_CONFIG` matches the live file's shape. | OK. Step 4 wording is inconsistent (C5). | OK |
| 4 | Pass. Invariant messages match the positional ctor calls. | OK | OK (`DEFAULT_MODELS` uses absolute imports, so the later cycle is safe) |
| 5 | Pass. The "missing key" strings come out exact through `key_hint` joining. | Step 7 grep is correct (1 definition, 3 calls) | OK, except C1 (stale docstring the plan says to keep) |
| 6 | Pass. Lines match `would voice: …` plus the marker. The binary and directory cases are caught. The BILLYG fix is required and is included. | OK | OK |
| 7 | Pass. Step 2's stated failure text is slightly off (C3). | OK | OK |
| 8 | Pass (arithmetic checked: 195, 15.6, 10.93, 0.89). The bad-WAV parametrize cases hit the right checks in order. | OK | OK |
| 9 | Pass. say lets the exception escape, so `str(result.exception)` holds. run/voice print to stderr. `connect_attempts == 2`. | OK | OK |
| 10 | Pass | OK | OK |
| 11 | Pass. Multipart byte assertions match httpx's encoding, and MockTransport calls `request.read()`. | OK | OK |
| 12 | Live and data-dependent. The script, tests and Interfaces agree (`guard_checks` keys, flags, the `<adopted>` table). | OK. `data/__init__.py` exists. | OK. See C7 and C8. |
| 13 | Pass. Usage errors exit 2 into mixed output. Decline exits 1 with the file untouched. Unload happens only when verify is off. | OK | OK (messages match the Interfaces list) |
| 14 | Pass. `_abs_clip("/ref.wav")` and `"/r/phil.wav"` resolve to themselves, so existing list/show assertions still hold. | OK | OK |
| 15 | Docs only. The template line matches Task 3 exactly. | Anchors exist (README L278/289/310/317/352/389, CLAUDE.md 131/186-188/607/611/774) | n/a (see C6) |

## Conflicts

None of these block execution.

- **C1: stale docstring (Task 5). Severity: review loop.**
  - L1841 says "Keep `speech_for`'s existing docstring and append…".
  - The existing docstring (process.py:88-106) says "`presenter.voice or presenter.voice_clone` is resolved, and `presenter.voice_clone` is passed as `clone_ref` … falls back to the house `config.tts.voice or config.tts.voice_clone`".
  - The new body (L1855-1866) passes `voice=presenter.voice` / `config.tts.voice` with no `or voice_clone` fallback, so the kept text becomes false.
  - Ruling: in Task 5, replace those two sentences with "the presenter's (or `[tts]`'s) own `voice`, `voice_clone` and `voice_clone_text` are passed through unchanged."

- **C2: verbatim duplication between `presenter edit` (Task 13) and `presenter add` (Task 14). Severity: review loop.**
  - The `--character-file` read block: L5928-5933 vs L6227-6232 (already present in today's add).
  - The `except ValidationError: echo "invalid presenter:"; Exit(1)` handler: L5972-5974 vs L6246-6248.
  - The "validate with a placeholder transcript, then `_draft_transcript`" idiom: L5965-5970 vs L6242-6244.
  - The `--transcribe and --voice-clone-text` usage check: L5916-5917 vs L6221-6222.
  - Ruling: in Task 13, extract `_read_character_file(path) -> str` and reuse it in Task 14. Optionally also a `_build_presenter(config, build, clip, transcribe)` helper. Or accept the duplication up front so reviewers don't loop on it.

- **C3: wrong expected-failure text (Task 7 Step 2, L2302). Severity: cosmetic.**
  - The plan says `AttributeError … preflight_calls`.
  - `FakeSpeechProvider(preflight_fail=True)` actually fails first with `TypeError: unexpected keyword argument 'preflight_fail'`.
  - Ruling: say "AttributeError/TypeError".

- **C4: commit trailer session id (Global Constraints, L36 and every commit block). Severity: cosmetic.**
  - Every commit block hard-codes `Claude-Session: …session_01TNheuMFMvYwCHKaT9xJRS2` and "Claude Opus 5.5" as co-author, including for Sonnet implementers.
  - That is the same class of problem as the scratchpad path you already ruled on.
  - Ruling: use the executing session's own attribution lines.

- **C5: "insert" vs "must read" (Task 3 Step 4, L1018). Severity: cosmetic.**
  - L1018 says to *insert* the transcript key and the subtables.
  - The "must read" block also rewrites two existing comments: "voxtral clones that voice" becomes "the house voice clones it", and "per-backend default when unset" becomes the "legacy spellings…" paragraph.
  - Ruling: "must read" governs.

- **C6: replacement anchors that span line wraps (Task 15 Steps 4.2 and 4.4, L6511 and L6544). Severity: cosmetic.**
  - The quoted text spans line wraps in CLAUDE.md: "…presenter voice clones are\nVoxtral-only)" at lines 187-188, and "(`emcee presenter\n  add/list/show/remove`)" around 611-612.
  - A literal single-line match will fail.
  - Ruling: match across the newline, or reflow the paragraph.

- **C7: thresholds used before they are written (Task 12 Step 4 vs Step 7, L5267 vs L5409). Severity: cosmetic, could confuse the implementer.**
  - Step 4 keeps the Kokoro take that passes `transcript_problem` "under the ADOPTED thresholds".
  - The thresholds are only written into verify.py in Step 7. They are operator-approved at Checkpoint 2 but not yet in code during Step 4.
  - Ruling: during Step 4, apply the approved values with setattr on `verify_mod` (as `recommend` does), or re-check the take after Step 7.

- **C8: a crash risk in the calibration script (Task 12 Step 1, L4884-4888 and L5133-5135). Severity: cosmetic; costs a re-run.**
  - If any drafted transcript comes back empty, `MlxAudioProvider` raises inside the `providers` dict comprehension. That aborts the whole run before the first unit renders.
  - Ruling: skip that voice and record it, or check the draft is non-blank in `voices()`.

## Things a code-review rubric would flag as defects

These are all mandated by the plan text.

- **Tests that assert little or nothing:**
  - Task 4 `test_test_calibration_is_registered_only_inside_a_test` (L1356-1358) only checks that the helper's own `monkeypatch.setitem` worked.
  - Task 7 `test_every_builtin_provider_has_a_noop_preflight` (L2174-2180): its Voxtral and ElevenLabs halves assert nothing beyond "didn't raise", and the `monkeypatch`/`tmp_path` fixtures are unused.
  - Task 12's parametrized `test_the_known_runaway_transcripts_fail` may run over an empty `RUNAWAY_TRANSCRIPTS`, and the plan explicitly allows that (L5278, L5306, L5370). It then silently skips.
  - Several constant-pin tests (`TTS_PINS`, `HOSTED_BACKENDS`, `PREFLIGHT_TEXT`, `QWEN3_TTS_1_7B_BASE`) are deliberate change-detectors.
- **Verbatim duplication:**
  - C2 above.
  - Test helpers: test_verify's `Scripted` (L4083) is near-identical to test_quality's (L3594). test_verify's `_forbid_scriptwrite` (L4218) copies test_voice_cmd's (L2207). The scriptwrite notes JSON is repeated at L3161-3168, L3687-3691 and L4335-4339 (plus the existing `_good_notes_json` copies). test_verify `_station` duplicates test_mlx_wiring `_home`.
  - Optional fix: move these into `tests/mlx_helpers.py`.
- **Swallowed errors:**
  - Task 12 `script_texts` does `except (OSError, ValueError): continue` (L4856), silently dropping unreadable manifests from the measurement. Count them into the data file.
  - Deliberate and visible, so probably fine: Task 7 keeps the pre-existing `except Exception: pass` around `speech.close()`. Task 13 turns an unload failure into a `note:` on stderr.

## Contradictions with the Global Constraints or the spec

- None of substance. Every strict surface, wire field, default and message I checked matches the spec.
- C4 (attribution) is the only clash with Global Constraints text, and the earlier scratchpad ruling already covers it.

## Steps that would leave the suite red at task end

- None found.
  - All `speech_provider_for` doubles are migrated in Task 5: test_tts, test_process 116-178, and test_run_cmd 318/430. No other call sites exist in src or tests.
  - All doubles that go through `_process_one` gain `preflight` in Task 7: TaggedProvider explicitly, CloseBlowsUpProvider by inheriting from FakeSpeechProvider.
  - The BILLYG fixture fix in Task 6 is required and is included.
  - No existing test enumerates the presenter subcommands.

(I logged nothing sensitive. One reading of `~/.emcee/config.toml` showed the live key in my own tool output only; it is not in this report or the log.)
