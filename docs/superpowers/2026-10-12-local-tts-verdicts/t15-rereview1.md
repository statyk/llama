# t15-rereview1 — re-review of Task 15 fix round (55a0b3f..d94cd90)

### Finding Verdicts
- **IMPORTANT 1 (Rollback config steps)**: ADDRESSED. The new paragraph is at README.md:539-545. I checked it against `git show v2.8.1:packages/emcee/src/emcee/config.py`. In v2.8.1, `TTSConfig(_StrictModel)` accepts only `backend, voice, voice_clone, model, api_key, chunk, bed, bed_gain_db`. On this branch, `TTSConfig` adds exactly five keys: `voice_clone_text`, `voxtral`, `elevenlabs`, `mlx_audio` and `verify` (packages/emcee/src/emcee/config.py:92-117). No other section changed: `station`, `assign`, `llm`/`tiers` and the root are identical. The text removes all four tables. It drops `[tts] voice_clone_text`, which item 8 (README.md:526-527) is the only place to introduce. It moves the key back and restores `backend`. After these steps the config contains only keys v2.8.1 knows, so it loads. The added presenter claim, "pins to voxtral/elevenlabs are harmless: the old binary ignores them", is also correct for loading. I ran one more read-only `git show v2.8.1:packages/emcee/src/emcee/presenters.py` to verify it: v2.8.1's `Presenter(BaseModel)` uses pydantic's default `extra="ignore"`, so `tts`/`tts_model`/`voice_clone_text` are dropped silently. This matches README item 1 (README.md:405-406). The paragraph is correct and short (7 lines).
- **M1** (Presenters shape sentence states the exception): ADDRESSED. README.md:329 reads "absent = `[tts] backend`, except never mlx_audio: pin it explicitly". This matches `TTSConfig`'s docstring (config.py:95-97).
- **M2** (item 7 drops "after the calibration doc exists"): ADDRESSED. README.md:497-498. The doc exists at docs/superpowers/2026-10-12-mlx-audio-calibration.md.
- **M3** (item 4: "emcee's error points you there"): ADDRESSED. README.md:458. It is accurate: tts/mlx_audio.py:100/121/133 say "see the mlx-audio server log".
- **M4** (item 5 cross-references Memory, item 6): ADDRESSED. README.md:474 reads "this server (see Memory, item 6)".
- **M5** (CLAUDE.md "~2.6 s"): ADDRESSED. CLAUDE.md:803-805. Measured: preflight_en.wav is 2.625 s.
- **M6** (three long CLAUDE.md lines re-wrapped, no words changed): ADDRESSED. CLAUDE.md:111-115 (dry-run), 135-138 (presenter edit) and 191-195 (ElevenLabs/mlx_audio). I compared the diff token by token and the words are identical. The conventions line was re-wrapped too, and its only word change is the M5 one. The CLAUDE.md lines still over ~82 columns in that region (123, 129, 162) predate this branch and are outside the finding.
- **M7** (trailing space after `emcee voice <a dead package>`): ADDRESSED. README.md:504. A grep finds no trailing whitespace in README.md.

### New Breakage in the Fix Diff
None at Critical or Important level. Two cosmetic Nits:
- README.md:475 (`` `emcee/tts/verify.py`; `MISS_FRACTION` 0.15 is pending the operator's review (see the evidence ``) is about 96 columns, and the next line holds only "doc)." The M4 insertion re-flowed this paragraph raggedly. README.md:458 also grew to about 88 columns. Both render fine in Markdown.

### Out-of-Scope Observations (non-blocking, Minor)
1. **The rollback drops a moved `model` silently.** Item 8 (README.md:527) tells the operator to move `[tts] api_key`/`model` into the hosted tables. Rollback moves only the *key* back. A `[tts.voxtral] model` that is deleted rather than moved back to `[tts] model` still lets v2.8.1 load the config, but house voicing silently reverts to the default model. Possible fix: "move a hosted key (and `model`) back to `[tts]`".
2. **"Harmless" covers loading, not voicing.** v2.8.1 ignores a presenter's `tts` pin, so that presenter voices on the restored house backend. A voxtral pin under a voxtral house (roydemure, the cited example) is truly harmless. An `elevenlabs` pin under a voxtral house would send an ElevenLabs `voice` id to Voxtral at voicing time. This is an unlikely configuration.
3. Rollback names only Phil. Any other presenter pinned to `mlx_audio` at rollback time (item 7 allows this after a listen) needs the same `--clear-tts --clear-tts-model` and a Voxtral-suitable `--voice-clone`. Otherwise v2.8.1 voices its mlx reference clip on Voxtral. One clause such as "(and any other mlx_audio-pinned presenter)" would cover it.
4. `[tts] voice_clone_text` is dropped only "if the house voice was moved". v2.8.1 rejects that key whenever it is present. Today only item 8 sets it, so the conditional matches practice.

### Verdict
**Fix round:** All findings addressed, no new Critical/Important breakage.
