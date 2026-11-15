"""`llama audio-prepass` (audio-check plan Task 9; spec 2026-11-14-junk-drop-audio-check,
"Replay and the rollout").

A temp library and a fake station dir; a fake classifier that reads its verdict out of
the file's bytes (`b"music 200 0.9"`), a fake archive.org client, and a fake
`read_duration` keyed by station file name. Nothing real is touched."""
import json
from pathlib import Path

import pytest

from llama.audio_check import cache, classify, model, prepass, rule
from llama.models import Show, Track
from llama.workspace import ShowWorkspace

IDENT = "band2001-01-01.aud"


def _verdict_bytes(verdict, run, frac) -> bytes:
    return f"{verdict} {run} {frac}".encode()


@pytest.fixture(autouse=True)
def fake_classifier(monkeypatch):
    seen: list[Path] = []

    def classify_file(path):
        path = Path(path)
        seen.append(path)
        text = path.read_bytes().decode()
        if text.startswith("CORRUPT"):
            from llama.audio_check import decode
            raise decode.DecodeError(f"{path.name} is not audio")
        v, r, f = text.split()
        return classify.Result(v, int(r), float(f))

    monkeypatch.setattr(classify, "classify_file", classify_file)
    monkeypatch.setattr(classify, "get_model", lambda: object())
    return seen


class FakeIA:
    def __init__(self, files: dict[str, tuple[str, bytes | None]]):
        # filename -> (length "m:ss" or seconds str, archive.org bytes or None = fetch fails)
        self.files = files
        self.downloads: list[str] = []

    def metadata(self, identifier):
        return {"files": [{"name": n, "md5": f"md5-{n}", "length": length}
                          for n, (length, _b) in self.files.items()]}

    def download_file(self, identifier, filename, dest, md5=None):
        self.downloads.append(filename)
        data = self.files.get(filename, (None, None))[1]
        if data is None:
            raise RuntimeError(f"download of {filename} failed: 503")
        Path(dest).write_bytes(data)
        return Path(dest)


def _env(tmp_path):
    root = tmp_path / "lib"
    (root / "shows").mkdir(parents=True)
    station = tmp_path / "station"
    station.mkdir()
    (station / "placeholder").mkdir()     # a mounted station is never empty
    return root, station, tmp_path / "out"


def _show(root, slug, titles, filenames=None, excluded=()):
    filenames = filenames or [f"t{i}.mp3" for i in range(1, len(titles) + 1)]
    d = root / "shows" / slug
    d.mkdir(parents=True)
    ws = ShowWorkspace(d)
    tracks = [Track(index=i, set="1", title=t, filename=f, duration_sec=300.0, title_source="tags")
              for i, (t, f) in enumerate(zip(titles, filenames), 1)]
    show = Show(performance_id=f"band/{slug}", identifier=IDENT, artist="Band",
                date="2001-01-01", tracks=tracks, excluded_files=list(excluded))
    ws.show.write_text(show.model_dump_json(indent=2))
    return ws


def _station(station, slug, titles, contents):
    out = station / slug
    (out / "audio").mkdir(parents=True)
    tracks = []
    for i, (t, c) in enumerate(zip(titles, contents), 1):
        name = f"{i:02d} - {t}.mp3"
        tracks.append({"index": i, "set": "1", "title": t, "filename": name, "duration_sec": 300.0})
        (out / "audio" / name).write_bytes(c)
    (out / "manifest.json").write_text(json.dumps(
        {"schema_version": 3, "source": {"identifier": IDENT}, "tracks": tracks,
         "dj_notes": None, "dj_audio": None}))
    return out


@pytest.fixture
def durations(monkeypatch):
    lengths: dict[str, float] = {}
    monkeypatch.setattr(prepass, "read_duration", lambda p: lengths.get(Path(p).name))
    return lengths


def _run(root, ia, out, station, **kw):
    msgs: list[str] = []
    rc = prepass.run(root, ia, out, station_root=station, echo=msgs.append, err=msgs.append, **kw)
    return rc, msgs


def _summary(out):
    return json.loads((out / "summary.json").read_text())


