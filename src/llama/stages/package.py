import hashlib
import io
import json
import re
import wave
from pathlib import Path

from llama.audio import packaged_filename, read_duration, tag_audio
from llama.manifest import broadcast_m3u_text, build_manifest, m3u_text
from llama.models import DJAudio, DJNotes, ManifestTrack, Show, VettingResult
from llama.speech_text import Lexicon, normalize_for_speech
from llama.status import detail
from llama.tts.provider import SpeechError
from llama.util import reviews_digest
from llama.workspace import ShowWorkspace, read_json, read_model, write_artifact

DURATION_TOLERANCE_S = 5.0

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
    import lameenc  # lazy: only the chunked path needs it

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

    pcm = b"".join(frames)
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(_bitrate_for_rate(framerate))
    encoder.set_in_sample_rate(framerate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    mp3_data = encoder.encode(pcm)
    mp3_data += encoder.flush()
    return mp3_data


def _segment_texts(notes: DJNotes) -> list[tuple[str, str]]:
    """(segment file stem, text) in broadcast order: one lead-in per set, then outro."""
    ordered = sorted(notes.set_intros, key=lambda x: (x == "encore", x))
    segs = [(f"set{key}-intro", notes.set_intros[key]) for key in ordered]
    segs.append(("99-outro", notes.outro))
    return segs


def _synthesize_dj_audio(pkg: Path, notes: DJNotes, speech, force: bool,
                         chunk: bool = False, lexicon: Lexicon | None = None) -> DJAudio:
    """One MP3 per DJNotes segment under package/dj-audio/.

    Segments are keyed by sha256(text + voice + model + chunk) in a sidecar
    map (segments.json) written with the audio; matching keys are skipped so
    a repackage never re-spends on unchanged text. force re-renders
    everything. Any provider failure propagates (SpeechError): the manifest
    is written only after this returns, so a failed run leaves no manifest
    referencing half-rendered audio.

    chunk ([tts] chunk, default off): synthesize each segment sentence-by-
    sentence and concatenate instead of one call per segment (see
    _synthesize_chunked). chunk is part of the cache key - chunked and
    single-call audio are different renders of the same text, so flipping
    [tts] chunk invalidates the affected clips and a redo re-synthesizes
    them (no --force needed).
    """
    lexicon = lexicon or Lexicon.empty()
    audio_dir = pkg / "dj-audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    sidecar = audio_dir / "segments.json"
    cached: dict[str, str] = json.loads(sidecar.read_text()) if sidecar.exists() else {}
    keys: dict[str, str] = {}
    for stem, text in _segment_texts(notes):
        spoken = normalize_for_speech(text, lexicon)
        filename = f"{stem}.mp3"
        dest = audio_dir / filename
        key = hashlib.sha256(
            f"{spoken}\n{speech.voice}\n{speech.model}\nchunk={chunk}".encode()).hexdigest()
        keys[filename] = key
        if force or not dest.exists() or cached.get(filename) != key:
            detail(f"synthesizing {filename}")
            data = _synthesize_chunked(spoken, speech) if chunk else speech.synthesize(spoken)
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(dest)
    for existing in audio_dir.glob("*.mp3"):
        if existing.name not in keys:
            detail(f"pruning orphan {existing.name}")
            existing.unlink()
    write_artifact(sidecar, json.dumps(keys, indent=2))
    return DJAudio(
        set_intros={key: f"dj-audio/set{key}-intro.mp3" for key in notes.set_intros},
        outro="dj-audio/99-outro.mp3",
    )


def run_package(show_ws: ShowWorkspace, ia, show: Show, notes: DJNotes | None = None,
                force: bool = False, speech=None, chunk: bool = False,
                lexicon: Lexicon | None = None) -> Path:
    pkg = show_ws.package_dir
    manifest_path = pkg / "manifest.json"
    if manifest_path.exists() and not force:
        return pkg

    audio_dir = pkg / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    md5s = {f["name"]: f.get("md5") for f in ia.metadata(show.identifier).get("files", [])}

    venue_city = ", ".join(p for p in [show.venue, show.city] if p)

    packaged: list[ManifestTrack] = []
    flags: list[str] = []
    for t in show.tracks:
        out_name = packaged_filename(t.index, t.title, Path(t.filename).suffix)
        dest = audio_dir / out_name
        if not dest.exists() or force:
            detail(f"downloading {t.index}/{len(show.tracks)}: {t.filename}")
            ia.download_file(show.identifier, t.filename, dest, md5=md5s.get(t.filename))
        tag_audio(
            dest,
            artist=show.artist,
            album=f"{show.date} {venue_city}".strip(),
            title=t.title, track=t.index, date=show.date, comment=show.identifier,
        )
        real = read_duration(dest)
        if real is not None and t.duration_sec is not None and abs(real - t.duration_sec) > DURATION_TOLERANCE_S:
            flags.append(f"duration mismatch on {out_name}: file {real:.0f}s vs metadata {t.duration_sec:.0f}s")
        packaged.append(ManifestTrack(index=t.index, set=t.set, title=t.title,
                                      filename=out_name,
                                      duration_sec=real if real is not None else t.duration_sec,
                                      segue=t.segue))

    context = notes.context if notes is not None else ""
    vetted = False
    if show_ws.vetting.exists():
        vr = read_model(show_ws.vetting, VettingResult)
        if vr.vetting.context:
            context = vr.vetting.context
        vetted = not vr.flags

    research_name = None
    if show_ws.research.exists():
        write_artifact(pkg / "research.md", show_ws.research.read_text())
        research_name = "research.md"
    reviews = read_json(show_ws.reviews) if show_ws.reviews.exists() else []
    write_artifact(pkg / "reviews.md", reviews_digest(reviews))

    dj_audio = None
    if speech is not None:
        if notes is None:
            raise SpeechError("voice is active but this show has no DJ script; "
                              "rerun with the script enabled")
        dj_audio = _synthesize_dj_audio(pkg, notes, speech, force, chunk=chunk, lexicon=lexicon)

    write_artifact(pkg / "playlist.m3u", m3u_text([t.filename for t in packaged]))
    if dj_audio is not None:
        # Broadcast order: DJ lead-ins/outro interleaved with the music; the
        # music-only playlist.m3u above is left untouched.
        write_artifact(pkg / "broadcast.m3u", broadcast_m3u_text(packaged, dj_audio))
    if show_ws.dj_notes_md.exists():
        write_artifact(pkg / "dj-notes.md", show_ws.dj_notes_md.read_text())
    # Manifest last: it is the package's "outputs written only on success" marker.
    write_artifact(manifest_path, build_manifest(
        show, notes, packaged, context=context,
        research=research_name, reviews="reviews.md", research_vetted=vetted,
        dj_audio=dj_audio))
    if flags:
        current = read_model(show_ws.show, Show)
        current.review_flags = current.review_flags + flags
        current.needs_review = True
        write_artifact(show_ws.show, current)
    return pkg
