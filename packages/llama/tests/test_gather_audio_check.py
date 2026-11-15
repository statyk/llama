"""The audio check wired into gather (spec
docs/superpowers/specs/2026-11-14-junk-drop-audio-check-design.md, "Where it runs and what
it writes"): each junk-title drop's outcome is recorded, a `music` outcome holds the show
under its own overrule kind, and nothing else changes. Strict surface: the kept track
list and the manifest never depend on the check.

Built on the canonical gd73-06-10 fixture (see test_gather_junk_drop.py)."""
import json
from pathlib import Path

import pytest

import llama.cli as cli
import llama.pipeline as pipeline
import llama.stages.gather as gather_mod
from llama import junk_titles
from llama.adjudicator.gate import OVERRULE_BAR
from llama.audio_check import cache, classify
from llama.audio_check.cache import CacheReadError, Outcome
from llama.models import Overrides, Show, ShowNotes
from llama.overrules import FlagKey, flag_key, records_for
from llama.replay import flag_family
from llama.stages.gather import compute_gather, run_gather
from llama.workspace import ShowWorkspace, read_model, write_artifact

from test_gather_junk_drop import F, IDENT, StubIA, _candidate, _md
from test_pipeline import JB_OFF, FakeIA, fake_providers

TUNING = {"d1t02": ("Tuning", "3:00")}
THREE = {"d1t02": ("Tuning", "1:00"), "d1t03": ("Crowd", "1:30"), "d2t02": ("Tuning", "2:00")}


class FakeChecker:
    """Scripted outcomes per filename; records what it was asked."""

    def __init__(self, outcomes, *, raises=None, new_verdicts=()):
        self.outcomes, self.raises = outcomes, raises or {}
        self.asked = []
        self.new_verdicts = list(new_verdicts)

    def check(self, filename):
        self.asked.append(filename)
        if filename in self.raises:
            raise self.raises[filename]
        return self.outcomes[filename]


def _factory(checker, calls=None):
    def factory(identifier, metadata):
        if calls is not None:
            calls.append((identifier, metadata))
        return checker
    return factory


def _gather(tmp_path, md, factory=None, overrides=None):
    sws = ShowWorkspace(tmp_path / "show")
    if overrides is not None:
        write_artifact(sws.overrides, overrides)
    return compute_gather(sws, StubIA(md), None, _candidate(), IDENT, checker_factory=factory)


MUSIC = Outcome("music", 550, 0.98)
JUNK = Outcome("junk", 12, 0.1)
UNCHECKED = Outcome("unchecked", None, None, error="fetch failed: boom")


def _three_outcomes():
    return {F["d1t02"]: MUSIC, F["d1t03"]: JUNK, F["d2t02"]: UNCHECKED}


def test_music_outcome_adds_hold_and_keeps_drop(tmp_path):
    base = _gather(tmp_path / "a", _md(TUNING))
    res = _gather(tmp_path / "b", _md(TUNING), _factory(FakeChecker({F["d1t02"]: MUSIC})))
    assert [t.model_dump() for t in res.show.tracks] == [t.model_dump() for t in base.show.tracks]
    assert F["d1t02"] not in [t.filename for t in res.show.tracks]
    new = [f for f in res.show.review_flags if f not in base.show.review_flags]
    assert len(new) == 1 and new[0].startswith(junk_titles.MUSIC_PREFIX)
    assert new[0].endswith(f"file {F['d1t02']}")
    assert new[0] == ("junk-title drop sounds like music: 'Tuning' (3:00) 9:10 continuous, "
                      "98% music, file gd73-06-10d1t02.mp3")
    assert res.show.needs_review is True
    (drop,) = res.junk_drops
    assert (drop.check, drop.run_sec, drop.frac, drop.check_error) == ("music", 550, 0.98, None)


