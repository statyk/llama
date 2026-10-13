#!/usr/bin/env python3
"""Calibration run for emcee's mlx_audio runaway guard and transcript
verification (spec 2026-10-12-local-tts-presenter-pinning-design.md, section
3 "Constants are measured, not guessed"). Evidence for
docs/superpowers/2026-10-12-mlx-audio-calibration.md.

Renders ~50 unseeded sentences in five presenters' cloned voices (Phil's
evaluated excerpt among them) and a few whole segments (the unchunked path)
through the real server, optionally ~10 Voxtral sentences, and saves every
unit's WAV under --clips-dir. The data file (--out) is written after every
rendered unit, so an interrupted run resumes with --reuse. It then cuts the
bake-off's two known runaways out of their mixes, and transcribes every unit
and both runaways with each --stt-model in turn (one pass per model, the TTS
model unloaded first and each STT model unloaded after its pass, to spare
memory). The FIRST --stt-model is the primary: it drafts the clone voices'
reference transcripts and fills the per-unit `transcript`/`recall`/... fields;
every model's results sit under the unit's `stt`. Finally it flags units for
the operator's listen and prints the flagged units, the constants the
derivation rules in `recommend` produce (the verification thresholds once per
STT model), and the comparison in `analyse`.

    ./.venv/bin/python scripts/mlx_audio_calibrate.py --url http://127.0.0.1:8781 \\
        --stt-model <primary stt model> [--stt-model <another>] --clips-dir <scratch dir> \\
        --out docs/superpowers/2026-10-12-mlx-audio-calibration-data.json \\
        [--voxtral] [--server-pid PID] [--station-root /Volumes/media/lma-radio/delivered]

Re-derive from the saved units after the operator's classification, without
rendering anything (a transcription pass runs only for a model with missing
results, so a complete data file needs no server):

    ./.venv/bin/python scripts/mlx_audio_calibrate.py --url ... --stt-model ... \\
        --out <the same data file> --reuse [--defects 3,17] [--artefacts 9]

Read-only on ~/.emcee, the station root and ~/tts-bakeoff, except that it
writes drafted reference transcripts to ~/tts-bakeoff/refs/<clip>.draft.txt;
every unit's WAV goes under --clips-dir.
"""
import argparse
import contextlib
import dataclasses
import io
import json
import math
import os
import statistics
import subprocess
import time
import tomllib
import wave
from collections import Counter
from pathlib import Path

import httpx

import emcee.tts.verify as verify_mod
from emcee.audio import _split_sentences
from emcee.speech_text import load_lexicon, normalize_for_speech
from emcee.tts.calibration import (ModelCalibration, cap_seconds, guard_problem, max_tokens_for,
                                   text_units)
from emcee.tts.mlx_audio import MlxAudioProvider
from emcee.tts.provider import SpeechError
from emcee.tts.verify import SttClient, comparable_words, match_words, transcript_problem
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
DEFECT_RECALL = 0.5   # mechanical default: a defect below this recall under EVERY model,
DEFECT_SPC = 2.0      # or above this multiple of the voice's median s/char
SHORT_WORDS = 8       # the verification derivation splits units at this many comparable words
THRESHOLD_NAMES = ("MISS_FLOOR", "MISS_FRACTION", "EXTRA_FLOOR", "EXTRA_FRACTION")
# Task 11's interim thresholds (verify.py carries the measured ones since).
INTERIM = {"MISS_FLOOR": 2, "MISS_FRACTION": 0.25, "EXTRA_FLOOR": 4, "EXTRA_FRACTION": 0.5}
MLX_KINDS = ("sentence", "segment")
# A name the STT models are known to mishear while Qwen says it right (the
# operator listened; probe doc): misses confined to it are an STT artefact.
DE_DOELEN = {"de", "doelen"}
DE_DOELEN_NOTE = "operator: De Doelen pronunciation correct (prior listen)"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wav_seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as w:
        frames = w.readframes(w.getnframes())
        return len(frames) / (w.getsampwidth() * w.getnchannels() * w.getframerate())


def has_loop(words: list[str]) -> bool:
    """A repetition loop: some word trigram occurs three or more times."""
    return any(c >= 3 for c in Counter(zip(words, words[1:], words[2:])).values())


def save(out: Path, data: dict) -> None:
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(out)


# ---------------------------------------------------------------- the units

