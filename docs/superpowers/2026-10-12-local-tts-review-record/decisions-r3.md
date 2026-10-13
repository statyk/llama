# Round-3 decisions: operator-requested scope additions (2026-10-12)

These are design changes the operator decided, not review findings. Apply exactly; where a removed item from earlier rounds comes back, restore it in the form stated here (not its earlier form). Keep the spec tight.

## 1. House voice and `emcee say` support `mlx_audio` (reverses the earlier narrowing)

- Remove the rule "`[tts] backend = "mlx_audio"` is a config error" and the matching Out-of-scope entry.
- `[tts]` gains `voice_clone_text` (transcript of `[tts] voice_clone`). With `[tts] backend = "mlx_audio"`: `[tts] voice_clone` and a non-blank `voice_clone_text` are required; a `[tts] voice` preset is a config error (mlx is clone-only).
- `emcee say`: `--clone PATH` gains `--clone-text TEXT`, required (non-blank) when the house backend is `mlx_audio`; `say --voice` with a `mlx_audio` house is a usage error. `say --presenter` follows the presenter's pin (already specified). `say` with no voice flags uses the house voice, including its transcript.
- The factory's required `clone_text` argument carries `[tts] voice_clone_text` (house), the presenter's transcript (presenter), or `--clone-text` (say).

## 2. Hosted backend keys: per-backend subtables (restored, operator chose this)

```toml
[tts.voxtral]       # api_key, model     (MISTRAL_API_KEY env still wins over api_key)
[tts.elevenlabs]    # api_key, model     (ELEVENLABS_API_KEY env still wins)
```
- A subtable applies whenever that backend is used — as the house backend or as a pin.
- Legacy `[tts] api_key`/`model` remain valid only while `[tts] backend` is a hosted backend, and then mean that backend's `api_key`/`model` exactly as today (the live config keeps working unchanged). Setting the same key both in `[tts]` and in the house backend's subtable is a config error naming both locations.
- With `[tts] backend = "mlx_audio"`, `[tts] api_key`/`model` are a config error whose message names `[tts.voxtral]`/`[tts.elevenlabs]` (for keys) and `[tts.mlx_audio] model` (for the model).
- Replace the "non-house hosted pin takes its key from env only" rule with: key = env var, else the backend's subtable `api_key`, else (house backend only) legacy `[tts] api_key`; model = the subtable's `model`, else (house only) legacy `[tts] model`, else the provider default. Presenter `tts_model` stays mlx-only.
- Subtables are strict (`_StrictModel`).

## 3. Runaway guard (always on for `mlx_audio`)

- Per request, `max_tokens` is capped in proportion to the text's length (replacing the flat 4000), so one sentence cannot generate minutes of audio. The cap formula's constants come from the calibration task (item 5).
- After each `mlx_audio` synthesis, the returned audio's duration is checked against the text's length; a clip implausibly long (or short) for its text is a guard failure. Constants from item 5.
- A guard failure retries that request once (output is non-deterministic); a second failure is a `SpeechError` naming the segment and the sentence, so the package fails rather than airing it. Evidence: the bake-off's Qwen 0.6B turned one set1 sentence into 320 s of babble (clip 432 s instead of ~120 s, WER 52%).

## 4. Transcript verification (optional, covers mlx and optionally Voxtral)

```toml
[tts.mlx_audio]
stt_model = "..."      # speech-to-text model served by the same mlx-audio server

[tts.verify]
backends = []          # default: off. e.g. ["mlx_audio"] or ["mlx_audio", "voxtral"]
```
- When a synthesis's backend is listed in `[tts.verify] backends`, the returned audio (per sentence on the chunked path, per segment otherwise) is transcribed via the server's `/v1/audio/transcriptions` (`stt_model`, `response_format=json`) and compared with the text that was sent. The comparison normalizes both sides (case, punctuation, numbers/ordinals — emcee's speech text spells numbers out, Whisper writes digits) and fails only on **gross** mismatch: too few of the script's words recovered, or a transcript far longer than the script. It must tolerate a wrong word or two per sentence (ASR itself misrenders proper nouns: "De Doelen" fails on Voxtral too). Thresholds come from item 5.
- A verification failure retries that synthesis once; a second failure is a `SpeechError` naming the segment, the sentence, and both texts. For Voxtral the retry costs one extra call for the failed sentence only.
- `[tts.verify] backends` non-empty requires `[tts.mlx_audio] stt_model`; a backend name not in (`mlx_audio`, `voxtral`, `elevenlabs`) is a config error.
- **Never silently skipped:** when verification applies to a package, preflight also checks the STT model (one transcription of a short in-memory clip) before any spend; an unreachable server or unloadable STT model fails the package before LLM spend and before the manifest clear — it never voices unverified. Add this to Stakes as a strict-surface clause. This means a Voxtral presenter depends on the local server when `"voxtral"` is listed — state it.
- Clips served from the render cache are not re-verified (they were verified when rendered). State it.
- `emcee say` verifies too when its backend is listed (no preflight; a dead server fails its first check).

## 5. Calibration task (constants are measured, not guessed)

- The guard's cap/duration constants and the verification thresholds are set by a measurement step in the implementation plan: render ~50 unseeded sentences (several presenters' clips, Phil included) through the real server, record per-sentence duration/characters and per-sentence transcript match, and pick constants that pass every clean sentence with margin and fail the bake-off's known runaway (Qwen 0.6B set1). Record the data and the chosen constants in an in-repo evidence doc; the constants then cite it (project convention for measured do-not-retune constants). This replaces/absorbs the existing "~50 unseeded sentences" pre-go-live gate premise: the gate becomes this task plus a go-live listen.

## 6. `--transcribe` returns, reusing the verification STT client

- `emcee presenter edit/add --transcribe` drafts `voice_clone_text` via the same `/v1/audio/transcriptions` client and `[tts.mlx_audio] stt_model`, prints the draft, writes only on confirmation; mutually exclusive with `--voice-clone-text`. Do NOT add a `DELETE /v1/models` unload (the STT model is expected to stay resident when verification is on).
- Note the bake-off's evidence: `mlx-community/whisper-large-v3-turbo` (mlx_whisper format) does not load in mlx-audio's server (its Whisper loader needs processor files); the server supports other STT families (Whisper with processor files, Parakeet, Qwen3-ASR, …). The plan's first task confirms a loadable `stt_model` by one live request. The runbook documents `mlx_whisper` on the CLI as the fallback for drafting a transcript by hand.

## 7. Memory and docs

- Runbook memory note: with verification on, the server holds the TTS model(s) and the STT model resident.
- Testing section: add tests for every new rule above (house mlx validation; `say --clone-text` / `--voice` with mlx house; subtables + legacy-key validity + duplicate error + mlx-house legacy-key error; guard retry-then-fail; verification pass/fail/retry, normalization of numbers, never-skipped when STT unreachable (no LLM spend, manifest bytes unchanged), cache hits not re-verified, voxtral verification only when listed).
