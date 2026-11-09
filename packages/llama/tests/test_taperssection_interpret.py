import json
from pathlib import Path

from herder import FakeProvider
from llama.config import TaperssectionArtist, TaperssectionConfig
from llama.stages.interpret import run_interpret
from llama.taperssection import Allowlist
from llama.workspace import RunWorkspace


def _al(*entries):
    return Allowlist.from_config(TaperssectionConfig(artists=list(entries)))


PHISH = TaperssectionArtist(name="Phish", creators=["Phish"], lineages=["aud"])


def _resp(collection, artist):
    return json.dumps({"query": "x", "collection": collection, "artist": artist, "count": 1})


def _run(tmp_path: Path, collection, artist, allowlist):
    ws = RunWorkspace(tmp_path, "r1")
    return run_interpret(ws, FakeProvider(completes=[_resp(collection, artist)]),
                         "Phish 1997-11-22", allowlist=allowlist)


def test_phish_query_maps_to_key(tmp_path):
    c = _run(tmp_path, "Phish", "Phish", _al(PHISH))
    assert c.collection == "ts-phish"
    assert c.artist == "Phish"
    assert c.query == "Phish 1997-11-22"


def test_jazz_is_phish_untouched(tmp_path):
    c = _run(tmp_path, "JazzIsPhish", "Jazz Is Phish", _al(PHISH))
    assert c.collection == "JazzIsPhish"
    assert c.artist == "Jazz Is Phish"


def test_empty_allowlist_untouched(tmp_path):
    for al in (None, Allowlist.empty()):
        c = _run(tmp_path / str(al is None), "Phish", "Phish", al)
        assert c.collection == "Phish"


def test_none_fields_safe(tmp_path):
    c = _run(tmp_path, None, None, _al(PHISH))
    assert c.collection is None and c.artist is None


def test_allowlist_wins_on_exact_match(tmp_path):
    # Decision (spec "Query mode"): interpret has no index of LMA collections, so
    # when a name exactly matches an allowlisted entry the allowlist wins. The
    # research round keeps allowlisted artists disjoint from LMA collections, so
    # this cannot shadow a real LMA collection in practice.
    e = TaperssectionArtist(name="Goose", creators=["Goose"], lineages=["aud"])
    c = _run(tmp_path, "Goose", "Goose", _al(e))
    assert c.collection == "ts-goose"


def test_stored_criteria_has_mapped_key(tmp_path):
    _run(tmp_path, "Phish", "Phish", _al(PHISH))
    again = run_interpret(RunWorkspace(tmp_path, "r1"), FakeProvider(), "ignored")
    assert again.collection == "ts-phish"


# --- final review M5: the CLI wires the configured allowlist into interpret ---------

_TS_CFG = ('\n[[taperssection.artists]]\nname = "Phish"\ncreators = ["Phish"]\n'
           'lineages = ["aud"]\n')


def _phish_interpret(monkeypatch):
    import llama.cli as cli
    monkeypatch.setattr(cli, "make_providers", lambda config: {
        "interpret": FakeProvider(completes=[_resp("Phish", "Phish")])})


def test_get_and_resume_interpret_with_the_configured_allowlist(tmp_path, monkeypatch):
    """`get` and `run resume` share `_interpret_and_stamp`: "Phish 1997-11-22" must
    resolve to the allowlisted key, not an (empty) LMA "Phish" collection."""
    import llama.cli as cli
    from llama.config import load_config
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n' + _TS_CFG)
    _phish_interpret(monkeypatch)
    ws = RunWorkspace(tmp_path, "r1")
    c = cli._interpret_and_stamp(load_config(cfg), ws, {"query": "Phish 1997-11-22"})
    assert (c.collection, c.artist) == ("ts-phish", "Phish")
    assert json.loads(ws.criteria.read_text())["collection"] == "ts-phish"


def test_profile_add_interprets_with_the_configured_allowlist(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    import llama.cli as cli
    from llama.profiles import load_profile
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n' + _TS_CFG)
    _phish_interpret(monkeypatch)
    res = CliRunner().invoke(cli.app, ["--config", str(cfg), "profile", "add", "ph", "Phish"])
    assert res.exit_code == 0, res.output
    assert load_profile(tmp_path, "ph").criteria.collection == "ts-phish"
