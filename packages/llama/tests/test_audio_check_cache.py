import json
import subprocess
import sys
from pathlib import Path

import pytest

from llama.audio_check import cache, classify, decode, model, rule
from llama.audio_check.cache import CacheReadError, CacheUnreadable, Checker, Outcome, identity, lookup, write_verdicts
from llama.audio_check.classify import Result
from llama.workspace import SHOW_STAGE_ORDER, ShowWorkspace, show_stage_artifacts

ID = "gd73-06-10.sbd"
META = {
    "files": [
        {"name": "d1t01.mp3", "md5": "aaa", "size": "1000"},
        {"name": "d1t02.mp3", "md5": "bbb", "size": "2000"},
        {"name": "d1t03.mp3", "md5": "ccc", "size": "3000"},
        {"name": "nomd5.mp3", "size": "4000"},
    ]
}
REPO = Path(__file__).resolve().parents[3]


class FakeIA:
    def __init__(self, exc=None):
        self.exc = exc
        self.calls = []
        self.seen_dests = []

    def download_file(self, identifier, filename, dest, md5=None):
        self.calls.append((identifier, filename, md5))
        dest = Path(dest)
        self.seen_dests.append(dest)
        if self.exc:
            dest.with_suffix(dest.suffix + ".part").write_bytes(b"partial")
            raise self.exc
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"audio")
        return dest


@pytest.fixture
def fake_classify(monkeypatch):
    calls = []
    results = {}

    def fake(path):
        path = Path(path)
        assert path.exists()
        calls.append(path)
        r = results.get(path.name, Result("music", 300, 0.9))
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(classify, "classify_file", fake)
    fake.calls, fake.results = calls, results
    return fake


def _store(path, filename, verdict="music", run_sec=300, frac=0.9, version=rule.VERSION, meta=META):
    entry = {**identity(ID, filename, meta), "verdict": verdict, "run_sec": run_sec,
             "frac": frac, "version": version, "checked_at": "2026-11-14T00:00:00Z"}
    data = json.loads(path.read_text()) if path.exists() else {"entries": []}
    data["entries"].append(entry)
    path.write_text(json.dumps(data))


def test_cached_current_verdict_used_without_classifier(tmp_path, fake_classify):
    p = tmp_path / "audio-check.json"
    _store(p, "d1t01.mp3", verdict="junk", run_sec=10, frac=0.1)
    ia = FakeIA()
    out = Checker(p, META, ID, ia=ia, tmp_dir=tmp_path).check("d1t01.mp3")
    assert out == Outcome("junk", 10, 0.1)
    assert fake_classify.calls == [] and ia.calls == []


def test_cache_only_uses_stale_verdict(tmp_path, fake_classify):
    p = tmp_path / "audio-check.json"
    _store(p, "d1t01.mp3", verdict="music", run_sec=200, frac=0.7, version="old")
    chk = Checker(p, META, ID)
    out = chk.check("d1t01.mp3")
    assert out == Outcome("music", 200, 0.7, stale=True)
    assert fake_classify.calls == [] and chk.new_verdicts == []


def test_online_stale_recompute_failure_keeps_stale(tmp_path, fake_classify):
    p = tmp_path / "audio-check.json"
    _store(p, "d1t01.mp3", verdict="music", run_sec=200, frac=0.7, version="old")
    chk = Checker(p, META, ID, ia=FakeIA(exc=RuntimeError("503")), tmp_dir=tmp_path)
    out = chk.check("d1t01.mp3")
    assert (out.check, out.run_sec, out.frac, out.stale) == ("music", 200, 0.7, True)
    assert "503" in out.error
    assert chk.new_verdicts == []


def test_online_stale_recompute_success_replaces(tmp_path, fake_classify):
    p = tmp_path / "audio-check.json"
    _store(p, "d1t01.mp3", verdict="music", run_sec=200, frac=0.7, version="old")
    fake_classify.results["d1t01.mp3"] = Result("junk", 0, 0.0)
    chk = Checker(p, META, ID, ia=FakeIA(), tmp_dir=tmp_path)
    assert chk.check("d1t01.mp3") == Outcome("junk", 0, 0.0)
    write_verdicts(p, chk.new_verdicts)
    data = json.loads(p.read_text())
    assert len(data["entries"]) == 1 and data["entries"][0]["version"] == rule.VERSION


def test_cache_only_missing_is_unchecked(tmp_path, fake_classify):
    out = Checker(tmp_path / "audio-check.json", META, ID).check("d1t01.mp3")
    assert out == Outcome("unchecked", None, None, error="no cached verdict")
    assert fake_classify.calls == []