def test_junk_outcome_changes_nothing(tmp_path):
    base = _gather(tmp_path / "a", _md(TUNING))
    res = _gather(tmp_path / "b", _md(TUNING), _factory(FakeChecker({F["d1t02"]: JUNK})))
    assert res.show.tracks == base.show.tracks
    assert res.show.review_flags == base.show.review_flags == []
    assert res.show.needs_review is False
    assert not any(n.startswith("audio check") for n in res.notes)
    assert res.junk_drops[0].check == "junk"


def test_unchecked_outcome_records_and_notes_but_never_holds(tmp_path):
    res = _gather(tmp_path, _md(TUNING), _factory(FakeChecker({F["d1t02"]: UNCHECKED})))
    assert res.show.needs_review is False and res.show.review_flags == []
    assert f"audio check skipped for {F['d1t02']}: fetch failed: boom" in res.notes
    (drop,) = res.junk_drops
    assert (drop.check, drop.run_sec, drop.frac, drop.check_error) == (
        "unchecked", None, None, "fetch failed: boom")


def test_no_checker_is_unchecked_with_a_note(tmp_path):
    res = _gather(tmp_path, _md(TUNING))
    assert res.notes.count(f"audio check skipped for {F['d1t02']}: no checker") == 1
    assert res.junk_drops[0].check_error == "no checker"
    assert res.new_verdicts == ()


def test_stale_verdict_is_noted_on_every_use(tmp_path):
    out = {F["d1t02"]: Outcome("music", 550, 0.98, stale=True),
           F["d1t03"]: Outcome("junk", 3, 0.0, error="stale verdict kept; recompute fetch failed: x",
                               stale=True),
           F["d2t02"]: JUNK}
    res = _gather(tmp_path, _md(THREE), _factory(FakeChecker(out)))
    stale = [n for n in res.notes if n.startswith("audio check used a stale verdict")]
    assert stale == [f"audio check used a stale verdict for {F['d1t02']}",
                     f"audio check used a stale verdict for {F['d1t03']}"]
    rows = {r["filename"]: r for r in res.show.excluded_files}
    assert rows[F["d1t03"]]["check"] == "junk" and "check_error" not in rows[F["d1t03"]]
    assert rows[F["d1t02"]]["check"] == "music"
    assert any(f.startswith(junk_titles.MUSIC_PREFIX) for f in res.show.review_flags)


def test_checker_not_built_when_nothing_dropped(tmp_path):
    calls = []
    res = _gather(tmp_path, _md(), _factory(FakeChecker({}), calls))
    assert calls == [] and res.junk_drops == ()
    assert not any(n.startswith("audio check") for n in res.notes)


def test_checker_built_once_with_identifier_and_metadata(tmp_path):
    calls = []
    md = _md(THREE)
    _gather(tmp_path, md, _factory(FakeChecker(_three_outcomes()), calls))
    assert len(calls) == 1
    assert calls[0][0] == IDENT and calls[0][1] == md


def _kept(res):
    return [t.model_dump() for t in res.show.tracks], res.show.set_breaks, res.kept_positions


@pytest.mark.parametrize("mode", ["music", "junk", "unchecked", "raise", "factory-raise",
                                  "factory-none", "garbage"])
def test_kept_track_list_identical_for_every_outcome(tmp_path, mode):
    base = _gather(tmp_path / "a", _md(THREE))
    if mode == "factory-raise":
        def factory(identifier, metadata):
            raise RuntimeError("no factory")
    elif mode == "factory-none":
        def factory(identifier, metadata):
            return None
    else:
        out = {"music": MUSIC, "junk": JUNK, "unchecked": UNCHECKED, "raise": None,
               "garbage": "not an outcome"}[mode]
        names = (F["d1t02"], F["d1t03"], F["d2t02"])
        raises = {n: RuntimeError("boom") for n in names} if mode == "raise" else None
        factory = _factory(FakeChecker({n: out for n in names}, raises=raises))
    res = _gather(tmp_path / "b", _md(THREE), factory)
    assert _kept(res) == _kept(base)
    assert [d.filename for d in res.junk_drops] == [d.filename for d in base.junk_drops]
    assert [(d.position, d.after_track, d.held) for d in res.junk_drops] == \
        [(d.position, d.after_track, d.held) for d in base.junk_drops]
    # Every drop row still carries what the manifest reads, unchanged.
    keys = ("filename", "reasons", "duration_sec", "title", "set", "after_track")
    assert [{k: r[k] for k in keys if k in r} for r in res.show.excluded_files] == \
        [{k: r[k] for k in keys if k in r} for r in base.show.excluded_files]
    if mode == "music":
        assert res.show.needs_review is True
    else:
        assert res.show.needs_review is False and res.show.review_flags == []


