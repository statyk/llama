"""scripts/rekey_overrides.py: the per-show checks, the library check, the llama-process
check and the read-only dry run (piece 4 spec 4.3; plan Task 17), and `--snapshot` with
`verify_snapshot`/`find_snapshot` (Task 18). Fixture show dirs under
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
    """main's default config is never ~/.llama, no test reads the real process table, and
    no test runs this machine's `llama` (--apply's version gate sees one good binary)."""
    monkeypatch.setattr(rk, "DEFAULT_ROOT", tmp_path_factory.mktemp("default-root"))
    monkeypatch.setattr(rk, "_ps_lines", lambda: [])
    monkeypatch.setattr(rk, "llama_versions", lambda: [("/usr/local/bin/llama", "2.18.0")])


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


# --- --snapshot (plan Task 18; spec 4.3 "`--snapshot`") ---

import hashlib
import shutil
import threading
import time
from datetime import datetime, timezone

from llama.locks import Locked, file_lock

SLUG = "gratefuldead-1973-06-10"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _snap(root: Path, capsys) -> tuple[int, str]:
    rc = rk.main(["--config", str(_config(root)), "--snapshot"])
    return rc, capsys.readouterr().out


def _snapshots(root: Path) -> list[Path]:
    return sorted(root.glob(rk.SNAPSHOT_PREFIX + "*"))


def _full_show(root: Path, date="1973-06-10") -> ShowWorkspace:
    """A legacy show with the files a delivered show holds: package/manifest.json and
    audio, briefing files, a lock, and a leftover `.audio-aside/`."""
    ws = _show(root, date=date, titles={1: "Dew"}, set_breaks=[3], encore_after=5)
    (ws.package_dir / "audio").mkdir(parents=True)
    (ws.package_dir / "audio" / F[0]).write_bytes(b"ID3 audio")
    (ws.package_dir / "manifest.json").write_text('{"tracks": []}')
    (ws.package_dir / "show.m3u").write_text("#EXTM3U\n")
    ws.briefing_md.write_text("brief")
    (ws.dir / ".audio-aside").mkdir()
    (ws.dir / ".audio-aside" / F[1]).write_bytes(b"old audio")
    ws.lock.write_text("")
    return ws


def _metadata_rels(ws: ShowWorkspace) -> set[str]:
    out = set()
    for p in ws.dir.rglob("*"):
        rel = p.relative_to(ws.dir).as_posix()
        if p.is_file() and rel != ".lock" and not rel.startswith(("package/audio/",
                                                                  ".audio-aside/")):
            out.add(rel)
    return out


def test_snapshot_copies_every_metadata_file_and_no_audio_or_lock(tmp_path, capsys):
    root = tmp_path / "lib"
    ws = _full_show(root)
    _show(root, date="1973-06-11")                  # a show with no overrides.json
    rels = _metadata_rels(ws)
    assert {"overrides.json", "show.json", "provenance.json", "briefing.md",
            "package/manifest.json", "package/show.m3u"} <= rels
    assert not (ws.dir / ".txn").exists()
    rc, out = _snap(root, capsys)
    assert rc == 0, out
    (snap,) = _snapshots(root)
    assert rk.find_snapshot(root) == snap
    assert f"snapshot: {snap} (2 shows" in out
    copied = {p.relative_to(snap / "shows" / SLUG).as_posix()
              for p in (snap / "shows" / SLUG).rglob("*") if p.is_file()}
    assert copied == rels
    for rel in rels:
        assert (snap / "shows" / SLUG / rel).read_bytes() == (ws.dir / rel).read_bytes()
    assert not (snap / "shows" / SLUG / ".lock").exists()
    assert not (snap / "shows" / SLUG / "package" / "audio").exists()
    assert not (snap / "shows" / SLUG / ".audio-aside").exists()
    manifest = json.loads((snap / "manifest.json").read_text())
    assert manifest["slugs"] == [SLUG, "gratefuldead-1973-06-11"]
    assert {k for k in manifest["files"] if k.startswith(SLUG + "/")} == {
        f"{SLUG}/{r}" for r in rels}
    assert snap.name == rk.SNAPSHOT_PREFIX + datetime.fromisoformat(
        manifest["created_at"]).strftime("%Y%m%dT%H%M%SZ")
    assert datetime.fromisoformat(manifest["created_at"]).utcoffset().total_seconds() == 0
    assert rk.verify_snapshot(snap) == []


def test_snapshot_names_its_directory_by_the_utc_start_and_refuses_an_existing_one(tmp_path):
    root = tmp_path / "lib"
    _show(root, titles={1: "Dew"})
    now = datetime(2026, 10, 24, 1, 2, 3, tzinfo=timezone.utc)
    snap = rk.snapshot(root, echo=lambda *a: None, now=now)
    assert snap == root / "rekey-snapshot-20261024T010203Z"
    manifest = json.loads((snap / "manifest.json").read_text())
    assert manifest["created_at"] == "2026-10-24T01:02:03+00:00"
    before = _tree_state(snap)
    with pytest.raises(rk._Refused, match="exists"):
        rk.snapshot(root, echo=lambda *a: None, now=now)
    assert _tree_state(snap) == before            # the existing snapshot is untouched
    assert rk.verify_snapshot(snap) == []


def test_lock_only_show_dir_is_not_a_show(tmp_path, capsys):
    """An `rm` husk (show_unit limitation 2) is not recorded, not copied and not a
    coverage gap: neither --apply nor --restore refuses on it."""
    root = tmp_path / "lib"
    _show(root, titles={1: "Dew"})
    husk = root / "shows" / "gratefuldead-1973-06-12"
    husk.mkdir()
    (husk / ".lock").write_text("")
    assert rk.library_shows(root) == [root / "shows" / SLUG]
    rc, out = _snap(root, capsys)
    assert rc == 0, out
    (snap,) = _snapshots(root)
    manifest = json.loads((snap / "manifest.json").read_text())
    assert manifest["slugs"] == [SLUG]
    assert not (snap / "shows" / husk.name).exists()
    assert rk.verify_snapshot(snap) == []
    rc, out = _apply(root, capsys)
    assert rc == 0, out
    assert f"rekeyed: {SLUG} (1 titles, 0 breaks)" in out.splitlines()
    assert husk.name not in out
    assert sorted(p.name for p in husk.iterdir()) == [".lock"]
    # --restore does not refuse on it either, and leaves it alone.
    rc, out = _restore(root, snap, capsys)
    assert rc == 0, out
    assert husk.name not in out
    assert sorted(p.name for p in husk.iterdir()) == [".lock"]
    assert classify(json.loads((root / "shows" / SLUG / "overrides.json").read_text())) \
        == "legacy"


def test_a_show_dir_holding_only_audio_fails_the_snapshot(tmp_path, capsys):
    """Not a husk (it holds a file), but nothing to copy: a recorded slug with no
    entry would never verify, so the snapshot fails now rather than later."""
    root = tmp_path / "lib"
    _show(root, titles={1: "Dew"})
    odd = root / "shows" / "gratefuldead-1973-06-12"
    (odd / "package" / "audio").mkdir(parents=True)
    (odd / "package" / "audio" / F[0]).write_bytes(b"ID3")
    rc, out = _snap(root, capsys)
    assert rc == 1
    assert "gratefuldead-1973-06-12" in out
    assert _snapshots(root) == []


def test_snapshot_hashes_verify(tmp_path, capsys):
    root = tmp_path / "lib"
    ws = _full_show(root)
    rc, out = _snap(root, capsys)
    assert rc == 0, out
    (snap,) = _snapshots(root)
    manifest = json.loads((snap / "manifest.json").read_text())
    for key, sha in manifest["files"].items():
        slug, rel = key.split("/", 1)
        assert sha == _sha((root / "shows" / slug / rel).read_bytes())
        assert sha == _sha((snap / "shows" / key).read_bytes())
    assert manifest["files"][f"{SLUG}/overrides.json"] == _sha(ws.overrides.read_bytes())
    assert rk.verify_snapshot(snap) == []


def test_a_copy_that_differs_from_its_source_fails_the_snapshot(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    ws = _full_show(root)
    _show(root, date="1973-06-11", titles={2: "Cat"})
    real = rk._write_copy

    def corrupt(dst, data):
        if dst.name == "show.json" and dst.parent.name == SLUG:
            data = bytes([data[0] ^ 1]) + data[1:]
        real(dst, data)
    monkeypatch.setattr(rk, "_write_copy", corrupt)
    before = ws.show.read_bytes()
    rc, out = _snap(root, capsys)
    assert rc == 1
    assert f"{SLUG}/show.json: the copy differs from its source" in out
    assert _snapshots(root) == []                  # partial directory removed
    assert rk.find_snapshot(root) is None
    assert ws.show.read_bytes() == before


def test_a_failure_after_the_manifest_is_written_removes_it(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    _show(root, titles={1: "Dew"})
    monkeypatch.setattr(rk, "verify_snapshot", lambda snap: ["planted problem"])
    rc, out = _snap(root, capsys)
    assert rc == 1
    assert "planted problem" in out
    assert _snapshots(root) == []


def test_an_interrupt_removes_the_partial_snapshot(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    _show(root, titles={1: "Dew"})

    def interrupt(dst, data):
        raise KeyboardInterrupt
    monkeypatch.setattr(rk, "_write_copy", interrupt)
    with pytest.raises(KeyboardInterrupt):
        rk.snapshot(root, echo=lambda *a: None)
    assert _snapshots(root) == []


@pytest.mark.parametrize("form", ["filename", "mixed", "unreadable"])
def test_snapshot_refuses_a_library_holding_a_filename_value(tmp_path, capsys, form):
    """A partly migrated library is no rollback point; an unreadable overrides.json
    cannot be shown not to hold one. Nothing is created, the lock file included."""
    root = tmp_path / "lib"
    _show(root, date="1973-06-10", titles={1: "Dew"})
    bad = {"filename": {"titles": {F[0]: "Dew"}},
           "mixed": {"titles": {"1": "Dew", F[1]: "Cat"}},
           "unreadable": "{not json"}[form]
    _show(root, date="1973-06-11", legacy=bad)
    cfg = _config(root)
    before = _tree_state(root)
    rc = rk.main(["--config", str(cfg), "--snapshot"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "gratefuldead-1973-06-11" in out
    if form != "unreadable":
        assert F[0 if form == "filename" else 1] in out
    assert _tree_state(root) == before
    assert not (root / rk.LOCK).exists()


def test_snapshot_refuses_while_llama_runs(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    _show(root, titles={1: "Dew"})
    cfg = _config(root)
    line = "601 1 /usr/local/bin/llama run resume --all"
    monkeypatch.setattr(rk, "llama_processes", lambda ps, *, self_pid: [line])
    before = _tree_state(root)
    rc = rk.main(["--config", str(cfg), "--snapshot"])
    out = capsys.readouterr().out
    assert rc == 1
    assert f"  {line}" in out.splitlines()
    assert _tree_state(root) == before
    assert not (root / rk.LOCK).exists()

    # A process check that cannot run refuses too.
    def boom():
        raise OSError("no ps")
    monkeypatch.setattr(rk, "_ps_lines", boom)
    monkeypatch.setattr(rk, "llama_processes", lambda ps, *, self_pid: [])
    rc = rk.main(["--config", str(cfg), "--snapshot"])
    assert rc == 1
    assert "process check failed: OSError: no ps" in capsys.readouterr().out
    assert _tree_state(root) == before


def _wait_until(pred, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_snapshot_takes_the_migration_lock_and_each_show_lock(tmp_path):
    root = tmp_path / "lib"
    _show(root, date="1973-06-10", titles={1: "Dew"})
    ws = _show(root, date="1973-06-11", titles={2: "Cat"})
    result = {}

    def run():
        try:
            result["snap"] = rk.snapshot(root, echo=lambda *a: None)
        except BaseException as exc:     # surfaced by the asserts below
            result["exc"] = exc
    with file_lock(ws.lock):
        t = threading.Thread(target=run)
        t.start()
        # It waits on the held show lock, holding the migration lock meanwhile.
        assert _wait_until(lambda: (root / rk.LOCK).exists() and _snapshots(root))
        time.sleep(0.3)
        assert t.is_alive()
        assert "snap" not in result and "exc" not in result
        with pytest.raises(Locked):
            with file_lock(root / rk.LOCK, blocking=False):
                pass
        (snap,) = _snapshots(root)
        assert not (snap / "manifest.json").exists()
    t.join(10)
    assert not t.is_alive()
    assert "exc" not in result, result
    assert rk.verify_snapshot(result["snap"]) == []
    # Released: another holder can take the migration lock now.
    with file_lock(root / rk.LOCK, blocking=False):
        pass


def test_a_held_migration_lock_refuses_the_snapshot(tmp_path):
    root = tmp_path / "lib"
    _show(root, titles={1: "Dew"})
    with file_lock(root / rk.LOCK):
        with pytest.raises(rk._Refused, match=r"\.rekey\.lock"):
            rk.snapshot(root, echo=lambda *a: None)
    assert _snapshots(root) == []


def test_an_overrides_json_rewritten_before_its_show_lock_fails_the_snapshot(tmp_path):
    """The form check is repeated on the bytes copied under the show lock."""
    root = tmp_path / "lib"
    ws = _show(root, titles={1: "Dew"})
    result = {}

    def run():
        try:
            result["snap"] = rk.snapshot(root, echo=lambda *a: None)
        except BaseException as exc:
            result["exc"] = exc
    with file_lock(ws.lock):
        t = threading.Thread(target=run)
        t.start()
        assert _wait_until(lambda: bool(_snapshots(root)))
        ws.overrides.write_text(json.dumps({"titles": {F[0]: "Dew"}}))
    t.join(10)
    assert isinstance(result.get("exc"), rk._Refused), result
    assert SLUG in str(result["exc"])
    assert _snapshots(root) == []


def test_a_symlink_in_a_show_dir_fails_the_snapshot(tmp_path, capsys):
    root = tmp_path / "lib"
    ws = _show(root, titles={1: "Dew"})
    (tmp_path / "elsewhere.json").write_text("{}")
    (ws.dir / "linked.json").symlink_to(tmp_path / "elsewhere.json")
    rc, out = _snap(root, capsys)
    assert rc == 1
    assert "linked.json" in out
    assert _snapshots(root) == []


def test_snapshot_refuses_a_root_without_shows(tmp_path, capsys):
    root = tmp_path / "lib"
    root.mkdir()
    rc, out = _snap(root, capsys)
    assert rc == 1
    assert _snapshots(root) == []


def test_directory_without_manifest_is_no_snapshot(tmp_path):
    root = tmp_path / "lib"
    root.mkdir()
    assert rk.find_snapshot(root) is None
    old = root / "rekey-snapshot-20261020T000000Z"
    new = root / "rekey-snapshot-20261024T000000Z"
    for d in (old, new):
        (d / "shows").mkdir(parents=True)
    assert rk.find_snapshot(root) is None
    (old / "manifest.json").write_text(json.dumps(
        {"created_at": "2026-10-20T00:00:00+00:00", "slugs": [], "files": {}}))
    assert rk.find_snapshot(root) == old
    assert rk.verify_snapshot(new) == ["no manifest.json"]
    (new / "manifest.json").write_text(json.dumps(
        {"created_at": "2026-10-24T00:00:00+00:00", "slugs": [], "files": {}}))
    assert rk.find_snapshot(root) == new
    (root / "rekey-snapshot-20261025T000000Z").write_text("a file, not a directory")
    assert rk.find_snapshot(root) == new


def _taken(root: Path, capsys) -> Path:
    _full_show(root)
    _show(root, date="1973-06-11", titles={2: "Cat"})
    rc, out = _snap(root, capsys)
    assert rc == 0, out
    (snap,) = _snapshots(root)
    assert rk.verify_snapshot(snap) == []
    return snap


def test_verify_snapshot_problems(tmp_path, capsys):
    root = tmp_path / "lib"
    snap = _taken(root, capsys)
    other = "gratefuldead-1973-06-11"
    # A missing file.
    gone = snap / "shows" / SLUG / "briefing.md"
    saved = gone.read_bytes()
    gone.unlink()
    problems = rk.verify_snapshot(snap)
    assert len(problems) == 1 and f"{SLUG}/briefing.md" in problems[0] and "missing" in problems[0]
    gone.write_bytes(saved)
    assert rk.verify_snapshot(snap) == []
    # A changed file.
    changed = snap / "shows" / SLUG / "package" / "manifest.json"
    changed.write_bytes(changed.read_bytes() + b" ")
    problems = rk.verify_snapshot(snap)
    assert len(problems) == 1 and f"{SLUG}/package/manifest.json" in problems[0]
    assert "sha256" in problems[0]
    changed.write_bytes(changed.read_bytes()[:-1])
    assert rk.verify_snapshot(snap) == []
    # A recorded slug with no entry.
    mpath = snap / "manifest.json"
    good = mpath.read_bytes()
    m = json.loads(good)
    m["files"] = {k: v for k, v in m["files"].items() if not k.startswith(other + "/")}
    mpath.write_text(json.dumps(m))
    assert rk.verify_snapshot(snap) == [f"{other}: recorded slug has no entry"]
    # An entry outside the recorded slugs, and one escaping the snapshot.
    m = json.loads(good)
    m["files"]["gratefuldead-1999-01-01/show.json"] = m["files"][f"{other}/show.json"]
    m["files"][f"{other}/../../../x"] = "0" * 64
    mpath.write_text(json.dumps(m))
    problems = rk.verify_snapshot(snap)
    assert any("gratefuldead-1999-01-01" in p and "not a recorded slug" in p for p in problems)
    assert any("../../../x" in p for p in problems)
    # An unreadable or malformed manifest.
    mpath.write_text("{")
    assert rk.verify_snapshot(snap)[0].startswith("manifest.json unreadable")
    for bad in ([], {"slugs": [], "files": {}}, {"created_at": "x", "slugs": [], "files": {}},
                {"created_at": "2026-10-24T00:00:00+00:00", "slugs": "a", "files": {}},
                {"created_at": "2026-10-24T00:00:00+00:00", "slugs": [], "files": []},
                {"created_at": "2026-10-24T00:00:00", "slugs": [], "files": {}},
                {"created_at": "2026-10-24T00:00:00+02:00", "slugs": [], "files": {}}):
        mpath.write_text(json.dumps(bad))
        assert rk.verify_snapshot(snap), bad
    # A missing manifest.
    mpath.unlink()
    assert rk.verify_snapshot(snap) == ["no manifest.json"]
    mpath.write_bytes(good)
    assert rk.verify_snapshot(snap) == []


def test_verify_snapshot_ignores_unlisted_files(tmp_path, capsys):
    root = tmp_path / "lib"
    snap = _taken(root, capsys)
    (snap / ".DS_Store").write_bytes(b"\0finder")
    (snap / "shows" / SLUG / ".DS_Store").write_bytes(b"\0finder")
    (snap / "shows" / SLUG / "stray.json").write_text("{}")
    assert rk.verify_snapshot(snap) == []


# --- --apply (plan Task 19; spec 4.3 "`--apply`", "Routes for an `--apply` refusal") ---

from helpers import tree_bytes
from llama.override_keys import classify, rekey_raw

D1, D2, D3, D4 = "1973-06-10", "1973-06-11", "1973-06-12", "1973-06-13"
S1, S2, S3, S4 = (f"gratefuldead-{d}" for d in (D1, D2, D3, D4))
THEN = ("  then: reinstall v2.17.0, repair {slug} with it (route below), then return to "
        "step 2 (dry run) and take a NEW snapshot")
FIRST = "  first: run --restore {snap} with the new binary, then reinstall v2.17.0"


def _apply(root: Path, capsys) -> tuple[int, str]:
    rc = rk.main(["--config", str(_config(root)), "--apply"])
    return rc, capsys.readouterr().out


def _snapped(root: Path, capsys, now=None) -> Path:
    """Take a snapshot of the library as it is (through `snapshot`, so the migration lock
    file exists afterwards, as after a real `--snapshot`)."""
    _config(root)
    snap = rk.snapshot(root, echo=lambda *a: None, now=now)
    capsys.readouterr()
    assert rk.verify_snapshot(snap) == []
    return snap


def _three(root: Path) -> list[ShowWorkspace]:
    """Titles only; breaks plus encore; `set_breaks: []` plus titles."""
    return [_show(root, date=D1, titles={1: "Dew", 4: "Star"}),
            _show(root, date=D2, set_breaks=[3], encore_after=5),
            _show(root, date=D3, titles={2: "Cat"}, set_breaks=[])]


def _record(root: Path) -> dict:
    return json.loads((root / rk.APPLIED).read_text())


def _refused_block(lines: list[str], slug: str, reason: str) -> list[str]:
    """The refusal line for `slug`/`reason` and every indented line under it."""
    i = next(i for i, l in enumerate(lines) if l.startswith(f"refused: {slug}: {reason} ("))
    j = i + 1
    while j < len(lines) and lines[j].startswith("  "):
        j += 1
    return lines[i:j]


def test_version_ok():
    for good in ("2.18.0", "2.18.0\n", " 2.18.1 ", "2.19", "2.18", "3.0.0", "10.0.0",
                 "2.100.0"):
        assert rk.version_ok(good), good
    for bad in ("2.17.0", "2.17.9", "2.9.0", "0.1.0", "0.0.0+unknown", "", "junk",
                "llama 2.18.0", "v2.18.0", "2.18.0rc1", "2.18.0+dirty", "2.18.0\n2.18.0",
                "2", "2..18", "２.18.0"):
        assert not rk.version_ok(bad), bad


def test_llama_versions_reads_every_llama_on_path(tmp_path, monkeypatch):
    """`which -a llama`, then `<path> --version` for each; a failing binary is reported
    with its exit status (version_ok then refuses it)."""
    monkeypatch.undo()          # the autouse stub replaces llama_versions; use the real one
    bins = []
    for name, body in (("a", "echo 2.18.0"), ("b", "echo 0.1.0"), ("c", "echo oops >&2; exit 3")):
        d = tmp_path / name
        d.mkdir()
        exe = d / "llama"
        exe.write_text(f"#!/bin/sh\n{body}\n")
        exe.chmod(0o755)
        bins.append(str(exe))
    monkeypatch.setenv("PATH", ":".join(str(Path(b).parent) for b in bins) + ":/usr/bin:/bin")
    got = rk.llama_versions()
    assert got[:2] == [(bins[0], "2.18.0"), (bins[1], "0.1.0")]
    assert got[2][0] == bins[2] and "3" in got[2][1] and "oops" in got[2][1]
    assert not rk.version_ok(got[2][1])
    assert len(got) == 3
    monkeypatch.setenv("PATH", str(tmp_path / "empty") + ":/usr/bin:/bin")
    assert rk.llama_versions() == []


def test_apply_refuses_without_a_snapshot(tmp_path, capsys):
    root = tmp_path / "lib"
    _three(root)
    _config(root)
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    assert rc == 1
    assert any(l.startswith("no verified snapshot: ") for l in out.splitlines()), out
    assert "rekeyed" not in out
    assert tree_bytes(root) == before
    assert not (root / rk.LOCK).exists()


@pytest.mark.parametrize("damage", ["deleted", "changed", "manifest"])
def test_apply_refuses_a_snapshot_with_a_deleted_or_changed_file(tmp_path, capsys, damage):
    root = tmp_path / "lib"
    _three(root)
    snap = _snapped(root, capsys)
    victim = snap / "shows" / S2 / "provenance.json"
    if damage == "deleted":
        victim.unlink()
    elif damage == "changed":
        victim.write_bytes(victim.read_bytes() + b" ")
    else:
        (snap / "manifest.json").unlink()      # no manifest: no snapshot at all
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    assert rc == 1
    (line,) = [l for l in out.splitlines() if l.startswith("no verified snapshot: ")]
    if damage != "manifest":
        assert f"{S2}/provenance.json" in line
    assert "rekeyed" not in out
    assert tree_bytes(root) == before


def test_apply_uses_the_newest_snapshot(tmp_path, capsys):
    """An older verified snapshot does not rescue a damaged newest one."""
    root = tmp_path / "lib"
    _three(root)
    _snapped(root, capsys, now=datetime(2026, 10, 24, 1, 0, 0, tzinfo=timezone.utc))
    new = _snapped(root, capsys, now=datetime(2026, 10, 24, 2, 0, 0, tzinfo=timezone.utc))
    (new / "shows" / S1 / "show.json").unlink()
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    assert rc == 1
    assert f"{S1}/show.json" in out
    assert tree_bytes(root) == before


def test_apply_refuses_a_show_the_snapshot_does_not_cover(tmp_path, capsys):
    """Shows created or edited after the snapshot: all refused up front, nothing
    written, the consistent show included."""
    root = tmp_path / "lib"
    _show(root, date=D1, titles={1: "Dew"})
    ws2 = _show(root, date=D2, titles={2: "Cat"})
    ws3 = _show(root, date=D3, titles={3: "Dew"})
    snap = _snapped(root, capsys)
    _show(root, date=D4, titles={1: "Dew"})                       # created after
    # Same content, other bytes: still legacy and consistent, so only the snapshot
    # comparison can refuse it.
    ws2.overrides.write_text(json.dumps(json.loads(ws2.overrides.read_text())))
    ws3.show.write_text(json.dumps(json.loads(ws3.show.read_text())))
    for ws in (ws2, ws3):
        assert isinstance(rk.check_show(ws, _ia(root), WANT), rk.Rekey)
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    lines = out.splitlines()
    assert rc == 1
    b4 = _refused_block(lines, S4, "not in the snapshot")
    b2 = _refused_block(lines, S2, "changed since the snapshot")
    b3 = _refused_block(lines, S3, "changed since the snapshot")
    assert "overrides.json" in b2[0] and "show.json" in b3[0]
    assert snap.name in b4[0]
    for slug, block in ((S2, b2), (S3, b3), (S4, b4)):
        assert block[1] == THEN.format(slug=slug)
        assert block[2].startswith("  repair: ")
    assert not any(l.startswith(f"refused: {S1}") for l in lines)
    assert "--restore" not in out
    assert "rekeyed" not in out.replace("0 rekeyed", "")
    assert tree_bytes(root) == before


@pytest.mark.parametrize("versions,expect", [
    ([("/a/llama", "2.17.0")], ["llama on PATH below 2.18.0: /a/llama 2.17.0"]),
    ([("/a/llama", "0.1.0")], ["llama on PATH below 2.18.0: /a/llama 0.1.0"]),
    ([("/a/llama", "0.0.0+unknown")], ["llama on PATH below 2.18.0: /a/llama 0.0.0+unknown"]),
    ([], ["no llama on PATH"]),
    ([("/a/llama", "2.18.0"), ("/b/llama", "2.17.0")],
     ["llama on PATH below 2.18.0: /b/llama 2.17.0"]),
], ids=["2.17.0", "0.1.0", "dev-unknown", "none", "one-good-one-low"])
def test_apply_refuses_a_low_or_dev_or_missing_llama(tmp_path, capsys, monkeypatch, versions,
                                                     expect):
    root = tmp_path / "lib"
    _three(root)
    _snapped(root, capsys)
    monkeypatch.setattr(rk, "llama_versions", lambda: versions)
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    lines = out.splitlines()
    assert rc == 1
    for line in expect:
        assert line in lines, out
    assert "/a/llama 2.18.0" not in out
    assert "rekeyed" not in out
    assert tree_bytes(root) == before


def test_apply_refuses_a_failed_version_check(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    _three(root)
    _snapped(root, capsys)

    def boom():
        raise OSError("no which")
    monkeypatch.setattr(rk, "llama_versions", boom)
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    assert rc == 1
    assert "no which" in out
    assert tree_bytes(root) == before


def test_apply_refuses_while_llama_runs(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    _three(root)
    _snapped(root, capsys)
    line = "601 1 /usr/local/bin/llama run resume --all"
    monkeypatch.setattr(rk, "_ps_lines", lambda: [line])
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    assert rc == 1
    assert "llama processes running:" in out.splitlines()
    assert f"  {line}" in out.splitlines()
    assert "rekeyed" not in out
    assert tree_bytes(root) == before

    def boom():
        raise OSError("no ps")
    monkeypatch.setattr(rk, "_ps_lines", boom)
    rc, out = _apply(root, capsys)
    assert rc == 1
    assert "process check failed: OSError: no ps" in out
    assert tree_bytes(root) == before


def test_a_held_migration_lock_refuses_the_apply(tmp_path, capsys):
    root = tmp_path / "lib"
    _three(root)
    _snapped(root, capsys)
    before = tree_bytes(root)
    with file_lock(root / rk.LOCK):
        rc, out = _apply(root, capsys)
    assert rc == 1
    assert rk.LOCK in out
    assert tree_bytes(root) == before


def test_apply_writes_nothing_when_any_show_would_be_refused(tmp_path, capsys):
    root = tmp_path / "lib"
    _show(root, date=D1, titles={1: "Dew"})
    _show(root, date=D2, legacy={"titles": {"1": "Wrong"}})
    _show(root, date=D3, set_breaks=[3], encore_after=5)
    _snapped(root, capsys)
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    lines = out.splitlines()
    assert rc == 1
    block = _refused_block(lines, S2, "title not applied")
    assert block[1:] == [THEN.format(slug=S2),
                         f"  repair: `llama redo {S2} --from gather`"]
    assert "--restore" not in out
    assert not any(l.startswith("rekeyed:") for l in lines)
    assert tree_bytes(root) == before
    assert not (root / rk.APPLIED).exists()


def test_apply_rekeys_and_records(tmp_path, capsys):
    root = tmp_path / "lib"
    wss = _three(root)
    old = [json.loads(ws.overrides.read_text()) for ws in wss]
    gathered = [json.loads(ws.show.read_text()) for ws in wss]
    snap = _snapped(root, capsys)
    rc, out = _apply(root, capsys)
    lines = out.splitlines()
    assert rc == 0, out
    assert [l for l in lines if l.startswith("rekeyed:")] == [
        f"rekeyed: {S1} (2 titles, 0 breaks)",
        f"rekeyed: {S2} (0 titles, 1 breaks, encore)",
        f"rekeyed: {S3} (1 titles, 0 breaks)"]
    for ws, o in zip(wss, old):
        assert ws.overrides.read_bytes() == json.dumps(rekey_raw(o, F), indent=2).encode()
        assert classify(json.loads(ws.overrides.read_text())) == "filename"
    assert json.loads(wss[2].overrides.read_text())["set_breaks"] == []
    rec = _record(root)
    assert set(rec) == {"snapshot", "updated_at", "shows"}
    assert rec["snapshot"] == snap.name
    assert rec["shows"] == [S1, S2, S3]
    assert datetime.fromisoformat(rec["updated_at"]).utcoffset().total_seconds() == 0
    assert not [p for p in root.rglob("*.tmp")]
    # A later gather of each show (today's code reads only the filename form) lands every
    # title, break and encore on the same files.
    for ws, date, was in zip(wss, (D1, D2, D3), gathered):
        ov = ws.overrides.read_bytes()
        library_show(root, held=False, date=date)
        now = json.loads(ws.show.read_text())
        assert ws.overrides.read_bytes() == ov
        assert [(t["filename"], t["title"], t["title_source"], t["set"]) for t in now["tracks"]] \
            == [(t["filename"], t["title"], t["title_source"], t["set"]) for t in was["tracks"]]
        assert now["set_breaks"] == was["set_breaks"]
    assert [t["title"] for t in json.loads(wss[0].show.read_text())["tracks"]][0] == "Dew"
    assert json.loads(wss[1].show.read_text())["set_breaks"] == [3, 5]
    assert json.loads(wss[2].show.read_text())["set_breaks"] == []


def test_unknown_keys_survive_the_raw_rewrite(tmp_path, capsys):
    root = tmp_path / "lib"
    legacy = {"zz": {"a": 1}, "narration": "vague", "titles": {"4": "Star", "1": "Dew"},
              "exclude": [], "venue": None, "yy": [1, "2", None]}
    ws = _show(root, titles={1: "Dew", 4: "Star"}, legacy=legacy)
    _snapped(root, capsys)
    rc, out = _apply(root, capsys)
    assert rc == 0, out
    got = json.loads(ws.overrides.read_text())
    assert list(got.items()) == [("zz", {"a": 1}), ("narration", "vague"),
                                 ("titles", {F[3]: "Star", F[0]: "Dew"}), ("exclude", []),
                                 ("venue", None), ("yy", [1, "2", None])]
    assert list(got["titles"]) == [F[3], F[0]]


def _edit_under_the_lock(monkeypatch, slug: str, edit):
    """Run `edit` on `slug`'s workspace just before the per-show step for it: after the
    up-front checks passed."""
    real = rk._rekey_show

    def wrapped(ws, *args, **kwargs):
        if ws.dir.name == slug:
            edit(ws)
        return real(ws, *args, **kwargs)
    monkeypatch.setattr(rk, "_rekey_show", wrapped)


@pytest.mark.parametrize("which", ["overrides.json", "show.json"])
def test_edit_after_the_snapshot_refuses_under_the_lock(tmp_path, capsys, monkeypatch, which):
    root = tmp_path / "lib"
    ws1, ws2, ws3 = _three(root)
    snap = _snapped(root, capsys)
    third = tree_bytes(ws3.dir)

    def edit(ws):
        p = ws.dir / which
        p.write_text(json.dumps(json.loads(p.read_text())))   # same content, other bytes
    _edit_under_the_lock(monkeypatch, S2, edit)
    rc, out = _apply(root, capsys)
    lines = out.splitlines()
    assert rc == 1
    assert f"rekeyed: {S1} (2 titles, 0 breaks)" in lines
    assert not any(l.startswith((f"rekeyed: {S2}", f"rekeyed: {S3}")) for l in lines)
    block = _refused_block(lines, S2, "changed since the snapshot")
    assert which in block[0]
    assert block[1] == FIRST.format(snap=snap)
    assert block[2] == THEN.format(slug=S2)
    assert block[3].startswith("  repair: ")
    assert classify(json.loads(ws1.overrides.read_text())) == "filename"
    assert classify(json.loads(ws2.overrides.read_text())) == "legacy"
    assert tree_bytes(ws3.dir) == third
    assert _record(root)["shows"] == [S1]


def test_a_check_failing_under_the_lock_refuses_and_stops(tmp_path, capsys, monkeypatch):
    """The checks are re-run on what was read under the lock: here the cached metadata
    changes after the up-front pass, so the kept list differs."""
    root = tmp_path / "lib"
    ws1, ws2, ws3 = _three(root)
    snap = _snapped(root, capsys)
    _edit_under_the_lock(monkeypatch, S2, lambda ws: _drop_first_file(root))
    rc, out = _apply(root, capsys)
    lines = out.splitlines()
    assert rc == 1
    block = _refused_block(lines, S2, "kept list differs")
    assert block[1] == FIRST.format(snap=snap)
    assert classify(json.loads(ws2.overrides.read_text())) == "legacy"
    assert classify(json.loads(ws3.overrides.read_text())) == "legacy"
    assert _record(root)["shows"] == [S1]


def _drop_first_file(root: Path):
    path = root / "cache" / f"md_{IDENT}.json"
    md = json.loads(path.read_text())
    md["files"] = [f for f in md["files"] if f["name"] != F[0]]
    path.write_text(json.dumps(md))


def test_interrupted_apply_continues(tmp_path, capsys, monkeypatch):
    """An exception after the first show's rename and before its record: a re-run
    records it (its file is exactly what the migration writes), rekeys the rest and
    never rewrites it again."""
    root = tmp_path / "lib"
    ws1, ws2, ws3 = _three(root)
    snap = _snapped(root, capsys)
    real = rk._write_record

    def boom(*a, **k):
        raise RuntimeError("power cut")
    monkeypatch.setattr(rk, "_write_record", boom)
    rc, out = _apply(root, capsys)
    assert rc == 1
    assert "power cut" in out
    assert classify(json.loads(ws1.overrides.read_text())) == "filename"
    assert classify(json.loads(ws2.overrides.read_text())) == "legacy"
    assert not (root / rk.APPLIED).exists()
    first = ws1.overrides.read_bytes()
    monkeypatch.setattr(rk, "_write_record", real)
    rc, out = _apply(root, capsys)
    lines = out.splitlines()
    assert rc == 0, out
    assert not any(l.startswith(f"rekeyed: {S1}") for l in lines)
    assert f"rekeyed: {S2} (0 titles, 1 breaks, encore)" in lines
    assert f"rekeyed: {S3} (1 titles, 0 breaks)" in lines
    assert ws1.overrides.read_bytes() == first
    rec = _record(root)
    assert rec["snapshot"] == snap.name
    assert rec["shows"] == [S1, S2, S3]


def test_interrupted_after_the_record_continues(tmp_path, capsys, monkeypatch):
    """A failure on the second show: the first is recorded, a re-run finishes."""
    root = tmp_path / "lib"
    _three(root)
    _snapped(root, capsys)
    real = rk._rekey_show

    def fail_second(ws, *a, **k):
        if ws.dir.name == S2:
            raise OSError("disk full")
        return real(ws, *a, **k)
    monkeypatch.setattr(rk, "_rekey_show", fail_second)
    rc, out = _apply(root, capsys)
    assert rc == 1 and "disk full" in out
    assert _record(root)["shows"] == [S1]
    monkeypatch.setattr(rk, "_rekey_show", real)
    rc, out = _apply(root, capsys)
    assert rc == 0, out
    assert _record(root)["shows"] == [S1, S2, S3]


def test_apply_after_a_restore_starts_a_fresh_record(tmp_path, capsys):
    root = tmp_path / "lib"
    ws1, ws2, ws3 = _three(root)
    first = _snapped(root, capsys, now=datetime(2026, 10, 24, 1, 0, 0, tzinfo=timezone.utc))
    rc, out = _apply(root, capsys)
    assert rc == 0, out
    assert _record(root)["shows"] == [S1, S2, S3]
    rc, out = _restore(root, first, capsys)
    assert rc == 0, out
    assert not (root / rk.APPLIED).exists()
    assert classify(json.loads(ws1.overrides.read_text())) == "legacy"
    ws2.overrides.unlink()                    # repaired with v2.17.0: no overrides now
    ws3.overrides.unlink()
    second = _snapped(root, capsys, now=datetime(2026, 10, 24, 2, 0, 0, tzinfo=timezone.utc))
    rc, out = _apply(root, capsys)
    assert rc == 0, out
    rec = _record(root)
    assert rec["snapshot"] == second.name
    assert rec["shows"] == [S1]


def test_a_record_of_another_snapshot_refuses(tmp_path, capsys):
    """rekey-applied.json naming a snapshot other than the newest (no restore renamed
    it) is ambiguous: refused, nothing written."""
    root = tmp_path / "lib"
    _three(root)
    _snapped(root, capsys)
    (root / rk.APPLIED).write_text(json.dumps(
        {"snapshot": "rekey-snapshot-20200101T000000Z", "updated_at": "2020-01-01T00:00:00+00:00",
         "shows": []}, indent=2))
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    assert rc == 1
    assert "rekey-snapshot-20200101T000000Z" in out
    assert tree_bytes(root) == before
    (root / rk.APPLIED).write_text("{")
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    assert rc == 1
    assert rk.APPLIED in out
    assert tree_bytes(root) == before


def test_apply_output_and_exit_codes(tmp_path, capsys):
    root = tmp_path / "lib"
    _show(root, date=D1, titles={1: "Dew"}, set_breaks=[3], encore_after=5)
    _show(root, date=D2)                                    # no overrides.json
    _show(root, date=D3, legacy={"set_breaks": []})         # no positional value
    _snapped(root, capsys)
    rc, out = _apply(root, capsys)
    lines = out.splitlines()
    assert rc == 0, out
    assert "llama processes running: none" in lines
    assert f"rekeyed: {S1} (1 titles, 1 breaks, encore)" in lines
    assert lines[-1] == "1 rekeyed, 0 refused, 0 already migrated, 2 without positional keys"
    assert "refused:" not in out
    # A re-run has nothing left to do and succeeds.
    rc, out = _apply(root, capsys)
    lines = out.splitlines()
    assert rc == 0, out
    assert not any(l.startswith("rekeyed:") for l in lines)
    assert lines[-1] == "0 rekeyed, 0 refused, 1 already migrated, 2 without positional keys"
    assert _record(root)["shows"] == [S1]
    # A refusal: exit 1, and the summary counts it.
    _show(root, date=D4, legacy={"titles": {"9": "X"}})
    rc, out = _apply(root, capsys)
    assert rc == 1
    assert out.splitlines()[-2:] == [
        "0 to rekey, 1 refused, 1 already migrated, 2 without positional keys",
        "nothing written"]


def test_a_rekey_that_does_not_round_trip_is_refused(tmp_path, capsys, monkeypatch):
    """The rewritten object must resolve to exactly the legacy positions: a mapping
    defect refuses the show and writes nothing for it."""
    root = tmp_path / "lib"
    ws1, ws2, ws3 = _three(root)
    _snapped(root, capsys)
    real = rk.rekey_raw

    def swapped(raw, names):
        return real(raw, [names[1], names[0], *names[2:]])
    monkeypatch.setattr(rk, "rekey_raw", swapped)
    before = tree_bytes(ws1.dir)
    rc, out = _apply(root, capsys)
    assert rc == 1
    block = _refused_block(out.splitlines(), S1, "rekey does not round-trip")
    assert block[1] == THEN.format(slug=S1)
    assert tree_bytes(ws1.dir) == before
    assert not (root / rk.APPLIED).exists()
    assert "rekeyed" not in out.replace("0 rekeyed", "")


def test_a_migrated_show_apply_did_not_write_is_not_recorded(tmp_path, capsys, monkeypatch):
    """Only a file byte-equal to what --apply writes from the snapshot is taken as an
    interrupted run's: any other filename-form file is neither recorded nor rewritten."""
    root = tmp_path / "lib"
    ws1, ws2, ws3 = _three(root)
    _snapped(root, capsys)
    monkeypatch.setattr(rk, "_write_record", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("power cut")))
    assert _apply(root, capsys)[0] == 1
    monkeypatch.undo()
    monkeypatch.setattr(rk, "_ps_lines", lambda: [])
    monkeypatch.setattr(rk, "llama_versions", lambda: [("/a/llama", "2.18.0")])
    edited = json.loads(ws1.overrides.read_text())
    edited["titles"][F[0]] = "Other"
    ws1.overrides.write_text(json.dumps(edited, indent=2))
    edited_bytes = ws1.overrides.read_bytes()
    rc, out = _apply(root, capsys)
    assert rc == 0, out
    assert "recorded:" not in out
    assert _record(root)["shows"] == [S2, S3]
    assert ws1.overrides.read_bytes() == edited_bytes