def _files(out):
    return {(r["slug"], r["source_file"]): r for r in _summary(out)["files"]}


def _cache(ws):
    return {e["filename"]: e for e in json.loads(ws.audio_check.read_text())["entries"]}


SONG = b"x"


def test_prepass_input_superset_includes_mid_show_intro(tmp_path, durations):
    root, station, out = _env(tmp_path)
    # "Intro" mid-show is no drop under rule B, but the pre-pass checks it anyway.
    ws = _show(root, "s1", ["Bertha", "Intro", "Sugaree", "Tuning"])
    ia = FakeIA({"t1.mp3": ("300", SONG), "t2.mp3": ("300", _verdict_bytes("junk", 0, 0.1)),
                 "t3.mp3": ("300", SONG), "t4.mp3": ("300", _verdict_bytes("music", 200, 0.9))})
    rc, _ = _run(root, ia, out, station)
    assert rc == 0
    files = _files(out)
    assert set(files) == {("s1", "t2.mp3"), ("s1", "t4.mp3")}
    assert files[("s1", "t2.mp3")]["outcome"] == "junk"
    assert files[("s1", "t4.mp3")]["outcome"] == "music"
    assert files[("s1", "t4.mp3")]["run_sec"] == 200
    assert sorted(ia.downloads) == ["t2.mp3", "t4.mp3"]   # no station copy: fetched
    c = _cache(ws)
    assert c["t4.mp3"]["verdict"] == "music" and c["t4.mp3"]["version"] == rule.VERSION
    assert c["t4.mp3"]["md5"] == "md5-t4.mp3"
    s = _summary(out)
    assert s["version"] == rule.VERSION and s["started_at"] and s["finished_at"]
    assert not (out / ".fetch").exists()                  # temp fetch dir removed


def test_prepass_pairs_same_title_drops_by_index(tmp_path, durations):
    root, station, out = _env(tmp_path)
    titles = ["Tune Up", "Bertha", "Tune Up", "Sugaree", "Tune Up"]
    ws = _show(root, "s1", titles)
    contents = [_verdict_bytes("junk", 10, 0.1), SONG, _verdict_bytes("music", 300, 0.95),
                SONG, _verdict_bytes("junk", 50, 0.3)]
    _station(station, "s1", titles, contents)
    for i, t in enumerate(titles, 1):
        durations[f"{i:02d} - {t}.mp3"] = 301.0
    ia = FakeIA({f"t{i}.mp3": ("300", None) for i in range(1, 6)})   # archive.org unused
    rc, _ = _run(root, ia, out, station)
    assert rc == 0 and ia.downloads == []
    files = _files(out)
    assert {k: (v["outcome"], v["run_sec"], v["audio"]) for k, v in files.items()} == {
        ("s1", "t1.mp3"): ("junk", 10, "station"),
        ("s1", "t3.mp3"): ("music", 300, "station"),
        ("s1", "t5.mp3"): ("junk", 50, "station")}
    c = _cache(ws)
    assert (c["t1.mp3"]["verdict"], c["t3.mp3"]["verdict"], c["t5.mp3"]["verdict"]) == \
        ("junk", "music", "junk")


def test_prepass_rejects_station_file_with_wrong_length_and_fetches(tmp_path, durations,
                                                                    fake_classifier):
    root, station, out = _env(tmp_path)
    from llama.stages.package import DURATION_TOLERANCE_S
    titles = ["Tuning", "Bertha", "Crowd"]
    _show(root, "s1", titles)
    _station(station, "s1", titles, [_verdict_bytes("music", 999, 1.0), SONG,
                                     _verdict_bytes("music", 999, 1.0)])
    durations["01 - Tuning.mp3"] = 300.0 + DURATION_TOLERANCE_S + 0.5   # just outside
    durations["03 - Crowd.mp3"] = 300.0 + DURATION_TOLERANCE_S          # at the edge: accepted
    ia = FakeIA({"t1.mp3": ("5:00", _verdict_bytes("junk", 0, 0.0)), "t2.mp3": ("300", SONG),
                 "t3.mp3": ("300", None)})
    rc, _ = _run(root, ia, out, station)
    assert rc == 0
    files = _files(out)
    assert files[("s1", "t1.mp3")]["outcome"] == "junk"
    assert files[("s1", "t1.mp3")]["audio"] == "archive.org"
    assert files[("s1", "t3.mp3")]["outcome"] == "music"
    assert files[("s1", "t3.mp3")]["audio"] == "station"
    assert ia.downloads == ["t1.mp3"]
    assert not any(p.parent == station / "s1" / "audio" and p.name == "01 - Tuning.mp3"
                   for p in fake_classifier)


