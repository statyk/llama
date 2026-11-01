"""Tests for scripts/backfill_voiced_on.py (tmp station only; never a real one)."""
import datetime as dt
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backfill_voiced_on as bf

EDT = dt.timezone(dt.timedelta(hours=-4))


def ts(*args) -> float:
    return dt.datetime(*args, tzinfo=EDT).timestamp()


@pytest.fixture(autouse=True)
def _no_procs(monkeypatch):
    monkeypatch.setattr(bf, "running_tools", lambda: [])


def make(root, slug, clip_time, *, dj_audio=None, extra=None, manifest_time=None):
    d = root / slug
    (d / "dj-audio").mkdir(parents=True)
    audio = dj_audio if dj_audio is not None else {
        "set_intros": {"1": "dj-audio/set1-intro.mp3"}, "outro": "dj-audio/99-outro.mp3"}
    m = {"schema_version": 3, "source": {"profile": "p"}, "extra": [1, 2],
         "dj_notes": {"context": "c"}, "dj_audio": audio}
    m.update(extra or {})
    mp = d / "manifest.json"
    mp.write_text(json.dumps(m, indent=2) + "\n")
    if isinstance(audio, dict):
        names = list((audio.get("set_intros") or {}).values()) + [audio.get("outro")]
        for n in names:
            if n:
                (d / n).write_bytes(b"x")
                os.utime(d / n, (clip_time, clip_time))
    mt = manifest_time if manifest_time is not None else ts(2026, 10, 30, 12, 0, 0)
    os.utime(mp, (mt, mt))
    return mp


def load(p):
    return json.loads(p.read_text())


def test_window_edges_inclusive(tmp_path):
    cases = {
        "lo-in": (ts(2026, 10, 10, 19, 28, 0), "voiced_before"),
        "hi-in": (ts(2026, 10, 10, 19, 40, 0), "voiced_before"),
        "lo-out": (ts(2026, 10, 10, 19, 27, 59), "voiced_on"),
        "hi-out": (ts(2026, 10, 10, 19, 40, 1), "voiced_on"),
    }
    paths = {k: make(tmp_path, k, t) for k, (t, _) in cases.items()}
    bf.backfill(tmp_path, apply=True)
    for k, (t, key) in cases.items():
        blk = load(paths[k])["dj_audio"]
        assert key in blk, k
        other = "voiced_on" if key == "voiced_before" else "voiced_before"
        assert other not in blk, k
        if key == "voiced_before":
            assert blk[key] == "2026-10-10"
        else:
            assert blk[key] == dt.datetime.fromtimestamp(t).date().isoformat()


def test_voiced_on_is_newest_clip_not_manifest(tmp_path):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12, 0, 0), manifest_time=ts(2026, 10, 31, 12, 0, 0))
    os.utime(p.parent / "dj-audio" / "99-outro.mp3", (ts(2026, 10, 22, 12), ts(2026, 10, 22, 12)))
    bf.backfill(tmp_path, apply=True)
    assert load(p)["dj_audio"]["voiced_on"] == dt.datetime.fromtimestamp(ts(2026, 10, 22, 12)).date().isoformat()


def test_manifest_mtime_preserved(tmp_path):
    mt = ts(2026, 10, 30, 12, 0, 0)
    p = make(tmp_path, "s", ts(2026, 10, 20, 12, 0, 0), manifest_time=mt)
    before = p.stat()
    bf.backfill(tmp_path, apply=True)
    after = p.stat()
    assert "voiced_on" in load(p)["dj_audio"]
    assert after.st_mtime_ns == before.st_mtime_ns


def test_manifest_changed_before_replace_is_skipped(tmp_path, capsys, monkeypatch):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12, 0, 0))

    def touch():
        data = load(p)
        data["extra"] = [9]
        p.write_text(json.dumps(data, indent=2) + "\n")

    monkeypatch.setattr(bf, "_before_replace", touch)
    bf.backfill(tmp_path, apply=True)
    out = capsys.readouterr().out
    assert "skip s: manifest changed" in out
    d = load(p)
    assert d["extra"] == [9] and "voiced_on" not in d["dj_audio"]


def test_awaiting_fix_survives(tmp_path):
    af = {"reason": "r", "marked_at": "2026-10-01T00:00:00Z"}
    p = make(tmp_path, "s", ts(2026, 10, 20, 12), extra={"awaiting_fix": af})
    bf.backfill(tmp_path, apply=True)
    d = load(p)
    assert d["awaiting_fix"] == af and "voiced_on" in d["dj_audio"]


def test_legacy_block_byte_equal_apart_from_key(tmp_path):
    legacy = {"set_intros": {"1": "dj-audio/set1-intro.mp3"}, "outro": "dj-audio/99-outro.mp3",
              "weird_unknown": {"a": 1}}
    p = make(tmp_path, "s", ts(2026, 10, 20, 12), dj_audio=legacy)
    before = p.read_text()
    bf.backfill(tmp_path, apply=True)
    after = load(p)
    expect = json.loads(before)
    expect["dj_audio"]["voiced_on"] = after["dj_audio"]["voiced_on"]
    assert after == expect
    assert p.read_text() == json.dumps(expect, indent=2) + "\n"


def test_dry_run_writes_nothing_and_counts(tmp_path, capsys):
    make(tmp_path, "a", ts(2026, 10, 10, 19, 30, 0))
    make(tmp_path, "b", ts(2026, 10, 20, 12))
    raws = {p: p.read_bytes() for p in tmp_path.glob("*/manifest.json")}
    bf.backfill(tmp_path, apply=False)
    out = capsys.readouterr().out
    assert {p: p.read_bytes() for p in tmp_path.glob("*/manifest.json")} == raws
    assert "voiced_before: 1, voiced_on: 1" in out


