"""Tests for scripts/backfill_tts_record.py (see test_stitch_m3u.py for the
sys.path idiom)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backfill_tts_record as bf

PHIL = bf.BACKFILL["phil"]
JB = bf.BACKFILL["jamesbrown"]


def make(root, slug, audio):
    d = root / slug
    d.mkdir()
    m = {"schema_version": 3, "source": {"profile": "p"}, "extra": [1, 2],
         "dj_notes": {"context": "ctx"}, "dj_audio": audio}
    (d / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    return d / "manifest.json"


def legacy(presenter, **more):
    return {"set_intros": {"1": "a.mp3"}, "outro": "o.mp3", "presenter": presenter, **more}


def load(p):
    return json.loads(p.read_text())


def test_vouched_presenters_get_their_record_and_nothing_else_moves(tmp_path, capsys):
    a = make(tmp_path, "a", legacy("phil"))
    b = make(tmp_path, "b", legacy("jamesbrown", future_key={"x": 1}))
    before = (load(a), load(b))
    bf.backfill(tmp_path, bf.BACKFILL, apply=True)
    out = capsys.readouterr().out
    assert "a: phil -> voxtral voxtral-mini-tts-2603" in out
    assert "b: jamesbrown -> mlx_audio mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16" in out
    assert "wrote 2" in out
    for path, old, rec in ((a, before[0], PHIL), (b, before[1], JB)):
        new = load(path)
        assert new["dj_audio"] == {**old["dj_audio"], "tts": rec}
        new["dj_audio"] = old["dj_audio"]
        assert new == old
    assert load(a)["dj_audio"]["tts"]["voice"] == "unknown"


def test_dry_run_writes_nothing(tmp_path, capsys):
    p = make(tmp_path, "a", legacy("phil"))
    raw = p.read_text()
    assert bf.main(["--station-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "a: phil -> voxtral" in out and "would write 1" in out
    assert "dry run: pass --apply to write" in out
    assert p.read_text() == raw


def test_unvouched_unrecorded_and_house_are_left_and_counted(tmp_path, capsys):
    paths = [make(tmp_path, "k1", legacy("kurt")), make(tmp_path, "k2", legacy("kurt")),
             make(tmp_path, "h", legacy(None)),
             make(tmp_path, "q", {"set_intros": {}, "outro": "o.mp3"})]
    raw = [p.read_text() for p in paths]
    bf.backfill(tmp_path, bf.BACKFILL, apply=True)
    out = capsys.readouterr().out
    assert "wrote 0" in out
    assert "left alone (no record, presenter not vouched for): ? 1, house 1, kurt 2" in out
    assert [p.read_text() for p in paths] == raw


def test_existing_record_never_overwritten(tmp_path, capsys):
    rec = {"backend": "voxtral", "model": "voxtral-mini-tts-2603", "voice": "clone:abc"}
    p = make(tmp_path, "a", legacy("phil", tts=rec))
    unvoiced = make(tmp_path, "b", None)
    (tmp_path / ".stage").mkdir()
    raw = (p.read_text(), unvoiced.read_text())
    bf.backfill(tmp_path, bf.BACKFILL, apply=True)
    assert capsys.readouterr().out == "wrote 0\n"
    assert (p.read_text(), unvoiced.read_text()) == raw


def test_unreadable_manifest_skipped(tmp_path, capsys):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "manifest.json").write_text("{nope")
    make(tmp_path, "good", legacy("phil"))
    bf.backfill(tmp_path, bf.BACKFILL, apply=True)
    out = capsys.readouterr().out
    assert out.startswith("skip bad:") and "wrote 1" in out