def test_prepass_station_copy_without_metadata_length_is_fetched(tmp_path, durations):
    root, station, out = _env(tmp_path)
    _show(root, "s1", ["Tuning", "Bertha"])
    _station(station, "s1", ["Tuning", "Bertha"], [_verdict_bytes("music", 999, 1.0), SONG])
    durations["01 - Tuning.mp3"] = 300.0
    ia = FakeIA({"t1.mp3": (None, _verdict_bytes("junk", 1, 0.0)), "t2.mp3": ("300", SONG)})
    _run(root, ia, out, station)
    assert _files(out)[("s1", "t1.mp3")]["audio"] == "archive.org"


def test_prepass_resumes_skipping_cached(tmp_path, durations, fake_classifier):
    root, station, out = _env(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha", "Crowd"])
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("music", 200, 0.9)), "t2.mp3": ("300", SONG),
                 "t3.mp3": ("300", None)})                      # t3 fails the first time
    _run(root, ia, out, station)
    assert _files(out)[("s1", "t3.mp3")]["outcome"] == "failed"
    ia.files["t3.mp3"] = ("300", _verdict_bytes("junk", 0, 0.0))
    ia.downloads.clear()
    fake_classifier.clear()
    rc, _ = _run(root, ia, out, station)
    assert rc == 0
    assert ia.downloads == ["t3.mp3"]                           # t1 not fetched again
    assert len(fake_classifier) == 1
    assert set(_cache(ws)) == {"t1.mp3", "t3.mp3"}


def test_prepass_stale_version_is_recomputed(tmp_path, durations):
    root, station, out = _env(tmp_path)
    ws = _show(root, "s1", ["Tuning"])
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})
    ws.audio_check.write_text(json.dumps({"entries": [
        {"identifier": IDENT, "filename": "t1.mp3", "md5": "md5-t1.mp3", "verdict": "music",
         "run_sec": 200, "frac": 0.9, "version": "old", "checked_at": "2026-01-01T00:00:00Z"}]}))
    _run(root, ia, out, station)
    assert ia.downloads == ["t1.mp3"]
    r = _files(out)[("s1", "t1.mp3")]
    assert (r["outcome"], r["cached"]) == ("junk", False)
    assert _cache(ws)["t1.mp3"]["version"] == rule.VERSION


def test_prepass_summary_lists_cached_with_stored_verdict(tmp_path, durations):
    root, station, out = _env(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Bertha"])
    ia = FakeIA({"t1.mp3": ("300", None), "t2.mp3": ("300", SONG)})
    ident = cache.identity(IDENT, "t1.mp3", ia.metadata(IDENT))
    cache.write_verdicts(ws.audio_check, [(ident, classify.Result("music", 250, 0.8))])
    rc, msgs = _run(root, ia, out, station)
    assert rc == 0 and ia.downloads == []
    r = _files(out)[("s1", "t1.mp3")]
    assert (r["outcome"], r["run_sec"], r["frac"], r["cached"], r["error"]) == \
        ("music", 250, 0.8, True, None)
    assert set(r) >= {"slug", "source_file", "outcome", "run_sec", "frac", "error", "cached"}
    assert "1 already cached" in msgs[-1]


def test_prepass_unavailable_exits_3_writes_nothing(tmp_path, monkeypatch, durations):
    root, station, out = _env(tmp_path)
    ws = _show(root, "s1", ["Tuning"])
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})

    def unavailable():
        raise model.ClassifierUnavailable("no onnxruntime")
    monkeypatch.setattr(classify, "get_model", unavailable)
    rc, msgs = _run(root, ia, out, station)
    assert rc == 3
    assert msgs == ["audio-prepass: classifier unavailable (no onnxruntime); nothing written"]
    assert not out.exists() and not ws.audio_check.exists() and ia.downloads == []