def test_checker_exception_is_unchecked_not_raise(tmp_path):
    checker = FakeChecker(_three_outcomes(), raises={F["d1t03"]: ValueError("kaput")})
    res = _gather(tmp_path, _md(THREE), _factory(checker))
    by = {d.filename: d for d in res.junk_drops}
    assert by[F["d1t03"]].check == "unchecked"
    assert by[F["d1t03"]].check_error == "audio check failed: ValueError: kaput"
    assert f"audio check skipped for {F['d1t03']}: audio check failed: ValueError: kaput" in res.notes
    # The other drops are still checked.
    assert by[F["d1t02"]].check == "music" and by[F["d2t02"]].check == "unchecked"
    assert checker.asked == [F["d1t02"], F["d1t03"], F["d2t02"]]

    def factory(identifier, metadata):
        raise OSError("cannot build")
    res = _gather(tmp_path / "f", _md(THREE), factory)
    assert {d.check for d in res.junk_drops} == {"unchecked"}
    assert {d.check_error for d in res.junk_drops} == {"audio check failed: OSError: cannot build"}


def test_excluded_row_carries_outcome(tmp_path):
    res = _gather(tmp_path, _md(THREE), _factory(FakeChecker(_three_outcomes())))
    rows = {r["filename"]: r for r in res.show.excluded_files if "junk title" in r["reasons"]}
    assert rows[F["d1t02"]] == {
        "filename": F["d1t02"], "reasons": ["junk title"], "duration_sec": 60.0,
        "title": "Tuning", "set": "1", "after_track": 1,
        "check": "music", "run_sec": 550, "frac": 0.98}
    assert rows[F["d1t03"]] == {
        "filename": F["d1t03"], "reasons": ["junk title"], "duration_sec": 90.0,
        "title": "Crowd", "set": "1", "after_track": 1,
        "check": "junk", "run_sec": 12, "frac": 0.1}
    assert rows[F["d2t02"]] == {
        "filename": F["d2t02"], "reasons": ["junk title"], "duration_sec": 120.0,
        "title": "Tuning", "set": "2", "after_track": 2,
        "check": "unchecked", "run_sec": None, "frac": None,
        "check_error": "fetch failed: boom"}


def test_new_verdicts_are_returned_not_written(tmp_path):
    nv = [({"identifier": IDENT, "filename": F["d1t02"], "md5": "x"},
           classify.Result("music", 550, 0.98))]
    res = _gather(tmp_path, _md(TUNING), _factory(FakeChecker({F["d1t02"]: MUSIC},
                                                              new_verdicts=nv)))
    assert res.new_verdicts == tuple(nv)
    assert not (tmp_path / "show" / "audio-check.json").exists()


# --- run_gather: the online checker and the cache write ---

class DownloadIA(StubIA):
    def __init__(self, md):
        super().__init__(md)
        self.downloads = []

    def download_file(self, identifier, filename, dest, md5=None):
        self.downloads.append(filename)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00" * 64)
        return dest


def _run(tmp_path, md, ia=None):
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, ia or DownloadIA(md), None, _candidate(), IDENT)
    return sws, show