def test_per_presenter_counts(tmp_path, capsys):
    make(tmp_path, "a", ts(2026, 10, 20, 12), dj_audio={
        "presenter": "phil", "set_intros": {"1": "dj-audio/set1-intro.mp3"}, "outro": "dj-audio/99-outro.mp3"})
    make(tmp_path, "b", ts(2026, 10, 20, 12))
    bf.backfill(tmp_path, apply=False)
    out = capsys.readouterr().out
    assert "presenter phil: 1" in out and "presenter ?: 1" in out


def test_already_set_null_and_null_block(tmp_path, capsys):
    a = make(tmp_path, "a", ts(2026, 10, 20, 12))
    d = load(a)
    d["dj_audio"]["voiced_on"] = "2026-01-01"
    a.write_text(json.dumps(d, indent=2) + "\n")
    b = make(tmp_path, "b", ts(2026, 10, 20, 12))
    d = load(b)
    d["dj_audio"]["voiced_on"] = None
    d["dj_audio"]["voiced_before"] = None
    b.write_text(json.dumps(d, indent=2) + "\n")
    c = make(tmp_path, "c", 0, dj_audio=None)
    d = load(c)
    d["dj_audio"] = None
    c.write_text(json.dumps(d, indent=2) + "\n")
    ra, rc = a.read_bytes(), c.read_bytes()
    bf.backfill(tmp_path, apply=True)
    assert a.read_bytes() == ra and c.read_bytes() == rc
    assert "voiced_on" in load(b)["dj_audio"] and load(b)["dj_audio"]["voiced_on"] != None  # noqa: E711


def test_idempotent(tmp_path):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12))
    bf.backfill(tmp_path, apply=True)
    once = p.read_bytes()
    bf.backfill(tmp_path, apply=True)
    assert p.read_bytes() == once


def test_missing_clip_left_alone_and_printed(tmp_path, capsys):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12))
    (p.parent / "dj-audio" / "99-outro.mp3").unlink()
    raw = p.read_bytes()
    bf.backfill(tmp_path, apply=True)
    assert p.read_bytes() == raw


def test_missing_clip_message(tmp_path, capsys):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12))
    (p.parent / "dj-audio" / "99-outro.mp3").unlink()
    bf.backfill(tmp_path, apply=False)
    assert "s: clip missing" in capsys.readouterr().out


def test_apply_refused_while_tool_runs(tmp_path, monkeypatch, capsys):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12))
    monkeypatch.setattr(bf, "running_tools", lambda: ["601 1 /usr/local/bin/emcee run"])
    raw = p.read_bytes()
    assert bf.backfill(tmp_path, apply=True) != 0
    assert p.read_bytes() == raw


def test_process_checked_before_each_write(tmp_path, monkeypatch):
    a = make(tmp_path, "a", ts(2026, 10, 20, 12))
    b = make(tmp_path, "b", ts(2026, 10, 20, 12))
    calls = iter([[], ["601 1 emcee run"]])
    monkeypatch.setattr(bf, "running_tools", lambda: next(calls))
    bf.backfill(tmp_path, apply=True)
    assert "voiced_on" in load(a)["dj_audio"]
    assert "voiced_on" not in load(b)["dj_audio"]


def test_main_dry_run(tmp_path, capsys):
    make(tmp_path, "s", ts(2026, 10, 20, 12))
    assert bf.main(["--station-root", str(tmp_path)]) == 0
    assert "dry run" in capsys.readouterr().out


def _write_after_classify(monkeypatch, p, mutate):
    real = bf.classify

    def classify(d, block):
        verdict = real(d, block)
        data = load(p)
        mutate(data)
        p.write_text(json.dumps(data, indent=2) + "\n")
        return verdict

    monkeypatch.setattr(bf, "classify", classify)


def test_block_cleared_between_classify_and_apply_is_skipped(tmp_path, capsys, monkeypatch):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12))
    _write_after_classify(monkeypatch, p, lambda d: d.update(dj_audio=None))
    assert bf.backfill(tmp_path, apply=True) == 0
    assert "skip s:" in capsys.readouterr().out
    assert load(p)["dj_audio"] is None


def test_revoiced_between_classify_and_apply_is_skipped(tmp_path, capsys, monkeypatch):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12))
    _write_after_classify(monkeypatch, p, lambda d: d["dj_audio"].update(voiced_on="2026-10-31"))
    bf.backfill(tmp_path, apply=True)
    assert "skip s:" in capsys.readouterr().out
    assert load(p)["dj_audio"]["voiced_on"] == "2026-10-31"
    assert "voiced_before" not in load(p)["dj_audio"]


def test_preexisting_voiced_before_is_left_alone(tmp_path):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12))
    d = load(p)
    d["dj_audio"]["voiced_before"] = "2026-10-10"
    p.write_text(json.dumps(d, indent=2) + "\n")
    raw = p.read_bytes()
    bf.backfill(tmp_path, apply=True)
    assert p.read_bytes() == raw


def test_non_canonical_formatting_is_skipped(tmp_path, capsys):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12))
    p.write_text(json.dumps(load(p)))  # compact, not indent=2
    raw = p.read_bytes()
    bf.backfill(tmp_path, apply=True)
    assert "formatting is not" in capsys.readouterr().out
    assert p.read_bytes() == raw


def test_no_trailing_newline_is_preserved(tmp_path):
    p = make(tmp_path, "s", ts(2026, 10, 20, 12))
    p.write_text(json.dumps(load(p), indent=2))
    bf.backfill(tmp_path, apply=True)
    out = p.read_bytes()
    assert not out.endswith(b"\n")
    assert "voiced_on" in json.loads(out)["dj_audio"]