def test_prepass_unavailable_cli_exit_3(tmp_path, monkeypatch):
    from conftest import cli_invoke
    root, station, out = _env(tmp_path)
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{root}"\ndelivery_path = "{station}"\n')

    def unavailable():
        raise model.ClassifierUnavailable("no model")
    monkeypatch.setattr(classify, "get_model", unavailable)
    r = cli_invoke(cfg, "audio-prepass", "--out", str(out))
    assert r.exit_code == 3
    assert "audio-prepass: classifier unavailable (no model); nothing written" in r.output
    assert not out.exists()


def test_prepass_failure_recorded_with_reason(tmp_path, durations):
    root, station, out = _env(tmp_path)
    ws = _show(root, "s1", ["Tuning", "Crowd", "Bertha"])
    ia = FakeIA({"t1.mp3": ("300", None), "t2.mp3": ("300", b"CORRUPT"),
                 "t3.mp3": ("300", SONG)})
    rc, _ = _run(root, ia, out, station)
    assert rc == 0
    files = _files(out)
    assert files[("s1", "t1.mp3")]["outcome"] == "failed"
    assert files[("s1", "t1.mp3")]["error"].startswith("fetch failed: download of t1.mp3")
    assert files[("s1", "t2.mp3")]["outcome"] == "failed"
    assert files[("s1", "t2.mp3")]["error"].startswith("decode failed:")
    assert not ws.audio_check.exists()                 # failures are never cached


def test_prepass_cache_read_error_recorded_and_run_continues(tmp_path, durations, monkeypatch):
    root, station, out = _env(tmp_path)
    ws1 = _show(root, "s1", ["Tuning"])
    ws2 = _show(root, "s2", ["Tuning"])
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})
    real = cache.write_verdicts

    def flaky(path, entries, **kw):
        if Path(path) == ws1.audio_check:
            raise cache.CacheReadError("cannot read: EIO")
        return real(path, entries, **kw)
    monkeypatch.setattr(cache, "write_verdicts", flaky)
    rc, _ = _run(root, ia, out, station)
    assert rc == 0
    files = _files(out)
    assert files[("s1", "t1.mp3")]["outcome"] == "failed"
    assert "cannot read: EIO" in files[("s1", "t1.mp3")]["error"]
    assert files[("s2", "t1.mp3")]["outcome"] == "junk"
    assert ws2.audio_check.exists() and not ws1.audio_check.exists()


def test_prepass_arm_adds_drops(tmp_path, durations):
    root, station, out = _env(tmp_path)
    # t2's title is a song today; the arm's new titling makes it a drop.
    _show(root, "s1", ["Tuning", "Bertha", "Sugaree"])
    arm = tmp_path / "arm.json"
    arm.write_text(json.dumps({"sha": "x", "shows": {"s1": {"junk_drops": [
        {"filename": "t2.mp3", "title": "Crowd", "check": "unchecked", "run_sec": None,
         "frac": None, "check_error": "no cached verdict"},
        {"filename": "t1.mp3", "title": "Tuning"}]}}}))
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0)),
                 "t2.mp3": ("300", _verdict_bytes("junk", 5, 0.1)), "t3.mp3": ("300", SONG)})
    rc, _ = _run(root, ia, out, station, arm=arm)
    assert rc == 0
    assert set(_files(out)) == {("s1", "t1.mp3"), ("s1", "t2.mp3")}
    assert sorted(ia.downloads) == ["t1.mp3", "t2.mp3"]          # t1 checked once