# --- --restore (plan Task 20; spec 4.3 "`--restore <snapshot-dir>`", "Why audio comes
# first", "What restore does not revert", "Restore runbook") ---

import os
import re

NOT_REVERTED = "not reverted: the ledger, runs/, the cache, reapply batch progress"
NEXT = ("next: reinstall v2.17.0 from the release; check llama --version reports 2.17.0; "
        "restart the sweep loop")
RESTORED_RECORD = re.compile(r"rekey-applied\.restored-\d{8}T\d{6}Z\.json")


def _restore(root: Path, snap: Path, capsys, station: Path | None = None) -> tuple[int, str]:
    cfg = _config(root)
    if station is not None:
        cfg.write_text(f'root = "{root}"\ndelivery_path = "{station}"\n\n'
                       f'[jerrybase]\nenabled = false\n')
    rc = rk.main(["--config", str(cfg), "--restore", str(snap)])
    return rc, capsys.readouterr().out


def _outside_audio(ws: ShowWorkspace) -> dict[str, bytes]:
    return {r: b for r, b in tree_bytes(ws.dir).items() if not r.startswith("package/audio/")}


def _audio(ws: ShowWorkspace) -> list[str]:
    d = ws.package_dir / "audio"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


def _package(ws: ShowWorkspace, manifest: str, audio: dict[str, bytes]):
    (ws.package_dir / "audio").mkdir(parents=True, exist_ok=True)
    (ws.package_dir / "manifest.json").write_text(manifest)
    for name, data in audio.items():
        (ws.package_dir / "audio" / name).write_bytes(data)


