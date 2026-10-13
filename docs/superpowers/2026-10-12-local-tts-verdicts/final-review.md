# Final whole-branch review: `local-tts` (7c93250..d94cd90)

Reviewer: Opus (final-review). I made no edits to the checkout. Mutants ran only in a scratch `git archive` copy, with the copy's sources shadowing via `PYTHONPATH`. Shadowing was proven by `emcee.__file__` resolving inside the copy.

**Suite.** `./.venv/bin/pytest -q` at d94cd90 gives **2900 passed, 1 skipped, 8 deselected**. That matches the implementers' report. `emcee.__file__` resolves inside the worktree.

## Strengths

- **Strict surface 1 (never silently fall back) holds structurally:**
  - `speech_provider_for(config, resolution, *, voice, clone_ref, clone_text)` has no defaults and never reads `[tts] backend`.
  - `resolve_tts` is pure.
  - The mlx branch can only build `MlxAudioProvider`.
  - `test_no_fallback_when_the_mlx_server_is_down` checks a hosted-construction spy across run, voice and say, and under both house shapes.
- **Strict surface 2 (before any spend) holds:**
  - `_process_one` runs in this order: `speech_for` (resolution and construction) → `preflight()` → the `--fresh` unlink → `rewrite_manifest(None, None)` → `process_package`.
  - `try/finally close` starts right after `speech_for`.
  - I mutated each step of that order (M1: preflight after the manifest clear; M8: unlink before preflight). The suite caught each one, with 17 and 11 failures, in tests that check manifest bytes, clip bytes and LLM task counts.
- **Cache integrity:**
  - `QualitySpeech` keeps the inner `.voice`/`.model`.
  - mlx identity hashes clip + `\0` + the stripped transcript.
  - Voxtral's identity is unchanged by the refactor. I checked that the house and an unpinned presenter produce the same `voice`/`model` as before, so upgrading does not invalidate the cache.
  - A failing segment raises before `atomic_write_bytes`, so no defective clip is cached. The sidecar is updated only after a successful render.
- **Backward compatibility:**
  - I loaded the live `~/.emcee/config.toml` under the new strict `TTSConfig`, printing only booleans. It loads: house voxtral, verify `[]`, no `[tts] model`.
  - All five live presenter TOMLs load under the strict `Presenter`. They use only known keys and hold absolute clip paths.
  - The unpinned path keeps the same model and key resolution.
- **Cross-task integration lines up end to end:**
  - CLI → `resolve_tts` → factory → `_quality` → `MlxAudioProvider` (guard) / `Verifier` → `render_speech_mp3` (chunked WAV, bed WAV, plain MP3) → `_synthesize_dj_audio`, which tags `.segment` on `SpeechDefect`.
  - `say` goes through `ad_hoc_speech` → `speech_for`/the resolver for every branch.
  - The hosted verification preflight uses the bundled clip. `packaging/emcee.spec` already runs `collect_data_files("emcee.data")`, so `preflight_en.wav` ships in the signed binary.
- **Tests verify real behaviour:**
  - Eight strict-surface mutants were all caught. These covered: preflight order, unlink order, an unpinned presenter inheriting mlx, the hosted verify preflight skipping its clip, mlx left unwrapped with verify off, the guard skipped on WAV, the nothing-heard rule removed, and quality changing the cache identity.
  - Everything is offline over `httpx.MockTransport`. `conftest.py` strips ambient API keys.
- **Repo rules:**
  - No llama import in emcee src.
  - No STT model id in src code. The one occurrence is a commented example in the `config init` template, which is documentation, not a default.
  - **No secret anywhere in the branch.** I compared the live key from config/env against the full branch diff, the commit messages, and every file under `.superpowers/`, `docs/`, `scripts/` and `packages/emcee`. I checked the whole key and its 12-character prefix and printed booleans only. Neither appears anywhere.
- **Measured constants are cited and pinned:**
  - The guard's clean edges, the Chatterbox and 0.6B runaways, and the cap-margin rule at six lengths are all pinned.
  - The worst clean transcripts and the known runaway transcripts are pinned.
  - The evidence doc is thorough and honest about its limits.

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