def test_run_gather_writes_new_verdicts_to_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(classify, "classify_file", lambda p: classify.Result("music", 550, 0.98))
    md = _md(TUNING)
    ia = DownloadIA(md)
    sws, show = _run(tmp_path, md, ia)
    assert ia.downloads == [F["d1t02"]]
    got = cache.lookup(sws.audio_check, IDENT, F["d1t02"], md)
    assert (got.verdict, got.run_sec, got.frac) == ("music", 550, 0.98)
    assert any(f.startswith(junk_titles.MUSIC_PREFIX) for f in show.review_flags)
    row = next(r for r in show.excluded_files if r["filename"] == F["d1t02"])
    assert row["check"] == "music"
    # A second gather reads the cache and fetches nothing.
    ia2 = DownloadIA(md)
    run_gather(sws, ia2, None, _candidate(), IDENT, force=True)
    assert ia2.downloads == []


def test_run_gather_writes_cache_before_show_json_and_overwrites_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(classify, "classify_file", lambda p: classify.Result("junk", 3, 0.05))
    sws = ShowWorkspace(tmp_path / "show")
    sws.dir.mkdir(parents=True)
    sws.audio_check.write_text("{not json")
    order = []
    real_write, real_artifact = cache.write_verdicts, gather_mod.write_artifact
    monkeypatch.setattr(cache, "write_verdicts",
                        lambda p, e, **k: (order.append("cache"), real_write(p, e, **k))[1])
    monkeypatch.setattr(gather_mod, "write_artifact",
                        lambda p, m: (order.append(Path(p).name), real_artifact(p, m))[1])
    md = _md(TUNING)
    run_gather(sws, DownloadIA(md), None, _candidate(), IDENT)
    assert order.index("cache") < order.index("show.json")
    assert order.index("cache") < order.index("notes.json")
    got = cache.lookup(sws.audio_check, IDENT, F["d1t02"], md)
    assert got.verdict == "junk"


@pytest.mark.parametrize("exc", [OSError("disk full"), CacheReadError("cannot read x: EIO"),
                                 RuntimeError("odd")])
def test_run_gather_cache_write_failure_is_note_not_raise(tmp_path, monkeypatch, exc):
    monkeypatch.setattr(classify, "classify_file", lambda p: classify.Result("junk", 3, 0.05))

    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(cache, "write_verdicts", boom)
    sws, show = _run(tmp_path, _md(TUNING))
    notes = read_model(sws.notes, ShowNotes).gather
    assert f"audio check cache not written: {exc}" in notes
    assert sws.show.exists() and show.needs_review is False


def test_run_gather_download_failure_is_unchecked(tmp_path):
    sws, show = _run(tmp_path, _md(TUNING), StubIA(_md(TUNING)))   # no download_file at all
    row = next(r for r in show.excluded_files if r["filename"] == F["d1t02"])
    assert row["check"] == "unchecked" and row["check_error"].startswith("fetch failed: ")
    notes = read_model(sws.notes, ShowNotes).gather
    assert any(n.startswith(f"audio check skipped for {F['d1t02']}: fetch failed: ") for n in notes)
    assert not sws.audio_check.exists()
    assert show.needs_review is False


# --- strict surface (2): the manifest is unchanged by the check ---

class DropIA(FakeIA):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        by_name = {F[k]: v for k, v in THREE.items()}
        for f in self.fixture["files"]:
            if f["name"] in by_name:
                f["title"], f["length"] = by_name[f["name"]]


def _package_end_to_end(root: Path, monkeypatch, checker_builder, overrules) -> Path:
    root.mkdir()
    (root / "config.toml").write_text(f'root = "{root}"\n{JB_OFF}')
    show_dir = root / "shows" / "gratefuldead-1973-06-10"
    write_artifact(ShowWorkspace(show_dir).overrides, Overrides(overrules=overrules))
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", DropIA)
    monkeypatch.setattr(gather_mod, "_online_checker", checker_builder)
    from typer.testing import CliRunner
    result = CliRunner().invoke(cli.app, ["--config", str(root / "config.toml"), "get",
                                          "GD 1973 best soundboard", "--auto", "--name", "t"])
    assert result.exit_code == 0, result.output
    return show_dir