def test_unreadable_cache_online_recomputes_and_cache_only_is_unchecked(tmp_path, fake_classify):
    p = tmp_path / "audio-check.json"
    p.write_text("{not json")
    out = Checker(p, META, ID).check("d1t01.mp3")
    assert out == Outcome("unchecked", None, None, error="verdict cache unreadable")
    chk = Checker(p, META, ID, ia=FakeIA(), tmp_dir=tmp_path)
    assert chk.check("d1t01.mp3") == Outcome("music", 300, 0.9)
    assert len(chk.new_verdicts) == 1
    # write_verdicts overwrites an unreadable file
    write_verdicts(p, chk.new_verdicts)
    assert lookup(p, ID, "d1t01.mp3", META).verdict == "music"


@pytest.mark.parametrize("text", ["[]", '{"entries": {}}', '{"entries": [1]}', '{}',
                                  '{"entries": [{"identifier": "x"}]}'])
def test_wrong_shape_is_unreadable(tmp_path, text):
    p = tmp_path / "audio-check.json"
    p.write_text(text)
    with pytest.raises(CacheUnreadable):
        lookup(p, ID, "d1t01.mp3", META)


def test_binary_garbage_is_unreadable_not_a_raise(tmp_path, fake_classify):
    p = tmp_path / "audio-check.json"
    p.write_bytes(b"\xff\xfe\x00garbage")
    with pytest.raises(CacheUnreadable) as ei:
        lookup(p, ID, "d1t01.mp3", META)
    assert not isinstance(ei.value, CacheReadError)
    assert Checker(p, META, ID).check("d1t01.mp3") == Outcome(
        "unchecked", None, None, error="verdict cache unreadable")
    chk = Checker(p, META, ID, ia=FakeIA(), tmp_dir=tmp_path / "tmp")
    assert chk.check("d1t01.mp3").check == "music"
    write_verdicts(p, chk.new_verdicts)  # corrupt content is overwritten
    assert lookup(p, ID, "d1t01.mp3", META).verdict == "music"


def test_unreadable_read_is_never_overwritten(tmp_path, monkeypatch, fake_classify):
    p = tmp_path / "audio-check.json"
    _store(p, "d1t01.mp3", verdict="music")
    _store(p, "d1t02.mp3", verdict="junk", run_sec=0, frac=0.0)
    before = p.read_bytes()
    real = Path.read_bytes

    def denied(self):
        if self == p:
            raise PermissionError(13, "Permission denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", denied)
    with pytest.raises(CacheReadError):
        lookup(p, ID, "d1t01.mp3", META)
    assert Checker(p, META, ID).check("d1t01.mp3").error == "verdict cache unreadable"
    chk = Checker(p, META, ID, ia=FakeIA(), tmp_dir=tmp_path / "tmp")
    assert chk.check("d1t03.mp3").check == "music"  # online: a miss, recomputed
    with pytest.raises(CacheReadError):
        write_verdicts(p, chk.new_verdicts)
    monkeypatch.undo()
    assert p.read_bytes() == before
    assert [x.name for x in tmp_path.iterdir() if x.name != "tmp"] == ["audio-check.json"]


def test_unusable_tmp_dir_is_unchecked_not_a_raise(tmp_path, fake_classify):
    ia = FakeIA()
    chk = Checker(tmp_path / "audio-check.json", META, ID, ia=ia, tmp_dir=Path("/dev/null/zz"))
    out = chk.check("d1t01.mp3")
    assert out.check == "unchecked" and out.error.startswith("fetch failed")
    assert ia.calls == [] and fake_classify.calls == [] and chk.new_verdicts == []


def test_unusable_tmp_dir_on_stale_keeps_stale(tmp_path, fake_classify):
    p = tmp_path / "audio-check.json"
    _store(p, "d1t01.mp3", verdict="music", version="old")
    out = Checker(p, META, ID, ia=FakeIA(), tmp_dir=Path("/dev/null/zz")).check("d1t01.mp3")
    assert (out.check, out.stale) == ("music", True) and "temp dir" in out.error


def test_lookup_missing_file_is_none(tmp_path):
    assert lookup(tmp_path / "nope.json", ID, "d1t01.mp3", META) is None


def test_online_miss_fetches_classifies_and_deletes_temp(tmp_path, fake_classify):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    ia = FakeIA()
    chk = Checker(tmp_path / "audio-check.json", META, ID, ia=ia, tmp_dir=tmp)
    assert chk.check("d1t01.mp3") == Outcome("music", 300, 0.9)
    assert ia.calls == [(ID, "d1t01.mp3", "aaa")]
    assert ia.seen_dests[0].is_relative_to(tmp)
    assert not ia.seen_dests[0].exists()
    assert list(tmp.iterdir()) == []
    assert chk.new_verdicts == [(identity(ID, "d1t01.mp3", META), Result("music", 300, 0.9))]
    assert not (tmp_path / "audio-check.json").exists()  # check itself writes nothing


