import hashlib
import io
import os
import wave
from pathlib import Path

import numpy as np
import pytest

from transmitter import assemble
from transmitter.announce_config import AnnounceSettings, Gaps
from transmitter.assemble import Assembler, gc_clips, scan_clips
from transmitter.concert import BreakContent
from transmitter.errors import AssemblyError, PieceUndecodable
from transmitter.layout import CONCERT_ROLE
from transmitter.station import Entry, file_set_key_and_sizes
from transmitter.workspace import Workspace
from tests_transmitter.helpers import requires_ffmpeg, write_mp3

pytestmark = requires_ffmpeg
RATE = 44_100


def tone(seconds: float, freq: float = 440.0, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    x = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([x, x], axis=1)


def make_pieces(tmp_path, specs):
    """specs: [(id, text, seconds)] -> pieces dir with piece-<id>.mp3; returns (dir, BreakContent)."""
    d = tmp_path / "pieces"
    d.mkdir(exist_ok=True)
    for pid, _text, secs in specs:
        write_mp3(d / f"piece-{pid}.mp3", tone(secs, 300 + 50 * len(pid)))
    pieces = tuple((pid, text) for pid, text, _ in specs)
    return d, BreakContent(pieces=pieces, entries=(), names=(), phrases=("id", "next"), y_time_id=None)


SPECS = [("aaa", "You are listening.", 1.0), ("bbb", "Coming up next, Foo", 0.8),
         ("ccc", "with Bar,", 0.6), ("ddd", "followed by Baz", 0.5)]


def read_wav(path: Path):
    with wave.open(str(path)) as w:
        raw = w.readframes(w.getnframes())
        return (w.getnchannels(), w.getsampwidth(), w.getframerate(),
                np.frombuffer(raw, dtype="<i2").reshape(-1, w.getnchannels()).astype(np.float32) / 32768)


def make_assembler(tmp_path, settings=None, specs=SPECS):
    d, content = make_pieces(tmp_path, specs)
    asm = Assembler(pieces=d, out_dir=tmp_path / "out", settings=settings or AnnounceSettings())
    return asm, content, d


def piece_len(d, pid):
    from transmitter.audio import iter_decode
    return sum(len(c) for c in iter_decode(d / f"piece-{pid}.mp3"))


def test_build_joins_pieces_with_the_spec_gaps(tmp_path):
    asm, content, d = make_assembler(tmp_path)
    show = asm.build(content)
    _, _, _, pcm = read_wav(show.dir / show.entries[0].path)
    g = Gaps()
    expected = sum(piece_len(d, p) for p, *_ in SPECS) + round(RATE * (g.after_id + g.within + g.after_comma))
    assert abs(len(pcm) - expected) <= len(SPECS)


def test_build_mixes_the_bed_under_with_lead_in_and_tail(tmp_path):
    t = np.arange(int(3 * RATE)) / RATE
    bed = np.stack([(0.5 * np.sin(2 * np.pi * 100 * t)).astype(np.float32)] * 2, axis=1)
    write_mp3(tmp_path / "bed.mp3", bed)
    s = AnnounceSettings(bed=tmp_path / "bed.mp3", bed_under_db=20.0)
    asm, content, d = make_assembler(tmp_path, s)
    _, _, _, pcm = read_wav((lambda sh: sh.dir / sh.entries[0].path)(asm.build(content)))
    voice_n = sum(piece_len(d, p) for p, *_ in SPECS)
    gaps_n = round(RATE * (0.4 + 0.05 + 0.15))
    assert abs(len(pcm) - (voice_n + gaps_n + round(RATE * 1.5))) <= 8
    # the voice starts after the 0.5 s lead-in; the gap after the first piece is voice-free
    lead = round(RATE * 0.5)
    p1 = piece_len(d, "aaa")
    gap = pcm[lead + p1 + 2000: lead + p1 + round(0.4 * RATE) - 2000, 0]
    # voice RMS: the joined pieces excluding gaps
    from transmitter.audio import iter_decode
    v = np.concatenate([np.concatenate(list(iter_decode(d / f"piece-{p}.mp3"))) for p, *_ in SPECS])
    rms = lambda x: float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))
    diff = 20 * np.log10(rms(v) / rms(gap))
    assert abs(diff - 20.0) < 0.5
    # lead-in carries bed (after the fade), the tail is bed only
    assert rms(pcm[round(0.2 * RATE):round(0.45 * RATE), 0]) > 0
    assert rms(pcm[-round(0.9 * RATE):-round(0.6 * RATE), 0]) > 0


def test_wav_is_44k1_stereo_16bit(tmp_path):
    asm, content, _ = make_assembler(tmp_path)
    show = asm.build(content)
    ch, width, rate, _ = read_wav(show.dir / show.entries[0].path)
    assert (ch, width, rate) == (2, 2, 44_100)


def test_slug_is_a_content_hash_and_rebuilding_reuses_the_file(tmp_path):
    asm, content, _ = make_assembler(tmp_path)
    a = asm.build(content)
    path = a.dir / a.entries[0].path
    old = path.stat()
    data = path.read_bytes()
    # an old mtime must survive a rebuild untouched (the clip's own key hashes it)
    os.utime(path, (1_000_000, 1_000_000))
    old = path.stat()
    key_before = file_set_key_and_sizes(a.dir, [a.entries[0].path])
    b = asm.build(content)
    now = path.stat()
    assert b.slug == a.slug and b.slug.startswith("concert-") and len(b.slug) == len("concert-") + 16
    assert (now.st_ino, now.st_mtime_ns, now.st_size) == (old.st_ino, old.st_mtime_ns, old.st_size)
    assert path.read_bytes() == data
    assert file_set_key_and_sizes(b.dir, [b.entries[0].path]) == key_before
    assert b.key == file_set_key_and_sizes(a.dir, [a.entries[0].path])[0]


