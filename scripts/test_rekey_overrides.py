"""scripts/rekey_overrides.py: the per-show checks, the library check, the llama-process
check and the read-only dry run (piece 4 spec 4.3; plan Task 17). Fixture show dirs under
`tmp_path` only, built with `fixture_library.library_show`; never ~/.llama."""
import json
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "llama" / "tests"))

import rekey_overrides as rk
from fixture_library import IDENT, library_show
from llama.junk import FORMAT_BY_AUDIO
from llama.replay import CacheOnlyIA
from llama.workspace import ShowWorkspace

WANT = FORMAT_BY_AUDIO["mp3"]
# The gd73 fixture's kept list, in play order (6 tracks; gather's own breaks are [3, 5]).
F = ["gd73-06-10d1t01.mp3", "gd73-06-10d1t02.mp3", "gd73-06-10d1t03.mp3",
     "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]


@pytest.fixture(autouse=True)
def _hermetic(tmp_path_factory, monkeypatch):
    """main's default config is never ~/.llama, and no test reads the real process table."""
    monkeypatch.setattr(rk, "DEFAULT_ROOT", tmp_path_factory.mktemp("default-root"))
    monkeypatch.setattr(rk, "_ps_lines", lambda: [])


def _show(root: Path, *, date="1973-06-10", titles=None, set_breaks=None, encore_after=None,
          legacy=None) -> ShowWorkspace:
    """A show gathered by today's code with the FILENAME form of the given overrides (the
    only form gather reads), then its overrides.json rewritten as v2.17.0 left it: the
    track-number form (or `legacy`, a raw dict or text, when given). Without overrides
    and without `legacy`, no overrides.json."""
    slug = f"gratefuldead-{date}"
    d = root / "shows" / slug
    d.mkdir(parents=True, exist_ok=True)
    fn, num = {}, {}
    if titles:
        fn["titles"] = {F[n - 1]: t for n, t in titles.items()}
        num["titles"] = {str(n): t for n, t in titles.items()}
    if set_breaks is not None:
        fn["set_breaks"] = [F[n - 1] for n in set_breaks]
        num["set_breaks"] = list(set_breaks)
    if encore_after is not None:
        fn["encore_after"] = F[encore_after - 1]
        num["encore_after"] = encore_after
    if fn:
        (d / "overrides.json").write_text(json.dumps(fn, indent=2))
    ws, _ = library_show(root, held=False, date=date)
    if legacy is not None:
        num = legacy
    if isinstance(num, str):
        ws.overrides.write_text(num)
    elif num:
        ws.overrides.write_text(json.dumps(num, indent=2))
    elif ws.overrides.exists():
        ws.overrides.unlink()
    return ws


def _config(root: Path) -> Path:
    cfg = root / "config.toml"
    cfg.write_text(f'root = "{root}"\n\n[jerrybase]\nenabled = false\n')
    return cfg


def _ia(root: Path) -> CacheOnlyIA:
    return CacheOnlyIA(root / "cache")


def _edit_show(ws: ShowWorkspace, fn):
    data = json.loads(ws.show.read_text())
    fn(data)
    ws.show.write_text(json.dumps(data, indent=2))


def _run(root: Path, capsys) -> tuple[int, str]:
    rc = rk.main(["--config", str(_config(root))])
    return rc, capsys.readouterr().out


def test_dry_run_would_rekey_a_consistent_show(tmp_path, capsys):
    root = tmp_path / "lib"
    ws = _show(root, titles={1: "Dew", 4: "Star"}, set_breaks=[3], encore_after=5)
    assert json.loads(ws.overrides.read_text()) == {
        "titles": {"1": "Dew", "4": "Star"}, "set_breaks": [3], "encore_after": 5}
    got = rk.check_show(ws, _ia(root), WANT)
    assert got == rk.Rekey(slug="gratefuldead-1973-06-10", titles=2, breaks=1, encore=True)
    rc, out = _run(root, capsys)
    lines = out.splitlines()
    assert "would rekey: gratefuldead-1973-06-10 (2 titles, 1 breaks, encore)" in lines
    assert "1 to rekey, 0 refused, 0 already migrated, 0 without positional keys" in lines
    assert "refused" not in out.replace("0 refused", "")
    assert rc == 0
    # No encore key: the line omits it.
    root2 = tmp_path / "lib2"
    _show(root2, titles={2: "Cat"})
    rc, out = _run(root2, capsys)
    assert "would rekey: gratefuldead-1973-06-10 (1 titles, 0 breaks)" in out.splitlines()
    assert rc == 0


HAND = rk.HAND_EDIT_ROUTE

# (case, the show's legacy overrides.json, a mutation of the fixture, the reason, a
# substring of its detail, its route).
CASES = [
    ("unreadable-json", "{not json", None, "unreadable", "overrides.json", rk.REASONS["unreadable"]),
    ("unreadable-model", {"set_breaks": [7.5]}, None, "unreadable", "overrides.json",
     rk.REASONS["unreadable"]),
    ("mixed", {"titles": {"1": "Dew", F[1]: "Cat"}}, None, "mixed", f"titles {F[1]}",
     rk.REASONS["mixed"]),
    ("duplicate-key", {"titles": {"2": "China Cat Sunflower", "02": "China Cat Sunflower"}},
     None, "duplicate key", "'2', '02'", HAND),
    ("no-show-json", {"titles": {"1": "Dew"}}, "drop-show", "no show.json", "show.json",
     rk.REASONS["no show.json"]),
    ("title-out-of-range", {"titles": {"9": "X"}}, None, "title out of range", "'9'",
     rk.REASONS["title out of range"]),
    ("title-key-minus-one", {"titles": {"-1": "X"}}, None, "title out of range", "'-1'", HAND),
    ("title-not-applied", {"titles": {"1": "Wrong"}}, None, "title not applied", "track 1",
     rk.REASONS["title not applied"]),
    ("structure-out-of-range", {"set_breaks": [6]}, None, "structure out of range",
     "out of range", rk.REASONS["structure out of range"]),
    ("structure-not-applied", {"set_breaks": [2]}, None, "structure not applied", "[3, 5]",
     rk.REASONS["structure not applied"]),
    ("repeated-filename", {"titles": {"1": "Morning Dew"}}, "repeat-filename",
     "repeated filename", F[0], rk.REASONS["repeated filename"]),
    ("missing-metadata", {"titles": {"1": "Morning Dew"}}, "drop-metadata", "kept list differs",
     f"md_{IDENT}.json", rk.REASONS["kept list differs"]),
]


@pytest.mark.parametrize("case,legacy,mutate,reason,detail,route", CASES,
                         ids=[c[0] for c in CASES])
def test_each_refusal_reason_with_its_route(tmp_path, capsys, case, legacy, mutate, reason,
                                            detail, route):
    root = tmp_path / "lib"
    if case == "duplicate-key":
        ws = _show(root, titles={2: "China Cat Sunflower"}, legacy=legacy)
    else:
        ws = _show(root, legacy=legacy)
    if mutate == "drop-show":
        ws.show.unlink()
    elif mutate == "repeat-filename":
        def dup(d):
            d["tracks"][1]["filename"] = d["tracks"][0]["filename"]
        _edit_show(ws, dup)
    elif mutate == "drop-metadata":
        (root / "cache" / f"md_{IDENT}.json").unlink()
    got = rk.check_show(ws, _ia(root), WANT)
    assert isinstance(got, list) and got, got
    mine = [r for r in got if r.reason == reason]
    assert mine, [r.reason for r in got]
    r = mine[0]
    assert r.slug == "gratefuldead-1973-06-10"
    assert detail in r.detail
    assert r.route == route
    assert set(rk.REASONS) >= {x.reason for x in got}
    rc, out = _run(root, capsys)
    lines = out.splitlines()
    i = lines.index(f"refused: gratefuldead-1973-06-10: {reason} ({r.detail})")
    assert lines[i + 1] == f"  repair: {route.replace('<show>', r.slug)}"
    assert "0 to rekey, 1 refused, 0 already migrated, 0 without positional keys" in lines
    assert rc == 1


def test_unreadable_and_mixed_stop_further_checks(tmp_path):
    root = tmp_path / "lib"
    # A mixed file whose numbered key is also out of range and not applied: only `mixed`.
    ws = _show(root, legacy={"titles": {"9": "X", F[1]: "Cat"}, "set_breaks": [6]})
    got = rk.check_show(ws, _ia(root), WANT)
    assert [r.reason for r in got] == ["mixed"]
    assert got[0].detail == f"filename-valued: titles {F[1]}"
    ws.overrides.write_text(json.dumps({"titles": {"9": "X"}, "set_breaks": [7.5]}))
    got = rk.check_show(ws, _ia(root), WANT)
    assert [r.reason for r in got] == ["unreadable"]


def test_every_other_failure_is_reported(tmp_path):
    root = tmp_path / "lib"
    ws = _show(root, legacy={"titles": {"9": "X", "1": "Wrong", "3": "A", "03": "B"},
                             "set_breaks": [2]})
    reasons = [r.reason for r in rk.check_show(ws, _ia(root), WANT)]
    assert reasons == ["duplicate key", "title out of range", "title not applied",
                       "structure not applied"]


def test_duplicate_key_seven_and_oh_seven(tmp_path):
    """The carried decision: `rekey_raw` collapses "7"/"07" last-wins, so check_show must
    catch them (equal legacy_int)."""
    root = tmp_path / "lib"
    ws = _show(root, legacy={"titles": {"7": "A", "07": "B"}})
    got = rk.check_show(ws, _ia(root), WANT)
    dup = [r for r in got if r.reason == "duplicate key"]
    assert dup and "'7', '07'" in dup[0].detail and dup[0].route == HAND


def test_a_redo_route_that_cannot_run_names_the_hand_edit(tmp_path):
    """No provenance.json: `llama redo <show> --from gather` cannot run (spec 4.3 "Routes
    with no CLI form")."""
    root = tmp_path / "lib"
    ws = _show(root, legacy={"titles": {"1": "Wrong"}})
    ws.provenance.unlink()
    got = rk.check_show(ws, _ia(root), WANT)
    (r,) = [r for r in got if r.reason == "title not applied"]
    assert r.route.startswith(HAND)
    assert "provenance.json" in r.route


def test_an_unreadable_show_json_is_refused(tmp_path):
    root = tmp_path / "lib"
    ws = _show(root, legacy={"titles": {"1": "Morning Dew"}})
    ws.show.write_text("{")
    got = rk.check_show(ws, _ia(root), WANT)
    assert [r.reason for r in got] == ["no show.json"]
    assert "unreadable" in got[0].detail


def test_structure_checks_only_when_a_structure_key_is_present(tmp_path):
    root = tmp_path / "lib"
    ws = _show(root, titles={1: "Dew"})
    show = json.loads(ws.show.read_text())
    assert show["set_breaks"] == [3, 5]     # its own alignment's, not the overrides'
    got = rk.check_show(ws, _ia(root), WANT)
    assert got == rk.Rekey(slug="gratefuldead-1973-06-10", titles=1, breaks=0, encore=False)
    # `set_breaks: []` is present (forced no breaks): the structure check runs.
    ws.overrides.write_text(json.dumps({"titles": {"1": "Dew"}, "set_breaks": []}))
    got = rk.check_show(ws, _ia(root), WANT)
    assert [r.reason for r in got] == ["structure not applied"]
    # An encore alone is present too.
    ws.overrides.write_text(json.dumps({"titles": {"1": "Dew"}, "encore_after": 5}))
    got = rk.check_show(ws, _ia(root), WANT)
    assert [r.reason for r in got] == ["structure not applied"]


def _add_short_tagged_file(root: Path):
    """The cached item gains a tagged 70 s interior file: the short-keep rule keeps it,
    today's rule (short_keep=False) drops it."""
    path = root / "cache" / f"md_{IDENT}.json"
    md = json.loads(path.read_text())
    md["files"] += [
        {"name": "gd73-06-10d1t04.shn", "format": "Shorten", "source": "original"},
        {"name": "gd73-06-10d1t04.mp3", "format": "VBR MP3", "length": "01:10",
         "title": "Sugar Magnolia", "source": "derivative", "original": "gd73-06-10d1t04.shn"}]
    path.write_text(json.dumps(md))


def test_kept_list_uses_todays_rule(tmp_path):
    root = tmp_path / "lib"
    ws = _show(root, titles={1: "Dew"})
    _add_short_tagged_file(root)
    from llama.models import Overrides
    from llama.stages.gather import final_kept
    md = json.loads((root / "cache" / f"md_{IDENT}.json").read_text())
    assert "gd73-06-10d1t04.mp3" in [f["name"] for f in final_kept(md["files"], Overrides(),
                                                                    WANT).kept]
    got = rk.check_show(ws, _ia(root), WANT)
    assert isinstance(got, rk.Rekey), got
    # show.json with an extra file is refused.
    def extra(d):
        t = dict(d["tracks"][-1])
        t.update(index=7, filename="gd73-06-10d1t04.mp3", title="Sugar Magnolia",
                 title_source="tags")
        d["tracks"].append(t)
    _edit_show(ws, extra)
    got = rk.check_show(ws, _ia(root), WANT)
    assert [r.reason for r in got] == ["kept list differs"]
    assert got[0].route == rk.REASONS["kept list differs"]


def test_check_show_judges_the_bytes_it_is_given(tmp_path):
    root = tmp_path / "lib"
    ws = _show(root, titles={1: "Dew"})
    wrong = json.dumps({"titles": {"1": "Wrong"}}).encode()
    got = rk.check_show(ws, _ia(root), WANT, overrides_bytes=wrong)
    assert [r.reason for r in got] == ["title not applied"]
    show = json.loads(ws.show.read_text())
    show["tracks"][0]["title"] = "Other"
    got = rk.check_show(ws, _ia(root), WANT, show_bytes=json.dumps(show).encode())
    assert [r.reason for r in got] == ["title not applied"]
    assert isinstance(rk.check_show(ws, _ia(root), WANT), rk.Rekey)


def test_shows_without_legacy_values_are_skipped_and_counted(tmp_path, capsys):
    root = tmp_path / "lib"
    _show(root, date="1973-06-10")                                     # no overrides.json
    _show(root, date="1973-06-11", legacy={"set_breaks": []})          # `[]` only
    _show(root, date="1973-06-12", legacy={"titles": {F[0]: "Dew"}})   # migrated
    _show(root, date="1973-06-13", titles={1: "Dew"})                  # legacy
    for d in ("1973-06-10", "1973-06-11", "1973-06-12"):
        assert rk.check_show(ShowWorkspace(root / "shows" / f"gratefuldead-{d}"),
                             _ia(root), WANT) is None
    rekeys, refused, migrated = rk.check_library(root, _ia(root), WANT)
    assert [r.slug for r in rekeys] == ["gratefuldead-1973-06-13"]
    assert refused == []
    assert migrated == ["gratefuldead-1973-06-12"]
    rc, out = _run(root, capsys)
    assert out.splitlines()[-1] == ("1 to rekey, 0 refused, 1 already migrated, "
                                    "2 without positional keys")
    assert rc == 0


def _tree_state(root: Path) -> dict[str, tuple]:
    state = {}
    for p in root.rglob("*"):
        st = p.lstat()
        key = str(p.relative_to(root))
        if p.is_dir() and not p.is_symlink():
            state[key] = ("dir", st.st_mtime_ns)
        else:
            state[key] = ("file", st.st_size, st.st_mtime_ns, p.read_bytes())
    state["."] = ("dir", root.stat().st_mtime_ns)
    return state


def _set_writable(root: Path, on: bool):
    for p in [root, *root.rglob("*")]:
        mode = p.stat().st_mode
        p.chmod(mode | stat.S_IWUSR if on else mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def test_dry_run_writes_nothing(tmp_path, capsys):
    root = tmp_path / "lib"
    _show(root, date="1973-06-10", titles={1: "Dew"}, set_breaks=[3], encore_after=5)
    _show(root, date="1973-06-11", legacy={"titles": {"1": "Wrong"}})
    _show(root, date="1973-06-12", legacy="{not json")
    cfg = _config(root)
    before = _tree_state(root)
    assert not [p for p in before if Path(p).name in (".lock", rk.LOCK)]
    _set_writable(root, False)
    try:
        rc = rk.main(["--config", str(cfg)])
    finally:
        _set_writable(root, True)
    out = capsys.readouterr().out
    assert rc == 1
    assert "would rekey: gratefuldead-1973-06-10 (1 titles, 1 breaks, encore)" in out
    after = _tree_state(root)
    assert after == before
    assert not [p for p in after if Path(p).name in (".lock", rk.LOCK)]


SELF = "/x/.venv/bin/python scripts/rekey_overrides.py --apply"
MAC_PY = ("/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/"
          "Resources/Python.app/Contents/MacOS/Python")


def test_process_check_matches():
    match = [
        "601     1 /usr/local/bin/llama run resume --all",
        "602     1 /x/.venv/bin/llama get q",
        "603     1 /usr/bin/python3 -m llama status",
        "604     1 /bin/zsh -c while true; do llama run resume --all; sleep 600; done",
        '605     1 bash -c "llama deliver x"',
        "606     1 /x/.venv/bin/python scripts/replay_holds.py run --all",
        # As macOS ps shows a venv console script and `python -m llama` (Homebrew's
        # framework Python re-execs; measured 2026-10-24).
        f"607     1 {MAC_PY} /x/.venv/bin/llama get q",
        f"608     1 {MAC_PY} -m llama status",
        "609     1 sh -c FOO=1 llama status",
        "610     1 zsh -c (llama status)",
        "611     1 zsh -c if true; then llama status; else true; fi",
        "612     1 zsh -c true || llama status",
        "613     1 zsh -c echo | llama status",
    ]
    other = [
        "1     0 /sbin/launchd",
        # The script's ancestors: an ancestor whose command would otherwise match, the
        # wrapper shell, the script itself.
        "300     1 /usr/local/bin/llama run resume --all",
        "400   300 zsh -c 'cd /Users/shawn/projects/llama && " + SELF + "'",
        "500   400 " + SELF,
        # The same command under another pid, and the same wrapper as an unrelated pid.
        "701     1 " + SELF,
        "702     1 zsh -c 'cd /Users/shawn/projects/llama && " + SELF + "'",
        f"703     1 {MAC_PY} scripts/rekey_overrides.py --apply",
        "704     1 vim packages/llama/src/llama/junk.py",
        "705     1 -zsh",
        "706     1 python -m pytest",
        f"707     1 {MAC_PY} /x/.venv/bin/pytest -q",
        "708     1 /x/.venv/bin/emcee run",
        "709   500 ps -axo pid=,ppid=,command=",
        "",
        "garbage",
    ]
    got = rk.llama_processes(other[:4] + match + other[4:], self_pid=500)
    assert got == match


def test_dry_run_prints_llama_processes_without_refusing(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    _show(root, titles={1: "Dew"})
    monkeypatch.setattr(rk, "_ps_lines", lambda: ["601 1 /usr/local/bin/llama get q"])
    rc, out = _run(root, capsys)
    lines = out.splitlines()
    i = lines.index("llama processes running:")
    assert lines[i + 1] == "  601 1 /usr/local/bin/llama get q"
    assert rc == 0
    monkeypatch.setattr(rk, "_ps_lines", lambda: [])
    rc, out = _run(root, capsys)
    assert "llama processes running: none" in out.splitlines()


def test_exit_codes(tmp_path, capsys):
    root = tmp_path / "lib"
    _show(root, date="1973-06-10", titles={1: "Dew"})
    _show(root, date="1973-06-11")
    assert _run(root, capsys)[0] == 0
    _show(root, date="1973-06-12", legacy={"titles": {"9": "X"}})
    assert _run(root, capsys)[0] == 1
    # An empty library: nothing refused.
    empty = tmp_path / "empty"
    empty.mkdir()
    rc, out = _run(empty, capsys)
    assert rc == 0
    assert "0 to rekey, 0 refused, 0 already migrated, 0 without positional keys" in out


def test_main_refuses_a_llama_outside_this_tree(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    root.mkdir()
    monkeypatch.setattr(rk.llama, "__file__", str(tmp_path / "elsewhere" / "__init__.py"))
    assert rk.main(["--config", str(_config(root))]) == 1
    assert "refusing to run" in capsys.readouterr().err


def test_a_failed_process_check_fails_the_dry_run(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    _show(root, titles={1: "Dew"})

    def boom():
        raise OSError("no ps")
    monkeypatch.setattr(rk, "_ps_lines", boom)
    rc, out = _run(root, capsys)
    assert "process check failed: OSError: no ps" in out.splitlines()
    assert "would rekey: gratefuldead-1973-06-10 (1 titles, 0 breaks)" in out.splitlines()
    assert rc == 1


def test_kept_list_is_compared_in_order(tmp_path):
    """Two show.json filenames swapped (same multiset) is not today's kept list."""
    root = tmp_path / "lib"
    ws = _show(root, set_breaks=[3], encore_after=5)

    def swap(d):
        a, b = d["tracks"][0]["filename"], d["tracks"][1]["filename"]
        d["tracks"][0]["filename"], d["tracks"][1]["filename"] = b, a
    _edit_show(ws, swap)
    got = rk.check_show(ws, _ia(root), WANT)
    assert [r.reason for r in got] == ["kept list differs"]
    assert f"first difference at track 1: {F[1]} vs {F[0]}" in got[0].detail


def test_a_matching_title_that_is_not_an_override_is_not_applied(tmp_path):
    root = tmp_path / "lib"
    ws = _show(root, legacy={"titles": {"1": "Morning Dew"}})
    assert json.loads(ws.show.read_text())["tracks"][0]["title_source"] == "tags"
    got = rk.check_show(ws, _ia(root), WANT)
    assert [r.reason for r in got] == ["title not applied"]
    assert "title_source tags" in got[0].detail


def test_a_negative_key_without_show_json_is_reported(tmp_path):
    root = tmp_path / "lib"
    ws = _show(root, legacy={"titles": {"-1": "X"}})
    ws.show.unlink()
    got = rk.check_show(ws, _ia(root), WANT)
    assert [r.reason for r in got] == ["no show.json", "title out of range"]
    assert got[1].route == HAND


def test_title_out_of_range_names_the_number_each_key_reads_as(tmp_path):
    root = tmp_path / "lib"
    ws = _show(root, legacy={"titles": {"7_0": "X", "+9": "Y", "-2": "Z"}})
    got = [r for r in rk.check_show(ws, _ia(root), WANT) if r.reason == "title out of range"]
    assert [r.detail for r in got] == [
        "titles keys '7_0' (reads as 70), '+9' (reads as 9) outside 1..6",
        "titles keys '-2' (reads as -2) outside 1..6"]


def test_printed_routes_name_the_show(tmp_path, capsys):
    root = tmp_path / "lib"
    ws = _show(root, legacy={"titles": {"1": "Wrong"}})
    (r,) = rk.check_show(ws, _ia(root), WANT)
    assert r.route == rk.REASONS["title not applied"]     # the dataclass keeps the template
    rc, out = _run(root, capsys)
    assert "  repair: `llama redo gratefuldead-1973-06-10 --from gather`" in out.splitlines()
    assert "<show>" not in out


def test_dry_run_notes_what_the_process_check_cannot_see(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    _show(root, titles={1: "Dew"})
    note = ("note: the process check cannot see a sweep loop typed at an interactive prompt "
            "while it sleeps; stop it by hand (runbook step 1)")
    for ps in ([], ["601 1 /usr/local/bin/llama get q"]):
        monkeypatch.setattr(rk, "_ps_lines", lambda ps=ps: ps)
        rc, out = _run(root, capsys)
        lines = out.splitlines()
        i = next(i for i, l in enumerate(lines) if l.startswith("llama processes running:"))
        assert lines[i + 1 + len(ps)] == note