None. I found no defect that can air a bad clip, spend money behind a configuration error, damage a voiced package or break an existing config, on the live station's configuration or the defaults.

### Minor (Nice to Have)

1. **The adopted verification thresholds are pinned only from below** (`packages/emcee/tests/test_calibration_measured.py:120-125`).
   - What's wrong: in the scratch copy, raising `MISS_FRACTION` 0.15→0.35 left the suite green (709/709 emcee). So did raising `EXTRA_FRACTION` 0.25→0.6. Only tightening is caught: 0.05 fails the Drumz/Wharf Rat clean edge. The test only asserts the Step 3 ceilings.
   - Why it matters: the evidence doc's adopted values can drift looser with no red test. That is the "green suite ≠ pinned" pattern.
   - How to fix: add `assert (MISS_FLOOR, MISS_FRACTION, EXTRA_FLOOR, EXTRA_FRACTION) == (2, 0.15, 4, 0.25)` citing the doc, and the same for the Qwen `ModelCalibration`. Do it once Shawn has ratified 0.15, or now with a comment saying it is pending.
2. **The hosted-WAV MP3 encode is unchecked** (`packages/emcee/src/emcee/tts/mlx_audio.py:34-38`, reached from `tts/quality.py:64`). This is predecessor flag 2, confirmed and refined.
   - What's wrong: a valid WAV with a sample width other than 2 (24/32-bit int) passes `wave` and passes verification, because the STT hears the true audio. `_encode_mp3` then encodes the bytes as int16, which is noise.
   - Why it matters: this is a silent path to airing damaged audio, but only when all of these hold: Voxtral is listed in `[tts.verify]`, the path is unchunked (`[tts] chunk = false`, or `say --no-chunk` with no bed), and Voxtral changes its WAV width. Today it returns 16-bit, and the default chunked path already checks this at `audio.py:138/183`. A float WAV raises `wave.Error` instead, which still fails the package, just with an untyped message.
   - How to fix: in `wav_to_mp3`, check `getsampwidth() == 2` and convert `wave.Error`/`EOFError` to `SpeechError`. That is about three lines.
3. **Dry-run says nothing about the house voice's own resolution** (`cli.py:_dry_run_marker`, run's dry-run branch).
   - What's wrong: under `[tts] backend = "mlx_audio"`, a house row (no presenter) prints `house` with no marker, even when `[tts.mlx_audio] model` is missing or uncalibrated. The real run then fails that package before any spend.
   - Why it matters: the spec covers presenters only, so this is spec-compliant. But an operator following runbook item 8 would reasonably expect dry-run to audit the voice they just moved.
   - How to fix: optionally, run `resolve_tts(config, None)` once for house rows when the house is mlx, and print `[unresolved: …]` or `[mlx_audio <model>]`.
4. **`--transcribe` does not expand `~` in a stored clip path** (`cli.py:_draft_transcript`).
   - What's wrong: it uses `Path(clip).read_bytes()` with no `expanduser()`. A legacy presenter file holding `~/…` (none on the live station; all five are absolute) gives "cannot read the voice clone" on `edit --transcribe` without `--voice-clone`. The provider itself does expand the path.
   - How to fix: `Path(clip).expanduser()`.

## Deferred-list triage

**Predecessor flags for this review:**

| item | verdict | reason |
|---|---|---|
| F1 dry-run loads by case-insensitive stem, run by configured id | defer | The spec mandates this lookup (§1, "`_presenter_file_exists`'s case-insensitive lookup"). The station's APFS is case-insensitive. On a case-sensitive filesystem the real run fails at `resolve_assignment`, before any spend, so the only effect is a wrong "resolves" label. The pre-existing `[missing]` marker already had the same divergence. |
| F2 `quality._attempt` → `wav_to_mp3` with no width check and no `wave.Error`→`SpeechError` | defer (cheap hardening recommended; Minor 2) | Latent: it needs Voxtral listed, the unchunked path, and an upstream format change. It is the one silent-noise path, so fold it in whenever this file is next touched. |
| F3 key printed into a subagent transcript | not-real for the branch (process only) | Verified: the live key (whole and 12-character prefix) is absent from the diff, the commit messages and every file under `.superpowers/`, `docs/`, `scripts/` and `packages/emcee`. Rotating it is Shawn's call. |

