# mlx-audio 0.5.8 server probe (2026-10-12)

Evidence for `docs/superpowers/specs/2026-10-12-local-tts-presenter-pinning-design.md`,
"Unverified premises". Script: `scripts/mlx_audio_probe.py`. Server:
`~/tts-bakeoff/venvs/mlx` (mlx-audio 0.5.8), `--host 127.0.0.1`, M4 Mac mini.
Worktree baseline suite: 2607 passed (`./.venv/bin/pytest -q`: 2607 passed,
1 skipped, 7 deselected).

## Result

| row | value | evidence |
|---|---|---|
| stt_model | `mlx-community/whisper-large-v3-turbo-asr-fp16` (recall phil_ex 1.0, de_doelen 0.952) | check `stt_chosen` |
| wave_reads_server_wav | yes (1 ch, 2 B, 24000 Hz) | `speech_wav` (online and offline) |
| nframes_header_matches | yes — header 151680 = read 151680 = on-disk 151680 (offline run: 193920 = 193920 = 193920) | `speech_wav` |
| max_tokens_truncates_silently | yes (2.0 s at max_tokens 25, status 200) | `truncation` |
| midstream_exception | `httpx.RemoteProtocolError` | `corrupt_ref` and `midstream_kill` (both) |
| read_timeout_exception | `httpx.ReadTimeout` | `read_timeout` |
| connect_exception | `httpx.ConnectError` | `connect_error` |
| unknown_model_status_online | 404 `{"detail":"Model not found: 'mlx-community/no-such-model-emcee-probe' is not a known HuggingFace repo or local path"}` | `unknown_model` (online) |
| unknown_model_status_offline | 500 `{"detail":"Failed to load model 'mlx-community/no-such-model-emcee-probe': Cannot find an appropriate cached snapshot folder for the specified revision on the local disk and outgoing traffic has been disabled. ..."}` | `unknown_model` (offline) |
| missing_ref_status | 400 `{"detail":"Reference audio file not found: <absolute path>"}` | `missing_ref` |
| delete_model_status | 204, then 404 `{"detail":"Model 'mlx-community/whisper-large-v3-turbo-asr-fp16' not found"}` | `delete_model` |
| default_filename_status | 200 `{"text":"The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of de Doolin."}` | `default_filename` |

## How it was run

Port 8765, scratch dir `$S` (session scratchpad). Online server:
`(cd ~/tts-bakeoff && exec venvs/mlx/bin/python -m mlx_audio.server --host 127.0.0.1 --port 8765 --log-dir $S/logs) > $S/server.log 2>&1 &`,
waited with `timeout 270 sh -c 'until curl -sf http://127.0.0.1:8765/ ...'`,
PID from `lsof -tiTCP:8765 -sTCP:LISTEN`. Probe (online):
`PROBE_SERVER_OFFLINE=0 ./.venv/bin/python scripts/mlx_audio_probe.py --url http://127.0.0.1:8765 --ref ~/tts-bakeoff/refs/phil_ex.wav --ref-text-file ~/tts-bakeoff/refs/phil_ex.txt --stereo-clip ~/.emcee/samples/phil.wav --out-dir $S --checks root,speech_wav,truncation,preflight,stt,default_filename,delete_model,unknown_model,missing_ref,corrupt_ref,connect_error,read_timeout`.
The server was then stopped (`kill`, port confirmed free), restarted with
`HF_HUB_OFFLINE=1` exported, and probed with
`--checks root,speech_wav,unknown_model,midstream_kill --server-pid <pid>`;
`midstream_kill` SIGKILLed it, and afterwards `ps -p <pid>` reported nothing and
port 8765 had no listener.

Clips: `phil_ex.wav` is 1 ch / 16-bit / 24000 Hz / 12.9 s; `~/.emcee/samples/phil.wav`
(the `stereo_48k` clip) is 2 ch / 16-bit / 48000 Hz / 26.44 s. The `de_doelen` clip is
the server's own `speech_wav` output (Qwen3-TTS 1.7B Base, Phil's clone).

## STT transcripts

