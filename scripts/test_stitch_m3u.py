"""Tests for scripts/stitch_m3u.py.

`scripts/` has no __init__.py and is not on sys.path by default, so this
module inserts its own directory before importing its sibling.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

import stitch_m3u as sm

# ---------------------------------------------------------------------------
# parse_m3u
# ---------------------------------------------------------------------------

def test_parse_m3u_skips_blank_and_comment_lines():
    text = "#EXTM3U\n\n# a comment\naudio/one.mp3\n"
    entries = sm.parse_m3u(text, Path("/pkg"))
    assert [e.path for e in entries] == [Path("/pkg/audio/one.mp3")]


def test_parse_m3u_extinf_title_applies_to_next_entry():
    text = "#EXTINF:120,Morning Dew\naudio/01.mp3\naudio/02.mp3\n"
    entries = sm.parse_m3u(text, Path("/pkg"))
    assert entries[0].extinf_title == "Morning Dew"
    assert entries[1].extinf_title is None


def test_parse_m3u_relative_paths_resolve_against_playlist_dir():
    entries = sm.parse_m3u("sub/track.mp3\n", Path("/some/dir"))
    assert entries[0].path == Path("/some/dir/sub/track.mp3")


def test_parse_m3u_absolute_paths_used_as_is():
    entries = sm.parse_m3u("/elsewhere/track.mp3\n", Path("/some/dir"))
    assert entries[0].path == Path("/elsewhere/track.mp3")


def test_parse_m3u_strips_bom():
    text = "﻿#EXTM3U\naudio/one.mp3\n"
    entries = sm.parse_m3u(text, Path("/pkg"))
    assert len(entries) == 1


def test_parse_m3u_empty_playlist_is_an_error():
    with pytest.raises(sm.StitchError):
        sm.parse_m3u("#EXTM3U\n\n# nothing here\n", Path("/pkg"))


def test_parse_m3u_rejects_remote_url():
    with pytest.raises(sm.StitchError):
        sm.parse_m3u("http://example.com/track.mp3\n", Path("/pkg"))


# ---------------------------------------------------------------------------
# can_stream_copy
# ---------------------------------------------------------------------------

def _probe(codec="mp3", rate=44100, channels=2, path="a.mp3"):
    return sm.Probe(path=Path(path), duration_sec=1.0, codec_name=codec, sample_rate=rate, channels=channels)


def test_can_stream_copy_true_for_uniform_mp3():
    assert sm.can_stream_copy([_probe(), _probe(path="b.mp3")]) is True


def test_can_stream_copy_false_for_mixed_sample_rate():
    assert sm.can_stream_copy([_probe(rate=44100), _probe(rate=22050)]) is False


def test_can_stream_copy_false_for_mixed_channels():
    assert sm.can_stream_copy([_probe(channels=2), _probe(channels=1)]) is False


def test_can_stream_copy_false_for_non_mp3():
    assert sm.can_stream_copy([_probe(codec="flac"), _probe(codec="flac")]) is False


def test_can_stream_copy_false_for_empty_list():
    assert sm.can_stream_copy([]) is False


# ---------------------------------------------------------------------------
# resolve_metadata
# ---------------------------------------------------------------------------

MANIFEST = {
    "schema_version": 3,
    "show": {"artist": "Grateful Dead", "date": "1973-06-10", "venue": "RFK Stadium", "city": "Washington, DC"},
    "tracks": [
        {"filename": "01 - Morning Dew.mp3", "title": "Morning Dew"},
        {"filename": "02 - Eyes of the World.mp3", "title": "Eyes of the World"},
    ],
}


def _entries(*names):
    return [sm.M3UEntry(path=Path(n)) for n in names]


def _probes(n, title=None):
    return [sm.Probe(path=Path("x"), duration_sec=1.0, codec_name="mp3", sample_rate=44100, channels=2, title=title)
            for _ in range(n)]


def test_resolve_metadata_derives_from_manifest():
    entries = _entries("01 - Morning Dew.mp3", "02 - Eyes of the World.mp3")
    meta = sm.resolve_metadata(entries, _probes(2), MANIFEST,
                                title=None, artist=None, album=None, playlist_stem="playlist")
    assert meta.artist == "Grateful Dead"
    assert meta.album == "1973-06-10 — RFK Stadium"
    assert meta.title == "Grateful Dead — 1973-06-10"
    assert meta.chapter_titles == ["Morning Dew", "Eyes of the World"]


def test_resolve_metadata_no_manifest_falls_back_to_playlist_stem():
    entries = _entries("a.mp3")
    meta = sm.resolve_metadata(entries, _probes(1), None,
                                title=None, artist=None, album=None, playlist_stem="my-show")
    assert meta.title == "my-show"
    assert meta.artist is None
    assert meta.album is None


def test_resolve_metadata_manifest_below_schema_version_3_is_ignored():
    old_manifest = {**MANIFEST, "schema_version": 2}
    entries = _entries("01 - Morning Dew.mp3")
    meta = sm.resolve_metadata(entries, _probes(1), old_manifest,
                                title=None, artist=None, album=None, playlist_stem="stem")
    assert meta.artist is None
    # falls through the whole cascade (manifest ignored) to the filename stem
    assert meta.chapter_titles == ["01 - Morning Dew"]


def test_resolve_metadata_cli_flags_win_over_manifest():
    entries = _entries("01 - Morning Dew.mp3")
    meta = sm.resolve_metadata(entries, _probes(1), MANIFEST,
                                title="Custom Title", artist="Custom Artist", album="Custom Album",
                                playlist_stem="stem")
    assert meta.title == "Custom Title"
    assert meta.artist == "Custom Artist"
    assert meta.album == "Custom Album"


def test_resolve_metadata_album_omits_empty_parts():
    manifest = {"schema_version": 3, "show": {"artist": "Dead", "date": "", "venue": "Winterland"}, "tracks": []}
    entries = _entries("a.mp3")
    meta = sm.resolve_metadata(entries, _probes(1), manifest,
                                title=None, artist=None, album=None, playlist_stem="stem")
    assert meta.album == "Winterland"


def test_chapter_title_cascade_manifest_wins():
    entries = _entries("01 - Morning Dew.mp3")
    entries[0].extinf_title = "EXTINF Title"
    probes = _probes(1, title="Embedded Title")
    meta = sm.resolve_metadata(entries, probes, MANIFEST,
                                title=None, artist=None, album=None, playlist_stem="stem")
    assert meta.chapter_titles == ["Morning Dew"]


def test_chapter_title_cascade_embedded_tag_over_extinf():
    entries = _entries("unmatched.mp3")
    entries[0].extinf_title = "EXTINF Title"
    probes = _probes(1, title="Embedded Title")
    meta = sm.resolve_metadata(entries, probes, MANIFEST,
                                title=None, artist=None, album=None, playlist_stem="stem")
    assert meta.chapter_titles == ["Embedded Title"]


def test_chapter_title_cascade_extinf_over_stem():
    entries = _entries("unmatched.mp3")
    entries[0].extinf_title = "EXTINF Title"
    probes = _probes(1, title=None)
    meta = sm.resolve_metadata(entries, probes, MANIFEST,
                                title=None, artist=None, album=None, playlist_stem="stem")
    assert meta.chapter_titles == ["EXTINF Title"]


def test_chapter_title_cascade_falls_back_to_stem():
    entries = _entries("set-1-intro.mp3")
    probes = _probes(1, title=None)
    meta = sm.resolve_metadata(entries, probes, MANIFEST,
                                title=None, artist=None, album=None, playlist_stem="stem")
    assert meta.chapter_titles == ["set-1-intro"]  # e.g. emcee's dj-audio clips, absent from tracks


# ---------------------------------------------------------------------------
# build_ffmetadata
# ---------------------------------------------------------------------------

def test_build_ffmetadata_header_and_tags():
    text = sm.build_ffmetadata({"title": "T", "artist": "A", "album": None}, [1.0], ["Chapter One"])
    lines = text.splitlines()
    assert lines[0] == ";FFMETADATA1"
    assert "title=T" in lines
    assert "artist=A" in lines
    assert not any(line.startswith("album=") for line in lines)  # empty tag omitted


def test_build_ffmetadata_chapter_timebase_and_cumulative_offsets():
    text = sm.build_ffmetadata({}, [1.5, 2.0], ["First", "Second"])
    assert text.count("[CHAPTER]") == 2
    assert text.count("TIMEBASE=1/1000") == 2
    # chapter 1: 0 -> 1500ms; chapter 2: 1500 -> 3500ms (chapter N's END is N+1's START)
    assert "START=0" in text
    assert "END=1500" in text
    assert "START=1500" in text
    assert "END=3500" in text


def test_build_ffmetadata_escapes_special_characters():
    text = sm.build_ffmetadata({"title": "a=b;c#d\\e"}, [], [])
    assert "title=a\\=b\\;c\\#d\\\\e" in text.splitlines()


def test_build_ffmetadata_escapes_chapter_title():
    text = sm.build_ffmetadata({}, [1.0], ["Rider > Truckin'"])
    assert "title=Rider > Truckin'" in text  # no special chars here, sanity check unescaped passthrough
    text2 = sm.build_ffmetadata({}, [1.0], ["a;b"])
    assert "title=a\\;b" in text2


# ---------------------------------------------------------------------------
# build_concat_list
# ---------------------------------------------------------------------------

def test_build_concat_list_basic(tmp_path):
    p1 = tmp_path / "one.mp3"
    p2 = tmp_path / "two.mp3"
    text = sm.build_concat_list([p1, p2])
    lines = text.splitlines()
    assert lines[0] == f"file '{p1.resolve()}'"
    assert lines[1] == f"file '{p2.resolve()}'"


def test_build_concat_list_escapes_single_quote(tmp_path):
    p = tmp_path / "Truckin's Best.mp3"
    text = sm.build_concat_list([p])
    assert text == f"file '{str(p.resolve()).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
    assert "'\\''" in text


# ---------------------------------------------------------------------------
# binary resolution
# ---------------------------------------------------------------------------

def _make_executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_resolve_binaries_defaults_to_path_lookup():
    which = lambda name: f"/usr/bin/{name}"
    ffmpeg, ffprobe = sm.resolve_binaries(None, None, which=which)
    assert ffmpeg == "/usr/bin/ffmpeg"
    assert ffprobe == "/usr/bin/ffprobe"


def test_resolve_binaries_ffmpeg_alone_finds_sibling_ffprobe(tmp_path):
    ffmpeg_path = _make_executable(tmp_path / "ffmpeg")
    _make_executable(tmp_path / "ffprobe")

    def which(name):
        raise AssertionError(f"should not fall back to PATH for {name}")

    ffmpeg, ffprobe = sm.resolve_binaries(str(ffmpeg_path), None, which=which)
    assert ffmpeg == str(ffmpeg_path)
    assert ffprobe == str(tmp_path / "ffprobe")


def test_resolve_binaries_ffmpeg_alone_falls_back_to_path_when_no_sibling(tmp_path):
    ffmpeg_path = _make_executable(tmp_path / "ffmpeg")
    ffmpeg, ffprobe = sm.resolve_binaries(str(ffmpeg_path), None, which=lambda name: "/usr/bin/ffprobe")
    assert ffprobe == "/usr/bin/ffprobe"


def test_resolve_binaries_missing_ffmpeg_raises_clear_error():
    with pytest.raises(sm.StitchError, match="ffmpeg"):
        sm.resolve_binaries(None, None, which=lambda name: None)


def test_resolve_binaries_explicit_nonexecutable_path_raises():
    with pytest.raises(sm.StitchError, match="--ffmpeg"):
        sm.resolve_binaries("/no/such/binary", None, which=shutil.which)


# ---------------------------------------------------------------------------
# Pre-flight checks (no ffmpeg needed: all of these abort before it is invoked)
# ---------------------------------------------------------------------------

def _playlist(tmp_path: Path, body: str) -> Path:
    playlist = tmp_path / "p.m3u"
    playlist.write_text(body)
    return playlist


def test_existing_output_refused_without_force(tmp_path, capsys):
    playlist = _playlist(tmp_path, "#EXTM3U\na.mp3\n")
    out = tmp_path / "out.mp3"
    out.write_text("previous take")
    assert sm.main([str(playlist), "-o", str(out)]) == 1
    assert "--force" in capsys.readouterr().err
    assert out.read_text() == "previous take"  # untouched


def test_missing_output_directory_reports_cleanly(tmp_path, capsys):
    playlist = _playlist(tmp_path, "#EXTM3U\na.mp3\n")
    assert sm.main([str(playlist), "-o", str(tmp_path / "nope" / "out.mp3")]) == 1
    err = capsys.readouterr().err
    assert "output directory does not exist" in err
    assert "ffmpeg" not in err  # a clean message, not a dump of ffmpeg's stderr


def test_missing_entry_aborts_before_ffmpeg_leaving_nothing(tmp_path, capsys):
    # The missing entry is first, so not even ffprobe runs — the dummy
    # binaries below exist only to prove nothing tried to invoke them.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        _make_executable(fake_bin / name)
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "b.mp3").write_bytes(b"")
    playlist = _playlist(pkg, "#EXTM3U\nghost.mp3\nb.mp3\n")
    out = pkg / "out.mp3"

    rc = sm.main([str(playlist), "-o", str(out), "--ffmpeg", str(fake_bin / "ffmpeg"),
                  "--ffprobe", str(fake_bin / "ffprobe")])

    assert rc == 1
    assert "ghost.mp3" in capsys.readouterr().err
    assert not out.exists()
    assert not list(pkg.glob("*.partial-*"))


def test_ffmpeg_commands_are_quieted_and_non_interactive():
    for cmd in (
        sm._build_copy_cmd("ffmpeg", Path("/tmp/c.txt"), Path("/tmp/m.txt"), Path("/tmp/o.partial-1")),
        sm._build_reencode_cmd("ffmpeg", [Path("/tmp/a.mp3")], Path("/tmp/m.txt"), "192k", Path("/tmp/o.partial-1")),
    ):
        assert cmd[:6] == ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
        assert cmd[-3:-1] == ["-f", "mp3"]  # partial name has no .mp3 suffix to infer from


# ---------------------------------------------------------------------------
# End-to-end (real ffmpeg)
# ---------------------------------------------------------------------------

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


def _make_sine_mp3(path: Path, rate: int, duration: float = 1.0) -> None:
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-ar", str(rate), "-ac", "2", "-codec:a", "libmp3lame",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _ffprobe_json(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters",
         str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(proc.stdout)


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not on PATH")
def test_end_to_end_reencode_route_mixed_sample_rates(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    a = pkg / "01 - First.mp3"
    b = pkg / "02 - Second.mp3"
    _make_sine_mp3(a, rate=44100, duration=1.0)
    _make_sine_mp3(b, rate=22050, duration=1.0)
    playlist = pkg / "playlist.m3u"
    playlist.write_text(
        "#EXTM3U\n"
        "#EXTINF:1,First Song\n"
        "01 - First.mp3\n"
        "#EXTINF:1,Second Song\n"
        "02 - Second.mp3\n"
    )

    out = pkg / "stitched.mp3"
    rc = sm.main(["--artist", "Test Artist", "--album", "Test Album", str(playlist), "-o", str(out)])
    assert rc == 0
    assert out.is_file()

    probed = _ffprobe_json(out)
    total_duration = float(probed["format"]["duration"])
    assert abs(total_duration - 2.0) < 0.3

    chapters = probed["chapters"]
    assert len(chapters) == 2
    assert chapters[0]["tags"]["title"] == "First Song"
    assert chapters[1]["tags"]["title"] == "Second Song"

    fmt_tags = {k.lower(): v for k, v in probed["format"].get("tags", {}).items()}
    assert fmt_tags.get("artist") == "Test Artist"
    assert fmt_tags.get("album") == "Test Album"


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not on PATH")
def test_end_to_end_stream_copy_route_matching_formats(tmp_path, capsys):
    pkg = tmp_path / "pkg2"
    pkg.mkdir()
    a = pkg / "01 - First.mp3"
    b = pkg / "02 - Second.mp3"
    _make_sine_mp3(a, rate=44100, duration=1.0)
    _make_sine_mp3(b, rate=44100, duration=1.0)
    playlist = pkg / "playlist.m3u"
    playlist.write_text(
        "#EXTM3U\n"
        "#EXTINF:1,First Song\n"
        "01 - First.mp3\n"
        "#EXTINF:1,Second Song\n"
        "02 - Second.mp3\n"
    )

    out = pkg / "stitched.mp3"
    rc = sm.main(["--artist", "Test Artist", str(playlist), "-o", str(out)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "stream-copy" in captured.out

    probed = _ffprobe_json(out)
    total_duration = float(probed["format"]["duration"])
    assert abs(total_duration - 2.0) < 0.3

    chapters = probed["chapters"]
    assert len(chapters) == 2
    assert chapters[0]["tags"]["title"] == "First Song"
    assert chapters[1]["tags"]["title"] == "Second Song"
