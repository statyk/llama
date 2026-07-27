import json

from typer.testing import CliRunner

import llama.cli as cli
from llama.llm.fake import FakeProvider

runner = CliRunner()

COLLECTIONS = [
    {"identifier": "GratefulDead", "title": "Grateful Dead", "downloads": 226766373},
    {"identifier": "RobynHitchcock", "title": "Robyn Hitchcock", "downloads": 1311958},
    {"identifier": "BackyardBand", "title": "Backyard Band", "downloads": 20},
]

ITEMS = (
    [{"identifier": f"gd{i}", "collection": ["GratefulDead"], "year": "1973"} for i in range(30)]
    + [{"identifier": f"rh{i}", "collection": ["RobynHitchcock"], "year": "1996"} for i in range(30)]
    + [{"identifier": "bb1", "collection": ["BackyardBand"], "year": "2019"}]
)


class ScrapeFakeIA:
    def __init__(self, *args, **kwargs):
        pass

    def scrape(self, query, fields, count=10000):
        if "mediatype:collection" in query:
            return COLLECTIONS
        return ITEMS


def matches_json(*pairs):
    return json.dumps({"matches": [{"identifier": i, "reason": r} for i, r in pairs]})


def setup(tmp_path, monkeypatch, provider):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: ScrapeFakeIA())
    monkeypatch.setattr(cli, "provider_ladder", lambda config, task: provider)
    return ["--config", str(tmp_path / "config.toml")]


def test_artists_query_prints_ranked_table(tmp_path, monkeypatch):
    provider = FakeProvider(completes=[matches_json(("RobynHitchcock", "jangly icon"))])
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, [*cfg, "artists", "jangly college rock"])
    assert result.exit_code == 0, result.output
    assert "Robyn Hitchcock" in result.output
    assert "30" in result.output           # recordings
    assert "1996" in result.output         # years
    assert "1.3M" in result.output         # downloads humanized
    assert "jangly icon" in result.output  # reason
    assert "Backyard Band" not in result.output


def test_artists_filter_excludes_backyard_from_llm_table(tmp_path, monkeypatch):
    provider = FakeProvider(completes=[matches_json(("GratefulDead", "x"))])
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, [*cfg, "artists", "anything"])
    assert result.exit_code == 0, result.output
    prompt = provider.calls[0][1]
    assert "GratefulDead" in prompt and "RobynHitchcock" in prompt
    assert "BackyardBand" not in prompt  # 1 recording, 20 downloads: filtered


def test_artists_no_query_lists_by_recordings_without_llm(tmp_path, monkeypatch):
    provider = FakeProvider()  # any complete() call would raise
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, [*cfg, "artists"])
    assert result.exit_code == 0, result.output
    assert "Grateful Dead" in result.output and "Robyn Hitchcock" in result.output
    assert "Backyard Band" not in result.output
    assert provider.calls == []


def test_artists_include_junk_includes_backyard(tmp_path, monkeypatch):
    provider = FakeProvider()
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, [*cfg, "artists", "--include-junk"])
    assert result.exit_code == 0, result.output
    assert "Backyard Band" in result.output


def test_artists_zero_matches_message(tmp_path, monkeypatch):
    provider = FakeProvider(completes=[matches_json(("NickDrake", "not on LMA"))])
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, [*cfg, "artists", "obscure query"])
    assert result.exit_code == 0, result.output
    assert "no matching artists" in result.output


def test_artists_impossible_thresholds_message(tmp_path, monkeypatch):
    provider = FakeProvider()
    cfg = setup(tmp_path, monkeypatch, provider)
    result = runner.invoke(cli.app, [*cfg, "artists", "anything",
                                     "--min-recordings", "999999",
                                     "--min-downloads", "999999999999"])
    assert result.exit_code == 0, result.output
    assert "no artists pass" in result.output
    assert provider.calls == []