def test_manifest_unchanged_by_audio_check(tmp_path, monkeypatch):
    # The music hold's overrule, recorded through the overrides API from a real gather.
    probe = _gather(tmp_path / "probe", DropIA().fixture, _factory(FakeChecker(_three_outcomes())))
    music = [f for f in probe.show.review_flags if f.startswith(junk_titles.MUSIC_PREFIX)]
    assert len(music) == 1 and probe.show.review_flags == music
    rules = records_for(music, probe.show, source="fix", at="2026-11-14T00:00:00Z")
    assert [r.kind for r in rules] == ["junk-music"]

    without = _package_end_to_end(tmp_path / "a", monkeypatch, lambda ws, ia: None, rules)
    with_ = _package_end_to_end(
        tmp_path / "b", monkeypatch,
        lambda ws, ia: _factory(FakeChecker(_three_outcomes())), rules)

    # The checker really ran in the second run: its outcomes are in show.json.
    shown = json.loads((with_ / "show.json").read_text())
    checks = {r["filename"]: r.get("check") for r in shown["excluded_files"]
              if "junk title" in r["reasons"]}
    assert checks == {F["d1t02"]: "music", F["d1t03"]: "junk", F["d2t02"]: "unchecked"}
    assert any(n.startswith("overruled: " + junk_titles.MUSIC_PREFIX)
               for n in read_model(ShowWorkspace(with_).notes, ShowNotes).gather)
    assert shown["needs_review"] is False
    a = (without / "package" / "manifest.json").read_bytes()
    b = (with_ / "package" / "manifest.json").read_bytes()
    assert a == b
    m = json.loads(b)
    assert [d["source_file"] for d in m["dropped_tracks"]] == [F["d1t02"], F["d1t03"], F["d2t02"]]
    assert not any(k in d for d in m["dropped_tracks"] for k in ("check", "run_sec", "frac",
                                                                 "check_error"))


# --- the brief prompt never sees the outcome ---

def test_brief_input_omits_audio_check_keys(tmp_path):
    from herder.fake import FakeProvider
    from llama.stages.brief import generate_briefing
    from test_pipeline import GOOD_BRIEFING_JSON

    res = _gather(tmp_path, _md(THREE), _factory(FakeChecker(_three_outcomes())))
    show = res.show.model_copy(update={"review_flags": [], "needs_review": False})
    provider = FakeProvider(completes=[GOOD_BRIEFING_JSON] * 2)
    generate_briefing(provider, show, "", [], narration="full", vetting=None)
    prompt = provider.calls[0][1]
    for key in ('"check"', '"run_sec"', '"frac"', '"check_error"', "fetch failed: boom"):
        assert key not in prompt
    stripped = [{k: v for k, v in r.items() if k not in ("check", "run_sec", "frac", "check_error")}
                for r in show.excluded_files]
    bare = show.model_copy(update={"excluded_files": stripped})
    assert bare.model_dump_json(indent=2) in prompt
    assert '"after_track": 1' in prompt   # the rest of each row is still there


def test_brief_input_unchanged_without_audio_check_keys(tmp_path):
    from llama.stages.brief import _brief_show_json
    res = _gather(tmp_path, _md(TUNING), _factory(FakeChecker({F["d1t02"]: JUNK})))
    legacy = res.show.model_copy(update={"excluded_files": [
        {k: v for k, v in r.items() if k not in ("check", "run_sec", "frac")}
        for r in res.show.excluded_files]})
    assert _brief_show_json(legacy) == legacy.model_dump_json(indent=2)


# --- the overrule, the bar and the replay family ---

def _drop_with(**kw):
    base = dict(filename="gd77-05-08d2t09.mp3", title="Crowd/Tuning", set="2",
                duration_sec=559.0, rule="A", position=8, after_track=8, held=False,
                check="music", run_sec=550, frac=0.98)
    base.update(kw)
    return junk_titles.JunkDrop(**base)


def _show():
    return Show(performance_id="a/1", identifier="gd77", artist="A", date="1977-05-08")


