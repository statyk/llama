"""The title backfill's plan and raw single-field writer (`emcee.retitle`).

Strict surface: the writer rewrites `manifest.json` on the live station share.
It must set only `dj_audio.title`, refuse any manifest not in emcee's exact
encoding, keep the original mtime (set on the temp before the rename), and
leave the file either fully old or fully new wherever it stops."""
import json
import os
from pathlib import Path

import pytest

from emcee import retitle
from emcee.config import EmceeConfig
from emcee.retitle import TitleWriteFailed, encode, plan_retitle, write_title

from .helpers import build_package, mark_awaiting_fix, set_dj_audio

OLD_NS = 1_700_000_000_123_456_789


def _config(**titles: str | None) -> EmceeConfig:
    """profile -> program title; each profile is assigned presenter `p`."""
    return EmceeConfig.model_validate({"assign": {"profiles": {
        prof: {"presenter": "p", **({"title": t} if t is not None else {})}
        for prof, t in titles.items()}}})


def _voiced(root: Path, slug: str, *, profile: str = "dead", **dj) -> Path:
    pkg = build_package(root, slug, voiced=True, profile=profile)
    set_dj_audio(pkg, profile=profile, profile_source="llama", **dj)
    return pkg


def _manifest(pkg: Path) -> Path:
    return pkg / "manifest.json"


def _age(path: Path) -> None:
    os.utime(path, ns=(OLD_NS, OLD_NS))


def _slugs(plan) -> list[str]:
    return [w.slug for w in plan.writes]


# ---- plan --------------------------------------------------------------


def test_plan_absent_and_null_title_are_the_same(tmp_path):
    _voiced(tmp_path, "a")                      # no title key
    _voiced(tmp_path, "b", title=None)          # title: null
    plan = plan_retitle(tmp_path, _config(dead=None))
    assert plan.writes == []
    assert plan.unchanged == 2
    assert plan.refused == [] and plan.awaiting == [] and plan.unvoiced == 0


def test_plan_writes_additions_changes_and_clears(tmp_path):
    a = _voiced(tmp_path, "a")                              # absent -> "X"
    b = _voiced(tmp_path, "b", title="Old")                 # "Old" -> "X"
    c = _voiced(tmp_path, "c", profile="other", title="Old")  # "Old" -> None
    _voiced(tmp_path, "d", title="X")                       # already "X"
    plan = plan_retitle(tmp_path, _config(dead="X", other=None))
    got = {w.slug: (w.old, w.new, w.dir, w.raw) for w in plan.writes}
    assert got == {
        "a": (None, "X", a, _manifest(a).read_bytes()),
        "b": ("Old", "X", b, _manifest(b).read_bytes()),
        "c": ("Old", None, c, _manifest(c).read_bytes()),
    }
    assert _slugs(plan) == ["a", "b", "c"]
    assert plan.unchanged == 1


def test_plan_skips_awaiting_fix_and_lists_it(tmp_path):
    marked = _voiced(tmp_path, "marked")
    mark_awaiting_fix(marked)
    nulled = _voiced(tmp_path, "nulled")
    mark_awaiting_fix(nulled, None)
    malformed = _voiced(tmp_path, "malformed")
    mark_awaiting_fix(malformed, "not a dict")
    plan = plan_retitle(tmp_path, _config(dead="X"))
    assert plan.awaiting == ["malformed", "marked"]
    assert _slugs(plan) == ["nulled"]


def test_plan_uses_the_voiced_profile_with_legacy_fallback(tmp_path):
    # A legacy block (no dj_audio.profile) was voiced under source.profile.
    legacy = build_package(tmp_path, "legacy", voiced=True, profile="dead")
    assert "profile" not in json.loads(_manifest(legacy).read_text())["dj_audio"]
    # A moved show: voiced as "other" although llama delivered it as "dead".
    moved = build_package(tmp_path, "moved", voiced=True, profile="dead")
    set_dj_audio(moved, profile="other", profile_source="move")
    plan = plan_retitle(tmp_path, _config(dead="Dead Hour", other="Other Hour"))
    assert {w.slug: w.new for w in plan.writes} == {"legacy": "Dead Hour",
                                                    "moved": "Other Hour"}