def test_online_miss_private_tempdir_when_none(tmp_path, fake_classify):
    ia = FakeIA()
    Checker(tmp_path / "audio-check.json", META, ID, ia=ia).check("d1t01.mp3")
    assert not ia.seen_dests[0].exists()
    assert not ia.seen_dests[0].parent.exists()


def test_fetch_failure_is_unchecked_with_reason(tmp_path, fake_classify):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    chk = Checker(tmp_path / "audio-check.json", META, ID, ia=FakeIA(exc=OSError("no route")), tmp_dir=tmp)
    out = chk.check("d1t01.mp3")
    assert out.check == "unchecked" and out.run_sec is None and out.frac is None
    assert "no route" in out.error and out.error.startswith("fetch failed")
    assert chk.new_verdicts == [] and list(tmp.iterdir()) == []
    assert fake_classify.calls == []


@pytest.mark.parametrize("exc,prefix", [
    (decode.DecodeError("not MP3/FLAC"), "decode failed"),
    (model.ClassifierUnavailable("no onnxruntime"), "classifier unavailable"),
    (ValueError("boom"), "audio check failed"),
])
def test_classify_failures_are_unchecked_with_reason(tmp_path, fake_classify, exc, prefix):
    fake_classify.results["d1t01.mp3"] = exc
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    chk = Checker(tmp_path / "audio-check.json", META, ID, ia=FakeIA(), tmp_dir=tmp)
    out = chk.check("d1t01.mp3")
    assert out.check == "unchecked" and out.error.startswith(prefix)
    assert str(exc) in out.error
    assert chk.new_verdicts == [] and list(tmp.iterdir()) == []


def test_same_title_files_keep_separate_verdicts(tmp_path, fake_classify):
    p = tmp_path / "audio-check.json"
    fake_classify.results.update({"d1t01.mp3": Result("junk", 5, 0.1),
                                  "d1t02.mp3": Result("music", 400, 0.95),
                                  "d1t03.mp3": Result("junk", 0, 0.0)})
    chk = Checker(p, META, ID, ia=FakeIA(), tmp_dir=tmp_path)
    outs = [chk.check(f) for f in ("d1t01.mp3", "d1t02.mp3", "d1t03.mp3")]
    assert [o.check for o in outs] == ["junk", "music", "junk"]
    write_verdicts(p, chk.new_verdicts)
    assert [lookup(p, ID, f, META).verdict for f in ("d1t01.mp3", "d1t02.mp3", "d1t03.mp3")] \
        == ["junk", "music", "junk"]
    assert len(json.loads(p.read_text())["entries"]) == 3


def test_identity_uses_md5_and_falls_back_to_size_without_md5():
    assert identity(ID, "d1t01.mp3", META) == {"identifier": ID, "filename": "d1t01.mp3", "md5": "aaa"}
    assert identity(ID, "nomd5.mp3", META) == {"identifier": ID, "filename": "nomd5.mp3", "size": "4000"}
    assert identity(ID, "absent.mp3", META) == {"identifier": ID, "filename": "absent.mp3", "size": None}
    assert identity(ID, "x.mp3", {}) == {"identifier": ID, "filename": "x.mp3", "size": None}


def test_lookup_misses_when_md5_changed(tmp_path):
    p = tmp_path / "audio-check.json"
    _store(p, "d1t01.mp3")
    changed = {"files": [{"name": "d1t01.mp3", "md5": "zzz"}]}
    assert lookup(p, ID, "d1t01.mp3", changed) is None
    assert lookup(p, ID, "d1t01.mp3", META) is not None


def test_write_is_atomic_merge(tmp_path, monkeypatch):
    p = tmp_path / "audio-check.json"
    write_verdicts(p, [(identity(ID, "d1t01.mp3", META), Result("junk", 1, 0.1))], now="T1")
    write_verdicts(p, [(identity(ID, "d1t02.mp3", META), Result("music", 200, 0.8))], now="T2")
    calls = []
    import llama.workspace as ws_mod
    real = ws_mod.atomic_write_text
    monkeypatch.setattr(ws_mod, "atomic_write_text", lambda path, text: (calls.append(path), real(path, text)))
    write_verdicts(p, [(identity(ID, "d1t01.mp3", META), Result("music", 150, 0.7))], now="T3")
    assert calls == [p]
    a = lookup(p, ID, "d1t01.mp3", META)
    b = lookup(p, ID, "d1t02.mp3", META)
    assert (a.verdict, a.run_sec, a.frac, a.version, a.checked_at) == ("music", 150, 0.7, rule.VERSION, "T3")
    assert (b.verdict, b.checked_at) == ("music", "T2")
    assert len(json.loads(p.read_text())["entries"]) == 2
    assert [x.name for x in tmp_path.iterdir()] == ["audio-check.json"]