def _restored_records(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if RESTORED_RECORD.fullmatch(p.name))


def test_restore_refuses_a_hash_mismatch_and_writes_nothing(tmp_path, capsys):
    root = tmp_path / "lib"
    _three(root)
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    victim = snap / "shows" / S2 / "show.json"
    victim.write_bytes(victim.read_bytes() + b" ")
    before = tree_bytes(root)
    rc, out = _restore(root, snap, capsys)
    assert rc == 1
    (line,) = [l for l in out.splitlines() if l.startswith("refusing to restore: ")]
    assert f"{S2}/show.json" in line
    assert "restored:" not in out
    assert tree_bytes(root) == before
    assert (root / rk.APPLIED).exists()
    # No manifest at all: no snapshot.
    (snap / "manifest.json").unlink()
    before = tree_bytes(root)
    rc, out = _restore(root, snap, capsys)
    assert rc == 1 and "no manifest.json" in out
    assert tree_bytes(root) == before


def test_restore_refuses_while_a_show_created_after_the_snapshot_exists(tmp_path, capsys):
    root = tmp_path / "lib"
    _three(root)
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    _show(root, date=D4, titles={1: "Dew"})
    before = tree_bytes(root)
    rc, out = _restore(root, snap, capsys)
    lines = out.splitlines()
    assert rc == 1
    i = lines.index(f"created after the snapshot: {S4}")
    assert lines[i + 1] == (f"  route: llama rm {S4} (add --forget if a later get should "
                            f"re-fetch it)")
    assert any(l.startswith("refusing to restore: ") for l in lines)
    assert not any(l.startswith(f"created after the snapshot: {s}")
                   for l in lines for s in (S1, S2, S3))
    assert "restored:" not in out
    assert tree_bytes(root) == before