All requests: multipart file named `clip.wav`, `language=en`, `response_format=json`.
Gate: every clip 200 with non-empty text, and recall >= 0.8 on both `phil_ex` and
`de_doelen`. Candidates were tried in the order listed; the first to pass wins.

| model | phil_ex | de_doelen | stereo_48k | recall phil_ex | recall de_doelen | gate |
|---|---|---|---|---|---|---|
| `mlx-community/whisper-large-v3-turbo-asr-fp16` | 200 | 200 | 200 | 1.0 | 0.952 | **pass (chosen)** |
| `mlx-community/parakeet-tdt-0.6b-v3` | 200 | 200 | 200 | 1.0 | 0.905 | pass |
| `mlx-community/parakeet-tdt-0.6b-v2` | 200 | 200 | 200 | 0.95 | 0.905 | pass |
| `mlx-community/whisper-large-v3-turbo` (control) | 500 | `httpx.ReadError` | 500 | 0.0 | — | fail (expected) |

Wall times (seconds; the first `phil_ex` request of each model includes its download
and load): whisper-asr-fp16 46.22 / 1.08 / 1.77; parakeet-v3 69.91 / 0.35 / 0.91;
parakeet-v2 65.84 / 0.18 / 0.91.

**Chosen model, `mlx-community/whisper-large-v3-turbo-asr-fp16`:**

- `phil_ex` reference (`phil_ex.txt`): "It's the chemistry, basically. And the poetry
  that these guys bring to their music. It's like, we'll be playing along."
  Heard: "It's the chemistry, basically. And the poetry that these guys bring to their
  music. It's like, we'll be playing along." (identical)
- De Doelen sentence: "The tapes have always called the room the Rotterdam Civic Hall,
  but it was really the great hall of De Doelen."
  Heard: "The tapes have always called the room the Rotterdam Civic Hall, but it was
  really the great hall of de Doolin." (the one missed word is the venue name)
- 48 kHz stereo clip (no reference): "It's the chemistry, basically. And the poetry
  that these guys bring to their music. It's like, we'll be playing along. And all of
  a sudden, something totally new will just emerge. And these guys just pounce on it
  and take it to some cosmic level. And this happens over and over and over again."
  The server resamples and downmixes a 48 kHz stereo upload without complaint.

**Rejected / not chosen:**

- The two Parakeet models passed the gate but come after the Whisper candidate in the
  order. Their transcripts are visibly more verbatim: parakeet-v3 heard `phil_ex` as
  "It's the chemistry. Uh basically. And and and the thing that the the the the poetry
  that these guys bring to their music. It's uh it's like the we'll be playing along."
  De Doelen came back as "Didoin" (v3) and "Dedoolin" (v2).
- `mlx-community/whisper-large-v3-turbo` (mlx_whisper format, the control) does not
  work in the server, as expected: the server log shows `UserWarning: Could not load
  WhisperProcessor` at load and `ValueError: Processor not found. Make sure the model
  was loaded with a HuggingFace processor.` from `whisper.py:get_tokenizer` on every
  request, returned as `500 Internal Server Error`. Its `de_doelen` request never
  reached the server (no access-log line); it failed client-side with `httpx.ReadError`
  on the keep-alive connection that the previous 500 had left closed (see below).

## Consequences for the plan

- Task 8: `_GENERATION_FAILURES = (httpx.RemoteProtocolError, httpx.ReadError,
  httpx.ReadTimeout)` already covers the measured mid-stream class
  (`httpx.RemoteProtocolError`, from both a corrupt reference clip and a SIGKILLed
  server): **no change**. The speech response is `transfer-encoding: chunked` with no
  `content-length`, and its 200 status is committed before generation finishes, so a
  generation failure can only show up as a broken body, never as a status code.
- Task 8: duration is computed from frames actually read (`len(readframes)`), which
  **is** equal to the header count — header = read = on-disk in both live responses.
  The server writes a complete WAV with a correct header, so `_read_wav`'s docstring
  holds.
- Task 8: `max_tokens` truncation is silent and exact: max_tokens 25 gave status 200 and
  exactly 48000 frames = 2.000 s = 25 / 12.5. That is within the one-frame tolerance, so
  the 12.5 tokens/s assumption behind `cap_seconds` holds.
