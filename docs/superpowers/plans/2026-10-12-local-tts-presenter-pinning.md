# emcee per-presenter TTS pinning + local `mlx_audio` backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a presenter (or the house voice) be pinned to a TTS backend — including a new free local `mlx_audio` backend served by `mlx_audio.server` — without any voice silently moving, falling back, or airing a runaway clip.

**Architecture:** A pure resolver (`emcee/tts/resolve.py`) turns config + presenter into a `TTSResolution` (backend, model, key) before any spend; `speech_provider_for` builds exactly that backend from the resolution (keyword-only, no defaults, so no call site can fall back to `[tts] backend`). The `mlx_audio` provider (`emcee/tts/mlx_audio.py`) speaks the server's `/v1/audio/speech` dialect with a per-model runaway guard (`emcee/tts/calibration.py`); a quality layer (`emcee/tts/quality.py`) owns the single re-synthesis on a guard or transcript-verification failure (`emcee/tts/verify.py`). A `preflight()` call on every provider runs before the `--fresh` unlink, the manifest clear and any LLM spend.

**Tech Stack:** Python (emcee requires >=3.11; the worktree venv is 3.14), pydantic v2, httpx (+ `httpx.MockTransport` in tests), stdlib `wave`, lameenc (via `emcee.audio._encode_mp3`), typer, pytest. Live side: mlx-audio 0.5.8's `mlx_audio.server` on this M4 Mac mini.

**Spec:** `docs/superpowers/specs/2026-10-12-local-tts-presenter-pinning-design.md` (approved; review mode Opus). Every task's implementer reads the spec section its task names.

## Global Constraints