def test_the_clip_show_is_a_clip_entry(tmp_path):
    asm, content, _ = make_assembler(tmp_path)
    show = asm.build(content)
    assert show.entries == (Entry(f"{show.slug}.wav", "clip", "Announcement"),)
    assert show.dir == tmp_path / "out"
    assert show.meta["role"] == CONCERT_ROLE and show.meta["ann_id"] is None
    assert show.meta["sizes"] == {f"{show.slug}.wav": (show.dir / f"{show.slug}.wav").stat().st_size}


def test_slug_changes_with_gaps_bed_gain_and_piece_files(tmp_path):
    t = np.arange(int(2 * RATE)) / RATE
    write_mp3(tmp_path / "bed.mp3", np.stack([(0.5 * np.sin(2 * np.pi * 100 * t)).astype(np.float32)] * 2, axis=1))
    base = AnnounceSettings()
    asm, content, d = make_assembler(tmp_path, base)
    s0 = asm.build(content).slug
    def slug_for(settings):
        return Assembler(pieces=d, out_dir=tmp_path / "out", settings=settings).build(content).slug
    assert slug_for(AnnounceSettings(gaps=Gaps(after_id=0.5))) != s0
    with_bed = slug_for(AnnounceSettings(bed=tmp_path / "bed.mp3"))
    assert with_bed != s0
    assert slug_for(AnnounceSettings(bed=tmp_path / "bed.mp3", bed_under_db=15)) != with_bed
    write_mp3(d / "piece-aaa.mp3", tone(1.2))
    assert slug_for(base) != s0


def test_missing_or_undecodable_piece_raises_piece_undecodable(tmp_path):
    asm, content, d = make_assembler(tmp_path)
    (d / "piece-ccc.mp3").unlink()
    with pytest.raises(PieceUndecodable) as e:
        asm.build(content)
    assert e.value.piece_id == "ccc"
    (d / "piece-ccc.mp3").write_bytes(b"not an mp3 at all" * 50)
    with pytest.raises(PieceUndecodable) as e:
        asm.build(content)
    assert e.value.piece_id == "ccc"
    (d / "piece-ccc.mp3").write_bytes(b"")
    with pytest.raises(PieceUndecodable) as e:
        asm.build(content)
    assert e.value.piece_id == "ccc"


def test_unreadable_bed_is_an_assembly_error(tmp_path):
    for bed in (tmp_path / "nope.mp3", Path(str(tmp_path / "bad\0bed.mp3"))):
        asm, content, _ = make_assembler(tmp_path, AnnounceSettings(bed=bed))
        with pytest.raises(AssemblyError) as e:
            asm.build(content)
        assert not isinstance(e.value, PieceUndecodable)
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"garbage" * 100)
    asm, content, _ = make_assembler(tmp_path, AnnounceSettings(bed=junk))
    with pytest.raises(AssemblyError):
        asm.build(content)


def test_scan_clips_finds_concert_wavs_only(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "concert-0123456789abcdef.wav").write_bytes(b"x" * 10)
    (out / "concert-empty.wav").write_bytes(b"")
    (out / ".concert-aa.wav.1.tmp").write_bytes(b"x")
    (out / "id-x.mp3").write_bytes(b"x")
    (out / "concert-0123456789abcdef.txt").write_bytes(b"x")
    (out / "concert-dir.wav").mkdir()
    shows = scan_clips(out)
    assert [s.slug for s in shows] == ["concert-0123456789abcdef"]
    assert shows[0].entries == (Entry("concert-0123456789abcdef.wav", "clip", "Announcement"),)
    assert shows[0].meta["role"] == CONCERT_ROLE
    assert scan_clips(tmp_path / "missing") == []


def test_gc_keeps_referenced_and_young_clips(tmp_path):
    out, cache = tmp_path / "out", tmp_path / "cache"
    out.mkdir(); cache.mkdir()
    now = 1_000_000.0
    def clip(name, age):
        p = out / name
        p.write_bytes(b"x" * 10)
        os.utime(p, (now - age, now - age))
        return p
    old_un = clip("concert-old.wav", 7200)
    kept = clip("concert-kept.wav", 7200)
    young = clip("concert-young.wav", 60)
    old_tmp = clip(".concert-x.wav.1.tmp", 7200)
    young_tmp = clip(".concert-y.wav.1.tmp", 60)
    keys = {}
    for p in (old_un, kept, young):
        k = file_set_key_and_sizes(out, [p.name])[0]
        (cache / f"{k}.json").write_text("{}")
        keys[p.name] = k
    n = gc_clips(out, cache, {"concert-kept"}, now_s=now)
    assert n == 2
    assert not old_un.exists() and not old_tmp.exists()
    assert kept.exists() and young.exists() and young_tmp.exists()
    assert not (cache / f"{keys['concert-old.wav']}.json").exists()
    assert (cache / f"{keys['concert-kept.wav']}.json").exists()
    assert (cache / f"{keys['concert-young.wav']}.json").exists()
    assert gc_clips(tmp_path / "missing", cache, set(), now_s=now) == 0


def test_workspace_concert_dir(tmp_path):
    assert Workspace(tmp_path).concert_dir == tmp_path / "render" / "concert"
