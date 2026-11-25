"""`emcee pieces`: voice transmitter's announcement pieces, verified strictly.

transmitter (another host) writes `piece-<id>.txt` into a shared folder, `<id>`
being `sha256(text)[:12]`. Each pending text is voiced here on the local TTS
server, checked, and left as `piece-<id>.mp3`, or as a `piece-<id>.failed` JSON
sidecar after `max_takes` bad takes. `piece-<id>.expect` (the operator's) replaces
the text the transcript is compared with.

Files on the share the two sides must keep apart: every file written here goes
through a dot-prefixed temp (`.piece-<id>.mp3.<token>.tmp`, `.piece-<id>.failed.
<token>.tmp`) and `os.replace`, so a reader never sees a half file; only those two
temp shapes are cleaned here, never transmitter's `.piece-*.txt.*.tmp`. One run at
a time: a non-blocking flock on `<emcee root>/pieces.lock` (local disk, not the
share). No station lock: no package is touched.
"""
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from emcee.audio import _encode_mp3
from emcee.config import EmceeConfig
from emcee.piece_audio import finish_take, onset_problem, pcm_to_wav, read_wav
from emcee.presenters import load_presenter
from emcee.process import speech_for
from emcee.speech_text import load_lexicon, normalize_for_speech
from emcee.tts.provider import SpeechBlocked, SpeechDefect, SpeechError
from emcee.tts.strict_verify import strict_problem
from emcee.tts.verify import SttClient

MAX_TAKES = 4
TEMP_MAX_AGE_S = 3600.0
LOCK_NAME = "pieces.lock"

_NAME = re.compile(r"^piece-([0-9a-f]{12})\.txt$")


def piece_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class PieceFile:
    id: str
    txt: Path

    @property
    def mp3(self) -> Path:
        return self.txt.with_name(f"piece-{self.id}.mp3")

    @property
    def failed(self) -> Path:
        return self.txt.with_name(f"piece-{self.id}.failed")

    @property
    def expect(self) -> Path:
        return self.txt.with_name(f"piece-{self.id}.expect")


@dataclass
class Tally:
    voiced: int = 0
    retakes: int = 0
    failed: int = 0
    left: int = 0


def _mp3_blocks(mp3: Path) -> bool:
    """True when `mp3` means the piece is not pending: a regular non-empty file
    (voiced, as transmitter counts it) or a non-regular entry (clutter, never
    replaced). Absent or a zero-byte regular file is not blocking, so the piece
    is re-voiced over it."""
    try:
        st = mp3.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return not stat.S_ISREG(st.st_mode) or st.st_size > 0


def pending(folder: Path) -> list[PieceFile]:
    """`piece-<id>.txt` regular files with neither a non-empty `.mp3` nor a `.failed`,
    sorted by id. Anything else in the folder is clutter and never raises."""
    found = []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    for name in names:
        m = _NAME.match(name)
        if not m:
            continue
        piece = PieceFile(m.group(1), folder / name)
        try:
            if not piece.txt.is_file():
                continue
        except OSError:
            continue
        if _mp3_blocks(piece.mp3) or piece.failed.exists():
            continue
        found.append(piece)
    return sorted(found, key=lambda p: p.id)


def _speech(config: EmceeConfig, presenter_id: str):
    """The speech provider for the presenter (test seam)."""
    speech, _bed = speech_for(config, load_presenter(config.root, presenter_id))
    return speech


def _stt(config: EmceeConfig):
    """The STT client on the mlx-audio server (test seam)."""
    mlx = config.tts.mlx_audio
    return SttClient(url=mlx.url, model=mlx.stt_model, timeout_s=mlx.timeout_s)


def _write_through_temp(dest: Path, data: bytes) -> None:
    """A dot-prefixed unique temp beside `dest`, fsynced, then `os.replace`.
    Readable by the other host's user (mkstemp makes it 0600)."""
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _clean_own_temps(folder: Path, *, now: float | None = None) -> None:
    """Delete this command's own dot-temps older than an hour, never the
    `.piece-*.txt.*.tmp` that transmitter writes."""
    now = time.time() if now is None else now
    for pattern in (".piece-*.mp3.*.tmp", ".piece-*.failed.*.tmp"):
        for path in folder.glob(pattern):
            try:
                if path.is_file() and now - path.stat().st_mtime > TEMP_MAX_AGE_S:
                    path.unlink()
            except OSError:
                pass