- **Scope:** `packages/emcee` (src + tests), `scripts/` (two live measurement scripts), `docs/superpowers/` (evidence docs), `README.md` and `CLAUDE.md`. llama, herder and transmitter are untouched. emcee never imports llama (`packages/emcee/tests/test_no_llama_imports.py`).
- **Worktree venv (CLAUDE.md):** run everything from the worktree root `/Users/shawn/projects/llama/.claude/worktrees/local-tts` with its OWN venv: `./.venv/bin/pytest -q` (never a bare `pytest`, never the repo-root `.venv`). `./.venv/bin/python -c "import emcee; print(emcee.__file__)"` must print a path inside the worktree. Task 1 creates the venv.
- **Every task ends with the FULL suite green:** `./.venv/bin/pytest -q` (live tests are deselected by default via `pytest.ini`'s `-m 'not live'`). Offline and deterministic: tests use `httpx.MockTransport`, never a real server or the network.
- **Strict config:** every new config table and the `Presenter` model inherit emcee's `_StrictModel` (`emcee/config.py`, `extra="forbid"`).
- **Backend names, exactly:** presenter pins `voxtral`, `elevenlabs`, `mlx_audio`; `fake` is a `[tts] backend` for tests, never a pin. `[tts.verify] backends` accepts only `mlx_audio`, `voxtral`, `elevenlabs`.
- **Defaults, exactly:** `[tts.mlx_audio] url = "http://127.0.0.1:8000"`, `timeout_s = 600`, `model` and `stt_model` unset; `[tts.verify] backends = []`.
- **Never silently fall back (strict surface 1):** a presenter or house voice resolving to `mlx_audio` is voiced by the mlx provider or fails; nothing constructs another backend for it.
- **Before any spend (strict surface 2):** configuration-only failures — resolution errors, provider construction, `preflight()` — happen before the `--fresh` unlink, before `rewrite_manifest(pkg, dj_notes=None, dj_audio=None)` and before any `provider_for(...)` LLM call.
- **mlx wire contract:** `POST {url}/v1/audio/speech` JSON `{"model", "input", "response_format": "wav", "max_tokens", "ref_audio": <absolute path>, "ref_text"}` — nothing else (no temperature/top_k/top_p: mlx-audio 0.5.8's server defaults define the evaluated voice). Transcription: `POST {url}/v1/audio/transcriptions`, multipart file named `clip.wav`, form fields `model=<stt_model>`, `language=en`, `response_format=json`. Unload: `DELETE {url}/v1/models?model_name=<stt_model>`.
- **Preflight, exactly:** sentence `"Good evening, and welcome to the show."` (`PREFLIGHT_TEXT`), `max_tokens = 200`, response must be a 16-bit mono 24000 Hz WAV.
- **mlx identity:** `.voice = "clone:" + sha256(clip_bytes + b"\0" + transcript.strip().encode()).hexdigest()[:16]`; `.model` = the resolved model id.
- **Measured constants:** `CALIBRATED_MODELS` (the runaway-guard table) is EMPTY until Task 12 measures its first entry, so no `mlx_audio` voice resolves in production on guessed constants; tests register a test-only entry (`tests/mlx_helpers.py`). The four verification thresholds in `emcee/tts/verify.py` start at interim values (Task 11) and are replaced by measured ones in Task 12; verification is off by default meanwhile.
- **Live tasks** (1 and 12) run the server from `~/tts-bakeoff/venvs/mlx` (mlx-audio 0.5.8). Never `pip install` into that venv (it is the evaluated environment). Never modify anything under `~/.emcee/` or the station root; read only. Every server is handled the same way (shell state does not persist between Bash calls, so each block sets its own variables):
  - **start:** one Bash call with the tool's `run_in_background: true`: `(cd ~/tts-bakeoff && exec venvs/mlx/bin/python -m mlx_audio.server --host 127.0.0.1 --port <P> --log-dir <dir>) > <log> 2>&1 &`;
  - **wait:** one foreground Bash call with the tool `timeout` set to 300000 ms: `timeout 270 sh -c 'until curl -sf http://127.0.0.1:<P>/ >/dev/null; do sleep 2; done'` — re-run it while it exits 124 (never an unbounded foreground `sleep` loop);
  - **PID:** `lsof -tiTCP:<P> -sTCP:LISTEN > <pidfile>` once it answers (not `$!`);
  - **stop:** `kill $(cat <pidfile>)`, then `timeout 60 sh -c 'while lsof -tiTCP:<P> -sTCP:LISTEN >/dev/null; do sleep 1; done'; ! lsof -tiTCP:<P> -sTCP:LISTEN` — the port must be free before the next start.
- **Usage errors** in new CLI flag combinations print `error: <message>` to stderr and exit **2**.
- **Commits:** one or more per task, on branch `local-tts`, never `git stash`, never `git clean -x/-X`. Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2
  ```

## Review Focus

1. **A relative or `~` clip path** (`emcee presenter edit phil --voice-clone samples/phil_ex.wav`, a relative `[tts] voice_clone`, `say --clone ./x.wav`) — the server reads `ref_audio` from ITS working directory, so emcee must store and send an absolute resolved path. → Task 8 `test_ref_audio_is_sent_as_an_absolute_path`; Task 13 `test_edit_stores_voice_clone_as_an_absolute_path`.
2. **A transcript passed as `"$(cat phil_ex.txt)"`** carries a trailing newline or surrounding spaces — it must be accepted, and the voice identity must not change between the stripped and unstripped forms (or a re-save would silently re-render every clip). → Task 8 `test_voice_identity_ignores_surrounding_whitespace_in_transcript`.
3. **A sentence that is all numbers** ("1972." or "May eleventh, 1972.") leaves zero comparable words after number-dropping — verification must pass it on length alone, not divide by zero or fail it. → Task 11 `test_all_number_sentence_passes`.
4. **Re-pinning one presenter** (voxtral → mlx_audio → voxtral) must re-render rather than reuse the other backend's clips. → Task 9 `test_repinning_a_presenter_changes_the_cache_key`.
5. **The mlx server down during `emcee run`** must fail only the `mlx_audio` presenters' packages — each at preflight, manifest untouched — while hosted presenters' packages in the same run still voice. → Task 9 `test_run_continues_other_presenters_when_mlx_is_down`.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `packages/emcee/src/emcee/presenters.py` | modify | `Presenter` on `_StrictModel`; `tts`/`tts_model`/`voice_clone_text`; validation; save re-validates |
| `packages/emcee/src/emcee/config.py` | modify | `[tts] voice_clone_text`, `[tts.voxtral]`/`[tts.elevenlabs]`/`[tts.mlx_audio]`/`[tts.verify]`, key/verify validators, template |
| `packages/emcee/src/emcee/tts/calibration.py` | create | `ModelCalibration`, `CALIBRATED_MODELS`, guard math |
| `packages/emcee/src/emcee/tts/resolve.py` | create | `TTSResolution`, `TTSResolutionError`, `resolve_tts` (pure) |
| `packages/emcee/src/emcee/tts/__init__.py` | modify | `speech_provider_for(config, resolution, *, voice, clone_ref, clone_text)`; mlx branch; quality wrapping |
| `packages/emcee/src/emcee/tts/provider.py` | modify | `preflight()` in the protocol; `SpeechDefect` |
| `packages/emcee/src/emcee/tts/voxtral.py`, `elevenlabs.py`, `fake.py` | modify | `preflight()` no-op; `key_hint`; fake `preflight_fail` |
| `packages/emcee/src/emcee/tts/mlx_audio.py` | create | `MlxAudioProvider`, `PREFLIGHT_TEXT`, `wav_to_mp3` |
| `packages/emcee/src/emcee/tts/quality.py` | create | `QualitySpeech` (the single quality retry, preflight STT check) |
| `packages/emcee/src/emcee/tts/verify.py` | create | `SttClient`, `Verifier`, `transcript_problem`, thresholds, bundled clip loader |
| `packages/emcee/src/emcee/data/preflight_en.wav` | create (Task 12) | bundled ~2 s Kokoro clip of `PREFLIGHT_TEXT` |
| `packages/emcee/src/emcee/process.py` | modify | `speech_for`/`ad_hoc_speech` through the resolver |
| `packages/emcee/src/emcee/audio.py` | modify | annotate `SpeechDefect.segment` |
| `packages/emcee/src/emcee/cli.py` | modify | dry-run pins, `_process_one` order, `--fresh` move, `presenter edit`, add/list/show, `say` flags |
| `packages/emcee/tests/conftest.py` | create | no ambient `MISTRAL_API_KEY`/`ELEVENLABS_API_KEY` |
| `packages/emcee/tests/mlx_helpers.py` | create | test-only calibration entry, WAV builders, mock server handler |
| `scripts/mlx_audio_probe.py`, `scripts/mlx_audio_calibrate.py` | create | live evidence scripts |
| `docs/superpowers/2026-10-12-mlx-audio-probe.md`, `docs/superpowers/2026-10-12-mlx-audio-calibration.md` (+ `-data.json`) | create | evidence docs |
| `README.md`, `CLAUDE.md` | modify | runbook, architecture paragraph |

## Task order and dependencies

1 probe (live) → 2 presenter → 3 config → 4 resolution → 5 factory migration → 6 dry-run → 7 preflight hook → 8 mlx provider → 9 mlx wiring → 10 quality layer → 11 verification → 12 calibration (live) → 13 `presenter edit` → 14 add/list/show/say → 15 docs. Each task depends only on earlier ones.

---

### Task 1: Worktree venv + live mlx-audio server probe

**Implementer model:** Opus (live measurement; judgement on candidates and on what the results mean for Tasks 8, 11, 12).
**Live:** yes — needs the real `mlx_audio.server` on this Mac and network access to download one STT model.

Spec: "Unverified premises" (last two bullets) and section 2 (Errors, Audio contract). The spec requires this to be the plan's first task.

**Files:**
- Create: `scripts/mlx_audio_probe.py`
- Create: `docs/superpowers/2026-10-12-mlx-audio-probe.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the probe doc's **Result** table, which later tasks read by these exact row names: `stt_model` (the server-loadable STT model id that passed the recall gate), `wave_reads_server_wav` (yes/no), `nframes_header_matches` (yes/no), `max_tokens_truncates_silently` (yes/no), `midstream_exception` (fully-qualified httpx class name, or `200-empty-body`), `read_timeout_exception`, `connect_exception`, `unknown_model_status_online`, `unknown_model_status_offline`, `missing_ref_status`, `delete_model_status`, `default_filename_status`. Also: a working worktree `.venv`.

- [ ] **Step 1: Create the worktree venv and record the baseline**

```bash
cd /Users/shawn/projects/llama/.claude/worktrees/local-tts
python3 -m venv .venv
./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"
./.venv/bin/python -c "import emcee; print(emcee.__file__)"
./.venv/bin/pytest -q 2>&1 | tail -3
```

Expected: the import path is under `/Users/shawn/projects/llama/.claude/worktrees/local-tts/packages/emcee/src/emcee/`; the suite passes. Note the passed count for the evidence doc. If the import path points at the main checkout, stop and fix the venv before anything else.

- [ ] **Step 2: Write the probe script**

Create `scripts/mlx_audio_probe.py`:

```python
#!/usr/bin/env python3
"""Probe a running mlx-audio 0.5.8 server for the facts emcee's mlx_audio
backend depends on (spec 2026-10-12-local-tts-presenter-pinning-design.md,
"Unverified premises"): a server-loadable stt_model returning non-empty json
text, stdlib `wave` reading a raw server WAV response, and the httpx exception
a mid-stream generation failure produces. Evidence for
docs/superpowers/2026-10-12-mlx-audio-probe.md.

Run from the worktree venv against a server started from
~/tts-bakeoff/venvs/mlx (see that doc for the exact commands):

    ./.venv/bin/python scripts/mlx_audio_probe.py --url http://127.0.0.1:8765 \\
        --ref ~/tts-bakeoff/refs/phil_ex.wav \\
        --ref-text-file ~/tts-bakeoff/refs/phil_ex.txt \\
        --stereo-clip ~/.emcee/samples/phil.wav --out-dir <scratch dir> \\
        [--checks a,b,...] [--server-pid PID]

Prints one JSON object per check and writes them all to <out-dir>/probe.json.
Reads the clips; never writes outside --out-dir.
"""
import argparse
import io
import json
import os
import re
import signal
import socket
import threading
import time
import wave
from collections import Counter
from pathlib import Path

import httpx

TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
# Tried in order; the first that transcribes all three clips (200, non-empty
# text) AND recovers >= MIN_RECALL of the reference words on phil_ex and the
# De Doelen sentence wins. The last is the control: mlx_whisper format,
# expected NOT to load.
STT_CANDIDATES = [
    "mlx-community/whisper-large-v3-turbo-asr-fp16",
    "mlx-community/parakeet-tdt-0.6b-v3",
    "mlx-community/parakeet-tdt-0.6b-v2",
    "mlx-community/whisper-large-v3-turbo",
]
DE_DOELEN = ("The tapes have always called the room the Rotterdam Civic Hall, "
             "but it was really the great hall of De Doelen.")
PREFLIGHT = "Good evening, and welcome to the show."
LONG = " ".join([DE_DOELEN] * 6)
MIN_RECALL = 0.8
ALL_CHECKS = ["root", "speech_wav", "truncation", "preflight", "stt", "default_filename",
              "delete_model", "unknown_model", "missing_ref", "corrupt_ref",
              "connect_error", "read_timeout", "midstream_kill"]

results: list[dict] = []


def record(name: str, **facts) -> dict:
    entry = {"check": name, **facts}
    results.append(entry)
    print(json.dumps(entry), flush=True)
    return entry


def wav_facts(data: bytes) -> dict:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            n = w.getnframes()
            frames = w.readframes(n)
            width, ch, rate = w.getsampwidth(), w.getnchannels(), w.getframerate()
        read = len(frames) // (width * ch)
        # `wave` stops at the header's declared data size, so a header that
        # UNDER-states the data would still "match" `read`. Count the frames
        # physically present after the `data` chunk header as well; the
        # nframes_header_matches row is "yes" only if all three agree.
        at = data.find(b"data")
        on_disk = (len(data) - at - 8) // (width * ch) if at >= 0 else -1
        return {"wave_ok": True, "channels": ch, "sampwidth": width, "rate": rate,
                "nframes_header": n, "frames_read": read, "frames_on_disk": on_disk,
                "seconds": round(read / rate, 3)}
    except Exception as e:  # recorded, not raised: this IS the measurement
        return {"wave_ok": False, "wave_error": f"{type(e).__name__}: {e}",
                "head_hex": data[:16].hex(), "length": len(data)}


def recall(reference: str, heard: str) -> float:
    """The fraction of the reference's words (lower-cased, apostrophes and
    punctuation dropped) that the transcript contains."""
    def words(s: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", s.lower().replace("'", "").replace("’", ""))
    want = words(reference)
    found = sum((Counter(want) & Counter(words(heard))).values())
    return round(found / max(len(want), 1), 3)


def exc_facts(e: BaseException) -> dict:
    return {"outcome": "raised",
            "exc_class": f"{type(e).__module__}.{type(e).__qualname__}",
            "exc": str(e)[:300]}


def speech(client: httpx.Client, url: str, text: str, *, max_tokens: int, ref: str,
           ref_text: str, model: str = TTS_MODEL) -> tuple[httpx.Response, float]:
    body = {"model": model, "input": text, "response_format": "wav",
            "max_tokens": max_tokens, "ref_audio": ref, "ref_text": ref_text}
    t = time.time()
    r = client.post(f"{url}/v1/audio/speech", json=body)
    return r, round(time.time() - t, 2)


def transcribe(client: httpx.Client, url: str, model: str, data: bytes,
               filename: str | None = "clip.wav") -> httpx.Response:
    files = {"file": (filename, data, "audio/wav")} if filename else {"file": data}
    return client.post(f"{url}/v1/audio/transcriptions", files=files,
                       data={"model": model, "language": "en", "response_format": "json"})


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-text-file", required=True)
    ap.add_argument("--stereo-clip", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--checks", default=",".join(ALL_CHECKS))
    ap.add_argument("--server-pid", type=int, default=None)
    a = ap.parse_args()
    url = a.url.rstrip("/")
    ref = str(Path(a.ref).expanduser().resolve())
    ref_text = Path(a.ref_text_file).expanduser().read_text().strip()
    out = Path(a.out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    checks = set(a.checks.split(","))
    client = httpx.Client(timeout=1800)
    de_doelen_wav = b""

    if "root" in checks:
        r = client.get(f"{url}/")
        record("root", status=r.status_code)

    if checks & {"speech_wav", "stt", "default_filename"}:
        r, secs = speech(client, url, DE_DOELEN, max_tokens=400, ref=ref, ref_text=ref_text)
        de_doelen_wav = r.content
        (out / "de_doelen.wav").write_bytes(de_doelen_wav)
        record("speech_wav", status=r.status_code, wall_s=secs,
               content_type=r.headers.get("content-type"),
               transfer_encoding=r.headers.get("transfer-encoding"),
               content_length=r.headers.get("content-length"),
               body_len=len(r.content), **wav_facts(r.content))

    if "truncation" in checks:
        r, secs = speech(client, url, DE_DOELEN, max_tokens=25, ref=ref, ref_text=ref_text)
        record("truncation", status=r.status_code, wall_s=secs, max_tokens=25,
               cap_seconds=25 / 12.5, **wav_facts(r.content))

    if "preflight" in checks:
        r, secs = speech(client, url, PREFLIGHT, max_tokens=200, ref=ref, ref_text=ref_text)
        record("preflight", status=r.status_code, wall_s=secs, **wav_facts(r.content))

    chosen = None
    if "stt" in checks:
        clips = {"phil_ex": Path(ref).read_bytes(), "de_doelen": de_doelen_wav,
                 "stereo_48k": Path(a.stereo_clip).expanduser().read_bytes()}
        references = {"phil_ex": ref_text, "de_doelen": DE_DOELEN}  # stereo_48k has none
        for model in STT_CANDIDATES:
            texts, ok = {}, True
            for name, data in clips.items():
                t = time.time()
                try:
                    r = transcribe(client, url, model, data)
                except httpx.HTTPError as e:
                    texts[name] = exc_facts(e)
                    ok = False
                    continue
                entry = {"status": r.status_code, "wall_s": round(time.time() - t, 2),
                         "body": r.text[:400]}
                if r.status_code == 200:
                    try:
                        entry["text"] = r.json().get("text")
                    except ValueError:
                        entry["text"] = None
                ok = ok and r.status_code == 200 and bool((entry.get("text") or "").strip())
                if name in references:
                    entry["recall"] = recall(references[name], entry.get("text") or "")
                    ok = ok and entry["recall"] >= MIN_RECALL
                texts[name] = entry
            record("stt", model=model, all_ok=ok, min_recall=MIN_RECALL, reference=ref_text,
                   de_doelen=DE_DOELEN, results=texts)
            if ok and chosen is None:
                chosen = model
        record("stt_chosen", model=chosen)

    if "default_filename" in checks and chosen:
        r = transcribe(client, url, chosen, de_doelen_wav, filename=None)
        record("default_filename", status=r.status_code, body=r.text[:300])

    if "delete_model" in checks and chosen:
        r1 = client.delete(f"{url}/v1/models", params={"model_name": chosen})
        r2 = client.delete(f"{url}/v1/models", params={"model_name": chosen})
        record("delete_model", first=r1.status_code, second=r2.status_code,
               second_body=r2.text[:200])

    if "unknown_model" in checks:
        r, secs = speech(client, url, PREFLIGHT, max_tokens=50, ref=ref, ref_text=ref_text,
                         model="mlx-community/no-such-model-emcee-probe")
        record("unknown_model", status=r.status_code, wall_s=secs, body=r.text[:300],
               hf_hub_offline=os.environ.get("PROBE_SERVER_OFFLINE", "unknown"))

    if "missing_ref" in checks:
        r, _ = speech(client, url, PREFLIGHT, max_tokens=50, ref=str(out / "nope.wav"),
                      ref_text=ref_text)
        record("missing_ref", status=r.status_code, body=r.text[:300])

    if "corrupt_ref" in checks:
        bad = out / "corrupt.wav"
        bad.write_bytes(b"this is not audio " * 200)
        try:
            r, _ = speech(client, url, PREFLIGHT, max_tokens=50, ref=str(bad), ref_text=ref_text)
            record("corrupt_ref", outcome="returned", status=r.status_code,
                   body_len=len(r.content), body_head=r.content[:200].decode("latin-1"))
        except httpx.HTTPError as e:
            record("corrupt_ref", **exc_facts(e))

    if "connect_error" in checks:
        dead = f"http://127.0.0.1:{free_port()}"
        try:
            speech(client, dead, PREFLIGHT, max_tokens=50, ref=ref, ref_text=ref_text)
            record("connect_error", outcome="returned")
        except httpx.HTTPError as e:
            record("connect_error", **exc_facts(e))

    if "read_timeout" in checks:
        quick = httpx.Client(timeout=httpx.Timeout(5.0, read=0.5))
        try:
            speech(quick, url, LONG, max_tokens=2000, ref=ref, ref_text=ref_text)
            record("read_timeout", outcome="returned")
        except httpx.HTTPError as e:
            record("read_timeout", **exc_facts(e))
        # A timed-out request keeps generating server-side: time how long the
        # next short request waits behind it.
        t = time.time()
        r, _ = speech(client, url, PREFLIGHT, max_tokens=200, ref=ref, ref_text=ref_text)
        record("after_timeout_next_request", status=r.status_code,
               wait_s=round(time.time() - t, 1))

    if "midstream_kill" in checks and a.server_pid:
        holder: dict = {}

        def go():
            try:
                r, _ = speech(client, url, LONG, max_tokens=3000, ref=ref, ref_text=ref_text)
                holder.update(outcome="returned", status=r.status_code, body_len=len(r.content))
            except httpx.HTTPError as e:
                holder.update(exc_facts(e))

        th = threading.Thread(target=go)
        th.start()
        time.sleep(8)  # long enough for the 200 + headers to be committed
        os.kill(a.server_pid, signal.SIGKILL)
        th.join(60)
        record("midstream_kill", **holder)

    (out / "probe.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Start the server (online, so the STT candidates can download) and run the probe**

Pick a free port (check `lsof -iTCP:8765 -sTCP:LISTEN` prints nothing; otherwise use another). Use the scratch dir `S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/probe` for `--out-dir` and logs. Follow Global Constraints' server procedure.

Start (one Bash call, `run_in_background: true`):

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/probe
mkdir -p $S/logs
(cd ~/tts-bakeoff && exec venvs/mlx/bin/python -m mlx_audio.server --host 127.0.0.1 --port 8765 \
    --log-dir $S/logs) > $S/server.log 2>&1 &
```

Wait, then record the PID (one foreground Bash call, tool `timeout` 300000 ms; the bounded until-loop, not a Monitor; re-run while it exits 124, and if it has not answered after two runs read `$S/server.log` and stop):

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/probe
timeout 270 sh -c 'until curl -sf http://127.0.0.1:8765/ >/dev/null; do sleep 2; done' \
    && lsof -tiTCP:8765 -sTCP:LISTEN > $S/server.pid && cat $S/server.pid
```

Run the probe (one Bash call, `run_in_background: true`; poll `$S/probe-online.jsonl` in ≤ 270 s chunks — the STT downloads can take minutes):

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/probe
cd /Users/shawn/projects/llama/.claude/worktrees/local-tts
PROBE_SERVER_OFFLINE=0 ./.venv/bin/python scripts/mlx_audio_probe.py --url http://127.0.0.1:8765 \
    --ref ~/tts-bakeoff/refs/phil_ex.wav --ref-text-file ~/tts-bakeoff/refs/phil_ex.txt \
    --stereo-clip ~/.emcee/samples/phil.wav --out-dir $S \
    --checks root,speech_wav,truncation,preflight,stt,default_filename,delete_model,unknown_model,missing_ref,corrupt_ref,connect_error,read_timeout \
    2>&1 | tee $S/probe-online.jsonl
```

A candidate wins only if every clip returns 200 with non-empty text AND its `recall` is ≥ 0.8 on both `phil_ex` (against `phil_ex.txt`) and `de_doelen` (against the De Doelen sentence), all with `language=en`. If no candidate passes (`stt_chosen` is null), try further mlx-audio-loadable STT repos you can find on Hugging Face (`mlx-community/*whisper*-asr*`, `mlx-community/parakeet-*`, `Qwen/Qwen3-ASR-*` / `mlx-community/Qwen3-ASR-*`) by editing `STT_CANDIDATES` and re-running with `--checks stt`; if still none passes, STOP and report BLOCKED — verification and `--transcribe` depend on it.

- [ ] **Step 4: Re-run offline, then the mid-stream kill**

Stop the server and check the port is free:

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/probe
kill $(cat $S/server.pid)
timeout 60 sh -c 'while lsof -tiTCP:8765 -sTCP:LISTEN >/dev/null; do sleep 1; done'
! lsof -tiTCP:8765 -sTCP:LISTEN
```

Restart it offline (one Bash call, `run_in_background: true`), then wait and record the new PID exactly as in Step 3:

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/probe
(cd ~/tts-bakeoff && export HF_HUB_OFFLINE=1 && exec venvs/mlx/bin/python -m mlx_audio.server \
    --host 127.0.0.1 --port 8765 --log-dir $S/logs) > $S/server-offline.log 2>&1 &
```

Then (one foreground Bash call, tool `timeout` 600000 ms):

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/probe
cd /Users/shawn/projects/llama/.claude/worktrees/local-tts
PROBE_SERVER_OFFLINE=1 ./.venv/bin/python scripts/mlx_audio_probe.py --url http://127.0.0.1:8765 \
    --ref ~/tts-bakeoff/refs/phil_ex.wav --ref-text-file ~/tts-bakeoff/refs/phil_ex.txt \
    --stereo-clip ~/.emcee/samples/phil.wav --out-dir $S/offline \
    --checks root,speech_wav,unknown_model,midstream_kill --server-pid $(cat $S/server.pid) \
    2>&1 | tee $S/probe-offline.jsonl
```

`midstream_kill` SIGKILLs the server; it is the last check. Confirm the server process is gone and the port free afterwards (`ps -p $(cat $S/server.pid)` reports nothing; `! lsof -tiTCP:8765 -sTCP:LISTEN`).

- [ ] **Step 5: Write the evidence doc**

Create `docs/superpowers/2026-10-12-mlx-audio-probe.md` with these sections, filled from the two JSONL outputs (paste the JSON lines verbatim in an appendix):

````markdown
# mlx-audio 0.5.8 server probe (2026-10-12)

Evidence for `docs/superpowers/specs/2026-10-12-local-tts-presenter-pinning-design.md`,
"Unverified premises". Script: `scripts/mlx_audio_probe.py`. Server:
`~/tts-bakeoff/venvs/mlx` (mlx-audio 0.5.8), `--host 127.0.0.1`, M4 Mac mini.
Worktree baseline suite: <N> passed.

## Result

| row | value | evidence |
|---|---|---|
| stt_model | <id> (recall phil_ex <r>, de_doelen <r>) | check `stt_chosen` |
| wave_reads_server_wav | yes/no (<channels> ch, <sampwidth> B, <rate> Hz) | `speech_wav` |
| nframes_header_matches | yes/no — yes only if header <n> = read <m> = on-disk <k> | `speech_wav` |
| max_tokens_truncates_silently | yes/no (<seconds> s at max_tokens 25, status <s>) | `truncation` |
| midstream_exception | <class> | `corrupt_ref` and `midstream_kill` |
| read_timeout_exception | <class> | `read_timeout` |
| connect_exception | <class> | `connect_error` |
| unknown_model_status_online | <status> <body excerpt> | `unknown_model` (online) |
| unknown_model_status_offline | <status> <body excerpt> | `unknown_model` (offline) |
| missing_ref_status | <status> <body excerpt> | `missing_ref` |
| delete_model_status | <first>, then <second> | `delete_model` |
| default_filename_status | <status> <body excerpt> | `default_filename` |

## STT transcripts
<a per-candidate table: model, status per clip, recall on phil_ex and on de_doelen (gate: >= 0.8 on both), pass/fail; then, for the chosen model, phil_ex vs its reference transcript, the De Doelen sentence and the 48 kHz stereo clip; plus each rejected candidate's failure>

## Consequences for the plan
- Task 8: `_GENERATION_FAILURES` covers <classes>; <"no change" | "add <class>">.
- Task 8: duration is computed from frames actually read (`len(readframes)`), which <is/is not> equal to the header count.
- Task 11/12/15: `stt_model = "<id>"`.
- <anything surprising, e.g. a 200 with an empty body on generation failure>

## Appendix: raw JSON lines
````

- [ ] **Step 6: Commit**

```bash
git add scripts/mlx_audio_probe.py docs/superpowers/2026-10-12-mlx-audio-probe.md
git commit -m "docs(emcee): live mlx-audio server probe for the local TTS backend

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---

### Task 2: `Presenter` — strict base, pin fields, validation

**Implementer model:** Sonnet (mechanical: one source file, one test file, complete spec).
**Live:** no.

Spec: section 1, "Presenter TOML" and "Validation"; section 6 "Presenter validation matrix".

**Files:**
- Modify: `packages/emcee/src/emcee/presenters.py` (whole `Presenter` class and `save_presenter`)
- Test: `packages/emcee/tests/test_presenters.py`

**Interfaces:**
- Consumes: `emcee.config._StrictModel`.
- Produces:
  - `TTS_PINS: tuple[str, ...] = ("voxtral", "elevenlabs", "mlx_audio")` in `emcee.presenters`.
  - `Presenter` fields (in this order): `id: str`, `name: str`, `sex: str`, `voice: str | None = None`, `voice_clone: str | None = None`, `character: str`, `bed: str | None = None`, `tts: str | None = None`, `tts_model: str | None = None`, `voice_clone_text: str | None = None`. `voice_id` property unchanged.
  - `save_presenter(root, presenter)` re-validates the whole presenter and raises `PresenterError` (writing nothing) when invalid.

- [ ] **Step 1: Write the failing tests**

Append to `packages/emcee/tests/test_presenters.py`:

```python
# --- pins: tts / tts_model / voice_clone_text (spec section 1) ----------------

from emcee.presenters import TTS_PINS


def clone(**overrides):
    return make(voice=None, voice_clone="/refs/phil.wav", **overrides)


def test_pin_values_are_exactly_the_three_backends():
    assert TTS_PINS == ("voxtral", "elevenlabs", "mlx_audio")


def test_valid_pins():
    assert make(tts="voxtral").tts == "voxtral"
    assert make(tts="elevenlabs").tts == "elevenlabs"
    assert clone(tts="voxtral").tts == "voxtral"
    p = clone(tts="mlx_audio", voice_clone_text="It's the chemistry, basically.")
    assert p.tts == "mlx_audio" and p.tts_model is None
    p = clone(tts="mlx_audio", tts_model="mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
              voice_clone_text="Hello there.")
    assert p.tts_model == "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"


@pytest.mark.parametrize("bad", ["", "fake", "kokoro", "Voxtral", " voxtral"])
def test_tts_rejects_anything_but_the_three_pins(bad):
    with pytest.raises(ValidationError, match="tts must be one of"):
        make(tts=bad)


@pytest.mark.parametrize("bad", ["", "   "])
def test_tts_model_rejects_empty_strings(bad):
    with pytest.raises(ValidationError, match="tts_model must not be empty"):
        clone(tts="mlx_audio", tts_model=bad, voice_clone_text="Hello there.")


@pytest.mark.parametrize("tts", [None, "voxtral", "elevenlabs"])
def test_tts_model_only_with_mlx_audio(tts):
    with pytest.raises(ValidationError, match='tts_model is allowed only with tts = "mlx_audio"'):
        make(tts=tts, tts_model="some/model")


def test_voice_clone_with_elevenlabs_pin_rejected():
    with pytest.raises(ValidationError, match="elevenlabs"):
        clone(tts="elevenlabs")


def test_mlx_audio_pin_rejects_a_preset_voice():
    with pytest.raises(ValidationError, match="clone-only"):
        make(tts="mlx_audio", voice_clone_text="Hello there.")


@pytest.mark.parametrize("text", [None, "", "  \n\t "])
def test_mlx_audio_pin_requires_a_non_blank_transcript(text):
    with pytest.raises(ValidationError, match="needs voice_clone_text"):
        clone(tts="mlx_audio", voice_clone_text=text)


def test_voice_clone_text_is_allowed_ahead_of_a_pin_and_with_voxtral():
    assert clone(voice_clone_text="Hello.").voice_clone_text == "Hello."
    assert clone(tts="voxtral", voice_clone_text="Hello.").tts == "voxtral"


def test_pin_fields_roundtrip(tmp_path: Path):
    p = clone(tts="mlx_audio", tts_model="m/x", voice_clone_text="It's the chemistry.\n")
    save_presenter(tmp_path, p)
    loaded = load_presenter(tmp_path, "casey")
    assert loaded == p
    text = (tmp_path / "presenters" / "casey.toml").read_text()
    assert 'tts = "mlx_audio"' in text and 'tts_model = "m/x"' in text


def test_unpinned_presenter_file_has_no_pin_keys(tmp_path: Path):
    text = save_presenter(tmp_path, make()).read_text()
    assert "tts" not in text and "voice_clone_text" not in text


def test_unknown_key_is_a_load_error(tmp_path: Path):
    path = tmp_path / "presenters" / "phil.toml"
    path.parent.mkdir(parents=True)
    path.write_text('name = "Phil"\nsex = "male"\nvoice_clone = "/r.wav"\n'
                    'character = "x"\ntts = "mlx_audio"\ntts_modle = "typo"\n'
                    'voice_clone_text = "Hi."\n')
    with pytest.raises(PresenterError, match="tts_modle"):
        load_presenter(tmp_path, "phil")


def test_unknown_constructor_key_rejected():
    with pytest.raises(ValidationError):
        make(tts_modle="typo")


# The five live presenter files (2026-10-12) use only these key sets; each
# must still load under the strict base.
@pytest.mark.parametrize("body", [
    'name = "Billy G"\nsex = "male"\nvoice_clone = "/s/billgraham2.wav"\n'
    'bed = "/s/dead_bed3.wav"\ncharacter = """\nBrooklyn-bred.\n"""\n',
    'name = "K.C."\nsex = "male"\nvoice_clone = "/s/kurt1.wav"\n'
    'bed = "/s/aurora_bed.wav"\ncharacter = "Grunge kid."\n',
    'name = "Uncle Pen"\nsex = "male"\nvoice_clone = "/s/monroe1.wav"\n'
    'bed = "/s/bluegrass-bed.wav"\ncharacter = """\nAn old bluegrass musician.\n"""\n',
    'name = "Professor Chapman"\nsex = "male"\nvoice_clone = "/s/phil.wav"\n'
    'bed = "/s/dead_bed3.wav"\ncharacter = """\nProfessorial.\n"""\n',
    'name = "Roy Demure"\nsex = "male"\nvoice_clone = "/s/troymcclure2.wav"\n'
    'bed = "/s/dead_bed3.wav"\ncharacter = """\nModeled on Troy McClure.\n"""\n',
])
def test_live_presenter_shapes_still_load(tmp_path: Path, body):
    path = tmp_path / "presenters" / "p.toml"
    path.parent.mkdir(parents=True)
    path.write_text(body)
    assert load_presenter(tmp_path, "p").tts is None


def test_save_revalidates_a_model_copy_built_presenter(tmp_path: Path):
    # model_copy(update=...) skips validators; save must not let it through.
    bad = make().model_copy(update={"tts": "fake"})
    with pytest.raises(PresenterError, match="tts must be one of"):
        save_presenter(tmp_path, bad)
    assert not (tmp_path / "presenters" / "casey.toml").exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_presenters.py -q`
Expected: FAIL — `ImportError: cannot import name 'TTS_PINS'`.

- [ ] **Step 3: Implement**

In `packages/emcee/src/emcee/presenters.py` replace the imports, add `TTS_PINS`, and replace `Presenter` and `save_presenter`:

```python
import tomllib
from pathlib import Path

import tomli_w
from pydantic import ValidationError, model_validator

from emcee.config import _StrictModel
from emcee.errors import EmceeError
from emcee.workspace import atomic_write_text

# Backends a presenter may pin with `tts = "..."`. "fake" is deliberately not
# one: tests select it through [tts] backend.
TTS_PINS = ("voxtral", "elevenlabs", "mlx_audio")


class PresenterError(EmceeError):
    """A presenter file is missing, unparseable, or fails validation."""


class Presenter(_StrictModel):
    """A reusable radio-show host: a TTS voice + an authored persona + an
    on-air identity. Referenced by profiles; never influences curation.

    Strict (`extra="forbid"`): a misspelled key such as `tts_modle` is a load
    error, never a pin silently ignored."""
    id: str              # filename stem; injected by load_presenter, not stored in TOML
    name: str            # on-air identity, spoken ("Casey")
    sex: str             # informs character + self-reference ("male" / "female")
    voice: str | None = None        # preset name (voxtral) or voice_id (elevenlabs)
    voice_clone: str | None = None  # absolute path to a 3-25s reference clip (voxtral / mlx_audio)
    character: str       # free-text persona description shaping tone
    bed: str | None = None  # optional per-host bed WAV (overrides [tts] bed)
    tts: str | None = None             # backend pin; None = [tts] backend (never mlx_audio)
    tts_model: str | None = None       # mlx_audio only; None = [tts.mlx_audio] model
    voice_clone_text: str | None = None  # transcript of voice_clone (mlx_audio requires it)

    @model_validator(mode="after")
    def _validate(self):
        if bool(self.voice) == bool(self.voice_clone):
            raise ValueError("a presenter needs exactly one of voice / voice_clone")
        if self.tts is not None and self.tts not in TTS_PINS:
            raise ValueError(f"tts must be one of {', '.join(TTS_PINS)} (got {self.tts!r}); "
                             "remove the key to use [tts] backend")
        if self.tts_model is not None:
            if not self.tts_model.strip():
                raise ValueError("tts_model must not be empty; remove the key to use "
                                 "[tts.mlx_audio] model")
            if self.tts != "mlx_audio":
                raise ValueError('tts_model is allowed only with tts = "mlx_audio"')
        if self.tts == "elevenlabs" and self.voice_clone:
            raise ValueError('voice_clone cannot be voiced with tts = "elevenlabs" '
                             "(cloning needs voxtral or mlx_audio)")
        if self.tts == "mlx_audio":
            if self.voice:
                raise ValueError('tts = "mlx_audio" is clone-only: use voice_clone, '
                                 "not a preset voice")
            if not (self.voice_clone_text or "").strip():
                raise ValueError('tts = "mlx_audio" needs voice_clone_text, the transcript '
                                 "of voice_clone")
        return self

    @property
    def voice_id(self) -> str:
        """The resolved voice string this presenter stamps into a run."""
        return self.voice or self.voice_clone


def save_presenter(root: Path, presenter: Presenter) -> Path:
    # Validate whole before writing: a caller that built `presenter` with
    # model_copy(update=...) skipped the validators.
    try:
        Presenter.model_validate(presenter.model_dump())
    except ValidationError as exc:
        raise PresenterError(f"invalid presenter {presenter.id!r}: {exc}") from exc
    path = root / "presenters" / f"{presenter.id}.toml"
    # TOML has no null: drop None fields; id is the filename, not file content.
    atomic_write_text(path, tomli_w.dumps(
        presenter.model_dump(mode="json", exclude_none=True, exclude={"id"})))
    return path
```

(`load_presenter`, `delete_presenter`, `list_presenters` are unchanged.)

- [ ] **Step 4: Run the file, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_presenters.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/presenters.py packages/emcee/tests/test_presenters.py
git commit -m "feat(emcee): presenter tts pin fields on a strict model

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---

### Task 3: Config — `[tts] voice_clone_text`, per-backend subtables, `[tts.verify]`

**Implementer model:** Sonnet (mechanical: `config.py` + `test_config.py`, complete spec).
**Live:** no.

Spec: section 1 "Config", "House voice on mlx_audio", "Hosted keys and models"; section 3 "Transcript verification" (config rules); section 5 (template); section 6 "Config".

**Files:**
- Modify: `packages/emcee/src/emcee/config.py`
- Test: `packages/emcee/tests/test_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (in `emcee.config`):
  - `HOSTED_BACKENDS: tuple[str, ...] = ("voxtral", "elevenlabs")`
  - `HostedTTSConfig(_StrictModel)`: `api_key: str | None = None`, `model: str | None = None`
  - `MlxAudioConfig(_StrictModel)`: `url: str = "http://127.0.0.1:8000"`, `model: str | None = None`, `timeout_s: float = 600`, `stt_model: str | None = None`
  - `VerifyConfig(_StrictModel)`: `backends: list[Literal["mlx_audio", "voxtral", "elevenlabs"]] = []`
  - `TTSConfig` gains `voice_clone_text: str | None = None`, `voxtral: HostedTTSConfig`, `elevenlabs: HostedTTSConfig`, `mlx_audio: MlxAudioConfig`, `verify: VerifyConfig` (all default-constructed).
  - Validation errors (raised as `ValueError` inside the model, surfacing as `ConfigError` from `load_config`) — messages contain these exact substrings: `[tts] api_key is not valid when [tts] backend is mlx_audio` … `[tts.voxtral] or [tts.elevenlabs] api_key`; `[tts] model is not valid when [tts] backend is mlx_audio; set [tts.mlx_audio] model`; `[tts] <key> and [tts.<backend>] <key> are both set`; `[tts.verify] backends needs [tts.mlx_audio] stt_model`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/emcee/tests/test_config.py` (and add `HostedTTSConfig, MlxAudioConfig, VerifyConfig, HOSTED_BACKENDS` to the `from emcee.config import (...)` list at the top):

```python
# --- [tts] subtables (spec section 1) -------------------------------------


def _load(tmp_path: Path, text: str):
    p = tmp_path / "config.toml"
    p.write_text(text)
    return load_config(p)


def test_hosted_backends_constant():
    assert HOSTED_BACKENDS == ("voxtral", "elevenlabs")


def test_tts_subtable_defaults():
    t = TTSConfig()
    assert t.voice_clone_text is None
    assert t.mlx_audio == MlxAudioConfig()
    assert t.mlx_audio.url == "http://127.0.0.1:8000"
    assert t.mlx_audio.timeout_s == 600
    assert t.mlx_audio.model is None and t.mlx_audio.stt_model is None
    assert t.voxtral == HostedTTSConfig() and t.elevenlabs == HostedTTSConfig()
    assert t.voxtral.api_key is None and t.voxtral.model is None
    assert t.verify == VerifyConfig() and t.verify.backends == []


def test_mlx_audio_table_with_defaults_and_values(tmp_path: Path):
    cfg = _load(tmp_path, '[tts.mlx_audio]\nmodel = "m/x"\nurl = "http://127.0.0.1:9000"\n'
                          'timeout_s = 120\nstt_model = "s/y"\n')
    assert cfg.tts.mlx_audio == MlxAudioConfig(url="http://127.0.0.1:9000", model="m/x",
                                               timeout_s=120, stt_model="s/y")


def test_mlx_audio_table_holding_only_stt_model_is_valid(tmp_path: Path):
    cfg = _load(tmp_path, '[tts.mlx_audio]\nstt_model = "s/y"\n')
    assert cfg.tts.mlx_audio.model is None and cfg.tts.mlx_audio.stt_model == "s/y"


@pytest.mark.parametrize("table", ["voxtral", "elevenlabs", "mlx_audio", "verify"])
def test_every_tts_subtable_is_strict(tmp_path: Path, table):
    with pytest.raises(ConfigError):
        _load(tmp_path, f"[tts.{table}]\nbogus_knob = 1\n")


def test_voice_clone_text_parses(tmp_path: Path):
    cfg = _load(tmp_path, '[tts]\nvoice_clone = "/r.wav"\nvoice_clone_text = "Hi there."\n')
    assert cfg.tts.voice_clone_text == "Hi there."


# The live ~/.emcee/config.toml's shape on 2026-10-12 (key redacted): a hosted
# house backend with legacy [tts] api_key, chunk and bed_gain_db.
LIVE_CONFIG = """
[station]
root = "/Volumes/media/lma-radio/delivered/"

[llm.scriptwrite]
backend = "claude_cli"

[tts]
voice_clone = "/Users/shawn/.emcee/samples/troymcclure2.wav"
api_key = "redacted"
chunk = true
bed_gain_db = -20.0

[assign]
default = "roydemure"

[assign.profiles.bluegrass]
presenter = "monroe"
title = "Bluegrass Valley"

[assign.profiles.dead]
presenter = "phil"
title = "One More from the Archive"

[assign.profiles.indie]
presenter = "kurt"
title = "Live from the Basement"
"""


def test_live_config_loads(tmp_path: Path):
    cfg = _load(tmp_path, LIVE_CONFIG)
    assert cfg.tts.backend == "voxtral" and cfg.tts.api_key == "redacted"
    assert cfg.tts.voxtral.api_key is None


def test_house_mlx_rejects_legacy_api_key_naming_the_subtables(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, '[tts]\nbackend = "mlx_audio"\napi_key = "k"\n')
    msg = str(exc.value)
    assert "[tts] api_key is not valid when [tts] backend is mlx_audio" in msg
    assert "[tts.voxtral] or [tts.elevenlabs] api_key" in msg


def test_house_mlx_rejects_legacy_model_naming_mlx_model(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, '[tts]\nbackend = "mlx_audio"\nmodel = "m"\n')
    assert ("[tts] model is not valid when [tts] backend is mlx_audio; "
            "set [tts.mlx_audio] model") in str(exc.value)


@pytest.mark.parametrize("backend", ["voxtral", "elevenlabs"])
def test_legacy_key_and_model_valid_under_a_hosted_house(tmp_path: Path, backend):
    cfg = _load(tmp_path, f'[tts]\nbackend = "{backend}"\napi_key = "k"\nmodel = "m"\n')
    assert (cfg.tts.api_key, cfg.tts.model) == ("k", "m")


@pytest.mark.parametrize("key", ["api_key", "model"])
def test_same_key_in_tts_and_house_subtable_names_both(tmp_path: Path, key):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, f'[tts]\n{key} = "a"\n\n[tts.voxtral]\n{key} = "b"\n')
    assert f"[tts] {key} and [tts.voxtral] {key} are both set" in str(exc.value)


def test_same_key_in_tts_and_a_non_house_subtable_is_fine(tmp_path: Path):
    cfg = _load(tmp_path, '[tts]\napi_key = "mistral"\n\n[tts.elevenlabs]\napi_key = "el"\n')
    assert (cfg.tts.api_key, cfg.tts.elevenlabs.api_key) == ("mistral", "el")


@pytest.mark.parametrize("name", ["fake", "kokoro", "MLX_AUDIO"])
def test_verify_rejects_unknown_backend_names(tmp_path: Path, name):
    with pytest.raises(ConfigError):
        _load(tmp_path, f'[tts.mlx_audio]\nstt_model = "s"\n\n[tts.verify]\nbackends = ["{name}"]\n')


def test_verify_nonempty_requires_stt_model(tmp_path: Path):
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, '[tts.verify]\nbackends = ["mlx_audio"]\n')
    assert "[tts.verify] backends needs [tts.mlx_audio] stt_model" in str(exc.value)


def test_verify_with_stt_model_is_valid(tmp_path: Path):
    cfg = _load(tmp_path, '[tts.mlx_audio]\nstt_model = "s"\n\n'
                          '[tts.verify]\nbackends = ["mlx_audio", "voxtral"]\n')
    assert cfg.tts.verify.backends == ["mlx_audio", "voxtral"]
```

Also extend `test_default_config_template_mentions_every_section`'s marker tuple with `"voice_clone_text", "[tts.voxtral]", "[tts.elevenlabs]", "[tts.mlx_audio]", "[tts.verify]"`.

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'HostedTTSConfig'`.

- [ ] **Step 3: Implement the models**

In `packages/emcee/src/emcee/config.py`, after `StationConfig`, add the subtable models and replace `TTSConfig`:

```python
# Hosted TTS backends: each has an API key and a model, configured in its own
# [tts.<backend>] table wherever it voices (house or pin).
HOSTED_BACKENDS = ("voxtral", "elevenlabs")


class HostedTTSConfig(_StrictModel):
    """[tts.voxtral] / [tts.elevenlabs]: applies wherever that backend voices
    (as [tts] backend or as a presenter pin). The provider's env var
    (MISTRAL_API_KEY / ELEVENLABS_API_KEY) still wins over api_key."""
    api_key: str | None = None
    model: str | None = None


class MlxAudioConfig(_StrictModel):
    """[tts.mlx_audio]: the local mlx-audio server. `model` has no default; it
    is required only when something resolves to mlx_audio (checked at
    resolution), so a table holding only stt_model is valid."""
    url: str = "http://127.0.0.1:8000"
    model: str | None = None
    timeout_s: float = 600                 # per sentence request
    stt_model: str | None = None           # speech-to-text model on the same server


VerifyBackend = Literal["mlx_audio", "voxtral", "elevenlabs"]


class VerifyConfig(_StrictModel):
    """[tts.verify]: transcript verification of newly synthesized audio."""
    backends: list[VerifyBackend] = Field(default_factory=list)   # default off


class TTSConfig(_StrictModel):
    """Spoken DJ patter (text-to-speech of the DJ script).

    `backend` is the HOUSE voice and every unpinned presenter's backend --
    except that an unpinned presenter never inherits mlx_audio (resolution
    rejects it), so changing the house voice never moves a presenter."""
    backend: str = "voxtral"            # or "elevenlabs" / "mlx_audio" / "fake"
    voice: str | None = None            # voxtral preset name / elevenlabs voice_id
    voice_clone: str | None = None      # path to a reference clip; when set, the house voice clones it
    voice_clone_text: str | None = None  # transcript of voice_clone (required on mlx_audio)
    model: str | None = None            # legacy: the HOUSE hosted backend's model
    api_key: str | None = None          # legacy: the HOUSE hosted backend's key (env wins)
    chunk: bool = True                  # synthesize each DJ-notes segment sentence-by-
                                         # sentence and concatenate, instead of one call
                                         # per segment (better prosody, loudness-normalized;
                                         # needs lameenc). false = one call per segment
    bed: str | None = None              # path to a 24kHz mono 16-bit WAV played
                                         # under the DJ voice; None = no bed
    bed_gain_db: float = -20.0          # bed loudness under the voice (station-level)
    voxtral: HostedTTSConfig = Field(default_factory=HostedTTSConfig)
    elevenlabs: HostedTTSConfig = Field(default_factory=HostedTTSConfig)
    mlx_audio: MlxAudioConfig = Field(default_factory=MlxAudioConfig)
    verify: VerifyConfig = Field(default_factory=VerifyConfig)

    @model_validator(mode="after")
    def _check_keys_and_verify(self):
        if self.backend == "mlx_audio":
            if self.api_key is not None:
                raise ValueError(
                    "[tts] api_key is not valid when [tts] backend is mlx_audio (it needs "
                    "no key); put a hosted backend's key in [tts.voxtral] or "
                    "[tts.elevenlabs] api_key")
            if self.model is not None:
                raise ValueError("[tts] model is not valid when [tts] backend is mlx_audio; "
                                 "set [tts.mlx_audio] model")
        elif self.backend in HOSTED_BACKENDS:
            sub = getattr(self, self.backend)
            for key in ("api_key", "model"):
                if getattr(self, key) is not None and getattr(sub, key) is not None:
                    raise ValueError(
                        f"[tts] {key} and [tts.{self.backend}] {key} are both set; they "
                        "mean the same setting, keep one")
        if self.verify.backends and not self.mlx_audio.stt_model:
            raise ValueError("[tts.verify] backends needs [tts.mlx_audio] stt_model (the "
                             "speech-to-text model verification transcribes with)")
        return self
```

- [ ] **Step 4: Extend the config template**

In `DEFAULT_CONFIG_TOML`, change the existing `[tts]` comment block: after the `# voice_clone = "..."` paragraph insert the transcript key, and after `# api_key = "..."` insert the subtables. The finished `[tts]` portion must read (everything stays commented, so the parsed template still equals the defaults):

```
# path to a 3-25s reference WAV; when set, the house voice clones it
# (ignores `voice`)
# voice_clone = "..."

# word-for-word transcript of voice_clone; required when the house voice is
# on mlx_audio, ignored by voxtral
# voice_clone_text = "..."

# legacy spellings of the HOUSE hosted backend's model and key (valid only
# while backend is voxtral/elevenlabs; the same key in [tts.<backend>] too is
# an error). Per-backend default model when unset
# (voxtral-mini-tts-2603 / eleven_multilingual_v2)
# model = "..."

# MISTRAL_API_KEY / ELEVENLABS_API_KEY env (env wins)
# api_key = "..."

# Per-backend tables. A hosted backend's table applies wherever it voices:
# as [tts] backend or as a presenter's `tts` pin.
# [tts.voxtral]
# api_key = "..."            # MISTRAL_API_KEY env wins
# model = "voxtral-mini-tts-2603"

# [tts.elevenlabs]
# api_key = "..."            # ELEVENLABS_API_KEY env wins
# model = "eleven_multilingual_v2"

# Local TTS through mlx-audio's server on this Mac (see the README runbook).
# A presenter opts in with tts = "mlx_audio"; the house voice only with
# [tts] backend = "mlx_audio" -- and then every presenter must pin `tts`.
# [tts.mlx_audio]
# url = "http://127.0.0.1:8000"
# model = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
# timeout_s = 600            # seconds per sentence request
# stt_model = "..."          # speech-to-text model on the same server

# Transcript verification: transcribe each newly synthesized clip on the
# mlx-audio server and re-synthesize once on a gross mismatch; a second
# failure fails the package. Needs [tts.mlx_audio] stt_model. Default off.
# [tts.verify]
# backends = ["mlx_audio"]
```

Keep the rest of the template (the `# Assignment is keyed by ...`, chunk and bed paragraphs, `[assign]`) unchanged.

- [ ] **Step 5: Run the file, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_config.py -q` → PASS (including the two template tests).
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/emcee/src/emcee/config.py packages/emcee/tests/test_config.py
git commit -m "feat(emcee): per-backend [tts] subtables, voice_clone_text and [tts.verify]

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---
### Task 4: Pure TTS resolution + the (empty) calibration table

**Implementer model:** Sonnet (mechanical: two new pure modules + tests; every rule is spelled out below).
**Live:** no.

Spec: section 1 "Resolution"; section 3 first paragraph (calibration table, "resolving to any other model is a configuration error"); section 6 "Resolution".

**Files:**
- Create: `packages/emcee/src/emcee/tts/calibration.py`
- Create: `packages/emcee/src/emcee/tts/resolve.py`
- Create: `packages/emcee/tests/mlx_helpers.py`
- Test: `packages/emcee/tests/test_resolve.py`

**Interfaces:**
- Consumes: `HOSTED_BACKENDS`, `EmceeConfig`, `TTSConfig` subtables (Task 3); `Presenter` (Task 2); `emcee.tts.voxtral.DEFAULT_MODEL`, `emcee.tts.elevenlabs.DEFAULT_MODEL`.
- Produces:
  - `emcee.tts.calibration.ModelCalibration` — frozen dataclass, fields in order `frame_rate_hz: float`, `cap_floor_s: float`, `cap_s_per_char: float`, `max_floor_s: float`, `max_s_per_char: float`, `min_s_per_char: float`, `min_slack_s: float`, `cap_margin_s: float`; `__post_init__` raises `ValueError` unless `frame_rate_hz > 0`, every other field `>= 0`, `cap_s_per_char >= max_s_per_char` and `cap_floor_s - cap_margin_s > max_floor_s`.
  - `emcee.tts.calibration.CALIBRATED_MODELS: dict[str, ModelCalibration] = {}` (Task 12 adds the first entry; tests use `monkeypatch.setitem`).
  - `emcee.tts.resolve.TTSResolution` — frozen dataclass: `backend: str`, `model: str | None`, `api_key: str | None`, `key_sources: tuple[str, ...]`, `presenter: str | None` (presenter id; `None` = house voice), `pinned: bool`.
  - `emcee.tts.resolve.TTSResolutionError(EmceeError)`.
  - `emcee.tts.resolve.resolve_tts(config: EmceeConfig, presenter: Presenter | None) -> TTSResolution` — pure, no I/O.
  - `emcee.tts.resolve.DEFAULT_MODELS = {"voxtral": <voxtral DEFAULT_MODEL>, "elevenlabs": <elevenlabs DEFAULT_MODEL>}` (imported as `from emcee.tts.voxtral import DEFAULT_MODEL as VOXTRAL_DEFAULT_MODEL` etc. — absolute submodule imports, because `emcee/tts/__init__.py` imports this module from Task 5 on).
  - Error message substrings (exact): `pin tts explicitly: the house backend is mlx_audio`; `no mlx_audio model`; `mlx_audio model not calibrated for the runaway guard`.
  - `tests/mlx_helpers.py`: `TEST_MODEL = "test/mlx-tts-model"`, `TEST_MODEL_B = "test/mlx-tts-model-b"`, `TEST_CAL` (values below), `calibrate_test_model(monkeypatch, *models)`.

- [ ] **Step 1: Write the calibration skeleton and the shared test helper**

Create `packages/emcee/src/emcee/tts/calibration.py`:

```python
"""Per-model calibration for the mlx_audio runaway guard.

The guard (spec section 3) caps each request's max_tokens in proportion to
the text's length and checks the returned audio's duration against that
length. Tokens become seconds through the model's codec frame rate, so every
constant is per model: emcee carries a table of calibrated mlx models, and
resolving to a model outside it is a configuration error
("mlx_audio model not calibrated for the runaway guard").

Lengths are measured in characters of whitespace-collapsed text (see
`text_units`, added with the guard math).
"""
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class ModelCalibration:
    frame_rate_hz: float   # codec frames (= generated tokens) per second of audio
    cap_floor_s: float     # max_tokens covers cap_floor_s + cap_s_per_char * chars
    cap_s_per_char: float
    max_floor_s: float     # longer than max_floor_s + max_s_per_char * chars: implausibly long
    max_s_per_char: float
    min_s_per_char: float  # shorter than min_s_per_char * chars - min_slack_s: implausibly short
    min_slack_s: float
    cap_margin_s: float    # within cap_margin_s of the cap's duration: a capped runaway

    def __post_init__(self):
        if self.frame_rate_hz <= 0:
            raise ValueError("frame_rate_hz must be positive")
        for f in fields(self):
            if getattr(self, f.name) < 0:
                raise ValueError(f"{f.name} must not be negative")
        # The cap must sit above every plausible clip, or the cap-margin check
        # would fire on legitimate long sentences.
        if self.cap_s_per_char < self.max_s_per_char:
            raise ValueError("cap_s_per_char must be >= max_s_per_char")
        if self.cap_floor_s - self.cap_margin_s <= self.max_floor_s:
            raise ValueError("cap_floor_s - cap_margin_s must exceed max_floor_s")


# Model id -> calibration. EMPTY until the calibration run (implementation
# plan Task 12) measures the first entry: nothing voices on mlx_audio with
# guessed constants. Tests register a test-only entry (tests/mlx_helpers.py).
CALIBRATED_MODELS: dict[str, ModelCalibration] = {}
```

Create `packages/emcee/tests/mlx_helpers.py`:

```python
"""Shared fixtures for the mlx_audio backend's tests.

TEST_MODEL / TEST_MODEL_B are test-only calibration entries: production's
CALIBRATED_MODELS is measured (implementation plan Task 12), and no test may
depend on its measured values. Register them per test with
`calibrate_test_model(monkeypatch)`.
"""
from emcee.tts import calibration

TEST_MODEL = "test/mlx-tts-model"
TEST_MODEL_B = "test/mlx-tts-model-b"
TEST_CAL = calibration.ModelCalibration(
    frame_rate_hz=12.5, cap_floor_s=8.0, cap_s_per_char=0.12, max_floor_s=4.0,
    max_s_per_char=0.11, min_s_per_char=0.03, min_slack_s=1.0, cap_margin_s=1.0)


def calibrate_test_model(monkeypatch, *models: str) -> None:
    """Register TEST_CAL under `models` (default: TEST_MODEL) for one test."""
    for model in models or (TEST_MODEL,):
        monkeypatch.setitem(calibration.CALIBRATED_MODELS, model, TEST_CAL)
```

- [ ] **Step 2: Write the failing resolution tests**

Create `packages/emcee/tests/test_resolve.py`:

```python
"""resolve_tts: which backend, model and key voice a presenter or the house
voice (spec section 1 "Resolution"). Pure: no files, no network."""
import pytest

from emcee.config import EmceeConfig
from emcee.presenters import Presenter
from emcee.tts import calibration
from emcee.tts.elevenlabs import DEFAULT_MODEL as EL_DEFAULT
from emcee.tts.resolve import DEFAULT_MODELS, TTSResolution, TTSResolutionError, resolve_tts
from emcee.tts.voxtral import DEFAULT_MODEL as VOX_DEFAULT

from tests.mlx_helpers import TEST_CAL, TEST_MODEL, TEST_MODEL_B, calibrate_test_model


def cfg(**tts) -> EmceeConfig:
    return EmceeConfig.model_validate({"tts": tts})


def host(**overrides) -> Presenter:
    d = dict(id="phil", name="Phil", sex="male", voice=None, voice_clone="/refs/phil.wav",
             character="Professorial.")
    d.update(overrides)
    return Presenter(**d)


def mlx_host(**overrides) -> Presenter:
    return host(tts="mlx_audio", voice_clone_text="It's the chemistry.", **overrides)


def test_test_models_are_never_production_entries():
    # Production entries are measured (plan Task 12); test entries exist only
    # inside a test, via calibrate_test_model.
    assert TEST_MODEL not in calibration.CALIBRATED_MODELS
    assert TEST_MODEL_B not in calibration.CALIBRATED_MODELS


def test_calibration_invariants():
    with pytest.raises(ValueError, match="cap_s_per_char"):
        calibration.ModelCalibration(12.5, 8.0, 0.10, 4.0, 0.11, 0.03, 1.0, 1.0)
    with pytest.raises(ValueError, match="must exceed max_floor_s"):
        calibration.ModelCalibration(12.5, 5.0, 0.12, 4.0, 0.11, 0.03, 1.0, 1.0)
    with pytest.raises(ValueError, match="positive"):
        calibration.ModelCalibration(0, 8.0, 0.12, 4.0, 0.11, 0.03, 1.0, 1.0)
    with pytest.raises(ValueError, match="negative"):
        calibration.ModelCalibration(12.5, 8.0, 0.12, 4.0, 0.11, -0.1, 1.0, 1.0)


def test_default_models_are_the_providers_defaults():
    assert DEFAULT_MODELS == {"voxtral": VOX_DEFAULT, "elevenlabs": EL_DEFAULT}


# --- house voice -----------------------------------------------------------


def test_house_hosted_uses_legacy_key_and_model_and_names_both_key_locations():
    r = resolve_tts(cfg(api_key="k-legacy", model="m-legacy"), None)
    assert r == TTSResolution(backend="voxtral", model="m-legacy", api_key="k-legacy",
                              key_sources=("[tts.voxtral] api_key", "[tts] api_key"),
                              presenter=None, pinned=False)


def test_house_hosted_subtable_key_and_model():
    r = resolve_tts(cfg(voxtral={"api_key": "k-sub", "model": "m-sub"}), None)
    assert (r.api_key, r.model) == ("k-sub", "m-sub")


def test_house_hosted_model_defaults_and_key_may_be_absent():
    r = resolve_tts(cfg(backend="elevenlabs"), None)
    assert (r.backend, r.model, r.api_key) == ("elevenlabs", EL_DEFAULT, None)


def test_house_fake_resolves_to_fake():
    r = resolve_tts(cfg(backend="fake"), None)
    assert (r.backend, r.model, r.api_key, r.key_sources) == ("fake", None, None, ())


def test_house_unknown_backend_passes_through_for_the_factory_to_reject():
    assert resolve_tts(cfg(backend="kokoro"), None).backend == "kokoro"


def test_house_mlx_uses_the_mlx_table_model(monkeypatch):
    calibrate_test_model(monkeypatch)
    r = resolve_tts(cfg(backend="mlx_audio", mlx_audio={"model": TEST_MODEL}), None)
    assert r == TTSResolution(backend="mlx_audio", model=TEST_MODEL, api_key=None,
                              key_sources=(), presenter=None, pinned=False)


def test_house_mlx_without_a_model_is_an_error():
    with pytest.raises(TTSResolutionError, match=r"no mlx_audio model.*\[tts.mlx_audio\] model"):
        resolve_tts(cfg(backend="mlx_audio"), None)


def test_house_mlx_uncalibrated_model_is_an_error():
    with pytest.raises(TTSResolutionError,
                       match="mlx_audio model not calibrated for the runaway guard"):
        resolve_tts(cfg(backend="mlx_audio", mlx_audio={"model": "other/model"}), None)


# --- presenters --------------------------------------------------------------


def test_unpinned_presenter_inherits_a_hosted_house():
    r = resolve_tts(cfg(api_key="k"), host())
    assert (r.backend, r.api_key, r.presenter, r.pinned) == ("voxtral", "k", "phil", False)


def test_unpinned_presenter_inherits_fake():
    assert resolve_tts(cfg(backend="fake"), host()).backend == "fake"


def test_unpinned_presenter_under_an_mlx_house_is_an_error(monkeypatch):
    calibrate_test_model(monkeypatch)
    with pytest.raises(TTSResolutionError,
                       match="pin tts explicitly: the house backend is mlx_audio"):
        resolve_tts(cfg(backend="mlx_audio", mlx_audio={"model": TEST_MODEL}), host())


def test_presenter_pin_beats_the_house_backend():
    r = resolve_tts(cfg(backend="voxtral"), host(voice="v", voice_clone=None, tts="elevenlabs"))
    assert (r.backend, r.pinned) == ("elevenlabs", True)


def test_pinned_hosted_ignores_legacy_tts_key_and_model_of_another_house():
    # [tts] api_key/model mean the HOUSE backend's (elevenlabs here), never voxtral's.
    r = resolve_tts(cfg(backend="elevenlabs", api_key="el-key", model="el-model"),
                    host(tts="voxtral"))
    assert (r.backend, r.model, r.api_key) == ("voxtral", VOX_DEFAULT, None)
    assert r.key_sources == ("[tts.voxtral] api_key",)


def test_pinned_hosted_same_as_house_still_gets_legacy_key():
    r = resolve_tts(cfg(api_key="k", model="m"), host(tts="voxtral"))
    assert (r.model, r.api_key) == ("m", "k")
    assert r.key_sources == ("[tts.voxtral] api_key", "[tts] api_key")


def test_pinned_hosted_uses_its_subtable():
    r = resolve_tts(cfg(backend="elevenlabs", voxtral={"api_key": "vk", "model": "vm"}),
                    host(tts="voxtral"))
    assert (r.model, r.api_key) == ("vm", "vk")


def test_mlx_pin_model_beats_the_mlx_table_model(monkeypatch):
    calibrate_test_model(monkeypatch, TEST_MODEL, TEST_MODEL_B)
    config = cfg(mlx_audio={"model": TEST_MODEL})
    assert resolve_tts(config, mlx_host()).model == TEST_MODEL
    assert resolve_tts(config, mlx_host(tts_model=TEST_MODEL_B)).model == TEST_MODEL_B


def test_mlx_pin_without_any_model_is_an_error():
    with pytest.raises(TTSResolutionError, match="no mlx_audio model"):
        resolve_tts(cfg(), mlx_host())


def test_mlx_pin_uncalibrated_model_is_an_error(monkeypatch):
    calibrate_test_model(monkeypatch)
    with pytest.raises(TTSResolutionError,
                       match="mlx_audio model not calibrated for the runaway guard"):
        resolve_tts(cfg(mlx_audio={"model": TEST_MODEL}), mlx_host(tts_model="other/model"))


def test_mlx_pin_resolution_fields(monkeypatch):
    calibrate_test_model(monkeypatch)
    r = resolve_tts(cfg(mlx_audio={"model": TEST_MODEL}), mlx_host())
    assert r == TTSResolution(backend="mlx_audio", model=TEST_MODEL, api_key=None,
                              key_sources=(), presenter="phil", pinned=True)


def test_test_calibration_is_registered_only_inside_a_test(monkeypatch):
    calibrate_test_model(monkeypatch)
    assert calibration.CALIBRATED_MODELS[TEST_MODEL] is TEST_CAL
```

- [ ] **Step 3: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_resolve.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'emcee.tts.resolve'`.

- [ ] **Step 4: Implement `resolve.py`**

Create `packages/emcee/src/emcee/tts/resolve.py`:

```python
"""Which TTS backend, model and key voice a presenter or the house voice.

Pure (no I/O): called before any LLM/TTS spend and before a package's
manifest blocks are cleared, so a configuration error never takes a
broadcast-ready package off air. See spec section 1 "Resolution".

- House voice: [tts] backend.
- Presenter: `presenter.tts` (a pin), else [tts] backend -- except that an
  unpinned presenter never inherits mlx_audio, so changing the house voice
  never moves a presenter.
- mlx_audio model: presenter.tts_model, else [tts.mlx_audio] model, else an
  error; a model outside the runaway guard's calibration table is an error.
- Hosted model/key: the backend's [tts.<backend>] table, else (only when it
  is the house backend) legacy [tts] model/api_key, else the provider's
  default model / no key (the provider's env var may still supply one).
"""
from dataclasses import dataclass

from emcee.config import HOSTED_BACKENDS, EmceeConfig
from emcee.errors import EmceeError
from emcee.presenters import Presenter
from emcee.tts.calibration import CALIBRATED_MODELS
from emcee.tts.elevenlabs import DEFAULT_MODEL as ELEVENLABS_DEFAULT_MODEL
from emcee.tts.voxtral import DEFAULT_MODEL as VOXTRAL_DEFAULT_MODEL

DEFAULT_MODELS = {"voxtral": VOXTRAL_DEFAULT_MODEL, "elevenlabs": ELEVENLABS_DEFAULT_MODEL}


class TTSResolutionError(EmceeError):
    """A presenter or the house voice cannot be resolved to a usable backend."""


@dataclass(frozen=True)
class TTSResolution:
    backend: str                  # "voxtral" | "elevenlabs" | "mlx_audio" | "fake" | (unknown)
    model: str | None             # concrete model id; None only for fake/unknown backends
    api_key: str | None           # config-supplied key (hosted only); env still wins
    key_sources: tuple[str, ...]  # config locations a missing-key error should name
    presenter: str | None         # presenter id; None = the house voice
    pinned: bool                  # True when the presenter's own `tts` chose the backend


def resolve_tts(config: EmceeConfig, presenter: Presenter | None) -> TTSResolution:
    house = config.tts.backend
    pid = presenter.id if presenter is not None else None
    who = f"presenter {pid!r}" if presenter is not None else "the house voice"
    if presenter is not None and presenter.tts is not None:
        backend, pinned = presenter.tts, True
    else:
        backend, pinned = house, False
        if presenter is not None and house == "mlx_audio":
            raise TTSResolutionError(
                f"presenter {pid!r}: pin tts explicitly: the house backend is mlx_audio "
                f"(e.g. `emcee presenter edit {pid} --tts voxtral`)")
    if backend == "mlx_audio":
        model = (presenter.tts_model if presenter is not None else None) \
            or config.tts.mlx_audio.model
        if not model:
            where = "the presenter's tts_model or " if presenter is not None else ""
            raise TTSResolutionError(f"{who}: no mlx_audio model: set {where}[tts.mlx_audio] model")
        if model not in CALIBRATED_MODELS:
            known = ", ".join(sorted(CALIBRATED_MODELS)) or "none yet"
            raise TTSResolutionError(
                f"{who}: mlx_audio model not calibrated for the runaway guard: {model!r} "
                f"(calibrated: {known})")
        return TTSResolution("mlx_audio", model, None, (), pid, pinned)
    if backend in HOSTED_BACKENDS:
        sub = getattr(config.tts, backend)
        is_house = backend == house
        model = sub.model or (config.tts.model if is_house else None) or DEFAULT_MODELS[backend]
        api_key = sub.api_key or (config.tts.api_key if is_house else None)
        sources = (f"[tts.{backend}] api_key",) + (("[tts] api_key",) if is_house else ())
        return TTSResolution(backend, model, api_key, sources, pid, pinned)
    return TTSResolution(backend, None, None, (), pid, pinned)
```

- [ ] **Step 5: Run the file, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_resolve.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass (nothing calls `resolve_tts` yet).

- [ ] **Step 6: Commit**

```bash
git add packages/emcee/src/emcee/tts/calibration.py packages/emcee/src/emcee/tts/resolve.py \
        packages/emcee/tests/mlx_helpers.py packages/emcee/tests/test_resolve.py
git commit -m "feat(emcee): pure TTS resolution and the runaway-guard calibration table

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---

### Task 5: Resolution-driven `speech_provider_for` and every call site

**Implementer model:** Opus (cross-cutting migration of every factory call site and test double, where a missed site is a strict-surface bug; ~4 source + 5 test files).
**Live:** no.

Spec: section 1 "Resolution" (factory paragraph: required arguments, `clone_text`, `speech_for`/`ad_hoc_speech` through the resolver, ElevenLabs-clone check, cache keying); "A missing key is the existing "API key missing" error … names the env var and the locations that apply".

**Files:**
- Modify: `packages/emcee/src/emcee/tts/__init__.py`
- Modify: `packages/emcee/src/emcee/process.py:87-147` (`speech_for`, `ad_hoc_speech`)
- Modify: `packages/emcee/src/emcee/tts/voxtral.py:54-73` (`key_hint`)
- Modify: `packages/emcee/src/emcee/tts/elevenlabs.py:22-37` (`key_hint`)
- Create: `packages/emcee/tests/conftest.py`
- Modify tests: `packages/emcee/tests/test_tts.py:147-214`, `packages/emcee/tests/test_process.py:112-178`, `packages/emcee/tests/test_run_cmd.py:318-319` and `:430-431`

**Interfaces:**
- Consumes: `resolve_tts`, `TTSResolution` (Task 4); `Presenter.voice_clone_text`, `TTSConfig.voice_clone_text`.
- Produces:
  - `emcee.tts.speech_provider_for(config: EmceeConfig, resolution: TTSResolution, *, voice: str | None, clone_ref: str | None, clone_text: str | None) -> SpeechProvider` — every argument required, the last three keyword-only, no defaults.
  - `VoxtralProvider(..., key_hint: str = "[tts] api_key")` and `ElevenLabsProvider(..., key_hint: str = "[tts] api_key")`: missing-key message `"<Mistral|ElevenLabs> API key missing: set <ENV> or <key_hint>"`.
  - `emcee.process.ad_hoc_speech(config, *, clone_ref=None, clone_text=None, voice=None, presenter=None)`.
  - `speech_for(config, presenter)` unchanged signature; it now calls `speech_provider_for(config, resolve_tts(config, presenter), voice=..., clone_ref=..., clone_text=...)` with the presenter's (or `[tts]`'s) `voice`, `voice_clone`, `voice_clone_text`.
  - ElevenLabs clone error substring: `voice cloning is not available on elevenlabs`.

- [ ] **Step 1: Add the emcee conftest (no ambient API keys)**

Create `packages/emcee/tests/conftest.py`:

```python
"""No emcee test may see the operator's real API keys: the missing-key tests
and the strict-surface tests set exactly the keys they mean."""
import pytest


@pytest.fixture(autouse=True)
def _no_ambient_tts_keys(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
```

- [ ] **Step 2: Rewrite the factory tests to the new signature (failing)**

In `packages/emcee/tests/test_tts.py`, replace everything from the `# --- speech_provider_for factory` comment through `test_factory_unknown_backend_raises` with:

```python
# --- speech_provider_for factory: resolution-driven -------------------------

from emcee.presenters import Presenter
from emcee.tts.resolve import resolve_tts
from emcee.tts.voxtral import VoxtralProvider


def _make(cfg, *, voice=None, clone_ref=None, clone_text=None, presenter=None):
    return speech_provider_for(cfg, resolve_tts(cfg, presenter), voice=voice,
                               clone_ref=clone_ref, clone_text=clone_text)


def test_factory_arguments_are_required_keywords():
    cfg = EmceeConfig.model_validate({"tts": {"backend": "fake"}})
    res = resolve_tts(cfg, None)
    with pytest.raises(TypeError):
        speech_provider_for(cfg, res)  # an unmigrated call site fails loudly
    with pytest.raises(TypeError):
        speech_provider_for(cfg, "voice-string", None)


def test_factory_fake_backend():
    cfg = EmceeConfig.model_validate({"tts": {"backend": "fake"}})
    assert isinstance(_make(cfg, voice="ignored"), FakeSpeechProvider)


def test_factory_elevenlabs_uses_voice_and_model(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    cfg = EmceeConfig.model_validate({"tts": {"backend": "elevenlabs", "model": "eleven_turbo_v2_5"}})
    p = _make(cfg, voice="v-abc")
    assert isinstance(p, ElevenLabsProvider)
    assert (p.voice, p.model) == ("v-abc", "eleven_turbo_v2_5")


def test_factory_voxtral_is_default_preset(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    p = _make(EmceeConfig.model_validate({"tts": {"voice": "british-dj"}}), voice="british-dj")
    assert isinstance(p, VoxtralProvider)
    assert p.voice == "british-dj"


def test_factory_voxtral_clone_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    ref = tmp_path / "dj.wav"; ref.write_bytes(b"REF")
    p = _make(EmceeConfig(), clone_ref=str(ref))
    assert isinstance(p, VoxtralProvider)
    assert p.voice.startswith("clone:")


def test_factory_ignores_config_clone_without_clone_ref(monkeypatch, tmp_path):
    # Callers own clone resolution (a presenter must fully own its voice):
    # the factory itself never falls back to [tts] voice_clone.
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    ref = tmp_path / "dj.wav"; ref.write_bytes(b"REF")
    cfg = EmceeConfig.model_validate({"tts": {"voice_clone": str(ref)}})
    with pytest.raises(SpeechError, match="no Voxtral voice configured"):
        _make(cfg)


def test_factory_voxtral_model_and_key_from_the_resolution(monkeypatch):
    cfg = EmceeConfig.model_validate({"tts": {"voxtral": {"api_key": "k-sub", "model": "m-sub"}}})
    p = _make(cfg, voice="v")
    assert (p.model, p.api_key) == ("m-sub", "k-sub")


def test_factory_env_key_wins_over_the_resolved_key(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k-env")
    cfg = EmceeConfig.model_validate({"tts": {"voxtral": {"api_key": "k-sub"}}})
    assert _make(cfg, voice="v").api_key == "k-env"


def test_factory_missing_house_key_names_env_and_both_locations():
    with pytest.raises(SpeechError) as exc:
        _make(EmceeConfig(), voice="v")
    assert str(exc.value) == ("Mistral API key missing: set MISTRAL_API_KEY or "
                              "[tts.voxtral] api_key or [tts] api_key")


def test_factory_missing_pinned_key_names_only_the_subtable():
    cfg = EmceeConfig.model_validate({"tts": {"backend": "elevenlabs", "api_key": "el"}})
    pinned = Presenter(id="p", name="P", sex="male", voice="v", character="x", tts="voxtral")
    with pytest.raises(SpeechError) as exc:
        _make(cfg, voice="v", presenter=pinned)
    assert str(exc.value) == "Mistral API key missing: set MISTRAL_API_KEY or [tts.voxtral] api_key"


def test_factory_elevenlabs_rejects_an_inherited_clone(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    cfg = EmceeConfig.model_validate({"tts": {"backend": "elevenlabs"}})
    unpinned = Presenter(id="p", name="P", sex="male", voice_clone="/refs/x.wav", character="x")
    with pytest.raises(SpeechError, match="voice cloning is not available on elevenlabs"):
        _make(cfg, clone_ref="/refs/x.wav", presenter=unpinned)


def test_factory_elevenlabs_rejects_a_pinned_clone(monkeypatch):
    # Presenter validation already refuses tts="elevenlabs" + voice_clone; the
    # factory still refuses any clone that reaches elevenlabs.
    from emcee.tts.resolve import TTSResolution
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    res = TTSResolution("elevenlabs", "eleven_multilingual_v2", None,
                        ("[tts.elevenlabs] api_key",), "p", True)
    with pytest.raises(SpeechError, match="voice cloning is not available on elevenlabs"):
        speech_provider_for(EmceeConfig(), res, voice=None, clone_ref="/refs/x.wav",
                            clone_text=None)


def test_factory_voxtral_no_voice_no_clone_raises(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    with pytest.raises(SpeechError):
        _make(EmceeConfig())


def test_factory_no_voice_raises(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    with pytest.raises(SpeechError):
        _make(EmceeConfig.model_validate({"tts": {"backend": "elevenlabs"}}))


def test_factory_unknown_backend_raises():
    cfg = EmceeConfig.model_validate({"tts": {"backend": "kokoro"}})
    with pytest.raises(SpeechError, match="unknown TTS backend"):
        _make(cfg, voice="v")
```

In `packages/emcee/tests/test_process.py`, replace the three `speech_for` precedence tests and the bed test (lines 116-178) with:

```python
def _recorder(calls):
    def fake_factory(config, resolution, *, voice, clone_ref, clone_text):
        calls.append((resolution.backend, resolution.presenter, voice, clone_ref, clone_text))
        return "sentinel"
    return fake_factory


def test_speech_for_presenter_voice_wins_and_house_clone_never_bleeds_in(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("emcee.process.speech_provider_for", _recorder(calls))
    presenter = _presenter(voice="presenter-preset")  # voice set, voice_clone None
    config = EmceeConfig(tts=TTSConfig(voice="house-voice", voice_clone="house-clone.wav",
                                       voice_clone_text="house words"))

    speech, bed = speech_for(config, presenter)

    assert speech == "sentinel"
    # house voice_clone and its transcript did NOT bleed in
    assert calls == [("voxtral", "waldo", "presenter-preset", None, None)]
    assert bed is None


def test_speech_for_presenter_voice_clone_and_transcript(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("emcee.process.speech_provider_for", _recorder(calls))
    presenter = _presenter(voice=None, voice_clone="/refs/casey.wav",
                           voice_clone_text="Casey's words.")

    speech_for(EmceeConfig(root=tmp_path), presenter)

    assert calls == [("voxtral", "waldo", None, "/refs/casey.wav", "Casey's words.")]


def test_speech_for_no_presenter_uses_the_house_voice_and_transcript(monkeypatch):
    calls = []
    monkeypatch.setattr("emcee.process.speech_provider_for", _recorder(calls))
    config = EmceeConfig(tts=TTSConfig(voice="house-voice", voice_clone="house-clone.wav",
                                       voice_clone_text="house words"))

    speech_for(config, None)

    assert calls == [("voxtral", None, "house-voice", "house-clone.wav", "house words")]


def test_speech_for_honors_a_presenter_pin(monkeypatch):
    calls = []
    monkeypatch.setattr("emcee.process.speech_provider_for", _recorder(calls))
    config = EmceeConfig(tts=TTSConfig(backend="fake", voice="house-voice"))

    speech_for(config, _presenter(tts="voxtral"))

    assert calls[0][0] == "voxtral"


def test_speech_for_raises_when_no_voice_resolvable_at_all(tmp_path):
    # Match on wording unique to speech_for's own message, not just
    # "[tts] voice" -- speech_provider_for's voxtral branch also raises a
    # SpeechError (an EmceeError subclass) containing "[tts] voice" when no
    # voice is configured, so a looser match/guard-removal mutation would
    # slip past undetected if speech_for's own guard were ever deleted.
    with pytest.raises(EmceeError, match="give the profile a presenter") as exc_info:
        speech_for(EmceeConfig(root=tmp_path), None)
    assert type(exc_info.value) is EmceeError


def test_speech_for_folds_in_presenter_bed(monkeypatch):
    monkeypatch.setattr("emcee.process.speech_provider_for", lambda *a, **k: "sentinel")
    presenter = _presenter(bed="/beds/casey.wav")
    config = EmceeConfig(tts=TTSConfig(voice="house-voice", bed="/beds/house.wav", bed_gain_db=-15.0))

    _, bed = speech_for(config, presenter)

    assert bed == Bed(Path("/beds/casey.wav"), -15.0)  # gain is always the station's
```

Add these `ad_hoc_speech` tests after the existing `test_ad_hoc_speech_rejects_more_than_one_voice_source`:

```python
def test_ad_hoc_speech_presenter_routes_through_the_resolver(monkeypatch):
    calls = []
    monkeypatch.setattr("emcee.process.speech_provider_for", _recorder(calls))
    config = EmceeConfig(tts=TTSConfig(backend="fake", voice="house"))

    ad_hoc_speech(config, presenter=_presenter(voice=None, voice_clone="/r.wav",
                                               voice_clone_text="words", tts="voxtral"))

    assert calls == [("voxtral", "waldo", None, "/r.wav", "words")]


def test_ad_hoc_speech_clone_passes_its_transcript_on_the_house_backend(monkeypatch):
    calls = []
    monkeypatch.setattr("emcee.process.speech_provider_for", _recorder(calls))

    ad_hoc_speech(EmceeConfig(), clone_ref="/x.wav", clone_text="spoken words")

    assert calls == [("voxtral", None, None, "/x.wav", "spoken words")]


def test_ad_hoc_speech_preset_has_no_clone(monkeypatch):
    calls = []
    monkeypatch.setattr("emcee.process.speech_provider_for", _recorder(calls))

    ad_hoc_speech(EmceeConfig(), voice="preset-x")

    assert calls == [("voxtral", None, "preset-x", None, None)]
```

In `packages/emcee/tests/test_run_cmd.py`, change the two `speech_provider_for` doubles:

```python
    monkeypatch.setattr(process_mod, "speech_provider_for",
                        lambda config, resolution, *, voice, clone_ref, clone_text:
                        TaggedProvider(voice))
```

and

```python
    monkeypatch.setattr(process_mod, "speech_provider_for",
                        lambda config, resolution, *, voice, clone_ref, clone_text:
                        CloseBlowsUpProvider())
```

- [ ] **Step 3: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_tts.py packages/emcee/tests/test_process.py packages/emcee/tests/test_run_cmd.py -q`
Expected: FAIL — e.g. `TypeError: speech_provider_for() got an unexpected keyword argument 'voice'` / argument-count errors.

- [ ] **Step 4: Implement the providers' key hint**

In `packages/emcee/src/emcee/tts/voxtral.py`, add `key_hint: str = "[tts] api_key",` as the last `__init__` parameter and change the missing-key raise to:

```python
        if not self.api_key:
            raise SpeechError(f"Mistral API key missing: set MISTRAL_API_KEY or {key_hint}")
```

In `packages/emcee/src/emcee/tts/elevenlabs.py`, add `key_hint: str = "[tts] api_key",` as the last `__init__` parameter and change its raise to:

```python
        if not self.api_key:
            raise SpeechError(f"ElevenLabs API key missing: set ELEVENLABS_API_KEY or {key_hint}")
```

- [ ] **Step 5: Implement the factory**

Replace `packages/emcee/src/emcee/tts/__init__.py` with:

```python
from emcee.config import EmceeConfig
from emcee.tts.elevenlabs import ElevenLabsProvider
from emcee.tts.fake import FakeSpeechProvider
from emcee.tts.provider import SpeechError, SpeechProvider
from emcee.tts.resolve import TTSResolution
from emcee.tts.voxtral import VoxtralProvider


def _who(resolution: TTSResolution) -> str:
    return (f"presenter {resolution.presenter!r}" if resolution.presenter is not None
            else "the house voice")


def speech_provider_for(config: EmceeConfig, resolution: TTSResolution, *,
                        voice: str | None, clone_ref: str | None,
                        clone_text: str | None) -> SpeechProvider:
    """Construct exactly the speech backend `resolution` names.

    Every argument is required and has no default: an unmigrated call site
    fails loudly instead of falling back to [tts] backend or dropping the
    transcript. `resolution` comes from `emcee.tts.resolve.resolve_tts`;
    `voice`/`clone_ref`/`clone_text` are the voice source the caller resolved
    (a presenter's own fields, the house [tts] fields, or `emcee say`'s
    flags) -- the factory never reads [tts] voice/voice_clone itself, so a
    presenter fully owns its voice. The render cache keys on the provider's
    `.voice`/`.model`, so a re-pinned presenter never reuses another
    backend's clips.
    """
    backend = resolution.backend
    key_hint = " or ".join(resolution.key_sources) or "[tts] api_key"
    if backend == "fake":
        return FakeSpeechProvider()
    if backend == "voxtral":
        if not (voice or clone_ref):
            raise SpeechError("no Voxtral voice configured: set [tts] voice "
                              "(preset) or [tts] voice_clone (reference clip)")
        return VoxtralProvider(voice=voice, clone_ref=clone_ref, model=resolution.model,
                               api_key=resolution.api_key, key_hint=key_hint)
    if backend == "elevenlabs":
        if clone_ref:
            raise SpeechError(f"{_who(resolution)}: voice cloning is not available on "
                              "elevenlabs: a voice_clone resolves to the elevenlabs backend "
                              "(clone on voxtral or mlx_audio, or use a preset voice)")
        if not voice:
            raise SpeechError("no TTS voice configured: "
                              "set [tts] voice or give the profile a presenter")
        return ElevenLabsProvider(voice=voice, model=resolution.model,
                                  api_key=resolution.api_key, key_hint=key_hint)
    raise SpeechError(f"unknown TTS backend {backend!r}")
```

(The `clone_text` argument is accepted and unused by both hosted branches: Voxtral needs no transcript. Task 9 adds the `mlx_audio` branch above the final raise.)

- [ ] **Step 6: Route `speech_for` and `ad_hoc_speech` through the resolver**

In `packages/emcee/src/emcee/process.py` add `from emcee.tts.resolve import resolve_tts` to the imports. Keep `speech_for`'s existing docstring and append this paragraph to it (before the closing `"""`):

```
    Resolution (`resolve_tts`) runs first and is pure: an unpinned
    presenter under an mlx_audio house, or a missing/uncalibrated mlx model,
    raises here -- before any spend and before `_process_one` clears the
    manifest. The presenter's (or [tts]'s) `voice_clone_text` travels with
    its clip as `clone_text`.
```

Then replace everything in `speech_for` below the docstring with the body below, and replace all of `ad_hoc_speech`:

```python
    # --- speech_for body (below its docstring) ---
    resolution = resolve_tts(config, presenter)
    if presenter is not None:
        voice, clone, text = presenter.voice, presenter.voice_clone, presenter.voice_clone_text
    else:
        voice, clone, text = config.tts.voice, config.tts.voice_clone, config.tts.voice_clone_text
    if not (voice or clone):
        raise EmceeError(
            "voice is active but none is configured: set [tts] voice, "
            "[tts] voice_clone, or give the profile a presenter"
        )
    speech = speech_provider_for(config, resolution, voice=voice, clone_ref=clone,
                                 clone_text=text)
    return speech, _resolve_bed(config, presenter)


def ad_hoc_speech(config: EmceeConfig, *, clone_ref: str | None = None,
                  clone_text: str | None = None, voice: str | None = None,
                  presenter: Presenter | None = None):
    """The speech provider for one ad-hoc `emcee say` run.

    At most one voice source may be named: a reference clip to clone
    (`--clone`, with its transcript `--clone-text`), a preset voice
    (`--voice`), or an existing presenter (`--presenter`, resolved exactly
    as a voiced package's presenter is: its pin, its clip, its transcript).
    With none of them, the house voice via `speech_for`. `--clone`/`--voice`
    voice on the HOUSE backend.

    Unlike `speech_for` this returns the provider alone -- `say` resolves
    its bed separately through `ad_hoc_bed`, which layers the command
    line's overrides on top.
    """
    named = [s for s in (clone_ref, voice, presenter) if s]
    if len(named) > 1:
        raise EmceeError("--clone, --voice and --presenter are mutually exclusive")
    if presenter is not None:
        speech, _ = speech_for(config, presenter)
        return speech
    if clone_ref:
        return speech_provider_for(config, resolve_tts(config, None), voice=None,
                                   clone_ref=clone_ref, clone_text=clone_text)
    if voice:
        return speech_provider_for(config, resolve_tts(config, None), voice=voice,
                                   clone_ref=None, clone_text=None)
    speech, _ = speech_for(config, None)
    return speech
```

- [ ] **Step 7: Check no other call site remains**

Run: `grep -rn "speech_provider_for(" packages/emcee/src`
Expected: only the definition in `tts/__init__.py` and the three calls in `process.py` (`speech_for`, and the two `ad_hoc_speech` branches), each passing `voice=`, `clone_ref=`, `clone_text=`.

- [ ] **Step 8: Run the touched files, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_tts.py packages/emcee/tests/test_process.py packages/emcee/tests/test_run_cmd.py packages/emcee/tests/test_voxtral.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 9: Commit**

```bash
git add packages/emcee/src/emcee/tts/__init__.py packages/emcee/src/emcee/process.py \
        packages/emcee/src/emcee/tts/voxtral.py packages/emcee/src/emcee/tts/elevenlabs.py \
        packages/emcee/tests/conftest.py packages/emcee/tests/test_tts.py \
        packages/emcee/tests/test_process.py packages/emcee/tests/test_run_cmd.py
git commit -m "feat(emcee): resolution-driven speech_provider_for at every call site

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---

### Task 6: `emcee run --dry-run` audits pins

**Implementer model:** Sonnet (mechanical: one function in `cli.py` + tests).
**Live:** no.

Spec: section 1, the `emcee run --dry-run` paragraph; section 6 "`emcee run --dry-run`".

**Files:**
- Modify: `packages/emcee/src/emcee/cli.py:276-283` (`_presenter_file_exists` → `_presenter_file`) and `:361-369` (the dry-run branch)
- Test: `packages/emcee/tests/test_run_cmd.py` (fix `BILLYG.toml` at `:548`; add tests)

**Interfaces:**
- Consumes: `resolve_tts`, `TTSResolutionError` (Task 4); `load_presenter`, `PresenterError`.
- Produces:
  - `emcee.cli._presenter_file(root: Path, presenter_id: str) -> Path | None` — the presenter file, matched case-insensitively, or `None` (replaces `_presenter_file_exists`).
  - `emcee.cli._dry_run_marker(config: EmceeConfig, presenter_id: str) -> str` — `""` or one of `"  [missing presenters/<id>.toml]"`, `"  [invalid presenters/<id>.toml]"` (also for an unreadable or non-UTF-8 file: `OSError`/`ValueError` from the load), `"  [unresolved: <message>]"`, `"  [<backend> <model>]"` (the last only for a pinned presenter).

- [ ] **Step 1: Write the failing tests**

In `packages/emcee/tests/test_run_cmd.py`, in `test_dry_run_lines_labels_and_missing_presenter_marker` replace

```python
    (home / "presenters" / "BILLYG.toml").write_text("")
```

with

```python
    (home / "presenters" / "BILLYG.toml").write_text(
        'name = "Billy G"\nsex = "male"\nvoice = "billy-preset"\ncharacter = "Gruff."\n')
```

Append:

```python
from emcee.presenters import Presenter, save_presenter
from emcee.tts.voxtral import DEFAULT_MODEL as VOX_DEFAULT

from tests.mlx_helpers import TEST_MODEL, calibrate_test_model

_PIN_ASSIGN = """
[assign.profiles.dead]
presenter = "phil"

[assign.profiles.bluegrass]
presenter = "roy"

[assign.profiles.indie]
presenter = "vox"
"""


def _pin_presenters(home: Path) -> None:
    clip = home / "phil.wav"
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"RIFF")
    save_presenter(home, Presenter(id="phil", name="Phil", sex="male", voice_clone=str(clip),
                                   voice_clone_text="It's the chemistry.", tts="mlx_audio",
                                   tts_model=TEST_MODEL, character="x"))
    save_presenter(home, Presenter(id="roy", name="Roy", sex="male", voice="roy-preset",
                                   character="x"))
    save_presenter(home, Presenter(id="vox", name="Vox", sex="male", voice="vox-preset",
                                   tts="voxtral", character="x"))


def test_dry_run_shows_backend_and_model_for_pinned_presenters_only(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home, station = _selection_station(tmp_path, monkeypatch, _PIN_ASSIGN)
    _pin_presenters(home)
    build_package(station, slug="a", profile="dead")
    build_package(station, slug="b", profile="bluegrass")
    build_package(station, slug="c", profile="indie")

    result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert f"would voice: a  dead  phil  [mlx_audio {TEST_MODEL}]\n" in result.output
    assert "would voice: b  bluegrass  roy\n" in result.output  # unpinned: unchanged
    assert f"would voice: c  indie  vox  [voxtral {VOX_DEFAULT}]\n" in result.output


def test_dry_run_marks_invalid_and_unresolved_presenters_and_completes(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    home.mkdir(parents=True)
    station.mkdir()
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n'
        '[tts]\nbackend = "mlx_audio"\nvoice_clone = "/h.wav"\nvoice_clone_text = "Hi."\n\n'
        f'[tts.mlx_audio]\nmodel = "{TEST_MODEL}"\n\n'
        '[assign.profiles.dead]\npresenter = "roy"\n\n'
        '[assign.profiles.indie]\npresenter = "kurt"\n\n'
        '[assign.profiles.jazz]\npresenter = "miles"\n')
    save_presenter(home, Presenter(id="roy", name="Roy", sex="male", voice="roy-preset",
                                   character="x"))  # unpinned under an mlx house
    (home / "presenters" / "kurt.toml").write_text(
        'name = "K"\nsex = "male"\nvoice = "k"\ncharacter = "x"\ntts_modle = "typo"\n')
    save_presenter(home, Presenter(id="miles", name="M", sex="male", voice_clone="/m.wav",
                                   voice_clone_text="So what.", tts="mlx_audio",
                                   tts_model="other/uncalibrated", character="x"))
    build_package(station, slug="a", profile="dead")
    build_package(station, slug="b", profile="indie")
    build_package(station, slug="c", profile="jazz")
    monkeypatch.setattr("emcee.cli.speech_for", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("dry-run must not build a provider")))

    result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert ("would voice: a  dead  roy  [unresolved: presenter 'roy': pin tts explicitly: "
            "the house backend is mlx_audio") in result.output
    assert "would voice: b  indie  kurt  [invalid presenters/kurt.toml]\n" in result.output
    assert ("would voice: c  jazz  miles  [unresolved: presenter 'miles': mlx_audio model "
            "not calibrated for the runaway guard") in result.output
    assert "3 package(s) would be voiced" in result.output


@pytest.mark.parametrize("bad", ["binary", "unreadable"])
def test_dry_run_marks_an_unloadable_presenter_file_invalid(tmp_path, monkeypatch, bad):
    home, station = _selection_station(tmp_path, monkeypatch, _PIN_ASSIGN)
    _pin_presenters(home)
    if bad == "binary":
        (home / "presenters" / "phil.toml").write_bytes(b"\xff\xfe\x00name = \x89PNG\r\n")
    else:  # a directory where the file should be: reading it raises OSError
        (home / "presenters" / "phil.toml").unlink()
        (home / "presenters" / "phil.toml").mkdir()
    build_package(station, slug="a", profile="dead")
    build_package(station, slug="b", profile="bluegrass")

    result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "would voice: a  dead  phil  [invalid presenters/phil.toml]\n" in result.output
    assert "would voice: b  bluegrass  roy\n" in result.output
```

Add `import pytest` to `test_run_cmd.py`'s imports if absent.

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_run_cmd.py -q`
Expected: FAIL — the new markers are absent from the output.

- [ ] **Step 3: Implement**

In `packages/emcee/src/emcee/cli.py`, add imports `from emcee.tts.resolve import TTSResolutionError, resolve_tts`, replace `_presenter_file_exists` with:

```python
def _presenter_file(root: Path, presenter_id: str) -> Path | None:
    """`presenters/<id>.toml`, comparing the id case-insensitively (the
    config may say `BillyG` for `billyg.toml`); None when there is none."""
    pdir = root / "presenters"
    exact = pdir / f"{presenter_id}.toml"
    if exact.exists():
        return exact
    want = f"{presenter_id}.toml".lower()
    if pdir.is_dir():
        for p in pdir.iterdir():
            if p.name.lower() == want:
                return p
    return None


def _dry_run_marker(config: EmceeConfig, presenter_id: str) -> str:
    """The row suffix `run --dry-run` prints for a presenter-assigned package:
    a missing or invalid file, a failed TTS resolution, or -- for a PINNED
    presenter only -- the backend and model it resolves to. Never raises, so
    one bad presenter cannot abort the listing; never preflights. An
    unreadable or non-UTF-8 file (OSError / UnicodeDecodeError, which
    load_presenter does not wrap) is invalid too."""
    path = _presenter_file(config.root, presenter_id)
    if path is None:
        return f"  [missing presenters/{presenter_id}.toml]"
    try:
        presenter = load_presenter(config.root, path.stem)
    except (PresenterError, OSError, ValueError):
        return f"  [invalid presenters/{presenter_id}.toml]"
    try:
        resolution = resolve_tts(config, presenter)
    except TTSResolutionError as exc:
        return f"  [unresolved: {exc}]"
    if resolution.pinned:
        return f"  [{resolution.backend} {resolution.model}]"
    return ""
```

and replace the dry-run branch's marker lines

```python
            if view.presenter is not None and not _presenter_file_exists(
                    config.root, view.presenter):
                line += f"  [missing presenters/{view.presenter}.toml]"
```

with

```python
            if view.presenter is not None:
                line += _dry_run_marker(config, view.presenter)
```

Update the `run` docstring's `--dry-run` sentence to add: "a pinned presenter's row also shows `[<backend> <model>]`, an unloadable presenter file `[invalid presenters/<id>.toml]` and a failed TTS resolution `[unresolved: <message>]`."

- [ ] **Step 4: Run the file, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_run_cmd.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/cli.py packages/emcee/tests/test_run_cmd.py
git commit -m "feat(emcee): run --dry-run shows presenter pins and resolution failures

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---

### Task 7: `preflight()` hook; `_process_one` order; `--fresh` unlink after preflight

**Implementer model:** Sonnet (mechanical: no-op methods + one specified reorder in `cli.py`).
**Live:** no.

Spec: section 2 "Preflight" (protocol, call order, test doubles) and "`emcee voice --fresh`"; Stakes, strict surface 2.

**Files:**
- Modify: `packages/emcee/src/emcee/tts/provider.py` (protocol), `tts/fake.py`, `tts/voxtral.py`, `tts/elevenlabs.py`
- Modify: `packages/emcee/src/emcee/cli.py:226-273` (`_process_one`) and `:448-465` (`voice_cmd`)
- Modify test double: `packages/emcee/tests/test_run_cmd.py` (`TaggedProvider`)
- Test: `packages/emcee/tests/test_tts.py`, `packages/emcee/tests/test_voice_cmd.py`

**Interfaces:**
- Consumes: Task 5's `speech_provider_for` signature (test doubles).
- Produces:
  - `SpeechProvider.preflight(self) -> None` in the protocol; no-op on `VoxtralProvider`, `ElevenLabsProvider`, `FakeSpeechProvider`.
  - `FakeSpeechProvider(fail=False, block=None, preflight_fail=False)`; attribute `preflight_calls: int`; with `preflight_fail=True`, `preflight()` raises `SpeechError("FakeSpeechProvider armed to fail preflight")`.
  - `emcee.cli._process_one(config, pkg, force: bool, fresh: Sequence[str] = ()) -> None` — order: `pkg.manifest()` → `resolve_assignment` → `speech_for` → `try:` `speech.preflight()` → unlink each `dj-audio/<stem>.mp3` in `fresh` and echo `re-rolling …` → `rewrite_manifest(pkg, dj_notes=None, dj_audio=None)` → `process_package(...)` `finally:` best-effort `speech.close()`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/emcee/tests/test_tts.py`:

```python
def test_every_builtin_provider_has_a_noop_preflight(monkeypatch, tmp_path):
    from emcee.tts.voxtral import VoxtralProvider
    fake = FakeSpeechProvider()
    fake.preflight()
    assert fake.preflight_calls == 1 and fake.calls == []  # no synthesis
    VoxtralProvider(voice="v", api_key="k").preflight()
    ElevenLabsProvider(voice="v", api_key="k").preflight()


def test_fake_preflight_can_be_armed_to_fail():
    with pytest.raises(SpeechError, match="armed to fail preflight"):
        FakeSpeechProvider(preflight_fail=True).preflight()
```

Append to `packages/emcee/tests/test_voice_cmd.py`:

```python
# ---------------------------------------------------------------------------
# preflight runs before the --fresh unlink, the manifest clear and any LLM
# spend (spec section 2; strict surface 2).
# ---------------------------------------------------------------------------

from emcee.cli import _process_one
from emcee.package_io import Package
from emcee.tts.fake import FakeSpeechProvider


def _arm_failing_preflight(monkeypatch):
    monkeypatch.setattr(process_mod, "speech_provider_for",
                        lambda config, resolution, *, voice, clone_ref, clone_text:
                        FakeSpeechProvider(preflight_fail=True))


def _forbid_scriptwrite(monkeypatch) -> list:
    scripted: list = []

    def no_llm(settings, task):
        scripted.append(task)
        raise AssertionError("scriptwrite LLM called before preflight passed")

    monkeypatch.setattr(process_mod, "provider_for", no_llm)
    return scripted


def test_failed_preflight_keeps_the_manifest_and_the_fresh_clip(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    pkg_dir = _fully_voiced_package(tmp_path, station, monkeypatch)
    manifest_before = (pkg_dir / "manifest.json").read_bytes()
    clip_before = (pkg_dir / "dj-audio" / "set1-intro.mp3").read_bytes()
    scripted = _forbid_scriptwrite(monkeypatch)
    _arm_failing_preflight(monkeypatch)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--fresh", "set1-intro"])

    assert result.exit_code == 1
    assert "armed to fail preflight" in result.stderr
    assert scripted == []
    assert (pkg_dir / "manifest.json").read_bytes() == manifest_before
    assert (pkg_dir / "dj-audio" / "set1-intro.mp3").read_bytes() == clip_before
    assert "re-rolling" not in result.output


def test_process_one_failed_preflight_spends_nothing_and_keeps_the_manifest(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    pkg_dir = _fully_voiced_package(tmp_path, station, monkeypatch)
    manifest_before = (pkg_dir / "manifest.json").read_bytes()
    scripted = _forbid_scriptwrite(monkeypatch)
    _arm_failing_preflight(monkeypatch)
    from emcee.config import load_config
    from emcee.tts.provider import SpeechError

    with pytest.raises(SpeechError, match="armed to fail preflight"):
        _process_one(load_config(), Package(pkg_dir), False)

    assert scripted == []
    assert (pkg_dir / "manifest.json").read_bytes() == manifest_before


def test_preflight_runs_before_the_unlink_and_the_manifest_clear(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    pkg_dir = _fully_voiced_package(tmp_path, station, monkeypatch)
    events: list[str] = []
    clip = pkg_dir / "dj-audio" / "set1-intro.mp3"

    class Spy(FakeSpeechProvider):
        def preflight(self):
            events.append("preflight:clip-present" if clip.exists() else "preflight:clip-gone")

    import emcee.cli as cli_mod
    real_rewrite = cli_mod.rewrite_manifest

    def spy_rewrite(pkg, **kw):
        events.append("clear")
        return real_rewrite(pkg, **kw)

    monkeypatch.setattr(process_mod, "speech_provider_for",
                        lambda config, resolution, *, voice, clone_ref, clone_text: Spy())
    monkeypatch.setattr(cli_mod, "rewrite_manifest", spy_rewrite)
    _arm_fake_llm(monkeypatch)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--fresh", "set1-intro"])

    assert result.exit_code == 0, result.output
    assert events[:2] == ["preflight:clip-present", "clear"]
    assert "re-rolling set1-intro" in result.output
```

Add `import pytest` to `test_voice_cmd.py`'s imports if absent.

In `packages/emcee/tests/test_run_cmd.py`'s `TaggedProvider`, add:

```python
        def preflight(self):
            pass
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_tts.py packages/emcee/tests/test_voice_cmd.py -q`
Expected: FAIL — `AttributeError: 'FakeSpeechProvider' object has no attribute 'preflight_calls'` / `preflight`.

- [ ] **Step 3: Implement the protocol and no-ops**

In `packages/emcee/src/emcee/tts/provider.py`, add to `SpeechProvider` after `synthesize`'s comment block:

```python
    def preflight(self) -> None: ...
    # Called once per package, unconditionally, before the `--fresh` unlink,
    # the manifest clear and any LLM spend (cli._process_one). A no-op on
    # hosted and fake providers (their configuration errors keep today's
    # timing); the mlx_audio provider synthesizes one fixed sentence so a
    # down server, an unknown model or a bad response fails here, for free.
```

In `tts/voxtral.py` and `tts/elevenlabs.py`, add to each provider class:

```python
    def preflight(self) -> None:
        """No-op: a hosted backend's configuration errors (an invalid key)
        keep today's timing -- they surface at the first synthesis."""
```

In `tts/fake.py`, change `__init__` to `def __init__(self, fail: bool = False, block: str | None = None, preflight_fail: bool = False):`, add `self.preflight_fail = preflight_fail` and `self.preflight_calls = 0`, extend the class docstring with "Arm with preflight_fail=True to have preflight() raise.", and add:

```python
    def preflight(self) -> None:
        self.preflight_calls += 1
        if self.preflight_fail:
            raise SpeechError("FakeSpeechProvider armed to fail preflight")
```

- [ ] **Step 4: Reorder `_process_one` and move the `--fresh` unlink**

In `packages/emcee/src/emcee/cli.py` add `from collections.abc import Sequence` and replace `_process_one` with:

```python
def _process_one(config: EmceeConfig, pkg: Package, force: bool,
                 fresh: Sequence[str] = ()) -> None:
    """Script + voice + broadcast-assemble one package. Shared by `run`'s
    per-pending-package loop and `voice`.

    Per the blessed call convention: `resolve_assignment`/`speech_for` are
    resolved fresh here, every call -- never hoisted above a per-package
    loop -- so each package's presenter-derived voice is never accidentally
    reused for a different package.

    Order (spec section 2, strict surface 2): resolution and provider
    construction, then `speech.preflight()`, THEN the `--fresh` unlink
    (`fresh` holds already-validated, de-duplicated clip stems), THEN the
    manifest clear, THEN `process_package` (the first LLM spend). So no
    configuration-only failure -- an unpinned presenter under an mlx_audio
    house, a down mlx-audio server, a missing model -- can discard a clip or
    take a broadcast-ready package off air.
    """
    manifest = pkg.manifest()
    presenter, title = resolve_assignment(config, manifest)
    speech, bed = speech_for(config, presenter)
    try:
        speech.preflight()
        if fresh:
            audio_dir = pkg.dir / "dj-audio"
            for stem in fresh:
                (audio_dir / f"{stem}.mp3").unlink()
            typer.echo(f"re-rolling {', '.join(fresh)} "
                       "(previous take(s) discarded — TTS is non-deterministic)")
        # JUDGMENT CALL: clears the manifest's dj_notes/dj_audio blocks before
        # reprocessing -- but only now, after resolution, provider
        # construction and preflight have all succeeded. `process_package`
        # overwrites `dj-notes.md` well before the manifest write that marks
        # its success, so a mid-pipeline failure on an already-*ready* package
        # would otherwise leave `dj-notes.md` holding the new (unrecorded)
        # script while the manifest -- and therefore `station.readiness` --
        # still reports the *old* blocks as present. Clearing first means a
        # failure here instead degrades the package to "pending". It never
        # touches `dj-audio/segments.json` (the per-clip cache `--fresh`
        # relies on).
        rewrite_manifest(pkg, dj_notes=None, dj_audio=None)
        process_package(config, pkg, speech, force)
    finally:
        # A raising close() must never mask a successful process_package --
        # or turn a completed package into a reported failure. Best-effort.
        try:
            speech.close()
        except Exception:
            pass
```

In `voice_cmd`, keep the stem validation but remove the unlink loop and its echo; pass the stems through:

```python
    stems: list[str] = []
    if fresh:
        audio_dir = pkg.dir / "dj-audio"
        available = sorted(p.stem for p in audio_dir.glob("*.mp3")) if audio_dir.is_dir() else []
        if not available:
            raise EmceeError(f"{pkg.dir.name} has no DJ audio to re-roll (not voiced yet)")
        unknown = [s for s in fresh if s not in available]
        if unknown:
            raise EmceeError(
                f"no clip {unknown[0]!r} in {pkg.dir.name}; clips: {', '.join(available)}"
            )
        stems = list(dict.fromkeys(fresh))  # dedupe: a repeated stem must not double-unlink

    try:
        _process_one(config, pkg, force, fresh=stems)
```

(the rest of `voice_cmd` is unchanged). In the `--fresh` option help, replace "Deletes the cached clip first so" with "Deletes the cached clip (after the TTS preflight passes) so".

- [ ] **Step 5: Run the files, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_tts.py packages/emcee/tests/test_voice_cmd.py packages/emcee/tests/test_run_cmd.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/emcee/src/emcee/tts packages/emcee/src/emcee/cli.py \
        packages/emcee/tests/test_tts.py packages/emcee/tests/test_voice_cmd.py \
        packages/emcee/tests/test_run_cmd.py
git commit -m "feat(emcee): provider preflight before the --fresh unlink and the manifest clear

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---
### Task 8: `MlxAudioProvider` and the runaway guard

**Implementer model:** Opus (new HTTP provider with many failure classes and the guard; design judgement on the probe's findings).
**Live:** no (reads the Task 1 probe doc; tests are offline).

Spec: section 2 (Request, Identity, Audio contract, Errors, Preflight, Timeout); section 3 "Runaway guard"; section 6 "Provider against `httpx.MockTransport`" and "Runaway guard".

**Before coding:** read `docs/superpowers/2026-10-12-mlx-audio-probe.md`'s Result table. If `midstream_exception` names an httpx class not in `(httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout)`, add it to `_GENERATION_FAILURES` below and to the parametrized test `test_generation_failures_are_not_retried`; if it is `200-empty-body`, the empty-body test already covers it. If `wave_reads_server_wav` is `no`, STOP and report BLOCKED (the audio contract rests on it). If `nframes_header_matches` is `no`, STOP and report BLOCKED: `_read_wav` counts `readframes(getnframes())`, which trusts the header's frame count, and this plan keeps that rather than parsing the data chunk's byte length (the chosen option: the docstring below stays true only while the probe says the header matches). Also STOP and report if the `max_tokens_truncates_silently` row's seconds differ from 25 / 12.5 = 2.0 s by more than one frame (0.08 s): the cap-margin rule and `cap_seconds` depend on 12.5 tokens per second.

**Files:**
- Modify: `packages/emcee/src/emcee/tts/provider.py` (add `SpeechDefect`)
- Modify: `packages/emcee/src/emcee/tts/calibration.py` (add the guard math)
- Create: `packages/emcee/src/emcee/tts/mlx_audio.py`
- Modify: `packages/emcee/tests/mlx_helpers.py` (WAV builder, mock server)
- Test: `packages/emcee/tests/test_mlx_audio.py`

**Interfaces:**
- Consumes: `ModelCalibration` (Task 4); `emcee.audio._encode_mp3(pcm, framerate, channels)` (lazy import).
- Produces:
  - `emcee.tts.provider.SpeechDefect(SpeechError)`: `__init__(self, backend: str, *, text: str, reason: str, transcript: str | None = None)`; attributes `backend`, `text`, `reason`, `transcript`, `segment: str | None = None`; `details == [f'text: "{text}"']` plus `f'transcript: "{transcript}"'` when given; `str()` = `f"{backend} audio failed a quality check{' in ' + segment if segment else ''}: {reason}"`.
  - `emcee.tts.calibration.text_units(text: str) -> int`, `max_tokens_for(cal, text) -> int`, `cap_seconds(cal, max_tokens) -> float`, `guard_problem(cal, text, seconds, max_tokens) -> str | None` (reason substrings: `at the … token cap`, `implausibly long`, `implausibly short`).
  - `emcee.tts.mlx_audio`: `SPEECH_PATH = "/v1/audio/speech"`, `SAMPLE_RATE = 24000`, `PREFLIGHT_TEXT = "Good evening, and welcome to the show."`, `PREFLIGHT_MAX_TOKENS = 200`, `CONNECT_RETRY_DELAY_S = 2.0`, `wav_to_mp3(wav: bytes) -> bytes`, and `MlxAudioProvider(*, url, model, clone_ref, clone_text, calibration, timeout_s=600.0, transport=None, retry_delay_s=CONNECT_RETRY_DELAY_S, sleep=time.sleep)` with `.url` (no trailing slash), `.model`, `.voice`, `synthesize`, `preflight`, `preflight_wav() -> bytes` (the preflight sentence's checked take; `preflight()` is `preflight_wav()` discarding it, and the verified preflight in Task 11 transcribes it), `close`.
  - Error message substrings (exact): `mlx-audio server not reachable at <url> (is the launchd service running?)`; `see the mlx-audio server log`; `mlx-audio returned <status>: <text>`; `non-WAV body`; `empty body`; `emcee needs 16-bit PCM`; `emcee needs mono`; `emcee supports only 24 kHz mlx models`; `needs the reference clip's transcript`.
  - `tests/mlx_helpers.py` additions: `wav_bytes(seconds, *, rate=24000, channels=1, width=2) -> bytes`, `plausible_seconds(text) -> float`, `class MlxServer` (MockTransport handler: attributes `down`, `speech_bodies`, `transcriptions`, `deletes`, `connect_attempts`; method `transport()`).

- [ ] **Step 1: Extend the test helpers**

Append to `packages/emcee/tests/mlx_helpers.py`:

```python
import io
import json
import wave

import httpx


def wav_bytes(seconds: float, *, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    """A silent PCM WAV of `seconds`."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(int(seconds * rate) * channels * width))
    return buf.getvalue()


def plausible_seconds(text: str) -> float:
    """A duration TEST_CAL's guard accepts for `text` (0.06 s per character,
    at least 0.5 s)."""
    return max(0.5, 0.06 * len(" ".join(text.split())))


class MlxServer:
    """An httpx MockTransport handler standing in for mlx_audio.server.

    Speech requests are recorded in `speech_bodies` and answered with a
    plausible silent WAV; `down=True` raises ConnectError for every request
    (counted in `connect_attempts`)."""

    def __init__(self, *, down: bool = False):
        self.down = down
        self.speech_bodies: list[dict] = []
        self.transcriptions: list[httpx.Request] = []
        self.deletes: list[dict] = []
        self.connect_attempts = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            self.connect_attempts += 1
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path == "/v1/audio/speech":
            body = json.loads(request.content)
            self.speech_bodies.append(body)
            return httpx.Response(200, content=wav_bytes(plausible_seconds(body["input"])))
        return httpx.Response(404, text=f"no route {request.method} {request.url.path}")

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)
```

- [ ] **Step 2: Write the failing tests**

Create `packages/emcee/tests/test_mlx_audio.py`:

```python
"""The mlx_audio provider against httpx.MockTransport (spec sections 2-3)."""
import hashlib
import json
import math

import httpx
import pytest

from emcee.tts.calibration import cap_seconds, guard_problem, max_tokens_for, text_units
from emcee.tts.mlx_audio import (CONNECT_RETRY_DELAY_S, PREFLIGHT_MAX_TOKENS, PREFLIGHT_TEXT,
                                 MlxAudioProvider)
from emcee.tts.provider import SpeechDefect, SpeechError, SpeechProvider

from tests.mlx_helpers import TEST_CAL, TEST_MODEL, MlxServer, plausible_seconds, wav_bytes

SENTENCE = "The tapes have always called the room the Rotterdam Civic Hall."
TRANSCRIPT = "It's the chemistry, basically."


@pytest.fixture
def clip(tmp_path):
    p = tmp_path / "phil_ex.wav"
    p.write_bytes(wav_bytes(1.0))
    return p


def make(handler, clip, *, text=TRANSCRIPT, sleeps=None, url="http://127.0.0.1:8000"):
    return MlxAudioProvider(url=url, model=TEST_MODEL, clone_ref=str(clip), clone_text=text,
                            calibration=TEST_CAL, transport=httpx.MockTransport(handler),
                            sleep=(sleeps if sleeps is not None else []).append)


def replying(data: bytes, status: int = 200):
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, content=data)
    return handler, calls


def raising(exc_type):
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        raise exc_type("boom", request=request)
    return handler, calls


# --- guard math ---------------------------------------------------------------


def test_text_units_collapse_whitespace():
    assert text_units("  Here  is\nMorning   Dew. ") == len("Here is Morning Dew.")


def test_max_tokens_is_proportional_to_text_length():
    short, long = "Hello there, friends.", SENTENCE * 3
    assert max_tokens_for(TEST_CAL, short) < max_tokens_for(TEST_CAL, long)
    n = text_units(long)
    assert max_tokens_for(TEST_CAL, long) == math.ceil((8.0 + 0.12 * n) * 12.5)
    assert max_tokens_for(TEST_CAL, SENTENCE) == 195


def test_cap_seconds_is_tokens_over_frame_rate():
    assert cap_seconds(TEST_CAL, 250) == 20.0


def test_guard_accepts_a_plausible_clip():
    mt = max_tokens_for(TEST_CAL, SENTENCE)
    assert guard_problem(TEST_CAL, SENTENCE, plausible_seconds(SENTENCE), mt) is None


def test_guard_rejects_long_short_and_cap_length():
    mt = max_tokens_for(TEST_CAL, SENTENCE)  # n = 63: max_tokens 195 (cap 15.6 s), longest 10.93 s
    assert "implausibly long" in guard_problem(TEST_CAL, SENTENCE, 13.0, mt)
    assert "implausibly short" in guard_problem(TEST_CAL, SENTENCE, 0.2, mt)
    assert "token cap" in guard_problem(TEST_CAL, SENTENCE, cap_seconds(TEST_CAL, mt), mt)
    assert "token cap" in guard_problem(TEST_CAL, SENTENCE, cap_seconds(TEST_CAL, mt) - 0.5, mt)


# --- request ------------------------------------------------------------------


def test_is_a_speech_provider(clip):
    assert isinstance(make(MlxServer(), clip), SpeechProvider)


def test_request_body_and_url(clip):
    handler, calls = replying(wav_bytes(plausible_seconds(SENTENCE)))
    make(handler, clip, url="http://127.0.0.1:8000/").synthesize(SENTENCE, fmt="wav")
    assert str(calls[0].url) == "http://127.0.0.1:8000/v1/audio/speech"
    assert json.loads(calls[0].content) == {
        "model": TEST_MODEL, "input": SENTENCE, "response_format": "wav",
        "max_tokens": max_tokens_for(TEST_CAL, SENTENCE),
        "ref_audio": str(clip.resolve()), "ref_text": TRANSCRIPT}


def test_ref_audio_is_sent_as_an_absolute_path(tmp_path, monkeypatch):
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples" / "phil_ex.wav").write_bytes(wav_bytes(1.0))
    monkeypatch.chdir(tmp_path)
    server = MlxServer()
    p = MlxAudioProvider(url="http://127.0.0.1:8000", model=TEST_MODEL,
                         clone_ref="samples/phil_ex.wav", clone_text=TRANSCRIPT,
                         calibration=TEST_CAL, transport=server.transport())
    p.synthesize(SENTENCE, fmt="wav")
    assert server.speech_bodies[0]["ref_audio"] == str((tmp_path / "samples" / "phil_ex.wav").resolve())


def test_context_arguments_are_accepted_and_not_sent(clip):
    server = MlxServer()
    make(server, clip).synthesize(SENTENCE, fmt="wav", previous_text="a", next_text="b")
    assert set(server.speech_bodies[0]) == {"model", "input", "response_format", "max_tokens",
                                            "ref_audio", "ref_text"}


# --- identity -----------------------------------------------------------------


def test_identity_hashes_clip_and_transcript(clip):
    p = make(MlxServer(), clip)
    expected = hashlib.sha256(clip.read_bytes() + b"\0" + TRANSCRIPT.encode()).hexdigest()[:16]
    assert p.voice == "clone:" + expected
    assert p.model == TEST_MODEL


def test_a_corrected_transcript_changes_the_identity(clip):
    assert make(MlxServer(), clip).voice != make(MlxServer(), clip, text="It is the chemistry.").voice


def test_voice_identity_ignores_surrounding_whitespace_in_transcript(clip):
    server = MlxServer()
    padded = make(server, clip, text=f"  {TRANSCRIPT}\n")
    assert padded.voice == make(MlxServer(), clip).voice
    padded.synthesize(SENTENCE, fmt="wav")
    assert server.speech_bodies[0]["ref_text"] == TRANSCRIPT


# --- construction-time rejection ----------------------------------------------


@pytest.mark.parametrize("text", [None, "", "  \n "])
def test_blank_transcript_rejected_before_synthesis(clip, text):
    with pytest.raises(SpeechError, match="needs the reference clip's transcript"):
        make(MlxServer(), clip, text=text)


def test_unreadable_or_empty_clip_rejected(tmp_path):
    with pytest.raises(SpeechError, match="unreadable"):
        make(MlxServer(), tmp_path / "missing.wav")
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(SpeechError, match="empty"):
        make(MlxServer(), empty)


# --- audio contract -----------------------------------------------------------


def test_wav_is_returned_as_is_for_fmt_wav(clip):
    data = wav_bytes(plausible_seconds(SENTENCE))
    handler, _ = replying(data)
    assert make(handler, clip).synthesize(SENTENCE, fmt="wav") == data


def test_mp3_is_encoded_locally_and_wav_still_requested(clip, monkeypatch):
    seen = {}

    def fake_encode(pcm, framerate, channels):
        seen.update(framerate=framerate, channels=channels, n=len(pcm))
        return b"MP3!"

    monkeypatch.setattr("emcee.audio._encode_mp3", fake_encode)
    server = MlxServer()
    assert make(server, clip).synthesize(SENTENCE) == b"MP3!"
    assert server.speech_bodies[0]["response_format"] == "wav"
    assert (seen["framerate"], seen["channels"]) == (24000, 1)


@pytest.mark.parametrize("data, match", [
    (b"", "empty body"),
    (b"<html>Bad Gateway</html>", "non-WAV body"),
    (wav_bytes(3.0, width=4), "emcee needs 16-bit PCM"),
    (wav_bytes(3.0, channels=2), "emcee needs mono"),
    (wav_bytes(3.0, rate=44100), "emcee supports only 24 kHz mlx models"),
])
def test_bad_audio_is_a_speech_error(clip, data, match):
    handler, _ = replying(data)
    with pytest.raises(SpeechError, match=match):
        make(handler, clip).synthesize(SENTENCE, fmt="wav")


# --- errors -------------------------------------------------------------------


def test_non_200_fails_at_once_with_the_servers_text(clip):
    handler, calls = replying(b"Model not found: 'x' is not a known HuggingFace repo", 404)
    sleeps: list = []
    with pytest.raises(SpeechError, match="mlx-audio returned 404: Model not found"):
        make(handler, clip, sleeps=sleeps).synthesize(SENTENCE)
    assert len(calls) == 1 and sleeps == []


@pytest.mark.parametrize("exc", [httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout])
def test_generation_failures_are_not_retried(clip, exc):
    handler, calls = raising(exc)
    sleeps: list = []
    with pytest.raises(SpeechError, match="see the mlx-audio server log"):
        make(handler, clip, sleeps=sleeps).synthesize(SENTENCE)
    assert len(calls) == 1 and sleeps == []


def test_connect_error_is_retried_once_then_names_the_server(clip):
    handler, calls = raising(httpx.ConnectError)
    sleeps: list = []
    with pytest.raises(SpeechError) as exc:
        make(handler, clip, sleeps=sleeps).synthesize(SENTENCE)
    assert str(exc.value) == ("mlx-audio server not reachable at http://127.0.0.1:8000 "
                              "(is the launchd service running?)")
    assert len(calls) == 2 and sleeps == [CONNECT_RETRY_DELAY_S]


def test_connect_error_then_success(clip):
    data = wav_bytes(plausible_seconds(SENTENCE))
    calls: list = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, content=data)

    assert make(handler, clip).synthesize(SENTENCE, fmt="wav") == data
    assert len(calls) == 2


# --- runaway guard (inside the provider; never retried there) -------------------


@pytest.mark.parametrize("seconds, reason", [
    (13.0, "implausibly long"),
    (0.2, "implausibly short"),
    (cap_seconds(TEST_CAL, max_tokens_for(TEST_CAL, SENTENCE)), "token cap"),
])
def test_guard_failures_raise_speech_defect_unretried(clip, seconds, reason):
    handler, calls = replying(wav_bytes(seconds))
    with pytest.raises(SpeechDefect) as exc:
        make(handler, clip).synthesize(SENTENCE, fmt="wav")
    assert reason in exc.value.reason
    assert exc.value.text == SENTENCE and exc.value.backend == "mlx_audio"
    assert isinstance(exc.value, SpeechError)
    assert exc.value.details == [f'text: "{SENTENCE}"']
    assert len(calls) == 1


def test_speech_defect_message_names_its_segment():
    d = SpeechDefect("mlx_audio", text="x", reason="clip is 9.0s, implausibly long",
                     transcript="y y y")
    d.segment = "set2-intro"
    assert str(d) == "mlx_audio audio failed a quality check in set2-intro: clip is 9.0s, implausibly long"
    assert d.details == ['text: "x"', 'transcript: "y y y"']


# --- preflight ------------------------------------------------------------------


def test_preflight_sentence_is_fixed_and_long_enough():
    assert PREFLIGHT_TEXT == "Good evening, and welcome to the show."
    assert len(PREFLIGHT_TEXT) >= 20 and PREFLIGHT_MAX_TOKENS == 200


def test_preflight_synthesizes_the_fixed_sentence(clip):
    server = MlxServer()
    make(server, clip).preflight()
    body = server.speech_bodies[0]
    assert (body["input"], body["max_tokens"], body["response_format"]) == (
        PREFLIGHT_TEXT, 200, "wav")


def test_preflight_wav_is_the_one_checked_take(clip):
    data = wav_bytes(2.0)
    handler, calls = replying(data)
    assert make(handler, clip).preflight_wav() == data
    assert len(calls) == 1


def test_preflight_on_a_dead_server_fails(clip):
    handler, _ = raising(httpx.ConnectError)
    with pytest.raises(SpeechError, match="not reachable"):
        make(handler, clip).preflight()


def test_preflight_rejects_a_non_24k_model(clip):
    handler, _ = replying(wav_bytes(2.0, rate=22050))
    with pytest.raises(SpeechError, match="24 kHz"):
        make(handler, clip).preflight()


def test_preflight_rejects_an_empty_wav(clip):
    handler, _ = replying(wav_bytes(0.0))
    with pytest.raises(SpeechError, match="no audio"):
        make(handler, clip).preflight()


def test_close_closes_the_client(clip):
    p = make(MlxServer(), clip)
    p.close()
    assert p._client.is_closed
```

- [ ] **Step 3: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_mlx_audio.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'emcee.tts.mlx_audio'`.

- [ ] **Step 4: Add `SpeechDefect`**

Append to `packages/emcee/src/emcee/tts/provider.py` (after `SpeechBlocked`):

```python
class SpeechDefect(SpeechError):
    """Synthesized audio failed a quality check: the mlx_audio runaway guard
    (implausible duration for the text) or transcript verification.

    The provider that detects it never retries; the quality layer
    (tts/quality.py) re-synthesizes once and raises a second failure, which
    fails the package rather than airing the clip. `segment` (the DJ clip
    stem) is filled in by the audio layer after the fact, as for
    SpeechBlocked, so the message is computed in `__str__`."""

    def __init__(self, backend: str, *, text: str, reason: str,
                 transcript: str | None = None):
        details = [f'text: "{text}"']
        if transcript is not None:
            details.append(f'transcript: "{transcript}"')
        super().__init__(f"{backend} audio failed a quality check: {reason}", details=details)
        self.backend = backend
        self.text = text
        self.reason = reason
        self.transcript = transcript
        self.segment: str | None = None

    def __str__(self) -> str:
        where = f" in {self.segment}" if self.segment else ""
        return f"{self.backend} audio failed a quality check{where}: {self.reason}"
```

- [ ] **Step 5: Add the guard math**

Append to `packages/emcee/src/emcee/tts/calibration.py` (add `import math` at the top):

```python
def text_units(text: str) -> int:
    """The length the guard scales with: characters of whitespace-collapsed text."""
    return len(" ".join(text.split()))


def max_tokens_for(cal: ModelCalibration, text: str) -> int:
    """The request's max_tokens: the cap's duration in codec frames. Always
    sent -- the server's default of 1200 (~96 s) silently truncates long
    unchunked segments."""
    return math.ceil((cal.cap_floor_s + cal.cap_s_per_char * text_units(text)) * cal.frame_rate_hz)


def cap_seconds(cal: ModelCalibration, max_tokens: int) -> float:
    return max_tokens / cal.frame_rate_hz


def guard_problem(cal: ModelCalibration, text: str, seconds: float,
                  max_tokens: int) -> str | None:
    """Why `seconds` of audio is implausible for `text`, or None. The cap
    check comes first: a runaway that ran into max_tokens would otherwise
    read as merely long (or, with a cap close to the limit, pass)."""
    n = text_units(text)
    cap = cap_seconds(cal, max_tokens)
    if seconds >= cap - cal.cap_margin_s:
        return f"clip is {seconds:.1f}s, at the {cap:.1f}s token cap (a capped runaway)"
    longest = cal.max_floor_s + cal.max_s_per_char * n
    if seconds > longest:
        return f"clip is {seconds:.1f}s, implausibly long for {n} characters (limit {longest:.1f}s)"
    shortest = max(0.0, cal.min_s_per_char * n - cal.min_slack_s)
    if seconds < shortest:
        return (f"clip is {seconds:.1f}s, implausibly short for {n} characters "
                f"(minimum {shortest:.1f}s)")
    return None
```

- [ ] **Step 6: Implement the provider**

Create `packages/emcee/src/emcee/tts/mlx_audio.py`:

```python
"""Local TTS through mlx-audio's OpenAI-style server (`python -m
mlx_audio.server`, mlx-audio 0.5.8). See spec section 2 and the probe
evidence in docs/superpowers/2026-10-12-mlx-audio-probe.md.

One HTTP dialect, model-agnostic: the model is a request field. Clone-only
(`ref_audio` is a local file path the SERVER reads, so it is always sent
absolute; `ref_text` is its transcript). Always requests WAV: the server
writes 16-bit PCM, read with stdlib `wave`; MP3 is encoded locally. There is
no content filter, so SpeechBlocked and the rephrase path never apply.
"""
import hashlib
import io
import struct
import time
import wave
from collections.abc import Callable
from pathlib import Path

import httpx

from emcee.tts.calibration import ModelCalibration, guard_problem, max_tokens_for
from emcee.tts.provider import SpeechDefect, SpeechError

SPEECH_PATH = "/v1/audio/speech"
SAMPLE_RATE = 24000          # only 24 kHz mlx models are supported (Qwen3-TTS is)
PREFLIGHT_TEXT = "Good evening, and welcome to the show."
PREFLIGHT_MAX_TOKENS = 200
CONNECT_RETRY_DELAY_S = 2.0
# Generation failures after the 200 arrive as an aborted chunked body
# (probe doc). Never retried: a timed-out request keeps running server-side.
_GENERATION_FAILURES = (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout)


def wav_to_mp3(wav: bytes) -> bytes:
    """Encode a 16-bit PCM WAV to MP3 with emcee's own encoder."""
    from emcee.audio import _encode_mp3  # lazy: emcee.audio imports emcee.tts
    with wave.open(io.BytesIO(wav), "rb") as w:
        return _encode_mp3(w.readframes(w.getnframes()), w.getframerate(), w.getnchannels())


class MlxAudioProvider:
    """`.voice` = "clone:" + sha256(clip bytes + b"\\0" + transcript)[:16]
    (Voxtral's pattern, plus the transcript: a corrected transcript
    invalidates cached clips); `.model` = the resolved model id. Both feed
    the render-cache key."""

    def __init__(self, *, url: str, model: str, clone_ref: str, clone_text: str | None,
                 calibration: ModelCalibration, timeout_s: float = 600.0,
                 transport: httpx.BaseTransport | None = None,
                 retry_delay_s: float = CONNECT_RETRY_DELAY_S,
                 sleep: Callable[[float], None] = time.sleep):
        transcript = (clone_text or "").strip()
        if not transcript:
            raise SpeechError("mlx_audio needs the reference clip's transcript "
                              "(voice_clone_text); it is empty")
        path = Path(clone_ref).expanduser().resolve()
        try:
            ref_bytes = path.read_bytes()
        except OSError as e:
            raise SpeechError(f"voice_clone reference unreadable: {e}") from e
        if not ref_bytes:
            raise SpeechError(f"voice_clone reference is empty: {path}")
        self.url = url.rstrip("/")
        self.model = model
        self.voice = "clone:" + hashlib.sha256(
            ref_bytes + b"\0" + transcript.encode()).hexdigest()[:16]
        self._ref_audio = str(path)
        self._ref_text = transcript
        self._cal = calibration
        self._retry_delay_s = retry_delay_s
        self._sleep = sleep
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def synthesize(self, text: str, fmt: str = "mp3", *,
                   previous_text: str | None = None,
                   next_text: str | None = None) -> bytes:
        """previous_text/next_text are accepted for interface parity and
        ignored: the endpoint has no context field. The runaway guard runs on
        every clip; its SpeechDefect is never retried here."""
        max_tokens = max_tokens_for(self._cal, text)
        wav = self._post(text, max_tokens)
        problem = guard_problem(self._cal, text, self._read_wav(wav), max_tokens)
        if problem:
            raise SpeechDefect("mlx_audio", text=text, reason=problem)
        return wav if fmt == "wav" else wav_to_mp3(wav)

    def preflight(self) -> None:
        """One fixed sentence: a down server, an unknown or unloadable model,
        or a bad response fails here, before any LLM spend -- and the cold
        model load is absorbed, at no cost."""
        self.preflight_wav()

    def preflight_wav(self) -> bytes:
        """The preflight sentence's take, after the 16-bit mono 24 kHz and
        non-empty checks. The verified preflight (tts/quality.py) transcribes
        this same take rather than synthesizing a second one."""
        wav = self._post(PREFLIGHT_TEXT, PREFLIGHT_MAX_TOKENS)
        if self._read_wav(wav) <= 0:
            raise SpeechError(f"mlx-audio preflight returned no audio for {self.model!r}; "
                              "see the mlx-audio server log")
        return wav

    def close(self) -> None:
        self._client.close()

    def _post(self, text: str, max_tokens: int) -> bytes:
        body = {"model": self.model, "input": text, "response_format": "wav",
                "max_tokens": max_tokens, "ref_audio": self._ref_audio,
                "ref_text": self._ref_text}
        for attempt in (1, 2):
            try:
                resp = self._client.post(self.url + SPEECH_PATH, json=body)
            except httpx.ConnectError as e:
                if attempt == 1:
                    self._sleep(self._retry_delay_s)
                    continue
                raise SpeechError(f"mlx-audio server not reachable at {self.url} "
                                  "(is the launchd service running?)") from e
            except _GENERATION_FAILURES as e:
                raise SpeechError(f"mlx-audio generation failed mid-response "
                                  f"({type(e).__name__}: {e}); see the mlx-audio server log") from e
            except httpx.HTTPError as e:
                raise SpeechError(f"mlx-audio request failed: {e}") from e
            break
        if resp.status_code != 200:
            raise SpeechError(f"mlx-audio returned {resp.status_code}: {resp.text[:500]}")
        return resp.content

    def _read_wav(self, data: bytes) -> float:
        """Seconds of audio in a server WAV, after checking it is 16-bit mono
        24 kHz. Counted from the frames actually read, not the header."""
        if not data:
            raise SpeechError("mlx-audio returned an empty body; see the mlx-audio server log")
        try:
            with wave.open(io.BytesIO(data), "rb") as w:
                width, channels, rate = w.getsampwidth(), w.getnchannels(), w.getframerate()
                frames = w.readframes(w.getnframes())
        except (wave.Error, EOFError, struct.error) as e:
            raise SpeechError(f"mlx-audio returned a non-WAV body ({e}); "
                              "see the mlx-audio server log") from e
        if width != 2:
            raise SpeechError(f"mlx-audio returned {width * 8}-bit audio; emcee needs 16-bit PCM")
        if channels != 1:
            raise SpeechError(f"mlx-audio returned {channels}-channel audio; emcee needs mono")
        if rate != SAMPLE_RATE:
            raise SpeechError(f"mlx-audio model {self.model!r} returns {rate} Hz audio; "
                              "emcee supports only 24 kHz mlx models")
        return len(frames) / (width * channels * rate)
```

- [ ] **Step 7: Run the file, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_mlx_audio.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 8: Commit**

```bash
git add packages/emcee/src/emcee/tts/provider.py packages/emcee/src/emcee/tts/calibration.py \
        packages/emcee/src/emcee/tts/mlx_audio.py packages/emcee/tests/mlx_helpers.py \
        packages/emcee/tests/test_mlx_audio.py
git commit -m "feat(emcee): mlx_audio provider with the runaway guard

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---

### Task 9: Wire `mlx_audio` into the factory; strict surfaces 1 and 2 end to end

**Implementer model:** Opus (strict-surface tests through three commands; judgement about what "no other provider" means in each path).
**Live:** no.

Spec: Stakes strict surfaces 1-2; section 1 "House voice on mlx_audio" (factory checks); section 2 "Preflight" (per-package error, `emcee run` carries on); section 6 bullets "Strict surface 2 …", "`run`, `voice` and `say --presenter` each send `ref_text` …", "A two-presenter `emcee run` …", and the resolution bullet "a resolved-mlx house voice with a `voice` preset, no clip or a blank transcript rejected".

**Files:**
- Modify: `packages/emcee/src/emcee/tts/__init__.py`
- Modify: `packages/emcee/tests/mlx_helpers.py` (add `install_mlx`)
- Test: `packages/emcee/tests/test_mlx_wiring.py`

**Interfaces:**
- Consumes: `MlxAudioProvider` (Task 8), `CALIBRATED_MODELS` (Task 4), `TTSResolution` (Task 4), `_process_one(config, pkg, force, fresh=())` (Task 7).
- Produces:
  - `speech_provider_for` builds `MlxAudioProvider(url=config.tts.mlx_audio.url, model=resolution.model, clone_ref=clone_ref, clone_text=clone_text, calibration=CALIBRATED_MODELS[resolution.model], timeout_s=config.tts.mlx_audio.timeout_s)` when `resolution.backend == "mlx_audio"`. The factory refers to the class through the module global `MlxAudioProvider` (tests patch `emcee.tts.MlxAudioProvider`).
  - House-voice factory errors (exact substrings): `mlx_audio is clone-only: [tts] voice is a preset`; `mlx_audio needs a reference clip: set [tts] voice_clone`; `mlx_audio needs the reference clip's transcript: set [tts] voice_clone_text`.
  - `tests/mlx_helpers.install_mlx(monkeypatch, server: MlxServer) -> None`.

- [ ] **Step 1: Add the test helper**

Append to `packages/emcee/tests/mlx_helpers.py`:

```python
def install_mlx(monkeypatch, server: MlxServer) -> None:
    """Route the factory's MlxAudioProvider through `server`: no real HTTP,
    no retry sleep."""
    from functools import partial

    from emcee.tts.mlx_audio import MlxAudioProvider
    monkeypatch.setattr("emcee.tts.MlxAudioProvider",
                        partial(MlxAudioProvider, transport=server.transport(),
                                sleep=lambda s: None))
```

- [ ] **Step 2: Write the failing tests**

Create `packages/emcee/tests/test_mlx_wiring.py`:

```python
"""mlx_audio through the factory and the commands: the strict surfaces
(spec Stakes 1 and 2) end to end through `emcee run`, `emcee voice` and
`emcee say --presenter`."""
import json
from pathlib import Path

import pytest
from herder import FakeProvider
from typer.testing import CliRunner

import emcee.process as process_mod
from emcee.cli import _process_one, app
from emcee.config import EmceeConfig, load_config
from emcee.package_io import Package
from emcee.presenters import Presenter, save_presenter
from emcee.process import speech_for
from emcee.tts import speech_provider_for
from emcee.tts.elevenlabs import ElevenLabsProvider
from emcee.tts.mlx_audio import PREFLIGHT_TEXT, MlxAudioProvider
from emcee.tts.provider import SpeechError
from emcee.tts.resolve import resolve_tts
from emcee.tts.voxtral import VoxtralProvider

from tests.helpers import build_package
from tests.mlx_helpers import TEST_MODEL, MlxServer, calibrate_test_model, install_mlx, wav_bytes

runner = CliRunner()
PHIL_TEXT = "It's the chemistry, basically."
SAY_TEXT = "Good evening, everybody, and welcome back to the archive."

_VOXTRAL_HOUSE = '[tts]\nvoice = "house-preset"\n'
_FAKE_HOUSE = '[tts]\nbackend = "fake"\nvoice = "house-preset"\n'
_ASSIGN_DEAD = '[assign.profiles.dead]\npresenter = "phil"\n'
_ASSIGN_ROY = '[assign.profiles.bluegrass]\npresenter = "roy"\n'


def _inner(p):
    # Task 10 wraps mlx providers in the quality layer; look through it.
    return getattr(p, "inner", p)


def _notes_json() -> str:
    return json.dumps({
        "context": "Spring '73 tour",
        "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                       "2": "China Cat Sunflower leads set two."},
        "outro": "I Know You Rider sends us off. Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"],
    })


def _arm_llm(monkeypatch) -> list[str]:
    tasks: list[str] = []

    def fake(settings, task):
        tasks.append(task)
        return FakeProvider(completes=[_notes_json()])

    monkeypatch.setattr(process_mod, "provider_for", fake)
    return tasks


def _home(tmp_path, monkeypatch, tts_toml: str, assign_toml: str) -> tuple[Path, Path]:
    home, station = tmp_path / "home", tmp_path / "station"
    home.mkdir()
    station.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n{tts_toml}\n'
        f'[tts.mlx_audio]\nmodel = "{TEST_MODEL}"\n\n{assign_toml}\n')
    return home, station


def _phil(home: Path, **overrides) -> Presenter:
    clip = home / "phil_ex.wav"
    clip.write_bytes(wav_bytes(1.0))
    d = dict(id="phil", name="Phil", sex="male", voice_clone=str(clip),
             voice_clone_text=PHIL_TEXT, tts="mlx_audio", character="Professorial.")
    d.update(overrides)
    p = Presenter(**d)
    save_presenter(home, p)
    return p


def _roy(home: Path) -> None:
    save_presenter(home, Presenter(id="roy", name="Roy", sex="male", voice="roy-preset",
                                   character="Smooth."))


def _forbid_hosted(monkeypatch) -> list[str]:
    """Fail any construction of a hosted provider, wherever it is imported
    from: the classes' __init__ are patched, not a module's name for them."""
    constructed: list[str] = []

    def forbidden(name):
        def init(self, *args, **kwargs):
            constructed.append(name)
            raise AssertionError(f"{name} constructed for an mlx_audio voice")
        return init

    monkeypatch.setattr(VoxtralProvider, "__init__", forbidden("voxtral"))
    monkeypatch.setattr(ElevenLabsProvider, "__init__", forbidden("elevenlabs"))
    return constructed


def _cmd(command: str, pkg: Path, tmp_path: Path) -> list[str]:
    text = tmp_path / "say.txt"
    text.write_text(SAY_TEXT)
    return {"run": ["run"], "voice": ["voice", str(pkg)],
            "say": ["say", str(text), "--presenter", "phil"]}[command]


# --- the factory ------------------------------------------------------------------


def test_factory_builds_the_mlx_provider_from_the_resolution(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "c.wav"
    clip.write_bytes(wav_bytes(1.0))
    cfg = EmceeConfig.model_validate({"tts": {"mlx_audio": {
        "model": TEST_MODEL, "url": "http://127.0.0.1:9001/", "timeout_s": 42}}})
    phil = Presenter(id="phil", name="P", sex="male", voice_clone=str(clip),
                     voice_clone_text=PHIL_TEXT, tts="mlx_audio", character="x")
    p = _inner(speech_provider_for(cfg, resolve_tts(cfg, phil), voice=None,
                                   clone_ref=str(clip), clone_text=PHIL_TEXT))
    assert isinstance(p, MlxAudioProvider)
    assert (p.url, p.model, p._ref_text) == ("http://127.0.0.1:9001", TEST_MODEL, PHIL_TEXT)
    assert p._client.timeout.read == 42


@pytest.mark.parametrize("voice, clone, text, match", [
    ("house-preset", True, "Hi there.", r"mlx_audio is clone-only: \[tts\] voice is a preset"),
    (None, False, "Hi there.", r"mlx_audio needs a reference clip: set \[tts\] voice_clone"),
    (None, True, "   ", r"mlx_audio needs the reference clip's transcript: set \[tts\] voice_clone_text"),
])
def test_house_voice_on_mlx_rejects_preset_missing_clip_and_blank_transcript(
        tmp_path, monkeypatch, voice, clone, text, match):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "h.wav"
    clip.write_bytes(wav_bytes(1.0))
    cfg = EmceeConfig.model_validate({"tts": {"backend": "mlx_audio",
                                              "mlx_audio": {"model": TEST_MODEL}}})
    with pytest.raises(SpeechError, match=match):
        speech_provider_for(cfg, resolve_tts(cfg, None), voice=voice,
                            clone_ref=str(clip) if clone else None, clone_text=text)


def test_house_voice_on_mlx_through_speech_for_needs_its_transcript(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "h.wav"
    clip.write_bytes(wav_bytes(1.0))
    cfg = EmceeConfig.model_validate({"tts": {"backend": "mlx_audio", "voice_clone": str(clip),
                                              "mlx_audio": {"model": TEST_MODEL}}})
    with pytest.raises(SpeechError, match=r"\[tts\] voice_clone_text"):
        speech_for(cfg, None)


# --- strict surface 1: never silently fall back -----------------------------------


@pytest.mark.parametrize("house", ["voxtral house, mlx presenter", "mlx house"])
@pytest.mark.parametrize("command", ["run", "voice", "say"])
def test_no_fallback_when_the_mlx_server_is_down(tmp_path, monkeypatch, command, house):
    """A Voxtral key in the env and the server down -- with a presenter
    pinned to mlx_audio under a voxtral house, or with the house voice itself
    on mlx_audio (no presenter): the command fails, and no provider but the
    mlx one is constructed (so none is called)."""
    monkeypatch.setenv("MISTRAL_API_KEY", "k-env")
    calibrate_test_model(monkeypatch)
    if house == "mlx house":
        house_clip = tmp_path / "house.wav"
        house_clip.write_bytes(wav_bytes(1.0))
        home, station = _home(tmp_path, monkeypatch,
                              f'[tts]\nbackend = "mlx_audio"\nvoice_clone = "{house_clip}"\n'
                              'voice_clone_text = "Hi there."\n', "")
        pkg = build_package(station, slug="showA")  # no profile: the house voice
    else:
        home, station = _home(tmp_path, monkeypatch, _VOXTRAL_HOUSE, _ASSIGN_DEAD)
        _phil(home)
        pkg = build_package(station, slug="showA", profile="dead")
    args = _cmd(command, pkg, tmp_path)
    if house == "mlx house" and command == "say":
        args = args[:2]  # no --presenter: the house voice
    server = MlxServer(down=True)
    install_mlx(monkeypatch, server)
    constructed = _forbid_hosted(monkeypatch)
    _arm_llm(monkeypatch)

    result = runner.invoke(app, args)

    assert result.exit_code == 1
    assert constructed == []
    assert server.connect_attempts == 2  # one call, retried once, then failed
    message = str(result.exception) if command == "say" else result.stderr
    assert "mlx-audio server not reachable at http://127.0.0.1:8000" in message


# --- strict surface 2: config-only failure never takes a package off air ---------


def _voiced_then_pinned(tmp_path, monkeypatch) -> Path:
    """A package voiced with phil unpinned (house fake), then phil pinned to
    mlx_audio with the server down."""
    calibrate_test_model(monkeypatch)
    home, station = _home(tmp_path, monkeypatch, _FAKE_HOUSE, _ASSIGN_DEAD)
    _phil(home, tts=None)
    _arm_llm(monkeypatch)
    pkg = build_package(station, slug="showA", profile="dead")
    first = runner.invoke(app, ["voice", str(pkg)])
    assert first.exit_code == 0, first.output
    _phil(home)
    install_mlx(monkeypatch, MlxServer(down=True))
    return pkg


def test_dead_server_leaves_a_voiced_package_untouched(tmp_path, monkeypatch):
    pkg_dir = _voiced_then_pinned(tmp_path, monkeypatch)
    before = (pkg_dir / "manifest.json").read_bytes()
    tasks = _arm_llm(monkeypatch)

    with pytest.raises(SpeechError, match="not reachable"):
        _process_one(load_config(), Package(pkg_dir), False)

    assert tasks == []  # no scriptwrite call
    assert (pkg_dir / "manifest.json").read_bytes() == before


def test_dead_server_voice_fresh_keeps_the_manifest_and_the_clip(tmp_path, monkeypatch):
    pkg_dir = _voiced_then_pinned(tmp_path, monkeypatch)
    before = (pkg_dir / "manifest.json").read_bytes()
    clip = pkg_dir / "dj-audio" / "set1-intro.mp3"
    clip_before = clip.read_bytes()
    tasks = _arm_llm(monkeypatch)

    result = runner.invoke(app, ["voice", str(pkg_dir), "--fresh", "set1-intro"])

    assert result.exit_code == 1
    assert "not reachable" in result.stderr
    assert tasks == []
    assert (pkg_dir / "manifest.json").read_bytes() == before
    assert clip.exists() and clip.read_bytes() == clip_before


def test_run_continues_other_presenters_when_mlx_is_down(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home, station = _home(tmp_path, monkeypatch, _FAKE_HOUSE, _ASSIGN_DEAD + _ASSIGN_ROY)
    _phil(home)
    _roy(home)
    a = build_package(station, slug="a", profile="dead")
    b = build_package(station, slug="b", profile="bluegrass")
    a_before = (a / "manifest.json").read_bytes()
    install_mlx(monkeypatch, MlxServer(down=True))
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[_notes_json()]))

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert "error: a: mlx-audio server not reachable" in result.stderr
    assert "voiced: b" in result.output
    assert (a / "manifest.json").read_bytes() == a_before
    assert json.loads((b / "manifest.json").read_text())["dj_audio"] is not None


# --- the transcript travels on every path -----------------------------------------


@pytest.mark.parametrize("command", ["run", "voice", "say"])
def test_each_path_sends_the_presenters_transcript(tmp_path, monkeypatch, command):
    calibrate_test_model(monkeypatch)
    home, station = _home(tmp_path, monkeypatch, _FAKE_HOUSE, _ASSIGN_DEAD)
    phil = _phil(home)
    pkg = build_package(station, slug="showA", profile="dead")
    server = MlxServer()
    install_mlx(monkeypatch, server)
    _arm_llm(monkeypatch)

    result = runner.invoke(app, _cmd(command, pkg, tmp_path))

    assert result.exit_code == 0, result.output
    assert server.speech_bodies
    ref = str(Path(phil.voice_clone).resolve())
    assert all(b["ref_text"] == PHIL_TEXT and b["ref_audio"] == ref for b in server.speech_bodies)
    first = server.speech_bodies[0]
    if command == "say":  # say has no LLM spend and no manifest: no preflight
        assert first["input"] != PREFLIGHT_TEXT
    else:
        assert (first["input"], first["max_tokens"]) == (PREFLIGHT_TEXT, 200)


# --- one provider per package; distinct cache keys --------------------------------


def test_two_presenters_on_different_backends_get_their_own_provider_and_cache_keys(
        tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home, station = _home(tmp_path, monkeypatch, _FAKE_HOUSE, _ASSIGN_DEAD + _ASSIGN_ROY)
    _phil(home)
    _roy(home)
    a = build_package(station, slug="a", profile="dead")
    b = build_package(station, slug="b", profile="bluegrass")
    install_mlx(monkeypatch, MlxServer())
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[_notes_json()]))
    built = []
    real = process_mod.speech_provider_for

    def spy(config, resolution, **kw):
        p = real(config, resolution, **kw)
        built.append((resolution.presenter, resolution.backend, p))
        return p

    monkeypatch.setattr(process_mod, "speech_provider_for", spy)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    assert [(pid, backend) for pid, backend, _ in built] == [("phil", "mlx_audio"), ("roy", "fake")]
    assert built[0][2] is not built[1][2]
    keys_a = json.loads((a / "dj-audio" / "segments.json").read_text())
    keys_b = json.loads((b / "dj-audio" / "segments.json").read_text())
    assert set(keys_a.values()).isdisjoint(keys_b.values())


def test_repinning_a_presenter_changes_the_cache_key(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home, station = _home(tmp_path, monkeypatch, _FAKE_HOUSE, _ASSIGN_DEAD)
    pkg = build_package(station, slug="showA", profile="dead")
    install_mlx(monkeypatch, MlxServer())
    _arm_llm(monkeypatch)
    sidecar = pkg / "dj-audio" / "segments.json"

    _phil(home, tts=None)
    assert runner.invoke(app, ["voice", str(pkg)]).exit_code == 0
    fake_keys = json.loads(sidecar.read_text())
    _phil(home)
    assert runner.invoke(app, ["voice", str(pkg)]).exit_code == 0
    mlx_keys = json.loads(sidecar.read_text())
    _phil(home, tts=None)
    assert runner.invoke(app, ["voice", str(pkg)]).exit_code == 0

    assert set(fake_keys.values()).isdisjoint(mlx_keys.values())
    assert json.loads(sidecar.read_text()) == fake_keys
```

- [ ] **Step 3: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_mlx_wiring.py -q`
Expected: FAIL — `SpeechError: unknown TTS backend 'mlx_audio'`, and `AttributeError` on `emcee.tts.MlxAudioProvider` from `install_mlx`.

- [ ] **Step 4: Implement the factory branch**

In `packages/emcee/src/emcee/tts/__init__.py` add the imports

```python
from emcee.tts.calibration import CALIBRATED_MODELS
from emcee.tts.mlx_audio import MlxAudioProvider
```

add, above `speech_provider_for`:

```python
def _mlx_provider(config: EmceeConfig, resolution: TTSResolution, *, voice: str | None,
                  clone_ref: str | None, clone_text: str | None) -> MlxAudioProvider:
    """mlx_audio is clone-only and needs the clip's transcript. A presenter
    pin is already validated (Presenter); the house voice is checked here,
    naming its [tts] keys."""
    house = resolution.presenter is None
    who = _who(resolution)
    if voice:
        raise SpeechError(
            "mlx_audio is clone-only: [tts] voice is a preset, but the house voice resolves "
            "to mlx_audio; set [tts] voice_clone and [tts] voice_clone_text instead"
            if house else f"{who}: mlx_audio is clone-only (a preset voice cannot be voiced on it)")
    if not clone_ref:
        raise SpeechError(
            "mlx_audio needs a reference clip: set [tts] voice_clone (the house voice "
            "resolves to mlx_audio)" if house else f"{who}: mlx_audio needs voice_clone")
    if not (clone_text or "").strip():
        raise SpeechError(
            "mlx_audio needs the reference clip's transcript: set [tts] voice_clone_text "
            "(the house voice resolves to mlx_audio)"
            if house else f"{who}: mlx_audio needs voice_clone_text, the transcript of voice_clone")
    mlx = config.tts.mlx_audio
    return MlxAudioProvider(url=mlx.url, model=resolution.model, clone_ref=clone_ref,
                            clone_text=clone_text,
                            calibration=CALIBRATED_MODELS[resolution.model],
                            timeout_s=mlx.timeout_s)
```

and in `speech_provider_for`, insert before the final `raise SpeechError(f"unknown TTS backend …")`:

```python
    if backend == "mlx_audio":
        return _mlx_provider(config, resolution, voice=voice, clone_ref=clone_ref,
                             clone_text=clone_text)
```

- [ ] **Step 5: Run the file, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_mlx_wiring.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/emcee/src/emcee/tts/__init__.py packages/emcee/tests/mlx_helpers.py \
        packages/emcee/tests/test_mlx_wiring.py
git commit -m "feat(emcee): wire mlx_audio into the speech factory; strict-surface tests

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---
### Task 10: The quality layer (the single quality retry)

**Implementer model:** Opus (new wrapper whose retry semantics are the safety mechanism; small but judgement-heavy).
**Live:** no.

Spec: section 3 "Quality layer"; section 6 "Runaway guard … Quality layer: one retry, a pass on the retry succeeding, a double failure a `SpeechDefect` carrying `.segment`; `SpeechBlocked` passed through; `preflight()`/`close()` delegated".

**Files:**
- Create: `packages/emcee/src/emcee/tts/quality.py`
- Modify: `packages/emcee/src/emcee/tts/__init__.py` (wrap the mlx provider)
- Modify: `packages/emcee/src/emcee/audio.py:25` (import) and `:342-344` (annotate `SpeechDefect.segment`)
- Test: `packages/emcee/tests/test_quality.py`

**Interfaces:**
- Consumes: `SpeechDefect` (Task 8), `MlxAudioProvider` (Task 8), `_mlx_provider` (Task 9).
- Produces:
  - `emcee.tts.quality.QualitySpeech(inner, *, backend: str, verifier=None)` with attributes `inner`, `backend`, `verifier`, `voice` (= `inner.voice`), `model` (= `inner.model`); methods `synthesize(text, fmt="mp3", *, previous_text=None, next_text=None) -> bytes`, `preflight() -> None`, `close() -> None`, and the private `_attempt(text, fmt, previous_text, next_text) -> bytes` (Task 11 extends it) and `_retrying(text: str, attempt: Callable[[], bytes]) -> bytes` (the two-attempt rule; Task 11's verified mlx preflight reuses it).
  - Double-failure reason suffix (exact): `" (failed twice)"`.
  - Retry notice line (stdout): `"<backend> quality check failed (<reason>); re-synthesizing once"`.
  - `speech_provider_for` returns `QualitySpeech(<MlxAudioProvider>, backend="mlx_audio", verifier=None)` for an `mlx_audio` resolution.
  - `_synthesize_dj_audio` sets `.segment` on a `SpeechDefect` exactly as on a `SpeechBlocked`.

- [ ] **Step 1: Write the failing tests**

Create `packages/emcee/tests/test_quality.py`:

```python
"""The quality layer: the single re-synthesis on a quality failure
(spec section 3 "Quality layer")."""
import json

import httpx
import pytest
from herder import FakeProvider

from emcee.audio import _synthesize_dj_audio
from emcee.config import EmceeConfig, TTSConfig
from emcee.models import ScriptNotes
from emcee.package_io import Package
from emcee.presenters import Presenter
from emcee.process import process_package
from emcee.tts import speech_provider_for
from emcee.tts.mlx_audio import MlxAudioProvider
from emcee.tts.provider import SpeechBlocked, SpeechDefect, SpeechError
from emcee.tts.quality import QualitySpeech
from emcee.tts.resolve import resolve_tts

from tests.helpers import build_package
from tests.mlx_helpers import (TEST_CAL, TEST_MODEL, calibrate_test_model, plausible_seconds,
                               wav_bytes)

WAV = wav_bytes(1.0)
TEXT = "The tapes have always called the room the Rotterdam Civic Hall."


def defect(text=TEXT):
    return SpeechDefect("mlx_audio", text=text, reason="clip is 13.0s, implausibly long")


class Scripted:
    """Inner-provider double: returns or raises `outcomes` in order."""
    voice = "inner-voice"
    model = "inner-model"

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[tuple] = []
        self.preflights = 0
        self.closed = False

    def synthesize(self, text, fmt="mp3", *, previous_text=None, next_text=None):
        self.calls.append((text, fmt, previous_text, next_text))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def preflight(self):
        self.preflights += 1

    def close(self):
        self.closed = True


def layer(inner):
    return QualitySpeech(inner, backend="mlx_audio", verifier=None)


def test_a_pass_is_returned_without_retry():
    inner = Scripted(WAV)
    assert layer(inner).synthesize(TEXT, "wav") == WAV
    assert len(inner.calls) == 1


def test_one_failure_resynthesizes_once_and_the_retry_wins(capsys):
    inner = Scripted(defect(), WAV)
    assert layer(inner).synthesize(TEXT, "wav") == WAV
    assert len(inner.calls) == 2
    assert ("mlx_audio quality check failed (clip is 13.0s, implausibly long); "
            "re-synthesizing once") in capsys.readouterr().out


def test_two_failures_raise_a_speech_defect_naming_the_text():
    inner = Scripted(defect(), defect())
    with pytest.raises(SpeechDefect) as exc:
        layer(inner).synthesize(TEXT, "wav")
    assert exc.value.reason == "clip is 13.0s, implausibly long (failed twice)"
    assert exc.value.text == TEXT
    assert exc.value.details == [f'text: "{TEXT}"']
    assert len(inner.calls) == 2


def test_content_filter_blocks_pass_straight_through():
    inner = Scripted(SpeechBlocked("voxtral", text=TEXT, categories=["sexual"]))
    with pytest.raises(SpeechBlocked):
        layer(inner).synthesize(TEXT)
    assert len(inner.calls) == 1


def test_a_transport_error_is_not_a_quality_retry():
    inner = Scripted(SpeechError("mlx-audio server not reachable at x"))
    with pytest.raises(SpeechError) as exc:
        layer(inner).synthesize(TEXT)
    assert not isinstance(exc.value, SpeechDefect)
    assert len(inner.calls) == 1


def test_format_and_context_are_forwarded():
    inner = Scripted(b"MP3")
    assert layer(inner).synthesize(TEXT, "mp3", previous_text="a", next_text="b") == b"MP3"
    assert inner.calls == [(TEXT, "mp3", "a", "b")]


def test_preflight_and_close_are_delegated_and_the_inner_identity_kept():
    inner = Scripted()
    q = layer(inner)
    q.preflight()
    q.close()
    assert inner.preflights == 1 and inner.closed
    assert (q.voice, q.model) == ("inner-voice", "inner-model")


def test_a_double_failure_in_a_dj_clip_carries_its_segment(tmp_path):
    pkg_dir = build_package(tmp_path / "station", voiced=False)
    notes = ScriptNotes(set_intros={"1": TEXT, "2": "Set two."}, outro="Thanks.")
    with pytest.raises(SpeechDefect) as exc:
        _synthesize_dj_audio(pkg_dir, notes, layer(Scripted(defect(), defect())), False)
    assert exc.value.segment == "set1-intro"
    assert "in set1-intro" in str(exc.value)


def test_a_double_failure_fails_the_package_and_leaves_the_manifest(tmp_path, monkeypatch):
    notes = {"context": "Spring '73 tour",
             "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                            "2": "China Cat Sunflower leads set two."},
             "outro": "I Know You Rider sends us off. Thanks for listening.",
             "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"]}
    monkeypatch.setattr("emcee.process.provider_for",
                        lambda settings, task: FakeProvider(completes=[json.dumps(notes)]))
    pkg = Package(build_package(tmp_path / "station", voiced=False))
    before = pkg.manifest_path.read_bytes()
    config = EmceeConfig(root=tmp_path / "home", tts=TTSConfig(chunk=False))

    with pytest.raises(SpeechDefect):
        process_package(config, pkg, layer(Scripted(defect(), defect())))

    assert pkg.manifest_path.read_bytes() == before


def test_a_runaway_then_a_good_take_through_the_real_provider(tmp_path):
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    takes = iter([30.0, plausible_seconds(TEXT)])
    calls: list = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=wav_bytes(next(takes)))

    inner = MlxAudioProvider(url="http://127.0.0.1:8000", model=TEST_MODEL, clone_ref=str(clip),
                             clone_text="Hi there.", calibration=TEST_CAL,
                             transport=httpx.MockTransport(handler))
    assert layer(inner).synthesize(TEXT, "wav")
    assert len(calls) == 2


def test_the_factory_wraps_every_mlx_provider_guard_only(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = EmceeConfig.model_validate({"tts": {"mlx_audio": {"model": TEST_MODEL}}})
    phil = Presenter(id="phil", name="P", sex="male", voice_clone=str(clip),
                     voice_clone_text="Hi there.", tts="mlx_audio", character="x")
    p = speech_provider_for(cfg, resolve_tts(cfg, phil), voice=None, clone_ref=str(clip),
                            clone_text="Hi there.")
    assert isinstance(p, QualitySpeech) and isinstance(p.inner, MlxAudioProvider)
    assert p.verifier is None and p.backend == "mlx_audio"
    assert (p.voice, p.model) == (p.inner.voice, p.inner.model)


def test_hosted_providers_are_not_wrapped_when_verification_is_off(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    cfg = EmceeConfig()
    p = speech_provider_for(cfg, resolve_tts(cfg, None), voice="v", clone_ref=None,
                            clone_text=None)
    assert not isinstance(p, QualitySpeech)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_quality.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'emcee.tts.quality'`.

- [ ] **Step 3: Implement the layer**

Create `packages/emcee/src/emcee/tts/quality.py`:

```python
"""The quality layer: sole owner of the quality retry (spec section 3).

Wraps every mlx_audio provider (the runaway guard, inside the provider,
raises SpeechDefect and never retries) and -- from transcript verification
on -- every provider whose backend is listed in [tts.verify] backends. Per
`synthesize` call: at most two attempts; a second quality failure raises
SpeechDefect, which fails the package rather than airing the clip. The
retried unit is whatever the caller synthesizes: the sentence when chunked,
the whole segment otherwise.

Keeps the inner `.voice`/`.model`, so cached clips are reused (never
re-verified) and enabling verification does not invalidate the cache.
SpeechBlocked and every other SpeechError pass straight through.
"""
from collections.abc import Callable

import typer

from emcee.tts.provider import SpeechDefect


class QualitySpeech:
    def __init__(self, inner, *, backend: str, verifier=None):
        self.inner = inner
        self.backend = backend
        self.verifier = verifier
        self.voice = inner.voice
        self.model = inner.model

    def synthesize(self, text: str, fmt: str = "mp3", *,
                   previous_text: str | None = None,
                   next_text: str | None = None) -> bytes:
        return self._retrying(text, lambda: self._attempt(text, fmt, previous_text, next_text))

    def _retrying(self, text: str, attempt: Callable[[], bytes]) -> bytes:
        """At most two attempts of `attempt` for `text`: a second quality
        failure raises SpeechDefect."""
        try:
            return attempt()
        except SpeechDefect as first:
            typer.echo(f"{self.backend} quality check failed ({first.reason}); "
                       "re-synthesizing once")
        try:
            return attempt()
        except SpeechDefect as second:
            raise SpeechDefect(second.backend, text=text,
                               reason=f"{second.reason} (failed twice)",
                               transcript=second.transcript) from second

    def _attempt(self, text: str, fmt: str, previous_text: str | None,
                 next_text: str | None) -> bytes:
        return self.inner.synthesize(text, fmt, previous_text=previous_text,
                                     next_text=next_text)

    def preflight(self) -> None:
        self.inner.preflight()

    def close(self) -> None:
        self.inner.close()
```

- [ ] **Step 4: Wrap the mlx provider and annotate the segment**

In `packages/emcee/src/emcee/tts/__init__.py` add `from emcee.tts.quality import QualitySpeech` and change the mlx branch to:

```python
    if backend == "mlx_audio":
        return QualitySpeech(_mlx_provider(config, resolution, voice=voice, clone_ref=clone_ref,
                                           clone_text=clone_text),
                             backend="mlx_audio", verifier=None)
```

In `packages/emcee/src/emcee/audio.py`, change the import to `from emcee.tts.provider import SpeechBlocked, SpeechDefect, SpeechError` and the handler in `_synthesize_dj_audio` to:

```python
            except (SpeechBlocked, SpeechDefect) as failed:
                failed.segment = stem
                raise
```

- [ ] **Step 5: Run the file, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_quality.py packages/emcee/tests/test_mlx_wiring.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/emcee/src/emcee/tts/quality.py packages/emcee/src/emcee/tts/__init__.py \
        packages/emcee/src/emcee/audio.py packages/emcee/tests/test_quality.py
git commit -m "feat(emcee): quality layer owns the single re-synthesis on a guard failure

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---

### Task 11: Transcript verification

**Implementer model:** Opus (STT client, comparison semantics, preflight STT checks for two provider kinds, strict surface "never silently skipped").
**Live:** no.

Spec: section 3 "Transcript verification" (all bullets, including "Never silently skipped"); section 6 "Verification" and the `say` "wrapped when the backend is listed" bullet.

**Files:**
- Create: `packages/emcee/src/emcee/tts/verify.py`
- Modify: `packages/emcee/src/emcee/tts/quality.py` (`_attempt`, `preflight`, `close`)
- Modify: `packages/emcee/src/emcee/tts/__init__.py` (`_quality` wrapping for every backend)
- Modify: `packages/emcee/tests/mlx_helpers.py` (replace `MlxServer`, extend `install_mlx`)
- Test: `packages/emcee/tests/test_verify.py`; `packages/emcee/tests/test_mlx_wiring.py` (append the config-only failure matrix — the first task in which every failure kind it covers exists)

**Interfaces:**
- Consumes: `QualitySpeech` and its `_retrying` (Task 10), `PREFLIGHT_TEXT`, `wav_to_mp3`, `MlxAudioProvider.preflight_wav` (Task 8), `[tts.verify]`/`[tts.mlx_audio]` config (Task 3), the `_forbid_hosted`/`_phil`/`_arm_llm` helpers of `test_mlx_wiring.py` (Task 9).
- Produces (in `emcee.tts.verify`):
  - Constants `TRANSCRIBE_PATH = "/v1/audio/transcriptions"`, `MODELS_PATH = "/v1/models"`, `PREFLIGHT_CLIP = "preflight_en.wav"`, `NUMBER_WORDS: frozenset[str]`, and the thresholds `MISS_FLOOR = 2`, `MISS_FRACTION = 0.25`, `EXTRA_FLOOR = 4`, `EXTRA_FRACTION = 0.5` (INTERIM; Task 12 replaces them with measured values).
  - `comparable_words(text: str) -> list[str]`; `transcript_problem(script: str, transcript: str) -> str | None`.
  - `SttClient(*, url, model, timeout_s=600.0, transport=None)` with `.url`, `.model`, `transcribe(wav: bytes) -> str`, `unload() -> None`, `close()`.
  - `Verifier(stt: SttClient)` with `check(wav, text, *, backend) -> None` (raises `SpeechDefect` with `reason = "transcript mismatch: <problem>"` and `transcript=`) and `close()`.
  - `preflight_clip_wav() -> bytes` (the `emcee.data` resource; missing → `SpeechError` naming `emcee/data/preflight_en.wav`).
  - `emcee.tts._quality(config, resolution, inner)`; the factory refers to `SttClient` through the module global (tests patch `emcee.tts.SttClient`).
  - Error substrings: `mlx-audio server not reachable at <url> for transcription`; `mlx-audio transcription returned <status>`; `verification preflight failed`.
  - `QualitySpeech.preflight()` with a verifier on `mlx_audio`: ONE `inner.preflight_wav()` take (max_tokens 200, the format/rate checks) is transcribed for the comparison, under `_retrying` (at most two takes); `inner.preflight()` is not called in that case.
  - `tests/mlx_helpers.MlxServer(*, down=False, stt_down=False, transcript=None, stt_status=200, speech_status=200)`; `install_mlx` also patches `emcee.tts.SttClient`.

- [ ] **Step 1: Replace the mock server and extend `install_mlx`**

In `packages/emcee/tests/mlx_helpers.py`, replace the `MlxServer` class and `install_mlx` with:

```python
class MlxServer:
    """An httpx MockTransport handler standing in for mlx_audio.server.

    - speech: recorded in `speech_bodies`, answered with a plausible silent WAV,
      or `speech_status` when that is not 200 (an unknown/unloadable model);
    - transcription: recorded in `transcriptions`; answers `transcript(last)`
      where `last` is the last synthesized input (default: echo `last`), or
      `stt_status` when that is not 200;
    - DELETE /v1/models: recorded in `deletes`, 204.
    `down=True` raises ConnectError for every request, `stt_down=True` for
    transcription only (both counted in `connect_attempts`)."""

    def __init__(self, *, down: bool = False, stt_down: bool = False, transcript=None,
                 stt_status: int = 200, speech_status: int = 200):
        self.down = down
        self.stt_down = stt_down
        self.transcript = transcript
        self.stt_status = stt_status
        self.speech_status = speech_status
        self.speech_bodies: list[dict] = []
        self.transcriptions: list[httpx.Request] = []
        self.deletes: list[dict] = []
        self.connect_attempts = 0
        self._last_input = ""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if self.down or (self.stt_down and path == "/v1/audio/transcriptions"):
            self.connect_attempts += 1
            raise httpx.ConnectError("connection refused", request=request)
        if path == "/v1/audio/speech":
            body = json.loads(request.content)
            self.speech_bodies.append(body)
            self._last_input = body["input"]
            if self.speech_status != 200:
                return httpx.Response(self.speech_status, text="Model could not be loaded")
            return httpx.Response(200, content=wav_bytes(plausible_seconds(body["input"])))
        if path == "/v1/audio/transcriptions":
            self.transcriptions.append(request)
            if self.stt_status != 200:
                return httpx.Response(self.stt_status, text="transcription failed")
            heard = self.transcript(self._last_input) if self.transcript else self._last_input
            return httpx.Response(200, json={"text": heard})
        if path == "/v1/models" and request.method == "DELETE":
            self.deletes.append(dict(request.url.params))
            return httpx.Response(204)
        return httpx.Response(404, text=f"no route {request.method} {path}")

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def install_mlx(monkeypatch, server: MlxServer) -> None:
    """Route the factory's MlxAudioProvider and SttClient through `server`:
    no real HTTP, no retry sleep."""
    from functools import partial

    from emcee.tts.mlx_audio import MlxAudioProvider
    from emcee.tts.verify import SttClient
    monkeypatch.setattr("emcee.tts.MlxAudioProvider",
                        partial(MlxAudioProvider, transport=server.transport(),
                                sleep=lambda s: None))
    monkeypatch.setattr("emcee.tts.SttClient", partial(SttClient, transport=server.transport()))
```

- [ ] **Step 2: Write the failing tests**

Create `packages/emcee/tests/test_verify.py`:

```python
"""Transcript verification (spec section 3): the comparison, the STT
client, the layer's use of it, and preflight's end-to-end STT check."""
from pathlib import Path

import json

import httpx
import pytest
from herder import FakeProvider
from typer.testing import CliRunner

import emcee.process as process_mod
from emcee.audio import _synthesize_dj_audio
from emcee.cli import _process_one, app
from emcee.config import EmceeConfig, load_config
from emcee.models import ScriptNotes
from emcee.package_io import Package
from emcee.presenters import Presenter, save_presenter
from emcee.process import ad_hoc_speech, process_package
from emcee.tts import speech_provider_for
from emcee.tts.fake import FakeSpeechProvider
from emcee.tts.mlx_audio import PREFLIGHT_TEXT
from emcee.tts.provider import SpeechDefect, SpeechError
from emcee.tts.quality import QualitySpeech
from emcee.tts.resolve import resolve_tts
from emcee.tts.verify import (SttClient, Verifier, comparable_words, preflight_clip_wav,
                              transcript_problem)

from tests.helpers import build_package
from tests.mlx_helpers import (TEST_MODEL, MlxServer, calibrate_test_model, install_mlx,
                               plausible_seconds, wav_bytes)

runner = CliRunner()
STT = "stt/test-model"
WAV = wav_bytes(1.0)
LINE = "Tonight we open the vault to the Grateful Dead in Rotterdam."


# --- the comparison -------------------------------------------------------------


def test_comparable_words_normalize_and_drop_numbers():
    assert comparable_words("It's May Eleventh, 1972 -- the 15th show!") == ["its", "may", "the", "show"]
    assert comparable_words("Seventy-two, twenty-one hundred.") == []


def test_exact_and_case_punctuation_differences_pass():
    assert transcript_problem(LINE, "tonight, we open the vault to the grateful dead in rotterdam") is None


def test_a_wrong_word_or_two_passes():
    assert transcript_problem("Here is Morning Dew.", "Here is morning due.") is None
    assert transcript_problem(
        "It was really the great hall of De Doelen, in Rotterdam.",
        "It was really the great hall of Dedoulin in Rotterdam.") is None


def test_number_formatting_is_ignored():
    assert transcript_problem("On May eleventh, 1972, the band played.",
                              "On May 11th, nineteen seventy-two, the band played.") is None


def test_all_number_sentence_passes():
    assert transcript_problem("1972.", "Nineteen seventy-two.") is None
    assert transcript_problem("Seventy-two.", "72") is None


def test_too_few_script_words_heard_fails():
    problem = transcript_problem(LINE, "tonight we")
    assert problem is not None and "words were heard" in problem


def test_a_transcript_far_longer_than_the_script_fails():
    loop = " ".join(["here is morning dew"] * 6)
    problem = transcript_problem("Here is Morning Dew.", loop)
    assert problem is not None and "words for a" in problem


def test_an_empty_transcript_fails_a_real_sentence():
    assert transcript_problem(LINE, "") is not None


# --- the STT client ---------------------------------------------------------------


def stt(server, url="http://127.0.0.1:8000"):
    return SttClient(url=url, model=STT, transport=server.transport())


def test_transcription_request_shape():
    server = MlxServer(transcript=lambda last: "  Hello there.  ")
    assert stt(server).transcribe(WAV) == "Hello there."
    req = server.transcriptions[0]
    assert req.url.path == "/v1/audio/transcriptions"
    body = req.content
    assert b'filename="clip.wav"' in body
    assert b'name="model"\r\n\r\nstt/test-model\r\n' in body
    assert b'name="language"\r\n\r\nen\r\n' in body
    assert b'name="response_format"\r\n\r\njson\r\n' in body


def test_failed_transcription_requests_are_speech_errors():
    with pytest.raises(SpeechError, match="not reachable at http://127.0.0.1:8000 for transcription"):
        stt(MlxServer(stt_down=True)).transcribe(WAV)
    with pytest.raises(SpeechError, match="mlx-audio transcription returned 500"):
        stt(MlxServer(stt_status=500)).transcribe(WAV)

    def no_text(request):
        return httpx.Response(200, json={"segments": []})

    client = SttClient(url="http://x", model=STT, transport=httpx.MockTransport(no_text))
    with pytest.raises(SpeechError, match="no text"):
        client.transcribe(WAV)


def test_unload_deletes_the_model():
    server = MlxServer()
    stt(server).unload()
    assert server.deletes == [{"model_name": STT}]


def test_the_bundled_clip_loader_fails_closed_when_missing(monkeypatch):
    monkeypatch.setattr("emcee.tts.verify.PREFLIGHT_CLIP", "no-such-clip.wav")
    with pytest.raises(SpeechError, match="emcee/data/no-such-clip.wav"):
        preflight_clip_wav()


# --- the layer with a verifier ----------------------------------------------------


class Scripted:
    voice = "inner-voice"
    model = "inner-model"

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[tuple] = []
        self.preflights = 0

    def synthesize(self, text, fmt="mp3", *, previous_text=None, next_text=None):
        self.calls.append((text, fmt))
        return self.outcomes.pop(0)

    def preflight(self):
        self.preflights += 1

    def close(self):
        pass


def verified(inner, server, backend="voxtral"):
    return QualitySpeech(inner, backend=backend, verifier=Verifier(stt(server)))


def test_verification_requests_wav_and_encodes_mp3_locally(monkeypatch):
    monkeypatch.setattr("emcee.audio._encode_mp3", lambda pcm, rate, ch: b"MP3!")
    inner = Scripted(WAV)
    server = MlxServer(transcript=lambda last: LINE)
    assert verified(inner, server).synthesize(LINE, "mp3") == b"MP3!"
    assert inner.calls == [(LINE, "wav")]
    assert len(server.transcriptions) == 1


def test_verification_pass_returns_the_wav():
    assert verified(Scripted(WAV), MlxServer(transcript=lambda last: LINE)).synthesize(LINE, "wav") == WAV


def test_verification_fail_then_pass():
    heard = iter(["completely unrelated words about the weather today", LINE])
    inner = Scripted(WAV, WAV)
    assert verified(inner, MlxServer(transcript=lambda last: next(heard))).synthesize(LINE, "wav") == WAV
    assert len(inner.calls) == 2


def test_verification_double_fail_names_both_texts():
    garbage = "completely unrelated words about the weather today"
    with pytest.raises(SpeechDefect) as exc:
        verified(Scripted(WAV, WAV), MlxServer(transcript=lambda last: garbage)).synthesize(LINE, "wav")
    assert exc.value.details == [f'text: "{LINE}"', f'transcript: "{garbage}"']
    assert "transcript mismatch" in exc.value.reason and "(failed twice)" in exc.value.reason


def test_a_failed_transcription_request_is_an_error_never_a_pass():
    inner = Scripted(WAV, WAV)
    with pytest.raises(SpeechError) as exc:
        verified(inner, MlxServer(stt_status=500)).synthesize(LINE, "wav")
    assert not isinstance(exc.value, SpeechDefect)
    assert len(inner.calls) == 1


def test_cache_hits_are_not_re_verified(tmp_path):
    checks: list[str] = []

    class CountingVerifier:
        def check(self, wav, text, *, backend):
            checks.append(text)

        def close(self):
            pass

    pkg = build_package(tmp_path / "station", voiced=False)
    notes = ScriptNotes(set_intros={"1": "Set one opens.", "2": "Set two follows."}, outro="Thanks.")
    speech = QualitySpeech(FakeSpeechProvider(), backend="voxtral", verifier=CountingVerifier())
    _synthesize_dj_audio(pkg, notes, speech, False)
    first = len(checks)
    _synthesize_dj_audio(pkg, notes, speech, False)
    assert first == 3 and len(checks) == first  # every clip came from the cache


# --- which providers are verified ---------------------------------------------------


def _verify_cfg(backends, **tts):
    return EmceeConfig.model_validate({"tts": {
        "mlx_audio": {"model": TEST_MODEL, "stt_model": STT},
        "verify": {"backends": backends}, **tts}})


def test_voxtral_is_verified_only_when_listed(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    off = _verify_cfg(["mlx_audio"])
    on = _verify_cfg(["voxtral"])
    plain = speech_provider_for(off, resolve_tts(off, None), voice="v", clone_ref=None, clone_text=None)
    wrapped = speech_provider_for(on, resolve_tts(on, None), voice="v", clone_ref=None, clone_text=None)
    assert not isinstance(plain, QualitySpeech)
    assert isinstance(wrapped, QualitySpeech) and wrapped.verifier is not None
    assert wrapped.voice == wrapped.inner.voice  # enabling verification keeps the cache key


@pytest.mark.parametrize("backends, verified_", [([], False), (["mlx_audio"], True)])
def test_mlx_gets_a_verifier_only_when_listed(tmp_path, monkeypatch, backends, verified_):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = _verify_cfg(backends)
    phil = Presenter(id="phil", name="P", sex="male", voice_clone=str(clip),
                     voice_clone_text="Hi there.", tts="mlx_audio", character="x")
    p = speech_provider_for(cfg, resolve_tts(cfg, phil), voice=None, clone_ref=str(clip),
                            clone_text="Hi there.")
    assert isinstance(p, QualitySpeech) and (p.verifier is not None) is verified_


def test_say_paths_are_wrapped_when_the_backend_is_listed(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = _verify_cfg(["voxtral"], voice="house-preset")
    host = Presenter(id="roy", name="R", sex="male", voice="roy-preset", character="x")
    for speech in (ad_hoc_speech(cfg), ad_hoc_speech(cfg, clone_ref=str(clip)),
                   ad_hoc_speech(cfg, presenter=host)):
        assert isinstance(speech, QualitySpeech) and speech.verifier is not None


# --- never silently skipped: preflight checks the STT path ---------------------------


def _station(tmp_path, monkeypatch, tts_toml: str, assign_toml: str = "") -> tuple[Path, Path]:
    home, station = tmp_path / "home", tmp_path / "station"
    home.mkdir()
    station.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(f'[station]\nroot = "{station}"\n\n{tts_toml}\n{assign_toml}\n')
    return home, station


def _forbid_scriptwrite(monkeypatch) -> list[str]:
    tasks: list[str] = []

    def no_llm(settings, task):
        tasks.append(task)
        raise AssertionError("LLM called before preflight passed")

    monkeypatch.setattr(process_mod, "provider_for", no_llm)
    return tasks


_MLX_VERIFIED = (f'[tts]\nbackend = "fake"\nvoice = "house"\n\n'
                 f'[tts.mlx_audio]\nmodel = "{TEST_MODEL}"\nstt_model = "{STT}"\n\n'
                 '[tts.verify]\nbackends = ["mlx_audio"]\n')
_VOXTRAL_VERIFIED = (f'[tts]\nvoice = "house-preset"\n\n'
                     f'[tts.mlx_audio]\nstt_model = "{STT}"\n\n'
                     '[tts.verify]\nbackends = ["voxtral"]\n')


def _mlx_presenter(home: Path) -> None:
    clip = home / "phil_ex.wav"
    clip.write_bytes(WAV)
    save_presenter(home, Presenter(id="phil", name="Phil", sex="male", voice_clone=str(clip),
                                   voice_clone_text="It's the chemistry.", tts="mlx_audio",
                                   character="x"))


@pytest.mark.parametrize("server_kwargs, error", [
    ({"stt_down": True}, "for transcription"),
    ({"transcript": lambda last: "nothing at all like the words that were sent"}, "transcript mismatch"),
])
def test_mlx_preflight_fails_the_package_on_a_broken_stt_path(tmp_path, monkeypatch,
                                                              server_kwargs, error):
    calibrate_test_model(monkeypatch)
    home, station = _station(tmp_path, monkeypatch, _MLX_VERIFIED,
                             '[assign.profiles.dead]\npresenter = "phil"\n')
    _mlx_presenter(home)
    pkg_dir = build_package(station, slug="showA", profile="dead", voiced=True)
    before = (pkg_dir / "manifest.json").read_bytes()
    install_mlx(monkeypatch, MlxServer(**server_kwargs))
    tasks = _forbid_scriptwrite(monkeypatch)

    with pytest.raises(SpeechError, match=error):
        _process_one(load_config(), Package(pkg_dir), False)

    assert tasks == []
    assert (pkg_dir / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("server_kwargs, error", [
    ({"stt_down": True}, "for transcription"),
    ({"transcript": lambda last: "nothing at all like the check sentence"}, "verification preflight failed"),
])
def test_hosted_preflight_checks_the_bundled_clip(tmp_path, monkeypatch, server_kwargs, error):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    home, station = _station(tmp_path, monkeypatch, _VOXTRAL_VERIFIED)
    pkg_dir = build_package(station, slug="showA", voiced=True)  # no profile: the house voice
    before = (pkg_dir / "manifest.json").read_bytes()
    install_mlx(monkeypatch, MlxServer(**server_kwargs))
    monkeypatch.setattr("emcee.tts.verify.preflight_clip_wav", lambda: wav_bytes(2.0))
    tasks = _forbid_scriptwrite(monkeypatch)

    with pytest.raises(SpeechError, match=error):
        _process_one(load_config(), Package(pkg_dir), False)

    assert tasks == []
    assert (pkg_dir / "manifest.json").read_bytes() == before


def test_hosted_preflight_passes_on_a_good_transcription(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    _station(tmp_path, monkeypatch, _VOXTRAL_VERIFIED)
    server = MlxServer(transcript=lambda last: PREFLIGHT_TEXT)
    install_mlx(monkeypatch, server)
    monkeypatch.setattr("emcee.tts.verify.preflight_clip_wav", lambda: wav_bytes(2.0))
    cfg = load_config()
    speech = speech_provider_for(cfg, resolve_tts(cfg, None), voice="house-preset",
                                 clone_ref=None, clone_text=None)
    speech.preflight()
    assert len(server.transcriptions) == 1 and server.speech_bodies == []  # no hosted spend


def _verified_mlx_speech(tmp_path, monkeypatch, server):
    """A verified, unchunked mlx provider routed through `server`, and its config."""
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = _verify_cfg(["mlx_audio"], chunk=False).model_copy(update={"root": tmp_path / "home"})
    phil = Presenter(id="phil", name="P", sex="male", voice_clone=str(clip),
                     voice_clone_text="Hi there.", tts="mlx_audio", character="x")
    install_mlx(monkeypatch, server)
    return cfg, speech_provider_for(cfg, resolve_tts(cfg, phil), voice=None,
                                    clone_ref=str(clip), clone_text="Hi there.")


def test_verified_mlx_preflight_transcribes_its_one_take(tmp_path, monkeypatch):
    server = MlxServer(transcript=lambda last: PREFLIGHT_TEXT)
    _, speech = _verified_mlx_speech(tmp_path, monkeypatch, server)
    speech.preflight()
    assert [(b["input"], b["max_tokens"]) for b in server.speech_bodies] == [(PREFLIGHT_TEXT, 200)]
    assert len(server.transcriptions) == 1
    assert wav_bytes(plausible_seconds(PREFLIGHT_TEXT)) in server.transcriptions[0].content


def test_verified_mlx_preflight_retries_once_on_a_mismatch(tmp_path, monkeypatch):
    heard = iter(["nothing like it, the weather today", PREFLIGHT_TEXT])
    server = MlxServer(transcript=lambda last: next(heard))
    _, speech = _verified_mlx_speech(tmp_path, monkeypatch, server)
    speech.preflight()
    assert [(b["input"], b["max_tokens"]) for b in server.speech_bodies] == [(PREFLIGHT_TEXT, 200)] * 2
    assert len(server.transcriptions) == 2


def test_a_verified_package_whose_segment_fails_twice_is_not_voiced(tmp_path, monkeypatch):
    garbage = "completely unrelated words about the weather today"
    cfg, speech = _verified_mlx_speech(tmp_path, monkeypatch,
                                       MlxServer(transcript=lambda last: garbage))
    notes = {"context": "Spring '73 tour",
             "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                            "2": "China Cat Sunflower leads set two."},
             "outro": "I Know You Rider sends us off. Thanks for listening.",
             "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"]}
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[json.dumps(notes)]))
    pkg = Package(build_package(tmp_path / "station", voiced=False))
    before = pkg.manifest_path.read_bytes()

    with pytest.raises(SpeechDefect) as exc:
        process_package(cfg, pkg, speech)

    assert exc.value.segment == "set1-intro"
    assert "in set1-intro" in str(exc.value) and "(failed twice)" in str(exc.value)
    assert pkg.manifest_path.read_bytes() == before
    assert not (pkg.dir / "dj-audio" / "set1-intro.mp3").exists()


def test_say_verifies_without_preflight(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home, _ = _station(tmp_path, monkeypatch, _MLX_VERIFIED)
    _mlx_presenter(home)
    server = MlxServer(stt_down=True)
    install_mlx(monkeypatch, server)
    text = tmp_path / "say.txt"
    text.write_text("Good evening, everybody, and welcome back to the archive.")

    result = runner.invoke(app, ["say", str(text), "--presenter", "phil"])

    assert result.exit_code == 1
    assert "for transcription" in str(result.exception)
    assert server.speech_bodies and server.speech_bodies[0]["input"] != PREFLIGHT_TEXT
```

Append to `packages/emcee/tests/test_mlx_wiring.py` (Task 9's file: its `_phil`, `_forbid_hosted`, `_arm_llm`, `_VOXTRAL_HOUSE` and `_ASSIGN_DEAD` are reused), and add `import re` and `from emcee.errors import EmceeError` to its imports:

```python
# --- strict surface 2: every configuration-only failure kind ----------------------
# (Task 11: the first task in which every kind below exists.)

_CONFIG_ONLY_FAILURES = [
    "unpinned presenter under an mlx house", "missing mlx model", "uncalibrated model",
    "unloadable model", "blank house transcript", "mlx house voice, server down",
    "mlx-pinned presenter, server down", "verification listed, STT unreachable",
]


def _config_only_failure(tmp_path, monkeypatch, case: str) -> tuple[Path, MlxServer, str]:
    """A broadcast-ready package (dj-audio/set1-intro.mp3 on disk) whose next
    voicing fails on configuration alone. Returns the package dir, the mock
    server to install and the expected error substring."""
    calibrate_test_model(monkeypatch)
    monkeypatch.setenv("MISTRAL_API_KEY", "k-env")  # a hosted fallback would have a key
    house_clip = tmp_path / "house.wav"
    house_clip.write_bytes(wav_bytes(1.0))

    def mlx_house(transcript: str) -> str:
        return (f'[tts]\nbackend = "mlx_audio"\nvoice_clone = "{house_clip}"\n'
                f'voice_clone_text = "{transcript}"\n')

    tts, mlx, verify = _VOXTRAL_HOUSE, f'model = "{TEST_MODEL}"\n', ""
    profile, phil, server = "dead", {}, MlxServer()
    if case == "unpinned presenter under an mlx house":
        tts, phil, error = mlx_house("Hi there."), {"tts": None}, "pin tts explicitly"
    elif case == "missing mlx model":
        mlx, error = "", "no mlx_audio model"
    elif case == "uncalibrated model":
        mlx, error = 'model = "other/uncalibrated"\n', "not calibrated for the runaway guard"
    elif case == "unloadable model":
        server, error = MlxServer(speech_status=500), "mlx-audio returned 500"
    elif case == "blank house transcript":
        tts, profile, error = mlx_house("   "), None, "set [tts] voice_clone_text"
    elif case == "mlx house voice, server down":
        tts, profile, error = mlx_house("Hi there."), None, "not reachable"
        server = MlxServer(down=True)
    elif case == "mlx-pinned presenter, server down":
        server, error = MlxServer(down=True), "not reachable"
    elif case == "verification listed, STT unreachable":
        mlx += 'stt_model = "stt/test-model"\n'
        verify = '[tts.verify]\nbackends = ["mlx_audio"]\n'
        server, error = MlxServer(stt_down=True), "for transcription"
    else:
        raise AssertionError(case)
    home, station = tmp_path / "home", tmp_path / "station"
    home.mkdir()
    station.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(f'[station]\nroot = "{station}"\n\n{tts}\n'
                                      f'[tts.mlx_audio]\n{mlx}\n{verify}\n{_ASSIGN_DEAD}\n')
    _phil(home, **phil)
    return build_package(station, slug="showA", profile=profile, voiced=True), server, error


@pytest.mark.parametrize("driver", ["_process_one", "voice --fresh"])
@pytest.mark.parametrize("case", _CONFIG_ONLY_FAILURES)
def test_a_config_only_failure_spends_nothing_and_keeps_the_package(tmp_path, monkeypatch,
                                                                    case, driver):
    pkg_dir, server, error = _config_only_failure(tmp_path, monkeypatch, case)
    install_mlx(monkeypatch, server)
    constructed = _forbid_hosted(monkeypatch)
    tasks = _arm_llm(monkeypatch)
    manifest = (pkg_dir / "manifest.json").read_bytes()
    clip = pkg_dir / "dj-audio" / "set1-intro.mp3"
    clip_bytes = clip.read_bytes()

    if driver == "_process_one":
        with pytest.raises(EmceeError, match=re.escape(error)):
            _process_one(load_config(), Package(pkg_dir), False, fresh=["set1-intro"])
    else:
        result = runner.invoke(app, ["voice", str(pkg_dir), "--fresh", "set1-intro"])
        assert result.exit_code == 1
        assert error in result.stderr

    assert tasks == []  # scriptwrite never called
    assert constructed == []  # no hosted provider
    assert (pkg_dir / "manifest.json").read_bytes() == manifest
    assert clip.exists() and clip.read_bytes() == clip_bytes  # the --fresh clip survives
```

- [ ] **Step 3: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_verify.py packages/emcee/tests/test_mlx_wiring.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'emcee.tts.verify'` (`install_mlx` now imports it, so the wiring file fails too).

- [ ] **Step 4: Implement `verify.py`**

Create `packages/emcee/src/emcee/tts/verify.py`:

```python
"""Transcript verification (spec section 3).

Transcribes synthesized audio on the mlx-audio server and fails only on a
GROSS mismatch with the text sent: too few of the script's words heard, or a
transcript far longer than the script (babble, a repetition loop). It
tolerates a wrong word or two per sentence -- ASR misrenders proper nouns
("De Doelen" fails on Voxtral too) and the lexicon's respellings
("Shugaree") are sent as spelled -- and ignores number-bearing tokens on both
sides, since number formatting is open-ended.

A failed transcription request is a SpeechError, never a pass.
"""
import re
from collections import Counter
from importlib import resources

import httpx

from emcee.tts.provider import SpeechDefect, SpeechError

TRANSCRIBE_PATH = "/v1/audio/transcriptions"
MODELS_PATH = "/v1/models"
# A ~2 s clip of mlx_audio.PREFLIGHT_TEXT, rendered with an Apache-2.0
# preset-voice model (provenance: docs/superpowers/2026-10-12-mlx-audio-calibration.md).
PREFLIGHT_CLIP = "preflight_en.wav"

# Gross-mismatch thresholds. INTERIM values, replaced by the measured ones
# from the calibration run (implementation plan Task 12). A script of n
# comparable words may lose up to max(MISS_FLOOR, int(MISS_FRACTION * n))
# of them, and the transcript may run up to max(EXTRA_FLOOR,
# int(EXTRA_FRACTION * n)) words longer.
MISS_FLOOR = 2
MISS_FRACTION = 0.25
EXTRA_FLOOR = 4
EXTRA_FRACTION = 0.5

NUMBER_WORDS = frozenset("""
    zero one two three four five six seven eight nine ten eleven twelve thirteen
    fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty
    sixty seventy eighty ninety hundred thousand million billion first second third
    fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth
    fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth
    thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth hundredth
    thousandth millionth
""".split())
_APOSTROPHES = str.maketrans("", "", "'’‘`")
_WORD = re.compile(r"[^\W_]+")


def comparable_words(text: str) -> list[str]:
    """Lower-cased words with apostrophes and punctuation removed, minus every
    number-bearing token (digits or a spelled-out number word)."""
    words = _WORD.findall(text.lower().translate(_APOSTROPHES))
    return [w for w in words if w not in NUMBER_WORDS and not any(c.isdigit() for c in w)]


def transcript_problem(script: str, transcript: str) -> str | None:
    """Why `transcript` grossly mismatches `script`, or None."""
    want, heard = comparable_words(script), comparable_words(transcript)
    n = len(want)
    found = sum((Counter(want) & Counter(heard)).values())
    if n - found > max(MISS_FLOOR, int(MISS_FRACTION * n)):
        return f"only {found} of the script's {n} words were heard"
    if len(heard) - n > max(EXTRA_FLOOR, int(EXTRA_FRACTION * n)):
        return f"heard {len(heard)} words for a {n}-word script"
    return None


class SttClient:
    """The mlx-audio server's transcription endpoint. Used by verification
    and by `emcee presenter add/edit --transcribe`."""

    def __init__(self, *, url: str, model: str, timeout_s: float = 600.0,
                 transport: httpx.BaseTransport | None = None):
        self.url = url.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def transcribe(self, wav: bytes) -> str:
        # The server picks its temp-file format from the upload's suffix;
        # httpx's default file name maps to .mp3, which needs ffmpeg.
        files = {"file": ("clip.wav", wav, "audio/wav")}
        data = {"model": self.model, "language": "en", "response_format": "json"}
        try:
            resp = self._client.post(self.url + TRANSCRIBE_PATH, files=files, data=data)
        except httpx.ConnectError as e:
            raise SpeechError(f"mlx-audio server not reachable at {self.url} for transcription "
                              "(is the launchd service running?)") from e
        except httpx.HTTPError as e:
            raise SpeechError(f"transcription request failed: {e}") from e
        if resp.status_code != 200:
            raise SpeechError(f"mlx-audio transcription returned {resp.status_code}: "
                              f"{resp.text[:500]}")
        try:
            text = resp.json().get("text")
        except (ValueError, AttributeError) as e:
            raise SpeechError(f"mlx-audio transcription returned non-JSON: {resp.text[:200]}") from e
        if not isinstance(text, str):
            raise SpeechError("mlx-audio transcription returned no text")
        return text.strip()

    def unload(self) -> None:
        """Free the STT model on the server (it keeps every model it has
        served resident until restart)."""
        try:
            resp = self._client.delete(self.url + MODELS_PATH, params={"model_name": self.model})
        except httpx.HTTPError as e:
            raise SpeechError(f"could not unload {self.model!r} from mlx-audio: {e}") from e
        if resp.status_code not in (200, 204, 404):
            raise SpeechError(f"could not unload {self.model!r}: mlx-audio returned "
                              f"{resp.status_code}")

    def close(self) -> None:
        self._client.close()


class Verifier:
    def __init__(self, stt: SttClient):
        self.stt = stt

    def check(self, wav: bytes, text: str, *, backend: str) -> None:
        transcript = self.stt.transcribe(wav)
        problem = transcript_problem(text, transcript)
        if problem:
            raise SpeechDefect(backend, text=text, reason=f"transcript mismatch: {problem}",
                               transcript=transcript)

    def close(self) -> None:
        self.stt.close()


def preflight_clip_wav() -> bytes:
    """The bundled check clip a hosted backend's preflight transcribes. Fails
    closed: a build without it cannot verify, so it cannot voice."""
    try:
        return resources.files("emcee.data").joinpath(PREFLIGHT_CLIP).read_bytes()
    except OSError as e:
        raise SpeechError(f"verification preflight clip missing from this build "
                          f"(emcee/data/{PREFLIGHT_CLIP}); verification cannot be checked") from e
```

- [ ] **Step 5: Verification inside the layer**

In `packages/emcee/src/emcee/tts/quality.py` add the imports

```python
from emcee.tts import verify as verify_mod
from emcee.tts.mlx_audio import PREFLIGHT_TEXT, wav_to_mp3
from emcee.tts.provider import SpeechDefect, SpeechError
```

and replace `_attempt`, `preflight` and `close` with:

```python
    def _attempt(self, text: str, fmt: str, previous_text: str | None,
                 next_text: str | None) -> bytes:
        if self.verifier is None:
            return self.inner.synthesize(text, fmt, previous_text=previous_text,
                                         next_text=next_text)
        # Always WAV from the inner provider: verification transcribes it, and
        # an MP3 caller gets a local encode (so a hosted backend's unchunked
        # output changes only when that backend is listed).
        wav = self.inner.synthesize(text, "wav", previous_text=previous_text,
                                    next_text=next_text)
        self.verifier.check(wav, text, backend=self.backend)
        return wav if fmt == "wav" else wav_to_mp3(wav)

    def preflight(self) -> None:
        """Verification is never silently skipped: when it applies, the STT
        path is checked end to end here, before any LLM spend and before the
        manifest clear. mlx: ONE take of the preflight sentence (max_tokens
        200, the format/rate checks) is transcribed for the full comparison,
        with the single retry (synthesis is non-deterministic) -- so the
        inner preflight, which would synthesize a second take, is skipped.
        Hosted: the bundled clip must transcribe to a pass -- no hosted spend."""
        if self.verifier is None:
            self.inner.preflight()
            return
        if self.backend == "mlx_audio":
            def take() -> bytes:
                wav = self.inner.preflight_wav()
                self.verifier.check(wav, PREFLIGHT_TEXT, backend=self.backend)
                return wav
            self._retrying(PREFLIGHT_TEXT, take)
            return
        self.inner.preflight()
        try:
            self.verifier.check(verify_mod.preflight_clip_wav(), PREFLIGHT_TEXT,
                                backend=self.backend)
        except SpeechDefect as defect:
            raise SpeechError(
                "verification preflight failed: the speech-to-text model did not transcribe "
                f"emcee's check clip correctly ({defect.reason}); fix [tts.mlx_audio] "
                "stt_model or the server before voicing", details=defect.details) from defect

    def close(self) -> None:
        try:
            self.inner.close()
        finally:
            if self.verifier is not None:
                self.verifier.close()
```

Update the module docstring's second paragraph to say verification now applies when the backend is listed.

- [ ] **Step 6: Wrap every listed backend in the factory**

In `packages/emcee/src/emcee/tts/__init__.py` add `from emcee.tts.verify import SttClient, Verifier`, add:

```python
def _quality(config: EmceeConfig, resolution: TTSResolution, inner) -> SpeechProvider:
    """Every mlx_audio provider gets the quality layer (the guard's retry);
    every provider whose backend is listed in [tts.verify] backends also gets
    a verifier on [tts.mlx_audio] stt_model (config guarantees one is set)."""
    listed = resolution.backend in config.tts.verify.backends
    if resolution.backend != "mlx_audio" and not listed:
        return inner
    verifier = None
    if listed:
        mlx = config.tts.mlx_audio
        verifier = Verifier(SttClient(url=mlx.url, model=mlx.stt_model, timeout_s=mlx.timeout_s))
    return QualitySpeech(inner, backend=resolution.backend, verifier=verifier)
```

and route the three real branches through it:

```python
        return _quality(config, resolution, VoxtralProvider(
            voice=voice, clone_ref=clone_ref, model=resolution.model,
            api_key=resolution.api_key, key_hint=key_hint))
```

```python
        return _quality(config, resolution, ElevenLabsProvider(
            voice=voice, model=resolution.model, api_key=resolution.api_key, key_hint=key_hint))
```

```python
    if backend == "mlx_audio":
        return _quality(config, resolution, _mlx_provider(
            config, resolution, voice=voice, clone_ref=clone_ref, clone_text=clone_text))
```

(`fake` is never wrapped: it cannot be listed.)

- [ ] **Step 7: Run the touched files, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_verify.py packages/emcee/tests/test_quality.py packages/emcee/tests/test_mlx_wiring.py packages/emcee/tests/test_mlx_audio.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 8: Commit**

```bash
git add packages/emcee/src/emcee/tts/verify.py packages/emcee/src/emcee/tts/quality.py \
        packages/emcee/src/emcee/tts/__init__.py packages/emcee/tests/mlx_helpers.py \
        packages/emcee/tests/test_verify.py packages/emcee/tests/test_mlx_wiring.py
git commit -m "feat(emcee): transcript verification on the mlx-audio server's STT model

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---
### Task 12: Calibration run — measured constants, the first calibrated model, the bundled preflight clip

**Implementer model:** Opus (live measurement and the judgement of which constants to adopt; the spec makes these the gate for Phil going live).
**Live:** yes — needs the real `mlx_audio.server` (Qwen3-TTS 1.7B and the Task 1 STT model, both cached), a second server for Kokoro, network for the Kokoro download, and optionally the Mistral API (≈10 short Voxtral requests).

**Checkpoint 1 — operator approval before this task starts (orchestrator).** Before dispatching Task 12, report to the operator (Shawn) and wait for an explicit go: it spends Voxtral credit (≈10 short sentences on the Mistral API), creates a new venv `~/tts-bakeoff/venvs/kokoro`, and downloads models (Kokoro and its `misaki` dependencies). Without the go, do not start; with a go that excludes Voxtral, run Step 2 without `--voxtral`.
**Checkpoint 2 — after Step 3.** The flagged units and the recommended constants go to the operator, who listens, classifies and reviews the constants before anything is adopted (Step 3 says how).

Spec: section 3 "Constants are measured, not guessed" (the measurement task), "Runaway guard" (calibration table, initially only Qwen3-TTS-12Hz 1.7B Base at 12.5 frames/s), "Never silently skipped" (the bundled ~2 s Apache-2.0 preset-voice WAV, provenance recorded); section 6 "One opt-in `live` test against a running server"; "Unverified premises" (memory headroom: `footprint`).

**Files:**
- Create: `scripts/mlx_audio_calibrate.py`
- Create: `docs/superpowers/2026-10-12-mlx-audio-calibration.md`
- Create: `docs/superpowers/2026-10-12-mlx-audio-calibration-data.json` (written by the script)
- Create: `docs/superpowers/2026-10-12-mlx-audio-requirements.txt` (the evaluated venv's `pip freeze`; the Kokoro venv and the runbook install against it)
- Create: `packages/emcee/src/emcee/data/preflight_en.wav`
- Modify: `packages/emcee/src/emcee/tts/calibration.py` (the first `CALIBRATED_MODELS` entry)
- Modify: `packages/emcee/src/emcee/tts/verify.py` (the four thresholds)
- Modify: `packages/emcee/src/emcee/data/__init__.py` (provenance line)
- Test: `packages/emcee/tests/test_calibration_measured.py`, `packages/emcee/tests/test_mlx_live.py`

**Interfaces:**
- Consumes: the probe doc's `stt_model` (Task 1); `MlxAudioProvider` (the script calls its private `_post`/`_read_wav` so a take over the measurement cap is still saved), `text_units`, `max_tokens_for`, `cap_seconds`, `guard_problem` (Task 8); `SttClient`, `comparable_words`, `transcript_problem`, threshold constants, `PREFLIGHT_CLIP` (Task 11); `QualitySpeech`, `Verifier` (Tasks 10-11).
- Produces:
  - `emcee.tts.calibration.QWEN3_TTS_1_7B_BASE = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"` and its `CALIBRATED_MODELS` entry (`frame_rate_hz=12.5`, the other seven fields measured).
  - Measured `MISS_FLOOR` (must stay `>= 2`), `MISS_FRACTION`, `EXTRA_FLOOR`, `EXTRA_FRACTION` in `emcee.tts.verify`.
  - `emcee/data/preflight_en.wav`: 16-bit mono 24000 Hz, 1.0–4.0 s, saying exactly `PREFLIGHT_TEXT`.
  - The evidence doc (cited by both constant blocks), its data file (every unit with its saved WAV path under the scratch dir, `flagged`, `recommendation`), and `docs/superpowers/2026-10-12-mlx-audio-requirements.txt`.
  - `scripts/mlx_audio_calibrate.py` flags: `--url`, `--stt-model`, `--out`, `--clips-dir`, `--voxtral`, `--server-pid`, `--station-root`, `--reuse`, `--defects`, `--artefacts`.
  - A `-m live` test reading `EMCEE_MLX_URL`, `EMCEE_MLX_STT_MODEL`, and `EMCEE_MLX_REF`/`EMCEE_MLX_REF_TEXT` (default `~/tts-bakeoff/refs/phil_ex.wav`/`.txt`).

- [ ] **Step 1: Write the calibration script**

Create `scripts/mlx_audio_calibrate.py`:

```python
#!/usr/bin/env python3
"""Calibration run for emcee's mlx_audio runaway guard and transcript
verification (spec 2026-10-12-local-tts-presenter-pinning-design.md, section
3 "Constants are measured, not guessed"). Evidence for
docs/superpowers/2026-10-12-mlx-audio-calibration.md.

Renders ~50 unseeded sentences in five presenters' cloned voices (Phil's
evaluated excerpt among them) and a few whole segments (the unchunked path)
through the real server, optionally ~10 Voxtral sentences, saves every unit's
WAV under --clips-dir, transcribes every unit with the server's STT model,
writes the units to --out at once, then measures the bake-off's two known
runaways, flags units for the operator's listen, and prints the flagged units
and the constants the derivation rules in `recommend` produce.

    ./.venv/bin/python scripts/mlx_audio_calibrate.py --url http://127.0.0.1:8765 \\
        --stt-model <probe doc stt_model> --clips-dir <scratch dir> \\
        --out docs/superpowers/2026-10-12-mlx-audio-calibration-data.json \\
        [--voxtral] [--server-pid PID] [--station-root /Volumes/media/lma-radio/delivered]

Re-derive from the saved units after the operator's classification, without
rendering anything:

    ./.venv/bin/python scripts/mlx_audio_calibrate.py --url ... --stt-model ... \\
        --out <the same data file> --reuse [--defects 3,17] [--artefacts 9]

Read-only on ~/.emcee, the station root and ~/tts-bakeoff, except that it
writes drafted reference transcripts to ~/tts-bakeoff/refs/<clip>.draft.txt;
every unit's WAV goes under --clips-dir.
"""
import argparse
import io
import json
import math
import os
import statistics
import subprocess
import tempfile
import time
import tomllib
import wave
from collections import Counter
from pathlib import Path

import emcee.tts.verify as verify_mod
from emcee.audio import _split_sentences
from emcee.speech_text import load_lexicon, normalize_for_speech
from emcee.tts.calibration import (ModelCalibration, cap_seconds, guard_problem, max_tokens_for,
                                   text_units)
from emcee.tts.mlx_audio import MlxAudioProvider
from emcee.tts.provider import SpeechError
from emcee.tts.verify import SttClient, comparable_words, transcript_problem
from emcee.tts.voxtral import VoxtralProvider

QWEN = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
HOME = Path.home()
BAKEOFF = HOME / "tts-bakeoff"
SAMPLES = HOME / ".emcee" / "samples"
# Deliberately generous: the measurement must see raw durations, so only a
# gross runaway (> ~0.45 s per character) trips it.
MEASURE_CAL = ModelCalibration(frame_rate_hz=12.5, cap_floor_s=20.0, cap_s_per_char=0.5,
                               max_floor_s=10.0, max_s_per_char=0.45, min_s_per_char=0.0,
                               min_slack_s=0.0, cap_margin_s=1.0)
OTHER_VOICES = ["monroe1", "kurt1", "troymcclure2", "billgraham2"]
N_SENTENCES = 50
N_VOXTRAL = 10
SEGMENT_MAX_CHARS = 1200
BED_PREROLL_S = 1.5   # mix_bed's lead-in before the voice (tts/bed.py)
GAP_S = 0.18          # audio._SILENCE_MS between chunked sentences
FLAG_RECALL = 0.8     # flagged for the operator's listen below this transcript recall
FLAG_SPC = (0.5, 1.5)  # ... or outside these multiples of the voice's median s/char
DEFECT_RECALL = 0.5   # mechanical default: a defect below this recall,
DEFECT_SPC = 2.0      # or above this multiple of the voice's median s/char


def wav_seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as w:
        frames = w.readframes(w.getnframes())
        return len(frames) / (w.getsampwidth() * w.getnchannels() * w.getframerate())


def has_loop(words: list[str]) -> bool:
    """A repetition loop: some word trigram occurs three or more times."""
    return any(c >= 3 for c in Counter(zip(words, words[1:], words[2:])).values())


def script_texts(station_root: str | None) -> list[str]:
    texts: list[str] = []
    root = Path(station_root) if station_root else None
    if root is not None and root.is_dir():
        for manifest in sorted(root.glob("*/manifest.json")):
            try:
                notes = json.loads(manifest.read_text()).get("dj_notes") or {}
            except (OSError, ValueError):
                continue
            texts += list((notes.get("set_intros") or {}).values())
            if notes.get("outro"):
                texts.append(notes["outro"])
    if not texts:
        texts = [p.read_text() for p in sorted((BAKEOFF / "inputs").glob("*.txt"))]
    return texts


def pick_units(texts: list[str]) -> tuple[list[str], list[str]]:
    lexicon = load_lexicon(HOME / ".emcee")
    segments = [normalize_for_speech(t, lexicon) for t in texts]
    sentences = sorted({s for seg in segments for s in _split_sentences(seg)}, key=len)
    idx = [round(i * (len(sentences) - 1) / (N_SENTENCES - 1)) for i in range(N_SENTENCES)]
    picked = list(dict.fromkeys(sentences[i] for i in idx))
    segs = sorted({s for s in segments if len(s) <= SEGMENT_MAX_CHARS}, key=len)
    seg_pick = list(dict.fromkeys([segs[0], segs[len(segs) // 2], segs[-1]])) if segs else []
    return picked, seg_pick


def voices(stt: SttClient) -> list[dict]:
    out = [{"name": "phil_ex", "clip": BAKEOFF / "refs" / "phil_ex.wav",
            "text": (BAKEOFF / "refs" / "phil_ex.txt").read_text().strip(), "transcript": "evaluated"}]
    for stem in OTHER_VOICES:
        clip = SAMPLES / f"{stem}.wav"
        if not clip.exists():
            continue
        draft = BAKEOFF / "refs" / f"{stem}.draft.txt"
        if not draft.exists():
            draft.write_text(stt.transcribe(clip.read_bytes()))
        out.append({"name": stem, "clip": clip, "text": draft.read_text().strip(),
                    "transcript": "stt-draft"})
    return out


def score(rec: dict, text: str, wav: bytes, stt: SttClient) -> dict:
    heard = stt.transcribe(wav)
    want, got = comparable_words(text), comparable_words(heard)
    found = sum((Counter(want) & Counter(got)).values())
    rec.update(status="ok", transcript=heard, words=len(want), missing=len(want) - found,
               extra=len(got) - len(want), recall=round(found / len(want), 3) if want else 1.0,
               loop=has_loop(got), interim_problem=transcript_problem(text, heard))
    return rec


def synthesize_raw(provider, text: str) -> tuple[bytes, str | None]:
    """The take and, for mlx, the measurement guard's verdict -- without
    raising on it, so a capped take is still saved for the operator to hear."""
    if isinstance(provider, MlxAudioProvider):
        mt = max_tokens_for(MEASURE_CAL, text)
        wav = provider._post(text, mt)
        return wav, guard_problem(MEASURE_CAL, text, provider._read_wav(wav), mt)
    return provider.synthesize(text, fmt="wav"), None


def measure(kind: str, voice: str, provider, text: str, stt: SttClient, clip: Path) -> dict:
    """Render one unit, save its WAV as `clip`, transcribe and score it."""
    rec = {"kind": kind, "voice": voice, "text": text, "chars": text_units(text), "clip": None}
    t = time.time()
    try:
        wav, runaway = synthesize_raw(provider, text)
    except SpeechError as e:
        rec.update(status="error", error=str(e), wall_s=round(time.time() - t, 1))
        return rec
    clip.write_bytes(wav)
    rec.update(clip=str(clip), wall_s=round(time.time() - t, 1),
               seconds=round(wav_seconds(wav), 3))
    print(f"{kind:8} {voice:12} {rec['chars']:5}ch {rec['seconds']:7.2f}s", flush=True)
    try:
        score(rec, text, wav, stt)
    except SpeechError as e:
        rec.update(status="error", error=f"transcription: {e}")
        return rec
    if runaway:
        rec.update(status="runaway-at-measurement-cap", reason=runaway)
    return rec


def classify(units: list[dict], defects: set[int], artefacts: set[int]) -> list[dict]:
    """Number the units, flag the ones the operator must listen to, and
    classify each as a defect or not. Flagged: status not ok, a loop, recall
    below FLAG_RECALL, or seconds per character outside FLAG_SPC times its
    voice's median. Mechanical default the operator may accept: a defect when
    recall < DEFECT_RECALL or seconds per character > DEFECT_SPC times the
    voice's median. `defects`/`artefacts` (unit indices: the operator's
    answer) override the default. Returns the flagged units."""
    spc = {i: u["seconds"] / u["chars"] for i, u in enumerate(units)
           if u.get("seconds") and u.get("chars")}
    median = {v: statistics.median(x for i, x in spc.items() if units[i]["voice"] == v)
              for v in {units[i]["voice"] for i in spc}}
    flagged = []
    for i, u in enumerate(units):
        u["index"] = i
        ratio = spc[i] / median[u["voice"]] if i in spc else None
        recall = u.get("recall")
        flags = []
        if u.get("status") not in ("ok", "not-measured"):
            flags.append(u.get("status"))
        if u.get("loop"):
            flags.append("loop")
        if recall is not None and recall < FLAG_RECALL:
            flags.append(f"recall {recall:.2f}")
        if ratio is not None and not FLAG_SPC[0] <= ratio <= FLAG_SPC[1]:
            flags.append(f"{ratio:.2f}x its voice's median s/char")
        default = ((recall is not None and recall < DEFECT_RECALL)
                   or (ratio is not None and ratio > DEFECT_SPC))
        u["defect"] = i in defects or (default and i not in artefacts)
        u["flags"] = flags
        if flags:
            flagged.append({k: u.get(k) for k in ("index", "kind", "voice", "text", "clip",
                                                  "seconds", "recall", "flags", "defect")})
    return flagged


def known_runaways(stt: SttClient) -> list[dict]:
    out = []
    for slug, seg, needle in [("qwen3tts-0.6b-bf16", "set1-intro", None),
                              ("chatterbox-fp16", "set2-intro", "Here is Morning Dew.")]:
        metrics = json.loads((BAKEOFF / "out" / f"{slug}-{seg}.metrics.json").read_text())
        per_call = metrics["per_call"]  # [wall_s, audio_s] per sentence, in order
        sentences = _split_sentences((BAKEOFF / "inputs" / f"{seg}.txt").read_text())
        rec = {"slug": slug, "segment": seg, "sentence_count": len(sentences),
               "call_count": len(per_call)}
        if len(sentences) != len(per_call):
            rec["status"] = "unmatched"
            out.append(rec)
            continue
        if needle is None:
            i = max(range(len(per_call)), key=lambda k: per_call[k][1])
        else:
            i = next(k for k, s in enumerate(sentences) if needle in s)
        rec.update(status="ok", index=i, text=sentences[i], chars=text_units(sentences[i]),
                   seconds=per_call[i][1])
        start = BED_PREROLL_S + sum(c[1] for c in per_call[:i]) + GAP_S * i
        mp3 = BAKEOFF / "out" / f"{slug}-{seg}.mp3"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cut = Path(tmp) / "cut.wav"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}",
                                "-t", f"{per_call[i][1]:.2f}", "-i", str(mp3), "-ac", "1",
                                "-ar", "24000", "-c:a", "pcm_s16le", str(cut)], check=True)
                heard = stt.transcribe(cut.read_bytes())
            rec.update(transcript=heard, interim_problem=transcript_problem(sentences[i], heard))
        except (subprocess.CalledProcessError, SpeechError, OSError) as e:
            rec["transcript_error"] = str(e)
        out.append(rec)
    return out


def ceil_to(x: float, step: float) -> float:
    return round(math.ceil(x / step - 1e-9) * step, 4)


def floor_to(x: float, step: float) -> float:
    return round(math.floor(x / step + 1e-9) * step, 4)


def recommend(units: list[dict], runaways: list[dict]) -> dict:
    """Derivation rules (the evidence doc restates them):
    clean = status ok, not a loop, not classified a defect (`classify`).
    guard -- over clean mlx units:
      max_floor_s = 2.0; max_s_per_char = smallest 0.005 step with every clean
        unit <= 0.8 x (max_floor_s + max_s_per_char x chars)   (25% headroom);
      min_slack_s = 0.5; min_s_per_char = largest 0.005 step with every clean
        unit >= 1.25 x (min_s_per_char x chars - min_slack_s);
      cap_s_per_char = max_s_per_char; cap_margin_s = 1.0;
      cap_floor_s = max_floor_s + 3.0  (satisfies ModelCalibration's invariant).
    verification -- over clean units of every kind (Voxtral included), split
      at 8 comparable words:
      MISS_FLOOR = max(2, 1 + worst short-unit missing);
      MISS_FRACTION = max(0.15, 1.5 x worst long-unit missing/words, 0.05 steps);
      EXTRA_FLOOR = max(4, 1 + worst short-unit extra);
      EXTRA_FRACTION = max(0.25, 1.5 x worst long-unit extra/words, 0.05 steps).
    Every defect must fail the derived guard or thresholds (`defects_passing`)."""
    mlx = [u for u in units if u["status"] == "ok" and u["kind"] in ("sentence", "segment")
           and not u["loop"] and not u["defect"]]
    max_floor_s, min_slack_s = 2.0, 0.5
    max_spc = ceil_to(max((u["seconds"] / 0.8 - max_floor_s) / u["chars"] for u in mlx), 0.005)
    min_spc = max(0.0, floor_to(min((u["seconds"] / 1.25 + min_slack_s) / u["chars"]
                                    for u in mlx), 0.005))
    cal = ModelCalibration(frame_rate_hz=12.5, cap_floor_s=max_floor_s + 3.0,
                           cap_s_per_char=max_spc, max_floor_s=max_floor_s,
                           max_s_per_char=max_spc, min_s_per_char=min_spc,
                           min_slack_s=min_slack_s, cap_margin_s=1.0)
    guard_checks = {"clean_failures": [u["text"] for u in mlx if guard_problem(
        cal, u["text"], u["seconds"], max_tokens_for(cal, u["text"]))]}
    for r in runaways:
        if r.get("status") != "ok":
            continue
        mt = max_tokens_for(cal, r["text"])
        if r["slug"].startswith("qwen"):
            # The 0.6B runaway ran into its max_tokens, so under this cap it
            # would end AT the cap: the cap-margin check fails it by
            # construction. Its measured duration (320 s) is checked against
            # the non-cap long limit as well.
            guard_checks[f"{r['slug']} cap-margin"] = guard_problem(
                cal, r["text"], cap_seconds(cal, mt), mt)
            longest = cal.max_floor_s + cal.max_s_per_char * r["chars"]
            guard_checks[f"{r['slug']} measured-vs-long-limit"] = (
                f"{r['seconds']}s > long limit {longest:.1f}s" if r["seconds"] > longest else None)
        else:  # Chatterbox's babble is a plain over-long clip
            guard_checks[r["slug"]] = guard_problem(cal, r["text"], r["seconds"], mt)
    scored = [u for u in units if u["status"] == "ok" and not u["loop"] and not u["defect"]]
    short = [u for u in scored if u["words"] < 8]
    long_ = [u for u in scored if u["words"] >= 8]
    thresholds = {
        "MISS_FLOOR": max(2, 1 + max((u["missing"] for u in short), default=0)),
        "MISS_FRACTION": max(0.15, ceil_to(1.5 * max((u["missing"] / u["words"] for u in long_),
                                                     default=0.0), 0.05)),
        "EXTRA_FLOOR": max(4, 1 + max((max(0, u["extra"]) for u in short), default=0)),
        "EXTRA_FRACTION": max(0.25, ceil_to(1.5 * max((max(0, u["extra"]) / u["words"]
                                                       for u in long_), default=0.0), 0.05)),
    }
    for name, value in thresholds.items():
        setattr(verify_mod, name, value)
    verify_checks = {
        "clean_failures": [u["text"] for u in scored if transcript_problem(u["text"], u["transcript"])],
        **{r["slug"]: transcript_problem(r["text"], r["transcript"])
           for r in runaways if r.get("transcript") is not None},
    }

    def caught(u: dict) -> bool:
        guarded = u["kind"] in ("sentence", "segment") and guard_problem(
            cal, u["text"], u["seconds"], max_tokens_for(cal, u["text"]))
        return bool(guarded or (u.get("transcript") is not None
                                and transcript_problem(u["text"], u["transcript"])))

    # Every unit classified as a defect must fail the derived constants.
    defects_passing = [u["index"] for u in units
                       if u.get("defect") and u.get("seconds") is not None and not caught(u)]
    return {"calibration": {f: getattr(cal, f) for f in cal.__dataclass_fields__},
            "guard_checks": guard_checks, "thresholds": thresholds,
            "verify_checks": verify_checks, "defects_passing": defects_passing}


def footprint(pid: int | None) -> str | None:
    if not pid:
        return None
    out = subprocess.run(["footprint", "-p", str(pid)], capture_output=True, text=True).stdout
    return "\n".join(line for line in out.splitlines() if "footprint" in line.lower())[:2000]


def voxtral_key() -> str | None:
    if os.environ.get("MISTRAL_API_KEY"):
        return os.environ["MISTRAL_API_KEY"]
    cfg = HOME / ".emcee" / "config.toml"
    if cfg.exists():
        return tomllib.loads(cfg.read_text()).get("tts", {}).get("api_key")
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--stt-model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--voxtral", action="store_true")
    ap.add_argument("--server-pid", type=int, default=None)
    ap.add_argument("--station-root", default="/Volumes/media/lma-radio/delivered")
    ap.add_argument("--clips-dir", default=None, help="scratch dir for every unit's WAV")
    ap.add_argument("--reuse", action="store_true",
                    help="re-derive from --out's saved units; render nothing")
    ap.add_argument("--defects", default="", help="unit indices the operator heard as defects")
    ap.add_argument("--artefacts", default="", help="unit indices the operator heard as artefacts")
    a = ap.parse_args()
    out = Path(a.out)
    stt = SttClient(url=a.url, model=a.stt_model)
    if a.reuse:
        data = json.loads(out.read_text())
    else:
        if not a.clips_dir:
            ap.error("--clips-dir is required unless --reuse")
        clips = Path(a.clips_dir).expanduser()
        clips.mkdir(parents=True, exist_ok=True)
        sentences, segments = pick_units(script_texts(a.station_root))
        vs = voices(stt)
        providers = {v["name"]: MlxAudioProvider(url=a.url, model=QWEN, clone_ref=str(v["clip"]),
                                                 clone_text=v["text"], calibration=MEASURE_CAL)
                     for v in vs}
        units: list[dict] = []

        def run(kind: str, name: str, provider, text: str) -> None:
            units.append(measure(kind, name, provider, text, stt,
                                 clips / f"{len(units):03d}-{kind}-{name}.wav"))

        others = [v["name"] for v in vs[1:]] or ["phil_ex"]
        for i, text in enumerate(sentences):
            name = "phil_ex" if i % 2 == 0 else others[(i // 2) % len(others)]
            run("sentence", name, providers[name], text)
        for text in segments:
            run("segment", "phil_ex", providers["phil_ex"], text)
        if a.voxtral:
            key = voxtral_key()
            if key:
                vox = VoxtralProvider(clone_ref=str(SAMPLES / "troymcclure2.wav"), api_key=key)
                for text in sentences[::max(1, len(sentences) // N_VOXTRAL)][:N_VOXTRAL]:
                    run("voxtral", "voxtral-house", vox, text)
            else:
                units.append({"kind": "voxtral", "status": "not-measured",
                              "error": "no Mistral key"})
        data = {"date": time.strftime("%Y-%m-%d"), "model": QWEN, "stt_model": a.stt_model,
                "voices": [{k: str(v[k]) for k in ("name", "clip", "text", "transcript")}
                           for v in vs],
                "units": units}
        out.write_text(json.dumps(data, indent=1))  # before anything below can fail
    if "runaways" not in data:
        data["runaways"] = known_runaways(stt)
        data["footprint"] = footprint(a.server_pid)
        out.write_text(json.dumps(data, indent=1))

    def indices(arg: str) -> set[int]:
        return {int(x) for x in arg.split(",") if x.strip()}

    data["flagged"] = classify(data["units"], indices(a.defects), indices(a.artefacts))
    data["recommendation"] = recommend(data["units"], data["runaways"])
    out.write_text(json.dumps(data, indent=1))
    print(json.dumps({"flagged": data["flagged"], "recommendation": data["recommendation"]},
                     indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Start the server offline and run the calibration**

The probe (Task 1) already downloaded the STT model; Qwen 1.7B is cached. Follow Global Constraints' server procedure (port 8765 or another free one; scratch dir `S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/calibrate`).

Check the port is free first (`! lsof -tiTCP:8765 -sTCP:LISTEN` succeeds; otherwise pick another). Start (one Bash call, `run_in_background: true`):

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/calibrate
mkdir -p $S/logs $S/clips
(cd ~/tts-bakeoff && export HF_HUB_OFFLINE=1 && exec venvs/mlx/bin/python -m mlx_audio.server \
    --host 127.0.0.1 --port 8765 --log-dir $S/logs) > $S/server.log 2>&1 &
```

Wait and record the PID (one foreground Bash call, tool `timeout` 300000 ms; the bounded until-loop, not a Monitor; re-run while it exits 124):

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/calibrate
timeout 270 sh -c 'until curl -sf http://127.0.0.1:8765/ >/dev/null; do sleep 2; done' \
    && lsof -tiTCP:8765 -sTCP:LISTEN > $S/server.pid && cat $S/server.pid
```

Then run the calibration (one Bash call, `run_in_background: true`; poll `$S/calibrate.log` in ≤ 270 s chunks; expect ~30-45 minutes). `--server-pid` is the `lsof` PID, so the `footprint` reading is the server's:

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/calibrate
cd /Users/shawn/projects/llama/.claude/worktrees/local-tts
./.venv/bin/python scripts/mlx_audio_calibrate.py --url http://127.0.0.1:8765 \
    --stt-model "<stt_model from the probe doc>" --voxtral --server-pid $(cat $S/server.pid) \
    --clips-dir $S/clips \
    --out docs/superpowers/2026-10-12-mlx-audio-calibration-data.json 2>&1 | tee $S/calibrate.log
```

`--voxtral` spends ≈10 short Mistral requests (the spec's "~10 Voxtral sentences"); drop the flag if Checkpoint 1 excluded it or no key is available, and record "voxtral not measured — do not list voxtral in [tts.verify] until it is" in the evidence doc. If `/Volumes/media/lma-radio/delivered` is not mounted, the script falls back to `~/tts-bakeoff/inputs/*.txt`; record which source was used. The data file holds every unit (with its WAV path under `$S/clips`) as soon as rendering ends, before the runaway measurement and the recommendation; if the run dies after that, re-run with `--reuse` instead of re-rendering. Leave the server up for Step 4's transcriptions, or stop it (Global Constraints' stop, port check included) and restart it the same way when needed.

- [ ] **Step 3: Report the flagged units and the recommendation; wait for the operator (Checkpoint 2)**

Read the printed `flagged` list and `recommendation`, and check mechanically:
- `guard_checks.clean_failures` must be `[]`; `guard_checks["chatterbox-fp16"]`, `guard_checks["qwen3tts-0.6b-bf16 cap-margin"]` and `guard_checks["qwen3tts-0.6b-bf16 measured-vs-long-limit"]` must all be non-null (the known runaways fail). The cap-margin row is satisfied by construction (the clip is placed AT the cap); the measured-vs-long-limit row is the real test of the 0.6B runaway's 320 s against the non-cap limit. If a runaway passes, propose tightening `max_s_per_char` (Chatterbox: 20 characters in ~10 s) rather than the floors, and re-check the clean set.
- `verify_checks.clean_failures` must be `[]`; each runaway with a transcript must be non-null; `defects_passing` must be `[]`.
- STOP and report to the orchestrator with the offending units, instead of proposing a threshold that no longer detects gross mismatch, if keeping every clean unit passing would need `MISS_FRACTION > 0.4`, `EXTRA_FRACTION > 1.0`, `MISS_FLOOR > 3` or `EXTRA_FLOOR > 6`. `MISS_FLOOR` stays `>= 2` (the spec tolerates "a wrong word or two per sentence").

Then end the turn with a report to the orchestrator (status NEEDS OPERATOR), which relays it to the operator (Shawn): every flagged unit (`error`, `runaway-at-measurement-cap`, `loop: true`, recall below 0.8, or seconds per character outside 0.5×-1.5× its voice's median) with its index, kind, voice, text, flags, saved WAV path and its mechanical-default classification; the recommendation and every check above; and any deviation you propose, with its reason. The mechanical default the operator can accept as-is: a unit is a **defect** if its transcript recall is < 0.5 or its duration exceeds 2× the median seconds-per-character for its voice; otherwise an artefact. Do not classify by ear and do not adopt any constant before the answer. If the operator reclassifies units, re-derive without rendering (`--reuse --defects <i,j> --artefacts <k>`, same `--url`/`--stt-model`/`--out`) and report the new `flagged`/`recommendation` the same way. Adopt (Steps 6-7) only the constants the operator approved, and record in the evidence doc each flagged unit's classification and who made it (the operator, or "mechanical default accepted").

- [ ] **Step 4: Render the bundled preflight clip with Kokoro**

Kokoro (Apache-2.0) needs `misaki`, which the evaluated venv lacks; never install into `venvs/mlx`. Freeze the evaluated venv (it has no `pip`; `uv` reads it) into the committed requirements file, make a separate Python 3.12 venv with `uv`, and install mlx-audio 0.5.8 with its server/tts/stt extras, constrained to that freeze:

```bash
cd /Users/shawn/projects/llama/.claude/worktrees/local-tts
uv pip freeze --python ~/tts-bakeoff/venvs/mlx/bin/python \
    > docs/superpowers/2026-10-12-mlx-audio-requirements.txt
grep -x 'mlx-audio==0.5.8' docs/superpowers/2026-10-12-mlx-audio-requirements.txt
uv venv --python 3.12 ~/tts-bakeoff/venvs/kokoro
uv pip install --python ~/tts-bakeoff/venvs/kokoro/bin/python \
    "mlx-audio[server,tts,stt]==0.5.8" "misaki[en]" \
    -c docs/superpowers/2026-10-12-mlx-audio-requirements.txt
```

If `misaki[en]` cannot be resolved under the constraints, report the conflict to the orchestrator rather than loosening the pins.

Serve Kokoro on another free port (`! lsof -tiTCP:8766 -sTCP:LISTEN` must succeed) per Global Constraints' server procedure (online: Kokoro downloads on first use). Start (one Bash call, `run_in_background: true`):

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/calibrate
mkdir -p $S/kokoro-logs
(cd ~/tts-bakeoff && exec venvs/kokoro/bin/python -m mlx_audio.server --host 127.0.0.1 --port 8766 \
    --log-dir $S/kokoro-logs) > $S/kokoro-server.log 2>&1 &
```

Wait and record the PID (one foreground Bash call, tool `timeout` 300000 ms; re-run while it exits 124), then render three takes (one foreground Bash call, tool `timeout` 600000 ms — the first request downloads the model):

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/calibrate
timeout 270 sh -c 'until curl -sf http://127.0.0.1:8766/ >/dev/null; do sleep 2; done' \
    && lsof -tiTCP:8766 -sTCP:LISTEN > $S/kokoro.pid && cat $S/kokoro.pid
```

```bash
S=/private/tmp/claude-501/-Users-shawn-projects-llama/a9d60e99-1777-47b4-9067-97da18fe3e6f/scratchpad/calibrate
for take in 1 2 3; do
  curl -s http://127.0.0.1:8766/v1/audio/speech -H 'Content-Type: application/json' \
    -d '{"model": "mlx-community/Kokoro-82M-bf16", "input": "Good evening, and welcome to the show.", "voice": "af_heart", "lang_code": "a", "response_format": "wav"}' \
    -o $S/preflight-take$take.wav
done
```

If `mlx-community/Kokoro-82M-bf16` does not load, try `prince-canuma/Kokoro-82M`; if Kokoro cannot run at all, use another Apache-2.0 preset-voice model mlx-audio serves and record why. For each take check with `wave` that it is 16-bit, mono, 24000 Hz and 1.0–4.0 s, and transcribe it with the STT server (restart the Qwen server, or POST to it if still up) using `SttClient(...).transcribe`; keep the first take whose transcript passes `transcript_problem(PREFLIGHT_TEXT, transcript) is None` under the ADOPTED thresholds. Copy it to `packages/emcee/src/emcee/data/preflight_en.wav`. Record provenance in the evidence doc: model repo id, HF revision (`cat ~/.cache/huggingface/hub/models--<org>--<name>/refs/main`), license as stated on the model card, voice, `lang_code`, mlx-audio version, take number, duration, `shasum -a 256` of the file, and its transcript. Stop the Kokoro server (`kill $(cat $S/kokoro.pid)`, then the port-free check on 8766) and, when done with it, the Qwen server (the same on 8765). The PyInstaller spec already bundles every `emcee.data` file (`packaging/emcee.spec`: `collect_data_files("emcee.data")`), so no packaging change is needed.

- [ ] **Step 5: Write the evidence doc**

Create `docs/superpowers/2026-10-12-mlx-audio-calibration.md` with: date, host (M4 mini 16 GB), mlx-audio version, TTS model, STT model, text source, voices (with which transcripts are STT drafts); the derivation rules (copy `recommend`'s docstring); a per-voice table (units, median and max seconds/char, min seconds/char); the clean-unit extremes; the known-runaway rows and how each fails — the Qwen 0.6B row as two checks, labelled "cap-margin check (satisfied by construction: the clip is placed at the cap)" and "measured 320 s vs the non-cap long limit"; every flagged unit with its WAV path, its flags and its classification (by the operator, or "mechanical default accepted"); the adopted guard constants and thresholds with every deviation from the recommendation, its reason and the operator's approval; the synthetic cap-margin check; the bundled clip's provenance; the Kokoro venv's install (`docs/superpowers/2026-10-12-mlx-audio-requirements.txt` as constraints); the `footprint` reading (and that it answers — or does not — the spec's "memory headroom" premise); and a "What this does not show" section (unseeded production rate is still sampled, not proven; presenters beyond these five are unmeasured; the go-live listen remains required).

- [ ] **Step 6: Write the failing tests for the measured constants**

Create `packages/emcee/tests/test_calibration_measured.py`. Fill the three literal tables from the data file, by these rules (copy the numbers and strings verbatim):
- `CLEAN_EDGES`: `(chars, seconds)` for the clean mlx units (status `ok`, kind `sentence` or `segment`, `loop` false, not classified as a defect in Step 3) with the 3 highest and the 3 lowest `seconds / chars`, plus the shortest and the longest text (de-duplicated).
- `CLEAN_TRANSCRIPTS`: `(text, transcript)` for the 3 clean units of any kind with the largest `missing / max(words, 1)` and the 3 with the largest `extra / max(words, 1)`.
- `RUNAWAY_TRANSCRIPTS`: `(text, transcript)` for each `runaways` row that has a `transcript`; leave the list empty (and say so in the doc) if extraction failed.

```python
"""The measured constants (docs/superpowers/2026-10-12-mlx-audio-calibration.md):
the first calibrated mlx model and the verification thresholds, pinned on
the edges of the calibration data and on the bake-off's known runaways."""
import io
import math
import wave
from importlib import resources

import pytest

from emcee.tts import verify
from emcee.tts.calibration import (CALIBRATED_MODELS, QWEN3_TTS_1_7B_BASE, cap_seconds,
                                   guard_problem, max_tokens_for)
from emcee.tts.mlx_audio import PREFLIGHT_TEXT
from emcee.tts.verify import transcript_problem

CAL = CALIBRATED_MODELS[QWEN3_TTS_1_7B_BASE]

# From the calibration data file (selection rules in the plan, Task 12 Step 6).
CLEAN_EDGES: list[tuple[int, float]] = [
    # (chars, seconds), copied verbatim
]
CLEAN_TRANSCRIPTS: list[tuple[str, str]] = [
    # (text, transcript), copied verbatim
]
RUNAWAY_TRANSCRIPTS: list[tuple[str, str]] = [
    # (text, transcript), copied verbatim
]
# The bake-off's known runaways (~/tts-bakeoff/out/*.metrics.json):
CHATTERBOX_MORNING_DEW = ("Here is Morning Dew.", "<seconds from the data file's chatterbox row>")
QWEN_06B_RUNAWAY_TEXT = "<text from the data file's qwen3tts-0.6b-bf16 row>"
QWEN_06B_RUNAWAY_SECONDS = 320.0  # per_call[5][1] of qwen3tts-0.6b-bf16-set1-intro.metrics.json


def text_of(chars: int) -> str:
    return "x" * chars  # the guard measures only whitespace-collapsed length


def test_qwen_1_7b_is_the_calibrated_model():
    assert QWEN3_TTS_1_7B_BASE == "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
    assert CAL.frame_rate_hz == 12.5  # qwen3_tts/config.py


def test_the_edges_of_the_clean_data_pass_the_guard():
    assert CLEAN_EDGES
    for chars, seconds in CLEAN_EDGES:
        text = text_of(chars)
        assert guard_problem(CAL, text, seconds, max_tokens_for(CAL, text)) is None, (chars, seconds)


def test_chatterbox_morning_dew_babble_fails_the_guard():
    text, seconds = CHATTERBOX_MORNING_DEW
    assert guard_problem(CAL, text, float(seconds), max_tokens_for(CAL, text)) is not None


def test_a_capped_runaway_fails_the_guard():
    # The cap-margin check: satisfied by construction (the clip is placed AT the cap).
    mt = max_tokens_for(CAL, QWEN_06B_RUNAWAY_TEXT)
    assert "token cap" in guard_problem(CAL, QWEN_06B_RUNAWAY_TEXT, cap_seconds(CAL, mt), mt)


def test_the_measured_qwen_0_6b_runaway_exceeds_the_long_limit():
    # The runaway's measured duration against the non-cap limit: give it a
    # cap above the clip, so only the "implausibly long" check can catch it.
    mt = math.ceil((QWEN_06B_RUNAWAY_SECONDS + CAL.cap_margin_s + 1.0) * CAL.frame_rate_hz)
    assert "implausibly long" in guard_problem(CAL, QWEN_06B_RUNAWAY_TEXT,
                                               QWEN_06B_RUNAWAY_SECONDS, mt)


def test_a_synthetic_cap_length_clip_fails_for_every_length():
    for chars in (5, 20, 60, 150, 400, 1200):
        text = text_of(chars)
        mt = max_tokens_for(CAL, text)
        assert "token cap" in guard_problem(CAL, text, cap_seconds(CAL, mt), mt)
        assert "token cap" in guard_problem(CAL, text, cap_seconds(CAL, mt) - CAL.cap_margin_s, mt)


def test_measured_thresholds_tolerate_a_wrong_word_or_two():
    assert 2 <= verify.MISS_FLOOR <= 3
    assert verify.EXTRA_FLOOR <= 6
    # ... and still detect gross mismatch (Step 3's STOP ceilings).
    assert verify.MISS_FRACTION <= 0.4 and verify.EXTRA_FRACTION <= 1.0


@pytest.mark.parametrize("text, transcript", CLEAN_TRANSCRIPTS)
def test_the_worst_clean_transcripts_pass(text, transcript):
    assert transcript_problem(text, transcript) is None


@pytest.mark.parametrize("text, transcript", RUNAWAY_TRANSCRIPTS)
def test_the_known_runaway_transcripts_fail(text, transcript):
    assert transcript_problem(text, transcript) is not None


def test_the_bundled_preflight_clip():
    data = resources.files("emcee.data").joinpath(verify.PREFLIGHT_CLIP).read_bytes()
    with wave.open(io.BytesIO(data), "rb") as w:
        assert (w.getsampwidth(), w.getnchannels(), w.getframerate()) == (2, 1, 24000)
        assert 1.0 <= w.getnframes() / w.getframerate() <= 4.0
    assert PREFLIGHT_TEXT == "Good evening, and welcome to the show."
```

Replace the two `"<...>"` placeholders in this file with the data file's values before running it (they are measurement outputs, not code), and confirm `QWEN_06B_RUNAWAY_SECONDS` equals the data file's `qwen3tts-0.6b-bf16` row `seconds`. Run: `./.venv/bin/pytest packages/emcee/tests/test_calibration_measured.py -q` → FAIL (`ImportError: cannot import name 'QWEN3_TTS_1_7B_BASE'`).

- [ ] **Step 7: Adopt the constants**

In `packages/emcee/src/emcee/tts/calibration.py` replace the empty table and its comment with (values: the adopted ones from Step 3, i.e. `recommendation.calibration` unless the doc records a deviation):

```python
QWEN3_TTS_1_7B_BASE = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"

# Model id -> calibration. Every entry is MEASURED; adding a model means a
# calibration run (scripts/mlx_audio_calibrate.py). Evidence and derivation:
# docs/superpowers/2026-10-12-mlx-audio-calibration.md.
CALIBRATED_MODELS: dict[str, ModelCalibration] = {
    QWEN3_TTS_1_7B_BASE: ModelCalibration(
        frame_rate_hz=12.5,          # qwen3_tts/config.py
        cap_floor_s=<adopted>,
        cap_s_per_char=<adopted>,
        max_floor_s=<adopted>,
        max_s_per_char=<adopted>,
        min_s_per_char=<adopted>,
        min_slack_s=<adopted>,
        cap_margin_s=<adopted>,
    ),
}
```

In `packages/emcee/src/emcee/tts/verify.py` replace the four interim values with the adopted thresholds and the comment's "INTERIM values, replaced by the measured ones from the calibration run (implementation plan Task 12)" with "Measured: docs/superpowers/2026-10-12-mlx-audio-calibration.md". In `packages/emcee/src/emcee/data/__init__.py` extend the docstring with: `preflight_en.wav -- a ~2 s Kokoro (Apache-2.0) clip of "Good evening, and welcome to the show.", the verification preflight's check clip; provenance in docs/superpowers/2026-10-12-mlx-audio-calibration.md.`

(`<adopted>` stands for the measured numbers; there is no other way to know them. Every one must appear in the evidence doc's "adopted" table.)

- [ ] **Step 8: Add the opt-in live test**

Create `packages/emcee/tests/test_mlx_live.py`:

```python
"""Opt-in: against a running mlx-audio server.

    EMCEE_MLX_URL=http://127.0.0.1:8000 EMCEE_MLX_STT_MODEL=<id> \\
        [EMCEE_MLX_REF=<clip.wav> EMCEE_MLX_REF_TEXT=<transcript.txt>] \\
        ./.venv/bin/pytest -m live packages/emcee/tests/test_mlx_live.py -q

Clones a real speaker's reference clip (default: Phil's evaluated excerpt,
~/tts-bakeoff/refs/phil_ex.wav and its transcript phil_ex.txt); skipped when
the clip or its transcript is absent."""
import io
import os
import wave
from pathlib import Path

import pytest

from emcee.tts.calibration import CALIBRATED_MODELS, QWEN3_TTS_1_7B_BASE
from emcee.tts.mlx_audio import MlxAudioProvider
from emcee.tts.quality import QualitySpeech
from emcee.tts.verify import SttClient, Verifier

pytestmark = pytest.mark.live
URL = os.environ.get("EMCEE_MLX_URL")
STT_MODEL = os.environ.get("EMCEE_MLX_STT_MODEL")
REF = Path(os.environ.get("EMCEE_MLX_REF", "~/tts-bakeoff/refs/phil_ex.wav")).expanduser()
REF_TEXT = Path(os.environ.get("EMCEE_MLX_REF_TEXT", "~/tts-bakeoff/refs/phil_ex.txt")).expanduser()


@pytest.mark.skipif(not (URL and STT_MODEL),
                    reason="set EMCEE_MLX_URL and EMCEE_MLX_STT_MODEL to a running mlx-audio server")
@pytest.mark.skipif(not (REF.is_file() and REF_TEXT.is_file()),
                    reason="set EMCEE_MLX_REF/EMCEE_MLX_REF_TEXT to a reference clip and its transcript")
def test_live_preflight_synthesis_and_verification():
    inner = MlxAudioProvider(url=URL, model=QWEN3_TTS_1_7B_BASE, clone_ref=str(REF),
                             clone_text=REF_TEXT.read_text(),
                             calibration=CALIBRATED_MODELS[QWEN3_TTS_1_7B_BASE])
    speech = QualitySpeech(inner, backend="mlx_audio",
                           verifier=Verifier(SttClient(url=URL, model=STT_MODEL)))
    try:
        speech.preflight()
        wav = speech.synthesize("Tonight we open the vault to the Grateful Dead in Rotterdam.", "wav")
    finally:
        speech.close()
    with wave.open(io.BytesIO(wav), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2)
```

- [ ] **Step 9: Run everything (offline), then the live test**

Run: `./.venv/bin/pytest -q` → all pass. A Task 11 test that the adopted thresholds now fail means the measurement contradicts the spec's tolerance: do not edit that test — report it.
Then start the Qwen server once more (offline, Global Constraints' procedure exactly as in Step 2) and run: `EMCEE_MLX_URL=http://127.0.0.1:8765 EMCEE_MLX_STT_MODEL="<stt_model>" ./.venv/bin/pytest -m live packages/emcee/tests/test_mlx_live.py -q` → PASS (it clones `~/tts-bakeoff/refs/phil_ex.wav` with `phil_ex.txt` unless `EMCEE_MLX_REF`/`EMCEE_MLX_REF_TEXT` say otherwise; a skip is not a pass). Record the result in the evidence doc. Stop the server and check the port is free.

- [ ] **Step 10: Commit**

```bash
git add scripts/mlx_audio_calibrate.py docs/superpowers/2026-10-12-mlx-audio-calibration.md \
        docs/superpowers/2026-10-12-mlx-audio-calibration-data.json \
        docs/superpowers/2026-10-12-mlx-audio-requirements.txt \
        packages/emcee/src/emcee/data/preflight_en.wav packages/emcee/src/emcee/data/__init__.py \
        packages/emcee/src/emcee/tts/calibration.py packages/emcee/src/emcee/tts/verify.py \
        packages/emcee/tests/test_calibration_measured.py packages/emcee/tests/test_mlx_live.py
git commit -m "feat(emcee): measured runaway-guard calibration for Qwen3-TTS 1.7B and verification thresholds

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---
### Task 13: `emcee presenter edit`

**Implementer model:** Sonnet (one command in `cli.py` + one test file; every rule and the full code are below).
**Live:** no.

Spec: section 4 "`emcee presenter edit <id>`" (every bullet) and the "Moving Phil" paragraph; section 6 "`presenter edit`".

**Files:**
- Modify: `packages/emcee/src/emcee/cli.py` (three helpers placed just above `presenter_add`; the `edit` command placed just after it)
- Test: `packages/emcee/tests/test_presenter_edit.py`

**Interfaces:**
- Consumes: `Presenter`, `save_presenter`, `load_presenter` (Task 2); `SttClient` (Task 11); config `[tts.mlx_audio]`, `[tts.verify]` (Task 3).
- Produces (in `emcee.cli`, reused by Task 14):
  - `_usage(message: str) -> NoReturn` — prints `error: <message>` to stderr, exits 2.
  - `_abs_clip(path: str) -> str` — `str(Path(path).expanduser().resolve())`.
  - `_draft_transcript(config: EmceeConfig, clip: str) -> str` — transcribes with `SttClient(url=[tts.mlx_audio] url, model=stt_model, timeout_s=[tts.mlx_audio] timeout_s)`, unloads the STT model when `[tts.verify] backends` is empty, prints `transcript draft:` and the text, asks `use this transcript?` (default no); on decline prints `transcript not written; presenter unchanged` and exits 1.
  - `emcee presenter edit <id>` with options `--name --sex --character --character-file --voice --voice-clone --voice-clone-text --bed --tts --tts-model --clear-tts --clear-tts-model --clear-bed --clear-voice-clone-text --transcribe`.
  - Usage-error messages (exact): `<set> and <clear> are mutually exclusive`; `--voice and --voice-clone are mutually exclusive`; `give at most one of --character / --character-file`; `--transcribe and --voice-clone-text are mutually exclusive`; `--transcribe and --clear-voice-clone-text are mutually exclusive`; `--transcribe needs a voice clone (this presenter has a preset voice)`; `--transcribe needs [tts.mlx_audio] stt_model (a speech-to-text model on the mlx-audio server)`; `nothing to edit: give at least one field option`.

- [ ] **Step 1: Write the failing tests**

Create `packages/emcee/tests/test_presenter_edit.py`:

```python
"""`emcee presenter edit` (spec section 4)."""
from functools import partial
from pathlib import Path

import pytest
from typer.testing import CliRunner

from emcee.cli import app
from emcee.presenters import Presenter, PresenterError, load_presenter, save_presenter
from emcee.tts.provider import SpeechError
from emcee.tts.verify import SttClient

from tests.mlx_helpers import MlxServer, wav_bytes

runner = CliRunner()
DRAFT = "It's the chemistry, basically."
STT_CONFIG = '[tts.mlx_audio]\nstt_model = "stt/test-model"\n'
STT_VERIFY_CONFIG = STT_CONFIG + '\n[tts.verify]\nbackends = ["mlx_audio"]\n'


def _home(tmp_path, monkeypatch, config: str = "") -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(config)
    return home


def _clip(tmp_path, name: str = "phil_ex.wav") -> Path:
    p = tmp_path / name
    p.write_bytes(wav_bytes(1.0))
    return p


def _save(home, **overrides) -> Presenter:
    d = dict(id="phil", name="Phil", sex="male", voice="phil-preset", character="Professorial.")
    d.update(overrides)
    p = Presenter(**d)
    save_presenter(home, p)
    return p


def _clone(home, tmp_path, **overrides) -> Presenter:
    return _save(home, voice=None, voice_clone=str(_clip(tmp_path, "old.wav")),
                 voice_clone_text="Old words.", **overrides)


def _edit(*args, input=None):
    return runner.invoke(app, ["presenter", "edit", "phil", *args], input=input)


def _file(home) -> Path:
    return home / "presenters" / "phil.toml"


def _stt(monkeypatch, server: MlxServer) -> None:
    monkeypatch.setattr("emcee.cli.SttClient", partial(SttClient, transport=server.transport()))


# --- plain fields ---------------------------------------------------------------


def test_edit_changes_only_the_given_fields(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home, bed="/beds/b.wav")
    r = _edit("--name", "Professor Chapman", "--sex", "nonbinary")
    assert r.exit_code == 0, r.output
    p = load_presenter(home, "phil")
    assert (p.name, p.sex) == ("Professor Chapman", "nonbinary")
    assert (p.voice, p.bed, p.character) == ("phil-preset", "/beds/b.wav", "Professorial.")
    assert "saved:" in r.output


def test_edit_character_and_character_file(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home)
    assert _edit("--character", "Cosmic.").exit_code == 0
    assert load_presenter(home, "phil").character == "Cosmic."
    cf = tmp_path / "c.txt"
    cf.write_text("  From a file.\n")
    assert _edit("--character-file", str(cf)).exit_code == 0
    assert load_presenter(home, "phil").character == "From a file."


def test_edit_bed_set_and_clear(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home)
    assert _edit("--bed", "/beds/new.wav").exit_code == 0
    assert load_presenter(home, "phil").bed == "/beds/new.wav"
    assert _edit("--clear-bed").exit_code == 0
    assert load_presenter(home, "phil").bed is None


def test_edit_pins_and_unpins_tts(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home)
    assert _edit("--tts", "voxtral").exit_code == 0
    assert load_presenter(home, "phil").tts == "voxtral"
    assert _edit("--clear-tts").exit_code == 0
    assert load_presenter(home, "phil").tts is None


def test_edit_tts_model_set_and_clear(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path, tts="mlx_audio")
    assert _edit("--tts-model", "m/x").exit_code == 0
    assert load_presenter(home, "phil").tts_model == "m/x"
    assert _edit("--clear-tts-model").exit_code == 0
    assert load_presenter(home, "phil").tts_model is None


def test_edit_voice_clone_text_set_and_clear(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path)
    assert _edit("--voice-clone-text", "New words.").exit_code == 0
    assert load_presenter(home, "phil").voice_clone_text == "New words."
    assert _edit("--clear-voice-clone-text").exit_code == 0
    assert load_presenter(home, "phil").voice_clone_text is None


# --- usage errors -----------------------------------------------------------------


@pytest.mark.parametrize("args, message", [
    (["--tts", "voxtral", "--clear-tts"], "--tts and --clear-tts are mutually exclusive"),
    (["--tts-model", "m", "--clear-tts-model"], "--tts-model and --clear-tts-model are mutually exclusive"),
    (["--bed", "/b.wav", "--clear-bed"], "--bed and --clear-bed are mutually exclusive"),
    (["--voice-clone-text", "x", "--clear-voice-clone-text"],
     "--voice-clone-text and --clear-voice-clone-text are mutually exclusive"),
    (["--voice", "a", "--voice-clone", "/b.wav"], "--voice and --voice-clone are mutually exclusive"),
    (["--character", "a", "--character-file", "/c.txt"], "give at most one of --character / --character-file"),
    (["--transcribe", "--voice-clone-text", "x"], "--transcribe and --voice-clone-text are mutually exclusive"),
    ([], "nothing to edit: give at least one field option"),
])
def test_usage_errors_exit_2_and_touch_nothing(tmp_path, monkeypatch, args, message):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path)
    before = _file(home).read_bytes()
    r = _edit(*args)
    assert r.exit_code == 2
    assert message in r.output
    assert _file(home).read_bytes() == before


# --- voice / clip / transcript coupling --------------------------------------------


def test_voice_clears_the_clip_and_its_transcript(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path)
    assert _edit("--voice", "new-preset").exit_code == 0
    p = load_presenter(home, "phil")
    assert (p.voice, p.voice_clone, p.voice_clone_text) == ("new-preset", None, None)


def test_a_changed_clip_clears_the_transcript_unless_a_new_one_is_given(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path)
    new = _clip(tmp_path, "new.wav")
    assert _edit("--voice-clone", str(new)).exit_code == 0
    p = load_presenter(home, "phil")
    assert (p.voice_clone, p.voice_clone_text) == (str(new.resolve()), None)
    assert _edit("--voice-clone", str(new), "--voice-clone-text", "New words.").exit_code == 0
    assert load_presenter(home, "phil").voice_clone_text == "New words."


def test_a_changed_clip_on_an_mlx_pin_forces_a_fresh_transcript(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path, tts="mlx_audio")
    before = _file(home).read_bytes()
    r = _edit("--voice-clone", str(_clip(tmp_path, "new.wav")))
    assert r.exit_code == 1
    assert "invalid presenter" in r.output and "needs voice_clone_text" in r.output
    assert _file(home).read_bytes() == before


def test_moving_phil_with_the_runbook_command(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home)
    clip = _clip(tmp_path)
    r = _edit("--tts", "mlx_audio", "--voice-clone", str(clip), "--voice-clone-text", DRAFT + "\n")
    assert r.exit_code == 0, r.output
    p = load_presenter(home, "phil")
    assert (p.tts, p.voice, p.voice_clone) == ("mlx_audio", None, str(clip.resolve()))
    assert p.voice_clone_text.strip() == DRAFT


def test_edit_stores_voice_clone_as_an_absolute_path(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _save(home)
    (tmp_path / "samples").mkdir()
    clip = _clip(tmp_path / "samples")
    monkeypatch.chdir(tmp_path)
    assert _edit("--voice-clone", "samples/phil_ex.wav").exit_code == 0
    assert load_presenter(home, "phil").voice_clone == str(clip.resolve())
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _edit("--voice-clone", "~/samples/phil_ex.wav").exit_code == 0
    assert load_presenter(home, "phil").voice_clone == str(clip.resolve())


def test_an_invalid_merged_edit_leaves_the_file_untouched(tmp_path, monkeypatch):
    # The merge is model_validate'd whole (model_copy would skip validators).
    home = _home(tmp_path, monkeypatch)
    _save(home)
    before = _file(home).read_bytes()
    r = _edit("--tts", "mlx_audio")
    assert r.exit_code == 1 and "clone-only" in r.output
    r = _edit("--tts-model", "m/x")
    assert r.exit_code == 1 and 'tts_model is allowed only with tts = "mlx_audio"' in r.output
    assert _file(home).read_bytes() == before


def test_editing_a_missing_presenter_errors(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    r = _edit("--name", "X")
    assert r.exit_code == 1 and isinstance(r.exception, PresenterError)


# --- --transcribe ------------------------------------------------------------------


def test_transcribe_confirmed_writes_the_draft_and_unloads_when_verification_is_off(
        tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    server = MlxServer(transcript=lambda last: DRAFT)
    _stt(monkeypatch, server)
    r = _edit("--transcribe", input="y\n")
    assert r.exit_code == 0, r.output
    assert "transcript draft:" in r.output and DRAFT in r.output
    assert load_presenter(home, "phil").voice_clone_text == DRAFT
    assert b'name="response_format"\r\n\r\njson\r\n' in server.transcriptions[0].content
    assert server.deletes == [{"model_name": "stt/test-model"}]


def test_transcribe_declined_leaves_the_file_untouched(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    before = _file(home).read_bytes()
    _stt(monkeypatch, MlxServer(transcript=lambda last: DRAFT))
    r = _edit("--transcribe", input="n\n")
    assert r.exit_code == 1
    assert "transcript not written; presenter unchanged" in r.output
    assert _file(home).read_bytes() == before


def test_transcribe_keeps_the_stt_model_loaded_when_verification_is_on(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_VERIFY_CONFIG)
    _clone(home, tmp_path)
    server = MlxServer(transcript=lambda last: DRAFT)
    _stt(monkeypatch, server)
    assert _edit("--transcribe", input="y\n").exit_code == 0
    assert server.deletes == []


def test_transcribe_transcribes_the_new_clip(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    new = tmp_path / "new.wav"
    new.write_bytes(wav_bytes(1.7))
    server = MlxServer(transcript=lambda last: DRAFT)
    _stt(monkeypatch, server)
    assert _edit("--voice-clone", str(new), "--transcribe", input="y\n").exit_code == 0
    assert new.read_bytes() in server.transcriptions[0].content
    p = load_presenter(home, "phil")
    assert (p.voice_clone, p.voice_clone_text) == (str(new.resolve()), DRAFT)


def test_transcribe_needs_an_stt_model(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _clone(home, tmp_path)
    r = _edit("--transcribe")
    assert r.exit_code == 2
    assert "--transcribe needs [tts.mlx_audio] stt_model" in r.output


def test_transcribe_needs_a_clone(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _save(home)
    r = _edit("--transcribe")
    assert r.exit_code == 2 and "--transcribe needs a voice clone" in r.output


def test_transcribe_on_an_unreachable_server_leaves_the_file_untouched(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    before = _file(home).read_bytes()
    _stt(monkeypatch, MlxServer(stt_down=True))
    r = _edit("--transcribe", input="y\n")
    assert r.exit_code == 1 and isinstance(r.exception, SpeechError)
    assert _file(home).read_bytes() == before


def test_an_invalid_edit_fails_before_transcribing(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch, STT_CONFIG)
    _clone(home, tmp_path)
    server = MlxServer(transcript=lambda last: DRAFT)
    _stt(monkeypatch, server)
    r = _edit("--tts", "elevenlabs", "--transcribe", input="y\n")  # elevenlabs cannot clone
    assert r.exit_code == 1 and "invalid presenter" in r.output
    assert server.transcriptions == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_presenter_edit.py -q`
Expected: FAIL — `No such command 'edit'` (exit code 2 with usage text) on every test that expects 0 or 1.

- [ ] **Step 3: Implement**

In `packages/emcee/src/emcee/cli.py` add imports `from typing import NoReturn`, `from pydantic import ValidationError`, `from emcee.tts.provider import SpeechError`, `from emcee.tts.verify import SttClient`. Add the three helpers (`_usage`, `_abs_clip`, `_draft_transcript`) just ABOVE `presenter_add` (Task 14 uses them there), and the `presenter_edit` command just after `presenter_add`:

```python
def _usage(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(2)


def _abs_clip(path: str) -> str:
    """voice_clone is stored absolute and resolved: the mlx-audio server
    reads the clip from its own working directory."""
    return str(Path(path).expanduser().resolve())


def _draft_transcript(config: EmceeConfig, clip: str) -> str:
    """`--transcribe`: draft voice_clone_text by transcribing `clip` with
    verification's STT client and [tts.mlx_audio] stt_model, print it, and
    return it only on confirmation. With [tts.verify] backends empty the STT
    model is unloaded afterwards (the server keeps every model resident)."""
    mlx = config.tts.mlx_audio
    if not mlx.stt_model:
        _usage("--transcribe needs [tts.mlx_audio] stt_model (a speech-to-text model on "
               "the mlx-audio server)")
    try:
        audio = Path(clip).read_bytes()
    except OSError as exc:
        raise EmceeError(f"cannot read the voice clone {clip}: {exc}") from exc
    stt = SttClient(url=mlx.url, model=mlx.stt_model, timeout_s=mlx.timeout_s)
    try:
        text = stt.transcribe(audio)
        if not config.tts.verify.backends:
            try:
                stt.unload()
            except SpeechError as exc:
                typer.echo(f"note: {exc}", err=True)
    finally:
        stt.close()
    if not text:
        raise EmceeError("the transcription came back empty; give --voice-clone-text by hand")
    typer.echo("transcript draft:")
    typer.echo(text)
    if not typer.confirm("use this transcript?", default=False):
        typer.echo("transcript not written; presenter unchanged", err=True)
        raise typer.Exit(1)
    return text


@presenter_app.command("edit")
def presenter_edit(
    id: str = typer.Argument(...),
    name: str = typer.Option(None, "--name"),
    sex: str = typer.Option(None, "--sex"),
    character: str = typer.Option(None, "--character"),
    character_file: Path = typer.Option(None, "--character-file"),
    voice: str = typer.Option(None, "--voice",
                              help="Preset voice; clears voice_clone and voice_clone_text"),
    voice_clone: str = typer.Option(
        None, "--voice-clone",
        help="Reference clip, stored as an absolute path; clears voice, and clears "
             "voice_clone_text unless --voice-clone-text or --transcribe gives a new one"),
    voice_clone_text: str = typer.Option(None, "--voice-clone-text",
                                         help="Transcript of the voice clone"),
    bed: str = typer.Option(None, "--bed"),
    tts: str = typer.Option(None, "--tts",
                            help="Pin a TTS backend: voxtral, elevenlabs or mlx_audio"),
    tts_model: str = typer.Option(None, "--tts-model", help="mlx_audio model for this presenter"),
    clear_tts: bool = typer.Option(False, "--clear-tts"),
    clear_tts_model: bool = typer.Option(False, "--clear-tts-model"),
    clear_bed: bool = typer.Option(False, "--clear-bed"),
    clear_voice_clone_text: bool = typer.Option(False, "--clear-voice-clone-text"),
    transcribe: bool = typer.Option(
        False, "--transcribe",
        help="Draft voice_clone_text by transcribing the (resulting) clip on the mlx-audio "
             "server; written only on confirmation"),
):
    """Edit a presenter; unspecified fields keep their values.

    The edit is validated whole (exactly the rules `presenters/<id>.toml` is
    loaded with) before an atomic save; any rejection -- validation, a
    declined transcript, an unreachable server -- leaves the file untouched.
    """
    config = load_config()
    old = load_presenter(config.root, id)  # PresenterError -> main_cli boundary
    for value, clear, set_flag, clear_flag in (
            (tts, clear_tts, "--tts", "--clear-tts"),
            (tts_model, clear_tts_model, "--tts-model", "--clear-tts-model"),
            (bed, clear_bed, "--bed", "--clear-bed"),
            (voice_clone_text, clear_voice_clone_text, "--voice-clone-text",
             "--clear-voice-clone-text")):
        if value is not None and clear:
            _usage(f"{set_flag} and {clear_flag} are mutually exclusive")
    if voice is not None and voice_clone is not None:
        _usage("--voice and --voice-clone are mutually exclusive")
    if character is not None and character_file is not None:
        _usage("give at most one of --character / --character-file")
    if transcribe and voice_clone_text is not None:
        _usage("--transcribe and --voice-clone-text are mutually exclusive")
    if transcribe and clear_voice_clone_text:
        _usage("--transcribe and --clear-voice-clone-text are mutually exclusive")

    changes: dict = {}
    if name is not None:
        changes["name"] = name
    if sex is not None:
        changes["sex"] = sex
    if character is not None:
        changes["character"] = character
    if character_file is not None:
        try:
            changes["character"] = character_file.read_text().strip()
        except OSError as exc:
            typer.echo(f"cannot read --character-file {character_file}: {exc}", err=True)
            raise typer.Exit(1)
    if voice is not None:
        changes.update(voice=voice, voice_clone=None, voice_clone_text=None)
    if voice_clone is not None:
        changes.update(voice_clone=_abs_clip(voice_clone), voice=None)
        if voice_clone_text is None and not transcribe:
            changes["voice_clone_text"] = None  # forces a fresh transcript for an mlx pin
    if voice_clone_text is not None:
        changes["voice_clone_text"] = voice_clone_text
    if clear_voice_clone_text:
        changes["voice_clone_text"] = None
    if bed is not None:
        changes["bed"] = bed
    if clear_bed:
        changes["bed"] = None
    if tts is not None:
        changes["tts"] = tts
    if clear_tts:
        changes["tts"] = None
    if tts_model is not None:
        changes["tts_model"] = tts_model
    if clear_tts_model:
        changes["tts_model"] = None
    if not changes and not transcribe:
        _usage("nothing to edit: give at least one field option")

    def merged(extra: dict | None = None) -> Presenter:
        # model_validate on the whole merge, never model_copy(update=...),
        # which skips validators.
        return Presenter.model_validate({**old.model_dump(), **changes, **(extra or {})})

    try:
        if transcribe:
            clip = changes.get("voice_clone", old.voice_clone)
            if not clip:
                _usage("--transcribe needs a voice clone (this presenter has a preset voice)")
            merged({"voice_clone_text": "draft"})  # every other rule, before transcribing
            changes["voice_clone_text"] = _draft_transcript(config, clip)
        new = merged()
    except ValidationError as exc:
        typer.echo(f"invalid presenter: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"saved: {save_presenter(config.root, new)}")
```

- [ ] **Step 4: Run the file, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_presenter_edit.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/emcee/src/emcee/cli.py packages/emcee/tests/test_presenter_edit.py
git commit -m "feat(emcee): presenter edit, with --transcribe and set/clear flags

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---

### Task 14: `presenter add` pin flags, `list`/`show` pins, `say --clone-text`

**Implementer model:** Sonnet (mechanical edits to three existing commands + tests; full code below).
**Live:** no.

Spec: section 4 "`emcee presenter add` gains …", "**`emcee say`:** …"; Stakes strict surface 4 (`presenter add` stores an absolute path; list/show change only for pinned presenters); section 6 "`say`: …".

**Files:**
- Modify: `packages/emcee/src/emcee/cli.py` (`presenter_add`, `presenter_list`, `presenter_show`, `say_cmd`)
- Test: `packages/emcee/tests/test_presenter_cmd.py`, `packages/emcee/tests/test_say_cmd.py`

**Interfaces:**
- Consumes: `_usage`, `_abs_clip`, `_draft_transcript` (Task 13); `ad_hoc_speech(config, *, clone_ref, clone_text, voice, presenter)` (Task 5); `install_mlx`, `MlxServer`, `calibrate_test_model`, `TEST_MODEL` (tests).
- Produces:
  - `presenter add` options `--voice-clone-text`, `--tts`, `--tts-model`, `--transcribe`; `voice_clone` stored via `_abs_clip`.
  - `emcee.cli._pin_label(p: Presenter) -> str` = `f"tts={p.tts}"` + `f" tts_model={p.tts_model}"` when set; `list` appends `"  " + _pin_label(p)` and `show` appends it to its first line, for pinned presenters only; `show` prints `transcript:` + `voice_clone_text` for pinned presenters that have one.
  - `say --clone-text TEXT`; usage errors (exact): `--clone-text needs --clone`; `--voice is a preset, but the house backend is mlx_audio, which is clone-only (use --clone with --clone-text, or --presenter)`; `--clone needs --clone-text (the clip's transcript) when the house backend is mlx_audio`. `say` passes `clone_text` to `ad_hoc_speech` only when `[tts] backend == "mlx_audio"`, else `None`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/emcee/tests/test_presenter_cmd.py`:

```python
# --- pins (spec section 4) ----------------------------------------------------------

from functools import partial

from emcee.presenters import load_presenter
from emcee.tts.verify import SttClient

from tests.mlx_helpers import MlxServer, wav_bytes


def _pinned_add_args(clip: str, *extra: str) -> list[str]:
    return ["presenter", "add", "phil", "--name", "Phil", "--sex", "male",
            "--voice-clone", clip, "--character", "Professorial.", *extra]


def test_presenter_add_with_a_pin_stores_an_absolute_clip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path / "home"))
    (tmp_path / "samples").mkdir()
    clip = tmp_path / "samples" / "phil_ex.wav"
    clip.write_bytes(wav_bytes(1.0))
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, _pinned_add_args("samples/phil_ex.wav", "--tts", "mlx_audio",
                                            "--tts-model", "m/x",
                                            "--voice-clone-text", "It's the chemistry."))
    assert r.exit_code == 0, r.output
    p = load_presenter(tmp_path / "home", "phil")
    assert (p.voice_clone, p.tts, p.tts_model, p.voice_clone_text) == (
        str(clip.resolve()), "mlx_audio", "m/x", "It's the chemistry.")


def test_presenter_add_rejects_an_invalid_pin(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    r = runner.invoke(app, ["presenter", "add", "x", "--name", "X", "--sex", "male",
                            "--voice", "preset", "--character", "y", "--tts", "mlx_audio"])
    assert r.exit_code == 1 and "invalid presenter" in r.output and "clone-only" in r.output
    assert not (tmp_path / "presenters" / "x.toml").exists()


@pytest.mark.parametrize("answer, saved", [("y\n", True), ("n\n", False)])
def test_presenter_add_transcribe(tmp_path: Path, monkeypatch, answer, saved):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text('[tts.mlx_audio]\nstt_model = "stt/test-model"\n')
    clip = tmp_path / "phil_ex.wav"
    clip.write_bytes(wav_bytes(1.0))
    server = MlxServer(transcript=lambda last: "It's the chemistry.")
    monkeypatch.setattr("emcee.cli.SttClient", partial(SttClient, transport=server.transport()))
    r = runner.invoke(app, _pinned_add_args(str(clip), "--tts", "mlx_audio", "--transcribe"),
                      input=answer)
    assert (r.exit_code == 0) is saved
    path = home / "presenters" / "phil.toml"
    assert path.exists() is saved
    if saved:
        assert load_presenter(home, "phil").voice_clone_text == "It's the chemistry."


def test_presenter_add_transcribe_needs_a_clone(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    r = runner.invoke(app, ["presenter", "add", "x", "--name", "X", "--sex", "male",
                            "--voice", "preset", "--character", "y", "--transcribe"])
    assert r.exit_code == 2 and "--transcribe needs --voice-clone" in r.output


def test_presenter_list_and_show_display_the_pin_only_when_pinned(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path))
    runner.invoke(app, ["presenter", "add", "phil", "--name", "Phil", "--sex", "male",
                        "--voice-clone", "/r/phil.wav", "--character", "x", "--tts", "mlx_audio",
                        "--tts-model", "m/x", "--voice-clone-text", "It's the chemistry."])
    runner.invoke(app, ["presenter", "add", "roy", "--name", "Roy", "--sex", "male",
                        "--voice", "roy-preset", "--character", "x"])
    listed = runner.invoke(app, ["presenter", "list"]).output
    assert f"{'phil':16.16s} {'Phil':20.20s} {'male':8.8s} clone:/r/phil.wav  tts=mlx_audio tts_model=m/x" in listed
    roy_line = next(line for line in listed.splitlines() if line.startswith("roy"))
    assert roy_line == f"{'roy':16.16s} {'Roy':20.20s} {'male':8.8s} roy-preset"
    shown = runner.invoke(app, ["presenter", "show", "phil"]).output
    assert shown.splitlines()[0] == "Phil  (male)  voice=clone:/r/phil.wav  tts=mlx_audio tts_model=m/x"
    assert "transcript:\nIt's the chemistry." in shown
    roy = runner.invoke(app, ["presenter", "show", "roy"]).output
    assert "tts=" not in roy and "transcript:" not in roy
```

Add `import pytest` to `test_presenter_cmd.py`'s imports.

In `packages/emcee/tests/test_say_cmd.py`, change the expected dict in `test_say_forwards_a_clone_reference` to

```python
    assert seen == {"clone_ref": str(ref), "clone_text": None, "voice": None, "presenter": None}
```

and append:

```python
# ---------------------------------------------------------------------------
# --clone-text and the mlx_audio house (spec section 4)
# ---------------------------------------------------------------------------

from tests.mlx_helpers import TEST_MODEL, MlxServer, calibrate_test_model, install_mlx, wav_bytes

HOUSE_TEXT = "House words, spoken for the record."


def _mlx_house(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    clip = home / "house.wav"
    clip.write_bytes(wav_bytes(1.0))
    (home / "config.toml").write_text(
        f'[tts]\nbackend = "mlx_audio"\nvoice_clone = "{clip}"\n'
        f'voice_clone_text = "{HOUSE_TEXT}"\n\n[tts.mlx_audio]\nmodel = "{TEST_MODEL}"\n')
    return clip


def test_say_clone_text_without_clone_is_a_usage_error(tmp_path, monkeypatch):
    _arm_speech(monkeypatch)
    result = _run(["say", str(_text_file(tmp_path)), "--clone-text", "words"], tmp_path, monkeypatch)
    assert result.exit_code == 2 and "--clone-text needs --clone" in result.output


def test_say_ignores_clone_text_under_a_hosted_house(tmp_path, monkeypatch):
    _, seen = _arm_speech(monkeypatch)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"REF")
    _run(["say", str(_text_file(tmp_path)), "--clone", str(ref), "--clone-text", "words"],
         tmp_path, monkeypatch)
    assert seen["clone_text"] is None


def test_say_forwards_clone_text_under_an_mlx_house(tmp_path, monkeypatch):
    _, seen = _arm_speech(monkeypatch)
    _mlx_house(tmp_path, monkeypatch)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"REF")
    result = runner.invoke(app, ["say", str(_text_file(tmp_path)), "--clone", str(ref),
                                 "--clone-text", "Their words."])
    assert result.exit_code == 0, result.output
    assert (seen["clone_ref"], seen["clone_text"]) == (str(ref), "Their words.")


@pytest.mark.parametrize("args, message", [
    (["--clone", "REF"], "--clone needs --clone-text (the clip's transcript) when the house backend is mlx_audio"),
    (["--clone", "REF", "--clone-text", "   "], "--clone needs --clone-text"),
    (["--voice", "preset"], "--voice is a preset, but the house backend is mlx_audio, which is clone-only"),
])
def test_say_usage_errors_under_an_mlx_house(tmp_path, monkeypatch, args, message):
    _arm_speech(monkeypatch)
    _mlx_house(tmp_path, monkeypatch)
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"REF")
    args = [str(ref) if a == "REF" else a for a in args]
    result = runner.invoke(app, ["say", str(_text_file(tmp_path)), *args])
    assert result.exit_code == 2 and message in result.output


def test_say_with_no_voice_flags_sends_the_house_transcript(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    _mlx_house(tmp_path, monkeypatch)
    server = MlxServer()
    install_mlx(monkeypatch, server)
    result = runner.invoke(app, ["say", str(_text_file(tmp_path, "Good evening to all of you out there."))])
    assert result.exit_code == 0, result.output
    assert server.speech_bodies and all(b["ref_text"] == HOUSE_TEXT for b in server.speech_bodies)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/pytest packages/emcee/tests/test_presenter_cmd.py packages/emcee/tests/test_say_cmd.py -q`
Expected: FAIL — `No such option: --tts` / `--clone-text`, and the `clone_text` key missing from `seen`.

- [ ] **Step 3: Implement `presenter add`, `list`, `show`**

In `packages/emcee/src/emcee/cli.py` replace `presenter_add` with:

```python
@presenter_app.command("add")
def presenter_add(
    id: str = typer.Argument(...),
    name: str = typer.Option(..., "--name"),
    sex: str = typer.Option(..., "--sex"),
    voice: str = typer.Option(None, "--voice"),
    voice_clone: str = typer.Option(None, "--voice-clone",
                                    help="Reference clip, stored as an absolute path"),
    voice_clone_text: str = typer.Option(None, "--voice-clone-text",
                                         help="Transcript of the voice clone"),
    character: str = typer.Option(None, "--character"),
    character_file: Path = typer.Option(None, "--character-file"),
    bed: str = typer.Option(None, "--bed"),
    tts: str = typer.Option(None, "--tts",
                            help="Pin a TTS backend: voxtral, elevenlabs or mlx_audio"),
    tts_model: str = typer.Option(None, "--tts-model", help="mlx_audio model for this presenter"),
    transcribe: bool = typer.Option(
        False, "--transcribe",
        help="Draft voice_clone_text by transcribing the clip on the mlx-audio server; "
             "written only on confirmation"),
    force: bool = typer.Option(False, "--force"),
):
    """Create a presenter (on-air host)."""
    config = load_config()
    root = config.root
    if bool(character) == bool(character_file):
        typer.echo("give exactly one of --character / --character-file", err=True)
        raise typer.Exit(1)
    if transcribe and voice_clone_text is not None:
        _usage("--transcribe and --voice-clone-text are mutually exclusive")
    if transcribe and not voice_clone:
        _usage("--transcribe needs --voice-clone")
    if character:
        text = character
    else:
        try:
            text = character_file.read_text().strip()
        except OSError as exc:
            typer.echo(f"cannot read --character-file {character_file}: {exc}", err=True)
            raise typer.Exit(1)
    dest = root / "presenters" / f"{id}.toml"
    if dest.exists() and not force:
        typer.echo(f"presenter {id!r} exists: {dest} (use --force to overwrite)", err=True)
        raise typer.Exit(1)
    fields = dict(id=id, name=name, sex=sex, voice=voice,
                  voice_clone=_abs_clip(voice_clone) if voice_clone else None,
                  character=text, bed=bed, tts=tts, tts_model=tts_model,
                  voice_clone_text=voice_clone_text)
    try:
        if transcribe:
            Presenter(**{**fields, "voice_clone_text": "draft"})  # every other rule first
            fields["voice_clone_text"] = _draft_transcript(config, fields["voice_clone"])
        p = Presenter(**fields)
    except ValidationError as exc:
        typer.echo(f"invalid presenter: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"saved: {save_presenter(root, p)}")
```

(The helpers `_usage`, `_abs_clip`, `_draft_transcript` already sit above `presenter_add` since Task 13.) Add, next to them:

```python
def _pin_label(p: Presenter) -> str:
    return f"tts={p.tts}" + (f" tts_model={p.tts_model}" if p.tts_model else "")
```

In `presenter_list`, change the valid-presenter branch to:

```python
            v = p.voice or f"clone:{p.voice_clone}"
            pin = f"  {_pin_label(p)}" if p.tts else ""
            typer.echo(f"{pid:16.16s} {p.name:20.20s} {p.sex:8.8s} {v}{pin}")
```

and `presenter_show` to:

```python
    p = load_presenter(root, id)     # PresenterError -> main_cli boundary
    v = p.voice or f"clone:{p.voice_clone}"
    typer.echo(f"{p.name}  ({p.sex})  voice={v}" + (f"  bed={p.bed}" if p.bed else "")
               + (f"  {_pin_label(p)}" if p.tts else ""))
    typer.echo("character:")
    typer.echo(p.character)
    if p.tts and p.voice_clone_text:
        typer.echo("transcript:")
        typer.echo(p.voice_clone_text)
```

- [ ] **Step 4: Implement the `say` flags**

In `say_cmd`, add the option after `clone`:

```python
    clone_text: str = typer.Option(
        None, "--clone-text",
        help="Transcript of the --clone clip; required when the house backend is "
             "mlx_audio, ignored otherwise"),
```

change the `--clone` help to `"Reference clip to clone (3-25s; voxtral or mlx_audio), instead of a preset voice"`, and replace the lines from `config = load_config()` through the `ad_hoc_speech(...)` call with:

```python
    config = load_config()
    if clone_text is not None and clone is None:
        _usage("--clone-text needs --clone")
    house_mlx = config.tts.backend == "mlx_audio"
    if house_mlx and voice:
        _usage("--voice is a preset, but the house backend is mlx_audio, which is clone-only "
               "(use --clone with --clone-text, or --presenter)")
    if house_mlx and clone is not None and not (clone_text or "").strip():
        _usage("--clone needs --clone-text (the clip's transcript) when the house backend "
               "is mlx_audio")

    text = text_file.read_text().strip()
    if not text:
        raise EmceeError(f"nothing to say: {text_file} is empty")

    host = load_presenter(config.root, presenter) if presenter else None
    speech = ad_hoc_speech(config, clone_ref=str(clone) if clone else None,
                           clone_text=clone_text if house_mlx else None,
                           voice=voice, presenter=host)
```

Extend the docstring's VOICE paragraph: "With no voice flags the house voice reads it, including its `[tts] voice_clone_text`. `--clone-text` is the `--clone` clip's transcript, required when the house backend is mlx_audio (which is clone-only, so `--voice` is refused there); `--presenter` resolves exactly as in `emcee run`, pin included."

- [ ] **Step 5: Run the files, then the full suite**

Run: `./.venv/bin/pytest packages/emcee/tests/test_presenter_cmd.py packages/emcee/tests/test_say_cmd.py packages/emcee/tests/test_presenter_edit.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/emcee/src/emcee/cli.py packages/emcee/tests/test_presenter_cmd.py \
        packages/emcee/tests/test_say_cmd.py
git commit -m "feat(emcee): presenter add pin flags, list/show pins, say --clone-text

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---
### Task 15: Docs — the runbook, CLAUDE.md, and the template's STT model

**Implementer model:** Sonnet (documentation from fully specified content; one config-template comment).
**Live:** no.

Spec: section 5 (every bullet); Stakes strict surface 4 (what changes for existing configs).

**Files:**
- Modify: `README.md` (the "emcee: voicing delivered packages" section)
- Modify: `CLAUDE.md` (Commands bullet for emcee; the "What this is" emcee paragraph; the emcee architecture bullet; Conventions)
- Modify: `packages/emcee/src/emcee/config.py` (one template comment)

**Interfaces:**
- Consumes: the probe doc's `stt_model` (Task 1); the calibration evidence doc and `docs/superpowers/2026-10-12-mlx-audio-requirements.txt` (Task 12); every command and key defined in Tasks 2-14.
- Produces: documentation only.

- [ ] **Step 1: Template comment**

In `DEFAULT_CONFIG_TOML`, replace `# stt_model = "..."          # speech-to-text model on the same server` with `# stt_model = "<stt_model from docs/superpowers/2026-10-12-mlx-audio-probe.md>"  # speech-to-text model on the same server` — writing the actual model id, not the angle-bracket text. Run `./.venv/bin/pytest packages/emcee/tests/test_config.py -q` → PASS.

- [ ] **Step 2: README — setup, presenters and `say`**

In the README's emcee `**Setup.**` block, after the `backend = "voxtral"` line add:

```
                               # or "mlx_audio": local, on this Mac (see "Local TTS" below)
```

In `**Presenters.**`, after the `emcee presenter show casey` line add:

```
    emcee presenter edit casey --tts voxtral
                                     # change any field; --clear-tts/--clear-tts-model/
                                     # --clear-bed/--clear-voice-clone-text; --transcribe
                                     # drafts voice_clone_text on the mlx-audio server
```

and extend the shape sentence ("`name`/`sex`/`character` + exactly one of `voice`/`voice_clone`, plus an optional `bed` override.") with: "Three optional keys pin a presenter's TTS: `tts` (`voxtral`, `elevenlabs` or `mlx_audio`; absent = `[tts] backend`), `tts_model` (mlx_audio only) and `voice_clone_text` (the clip's transcript, required by mlx_audio). The file is strict: an unknown key is a load error. `emcee run --dry-run` shows each pinned presenter's backend and model."

In the `say` examples, change the `--clone ref.wav` comment to `# clone a 3-25s reference clip (voxtral or mlx_audio; under an mlx_audio house add --clone-text "<transcript>")`.

- [ ] **Step 3: README — the runbook**

Insert this subsection immediately before `**Upgrading from a pre-split llama.**` (fill `<STT_MODEL>` with the probe doc's `stt_model`, and `<YOU>` stays as written for the reader to substitute):

````markdown
**Local TTS on this Mac (`mlx_audio`).** A presenter (or the house voice) can
be voiced by a free local model served by [mlx-audio](https://github.com/Blaizzy/mlx-audio)'s
`mlx_audio.server`, instead of hosted Voxtral. Only calibrated models resolve
(today: `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16`; evidence in
`docs/superpowers/2026-10-12-mlx-audio-calibration.md`), and an `mlx_audio`
voice never falls back to another backend: if the server is down, its
packages fail (before any LLM spend, and without touching a voiced package)
and the rest of `emcee run` carries on.

1. **Install the new emcee release before pinning any presenter.** An older
   binary does not know `tts`/`tts_model` and would voice the presenter on
   Voxtral from the newly edited clip. (Older binaries silently ignore these
   keys; from this release an unknown key is a load error.)
2. **A dedicated venv, pinned to the evaluated mlx-audio**, whose server-side
   sampling defaults (temperature, top_k, top_p) define the evaluated voice —
   emcee does not send them. From a checkout of this repo (the constraints
   file is the evaluated environment's `pip freeze`):

       mkdir -p ~/.mlx-audio/logs
       uv venv --python 3.12 ~/.mlx-audio/venv
       uv pip install --python ~/.mlx-audio/venv/bin/python \
           "mlx-audio[server,tts,stt]==0.5.8" \
           -c docs/superpowers/2026-10-12-mlx-audio-requirements.txt

3. **Download the models once, while online** (the service runs offline, so a
   mistyped model id fails fast instead of starting a download):

       ~/.mlx-audio/venv/bin/python -c "from huggingface_hub import snapshot_download as d; \
           d('mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16'); d('<STT_MODEL>')"

4. **A launchd agent**, bound to 127.0.0.1, with a working directory and log
   directory that exist (launchd starts jobs in `/`, where the server's
   default relative `logs` directory cannot be created). Save as
   `~/Library/LaunchAgents/com.lma-radio.mlx-audio.plist`:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
     <key>Label</key><string>com.lma-radio.mlx-audio</string>
     <key>ProgramArguments</key>
     <array>
       <string>/Users/<YOU>/.mlx-audio/venv/bin/python</string>
       <string>-m</string><string>mlx_audio.server</string>
       <string>--host</string><string>127.0.0.1</string>
       <string>--port</string><string>8000</string>
       <string>--log-dir</string><string>/Users/<YOU>/.mlx-audio/logs</string>
     </array>
     <key>WorkingDirectory</key><string>/Users/<YOU>/.mlx-audio</string>
     <key>EnvironmentVariables</key>
     <dict><key>HF_HUB_OFFLINE</key><string>1</string></dict>
     <key>RunAtLoad</key><true/>
     <key>KeepAlive</key><true/>
     <key>StandardOutPath</key><string>/Users/<YOU>/.mlx-audio/server.log</string>
     <key>StandardErrorPath</key><string>/Users/<YOU>/.mlx-audio/server.log</string>
   </dict>
   </plist>
   ```

   Start it with `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.lma-radio.mlx-audio.plist`,
   restart with `launchctl kickstart -k gui/$(id -u)/com.lma-radio.mlx-audio`,
   stop with `launchctl bootout gui/$(id -u)/com.lma-radio.mlx-audio`.
   `curl -s http://127.0.0.1:8000/` answers when it is up. A generation
   failure's details are in `~/.mlx-audio/server.log` — emcee's error says so.
5. **emcee config:**

       [tts.mlx_audio]
       model = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
       stt_model = "<STT_MODEL>"    # for verification and --transcribe
       # url = "http://127.0.0.1:8000"   timeout_s = 600 (defaults)

       # optional: transcribe every new clip and re-synthesize once on a gross mismatch
       # [tts.verify]
       # backends = ["mlx_audio"]    # adding "voxtral" makes Voxtral presenters depend on this server too

   Hosted keys can move into `[tts.voxtral] api_key` / `[tts.elevenlabs]
   api_key` (they apply wherever that backend voices); your existing `[tts]
   api_key` keeps working while `[tts] backend` is hosted. Don't set the same
   key in both places.
6. **Memory.** The server keeps every model it has served resident until it
   restarts: presenters pinned to different mlx models hold all of them, and
   with verification on it also holds the STT model (`--transcribe` unloads
   the STT model again when verification is off).
7. **Moving Phil** (his evaluated 12.9 s, 24 kHz mono excerpt and its
   transcript), after the calibration doc exists:

       cp ~/tts-bakeoff/refs/phil_ex.wav ~/tts-bakeoff/refs/phil_ex.txt ~/.emcee/samples/
       emcee presenter edit phil --tts mlx_audio --voice-clone ~/.emcee/samples/phil_ex.wav \
           --voice-clone-text "$(cat ~/.emcee/samples/phil_ex.txt)"
       emcee run --dry-run                       # phil's rows now end [mlx_audio <model>]
       emcee say notes.txt --presenter phil      # go-live listen, then one real package:
       emcee voice <a dead package> 

   During that first real `emcee voice` (TTS, STT and `claude -p` all
   resident), take a memory reading from another terminal —
   `footprint -p $(lsof -tiTCP:8000 -sTCP:LISTEN)` and `vm_stat` — and record
   it beside the calibration doc's `footprint` reading.

   For any presenter other than Phil (whose voice was evaluated), listen
   before relying on the pin: pin them, render one `emcee say notes.txt
   --presenter <id>` and listen to it with no `emcee run` in between, and
   unpin (`--clear-tts`) if it does not pass.

   For a NEW presenter, `--transcribe` drafts the transcript (`emcee
   presenter add … --voice-clone clip.wav --tts mlx_audio --transcribe`) and
   writes it only after you confirm it. Without a server-loadable STT model,
   draft it by hand with `mlx_whisper clip.wav --model
   mlx-community/whisper-large-v3-turbo --language en` (from `pip install
   mlx-whisper`) and pass it as `--voice-clone-text`. Reference clips may be
   any rate or channel count (the server resamples and down-mixes them).
8. **Moving the house voice to mlx_audio** (`[tts] backend = "mlx_audio"`,
   plus `[tts] voice_clone` and `voice_clone_text`; drop `[tts] api_key`/`model`
   into the hosted tables): pin every presenter first, e.g. `emcee presenter
   edit roydemure --tts voxtral` — an unpinned presenter under an mlx_audio
   house is an error, never a silent move. With `[assign] default =
   "roydemure"` every package has a presenter, so moving "the default voice"
   means pinning Roy, not changing the house.
9. **Rollback.** Unpin Phil back to his aired Voxtral reference — and do this
   BEFORE downgrading the emcee binary:

       emcee presenter edit phil --clear-tts --clear-tts-model --voice-clone ~/.emcee/samples/phil.wav

   A re-pinned presenter never reuses the other backend's clips (the render
   cache keys on backend voice and model), so his next packages re-render.
````

- [ ] **Step 4: CLAUDE.md**

1. In the Commands bullet for emcee, replace `` `emcee presenter add/list/show/remove` `` … `(`presenters/<id>.toml`)` with: `` `emcee presenter add/edit/list/show/remove` (`presenters/<id>.toml`; `edit` changes any field with set/`--clear-*` flags, `--transcribe` drafts `voice_clone_text` on the mlx-audio server's STT model and writes it only on confirmation; `voice_clone` is stored as an absolute path) ``, and after the `--dry-run` description in the same bullet add: "a pinned presenter's row also shows `[<backend> <model>]`, an unloadable presenter file `[invalid presenters/<id>.toml]`, a failed TTS resolution `[unresolved: …]`".
2. In "What this is", replace "TTS (hosted Mistral Voxtral by default, ElevenLabs as an opt-in alternative — presenter voice clones are Voxtral-only)" with "TTS (hosted Mistral Voxtral by default, ElevenLabs as an opt-in alternative, and a free local `mlx_audio` backend over mlx-audio's server; a presenter may pin any of the three with `tts`, and clones are voiced on voxtral or mlx_audio, never elevenlabs)".
3. In the emcee architecture bullet, after the sentence ending "re-voices only that segment …" paragraph (before "`presenters.py` manages …"), add:

```markdown
  **Per-presenter TTS pinning + the local `mlx_audio` backend**
  (`docs/superpowers/specs/2026-10-12-local-tts-presenter-pinning-design.md`).
  A presenter's `tts` pins its backend; an unpinned presenter inherits
  `[tts] backend` — EXCEPT that a presenter never inherits `mlx_audio` (a
  resolution error, `pin tts explicitly`), so moving the house voice never
  moves a presenter. `tts/resolve.py:resolve_tts` is pure and runs before any
  spend; `speech_provider_for(config, resolution, *, voice, clone_ref,
  clone_text)` takes no defaults, so no call site can fall back to `[tts]
  backend` or drop the transcript. Hosted keys/models live in
  `[tts.voxtral]`/`[tts.elevenlabs]` (legacy `[tts] api_key`/`model` still mean
  the HOUSE hosted backend's; the env var still wins). `tts/mlx_audio.py` is
  clone-only, sends `ref_audio` as an ABSOLUTE path (the server reads it from
  its own cwd) plus `ref_text` (`voice_clone_text`), always requests WAV, and
  never falls back. Every mlx clip passes the per-model runaway guard
  (`tts/calibration.py`: `max_tokens` capped in proportion to the text, the
  duration checked; `CALIBRATED_MODELS` holds MEASURED entries only, and an
  uncalibrated model is a resolution error). The quality layer
  (`tts/quality.py`) owns the ONE re-synthesis; a second guard or
  verification failure is a `SpeechDefect` that fails the package. Optional
  transcript verification (`[tts.verify] backends`, `tts/verify.py`) fails only
  gross mismatches and never re-verifies cached clips. `preflight()` runs in
  `cli._process_one` before the `--fresh` unlink, the manifest clear and any
  LLM spend: a no-op on hosted providers, one fixed sentence on mlx, and the
  STT path end to end when verification applies (hosted: the bundled
  `emcee/data/preflight_en.wav`). Evidence: `docs/superpowers/2026-10-12-mlx-audio-probe.md`
  and `…-mlx-audio-calibration.md` (adding a model means a calibration run,
  `scripts/mlx_audio_calibrate.py`). Runbook: README "Local TTS on this Mac".
```

4. In the same bullet, change "`presenters.py` manages `presenters/<id>.toml` (`emcee presenter add/list/show/remove`) — the same TOML shape llama's presenters used to have (`name`/`sex`/`character` + exactly one of `voice`/`voice_clone`, optional `bed` override)" to add "`add/edit/list/show/remove`" and ", plus the optional `tts`/`tts_model`/`voice_clone_text` pin; strict — an unknown key is a load error".
5. In "Conventions", after "Audio files (`*.mp3`, `*.flac`, `*.shn`) are gitignored; never commit audio." add: "One exception: `packages/emcee/src/emcee/data/preflight_en.wav`, the ~2 s bundled check clip for the verification preflight (provenance in `docs/superpowers/2026-10-12-mlx-audio-calibration.md`)."

- [ ] **Step 5: Check, then run the full suite**

Run: `grep -n "Voxtral-only" README.md CLAUDE.md packages/emcee/src` → no remaining claim that presenter clones are Voxtral-only (the ElevenLabs factory message says "not available on elevenlabs").
Run: `./.venv/bin/pytest -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md packages/emcee/src/emcee/config.py
git commit -m "docs(emcee): local mlx_audio runbook, presenter pinning and edit

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TNheuMFMvYwCHKaT9xJRS2"
```

---

## Spec coverage map

| Spec requirement | Task |
|---|---|
| Stakes 1 — never silently fall back | 5 (keyword-only factory), 9 (`test_no_fallback_when_the_mlx_server_is_down`) |
| Stakes 2 — config failures before LLM spend / manifest clear / `--fresh` unlink | 7 (order + fake-preflight tests), 9 (dead server), 11 (STT path; the config-only failure matrix over `_process_one` and `voice --fresh`) |
| Stakes 2 — verification never silently skipped; cache hits reused unverified | 11 |
| Stakes 3 — double guard/verification failure fails the package | 10, 11 |
| Stakes 4 — unchanged behaviour with no pins; `--fresh` keeps clips on failure; strict presenter files; absolute `voice_clone` in `add`; list/show/dry-run change only for pins | 2, 6, 7, 13, 14 |
| §1 Presenter fields, strict base, validation | 2 |
| §1 Config subtables, legacy keys, duplicate-key error, house-mlx key/model errors | 3 |
| §1 Resolution rules, calibration-table check | 4 |
| §1 Factory required args, `clone_text`, `speech_for`/`ad_hoc_speech` via resolver, ElevenLabs clone check, missing-key message | 5 |
| §1 House voice on mlx_audio: preset/clip/transcript rejected naming `[tts]` keys | 9 |
| §1 Dry-run pins, `[invalid …]`, `[unresolved: …]`, case-insensitive load | 6 |
| §2 Request, identity, audio contract, errors, timeout | 8 |
| §2 Preflight (protocol, no-op hosted/fake, mlx sentence, 24 kHz) and its position; `--fresh` move | 7, 8, 9 |
| §3 Runaway guard and calibration table | 4, 8, 12 |
| §3 Quality layer | 10 |
| §3 Transcript verification (request shape, comparison, config rules, preflight STT check, bundled clip, `say`) | 3, 11, 12 |
| §3 Constants measured (calibration task) | 12 |
| §4 `presenter edit` | 13 |
| §4 `presenter add` flags, list/show pins, `say --clone-text`/`--voice` rules, reference clips not converted | 14 (server-side resampling: no code; runbook in 15) |
| §5 Runbook, template, evidence doc, CLAUDE.md | 3 (template), 12 (evidence), 15 |
| §6 Every testing bullet | 2-14 (each bullet's test lives with its code) |
| §6 One opt-in live test | 12 |
| Unverified premises: STT model, live WAV, mid-stream exception | 1 |
| Unverified premises: memory (`footprint`), unseeded quality | 12 (recorded), 15 (runbook go-live listen) |
