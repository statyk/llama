"""Concatenate an m3u playlist's entries into one mp3.

A show package holds many audio files plus an m3u naming their play order
(`package/playlist.m3u` from llama, `broadcast.m3u` from emcee). This is a
generic m3u tool for the cases that want one mp3 instead of a directory plus
a playlist: archiving an aired broadcast, handing someone a single file,
auditioning a whole show. It merely knows how to take advantage of a llama
`manifest.json` when one happens to sit next to the playlist; it does not
import llama, emcee, or herder.

Usage:
  python3 scripts/stitch_m3u.py PLAYLIST.m3u
          [-o OUT.mp3] [--title T] [--artist A] [--album AL]
          [--bitrate 192k] [--reencode] [--force]
          [--ffmpeg PATH] [--ffprobe PATH]

Stream-copy is used when every entry is mp3 with a uniform sample rate and
channel count (a lossless splice); otherwise the entries are re-encoded.
`--reencode` forces the re-encode path.

Known limitations:
  - mp3 stream-copy concatenation is not gapless: encoder delay and padding
    at each join are inherent to the format. The re-encode route removes the
    interior joins but re-encodes already-lossy audio.
  - Chapter offsets derive from probed durations, so on the re-encode route
    they can drift a few milliseconds from true positions.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Stdlib only: this script ships standalone, with no packaging and no
# dependency on the llama/emcee/herder packages in this repo.


class StitchError(Exception):
    """A user-facing error. `main` prints its message to stderr and exits 1."""


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class M3UEntry:
    path: Path
    extinf_title: str | None = None


@dataclass
class Probe:
    path: Path
    duration_sec: float
    codec_name: str
    sample_rate: int
    channels: int
    title: str | None = None
    artist: str | None = None


@dataclass
class Metadata:
    title: str | None
    artist: str | None
    album: str | None
    chapter_titles: list[str]  # one per entry, same order


# ---------------------------------------------------------------------------
# 1. Parse the playlist
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")


def parse_m3u(text: str, playlist_dir: Path) -> list[M3UEntry]:
    """Parse m3u text into ordered entries.

    Blank lines and `#` comments are skipped, except `#EXTINF:<seconds>,
    <title>` — its title applies to the next entry. Relative paths resolve
    against `playlist_dir`; absolute paths are used as-is. A remote (URL)
    entry or an empty playlist is a StitchError.
    """
    text = text.lstrip("﻿")
    entries: list[M3UEntry] = []
    pending_title: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            _, _, rest = line.partition(",")
            pending_title = rest.strip() or None
            continue
        if line.startswith("#"):
            continue  # #EXTM3U and any other directive/comment
        if _URL_RE.match(line):
            raise StitchError(f"remote playlist entries are not supported: {line}")
        path = Path(line)
        if not path.is_absolute():
            path = playlist_dir / path
        entries.append(M3UEntry(path=path, extinf_title=pending_title))
        pending_title = None
    if not entries:
        raise StitchError("playlist has no entries")
    return entries


# ---------------------------------------------------------------------------
# 2. Probe every entry
# ---------------------------------------------------------------------------

def probe_entry(ffprobe: str, path: Path) -> Probe:
    """Run ffprobe on one entry and collect duration/codec/tags. Raises
    StitchError naming `path` on any failure — a missing file, a probe
    failure, no audio stream, or no duration."""
    if not path.is_file():
        raise StitchError(f"missing file: {path}")
    cmd = [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except OSError as e:
        raise StitchError(f"ffprobe failed on {path}: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise StitchError(f"ffprobe timed out on {path}: {e}") from e
    if proc.returncode != 0:
        raise StitchError(f"ffprobe failed on {path}: {proc.stderr.strip()[:500]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise StitchError(f"ffprobe produced unreadable output for {path}: {e}") from e

    audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio_streams:
        raise StitchError(f"no audio stream in {path}")
    stream = audio_streams[0]
    fmt = data.get("format", {})
    duration = _probed_duration(fmt, stream)
    if duration is None:
        raise StitchError(f"no duration for {path}")

    fmt_tags = fmt.get("tags", {}) or {}
    stream_tags = stream.get("tags", {}) or {}
    # Prefer stream-level tags (mp3 ID3 usually surfaces here) over format-level.
    title = stream_tags.get("title") or fmt_tags.get("title")
    artist = stream_tags.get("artist") or fmt_tags.get("artist")

    return Probe(
        path=path,
        duration_sec=duration,
        codec_name=stream.get("codec_name", ""),
        sample_rate=int(stream.get("sample_rate") or 0),
        channels=int(stream.get("channels") or 0),
        title=title,
        artist=artist,
    )


def _probed_duration(fmt: dict, stream: dict) -> float | None:
    for source in (fmt, stream):
        raw = source.get("duration")
        if raw in (None, "N/A"):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


# ---------------------------------------------------------------------------
# 3. Resolve metadata
# ---------------------------------------------------------------------------

def can_stream_copy(probes: list[Probe]) -> bool:
    """True when every entry is mp3 with an identical sample rate and
    channel count, so ffmpeg can concat them without decoding."""
    if not probes:
        return False
    codecs = {p.codec_name for p in probes}
    rates = {p.sample_rate for p in probes}
    channels = {p.channels for p in probes}
    return codecs == {"mp3"} and len(rates) == 1 and len(channels) == 1


def _join_parts(parts: list[str | None]) -> str | None:
    kept = [p for p in parts if p]
    return " — ".join(kept) if kept else None


def resolve_metadata(
    entries: list[M3UEntry],
    probes: list[Probe],
    manifest: dict | None,
    *,
    title: str | None,
    artist: str | None,
    album: str | None,
    playlist_stem: str,
) -> Metadata:
    """Derive tags and per-chapter titles. Explicit CLI flags (`title`/
    `artist`/`album`) always win. `manifest` is the parsed contents of a
    llama `manifest.json`, or None when absent/unusable — only a v3+
    manifest contributes anything.

    Per-chapter titles use this cascade: manifest track title for the
    entry's basename -> the entry's own embedded title tag -> the #EXTINF
    title -> the filename stem. Entries with no manifest track (e.g.
    emcee's dj-audio/ clips in a broadcast.m3u) chapter under their stem.
    """
    derived_artist = derived_album = derived_title = None
    track_titles: dict[str, str] = {}
    if manifest is not None and isinstance(manifest.get("schema_version"), int) and manifest["schema_version"] >= 3:
        show = manifest.get("show") or {}
        derived_artist = show.get("artist") or None
        derived_album = _join_parts([show.get("date"), show.get("venue")])
        derived_title = _join_parts([show.get("artist"), show.get("date")])
        for track in manifest.get("tracks", []) or []:
            fname, ttitle = track.get("filename"), track.get("title")
            if fname and ttitle:
                track_titles[fname] = ttitle

    chapter_titles = []
    for entry, probe in zip(entries, probes):
        chapter_titles.append(
            track_titles.get(entry.path.name)
            or probe.title
            or entry.extinf_title
            or entry.path.stem
        )

    return Metadata(
        title=title or derived_title or playlist_stem,
        artist=artist or derived_artist,
        album=album or derived_album,
        chapter_titles=chapter_titles,
    )


# ---------------------------------------------------------------------------
# 5. Chapters and tags / concat list
# ---------------------------------------------------------------------------

def _escape_ffmetadata(value: str) -> str:
    """FFMETADATA1 escaping: '=', ';', '#', '\\' and newlines are prefixed
    with a backslash."""
    out = []
    for ch in value:
        if ch in "=;#\\\n":
            out.append("\\")
        out.append(ch)
    return "".join(out)


def build_ffmetadata(tags: dict[str, str], durations_sec: list[float], chapter_titles: list[str]) -> str:
    """Render an FFMETADATA1 document: file-level tags first, then one
    [CHAPTER] block per entry at TIMEBASE=1/1000, with integer-millisecond
    start/end from cumulative durations (chapter N's END is chapter N+1's
    START)."""
    lines = [";FFMETADATA1"]
    for key, value in tags.items():
        if value:
            lines.append(f"{key}={_escape_ffmetadata(str(value))}")
    cursor_ms = 0
    for duration_sec, chapter_title in zip(durations_sec, chapter_titles):
        start_ms = cursor_ms
        end_ms = start_ms + round(duration_sec * 1000)
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            f"title={_escape_ffmetadata(chapter_title)}",
        ]
        cursor_ms = end_ms
    return "\n".join(lines) + "\n"


def _escape_concat_path(path: Path) -> str:
    # ffmpeg concat-list quoting: a single quote closes the quoted string,
    # so an interior one is escaped as close-quote, escaped-literal-quote,
    # reopen-quote: '\''
    return str(path.resolve()).replace("'", "'\\''")


def build_concat_list(paths: list[Path]) -> str:
    """Render an ffmpeg concat-demuxer list: one `file '<abs-path>'` line
    per entry, in order, using absolute resolved paths."""
    return "\n".join(f"file '{_escape_concat_path(p)}'" for p in paths) + "\n"


# ---------------------------------------------------------------------------
# Binary resolution
# ---------------------------------------------------------------------------

def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _resolve_named(arg: str | None, name: str, flag: str, which) -> str:
    if arg is not None:
        if not _is_executable(Path(arg)):
            raise StitchError(f"{flag} {arg!r} is not an executable file")
        return arg
    found = which(name)
    if not found:
        raise StitchError(f"{name} not found on PATH; pass {flag} to name it explicitly")
    return found


def resolve_binaries(ffmpeg_arg: str | None, ffprobe_arg: str | None, which=shutil.which) -> tuple[str, str]:
    """Resolve the ffmpeg/ffprobe executables to invoke.

    Each defaults to a PATH lookup. If `--ffmpeg` is given without
    `--ffprobe`, ffprobe is looked for in the same directory as the given
    ffmpeg first, then falls back to PATH. `which` is injectable so this
    stays testable without touching the real PATH.
    """
    ffmpeg = _resolve_named(ffmpeg_arg, "ffmpeg", "--ffmpeg", which)

    if ffprobe_arg is not None:
        ffprobe = _resolve_named(ffprobe_arg, "ffprobe", "--ffprobe", which)
    elif ffmpeg_arg is not None:
        sibling_name = "ffprobe.exe" if ffmpeg_arg.endswith(".exe") else "ffprobe"
        sibling = Path(ffmpeg_arg).parent / sibling_name
        if _is_executable(sibling):
            ffprobe = str(sibling)
        else:
            found = which("ffprobe")
            if not found:
                raise StitchError(
                    "ffprobe not found next to the given --ffmpeg and not on PATH; pass --ffprobe explicitly")
            ffprobe = found
    else:
        found = which("ffprobe")
        if not found:
            raise StitchError("ffprobe not found on PATH; pass --ffprobe to name it explicitly")
        ffprobe = found

    return ffmpeg, ffprobe


# ---------------------------------------------------------------------------
# ffmpeg invocation
# ---------------------------------------------------------------------------

def _ffmpeg_base(ffmpeg: str) -> list[str]:
    """Flags common to both routes. Quieting ffmpeg is what makes the stderr
    tail surfaced on failure readable — with the banner and per-input dumps
    left on, a real error scrolls off the end of a many-track run."""
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]


def _build_copy_cmd(ffmpeg: str, concat_path: Path, metadata_path: Path, output: Path) -> list[str]:
    return [
        *_ffmpeg_base(ffmpeg),
        "-f", "concat", "-safe", "0", "-i", str(concat_path),
        "-i", str(metadata_path),
        "-map_metadata", "1",
        "-c", "copy",
        "-id3v2_version", "3",
        "-f", "mp3",  # the partial output name doesn't end in .mp3; name the muxer explicitly
        str(output),
    ]


def _build_reencode_cmd(ffmpeg: str, paths: list[Path], metadata_path: Path, bitrate: str, output: Path) -> list[str]:
    n = len(paths)
    inputs = []
    for path in paths:
        inputs += ["-i", str(path)]
    inputs += ["-i", str(metadata_path)]
    # Normalizing each stream to a common rate/layout first is what lets
    # `concat` accept heterogeneous inputs.
    per_stream = ";".join(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}]" for i in range(n))
    concat = "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[outa]"
    return [
        *_ffmpeg_base(ffmpeg),
        *inputs,
        "-filter_complex", f"{per_stream};{concat}",
        "-map", "[outa]",
        "-map_metadata", str(n),
        "-c:a", "libmp3lame", "-b:a", bitrate,
        "-id3v2_version", "3",
        "-f", "mp3",  # the partial output name doesn't end in .mp3; name the muxer explicitly
        str(output),
    ]


def _load_manifest(playlist_dir: Path) -> dict | None:
    manifest_path = playlist_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None  # not a usable manifest; proceed as if absent


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Concatenate an m3u playlist's entries into one mp3, with per-entry chapters and tags.")
    parser.add_argument("playlist", type=Path, help="m3u playlist to stitch")
    parser.add_argument("-o", "--output", type=Path, default=None,
                         help="output mp3 path (default: <playlist-stem>.mp3 beside the playlist)")
    parser.add_argument("--title", help="override the derived/fallback title")
    parser.add_argument("--artist", help="override the derived artist")
    parser.add_argument("--album", help="override the derived album")
    parser.add_argument("--bitrate", default="192k", help="re-encode bitrate (default 192k)")
    parser.add_argument("--reencode", action="store_true", help="force re-encoding even if stream-copy is eligible")
    parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    parser.add_argument("--ffmpeg", help="path to the ffmpeg binary (default: PATH lookup)")
    parser.add_argument("--ffprobe", help="path to the ffprobe binary (default: sibling of --ffmpeg, then PATH)")
    return parser


def _run(args: argparse.Namespace) -> None:
    playlist_path = args.playlist.resolve()
    if not playlist_path.is_file():
        raise StitchError(f"playlist not found: {playlist_path}")
    playlist_dir = playlist_path.parent

    output = (args.output or playlist_dir / f"{playlist_path.stem}.mp3").resolve()
    if output.exists() and not args.force:
        raise StitchError(f"{output} already exists; pass --force to overwrite")
    if not output.parent.is_dir():
        raise StitchError(f"output directory does not exist: {output.parent}")

    ffmpeg, ffprobe = resolve_binaries(args.ffmpeg, args.ffprobe)

    text = playlist_path.read_text(encoding="utf-8")
    entries = parse_m3u(text, playlist_dir)

    # Probe everything before touching ffmpeg: the run either produces a
    # complete output or produces nothing, never a silently short one.
    probes = [probe_entry(ffprobe, entry.path) for entry in entries]

    manifest = _load_manifest(playlist_dir)
    metadata = resolve_metadata(
        entries, probes, manifest,
        title=args.title, artist=args.artist, album=args.album,
        playlist_stem=playlist_path.stem,
    )

    reencode = args.reencode or not can_stream_copy(probes)
    print(f"route: {'re-encode' if reencode else 'stream-copy (lossless splice)'}")

    tags = {"title": metadata.title, "artist": metadata.artist, "album": metadata.album}
    durations = [p.duration_sec for p in probes]
    ffmetadata_text = build_ffmetadata(tags, durations, metadata.chapter_titles)

    with tempfile.TemporaryDirectory(prefix="stitch_m3u-") as tmp:
        tmp_dir = Path(tmp)
        metadata_path = tmp_dir / "ffmetadata.txt"
        metadata_path.write_text(ffmetadata_text, encoding="utf-8")

        if reencode:
            cmd = _build_reencode_cmd(ffmpeg, [e.path for e in entries], metadata_path, args.bitrate,
                                       output.parent / f"{output.name}.partial-{os.getpid()}")
        else:
            concat_path = tmp_dir / "concat.txt"
            concat_path.write_text(build_concat_list([e.path for e in entries]), encoding="utf-8")
            cmd = _build_copy_cmd(ffmpeg, concat_path, metadata_path,
                                   output.parent / f"{output.name}.partial-{os.getpid()}")

        partial = Path(cmd[-1])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except OSError as e:
            raise StitchError(f"ffmpeg invocation failed: {e}") from e
        except subprocess.TimeoutExpired as e:
            raise StitchError(f"ffmpeg timed out: {e}") from e

        if proc.returncode != 0:
            partial.unlink(missing_ok=True)
            tail = "\n".join(proc.stderr.strip().splitlines()[-20:])
            raise StitchError(f"ffmpeg exited {proc.returncode}:\n{tail}")

        partial.replace(output)

    print(f"wrote {output}")


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        _run(args)
    except StitchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