def test_restore_refuses_while_llama_runs(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    _three(root)
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    line = "601 1 /bin/zsh -c while true; do llama run resume --all; sleep 600; done"
    monkeypatch.setattr(rk, "_ps_lines", lambda: [line])
    before = tree_bytes(root)
    rc, out = _restore(root, snap, capsys)
    assert rc == 1
    assert "llama processes running:" in out.splitlines()
    assert f"  {line}" in out.splitlines()
    assert "restored:" not in out
    assert tree_bytes(root) == before

    def boom():
        raise OSError("no ps")
    monkeypatch.setattr(rk, "_ps_lines", boom)
    rc, out = _restore(root, snap, capsys)
    assert rc == 1
    assert "process check failed: OSError: no ps" in out
    assert tree_bytes(root) == before


def test_a_held_migration_lock_refuses_the_restore(tmp_path, capsys):
    root = tmp_path / "lib"
    _three(root)
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    before = tree_bytes(root)
    with file_lock(root / rk.LOCK):
        rc, out = _restore(root, snap, capsys)
    assert rc == 1
    assert rk.LOCK in out and "restored:" not in out
    assert tree_bytes(root) == before


def test_restore_puts_every_file_back_byte_equal_and_deletes_files_written_since(tmp_path,
                                                                                capsys):
    root = tmp_path / "lib"
    ws = _full_show(root)                 # its .audio-aside/ predates the snapshot
    other = _show(root, date=D2, titles={2: "Cat"})
    other.notes.unlink(missing_ok=True)   # so its notes.json below is written since
    ws_notes = ws.notes.read_bytes()
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    assert classify(json.loads(ws.overrides.read_text())) == "filename"
    _edit_show(ws, lambda d: d.update(review_flags=["something new"]))
    ws.notes.write_text('{"notes": ["new"]}')
    ws.briefing_json.write_text("{}")
    (ws.dir / ".txn" / "package").mkdir(parents=True)
    (ws.dir / ".txn" / "show.json").write_text("{}")
    (ws.dir / ".txn" / "package" / "manifest.json").write_text("{}")
    (ws.package_dir / "extra").mkdir()
    (ws.package_dir / "extra" / "x.txt").write_text("x")
    other.notes.write_text("{}")
    assert (ws.dir / ".audio-aside" / F[1]).exists()
    lock_before = ws.lock.read_bytes()
    rc, out = _restore(root, snap, capsys)
    lines = out.splitlines()
    assert rc == 0, out
    assert f"restored: {SLUG}" in lines and f"restored: {S2}" in lines
    for w in (ws, other):
        assert _outside_audio(w) == tree_bytes(snap / "shows" / w.dir.name)
    assert classify(json.loads(ws.overrides.read_text())) == "legacy"
    assert not (ws.dir / ".txn").exists()
    assert not (ws.dir / ".audio-aside").exists()
    assert not (ws.package_dir / "extra").exists()
    assert ws.notes.read_bytes() == ws_notes and not other.notes.exists()
    assert ws.lock.exists() and ws.lock.read_bytes() == lock_before
    assert _audio(ws) == [F[0]]          # package/manifest.json unchanged: audio kept
    assert not [p for p in root.rglob("*.tmp")]
    assert lines[-1] == NEXT
    assert NOT_REVERTED in lines


def test_restore_empties_audio_unless_the_manifest_is_byte_equal(tmp_path, capsys):
    root = tmp_path / "lib"
    same = _show(root, date=D1, titles={1: "Dew"})
    repack = _show(root, date=D2, titles={2: "Cat"})
    fresh = _show(root, date=D3, titles={3: "Dew"})
    _package(same, '{"tracks": ["a"]}', {F[0]: b"old a"})
    _package(repack, '{"tracks": ["b"]}', {F[0]: b"old b"})
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    _package(repack, '{"tracks": ["b", "new"]}', {F[0]: b"new b0", F[1]: b"new b1"})
    _package(fresh, '{"tracks": ["c"]}', {F[0]: b"new c"})
    rc, out = _restore(root, snap, capsys)
    lines = out.splitlines()
    assert rc == 0, out
    assert _audio(same) == [F[0]]
    assert (same.package_dir / "audio" / F[0]).read_bytes() == b"old a"
    assert f"restored: {S1}" in lines
    assert _audio(repack) == []
    assert (repack.package_dir / "manifest.json").read_text() == '{"tracks": ["b"]}'
    assert f"restored: {S2} (audio emptied)" in lines
    assert _audio(fresh) == []
    assert not (fresh.package_dir / "manifest.json").exists()
    assert f"restored: {S3} (audio emptied)" in lines
    for w in (same, repack, fresh):
        assert _outside_audio(w) == tree_bytes(snap / "shows" / w.dir.name)


@pytest.mark.parametrize("fail_at", ["overrides.json", "show.json"])
def test_crash_after_emptying_then_rerun_leaves_no_audio_beside_the_restored_manifest(
        tmp_path, capsys, monkeypatch, fail_at):
    """A crash in the copy step, before (`overrides.json`) or after (`show.json`) the
    package manifest is copied back: the audio was emptied first, so a re-run, which
    may then find the manifests equal, never keeps the new-numbered audio."""
    root = tmp_path / "lib"
    ws = _show(root, date=D1, titles={1: "Dew"})
    _show(root, date=D2, titles={2: "Cat"})
    _package(ws, '{"tracks": ["old"]}', {F[0]: b"old"})
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    _package(ws, '{"tracks": ["new"]}', {F[0]: b"new 0", F[1]: b"new 1"})
    _edit_show(ws, lambda d: d.update(review_flags=["re-gathered"]))
    real = rk._durable_write

    def crash(path, data):
        if path.parent == ws.dir and path.name == fail_at:
            raise RuntimeError("power cut")
        return real(path, data)
    monkeypatch.setattr(rk, "_durable_write", crash)
    rc, out = _restore(root, snap, capsys)
    assert rc == 1 and "power cut" in out
    assert _audio(ws) == []
    want_manifest = fail_at == "show.json"
    assert ((ws.package_dir / "manifest.json").read_text() == '{"tracks": ["old"]}') \
        == want_manifest
    assert (root / rk.APPLIED).exists()
    monkeypatch.setattr(rk, "_durable_write", real)
    rc, out = _restore(root, snap, capsys)
    assert rc == 0, out
    assert _audio(ws) == []
    assert (ws.package_dir / "manifest.json").read_text() == '{"tracks": ["old"]}'
    assert _outside_audio(ws) == tree_bytes(snap / "shows" / S1)


def test_restore_lists_what_it_does_not_revert(tmp_path, capsys):
    root = tmp_path / "lib"
    station = tmp_path / "station"
    _three(root)
    (root / "reapply" / "oldbatch").mkdir(parents=True)
    (root / "runs" / "old-run").mkdir(parents=True)
    for slug in (S1, S2, S3):
        (station / slug).mkdir(parents=True)
        (station / slug / "manifest.json").write_text('{"dj_audio": null}')
    (station / S2 / "song.mp3").write_bytes(b"audio")
    time.sleep(0.05)
    snap = _snapped(root, capsys)
    time.sleep(0.05)
    assert _apply(root, capsys)[0] == 0
    (root / "reapply" / "newbatch").mkdir()
    (root / "reapply" / "newbatch" / "progress.jsonl").write_text("")
    (root / "runs" / "new-run").mkdir()
    (station / S2 / "manifest.json").write_text('{"dj_audio": {"presenter": "phil"}}')
    (station / S3 / "manifest.json").write_text('{"dj_audio": null}')
    (station / "gratefuldead-1973-06-14").mkdir()
    (station / "gratefuldead-1973-06-14" / "manifest.json").write_text("{")
    station_before = _tree_state(station)
    _set_writable(station, False)
    try:
        rc, out = _restore(root, snap, capsys, station=station)
    finally:
        _set_writable(station, True)
    lines = out.splitlines()
    assert rc == 0, out
    assert _tree_state(station) == station_before
    assert NOT_REVERTED in lines
    assert f"  {root / 'reapply' / 'newbatch'}" in lines
    assert f"  {root / 'runs' / 'new-run'}" in lines
    assert f"  {station / S2} (voiced)" in lines
    assert f"  {station / S3}" in lines
    assert f"  {station / 'gratefuldead-1973-06-14'} (unreadable)" in lines
    for gone in ("oldbatch", "old-run", str(station / S1)):
        assert not any(l.strip().startswith(str(root)) and l.endswith(gone) for l in lines)
        assert not any(l.strip() == gone or l.strip().startswith(gone + " ") for l in lines)
    assert (root / "reapply" / "newbatch" / "progress.jsonl").exists()   # listed, not removed
    assert (root / "runs" / "new-run").is_dir()
    assert lines[-1] == NEXT
    # The lists follow the restore and precede the next steps.
    assert lines.index(NOT_REVERTED) > max(i for i, l in enumerate(lines)
                                           if l.startswith("restored: "))


def test_restore_without_a_delivery_path_skips_the_station_list(tmp_path, capsys):
    root = tmp_path / "lib"
    _three(root)
    snap = _snapped(root, capsys)
    rc, out = _restore(root, snap, capsys)
    assert rc == 0, out
    assert any("no delivery_path" in l for l in out.splitlines())


def test_restore_recreates_a_show_removed_since(tmp_path, capsys):
    root = tmp_path / "lib"
    ws1, ws2, ws3 = _three(root)
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    shutil.rmtree(ws2.dir)
    rc, out = _restore(root, snap, capsys)
    assert rc == 0, out
    assert f"restored: {S2}" in out.splitlines()     # it had no audio to empty
    assert _outside_audio(ws2) == tree_bytes(snap / "shows" / S2)
    assert classify(json.loads(ws2.overrides.read_text())) == "legacy"


def test_restore_renames_the_applied_record(tmp_path, capsys, monkeypatch):
    root = tmp_path / "lib"
    _three(root)
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    rec = (root / rk.APPLIED).read_bytes()
    # A failed restore leaves the record in place.
    real = rk._durable_write

    def crash(path, data):
        if path.parent.name == S3:
            raise OSError("disk full")
        return real(path, data)
    monkeypatch.setattr(rk, "_durable_write", crash)
    rc, out = _restore(root, snap, capsys)
    assert rc == 1 and "disk full" in out
    assert f"restored: {S1}" in out.splitlines()
    assert (root / rk.APPLIED).read_bytes() == rec
    assert _restored_records(root) == []
    assert not out.splitlines()[-1] == NEXT
    monkeypatch.setattr(rk, "_durable_write", real)
    rc, out = _restore(root, snap, capsys)
    assert rc == 0, out
    assert not (root / rk.APPLIED).exists()
    (renamed,) = _restored_records(root)
    assert renamed.read_bytes() == rec
    assert f"renamed: {root / rk.APPLIED} -> {renamed}" in out.splitlines()
    # A restore with no record renames nothing.
    rc, out = _restore(root, snap, capsys)
    assert rc == 0, out
    assert _restored_records(root) == [renamed]
    assert "renamed:" not in out


def test_restore_never_follows_a_symlink_out_of_the_show_dir(tmp_path, capsys):
    """A symlinked package/audio/ or stray directory is removed as a link: nothing
    outside the show dir is deleted."""
    root = tmp_path / "lib"
    ws = _show(root, date=D1, titles={1: "Dew"})
    snap = _snapped(root, capsys)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.mp3").write_bytes(b"keep")
    ws.package_dir.mkdir()
    (ws.package_dir / "audio").symlink_to(outside)
    (ws.dir / ".txn").symlink_to(outside)
    rc, out = _restore(root, snap, capsys)
    assert rc == 0, out
    assert (outside / "keep.mp3").read_bytes() == b"keep"
    assert not os.path.lexists(ws.dir / ".txn")
    assert not os.path.lexists(ws.package_dir / "audio")
    assert _outside_audio(ws) == tree_bytes(snap / "shows" / S1)


# --- FW2 (final review fix wave items 7-9, 11-13) ---

def test_first_restore_line_on_the_up_front_refusal_after_an_interrupted_run(
        tmp_path, capsys, monkeypatch):
    """(pin) Item 7 (Task 19 Minor 1): an interrupted --apply left S1 rewritten and
    unrecorded; the re-run refuses S2 and S3 up front, and since the library holds a
    migrated show every refusal names --restore first. Nothing is written."""
    root = tmp_path / "lib"
    ws1, ws2, ws3 = _three(root)
    snap = _snapped(root, capsys)
    real = rk._write_record
    monkeypatch.setattr(rk, "_write_record", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("power cut")))
    assert _apply(root, capsys)[0] == 1
    assert classify(json.loads(ws1.overrides.read_text())) == "filename"
    monkeypatch.setattr(rk, "_write_record", real)
    _drop_first_file(root)                       # S2, S3: the kept list now differs
    before = tree_bytes(root)
    rc, out = _apply(root, capsys)
    lines = out.splitlines()
    assert rc == 1
    for slug in (S2, S3):
        block = _refused_block(lines, slug, "kept list differs")
        assert block[1] == FIRST.format(snap=snap)
        assert block[2] == THEN.format(slug=slug)
    assert "first: run --restore" in out
    assert lines[-1] == "nothing written"
    assert "recorded:" not in out
    assert tree_bytes(root) == before
    assert not (root / rk.APPLIED).exists()


