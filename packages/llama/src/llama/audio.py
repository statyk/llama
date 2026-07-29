import re
from pathlib import Path

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import COMM, ID3, TALB, TDRC, TIT2, TPE1, TRCK

_UNSAFE = re.compile(r'[\\/:*?"<>|]+')


def packaged_filename(index: int, title: str, ext: str) -> str:
    safe = _UNSAFE.sub("_", title).strip().strip(".")
    safe = re.sub(r"\s+", " ", safe).strip("_ ") or "untitled"
    return f"{index:02d} - {safe}{ext}"


def tag_audio(path: Path, *, artist: str, album: str, title: str, track: int, date: str, comment: str) -> None:
    if path.suffix.lower() == ".flac":
        f = FLAC(path)
        f["artist"], f["album"], f["title"] = artist, album, title
        f["tracknumber"], f["date"], f["comment"] = str(track), date, comment
        f.save()
        return
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    tags.add(TRCK(encoding=3, text=str(track)))
    tags.add(TDRC(encoding=3, text=date))
    tags.add(COMM(encoding=3, lang="eng", desc="", text=comment))
    tags.save(path, v2_version=3)


def read_duration(path: Path) -> float | None:
    try:
        f = mutagen.File(path)
    except Exception:
        return None
    if f is None or f.info is None:
        return None
    return float(f.info.length)
