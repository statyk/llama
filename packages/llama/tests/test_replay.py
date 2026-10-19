"""llama.replay: cache-only clients and the harness's input digests (spec slice 0)."""
import json

import pytest

from llama.config import Config
from llama.models import ResearchVetting, VettingResult
from llama.replay import (CacheMiss, CacheOnlyIA, CacheOnlySetlistFM, code_identity,
                          config_fingerprint, input_digests, setlistfm_client)
from llama.setlistfm import cache_key
from llama.workspace import ShowWorkspace, write_artifact


def test_cache_only_ia_reads_the_cache_and_refuses_the_network(tmp_path):
    (tmp_path / "md_x.json").write_text(json.dumps({"metadata": {"title": "t"}, "files": []}))
    ia = CacheOnlyIA(tmp_path)
    assert ia.metadata("x")["metadata"]["title"] == "t"
    with pytest.raises(CacheMiss):
        ia.metadata("missing")
    assert ia.misses == ["missing"]
    for call in (lambda: ia.search("q", ["identifier"]),
                 lambda: ia.scrape("q", ["identifier"]),
                 lambda: ia.download_file("x", "a.mp3", tmp_path / "a.mp3")):
        with pytest.raises(CacheMiss):
            call()


def test_cache_only_setlistfm_uses_the_clients_key_and_counts_misses(tmp_path):
    raw = {"setlist": [{"venue": {"name": "RFK Stadium"}, "sets": {"set": []}}]}
    (tmp_path / (cache_key("Grateful Dead", "1973-06-10") + ".json")).write_text(json.dumps(raw))
    sl = CacheOnlySetlistFM(tmp_path)
    assert sl.setlist("Grateful Dead", "1973-06-10", venue="RFK Stadium") == raw["setlist"][0]
    assert sl.setlist("Grateful Dead", "1973-06-11") is None
    assert sl.misses == [("Grateful Dead", "1973-06-11")]


def test_input_digests_cover_the_five_inputs_and_ignore_vet_flags(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.show, {"a": 1})
    write_artifact(ws.provenance, {"b": 2})
    ws.research.write_text("r")
    v = VettingResult(vetting=ResearchVetting(asserted_songs=["X"]), flags=["research asserts unknown song: X"])
    write_artifact(ws.vetting, v)
    d = input_digests(ws)
    assert set(d) == {"show.json", "overrides.json", "provenance.json", "research.md", "vetting.extraction"}
    assert d["overrides.json"] is None
    write_artifact(ws.vetting, v.model_copy(update={"flags": []}))
    assert input_digests(ws)["vetting.extraction"] == d["vetting.extraction"]
    write_artifact(ws.vetting, v.model_copy(update={"vetting": ResearchVetting(asserted_songs=["Y"])}))
    assert input_digests(ws)["vetting.extraction"] != d["vetting.extraction"]


def test_config_fingerprint_changes_with_structure_and_setlistfm(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    a = config_fingerprint(Config())
    assert a == config_fingerprint(Config())
    assert a != config_fingerprint(Config(structure={"align_coverage_threshold": 0.7}))
    monkeypatch.setenv("SETLISTFM_API_KEY", "k")
    assert a != config_fingerprint(Config())


def test_code_identity_is_a_git_sha_or_a_version_string():
    import re
    ident = code_identity()
    assert re.fullmatch(r"[0-9a-f]{40}(?:-dirty)?", ident) or ident.startswith("version:")


def test_setlistfm_client_is_none_unless_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    assert setlistfm_client(Config(root=tmp_path)) is None
    monkeypatch.setenv("SETLISTFM_API_KEY", "k")
    client = setlistfm_client(Config(root=tmp_path))
    assert isinstance(client, CacheOnlySetlistFM)