def test_check_show_under_the_lock_judges_the_bytes_read_there(tmp_path, capsys, monkeypatch):
    """(pin) Item 8 (Task 19 Minor 2): `_rekey_show` hands check_show the bytes it read
    under the show lock, never None (which would make it re-read the files)."""
    root = tmp_path / "lib"
    wss = _three(root)
    want = {ws.dir.name: (ws.overrides.read_bytes(), ws.show.read_bytes()) for ws in wss}
    _snapped(root, capsys)
    real_check, real_rekey = rk.check_show, rk._rekey_show
    inside: list[str] = []
    calls: list[tuple] = []

    def rekey(ws, *a, **k):
        inside.append(ws.dir.name)
        try:
            return real_rekey(ws, *a, **k)
        finally:
            inside.pop()

    def check(ws, ia, want_, **kw):
        if inside:
            calls.append((ws.dir.name, kw.get("overrides_bytes"), kw.get("show_bytes")))
        return real_check(ws, ia, want_, **kw)
    monkeypatch.setattr(rk, "_rekey_show", rekey)
    monkeypatch.setattr(rk, "check_show", check)
    rc, out = _apply(root, capsys)
    assert rc == 0, out
    assert [c[0] for c in calls] == [S1, S2, S3]
    for slug, ov, sh in calls:
        assert ov is not None and sh is not None, slug
        assert (ov, sh) == want[slug], slug