- Task 8: a corrupt `ref_audio` file is **not** a 4xx. The server returns 200, starts
  the stream, and then drops it (`miniaudio.DecodeError` server-side), so the client
  sees `httpx.RemoteProtocolError` and emcee reports "generation failed mid-response".
  A *missing* ref file is a clean 400 with the path in `detail`. Preflight sends the
  real ref clip, so it catches both before any spend.
- Task 8: an unknown model id gives 404 online but **500** under `HF_HUB_OFFLINE=1`,
  each with a readable `detail`. The plan's "any non-200 is a SpeechError carrying the
  body" handles both. No code should key on 404 specifically.
- Task 8: a client-side `httpx.ReadTimeout` does **not** stop the server. The next short
  request waited 75.4 s behind the abandoned generation. So retrying after a timeout
  would queue behind the job that is still running. The plan's choice not to retry
  `ReadTimeout` is right.
- Task 8 / 11 (minor): after an unhandled server exception that returns a 500 (seen on
  the transcription endpoint), uvicorn closes the connection. The next request on the
  same pooled `httpx.Client` connection then failed with `httpx.ReadError` without
  reaching the server. In Task 8 that would be labelled "generation failed
  mid-response" even though no generation started. It only matters after a 500, which
  already raises `SpeechError` and stops the clip, so it is a wording issue rather than
  a correctness one.
- Task 11: unloading with `DELETE /v1/models?model_name=<stt_model>` returns 204 the
  first time and **404** when the model is not loaded. Unload code must treat 404 as
  "already unloaded" and not as an error.
- Task 11: the multipart file name `clip.wav` is **not** load-bearing on this Mac. httpx's
  default file name also returned 200 with the correct text, probably because ffmpeg is
  installed here, so the plan's comment ("httpx's default file name maps to .mp3, which
  needs ffmpeg") is unproven either way. Keeping `clip.wav` costs nothing.
- Task 11/12/15: `stt_model = "mlx-community/whisper-large-v3-turbo-asr-fp16"`
  (about 1.6 GB, now in `~/.cache/huggingface/hub`).
- Task 11/12 (verification thresholds): Whisper misheard the foreign venue name
  ("De Doelen" became "de Doolin"), costing 1 of 21 words (recall 0.952) on a clean
  clip. All three passing models missed this word. Short clips heavy in proper nouns
  will score lower, and Task 12's measured thresholds need to allow for that.
- Task 11/12 (judgement for the controller): Whisper **cleans up disfluencies**. Its
  `phil_ex` transcript matches `phil_ex.txt` word for word, while both Parakeet models
  hear repeated words ("And and and the thing that the the the the poetry"). The
  bake-off's `scripts/asr.py` used `mlx-community/whisper-large-v3-turbo`, so
  `phil_ex.txt` was most likely a Whisper transcript (inferred, not checked), and the
  1.0 recall is partly circular. For a runaway or babble check, a verbatim transcriber
  might see repetition that Whisper smooths over. Parakeet v3 also passed the gate and
  is about 2–3x faster per clip once loaded (de_doelen 0.35 s vs 1.08 s, stereo 0.91 s vs 1.77 s). The brief's rule (first passing candidate, in
  order) picked Whisper; whether Parakeet would be better for verification is a
  judgement call that the probe does not settle.
- Generation varies between runs: the same De Doelen sentence came out as 6.32 s
  online and 8.08 s offline (unseeded sampling, as the spec expects).

## Appendix: raw JSON lines

Online run (`probe-online.jsonl`):

