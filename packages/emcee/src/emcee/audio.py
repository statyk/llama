"""Spoken DJ-audio synthesis + broadcast playlist assembly.

Port of the speech half of llama's `stages/package.py` (chunked-synthesis
sentence splitting, bed mixing, per-segment caching, `_synthesize_dj_audio`)
plus llama's `manifest.py` playlist helpers (`m3u_text`,
`interleave_broadcast`, `broadcast_m3u_text`) -- re-addressed to emcee's
`ScriptNotes`/`DJAudioBlock` models and to a manifest `tracks: list[dict]`
slice instead of llama's `ManifestTrack`/`DJAudio` models. emcee never
imports llama, so this is a text port, not a shared dependency.
"""

import hashlib
import io
import json
import re
import wave
from pathlib import Path

import typer

from emcee.models import DJAudioBlock, ScriptNotes
from emcee.speech_text import Lexicon, normalize_for_speech
from emcee.tts.bed import Bed, load_bed_pcm, mix_bed
from emcee.tts.provider import SpeechError
from emcee.workspace import atomic_write_bytes, atomic_write_text


def detail(text: str) -> None:
    """Plain progress line for the audio pipeline.

    llama's `detail()` (`llama.status`) is a TTY-aware progress printer tied
    to its multi-stage step machinery, which emcee has no equivalent of --
    emcee is a single-purpose orchestrator, not a staged pipeline with a
    step/status subsystem to hook into. This is a deliberately minimal
    stand-in: just echo the line via typer so the ported call sites
    (`_synthesize_dj_audio`'s "synthesizing ..." / "pruning orphan ..."
    lines) stay verbatim and the port stays line-for-line comparable to
    llama's source. Building a status/step subsystem for this is out of
    scope.
    """
    typer.echo(text)


# --- Sentence-level chunked synthesis ([tts] chunk, default off) ---------
# Synthesizes each DJ-notes segment sentence-by-sentence instead of one call
# for the whole segment, then concatenates the raw PCM and encodes a single
# MP3. This noticeably improves prosody/pacing on longer patter (a single
# long TTS call tends to rush or flatten out); the cost is more provider
# round-trips per segment. Gated off by default; does not affect the
# default (whole-segment) path at all.

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "jr.", "sr.",
                   "mt.", "ft.", "etc.", "inc.", "co.", "ave."}
_MIN_FRAGMENT_LEN = 20
_SILENCE_MS = 180


def _split_sentences(text: str) -> list[str]:
    """Pragmatic sentence splitter: split on .!? + whitespace, but don't
    split after common abbreviations, single-letter initials, or decimals
    (a digit immediately before/after the break). Short fragments (< ~20
    chars, e.g. "Dr." mis-split, or "Wow!" before a stray break) are merged
    with an adjacent sentence: a short *previous* chunk absorbs the next part,
    and a short *current* part (including a short trailing one like "Here's
    set two.") folds back into the previous chunk. The latter matters because
    a tiny, context-free fragment synthesized as its own TTS clip makes the
    backend hallucinate phoneme salad. Not linguistically rigorous - good
    enough for DJ patter, not a general-purpose sentence segmenter.
    """
    raw_parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text.strip()) if p.strip()]
    sentences: list[str] = []
    for part in raw_parts:
        if sentences:
            prev = sentences[-1]
            prev_last_word = prev.rsplit(None, 1)[-1].lower() if prev else ""
            is_abbrev = prev_last_word in _ABBREVIATIONS
            is_initial = (len(prev_last_word) == 2 and prev_last_word[0].isalpha()
                         and prev_last_word[1] == ".")
            is_decimal = prev_last_word[:-1].isdigit() and part[:1].isdigit()
            too_short = len(prev) < _MIN_FRAGMENT_LEN or len(part) < _MIN_FRAGMENT_LEN
            if is_abbrev or is_initial or is_decimal or too_short:
                sentences[-1] = f"{prev} {part}"
                continue
        sentences.append(part)
    return sentences or [text.strip()]


def _bitrate_for_rate(framerate: int) -> int:
    """LAME bitrate for a given PCM sample rate, tuned for mono speech.

    Voxtral (and our ElevenLabs pcm_* mirror) return 24kHz mono - an
    MPEG-2 "half rate". Hardcoding 128kbps regardless of rate produces an
    unusual 128kbps@24kHz combination that has been observed to make
    ffmpeg/mplayer emit `[mp3float] overread ... enddists` warnings on the
    resulting clips (cosmetic - the audio plays fine - but not what we want
    shipping to air). Scaling the bitrate down for lower sample rates avoids
    the odd combination; 64kbps is ample for a 24kHz mono speech stream.
    """
    if framerate <= 24000:
        return 64
    if framerate <= 32000:
        return 96
    return 128