**Task 1–11 minors:**

| item | verdict | reason |
|---|---|---|
| T1 probe doc phrases 404-unload as an action item | not-real | `SttClient.unload` accepts 404 (`verify.py:163`). |
| T1 1.6 GB vs 1.5 GB | defer | Cosmetic. |
| T1 probe script `data.find`, fixed sleep, unclosed client | defer | One-off measurement script, plan-verbatim. |
| T2 mid-file import in `test_presenters.py` | defer | Style. |
| T2 `save_presenter` error embeds the pydantic dump | defer | Same style as the load path. Verbose, not wrong. |
| T3 template `[tts] backend` comment omits mlx_audio | not-real | Fixed: the template now says `or "mlx_audio" (local, …)`. |
| T3 duplicate-key test covers only the voxtral house | defer | The code path is generic (`getattr(self, self.backend)`). |
| T3 `timeout_s` has no positivity bound; whitespace `stt_model` | defer | Both fail at preflight, before any spend. |
| T4 RED written after the fact | not-real | Process note. The tests exist and are mutation-sensitive. |
| T5 elevenlabs clone wording | not-real | Reworded in 48dd265. |
| T5 `Presenter.voice_id` dead in src | defer | Dead-code cleanup. |
| T5 unreachable `or "[tts] api_key"` key_hint fallback | not-real | Harmless defensive default. |
| T5 pin test asserts only the backend | defer | Resolution fields are pinned in `test_resolve.py`. |
| T6 case-insensitive dry-run | defer | Same as F1. |
| T6 `_presenter_file` `iterdir()` outside try | defer | Pre-existing. An unreadable `presenters/` would break far more than dry-run. |
| T6 `speech_for` guard test passes on base | defer | Regression guard only. |
| T7 mid-module imports in `test_voice_cmd.py` | defer | Style. |
| T7 no run-level failed-preflight test | not-real | Covered by `test_run_continues_other_presenters_when_mlx_is_down`. |
| T8 ReadError after a prior 500 labelled mid-response | not-real | Wording only, one provider per package. |
| T8 float WAV reads as "unknown format: 3" | defer | Wording. It still fails closed. |
| T9 presenter-worded `_mlx_provider` branches untested | defer | Unreachable through `Presenter` validation. |
| T10 no chunked retry-then-succeed test | defer | `test_a_runaway_then_a_good_take_through_the_real_provider` covers the layer. |
| T10 retry notice doesn't name the sentence | defer | UX polish. The final `SpeechDefect` names the text and segment. |
| T11 `wav_to_mp3` | defer | Same as F2. |
| T11 `speech_bodies == []` proves nothing | defer | True, but by inspection hosted `inner.preflight()` is a no-op, and M3 shows the clip check itself is pinned. |
| T11 sidecar branch mostly unexercised | defer | Pre-existing persist-as-you-go logic, unchanged. |
| T11 no test lists elevenlabs in `[tts.verify]` | defer | Same code path as voxtral. ElevenLabs WAV is built 16-bit locally. |

**Task 12–15 items:**