def script_texts(station_root: str | None) -> tuple[list[str], dict]:
    """The DJ scripts to sample, and a record of where they came from: the
    station root's delivered manifests (their `dj_notes`), else the bake-off's
    input texts. Unreadable manifests are recorded, not silently dropped."""
    texts: list[str] = []
    source = {"station_root": station_root, "manifests": 0, "with_dj_notes": 0,
              "without_dj_notes": 0, "skipped": []}
    root = Path(station_root) if station_root else None
    if root is not None and root.is_dir():
        for manifest in sorted(root.glob("*/manifest.json")):
            source["manifests"] += 1
            try:
                notes = json.loads(manifest.read_text()).get("dj_notes") or {}
            except (OSError, ValueError, AttributeError) as e:
                source["skipped"].append({"path": str(manifest), "reason": f"{type(e).__name__}: {e}"})
                continue
            if not notes:
                source["without_dj_notes"] += 1
                continue
            source["with_dj_notes"] += 1
            texts += list((notes.get("set_intros") or {}).values())
            if notes.get("outro"):
                texts.append(notes["outro"])
    if texts:
        source["used"] = "station-root dj_notes (set_intros + outro)"
    else:
        files = sorted((BAKEOFF / "inputs").glob("*.txt"))
        texts = [p.read_text() for p in files]
        source["used"] = "bake-off inputs: " + ", ".join(str(p) for p in files)
    source["skipped_count"] = len(source["skipped"])
    source["texts"] = len(texts)
    return texts, source