def test_restore_repeats_a_listing_failure_before_next(tmp_path, capsys):
    """Item 9 (Task 20 Minor 1): a station or runs listing failure is printed where it
    happens and again just before `next:`, so it is not lost in a long scroll."""
    root = tmp_path / "lib"
    _three(root)
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    station = tmp_path / "station"
    station.write_text("not a directory")         # unlistable delivery_path
    (root / "runs").mkdir()
    (root / "runs").chmod(0)
    try:
        rc, out = _restore(root, snap, capsys, station=station)
    finally:
        (root / "runs").chmod(0o755)
    lines = out.splitlines()
    assert rc == 0, out
    (sw,) = {l for l in lines if l.startswith(f"  warning: cannot list {station}: ")}
    (rw,) = {l for l in lines if l.startswith(f"  warning: cannot list {root / 'runs'}: ")}
    assert lines.count(sw) == 2 and lines.count(rw) == 2
    assert lines[-1] == NEXT
    assert lines[-3:-1] == [rw, sw]
    assert lines.index(sw) < lines.index(NEXT) - 2


def test_snapshot_flushes_the_root_after_its_manifest(tmp_path, capsys, monkeypatch):
    """Item 11 (T18): the root is flushed after manifest.json is renamed into place, so
    the snapshot directory's own entry in the root is durable too."""
    root = tmp_path / "lib"
    _three(root)
    _config(root)
    real = rk._sync_dir
    seen: list[bool] = []

    def spy(d):
        if Path(d) == root:
            seen.append(any(root.glob(f"{rk.SNAPSHOT_PREFIX}*/{rk.MANIFEST}")))
        return real(d)
    monkeypatch.setattr(rk, "_sync_dir", spy)
    snap = rk.snapshot(root, echo=lambda *a: None)
    assert seen and seen[-1] is True
    assert rk.verify_snapshot(snap) == []