def _foreign(pkg: Path, how: str) -> None:
    path = _manifest(pkg)
    data = json.loads(path.read_text())
    if how == "non-ascii":
        data["show"]["venue"] = "Café Wha?"
        path.write_bytes((json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode())
    elif how == "no-newline":
        path.write_bytes(json.dumps(data, indent=2).encode())
    elif how == "indent-4":
        path.write_bytes((json.dumps(data, indent=4) + "\n").encode())
    elif how == "duplicate-keys":
        text = json.dumps(data, indent=2) + "\n"
        path.write_bytes(text.replace('"schema_version": 3,',
                                      '"schema_version": 3,\n  "schema_version": 3,', 1).encode())
    elif how == "float-1.50":
        data["total_duration_sec"] = 1.5
        text = json.dumps(data, indent=2) + "\n"
        assert '"total_duration_sec": 1.5,' in text
        path.write_bytes(text.replace('"total_duration_sec": 1.5,',
                                      '"total_duration_sec": 1.50,').encode())
    elif how == "dj-audio-list":
        data["dj_audio"] = ["dj-audio/99-outro.mp3"]
        path.write_bytes((json.dumps(data, indent=2) + "\n").encode())
    elif how == "invalid-json":
        path.write_bytes(path.read_bytes()[:-20])
    elif how == "not-an-object":
        path.write_bytes(b"[]\n")
    elif how == "not-utf8":
        path.write_bytes(path.read_bytes().replace(b"Some Venue", b"Caf\xe9 Venue"))
    else:
        raise AssertionError(how)


FOREIGN = ["non-ascii", "no-newline", "indent-4", "duplicate-keys", "float-1.50",
           "dj-audio-list", "invalid-json", "not-an-object", "not-utf8"]


def test_plan_refuses_foreign_encodings(tmp_path):
    before = {}
    for how in FOREIGN:
        pkg = _voiced(tmp_path, how, title="Old")
        _foreign(pkg, how)
        _age(_manifest(pkg))
        before[how] = (_manifest(pkg).read_bytes(), _manifest(pkg).stat().st_mtime_ns)
    plan = plan_retitle(tmp_path, _config(dead="X"))
    reasons = dict(plan.refused)
    assert sorted(reasons) == sorted(FOREIGN)
    assert plan.writes == [] and plan.unchanged == 0 and plan.unvoiced == 0
    for how in ["non-ascii", "no-newline", "indent-4", "duplicate-keys", "float-1.50"]:
        assert reasons[how] == "not in emcee's encoding", how
    assert "dj_audio" in reasons["dj-audio-list"]
    assert "JSON" in reasons["invalid-json"] and "JSON" in reasons["not-utf8"]
    assert "object" in reasons["not-an-object"]
    for how, (raw, mtime) in before.items():
        path = _manifest(tmp_path / how)
        assert path.read_bytes() == raw and path.stat().st_mtime_ns == mtime, how


def test_plan_refuses_pre_v3_voiced_or_not(tmp_path):
    for slug, voiced in (("v2-voiced", True), ("v2-unvoiced", False)):
        pkg = build_package(tmp_path, slug, voiced=voiced, profile="dead")
        data = json.loads(_manifest(pkg).read_text())
        data["schema_version"] = 2
        _manifest(pkg).write_text(json.dumps(data, indent=2) + "\n")
    no_version = build_package(tmp_path, "no-version", voiced=False)
    data = json.loads(_manifest(no_version).read_text())
    del data["schema_version"]
    _manifest(no_version).write_text(json.dumps(data, indent=2) + "\n")
    plan = plan_retitle(tmp_path, _config(dead="X"))
    assert [s for s, _ in plan.refused] == ["no-version", "v2-unvoiced", "v2-voiced"]
    assert all(r.startswith("unsupported") for _, r in plan.refused)
    assert plan.unvoiced == 0 and plan.writes == []


def test_plan_ignores_unvoiced_and_dot_directories(tmp_path):
    build_package(tmp_path, "unvoiced", voiced=False)
    hidden = _voiced(tmp_path, ".hidden")
    assert _manifest(hidden).exists()
    (tmp_path / "interstitials").mkdir()
    (tmp_path / "interstitials" / "id.mp3").write_text("x")
    (tmp_path / "stray.json").write_text("{}")
    _voiced(tmp_path, "voiced")
    plan = plan_retitle(tmp_path, _config(dead="X"))
    assert plan.unvoiced == 1
    assert _slugs(plan) == ["voiced"]
    assert plan.refused == [] and plan.awaiting == [] and plan.unchanged == 0


def test_plan_on_a_missing_root_is_empty(tmp_path):
    plan = plan_retitle(tmp_path / "nope", _config(dead="X"))
    assert (plan.writes, plan.awaiting, plan.refused, plan.unchanged, plan.unvoiced) == (
        [], [], [], 0, 0)


# ---- writer ------------------------------------------------------------


def _one(tmp_path: Path, **dj) -> tuple[Path, bytes]:
    pkg = _voiced(tmp_path, "show", **dj)
    _age(_manifest(pkg))
    return pkg, _manifest(pkg).read_bytes()


def test_write_sets_only_the_title_key(tmp_path):
    pkg, raw = _one(tmp_path)
    out = write_title(pkg, expect=raw, title="Gravel & Steel")
    data = json.loads(raw)
    data["dj_audio"]["title"] = "Gravel & Steel"
    assert out == encode(data) == _manifest(pkg).read_bytes()
    # The new key lands LAST in dj_audio, as on the voicing path.
    assert list(json.loads(out)["dj_audio"])[-1] == "title"
    # Every byte outside the inserted line is the original's.
    inserted = b',\n    "title": "Gravel & Steel"'
    i = out.index(inserted)
    assert out[:i] + out[i + len(inserted):] == raw
    # A present title is replaced in place, and a clear writes null.
    out2 = write_title(pkg, expect=out, title=None)
    assert json.loads(out2)["dj_audio"]["title"] is None
    assert out2 == out.replace(b'"title": "Gravel & Steel"', b'"title": null')


def test_write_sets_mtime_before_the_rename(tmp_path, monkeypatch):
    pkg, raw = _one(tmp_path)
    opened, fsynced, events = [], set(), []
    real_open, real_fsync, real_utime, real_replace = open, os.fsync, os.utime, os.replace

    def spy_open(*a, **k):
        f = real_open(*a, **k)
        opened.append(f)
        return f

    def spy_fsync(fd):
        fsynced.add(fd)
        return real_fsync(fd)

    def spy_utime(path, *a, **k):
        tmp = [f for f in opened if Path(f.name) == Path(path)]
        assert tmp, "utime ran on something other than the temp"
        assert tmp[0].closed, "utime ran on an open temp"
        events.append(("utime", Path(path).name))
        return real_utime(path, *a, **k)

    def spy_replace(src, dst):
        events.append(("replace", Path(src).name))
        assert os.stat(src).st_mtime_ns == OLD_NS
        return real_replace(src, dst)

    monkeypatch.setattr(retitle, "open", spy_open, raising=False)
    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "utime", spy_utime)
    monkeypatch.setattr(os, "replace", spy_replace)
    write_title(pkg, expect=raw, title="X")
    assert len(opened) == 1
    name = Path(opened[0].name).name
    assert name.startswith(".manifest.json.emcee-") and name.endswith(".tmp")
    assert Path(opened[0].name).parent == pkg
    assert opened[0].mode == "xb"
    # It was fsynced: its descriptor number went through os.fsync.
    assert fsynced
    assert events == [("utime", name), ("replace", name)]


