"""Replay's audio check is cache-only (spec 2026-11-14-junk-drop-audio-check-design,
"Replay and the rollout"): the checker reads the REAL show dir's verdict cache (never the
scratch workspace), never downloads, and the cache file is one of the replay's inputs."""
import hashlib
import json

import pytest

from fixture_library import IDENT
from fixture_library import library_show as _library_show
from fixture_library import replay_config as _config
from llama.audio_check import cache as audio_cache
from llama.audio_check import classify
from llama.replay import CacheOnlyIA, input_digests, replay_show

TUNING = "gd73-06-10d1t02.mp3"


def drop_tuning(root, filename=TUNING, title="Tuning", length="3:00"):
    """Retitle `filename` in the cached metadata so the junk-title rule drops it."""
    path = root / "cache" / f"md_{IDENT}.json"
    md = json.loads(path.read_text())
    for f in md["files"]:
        if f["name"] == filename:
            f["title"], f["length"] = title, length
    path.write_text(json.dumps(md))
    return md


def cache_verdict(ws, md, filename=TUNING, verdict="junk", run_sec=12, frac=0.1):
    """Store a verdict for `filename` in the show's real verdict cache."""
    audio_cache.write_verdicts(ws.audio_check, [(audio_cache.identity(IDENT, filename, md),
                                                 classify.Result(verdict, run_sec, frac))])


class _SpyIA(CacheOnlyIA):
    def __init__(self, cache_dir):
        super().__init__(cache_dir)
        self.downloads = []

    def download_file(self, *args, **kwargs):
        self.downloads.append(args)
        return super().download_file(*args, **kwargs)


def _replay(tmp_path, ws, ia=None):
    return replay_show(ws, config=_config(tmp_path), ia=ia or CacheOnlyIA(tmp_path / "cache"),
                       slfm=None, scratch=tmp_path / "scratch" / ws.dir.name, delivered=set())


def test_replay_checker_reads_real_show_dir_not_scratch(tmp_path, monkeypatch):
    ws, _ = _library_show(tmp_path, held=False)
    md = drop_tuning(tmp_path)
    cache_verdict(ws, md, verdict="music", run_sec=170, frac=0.9)
    built = []
    real = audio_cache.Checker

    def spy(cache_path, metadata, identifier, **kw):
        built.append((cache_path, identifier, kw))
        return real(cache_path, metadata, identifier, **kw)
    monkeypatch.setattr(audio_cache, "Checker", spy)
    r = _replay(tmp_path, ws)
    assert r.unreplayable is None
    assert built == [(ws.audio_check, IDENT, {"ia": None})]
    assert r.junk_drops[0]["check"] == "music"
    # the scratch workspace never gains a verdict cache (it holds only the overrides copy)
    scratch = tmp_path / "scratch" / ws.dir.name
    assert not (scratch / ws.audio_check.name).exists()


def test_replay_never_downloads(tmp_path, monkeypatch):
    ws, _ = _library_show(tmp_path, held=False)
    drop_tuning(tmp_path)
    monkeypatch.setattr(classify, "classify_file",
                        lambda path: pytest.fail("replay classified audio"))
    ia = _SpyIA(tmp_path / "cache")
    r = _replay(tmp_path, ws, ia)
    assert r.unreplayable is None and ia.downloads == []
    d = r.junk_drops[0]
    assert d["check"] == "unchecked" and d["check_error"] == "no cached verdict"
    assert not ws.audio_check.exists()


def test_input_digests_include_audio_check_when_present(tmp_path):
    ws, _ = _library_show(tmp_path, held=False)
    md = drop_tuning(tmp_path)
    cache_verdict(ws, md)
    d = input_digests(ws)
    assert d["audio-check.json"] == hashlib.sha256(ws.audio_check.read_bytes()).hexdigest()


def test_input_digests_omit_audio_check_when_absent(tmp_path):
    ws, _ = _library_show(tmp_path, held=False)
    d = input_digests(ws)
    assert "audio-check.json" not in d
    assert set(d) == {"show.json", "overrides.json", "provenance.json", "research.md",
                      "vetting.extraction"}


def test_arm_row_junk_drops_carry_outcome(tmp_path):
    ws, _ = _library_show(tmp_path, held=False)
    md = drop_tuning(tmp_path)
    drop_tuning(tmp_path, "gd73-06-10d2t02.mp3", title="Crowd", length="1:30")
    md = json.loads((tmp_path / "cache" / f"md_{IDENT}.json").read_text())
    cache_verdict(ws, md, verdict="junk", run_sec=12, frac=0.1)
    r = _replay(tmp_path, ws)
    assert r.unreplayable is None
    by_file = {d["filename"]: d for d in r.junk_drops}
    assert by_file[TUNING] == {"filename": TUNING, "title": "Tuning", "set": "1",
                               "after_track": 1, "duration_sec": 180.0, "rule": "A",
                               "held": False, "check": "junk", "run_sec": 12, "frac": 0.1,
                               "check_error": None}
    crowd = by_file["gd73-06-10d2t02.mp3"]
    assert (crowd["check"], crowd["run_sec"], crowd["frac"], crowd["check_error"]) == \
        ("unchecked", None, None, "no cached verdict")
    assert json.loads(json.dumps(r.to_dict()))["junk_drops"] == r.junk_drops


@pytest.mark.parametrize("frac", [float("nan"), float("inf"), float("-inf")])
def test_replay_non_finite_music_verdict_is_unchecked_not_a_raise(tmp_path, frac):
    # write_verdicts json.dumps a non-finite frac as NaN/Infinity, which json.loads reads
    # back: corrupt content (the whole cache is unreadable), never a raise out of gather.
    ws, _ = _library_show(tmp_path, held=False)
    md = drop_tuning(tmp_path)
    cache_verdict(ws, md, verdict="music", run_sec=300, frac=frac)
    r = _replay(tmp_path, ws)
    assert r.unreplayable is None
    d = r.junk_drops[0]
    assert (d["check"], d["run_sec"], d["frac"], d["check_error"]) == \
        ("unchecked", None, None, "verdict cache unreadable")
    json.dumps(r.to_dict(), allow_nan=False)