def test_prepass_from_skips_adds_reapply_only_drops(tmp_path, durations):
    root, station, out = _env(tmp_path)
    odd = "Band 2001, 01, 01 t2.mp3"                    # a filename containing ", "
    _show(root, "s1", ["Bertha", "Sugaree", "Scarlet"], filenames=["t1.mp3", odd, "t3.mp3"])
    progress = tmp_path / "progress.jsonl"
    progress.write_text("\n".join([
        json.dumps({"slug": "s1", "outcome": f"skipped: unchecked drop ({odd}, t3.mp3)",
                    "retryable": True}),
        "{not json",
        json.dumps({"slug": "s9", "outcome": "unchanged", "retryable": False}),
    ]) + "\n")
    ia = FakeIA({"t1.mp3": ("300", SONG), odd: ("300", _verdict_bytes("music", 150, 0.7)),
                 "t3.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})
    rc, _ = _run(root, ia, out, station, from_skips=progress)
    assert rc == 0
    files = _files(out)
    assert set(files) == {("s1", odd), ("s1", "t3.mp3")}
    assert files[("s1", odd)]["outcome"] == "music"


def test_split_names_matches_known_names_not_commas():
    known = {"a, b.mp3", "a", "b.mp3", "c.mp3"}
    assert prepass.split_names("a, b.mp3, c.mp3", known) in (["a, b.mp3", "c.mp3"],
                                                              ["a", "b.mp3", "c.mp3"])
    assert prepass.split_names("a, b.mp3", {"a, b.mp3", "c.mp3"}) == ["a, b.mp3"]
    assert prepass.split_names("x.mp3", {"a"}) is None
    assert prepass.split_names("", {"a"}) is None


def test_prepass_from_skips_unmatched_names_fail_loudly(tmp_path, durations):
    root, station, out = _env(tmp_path)
    _show(root, "s1", ["Bertha"])
    progress = tmp_path / "progress.jsonl"
    progress.write_text(json.dumps({"slug": "s1", "outcome": "skipped: unchecked drop (zz.mp3)"}) + "\n")
    _run(root, FakeIA({"t1.mp3": ("300", SONG)}), out, station, from_skips=progress)
    r = _files(out)[("s1", "zz.mp3")]
    assert r["outcome"] == "failed" and "do not match" in r["error"]


def test_prepass_slug_restricts_and_writes_nothing_else(tmp_path, durations):
    root, station, out = _env(tmp_path)
    _show(root, "s1", ["Tuning"])
    ws2 = _show(root, "s2", ["Tuning"])
    _station(station, "s2", ["Tuning"], [_verdict_bytes("junk", 0, 0.0)])
    durations["01 - Tuning.mp3"] = 300.0
    before_station = sorted((p, p.stat().st_mtime_ns) for p in station.rglob("*"))
    lib_before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})
    _run(root, ia, out, station, slugs=["s2"])
    assert set(_files(out)) == {("s2", "t1.mp3")}
    assert sorted((p, p.stat().st_mtime_ns) for p in station.rglob("*")) == before_station
    after = {p for p in root.rglob("*") if p.is_file()}
    assert after - set(lib_before) == {ws2.audio_check, ws2.lock}
    assert all(p.read_bytes() == b for p, b in lib_before.items())


def test_prepass_refuses_out_inside_station(tmp_path, durations):
    root, station, out = _env(tmp_path)
    rc, msgs = _run(root, FakeIA({}), station / "x", station)
    assert rc == 2 and "overlaps the station root" in msgs[0]
    assert not (station / "x").exists()


def test_prepass_summary_valid_after_each_show(tmp_path, durations, monkeypatch):
    root, station, out = _env(tmp_path)
    _show(root, "s1", ["Tuning"])
    _show(root, "s2", ["Tuning"])
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})
    real = prepass._one_show
    calls = []

    def stop_second(ws, slug, *a):
        calls.append(slug)
        if slug == "s2":
            snap = _summary(out)
            assert snap["finished_at"] is None
            assert [r["slug"] for r in snap["files"]] == ["s1"]
            raise KeyboardInterrupt
        return real(ws, slug, *a)
    monkeypatch.setattr(prepass, "_one_show", stop_second)
    with pytest.raises(KeyboardInterrupt):
        _run(root, ia, out, station)
    assert [r["slug"] for r in _summary(out)["files"]] == ["s1"]
    assert not (out / ".fetch").exists()


# --- fix round 1: station gate (R11) and the merged summary (R10) ---