```json
{"check": "root", "status": 200}
{"check": "speech_wav", "status": 200, "wall_s": 21.27, "content_type": "audio/wav", "transfer_encoding": "chunked", "content_length": null, "body_len": 303404, "wave_ok": true, "channels": 1, "sampwidth": 2, "rate": 24000, "nframes_header": 151680, "frames_read": 151680, "frames_on_disk": 151680, "seconds": 6.32}
{"check": "truncation", "status": 200, "wall_s": 6.99, "max_tokens": 25, "cap_seconds": 2.0, "wave_ok": true, "channels": 1, "sampwidth": 2, "rate": 24000, "nframes_header": 48000, "frames_read": 48000, "frames_on_disk": 48000, "seconds": 2.0}
{"check": "preflight", "status": 200, "wall_s": 4.93, "wave_ok": true, "channels": 1, "sampwidth": 2, "rate": 24000, "nframes_header": 44160, "frames_read": 44160, "frames_on_disk": 44160, "seconds": 1.84}
{"check": "stt", "model": "mlx-community/whisper-large-v3-turbo-asr-fp16", "all_ok": true, "min_recall": 0.8, "reference": "It's the chemistry, basically. And the poetry that these guys bring to their music. It's like, we'll be playing along.", "de_doelen": "The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of De Doelen.", "results": {"phil_ex": {"status": 200, "wall_s": 46.22, "body": "{\"text\":\"It's the chemistry, basically. And the poetry that these guys bring to their music. It's like, we'll be playing along.\"}", "text": "It's the chemistry, basically. And the poetry that these guys bring to their music. It's like, we'll be playing along.", "recall": 1.0}, "de_doelen": {"status": 200, "wall_s": 1.08, "body": "{\"text\":\"The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of de Doolin.\"}", "text": "The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of de Doolin.", "recall": 0.952}, "stereo_48k": {"status": 200, "wall_s": 1.77, "body": "{\"text\":\"It's the chemistry, basically. And the poetry that these guys bring to their music. It's like, we'll be playing along. And all of a sudden, something totally new will just emerge. And these guys just pounce on it and take it to some cosmic level. And this happens over and over and over again.\"}", "text": "It's the chemistry, basically. And the poetry that these guys bring to their music. It's like, we'll be playing along. And all of a sudden, something totally new will just emerge. And these guys just pounce on it and take it to some cosmic level. And this happens over and over and over again."}}}
{"check": "stt", "model": "mlx-community/parakeet-tdt-0.6b-v3", "all_ok": true, "min_recall": 0.8, "reference": "It's the chemistry, basically. And the poetry that these guys bring to their music. It's like, we'll be playing along.", "de_doelen": "The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of De Doelen.", "results": {"phil_ex": {"status": 200, "wall_s": 69.91, "body": "{\"text\":\"It's the chemistry. Uh basically. And and and the thing that the the the the poetry that these guys bring to their music. It's uh it's like the we'll be playing along.\"}", "text": "It's the chemistry. Uh basically. And and and the thing that the the the the poetry that these guys bring to their music. It's uh it's like the we'll be playing along.", "recall": 1.0}, "de_doelen": {"status": 200, "wall_s": 0.35, "body": "{\"text\":\"The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of Didoin.\"}", "text": "The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of Didoin.", "recall": 0.905}, "stereo_48k": {"status": 200, "wall_s": 0.91, "body": "{\"text\":\"It's the chemistry, basically. And and and the thing that the the the the poetry that these guys bring to their music. It's uh it's like the we'll be playing along and all of a sudden something totally new will will just emerge and these guys just pounce on it and and take it take it to some cosmic level. And it's this happens over and over and over again.\"}", "text": "It's the chemistry, basically. And and and the thing that the the the the poetry that these guys bring to their music. It's uh it's like the we'll be playing along and all of a sudden something totally new will will just emerge and these guys just pounce on it and and take it take it to some cosmic level. And it's this happens over and over and over again."}}}
{"check": "stt", "model": "mlx-community/parakeet-tdt-0.6b-v2", "all_ok": true, "min_recall": 0.8, "reference": "It's the chemistry, basically. And the poetry that these guys bring to their music. It's like, we'll be playing along.", "de_doelen": "The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of De Doelen.", "results": {"phil_ex": {"status": 200, "wall_s": 65.84, "body": "{\"text\":\"It's the chemistry, basically. And the thing that the the poetry that these guys bring to their music is like we'll be playing along.\"}", "text": "It's the chemistry, basically. And the thing that the the poetry that these guys bring to their music is like we'll be playing along.", "recall": 0.95}, "de_doelen": {"status": 200, "wall_s": 0.18, "body": "{\"text\":\"The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of Dedoolin.\"}", "text": "The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of Dedoolin.", "recall": 0.905}, "stereo_48k": {"status": 200, "wall_s": 0.91, "body": "{\"text\":\"It's the chemistry, basically. And the thing that the the the poetry that these guys bring to their music is uh it's like that we'll be playing along and all of a sudden something totally new will will just emerge and these guys just pounce on it and and take it take it to some cosmic level and this this happens over and over and over again.\"}", "text": "It's the chemistry, basically. And the thing that the the the poetry that these guys bring to their music is uh it's like that we'll be playing along and all of a sudden something totally new will will just emerge and these guys just pounce on it and and take it take it to some cosmic level and this this happens over and over and over again."}}}
{"check": "stt", "model": "mlx-community/whisper-large-v3-turbo", "all_ok": false, "min_recall": 0.8, "reference": "It's the chemistry, basically. And the poetry that these guys bring to their music. It's like, we'll be playing along.", "de_doelen": "The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of De Doelen.", "results": {"phil_ex": {"status": 500, "wall_s": 0.76, "body": "Internal Server Error", "recall": 0.0}, "de_doelen": {"outcome": "raised", "exc_class": "httpx.ReadError", "exc": "[Errno 54] Connection reset by peer"}, "stereo_48k": {"status": 500, "wall_s": 0.39, "body": "Internal Server Error"}}}
{"check": "stt_chosen", "model": "mlx-community/whisper-large-v3-turbo-asr-fp16"}
{"check": "default_filename", "status": 200, "body": "{\"text\":\"The tapes have always called the room the Rotterdam Civic Hall, but it was really the great hall of de Doolin.\"}"}
{"check": "delete_model", "first": 204, "second": 404, "second_body": "{\"detail\":\"Model 'mlx-community/whisper-large-v3-turbo-asr-fp16' not found\"}"}
{"check": "unknown_model", "status": 404, "wall_s": 0.09, "body": "{\"detail\":\"Model not found: 'mlx-community/no-such-model-emcee-probe' is not a known HuggingFace repo or local path\"}", "hf_hub_offline": "0"}
{"check": "missing_ref", "status": 400, "body": "{\"detail\":\"Reference audio file not found: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-local-tts/34804e6e-d345-4305-9f38-4fdc4fe2b5c1/scratchpad/probe/nope.wav\"}"}
{"check": "corrupt_ref", "outcome": "raised", "exc_class": "httpx.RemoteProtocolError", "exc": "peer closed connection without sending complete message body (incomplete chunked read)"}
{"check": "connect_error", "outcome": "raised", "exc_class": "httpx.ConnectError", "exc": "[Errno 61] Connection refused"}
{"check": "read_timeout", "outcome": "raised", "exc_class": "httpx.ReadTimeout", "exc": "timed out"}
{"check": "after_timeout_next_request", "status": 200, "wait_s": 75.4}
```

Offline run (`probe-offline.jsonl`, server started with `HF_HUB_OFFLINE=1`):

```json
{"check": "root", "status": 200}
{"check": "speech_wav", "status": 200, "wall_s": 19.37, "content_type": "audio/wav", "transfer_encoding": "chunked", "content_length": null, "body_len": 387884, "wave_ok": true, "channels": 1, "sampwidth": 2, "rate": 24000, "nframes_header": 193920, "frames_read": 193920, "frames_on_disk": 193920, "seconds": 8.08}
{"check": "unknown_model", "status": 500, "wall_s": 0.63, "body": "{\"detail\":\"Failed to load model 'mlx-community/no-such-model-emcee-probe': Cannot find an appropriate cached snapshot folder for the specified revision on the local disk and outgoing traffic has been disabled. To enable repo look-ups and downloads online, set 'HF_HUB_OFFLINE=0' as environment variab", "hf_hub_offline": "1"}
{"check": "midstream_kill", "outcome": "raised", "exc_class": "httpx.RemoteProtocolError", "exc": "peer closed connection without sending complete message body (incomplete chunked read)"}
```