def _encode_mp3(pcm: bytes, framerate: int, channels: int) -> bytes:
    """Encode raw int16 PCM to MP3 via lameenc (mono-speech bitrate by rate)."""
    import lameenc  # lazy: only the PCM paths need it
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(_bitrate_for_rate(framerate))
    encoder.set_in_sample_rate(framerate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    return encoder.encode(pcm) + encoder.flush()


def _chunked_pcm(text: str, speech) -> tuple[bytes, int, int]:
    """Sentence-by-sentence synthesis + PCM concat (no encode). Returns
    (pcm, framerate, channels). See _synthesize_chunked for the rationale;
    this is its PCM half, shared with the bed path."""
    sentences = _split_sentences(text)
    frames: list[bytes] = []
    framerate = channels = sampwidth = None
    for i, sentence in enumerate(sentences):
        # Give each chunk its neighbors as context so a context-aware backend
        # (ElevenLabs) keeps prosody continuous across the boundary; backends
        # without such a field (Voxtral) ignore these.
        previous_text = sentences[i - 1] if i > 0 else None
        next_text = sentences[i + 1] if i < len(sentences) - 1 else None
        wav_bytes = speech.synthesize(sentence, fmt="wav",
                                      previous_text=previous_text, next_text=next_text)
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            if framerate is None:
                framerate, channels, sampwidth = w.getframerate(), w.getnchannels(), w.getsampwidth()
                if sampwidth != 2:
                    raise SpeechError(
                        f"chunked synthesis requires 16-bit PCM audio from the speech "
                        f"backend, got {sampwidth * 8}-bit (lameenc only accepts int16 "
                        "samples)")
            frames.append(w.readframes(w.getnframes()))
        if i < len(sentences) - 1:
            silence_frames = int(framerate * (_SILENCE_MS / 1000))
            frames.append(bytes(silence_frames * channels * sampwidth))
    return b"".join(frames), framerate, channels


def _synthesize_chunked(text: str, speech) -> bytes:
    """Sentence-by-sentence synthesis + PCM concat + single MP3 encode.

    Splits `text`, synthesizes each sentence as WAV (fmt="wav"), concatenates
    the raw PCM frames with ~180ms of inserted silence between sentences,
    then encodes the whole thing to MP3 once via lameenc. Concatenating raw
    PCM (rather than stitching MP3 files) avoids frame-boundary/join
    artifacts between clips.

    NOTE on the bitrate choice: _bitrate_for_rate's mapping is a best-effort
    fix based on standard LAME/MPEG rate-family guidance (matching the
    bitrate family to the sample rate), not confirmed against a real
    `ffmpeg -v error` pass on live chunked audio (no network in the build
    sandbox). The owner should verify a real chunked run comes back clean;
    if warnings persist, the documented next step is resampling to 44.1kHz
    or 48kHz (an MPEG-1 rate) before encoding - out of scope here.
    """
    pcm, framerate, channels = _chunked_pcm(text, speech)
    return _encode_mp3(pcm, framerate, channels)


def _segment_pcm(text: str, speech, chunk: bool) -> tuple[bytes, int, int]:
    """One DJ segment's voice as raw int16 PCM (pcm, framerate, channels),
    from either the chunked concat or a single whole-segment fmt='wav' call.
    Used by the bed path, which needs PCM to mix before encoding."""
    if chunk:
        return _chunked_pcm(text, speech)
    wav_bytes = speech.synthesize(text, fmt="wav")
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        if w.getsampwidth() != 2:
            raise SpeechError(
                f"bed mixing requires 16-bit PCM audio from the speech backend, "
                f"got {w.getsampwidth() * 8}-bit")
        return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()


def _segment_texts(notes: ScriptNotes) -> list[tuple[str, str]]:
    """(segment file stem, text) in broadcast order: one lead-in per set, then outro."""
    ordered = sorted(notes.set_intros, key=lambda x: (x == "encore", x))
    segs = [(f"set{key}-intro", notes.set_intros[key]) for key in ordered]
    segs.append(("99-outro", notes.outro))
    return segs


def _synthesize_dj_audio(pkg: Path, notes: ScriptNotes, speech, force: bool,
                         chunk: bool = False, lexicon: Lexicon | None = None,
                         bed: Bed | None = None) -> DJAudioBlock:
    """One MP3 per ScriptNotes segment under package/dj-audio/.

    Segments are keyed by sha256(the speech-normalized text + voice + model +
    chunk [+ bed]) in a sidecar map (segments.json) written with the audio;
    matching keys are skipped so a repackage never re-spends on unchanged
    text — and editing the pronunciation lexicon or symbol rules also
    invalidates just the affected clips. force re-renders
    everything. Any provider failure propagates (SpeechError): the manifest
    is written only after this returns, so a failed run leaves no manifest
    referencing half-rendered audio.

    chunk ([tts] chunk, default off): synthesize each segment sentence-by-
    sentence and concatenate instead of one call per segment (see
    _synthesize_chunked). chunk is part of the cache key - chunked and
    single-call audio are different renders of the same text, so flipping
    [tts] chunk invalidates the affected clips and a redo re-synthesizes
    them (no --force needed).

    bed (opt-in instrumental bed mixed under the voice, [tts] bed /
    Presenter.bed): when active, the bed PCM is loaded once and mixed under
    each segment's voice PCM before a single MP3 encode (see _segment_pcm /
    mix_bed). The bed's content hash + gain are folded into the cache key so
    changing the bed file or its gain re-renders affected clips; a no-bed
    run's key is unaffected (see bed_key below), so existing no-bed caches
    stay valid.
    """
    lexicon = lexicon or Lexicon.empty()
    audio_dir = pkg / "dj-audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    sidecar = audio_dir / "segments.json"
    cached: dict[str, str] = json.loads(sidecar.read_text()) if sidecar.exists() else {}
    keys: dict[str, str] = {}
    bed_pcm = bed_rate = None
    bed_key = ""
    if bed is not None:
        bed_pcm, bed_rate, _, _ = load_bed_pcm(bed.path)
        bed_key = f"\nbed={hashlib.sha256(bed_pcm).hexdigest()[:16]}:{bed.gain_db}"
    for stem, text in _segment_texts(notes):
        spoken = normalize_for_speech(text, lexicon)
        filename = f"{stem}.mp3"
        dest = audio_dir / filename
        key = hashlib.sha256(
            f"{spoken}\n{speech.voice}\n{speech.model}\nchunk={chunk}{bed_key}".encode()
        ).hexdigest()
        keys[filename] = key
        if force or not dest.exists() or cached.get(filename) != key:
            detail(f"synthesizing {filename}")
            if bed is not None:
                pcm, rate, channels = _segment_pcm(spoken, speech, chunk)
                if rate != bed_rate:
                    raise SpeechError(
                        f"bed music sample rate {bed_rate}Hz does not match the "
                        f"voice audio ({rate}Hz)")
                if channels != 1:
                    raise SpeechError("bed mixing requires mono voice audio")
                data = _encode_mp3(mix_bed(pcm, bed_pcm, rate, gain_db=bed.gain_db),
                                   rate, channels)
            elif chunk:
                data = _synthesize_chunked(spoken, speech)
            else:
                data = speech.synthesize(spoken)
            atomic_write_bytes(dest, data)
    for existing in audio_dir.glob("*.mp3"):
        if existing.name not in keys:
            detail(f"pruning orphan {existing.name}")
            existing.unlink()
    atomic_write_text(sidecar, json.dumps(keys, indent=2))
    return DJAudioBlock(
        set_intros={key: f"dj-audio/set{key}-intro.mp3" for key in notes.set_intros},
        outro="dj-audio/99-outro.mp3",
    )


# --- Broadcast playlist assembly, ported from llama's manifest.py --------
# emcee has no `Manifest`/`ManifestTrack` model (package_io never round-trips
# the whole manifest -- see its module docstring), so these take a plain
# `tracks: list[dict]` slice straight from the manifest JSON instead of
# llama's `ManifestTrack` objects: `t.set` -> `t["set"]`,
# `t.filename` -> `t["filename"]`.


def m3u_text(filenames: list[str]) -> str:
    return "\n".join(["#EXTM3U", *[f"audio/{name}" for name in filenames]]) + "\n"


def interleave_broadcast(tracks: list[dict], dj_audio: DJAudioBlock) -> list[str]:
    """Package-relative paths in broadcast order: each set's lead-in before
    that set's first track, then the tracks, then dj_audio.outro after the
    last one. An encore set has no key in set_intros and so gets no lead-in —
    it plays straight into the outro. Music paths are `audio/<file>`; the
    dj_audio paths already carry their own `dj-audio/` prefix.
    """
    paths: list[str] = []
    seen: set[str] = set()
    for t in tracks:
        if t["set"] not in seen:
            seen.add(t["set"])
            intro = dj_audio.set_intros.get(t["set"])
            if intro:
                paths.append(intro)
        paths.append(f"audio/{t['filename']}")
    paths.append(dj_audio.outro)
    return paths


def broadcast_m3u_text(tracks: list[dict], dj_audio: DJAudioBlock) -> str:
    return "\n".join(["#EXTM3U", *interleave_broadcast(tracks, dj_audio)]) + "\n"