def test_restore_refuses_a_snapshot_the_applied_record_does_not_name(tmp_path, capsys):
    """Item 12 (T20): rekey-applied.json names the snapshot the shows were rewritten
    from; restoring another (an older one, a mistyped path) would discard every edit
    between the two. Refused, nothing written; the named one restores."""
    root = tmp_path / "lib"
    ws1, _, _ = _three(root)
    old = _snapped(root, capsys, now=datetime(2026, 10, 24, 1, 0, 0, tzinfo=timezone.utc))
    new = _snapped(root, capsys, now=datetime(2026, 10, 24, 2, 0, 0, tzinfo=timezone.utc))
    assert _apply(root, capsys)[0] == 0
    assert _record(root)["snapshot"] == new.name
    before = tree_bytes(root)
    rc, out = _restore(root, old, capsys)
    assert rc == 1
    (line,) = [l for l in out.splitlines() if l.startswith("refusing to restore: ")]
    assert new.name in line and old.name in line
    assert "restored:" not in out
    assert tree_bytes(root) == before
    # an unreadable record refuses too
    rec = (root / rk.APPLIED).read_bytes()
    (root / rk.APPLIED).write_text("{")
    before = tree_bytes(root)
    rc, out = _restore(root, new, capsys)
    assert rc == 1 and rk.APPLIED in out and "restored:" not in out
    assert tree_bytes(root) == before
    (root / rk.APPLIED).write_bytes(rec)
    rc, out = _restore(root, new, capsys)
    assert rc == 0, out
    assert classify(json.loads(ws1.overrides.read_text())) == "legacy"