def test_write_mtime_is_the_original_afterwards(tmp_path, monkeypatch):
    pkg, raw = _one(tmp_path)
    write_title(pkg, expect=raw, title="X")
    assert _manifest(pkg).stat().st_mtime_ns == OLD_NS

    # A rename that bumps the mtime (an NFS server stamping it) is corrected.
    real_replace, real_utime = os.replace, os.utime
    calls = []

    def bumping_replace(src, dst):
        real_replace(src, dst)
        real_utime(dst, ns=(OLD_NS, OLD_NS + 10**12))

    def spy_utime(path, *a, **k):
        calls.append(Path(path).name)
        return real_utime(path, *a, **k)

    monkeypatch.setattr(os, "replace", bumping_replace)
    monkeypatch.setattr(os, "utime", spy_utime)
    raw2 = _manifest(pkg).read_bytes()
    write_title(pkg, expect=raw2, title="Y")
    assert _manifest(pkg).stat().st_mtime_ns == OLD_NS
    assert calls[-1] == "manifest.json" and len(calls) == 2


def test_write_skips_when_the_file_changed_before_rename(tmp_path, monkeypatch):
    pkg, raw = _one(tmp_path)
    other = raw.replace(b"Some Venue", b"Other Venue")
    real_utime = os.utime

    def interloper(path, *a, **k):
        _manifest(pkg).write_bytes(other)      # another writer, mid-sequence
        return real_utime(path, *a, **k)

    monkeypatch.setattr(os, "utime", interloper)
    assert write_title(pkg, expect=raw, title="X") is None
    assert _manifest(pkg).read_bytes() == other
    assert sorted(p.name for p in pkg.iterdir() if p.name.startswith(".")) == []


