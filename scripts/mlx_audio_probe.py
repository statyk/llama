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