def _migrated_three(root: Path, capsys):
    wss = _three(root)
    (wss[1].dir / "extra").mkdir()
    (wss[1].dir / "extra" / "x.txt").write_text("snapshotted")
    snap = _snapped(root, capsys)
    assert _apply(root, capsys)[0] == 0
    return wss, snap


def _stopped_at_s2(root, snap, wss, capsys, message):
    third = tree_bytes(wss[2].dir)
    rec = (root / rk.APPLIED).read_bytes()
    rc, out = _restore(root, snap, capsys)
    lines = out.splitlines()
    assert rc == 1
    assert f"restored: {S1}" in lines
    assert f"error: {S2}: OSError: {message}" in lines
    i = lines.index(f"error: {S2}: OSError: {message}")
    assert lines[i + 1].startswith("stopped: 1 show(s) after it not reached; re-run --restore")
    assert lines[i + 1:] == lines[-1:]                       # nothing printed after the stop
    assert not any(l.startswith(f"restored: {S3}") for l in lines)
    assert tree_bytes(wss[2].dir) == third                  # S3 untouched: still migrated
    assert classify(json.loads(wss[2].overrides.read_text())) == "filename"
    assert (root / rk.APPLIED).read_bytes() == rec           # the record is not renamed
    assert _restored_records(root) == []
    return lines


def test_restore_stops_at_a_directory_where_the_snapshot_holds_a_file(tmp_path, capsys):
    """Item 13 (T20): `_copy_back`'s directory-for-a-file refusal."""
    root = tmp_path / "lib"
    wss, snap = _migrated_three(root, capsys)
    assert f"{S2}/show.json" in json.loads((snap / rk.MANIFEST).read_text())["files"]
    target = wss[1].show
    target.unlink()
    target.mkdir()
    (target / "inside").write_text("keep")
    _stopped_at_s2(root, snap, wss, capsys,
                   f"{target}: a directory where the snapshot holds a file; repair it by hand")
    assert (target / "inside").read_text() == "keep"


def test_restore_stops_at_a_link_on_the_way_to_a_copy(tmp_path, capsys):
    """Item 13 (T20): `_check_inside` refuses a copy through a non-directory: nothing is
    written through the link, and nothing outside the show dir is touched."""
    root = tmp_path / "lib"
    wss, snap = _migrated_three(root, capsys)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.txt").write_text("outside")
    shutil.rmtree(wss[1].dir / "extra")
    (wss[1].dir / "extra").symlink_to(outside)
    _stopped_at_s2(root, snap, wss, capsys,
                   f"{wss[1].dir / 'extra'}: not a directory; repair it by hand")
    assert (outside / "x.txt").read_text() == "outside"
    assert sorted(p.name for p in outside.iterdir()) == ["x.txt"]
    assert (wss[1].dir / "extra").is_symlink()


def test_restore_stops_at_a_record_rename_collision(tmp_path, capsys, monkeypatch):
    """Item 13 (T20): every show restored, then the record's rename target exists: the
    rename is refused, the record and the existing file are left as they are, and no
    `next:` is printed."""
    root = tmp_path / "lib"
    wss, snap = _migrated_three(root, capsys)
    name = "rekey-applied.restored-20261024T030000Z.json"
    monkeypatch.setattr(rk, "_restore_record_name", lambda now: name)
    (root / name).write_text("an earlier restore's record")
    rec = (root / rk.APPLIED).read_bytes()
    rc, out = _restore(root, snap, capsys)
    lines = out.splitlines()
    assert rc == 1
    assert all(f"restored: {s}" in lines for s in (S1, S2, S3))
    assert lines[-1] == (f"error: renaming {root / rk.APPLIED}: {root / name} exists; "
                         f"re-run --restore in a second")
    assert NEXT not in lines and "renamed:" not in out
    assert (root / rk.APPLIED).read_bytes() == rec
    assert (root / name).read_text() == "an earlier restore's record"