def test_write_default_clock_is_iso(tmp_path):
    from datetime import datetime
    p = tmp_path / "audio-check.json"
    write_verdicts(p, [(identity(ID, "d1t01.mp3", META), Result("junk", 1, 0.1))])
    datetime.fromisoformat(lookup(p, ID, "d1t01.mp3", META).checked_at.replace("Z", "+00:00"))


def test_lookup_imports_no_numpy_or_classify(tmp_path):
    p = tmp_path / "audio-check.json"
    _store(p, "d1t01.mp3")
    code = (
        "import sys, json\n"
        "from pathlib import Path\n"
        "import llama.audio_check.cache as c\n"
        f"meta = json.loads({json.dumps(json.dumps(META))})\n"
        f"assert c.identity({ID!r}, 'd1t01.mp3', meta)['md5'] == 'aaa'\n"
        f"assert c.lookup(Path({str(p)!r}), {ID!r}, 'd1t01.mp3', meta).verdict == 'music'\n"
        "print(sorted({'numpy', 'onnxruntime', 'miniaudio', 'llama.audio_check.classify'} & set(sys.modules)))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]", out.stdout + out.stderr


def test_cache_not_a_stage_artifact(tmp_path):
    ws = ShowWorkspace(tmp_path)
    assert ws.audio_check == tmp_path / "audio-check.json"
    assert ws.audio_check not in sum((show_stage_artifacts(ws, s) for s in SHOW_STAGE_ORDER), [])


def _raw_entry(**kw):
    entry = {"identifier": ID, "filename": "d1t01.mp3", "md5": "aaa", "verdict": "music",
             "run_sec": 300, "frac": 0.9, "version": rule.VERSION,
             "checked_at": "2026-11-14T00:00:00Z"}
    entry.update(kw)
    return entry


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_frac_is_corrupt_content(tmp_path, fake_classify, token):
    # json.loads accepts these tokens; a non-finite frac would raise later (music_flag's
    # int(round(...))) or write non-standard JSON into arm rows and members.json.
    p = tmp_path / "audio-check.json"
    p.write_text('{"entries": [{"identifier": "%s", "filename": "d1t01.mp3", "md5": "aaa", '
                 '"verdict": "music", "run_sec": 300, "frac": %s, "version": "%s", '
                 '"checked_at": "2026-11-14T00:00:00Z"}]}' % (ID, token, rule.VERSION))
    with pytest.raises(CacheUnreadable) as ei:
        lookup(p, ID, "d1t01.mp3", META)
    assert not isinstance(ei.value, CacheReadError)
    assert Checker(p, META, ID).check("d1t01.mp3") == Outcome(
        "unchecked", None, None, error="verdict cache unreadable")
    chk = Checker(p, META, ID, ia=FakeIA(), tmp_dir=tmp_path / "tmp")
    assert chk.check("d1t01.mp3") == Outcome("music", 300, 0.9)   # online: recomputed
    write_verdicts(p, chk.new_verdicts)                            # corrupt content: overwritten
    assert json.loads(p.read_text())["entries"][0]["frac"] == 0.9


@pytest.mark.parametrize("bad", [{"md5": ["x"]}, {"md5": 5}, {"md5": None},
                                 {"md5": None, "size": ["4000"]}, {"md5": None, "size": True},
                                 {"md5": None, "size": {"n": 1}}, {"md5": None, "size": 1.5}])
def test_mistyped_identity_is_corrupt_content_and_overwritten(tmp_path, fake_classify, bad):
    entry = _raw_entry(**bad)
    if entry.get("md5") is None and "size" in bad:
        del entry["md5"]
    p = tmp_path / "audio-check.json"
    p.write_text(json.dumps({"entries": [entry]}))
    with pytest.raises(CacheUnreadable) as ei:
        lookup(p, ID, "d1t01.mp3", META)
    assert not isinstance(ei.value, CacheReadError)
    assert Checker(p, META, ID).check("d1t01.mp3").error == "verdict cache unreadable"
    chk = Checker(p, META, ID, ia=FakeIA(), tmp_dir=tmp_path / "tmp")
    assert chk.check("d1t01.mp3").check == "music"
    write_verdicts(p, chk.new_verdicts)               # no TypeError (unhashable list)
    assert lookup(p, ID, "d1t01.mp3", META).verdict == "music"


@pytest.mark.parametrize("ident", [{"md5": "aaa"}, {"size": "4000"}, {"size": 4000},
                                   {"size": None}])
def test_identity_types_the_writer_writes_are_readable(tmp_path, ident):
    entry = {k: v for k, v in _raw_entry().items() if k != "md5"}
    entry.update(ident)
    p = tmp_path / "audio-check.json"
    p.write_text(json.dumps({"entries": [entry]}))
    assert cache._read_entries(p) == [entry]