| item | verdict | reason |
|---|---|---|
| T12 `--rescore` not enforced with `--reuse` | defer | One-off script. |
| T12 log appended afterwards | not-real | Process. |
| T12 `_DROPPED_G` folds a closing quote on a quoted phrase ending in "in" | defer | It can only cost a word on the script side, never give false credit. One quoted span in 129 scripts. The doc sentence at :143-145 is slightly inaccurate. |
| T12 test asserts `== 1` | defer | Freezes a conservative under-credit. `<= 2` would be better but it is harmless. |
| T12 note: `MISS_FRACTION` 0.15 | operator decision (not a defect) | See Recommendations. Verification is off by default, so merging does not activate it. |
| T13 `except Exception` vs `ValidationError` | defer | Equivalent today. |
| T13 edit loads before flag-conflict checks (exit 1 vs 2) | defer | Only for an unknown id plus conflicting flags. Brief-verbatim. |
| T14 add-side `--transcribe` + `--voice-clone-text` test | defer | The guard line exists (`cli.py` add). The edit side is tested. |
| T14 no unmocked `say --clone --clone-text` under an mlx house | defer | The wire contract is covered by `test_each_path_sends_the_presenters_transcript` and the provider tests. |
| T14 comment overstates unload order | defer | Comment only. |
| T14 double colon in the elevenlabs clone message | defer | Cosmetic. |
| T15 rollback moves only the hosted key, not `[tts.voxtral] model` | defer (not-real for this station) | The live config sets no model anywhere (checked as booleans). A one-word doc fix ("key and model") would make it general. |
| T15 rollback names only Phil | defer (mostly not-real) | Only Phil's `voice_clone` changes in the runbook. Other presenters pinned per item 7 keep their aired clip, so an old binary voices them on Voxtral from that same clip, as before. A new mlx-only presenter would be voiced on Voxtral from its clip. A one-sentence generalisation is cheap. |
| T15 "harmless" pins | defer | Overbroad only for an elevenlabs pin under a restored voxtral house. That fails the package after LLM spend and never damages a ready package. The station has no elevenlabs pins or config. A one-clause doc fix is optional. |
| T15 README reflow at :458/:475 | defer | Cosmetic. |

## Declined to judge

- **The three "pending Shawn's review" decisions on their merits**: `MISS_FRACTION` 0.15, the dropped-g fold, and memory option (a). These are operator calls. I checked only that the code and docs match what was recorded.
- **Qwen voice quality, the four Whisper-drafted reference transcripts, and the go-live listen.** These need an ear, and the runbook makes them prerequisites.
- **Re-deriving the calibration** from `2026-10-12-mlx-audio-calibration-data.json`. I took the doc's derivations as given and spot-checked only that the pinned edges satisfy the adopted guard.
- **Internals of `scripts/mlx_audio_calibrate.py` and `scripts/mlx_audio_probe.py`.** They are one-off measurement tools outside the runtime path, reviewed per task. I checked only that they never write to `~/.emcee` or print the key. `voxtral_key()` reads it in memory only.
- **Long unchunked mlx renders** (`say --no-chunk` over ~2,000+ characters), where the token cap can exceed `timeout_s` at RTF 2.8. This is outside the spec's scenarios, and it fails safe with a `SpeechError`.
- **Memory management, concurrent mlx models, and managing the server process.** All are out of scope per the spec.
- **Release cutting and signing.** Out of scope. I only confirmed that `packaging/emcee.spec` bundles `emcee.data`.
- **The planning, spec and review-record docs** under `docs/superpowers/`, beyond what the checks above needed.
- **Key rotation after the transcript escape.** Shawn's call.

## Recommendations

1. **Before or at the finish decision, Shawn should ratify or adjust** the three llama-9b decisions recorded as pending his review: `MISS_FRACTION` 0.15 (with the dropped-g fold), and memory option (a).
   - None is active on merge: verification defaults to off, and option (a) is runbook guidance only.
   - Once ratified, pin the exact values (Minor 1).
2. Optional single hardening commit, about 10 lines: Minor 2 (the `wav_to_mp3` width check), Minor 4 (`expanduser`) and the three one-clause rollback doc edits. None blocks the merge.
3. Operational gates stay as the runbook says: install the new binary before any pin, correct the four drafted transcripts, do the go-live listen, and take a memory reading on the first real `emcee voice`.

## Assessment

**Ready to merge?** Yes

**Reasoning:** The branch implements the spec, and all four strict surfaces hold.

- **Surfaces 1 and 2:** no silent fallback, and the before-spend ordering is correct. Both are enforced by construction and pinned by tests that fail under every ordering and fallback mutant I tried.
- **Surface 3:** a double quality failure fails the package and caches nothing.
- **Surface 4:** the live config and all five presenter files load unchanged, and the unpinned cache identity is unchanged.

The full suite is green and offline. Nothing secret is in the branch.

What remains is minor:
- A threshold pin that is one-sided.
- A latent unchecked hosted-WAV encode reachable only under non-default settings plus an upstream change.
- Two small UX gaps.
- Doc-level rollback generalisations.

Shawn's pending threshold and memory decisions are operator calls. They don't block the merge, because verification ships off.