def _read_text(piece: PieceFile) -> str | None:
    try:
        return piece.txt.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_expect(piece: PieceFile) -> str | None:
    try:
        return piece.expect.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def run_pieces(folder: Path, *, speech, stt, lexicon, max_takes: int, limit: int | None,
               echo: Callable[[str], None]) -> Tally:
    """Voice each pending piece. A `SpeechError` other than a runaway-guard
    `SpeechDefect` or `SpeechBlocked` (server or STT down, unusable WAV) propagates: the run
    aborts and the piece in hand gets no sidecar."""
    tally = Tally()
    todo = pending(folder)
    inner = getattr(speech, "inner", speech)
    done = 0
    for index, piece in enumerate(todo):
        if limit is not None and done >= limit:
            tally.left = len(todo) - index
            break
        text = _read_text(piece)
        if text is None:
            continue  # vanished (or unreadable) since the listing: not ours to judge
        if piece_id(text) != piece.id:
            echo(f"skip {piece.id}: text does not match its id")
            continue
        expect = _read_expect(piece)
        reason, transcript = "no take made", None
        voiced = False
        takes = 0
        for _ in range(max_takes):
            takes += 1
            transcript = None
            try:
                wav = inner.synthesize(normalize_for_speech(text, lexicon), "wav")
            except SpeechDefect as exc:
                reason = exc.reason
            except SpeechBlocked as exc:
                reason = f"content filter blocked the take: {exc}"
            else:
                pcm, rate = read_wav(wav)
                reason = onset_problem(pcm, rate)
                if reason is None:
                    try:
                        pcm = finish_take(pcm, rate)
                    except ValueError:
                        reason = "no speech after trim"
                if reason is None:
                    transcript = stt.transcribe(pcm_to_wav(pcm, rate))
                    reason = strict_problem(text, transcript, expect=expect)
                if reason is None:
                    _write_through_temp(piece.mp3, _encode_mp3(pcm, rate, 1))
                    voiced = True
                    break
            if takes < max_takes:
                echo(f"re-take {piece.id} ({reason})")
                tally.retakes += 1
        done += 1
        if voiced:
            tally.voiced += 1
            echo(f"voiced {piece.id}: {text}")
        else:
            payload = {"attempts": takes, "last_reason": reason,
                       "last_transcript": transcript,
                       "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            _write_through_temp(piece.failed, json.dumps(payload).encode())
            tally.failed += 1
            echo(f"failed {piece.id} after {takes} takes: {reason}")
    echo(f"voiced {tally.voiced}, re-takes {tally.retakes}, failed {tally.failed}, "
         f"left {tally.left}")
    return tally


def run_command(config: EmceeConfig, folder: Path, presenter_id: str, *, max_takes: int,
                limit: int | None, dry_run: bool, echo: Callable[[str], None],
                err: Callable[[str], None]) -> int:
    """The command body; returns the exit code."""
    if not folder.is_dir():
        err(f"error: {folder} does not exist (share not mounted?)")
        return 1
    config.root.mkdir(parents=True, exist_ok=True)
    fd = os.open(config.root / LOCK_NAME, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            echo("another emcee pieces is running")
            return 0
        todo = pending(folder)
        if not todo:
            return 0
        if dry_run:
            for piece in todo:
                try:
                    shown = piece.txt.read_bytes().decode("utf-8", errors="replace")
                except OSError:
                    continue
                echo(f"{piece.id}: {shown}")
            return 0
        if not config.tts.mlx_audio.stt_model:
            err("error: emcee pieces needs [tts.mlx_audio] stt_model for strict verification")
            return 1
        speech = stt = None
        try:
            speech = _speech(config, presenter_id)
            speech.preflight()
            stt = _stt(config)
            _clean_own_temps(folder)
            run_pieces(folder, speech=speech, stt=stt, lexicon=load_lexicon(config.root),
                       max_takes=max_takes, limit=limit, echo=echo)
        except SpeechError as exc:
            err(f"error: {exc}")
            for line in getattr(exc, "details", []):
                err(f"  {line}")
            return 1
        except OSError as exc:
            err(f"error: {exc}")
            return 1
        finally:
            for closer in (stt, speech):
                close = getattr(closer, "close", None)
                if close:
                    try:
                        close()
                    except Exception:
                        pass
        return 0
    finally:
        os.close(fd)
