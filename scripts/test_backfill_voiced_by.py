"""Tests for scripts/backfill_voiced_by.py (see test_stitch_m3u.py for the
sys.path idiom)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backfill_voiced_by as bf
from emcee.presenters import Presenter, save_presenter


def P(id, name):
    return Presenter(id=id, name=name, sex="male", voice="v", character="c")


def make(root, slug, text, audio=None, extra=None):
    d = root / slug
    d.mkdir()
    m = {
        "schema_version": 3, "source": {"profile": "p"}, "extra": [1, 2],
        "dj_notes": {"context": "ctx", "set_intros": {"1": text}, "outro": "bye",
                     "mentioned_songs": ["A"]},
        "dj_audio": audio if audio is not None else {"set_intros": {"1": "a.mp3"}, "outro": "o.mp3"},
    }
    m.update(extra or {})
    (d / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    return d / "manifest.json"


def load(p):
    return json.loads(p.read_text())


PRES = [P("kurt", "K.C."), P("al", "Al"), P("bob", "Bob")]


def test_single_match_applied_preserves_everything(tmp_path, capsys):
    p = make(tmp_path, "s1", "Hi, this is K.C., welcome")
    before = load(p)
    bf.backfill(tmp_path, PRES, apply=True)
    after = load(p)
    assert capsys.readouterr().out.strip() == "s1: kurt"
    assert after["dj_audio"] == {**before["dj_audio"], "presenter": "kurt"}
    after["dj_audio"] = before["dj_audio"]
    assert after == before


def test_dry_run_writes_nothing(tmp_path, capsys, monkeypatch):
    # Hermetic: main() loads config + presenters from EMCEE_ROOT, so point it
    # at a private root (kept apart from the station dir swept for packages).
    emcee_root = tmp_path / "emcee"
    emcee_root.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(emcee_root))
    save_presenter(emcee_root, P("kurt", "K.C."))
    station = tmp_path / "station"
    station.mkdir()
    p = make(station, "s1", "this is K.C. here")
    raw = p.read_text()
    assert bf.main(["--station-root", str(station)]) == 0
    out = capsys.readouterr().out
    assert "s1: kurt" in out and "dry run: pass --apply to write" in out
    assert p.read_text() == raw


def test_zero_match(tmp_path, capsys):
    p = make(tmp_path, "s1", "nobody here")
    raw = p.read_text()
    bf.backfill(tmp_path, PRES, apply=True)
    assert "s1: left as ? (no presenter name found)" in capsys.readouterr().out
    assert p.read_text() == raw


def test_ambiguous(tmp_path, capsys):
    p = make(tmp_path, "s1", "Bob and Al are here")
    raw = p.read_text()
    bf.backfill(tmp_path, PRES, apply=True)
    assert "s1: left as ? (ambiguous: al, bob)" in capsys.readouterr().out
    assert p.read_text() == raw


def test_whole_word(tmp_path, capsys):
    make(tmp_path, "s1", "Alan and XK.C.Y and Bobby")
    bf.backfill(tmp_path, PRES, apply=False)
    assert "no presenter name found" in capsys.readouterr().out


def test_already_recorded_and_unvoiced_ignored(tmp_path, capsys):
    a = make(tmp_path, "s1", "K.C.", audio={"set_intros": {}, "outro": "o", "presenter": None})
    b = make(tmp_path, "s2", "K.C.", extra={"dj_audio": None})
    (tmp_path / ".stage").mkdir()
    raw = (a.read_text(), b.read_text())
    bf.backfill(tmp_path, PRES, apply=True)
    assert capsys.readouterr().out == ""
    assert (a.read_text(), b.read_text()) == raw


def test_unreadable_manifest_skipped(tmp_path, capsys):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "manifest.json").write_text("{nope")
    bf.backfill(tmp_path, PRES, apply=True)
    assert capsys.readouterr().out.startswith("skip bad:")