def test_write_skips_when_the_file_is_gone_before_rename(tmp_path, monkeypatch):
    pkg, raw = _one(tmp_path)
    real_utime = os.utime

    def remover(path, *a, **k):
        _manifest(pkg).unlink()
        return real_utime(path, *a, **k)

    monkeypatch.setattr(os, "utime", remover)
    assert write_title(pkg, expect=raw, title="X") is None
    assert not _manifest(pkg).exists()
    assert [p.name for p in pkg.iterdir() if p.name.startswith(".")] == []


def test_write_post_rename_verify_failure_puts_back_own_bytes(tmp_path, monkeypatch):
    pkg, raw = _one(tmp_path, title="Old")
    monkeypatch.setattr(retitle, "_unchanged_except_title", lambda *a: False)
    with pytest.raises(TitleWriteFailed, match=r"^show: .*the original was put back$"):
        write_title(pkg, expect=raw, title="X")
    assert _manifest(pkg).read_bytes() == raw
    assert _manifest(pkg).stat().st_mtime_ns == OLD_NS
    assert [p.name for p in pkg.iterdir() if p.name.startswith(".")] == []


def test_write_post_rename_verify_failure_leaves_a_foreign_write(tmp_path, monkeypatch):
    pkg, raw = _one(tmp_path)
    foreign = raw.replace(b"Some Venue", b"Other Venue")
    real_replace = os.replace

    def then_another_writer(src, dst):
        real_replace(src, dst)
        Path(dst).write_bytes(foreign)

    monkeypatch.setattr(os, "replace", then_another_writer)
    with pytest.raises(TitleWriteFailed,
                       match=r"^show: .*left as the other writer wrote it$"):
        write_title(pkg, expect=raw, title="X")
    assert _manifest(pkg).read_bytes() == foreign


def test_write_preserves_awaiting_fix_and_unknown_keys(tmp_path):
    pkg = _voiced(tmp_path, "show")
    mark_awaiting_fix(pkg)
    path = _manifest(pkg)
    data = json.loads(path.read_text())
    data["future_key"] = {"nested": [1, 2.5, None, True]}
    data["dj_audio"]["unknown_dj_key"] = "kept"
    path.write_text(json.dumps(data, indent=2) + "\n")
    raw = path.read_bytes()
    out = write_title(pkg, expect=raw, title="X")
    after = json.loads(out)
    assert after["awaiting_fix"] == data["awaiting_fix"]
    assert after["future_key"] == data["future_key"]
    assert after["dj_audio"]["unknown_dj_key"] == "kept"
    assert list(after) == list(data)
    data["dj_audio"]["title"] = "X"
    assert out == encode(data)


def test_write_refuses_bytes_not_in_emcees_encoding(tmp_path):
    pkg, raw = _one(tmp_path)
    foreign = raw.rstrip(b"\n")
    _manifest(pkg).write_bytes(foreign)
    with pytest.raises(ValueError):
        write_title(pkg, expect=foreign, title="X")
    assert _manifest(pkg).read_bytes() == foreign


def test_unchanged_except_title_is_strict():
    before = {"a": 1, "dj_audio": {"x": True}}
    ok = {"a": 1, "dj_audio": {"x": True, "title": "T"}}
    f = retitle._unchanged_except_title
    assert f(before, ok, "T")
    assert not f(before, ok, None)
    assert not f(before, {"a": 1, "dj_audio": {"x": True}}, None)       # no title key
    assert not f(before, {"a": 1.0, "dj_audio": {"x": True, "title": "T"}}, "T")
    assert not f(before, {"a": 1, "dj_audio": {"x": 1, "title": "T"}}, "T")
    assert not f(before, {"a": 1, "b": 2, "dj_audio": {"x": True, "title": "T"}}, "T")
    assert not f(before, {"a": 1, "dj_audio": None}, "T")
    assert not f(before, [], "T")
