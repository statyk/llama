### Spec Compliance
- ✅ Spec compliant. Every Step 1-5 item of the brief and each controller ruling R1-R5 is present in 55a0b3f:
  - Template: `config.py:283` stt_model = `mlx-community/whisper-large-v3-turbo-asr-fp16`, in a comment only. `MlxAudioConfig.stt_model` still defaults to None (`config.py:81`).
  - README: setup line, `presenter edit` example, shape sentence, `say --clone` comment, and the runbook (items 1-9) inserted before "Upgrading from a pre-split llama".
  - CLAUDE.md: the five edits; anchors were matched across line wraps (R4).
  - R1 is the paragraph after item 5's config block. R2 is item 6. R3 is item 7's "Go-live prerequisite". R5 is the `[tts] backend` comment listing mlx_audio, and no case-insensitive "voxtral[- ]only" remains in README.md, CLAUDE.md or packages/emcee/src.
- ⚠️ Cannot verify from the diff: that the `mlx-audio[server,tts,stt]` extras resolve under `uv` with the constraints file. That needs a network install. The constraints file does pin `mlx-audio==0.5.8` (`docs/superpowers/2026-10-12-mlx-audio-requirements.txt:32`), which agrees with the runbook.

### Strengths
- **Accuracy against the code (named risk 1).** Every flag, key, default and message I checked exists as written:
  - `presenter edit` options `--tts`, `--tts-model`, `--clear-tts`, `--clear-tts-model`, `--clear-bed`, `--clear-voice-clone-text`, `--transcribe`, `--voice-clone`, `--voice-clone-text` (`cli.py:884-903`).
  - `presenter add --transcribe` requires `--voice-clone` (`cli.py:859`).
  - `say --clone-text` (`cli.py:517-579`).
  - Dry-run suffixes `[invalid presenters/<id>.toml]`, `[unresolved: …]` and `[<backend> <model>]` (`cli.py:310-316`).
  - `[tts.mlx_audio]` defaults url `http://127.0.0.1:8000` and timeout_s 600 (`config.py:78,80`).
  - `[tts.verify] backends` defaults to off (`config.py:89`).
  - The legacy `[tts] api_key`/`model` rules, including the duplicate-key error and the mlx-house rejection (`config.py:115-133`), which back runbook items 5 and 8.
  - The "pin tts explicitly" error (`tts/resolve.py:53`).
  - `--transcribe` unloads STT only when verify is off (`cli.py:788-791`).
  - `voice_clone` stored absolute (`cli.py:766`).
  - `speech_provider_for`'s keyword-only, no-default signature (`tts/__init__.py:60-62`).
  - `preflight()` runs before the `--fresh` unlink and the manifest clear (`cli.py:253-262`).
  - `CALIBRATED_MODELS`, `SpeechDefect`, `scripts/mlx_audio_calibrate.py`, the spec path and the tracked `preflight_en.wav` all exist.
- **Accuracy against the evidence doc (named risk 2).** Every figure matches `docs/superpowers/2026-10-12-mlx-audio-calibration.md`:
  - 6.6-7.0 GB between sentences, spikes of 10-12 GB, `phys_footprint_peak` 12 GB, and swap 1.4 → 5.5 GB on run 1 (lines 339-348).
  - 5068 MB and 2786 MB (lines 325-326).
  - 16 GB mini (line 19).
  - Verification recommendation and its three reasons (lines 370-376); `MISS_FRACTION` 0.15 pending review (line 377, matching `tts/verify.py:32`).
  - The four draft transcript paths (line 382).
  - Phil's 12.9 s / 24 kHz / mono excerpt (probe doc line 39).
  - The implementer was right not to invent "Whisper adds ~1.6 GB", which the doc does not contain.