def pick_units(texts: list[str]) -> tuple[list[str], list[str]]:
    lexicon = load_lexicon(HOME / ".emcee")
    segments = [normalize_for_speech(t, lexicon) for t in texts]
    sentences = sorted({s for seg in segments for s in _split_sentences(seg)}, key=len)
    idx = [round(i * (len(sentences) - 1) / (N_SENTENCES - 1)) for i in range(N_SENTENCES)]
    picked = list(dict.fromkeys(sentences[i] for i in idx))
    segs = sorted({s for s in segments if len(s) <= SEGMENT_MAX_CHARS}, key=len)
    seg_pick = list(dict.fromkeys([segs[0], segs[len(segs) // 2], segs[-1]])) if segs else []
    return picked, seg_pick


def voices(stt: SttClient) -> tuple[list[dict], list[dict]]:
    """The clone voices, and the ones skipped (missing clip, or an empty
    drafted transcript -- recorded, never aborting the run)."""
    out = [{"name": "phil_ex", "clip": str(BAKEOFF / "refs" / "phil_ex.wav"),
            "text": (BAKEOFF / "refs" / "phil_ex.txt").read_text().strip(), "transcript": "evaluated"}]
    skipped = []
    for stem in OTHER_VOICES:
        clip = SAMPLES / f"{stem}.wav"
        if not clip.exists():
            skipped.append({"name": stem, "reason": f"clip missing: {clip}"})
            continue
        draft = BAKEOFF / "refs" / f"{stem}.draft.txt"
        if not draft.exists():
            log(f"drafting the reference transcript of {stem}")
            draft.write_text(stt.transcribe(clip.read_bytes()))
        text = draft.read_text().strip()
        if not text:
            skipped.append({"name": stem, "reason": f"drafted transcript is empty: {draft}"})
            continue
        out.append({"name": stem, "clip": str(clip), "text": text, "transcript": "stt-draft",
                    "draft": str(draft)})
    return out, skipped


def plan_units(sentences: list[str], segments: list[str], vs: list[dict],
               voxtral: bool) -> list[dict]:
    plan = []
    others = [v["name"] for v in vs[1:]] or ["phil_ex"]
    for i, text in enumerate(sentences):
        plan.append({"kind": "sentence", "voice": "phil_ex" if i % 2 == 0
                     else others[(i // 2) % len(others)], "text": text})
    for text in segments:
        plan.append({"kind": "segment", "voice": "phil_ex", "text": text})
    if voxtral:
        for text in sentences[::max(1, len(sentences) // N_VOXTRAL)][:N_VOXTRAL]:
            plan.append({"kind": "voxtral", "voice": "voxtral-house", "text": text})
    return plan


def synthesize_raw(provider, text: str) -> tuple[bytes, str | None]:
    """The take and, for mlx, the measurement guard's verdict -- without
    raising on it, so a capped take is still saved for the operator to hear."""
    if isinstance(provider, MlxAudioProvider):
        mt = max_tokens_for(MEASURE_CAL, text)
        wav = provider._post(text, mt)
        return wav, guard_problem(MEASURE_CAL, text, provider._read_wav(wav), mt)
    return provider.synthesize(text, fmt="wav"), None


def render(kind: str, voice: str, provider, text: str, clip: Path) -> dict:
    """Render one unit and save its WAV as `clip`. Transcription is a later pass."""
    rec = {"kind": kind, "voice": voice, "text": text, "chars": text_units(text), "clip": None,
           "stt": {}}
    t = time.time()
    try:
        wav, runaway = synthesize_raw(provider, text)
    except SpeechError as e:
        rec.update(render_status="error", error=str(e), wall_s=round(time.time() - t, 1))
        log(f"{kind:8} {voice:14} {rec['chars']:5}ch ERROR {e}")
        return rec
    clip.write_bytes(wav)
    rec.update(clip=str(clip), wall_s=round(time.time() - t, 1),
               seconds=round(wav_seconds(wav), 3), render_status="ok")
    if runaway:
        rec.update(render_status="runaway-at-measurement-cap", reason=runaway)
    log(f"{kind:8} {voice:14} {rec['chars']:5}ch {rec['seconds']:7.2f}s "
        f"wall {rec['wall_s']:6.1f}s {rec['render_status']}")
    return rec


def unload(url: str, model: str) -> int | None:
    """Free a model on the server; 204 and 404 (not loaded) are both fine."""
    try:
        resp = httpx.delete(url.rstrip("/") + "/v1/models", params={"model_name": model},
                            timeout=60)
    except httpx.HTTPError as e:
        log(f"unload {model}: {type(e).__name__}: {e}")
        return None
    log(f"unload {model}: {resp.status_code}")
    return resp.status_code


def render_all(data: dict, out: Path, url: str, use_voxtral: bool, server_pid: int | None) -> None:
    clips = Path(data["clips_dir"])
    clips.mkdir(parents=True, exist_ok=True)
    units, plan = data["units"], data["plan"]
    providers: dict = {}

    def provider_for(name: str):
        if name not in providers:
            if name == "voxtral-house":
                key = voxtral_key()
                providers[name] = (VoxtralProvider(clone_ref=str(SAMPLES / "troymcclure2.wav"),
                                                   api_key=key) if key else None)
            else:
                v = next(v for v in data["voices"] if v["name"] == name)
                providers[name] = MlxAudioProvider(url=url, model=QWEN, clone_ref=v["clip"],
                                                   clone_text=v["text"], calibration=MEASURE_CAL)
        return providers[name]

    for item in plan[len(units):]:
        if item["kind"] == "voxtral" and not use_voxtral:
            units.append({**item, "render_status": "not-measured", "stt": {},
                          "error": "--voxtral not given"})
        else:
            p = provider_for(item["voice"])
            if p is None:
                units.append({**item, "render_status": "not-measured", "stt": {},
                              "error": "no Mistral key"})
            else:
                units.append(render(item["kind"], item["voice"], p, item["text"],
                                    clips / f"{len(units):03d}-{item['kind']}-{item['voice']}.wav"))
        save(out, data)
        log(f"rendered {len(units)}/{len(plan)}")
    for p in providers.values():
        if p is not None:
            p.close()
    data["render_complete"] = True
    data["footprint"] = footprint(server_pid)
    save(out, data)


# ------------------------------------------------------- the known runaways

def known_runaways(clips: Path) -> list[dict]:
    """The bake-off's two runaways, cut out of their bed-mixed MP3s as WAVs
    under `clips` (transcribed later, by every STT model)."""
    out = []
    for slug, seg, needle in [("qwen3tts-0.6b-bf16", "set1-intro", None),
                              ("chatterbox-fp16", "set2-intro", "Here is Morning Dew.")]:
        metrics = json.loads((BAKEOFF / "out" / f"{slug}-{seg}.metrics.json").read_text())
        per_call = metrics["per_call"]  # [wall_s, audio_s] per sentence, in order
        sentences = _split_sentences((BAKEOFF / "inputs" / f"{seg}.txt").read_text())
        rec = {"slug": slug, "segment": seg, "sentence_count": len(sentences),
               "call_count": len(per_call), "stt": {}}
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
        cut = clips / f"runaway-{slug}-{seg}.wav"
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}",
                            "-t", f"{per_call[i][1]:.2f}", "-i", str(mp3), "-ac", "1",
                            "-ar", "24000", "-c:a", "pcm_s16le", str(cut)], check=True)
            rec["clip"] = str(cut)
        except (subprocess.CalledProcessError, OSError) as e:
            rec["cut_error"] = str(e)
        out.append(rec)
    return out


# ------------------------------------------------------------ transcription

@contextlib.contextmanager
def thresholds(values: dict):
    """Run emcee's own transcript_problem under `values`, then restore."""
    saved = {name: getattr(verify_mod, name) for name in THRESHOLD_NAMES}
    for name, value in values.items():
        setattr(verify_mod, name, value)
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(verify_mod, name, value)


def problem_under(values: dict, text: str, transcript: str) -> str | None:
    with thresholds(values):
        return transcript_problem(text, transcript)


def score(text: str, heard: str) -> dict:
    want, got = comparable_words(text), comparable_words(heard)
    found, missing, extra = match_words(want, got)
    return {"transcript": heard, "words": len(want), "found": found, "missing": len(want) - found,
            "extra": len(got) - len(want), "recall": round(found / len(want), 3) if want else 1.0,
            "loop": has_loop(got), "interim_problem": problem_under(INTERIM, text, heard),
            "missing_words": sorted(missing.elements()),
            "extra_words": sorted(extra.elements())}


def rescore(data: dict) -> int:
    """Re-score every saved transcript (every STT model's) with the current
    matching, without loading any model; returns how many were re-scored."""
    n = 0
    for r in data["units"] + data["runaways"]:
        for model, s in r.get("stt", {}).items():
            if "transcript" in s:
                r["stt"][model] = {**s, **score(r["text"], s["transcript"])}
                n += 1
    return n


def transcribe_pass(data: dict, out: Path, url: str, model: str, server_pid: int | None) -> None:
    """Transcribe every unit and runaway still lacking a result for `model`."""
    todo = [r for r in data["units"] + data["runaways"]
            if r.get("clip") and "transcript" not in r["stt"].get(model, {})]
    if not todo:
        return
    log(f"transcription pass {model}: {len(todo)} clips")
    stt = SttClient(url=url, model=model)
    for n, r in enumerate(todo, 1):
        t = time.time()
        try:
            heard = stt.transcribe(Path(r["clip"]).read_bytes())
            r["stt"][model] = {**score(r["text"], heard), "wall_s": round(time.time() - t, 2)}
        except (SpeechError, OSError) as e:
            r["stt"][model] = {"error": f"transcription: {e}"}
        log(f"{model.split('/')[-1]} {n}/{len(todo)} "
            f"recall {r['stt'][model].get('recall')} {r['stt'][model].get('error', '')}")
        if n % 5 == 0:
            save(out, data)
    data.setdefault("footprint_stt", {})[model] = footprint(server_pid)
    try:
        stt.unload()
        log(f"unloaded {model}")
    except SpeechError as e:
        log(f"unload {model}: {e}")
    stt.close()
    save(out, data)


def finalize(data: dict, primary: str) -> None:
    """The brief's per-unit fields, from the primary STT model; `loop` is
    a loop heard by ANY model; `status` is the render status, or `error`
    when the primary transcription failed."""
    for rows in (data["units"], data["runaways"]):
        for r in rows:
            p = r["stt"].get(primary, {})
            for k in ("transcript", "words", "missing", "extra", "recall", "interim_problem"):
                if k in p:
                    r[k] = p[k]
            if "render_status" in r:
                r["loop"] = any(s.get("loop") for s in r["stt"].values())
                r["status"] = r["render_status"]
                if r["render_status"] in ("ok", "runaway-at-measurement-cap") and "transcript" not in p:
                    r["status"] = "error"
                    r["error"] = p.get("error", "transcription: not run")


# ----------------------------------------------------------- classification

def de_doelen_only(u: dict) -> bool:
    """Every model's misses are confined to the name De Doelen (and some are)."""
    if "doelen" not in comparable_words(u.get("text", "")):
        return False
    misses = [set(s.get("missing_words", [])) for s in u["stt"].values() if "transcript" in s]
    return bool(misses) and all(m <= DE_DOELEN for m in misses) and any(misses)


def classify(units: list[dict], defects: set[int], artefacts: set[int]) -> list[dict]:
    """Number the units, flag the ones the operator must listen to, and
    classify each as a defect or not. Flagged: status not ok, a loop (any STT
    model), recall below FLAG_RECALL under ANY STT model (the flag names the
    model), or seconds per character outside FLAG_SPC times its voice's
    median. Mechanical default the operator may accept: a defect when recall
    < DEFECT_RECALL under EVERY STT model (one model hearing it is evidence
    of an STT artefact; a unit whose only misses are "De Doelen" never counts
    as low recall) or seconds per character > DEFECT_SPC times the voice's
    median. `defects`/`artefacts` (unit indices: the operator's answer)
    override the default. Returns the flagged units."""
    spc = {i: u["seconds"] / u["chars"] for i, u in enumerate(units)
           if u.get("seconds") and u.get("chars")}
    median = {v: statistics.median(x for i, x in spc.items() if units[i]["voice"] == v)
              for v in {units[i]["voice"] for i in spc}}
    flagged = []
    for i, u in enumerate(units):
        u["index"] = i
        ratio = spc[i] / median[u["voice"]] if i in spc else None
        u["spc_ratio"] = round(ratio, 3) if ratio is not None else None
        heard = {m: s for m, s in u.get("stt", {}).items() if "transcript" in s}
        recalls = [s["recall"] for s in heard.values()]
        flags = []
        if u.get("status") not in ("ok", "not-measured"):
            flags.append(u.get("status"))
        for m, s in heard.items():
            if s["loop"]:
                flags.append(f"loop ({m.split('/')[-1]})")
        for m, s in heard.items():
            if s["recall"] < FLAG_RECALL:
                flags.append(f"recall {s['recall']:.2f} ({m.split('/')[-1]})")
        if ratio is not None and not FLAG_SPC[0] <= ratio <= FLAG_SPC[1]:
            flags.append(f"{ratio:.2f}x its voice's median s/char")
        notes = [DE_DOELEN_NOTE] if de_doelen_only(u) else []
        default = ((bool(recalls) and max(recalls) < DEFECT_RECALL and not notes)
                   or (ratio is not None and ratio > DEFECT_SPC))
        u["default_defect"] = default
        u["defect"] = i in defects or (default and i not in artefacts)
        u["classified_by"] = ("operator" if i in defects or i in artefacts
                              else "mechanical default")
        u["flags"] = flags
        u["notes"] = notes
        if flags:
            flagged.append({k: u.get(k) for k in (
                "index", "kind", "voice", "text", "clip", "seconds", "chars", "spc_ratio",
                "recall", "flags", "notes", "default_defect", "defect", "classified_by")}
                | {"transcripts": {m: s["transcript"] for m, s in heard.items()},
                   "recalls": {m: s["recall"] for m, s in heard.items()}})
    return flagged


# ---------------------------------------------------------------- derivation

def ceil_to(x: float, step: float) -> float:
    return round(math.ceil(x / step - 1e-9) * step, 4)


def floor_to(x: float, step: float) -> float:
    return round(math.floor(x / step + 1e-9) * step, 4)


def is_clean(u: dict) -> bool:
    return u.get("status") == "ok" and not u.get("loop") and not u.get("defect")


def clean_for(units: list[dict], model: str, kinds=None) -> list[dict]:
    return [u for u in units if is_clean(u) and "transcript" in u["stt"].get(model, {})
            and (kinds is None or u["kind"] in kinds)]


def derive_thresholds(scored: list[dict], model: str) -> dict:
    """The verification rule, over `scored` units' results for `model`."""
    stats = [u["stt"][model] for u in scored]
    short = [s for s in stats if s["words"] < SHORT_WORDS]
    long_ = [s for s in stats if s["words"] >= SHORT_WORDS]
    return {
        "MISS_FLOOR": max(2, 1 + max((s["missing"] for s in short), default=0)),
        "MISS_FRACTION": max(0.15, ceil_to(1.5 * max((s["missing"] / s["words"] for s in long_),
                                                     default=0.0), 0.05)),
        "EXTRA_FLOOR": max(4, 1 + max((max(0, s["extra"]) for s in short), default=0)),
        "EXTRA_FRACTION": max(0.25, ceil_to(1.5 * max((max(0, s["extra"]) / s["words"]
                                                       for s in long_), default=0.0), 0.05)),
    }


def ceilings_exceeded(th: dict) -> list[str]:
    """Step 3's STOP ceilings: past these a threshold no longer detects gross mismatch."""
    out = []
    if th["MISS_FRACTION"] > 0.4:
        out.append(f"MISS_FRACTION {th['MISS_FRACTION']} > 0.4")
    if th["EXTRA_FRACTION"] > 1.0:
        out.append(f"EXTRA_FRACTION {th['EXTRA_FRACTION']} > 1.0")
    if th["MISS_FLOOR"] > 3:
        out.append(f"MISS_FLOOR {th['MISS_FLOOR']} > 3")
    if th["EXTRA_FLOOR"] > 6:
        out.append(f"EXTRA_FLOOR {th['EXTRA_FLOOR']} > 6")
    return out


def guarded(cal: ModelCalibration, u: dict) -> str | None:
    """The derived guard's verdict on a unit; None for Voxtral (no guard there)."""
    if u["kind"] not in MLX_KINDS or u.get("seconds") is None:
        return None
    return guard_problem(cal, u["text"], u["seconds"], max_tokens_for(cal, u["text"]))


def guard_checks_for(cal: ModelCalibration, mlx: list[dict], runaways: list[dict]) -> dict:
    """Step 3's guard checks: no clean mlx unit may fail; both runaways must."""
    guard_checks = {"clean_failures": [u["text"] for u in mlx if guarded(cal, u)]}
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
    return guard_checks


def recommend(units: list[dict], runaways: list[dict], models: list[str],
              max_spc_override: float | None = None) -> dict:
    """Derivation rules (the evidence doc restates them):
    clean = status ok, not a loop (under any STT model), not classified a
      defect (`classify`).
    guard -- TTS-only, computed once, over clean mlx units:
      max_floor_s = 2.0; max_s_per_char = smallest 0.005 step with every clean
        unit <= 0.8 x (max_floor_s + max_s_per_char x chars)   (25% headroom);
      min_slack_s = 0.5; min_s_per_char = largest 0.005 step with every clean
        unit >= 1.25 x (min_s_per_char x chars - min_slack_s);
      cap_s_per_char = max_s_per_char; cap_margin_s = 1.0;
      cap_floor_s = max_floor_s + 3.0  (satisfies ModelCalibration's invariant).
    verification -- PER STT MODEL, over that model's results on clean units,
      split at 8 comparable words, three ways: every clean unit (`all`, the
      recommendation), clean mlx units only, clean Voxtral units only:
      MISS_FLOOR = max(2, 1 + worst short-unit missing);
      MISS_FRACTION = max(0.15, 1.5 x worst long-unit missing/words, 0.05 steps);
      EXTRA_FLOOR = max(4, 1 + worst short-unit extra);
      EXTRA_FRACTION = max(0.25, 1.5 x worst long-unit extra/words, 0.05 steps).
    Every defect must fail the derived guard or thresholds (`defects_passing`).
    The top-level thresholds/verify_checks/defects_passing are the primary
    (first) STT model's `all` derivation; `per_stt` holds every model's."""
    mlx = [u for u in units if is_clean(u) and u["kind"] in MLX_KINDS]
    max_floor_s, min_slack_s = 2.0, 0.5
    max_spc = ceil_to(max((u["seconds"] / 0.8 - max_floor_s) / u["chars"] for u in mlx), 0.005)
    min_spc = max(0.0, floor_to(min((u["seconds"] / 1.25 + min_slack_s) / u["chars"]
                                    for u in mlx), 0.005))
    cal = ModelCalibration(frame_rate_hz=12.5, cap_floor_s=max_floor_s + 3.0,
                           cap_s_per_char=max_spc, max_floor_s=max_floor_s,
                           max_s_per_char=max_spc, min_s_per_char=min_spc,
                           min_slack_s=min_slack_s, cap_margin_s=1.0)
    guard_checks = guard_checks_for(cal, mlx, runaways)
    adopted = None
    if max_spc_override is not None:
        # An operator-approved deviation: the adopted max_s_per_char, with
        # cap_s_per_char kept equal to it as the derivation rule has it.
        acal = dataclasses.replace(cal, max_s_per_char=max_spc_override,
                                   cap_s_per_char=max_spc_override)
        adopted = {"deviation": f"max_s_per_char = cap_s_per_char = {max_spc_override} "
                                f"(derived {max_spc})",
                   "calibration": {f: getattr(acal, f) for f in acal.__dataclass_fields__},
                   "guard_checks": guard_checks_for(acal, mlx, runaways),
                   "clean_long_limit_ratio_max": round(max(
                       u["seconds"] / (acal.max_floor_s + acal.max_s_per_char * u["chars"])
                       for u in mlx), 3)}

    per_stt = {}
    for model in models:
        derived = {"all": clean_for(units, model), "mlx": clean_for(units, model, MLX_KINDS),
                   "voxtral": clean_for(units, model, ("voxtral",))}
        th = {k: derive_thresholds(v, model) for k, v in derived.items() if v}
        rec_th = th.get("all")
        if rec_th is None:
            per_stt[model] = {"thresholds": {}, "note": "no clean unit transcribed"}
            continue
        verify_checks = {
            "clean_failures": [u["text"] for u in derived["all"]
                               if problem_under(rec_th, u["text"], u["stt"][model]["transcript"])],
            **{r["slug"]: problem_under(rec_th, r["text"], r["stt"][model]["transcript"])
               for r in runaways if "transcript" in r["stt"].get(model, {})},
        }

        def caught(u: dict) -> bool:
            s = u["stt"].get(model, {})
            return bool(guarded(cal, u) or ("transcript" in s and problem_under(
                rec_th, u["text"], s["transcript"])))

        # Every unit classified as a defect must fail the derived constants.
        defects_passing = [u["index"] for u in units
                           if u.get("defect") and u.get("seconds") is not None and not caught(u)]
        per_stt[model] = {"thresholds": rec_th, "derivations": th,
                          "units_per_derivation": {k: len(v) for k, v in derived.items()},
                          "ceilings_exceeded": {k: ceilings_exceeded(v) for k, v in th.items()},
                          "verify_checks": verify_checks, "defects_passing": defects_passing}
    primary = per_stt[models[0]]
    return {"calibration": {f: getattr(cal, f) for f in cal.__dataclass_fields__},
            "guard_checks": guard_checks, "thresholds": primary.get("thresholds"),
            "verify_checks": primary.get("verify_checks"),
            "defects_passing": primary.get("defects_passing"), "per_stt": per_stt,
            "adopted_guard": adopted}


# ------------------------------------------------------------------ analysis

def describe(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    s = sorted(values)
    p90 = s[min(len(s) - 1, math.ceil(0.9 * len(s)) - 1)]  # nearest rank
    return {"n": len(s), "median": round(statistics.median(s), 3), "p90": round(p90, 3),
            "max": round(s[-1], 3)}


def rate(failed: list, total: int) -> dict:
    return {"failed": len(failed), "of": total,
            "rate": round(len(failed) / total, 3) if total else None, "units": failed}


def found_zero(u: dict, model: str) -> bool:
    s = u["stt"][model]
    return s["words"] >= 1 and s["found"] == 0


def analyse(units: list[dict], runaways: list[dict], rec: dict, models: list[str]) -> dict:
    """The STT comparison (per model, per backend): the missing/extra
    distributions on clean units; false-alarm rates (leave-one-out, interim
    thresholds, cross-backend); what verification catches that the guard
    does not; and the short-sentence analysis."""
    cal = ModelCalibration(**rec["calibration"])
    backends = {"mlx": MLX_KINDS, "voxtral": ("voxtral",)}
    out: dict = {}
    for model in models:
        if not rec["per_stt"][model].get("thresholds"):
            continue
        th = rec["per_stt"][model]["derivations"]
        clean_all = clean_for(units, model)
        m: dict = {"distributions": {}, "false_alarms": {}}
        for b, kinds in backends.items():
            cl = [u["stt"][model] for u in clean_all if u["kind"] in kinds]
            m["distributions"][b] = {
                "missing": describe([s["missing"] for s in cl]),
                "missing_per_word": describe([s["missing"] / s["words"] for s in cl if s["words"]]),
                "extra": describe([s["extra"] for s in cl]),
                "extra_per_word": describe([s["extra"] / s["words"] for s in cl if s["words"]]),
                "missing_histogram": dict(sorted(Counter(s["missing"] for s in cl).items())),
                "extra_histogram": dict(sorted(Counter(s["extra"] for s in cl).items())),
            }

        def fails(values: dict, u: dict) -> bool:
            return bool(problem_under(values, u["text"], u["stt"][model]["transcript"]))

        fa = m["false_alarms"]
        for b, kinds in backends.items():
            mine = [u for u in clean_all if u["kind"] in kinds]
            # (i) leave-one-out: thresholds derived without unit i (over every
            # clean unit, and over its own backend's), tested on unit i.
            loo_all = [u["index"] for u in mine
                       if fails(derive_thresholds([v for v in clean_all if v is not u], model), u)]
            loo_own = [u["index"] for u in mine
                       if (rest := [v for v in mine if v is not u])
                       and fails(derive_thresholds(rest, model), u)]
            fa[b] = {"loo_all_derivation": rate(loo_all, len(mine)),
                     "loo_own_backend_derivation": rate(loo_own, len(mine)),
                     # (ii) the interim thresholds
                     "interim": rate([u["index"] for u in mine if fails(INTERIM, u)], len(mine)),
                     "recommended_all": rate([u["index"] for u in mine if fails(th["all"], u)],
                                             len(mine))}
        # (iii) cross-backend
        for src, dst in (("mlx", "voxtral"), ("voxtral", "mlx")):
            if src in th:
                mine = [u for u in clean_all if u["kind"] in backends[dst]]
                fa[dst][f"{src}_derived_thresholds"] = rate(
                    [u["index"] for u in mine if fails(th[src], u)], len(mine))

        # (c) what verification catches that the derived guard does not
        def catches(values: dict) -> list[dict]:
            rows = []
            for u in units:
                s = u.get("stt", {}).get(model, {})
                if "transcript" not in s or guarded(cal, u):
                    continue
                p = problem_under(values, u["text"], s["transcript"])
                if p:
                    rows.append({"index": u["index"], "kind": u["kind"], "voice": u["voice"],
                                 "text": u["text"], "clip": u["clip"], "problem": p,
                                 "clean": is_clean(u), "defect": u.get("defect"),
                                 "transcripts": {k: v.get("transcript")
                                                 for k, v in u["stt"].items()}})
            return rows
        m["caught_not_guarded"] = {"recommended": catches(th["all"]), "interim": catches(INTERIM)}

        # R6: short sentences
        short = [u for u in units if "transcript" in u.get("stt", {}).get(model, {})
                 and u["stt"][model]["words"] <= 2]
        m["short_sentences"] = {
            "units_le_2_words": [{"index": u["index"], "kind": u["kind"], "text": u["text"],
                                  "words": u["stt"][model]["words"],
                                  "found": u["stt"][model]["found"],
                                  "transcript": u["stt"][model]["transcript"],
                                  "clean": is_clean(u)} for u in short],
            "found_zero_rule": {
                "clean_failing": [u["index"] for u in clean_all if found_zero(u, model)],
                "clean_failing_by_backend": {
                    b: rate([u["index"] for u in clean_all
                             if u["kind"] in kinds and found_zero(u, model)],
                            len([u for u in clean_all if u["kind"] in kinds]))
                    for b, kinds in backends.items()},
                "nonclean_caught": [u["index"] for u in units
                                    if not is_clean(u) and "transcript" in u.get("stt", {}).get(model, {})
                                    and found_zero(u, model)],
                "runaways_caught": [r["slug"] for r in runaways
                                    if "transcript" in r["stt"].get(model, {})
                                    and found_zero(r, model)],
            },
            "le_2_any_miss_rule": {
                "clean_failing": [u["index"] for u in clean_all
                                  if u["stt"][model]["words"] <= 2
                                  and u["stt"][model]["missing"] > 0],
            },
        }
        out[model] = m

    # per-voice duration table (guard evidence)
    spc: dict = {}
    for u in units:
        if u.get("seconds") and u.get("chars") and u.get("status") == "ok":
            spc.setdefault(u["voice"], []).append(u["seconds"] / u["chars"])
    per_voice = {v: {"units": len(x), "median_spc": round(statistics.median(x), 4),
                     "max_spc": round(max(x), 4), "min_spc": round(min(x), 4)}
                 for v, x in sorted(spc.items())}
    return {"per_stt": out, "per_voice": per_voice}


# --------------------------------------------------------------------- misc

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
    ap.add_argument("--stt-model", required=True, action="append",
                    help="repeatable; the first is the primary")
    ap.add_argument("--out", required=True)
    ap.add_argument("--voxtral", action="store_true")
    ap.add_argument("--server-pid", type=int, default=None)
    ap.add_argument("--station-root", default="/Volumes/media/lma-radio/delivered")
    ap.add_argument("--clips-dir", default=None, help="scratch dir for every unit's WAV")
    ap.add_argument("--reuse", action="store_true",
                    help="resume from --out's saved units; render only what is missing")
    ap.add_argument("--defects", default="", help="unit indices the operator heard as defects")
    ap.add_argument("--artefacts", default="", help="unit indices the operator heard as artefacts")
    ap.add_argument("--rescore", action="store_true",
                    help="with --reuse: re-score every saved transcript with the current matching")
    ap.add_argument("--max-s-per-char", type=float, default=None,
                    help="an adopted max_s_per_char (= cap_s_per_char) to re-check the guard at")
    a = ap.parse_args()
    out = Path(a.out)
    models = list(dict.fromkeys(a.stt_model))
    primary = models[0]
    if a.reuse:
        data = json.loads(out.read_text())
        if a.clips_dir:
            data["clips_dir"] = str(Path(a.clips_dir).expanduser())
    else:
        if not a.clips_dir:
            ap.error("--clips-dir is required unless --reuse")
        clips = Path(a.clips_dir).expanduser()
        clips.mkdir(parents=True, exist_ok=True)
        texts, source = script_texts(a.station_root)
        sentences, segments = pick_units(texts)
        # How common very short sentences are in production (R6), not just
        # in the sample: every distinct sentence of the source.
        lexicon = load_lexicon(HOME / ".emcee")
        corpus = sorted({s for t in texts for s in _split_sentences(normalize_for_speech(t, lexicon))})
        tiny = [s for s in corpus if len(comparable_words(s)) <= 2]
        source["sentences_total"] = len(corpus)
        source["sentences_le_2_comparable_words"] = {"count": len(tiny), "examples": tiny[:40]}
        stt = SttClient(url=a.url, model=primary)
        vs, skipped_voices = voices(stt)
        stt.close()
        unload(a.url, primary)  # free it for rendering; the transcription pass reloads it
        data = {"date": time.strftime("%Y-%m-%d"), "model": QWEN, "stt_model": primary,
                "stt_models": models, "url": a.url, "clips_dir": str(clips),
                "text_source": source, "voices": vs, "skipped_voices": skipped_voices,
                "plan": plan_units(sentences, segments, vs, a.voxtral), "units": [],
                "render_complete": False}
        save(out, data)
    data["stt_models"] = list(dict.fromkeys(data.get("stt_models", []) + models))
    data["interim_thresholds"] = INTERIM
    if not data.get("render_complete"):
        log(f"rendering {len(data['plan']) - len(data['units'])} of {len(data['plan'])} units")
        render_all(data, out, a.url, a.voxtral, a.server_pid)
        unload(a.url, QWEN)
    if "runaways" not in data:
        data["runaways"] = known_runaways(Path(data["clips_dir"]))
        save(out, data)
    for model in models:
        transcribe_pass(data, out, a.url, model, a.server_pid)
    if a.rescore:
        log(f"re-scored {rescore(data)} saved transcripts")
    finalize(data, primary)

    def indices(arg: str) -> set[int]:
        return {int(x) for x in arg.split(",") if x.strip()}

    data["flagged"] = classify(data["units"], indices(a.defects), indices(a.artefacts))
    data["recommendation"] = recommend(data["units"], data["runaways"], models,
                                       a.max_s_per_char)
    data["analysis"] = analyse(data["units"], data["runaways"], data["recommendation"], models)
    save(out, data)
    print(json.dumps({"flagged": data["flagged"], "recommendation": data["recommendation"]},
                     indent=1))


if __name__ == "__main__":
    main()
