from pathlib import Path

from mutagen.id3 import ID3

from llama.audio import packaged_filename, read_duration, tag_audio


def test_packaged_filename():
    assert packaged_filename(1, "Morning Dew", ".mp3") == "01 - Morning Dew.mp3"
    assert packaged_filename(12, "Truckin' > The Other One", ".mp3") == "12 - Truckin' _ The Other One.mp3"
    assert packaged_filename(3, "///", ".flac") == "03 - untitled.flac"


def test_tag_mp3_roundtrip(tmp_path: Path):
    # ID3 tags prepend to any file; no valid MPEG frames needed for tagging
    p = tmp_path / "01 - Morning Dew.mp3"
    p.write_bytes(b"\x00" * 64)
    tag_audio(p, artist="Grateful Dead", album="1973-06-10 RFK Stadium, Washington, DC",
              title="Morning Dew", track=1, date="1973-06-10", comment="gd73-06-10.sbd")
    tags = ID3(p)
    assert str(tags["TIT2"]) == "Morning Dew"
    assert str(tags["TPE1"]) == "Grateful Dead"
    assert str(tags["TRCK"]) == "1"
    assert "1973" in str(tags["TDRC"])


def test_read_duration_none_for_garbage(tmp_path: Path):
    p = tmp_path / "x.mp3"
    p.write_bytes(b"not audio")
    assert read_duration(p) is None