- **Strict surface 4 (named risk 3).** README item 1 says to install the new release before pinning. Its claim that older binaries silently ignore the keys is TRUE: v2.8.1's `Presenter` is a plain `BaseModel` (`git show v2.8.1:…/presenters.py:15`). The unknown-key-is-an-error note is in item 1, the Presenters paragraph and the CLAUDE.md architecture bullet.
- **Rollback command (named risk 4).** `edit phil --clear-tts --clear-tts-model --voice-clone …/phil.wav` is valid. `--voice-clone` without `--voice-clone-text` also clears `voice_clone_text` (`cli.py:938-940`), so the result is a clean voxtral presenter.
- **No secrets (named risk 5).** Only `"..."` placeholders appear; nothing from ~/.emcee/config.toml.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **README.md item 9 (Rollback): the step is incomplete. After it, the downgraded binary will not load its config at all.** The step is plan-mandated text, and the gap is the brief's.
   - **What's wrong.** v2.8.1's `TTSConfig` is a `_StrictModel` (`extra="forbid"`) with no `voxtral`/`elevenlabs`/`mlx_audio`/`verify`/`voice_clone_text` fields (`git show v2.8.1:packages/emcee/src/emcee/config.py:15-25,61-74`). Item 5 tells the operator to add `[tts.mlx_audio]`, optionally `[tts.verify]`, and to move hosted keys into `[tts.voxtral]`/`[tts.elevenlabs]`. After "unpin Phil, then downgrade", every emcee command on the old binary fails with an unknown-key error.
   - **Why it matters.** It fails loudly, so nothing is voiced wrongly and no data is at risk. But the rollback is the procedure an operator runs under stress, and as written it does not end in a working station.
   - **Fix.** Add one sentence to item 9: before downgrading, also remove `[tts.mlx_audio]`, `[tts.verify]` and `[tts.voxtral]`/`[tts.elevenlabs]` from `~/.emcee/config.toml`. Move a hosted key back to `[tts] api_key` (or rely on the env var). If the house was moved (item 8), restore `[tts] backend` and drop `[tts] voice_clone_text`. Presenter pins to voxtral/elevenlabs (item 8's `roydemure`) are harmless to the old binary, which ignores them.

#### Minor (Nice to Have)
1. **README.md, Presenters shape sentence ("`tts` … absent = `[tts] backend`").** This is incomplete under an mlx_audio house: an unpinned presenter is then a resolution error, not an inherited backend. Item 8 says so, but the reference sentence should too. Suggested wording: "absent = `[tts] backend`, except never mlx_audio". The text is brief-mandated.
2. **README.md item 7, "after the calibration doc exists".** The doc now exists (`docs/superpowers/2026-10-12-mlx-audio-calibration.md`), so the clause is stale plan language. Drop it. The text is brief-mandated.
3. **README.md item 4, "emcee's error says so".** The error text is "see the mlx-audio server log" (`tts/mlx_audio.py:100,121,133,140`). It names no path, so the runbook is where `~/.mlx-audio/server.log` is learned. The sentence is acceptable, but "emcee's error points you there" would be more accurate.
4. **README.md item 5's R1 paragraph does not point to item 6.** The doc says to "weigh the memory finding above before enabling it" (calibration doc line 376). Item 6 does say "verification costs the Whisper resident set", but the recommendation paragraph itself has no cross-reference. A short "(see Memory, item 6)" would close this.
5. **CLAUDE.md conventions bullet, "the ~2 s bundled check clip".** The clip is 2.625 s (calibration doc, preflight table, "format" row). "~2.6 s" would be exact. The text is brief-mandated.
6. **CLAUDE.md, the three replaced lines.** The `--dry-run` addition, the `presenter add/edit/…` line and the "What this is" TTS sentence were inserted as single 200+-character lines in a file hard-wrapped at about 80 columns. This is cosmetic, but it makes future anchor matching (R4) harder. Re-wrap them.
7. **README.md:502 trailing space.** `emcee voice <a dead package> ` has a trailing space.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The documentation is accurate against the code and the evidence doc on every point checked, and covers the brief and R1-R5. The one Important gap is in the brief's own rollback text: unpinning before downgrading leaves the new `[tts.*]` subtables in place, and the strict v2.8.1 config refuses them. Item 9 needs one more sentence.