@pytest.mark.parametrize("state,expect", [
    ("none", "audio-prepass: no delivery_path in config: the station root is needed "
             "(set delivery_path); nothing written"),
    ("missing", "is unreadable (is the station mounted?); nothing written"),
    ("empty", "is empty (is the station mounted?); nothing written"),
    ("dotfiles", "is empty (is the station mounted?); nothing written"),
])
def test_prepass_refuses_unusable_station_root(tmp_path, durations, monkeypatch, state, expect):
    root, station, out = _env(tmp_path)
    ws = _show(root, "s1", ["Tuning"])
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})
    models = []
    monkeypatch.setattr(classify, "get_model", lambda: models.append(1))
    bare = tmp_path / "mnt"
    if state == "none":
        st = None
    elif state == "missing":
        st = tmp_path / "nowhere"
    else:
        bare.mkdir()
        if state == "dotfiles":
            (bare / ".DS_Store").write_text("")
        st = bare
    rc, msgs = _run(root, ia, out, st)
    assert rc == 2
    assert len(msgs) == 1 and msgs[0].endswith(expect) and msgs[0].startswith("audio-prepass: ")
    assert models == []                                  # refused before the model loads
    assert not out.exists() and not ws.audio_check.exists() and ia.downloads == []


def test_prepass_cli_refuses_without_delivery_path(tmp_path):
    from conftest import cli_invoke
    root, station, out = _env(tmp_path)
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{root}"\n')
    r = cli_invoke(cfg, "audio-prepass", "--out", str(out))
    assert r.exit_code == 2 and "no delivery_path in config" in r.output
    assert not out.exists()


def test_prepass_slug_retry_keeps_other_shows_rows(tmp_path, durations):
    root, station, out = _env(tmp_path)
    _show(root, "s1", ["Tuning"])
    _show(root, "s2", ["Tuning", "Crowd"])
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0)), "t2.mp3": ("300", None)})
    _run(root, ia, out, station)
    first = _summary(out)
    assert first["finished_at"] and set(_files(out)) == {("s1", "t1.mp3"), ("s2", "t1.mp3"),
                                                         ("s2", "t2.mp3")}
    assert _files(out)[("s2", "t2.mp3")]["outcome"] == "failed"
    ia.files["t2.mp3"] = ("300", _verdict_bytes("music", 200, 0.9))
    rc, msgs = _run(root, ia, out, station, slugs=["s2"])
    assert rc == 0
    s = _summary(out)
    assert s["started_at"] >= first["started_at"] and s["finished_at"]
    files = _files(out)
    assert set(files) == {("s1", "t1.mp3"), ("s2", "t1.mp3"), ("s2", "t2.mp3")}
    assert files[("s1", "t1.mp3")] == {r["source_file"]: r for r in first["files"]
                                       if r["slug"] == "s1"}["t1.mp3"]       # kept as is
    assert files[("s2", "t2.mp3")]["outcome"] == "music"                     # replaced
    assert files[("s2", "t1.mp3")]["cached"] is True                         # replaced
    assert [(r["slug"], r["source_file"]) for r in s["files"]] == \
        [(r["slug"], r["source_file"]) for r in first["files"]]              # order kept
    assert "summary holds 3 file(s), 0 failed, 1 show(s) with a music verdict" in msgs[-1]


def test_prepass_interrupted_run_leaves_finished_at_null(tmp_path, durations, monkeypatch,
                                                       capsys):
    root, station, out = _env(tmp_path)
    _show(root, "s1", ["Tuning"])
    _show(root, "s2", ["Tuning"])
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})
    _run(root, ia, out, station)                     # a full run first: finished_at set
    assert _summary(out)["finished_at"]
    real = prepass._one_show

    def stop_second(ws, slug, *a):
        if slug == "s2":
            raise KeyboardInterrupt
        return real(ws, slug, *a)
    monkeypatch.setattr(prepass, "_one_show", stop_second)
    with pytest.raises(KeyboardInterrupt):
        _run(root, ia, out, station)
    s = _summary(out)
    assert s["finished_at"] is None
    assert {(r["slug"], r["source_file"]) for r in s["files"]} == {("s1", "t1.mp3"),
                                                                   ("s2", "t1.mp3")}
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    import audio_check_population as pop
    capsys.readouterr()
    assert pop.main(["--summary", str(out / "summary.json")]) == 1
    assert "INCOMPLETE: summary.json has no finished_at" in capsys.readouterr().out