def test_music_flag_wording():
    assert junk_titles.music_flag(_drop_with()) == (
        "junk-title drop sounds like music: 'Crowd/Tuning' (9:19) 9:10 continuous, "
        "98% music, file gd77-05-08d2t09.mp3")


def test_music_overrule_survives_changed_numbers():
    show = _show()
    k1 = flag_key(junk_titles.music_flag(_drop_with(run_sec=550, frac=0.98)), show)
    k2 = flag_key(junk_titles.music_flag(_drop_with(run_sec=540, frac=0.97, duration_sec=561.0)),
                  show)
    assert k1 == k2 == FlagKey("junk-music", ("gd77-05-08d2t09.mp3",))
    assert flag_key(junk_titles.music_flag(_drop_with(filename="other.mp3")), show) != k1


def test_music_and_size_holds_have_distinct_kinds():
    show = _show()
    d = _drop_with()
    size = flag_key(junk_titles.hold_flag(d, total=10000.0, median=400.0), show)
    music = flag_key(junk_titles.music_flag(d), show)
    assert size.kind == "junk-drop" and music.kind == "junk-music"
    assert size.subject == music.subject
    assert not junk_titles.MUSIC_PREFIX.startswith(junk_titles.HOLD_PREFIX)
    assert not junk_titles.HOLD_PREFIX.startswith(junk_titles.MUSIC_PREFIX)


def test_size_overrule_does_not_release_music_hold(tmp_path):
    from llama.models import Overrule
    rule = Overrule(identifier=IDENT, kind="junk-drop", subject=[F["d1t02"]],
                    flag="f", source="fix", at="2026-11-14T00:00:00Z")
    res = _gather(tmp_path, _md({"d1t02": ("Crowd", "6:40")}),
                  _factory(FakeChecker({F["d1t02"]: MUSIC})), Overrides(overrules=[rule]))
    assert [f for f in res.show.review_flags] == [junk_titles.music_flag(res.junk_drops[0])]
    assert res.show.needs_review is True
    music_rule = Overrule(identifier=IDENT, kind="junk-music", subject=[F["d1t02"]],
                          flag="f", source="fix", at="2026-11-14T00:00:00Z")
    both = _gather(tmp_path / "b", _md({"d1t02": ("Crowd", "6:40")}),
                   _factory(FakeChecker({F["d1t02"]: MUSIC})),
                   Overrides(overrules=[rule, music_rule]))
    assert both.show.review_flags == [] and both.show.needs_review is False
    assert "overruled: " + junk_titles.music_flag(both.junk_drops[0]) in both.notes


def test_adjudicator_bar_never_for_music_hold():
    assert OVERRULE_BAR["junk-music"] == "never"


def test_replay_family_for_music_hold():
    assert flag_family(junk_titles.music_flag(_drop_with())) == "junk-music"


@pytest.mark.parametrize("bad", [dict(frac=float("nan")), dict(frac=float("inf")),
                                 dict(frac=float("-inf")), dict(duration_sec=float("nan"))])
def test_music_flag_never_raises_on_non_finite(bad):
    flag = junk_titles.music_flag(_drop_with(**bad))
    assert flag.startswith(junk_titles.MUSIC_PREFIX)
    assert flag.endswith("file gd77-05-08d2t09.mp3")
    assert flag_key(flag, _show()) == FlagKey("junk-music", ("gd77-05-08d2t09.mp3",))


def test_gather_non_finite_music_outcome_holds_not_raises(tmp_path):
    # The backstop: a checker that hands gather a non-finite frac (the cache now refuses
    # one) still completes, with the music hold keyed on the filename.
    res = _gather(tmp_path, _md(TUNING),
                  _factory(FakeChecker({F["d1t02"]: Outcome("music", 550, float("nan"))})))
    assert res.show.needs_review is True
    (flag,) = [f for f in res.show.review_flags if f.startswith(junk_titles.MUSIC_PREFIX)]
    assert flag.endswith(f"file {F['d1t02']}")
