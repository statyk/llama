### Spec Compliance
- ✅ Spec compliant. Every Result row matches the raw measurements, the STT selection followed the brief's rule, and the Consequences follow from the evidence.
  - `scripts/mlx_audio_probe.py` is **byte-identical** to the brief's Step 2 code block. I extracted the brief's code block and diffed it against the committed file: no difference.
  - The appendix JSON lines (doc lines 172-199) are **byte-identical** to `$S/probe-online.jsonl` (17 lines) and `$S/probe-offline.jsonl` (4 lines). I diffed both. `probe.json` and `offline/probe.json` hold the same check sequence, and `probe-online.rc` is `0`.
  - I checked all 12 Result rows (doc lines 30-41) against the JSON. Each one is backed by a measured field: `stt_chosen`, `speech_wav` channels/sampwidth/rate, header=read=on-disk 151680 (online) and 193920 (offline), truncation 48000 frames = 2.0 s at status 200, `RemoteProtocolError` in both `corrupt_ref` and `midstream_kill`, `ReadTimeout`, `ConnectError`, 404 online and 500 offline, 400, 204 then 404, and a 200 default filename. I found nothing inferred.
  - STT rule: `whisper-large-v3-turbo-asr-fp16` is the first entry in `STT_CANDIDATES`. It returned 200 with non-empty text on all three clips, with recall 1.0 on phil_ex and 0.952 on de_doelen, and it is the recorded `stt_chosen`. The script tries every candidate (the two Parakeets also passed; the control failed with 500s and a `ReadError`), which is how the brief's code is written.
  - Consequences vs the plan: I checked `docs/superpowers/plans/2026-10-12-local-tts-presenter-pinning.md`.
    - The quoted tuple `_GENERATION_FAILURES = (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout)` matches the plan's Task 8 code.
    - The plan's `_post` retries only `ConnectError`, so "the plan's choice not to retry ReadTimeout" is accurate.
    - Task 8's three STOP conditions (wave no, nframes no, truncation off by more than 0.08 s) correctly do not fire.
    - The "default file name maps to .mp3" comment the doc refers to is in the plan's Task 11 `SttClient`.
- ⚠️ Cannot verify from the diff or the JSONL:
  - That `phil_ex.txt` is a Whisper transcript. The doc labels this "inferred, not checked", which is honest.
  - The "M4 Mac mini" host label.
  - Whether the TTS actually pronounced "De Doelen" correctly. Only a human listening can tell.

### Strengths
- The evidence is easy to audit. The raw JSON is pasted verbatim, and every Result row names the check it comes from.
- I checked the surprising claims against the server logs, and all of them hold:
  - **Control model:** `Could not load WhisperProcessor` and `ValueError: Processor not found` appear in `server.log` (lines 39-53).
  - **Corrupt ref:** the server sends a 200 before `miniaudio.DecodeError` (`server.log` 265-283, and `_stream_inference_results raise chunk.error`).
  - **Dropped connections:** each unhandled 500 is followed by "Exception in ASGI application" and a new client port (49389 → 49640 → 49641). The control's de_doelen request has no access-log line, which confirms the doc's stale-connection `ReadError` explanation.
  - **Offline 500:** the response says `LocalEntryNotFoundError ... outgoing traffic has been disabled` (`server-offline.log` 78-79), which proves `HF_HUB_OFFLINE` was in effect.
- The kill really happened mid-stream. `midstream_kill` and `corrupt_ref` both failed with "incomplete chunked read". That message means the 200 headers and the chunked transfer had already been committed, so the doc's claim that the status is committed before generation ends is supported.
- The doc goes past the template with consequences later tasks can use:
  - unknown model is 404 online but 500 offline, so code must not key on 404;
  - after a ReadTimeout, the next request waited 75.4 s;
  - the `clip.wav` file name is not proven to be needed;
  - Whisper smooths disfluencies, which affects the runaway and babble checks in Tasks 11/12.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **Task 11 unload bullet reads as an action item, but the plan already does it** (`docs/superpowers/2026-10-12-mlx-audio-probe.md:142-144`). The doc says "Unload code must treat 404 as 'already unloaded'". The plan's `SttClient.unload` already accepts it (`if resp.status_code not in (200, 204, 404)`, around plan line 4573). Rewording it as "confirms the plan's 404 handling" would stop a Task 11 implementer from looking for a change that is not needed.
2. **Model size disagrees with the handback** (doc line 150). The doc says the whisper-asr-fp16 model is "about 1.6 GB"; the handback says 1.5G. This is cosmetic.
3. **Script fragility, plan-mandated because the script is verbatim from the brief:**
   - **First "data" match:** `wav_facts` uses `data.find(b"data")` (`scripts/mlx_audio_probe.py:282`). That finds the first such byte sequence, which could sit inside an earlier chunk such as LIST. Here all three frame counts agreed, so the results are unaffected.
   - **Fixed 8 s wait:** `midstream_kill` waits a fixed `time.sleep(8)` (line 472) and assumes the headers have been committed by then. The "incomplete chunked read" message proves after the fact that they were. The doc could cite that message as the evidence that the kill was mid-stream.
   - **Unclosed client:** the `read_timeout` check's `quick` client is never closed (line 447).
   - None of these needs a fix for this task.

### Assessment
**Task quality:** Approved
**Reasoning:** Every Result row and the appendix match the raw measurements exactly, the server logs confirm each surprising claim, the STT choice follows the brief's first-in-order rule, and the Task 8/11/12/15 consequences agree with the plan's code. The remaining items are minor wording points plus one judgement call for the controller: Whisper versus a verbatim STT such as Parakeet v3 for runaway verification, with a possibly circular recall of 1.0 on phil_ex. The probe correctly leaves that call open.

Notes for the controller (not defects of this task):
- Port 8765 is now held by an unrelated process (`lma-radio-ops/hls-start-test/serve.py`, per the implementer). Task 12 must run its own free-port check, as Global Constraints already require.
- About 6.1 GB of STT models were downloaded into `~/.cache/huggingface/hub`, including both Parakeets. Whether to delete them is the owner's decision.