@pytest.mark.parametrize("content", ["{not json", '{"files": "x"}', '{"files": [{"slug": 1}]}', "[]"])
def test_prepass_corrupt_prior_summary_exits_2(tmp_path, durations, content):
    root, station, out = _env(tmp_path)
    ws = _show(root, "s1", ["Tuning"])
    out.mkdir()
    (out / "summary.json").write_text(content)
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})
    rc, msgs = _run(root, ia, out, station)
    assert rc == 2 and str(out / "summary.json") in msgs[0]
    assert (out / "summary.json").read_text() == content       # never discarded
    assert not ws.audio_check.exists() and ia.downloads == []


# --- fix round 2: a prior summary of another version never merges (R12) ---

@pytest.mark.parametrize("version,shown", [("yamnet-onnx-0/rule-old", "yamnet-onnx-0/rule-old"),
                                           (None, "missing"), (7, "missing")])
def test_prepass_prior_summary_of_another_version_exits_2(tmp_path, durations, version, shown):
    root, station, out = _env(tmp_path)
    ws = _show(root, "s1", ["Tuning"])
    out.mkdir()
    doc = {"started_at": "a", "finished_at": "b", "files": [
        {"slug": "s9", "source_file": "x.mp3", "outcome": "music", "run_sec": 200,
         "frac": 0.9, "error": None, "cached": False}]}
    if version is not None:
        doc["version"] = version
    content = json.dumps(doc)
    (out / "summary.json").write_text(content)
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})
    rc, msgs = _run(root, ia, out, station)
    assert rc == 2 and len(msgs) == 1
    m = msgs[0]
    assert str(out / "summary.json") in m and f"version {shown}" in m
    assert rule.VERSION in m and "delete DIR to start a fresh summary" in m
    assert (out / "summary.json").read_text() == content
    assert not ws.audio_check.exists() and ia.downloads == []


def test_prepass_prior_summary_of_this_version_merges(tmp_path, durations):
    root, station, out = _env(tmp_path)
    _show(root, "s1", ["Tuning"])
    out.mkdir()
    prior = {"slug": "s9", "source_file": "x.mp3", "outcome": "music", "run_sec": 200,
             "frac": 0.9, "error": None, "cached": False}
    (out / "summary.json").write_text(json.dumps(
        {"version": rule.VERSION, "started_at": "a", "finished_at": "b", "files": [prior]}))
    rc, _ = _run(root, FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))}), out, station)
    assert rc == 0
    files = _files(out)
    assert files[("s9", "x.mp3")] == prior and ("s1", "t1.mp3") in files


def test_prepass_overwrites_mistyped_identity_instead_of_aborting(tmp_path, durations):
    # An unhashable md5 used to escape write_verdicts as a TypeError and abort the run.
    root, station, out = _env(tmp_path)
    ws = _show(root, "s1", ["Tuning"])
    _show(root, "s2", ["Tuning"])
    ia = FakeIA({"t1.mp3": ("300", _verdict_bytes("junk", 0, 0.0))})
    ws.audio_check.write_text(json.dumps({"entries": [
        {"identifier": IDENT, "filename": "t1.mp3", "md5": ["md5-t1.mp3"], "verdict": "music",
         "run_sec": 200, "frac": 0.9, "version": rule.VERSION,
         "checked_at": "2026-01-01T00:00:00Z"}]}))
    rc, _ = _run(root, ia, out, station)
    assert rc == 0 and _summary(out)["finished_at"] is not None
    files = _files(out)
    assert files[("s1", "t1.mp3")]["outcome"] == "junk"
    assert files[("s2", "t1.mp3")]["outcome"] == "junk"
    assert _cache(ws)["t1.mp3"]["md5"] == "md5-t1.mp3"
