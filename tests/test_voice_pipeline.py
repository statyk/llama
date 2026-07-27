import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.llm.fake import FakeProvider
from llama.tts.fake import SILENT_MP3, FakeSpeechProvider

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "gd73_metadata.json"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"
SHOW_DIR = "gratefuldead-1973-06-10"

# jerrybase off: same isolation rationale as tests/test_pipeline.py (the
# synthesized candidate's venue differs from the dataset's).
VOICED_CFG = ('{root}\n[jerrybase]\nenabled = false\n'
              '[tts]\nbackend = "fake"\nenabled = true\nvoice = "v-abc"\n')
UNVOICED_CFG = ('{root}\n[jerrybase]\nenabled = false\n'
                '[tts]\nbackend = "fake"\nvoice = "v-abc"\n')  # enabled = false

CRITERIA = json.dumps({
    "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
    "date_from": "1973-01-01", "date_to": "1973-12-31",
    "setlist_constraints": [], "soft_preferences": None,
    "min_avg_rating": 3.5, "min_reviews": 2, "count": 1,
})

ASSESSMENTS = json.dumps({"assessments": [{
    "performance_id": "GratefulDead/1973-06-10", "quality_score": 9.5,
    "non_attendee_evidence": "couchtaper praises the tape",
    "recording_complaints": [], "rationale": "monumental Dark Star",
}]})

NOTES = json.dumps({
    "context": "Peak 1973",
    "set_intros": {"1": "Tonight, the Grateful Dead at RFK Stadium. Morning Dew opens.",
                   "2": "A monumental Dark Star."},
    "outro": "Johnny B. Goode sends us off. From the hollister soundboard.",
    "mentioned_songs": ["Morning Dew", "Dark Star", "Johnny B. Goode"],
})

VET = json.dumps({
    "asserted_songs": ["Morning Dew", "Dark Star"],
    "asserted_dates": ["1973-06-10"],
    "context": "Peak 1973, RFK Stadium",
})


class FakeIA:
    def __init__(self, *args, **kwargs):
        self.fixture = json.loads(FIXTURE.read_text())

    def scrape(self, query, fields, count=10000):
        return [{"identifier": IDENT, "date": "1973-06-10T00:00:00Z",
                 "venue": "RFK Stadium", "coverage": "Washington, DC",
                 "avg_rating": 4.8, "num_reviews": 40,
                 "description": self.fixture["metadata"]["description"]}]

    def metadata(self, identifier):
        return self.fixture

    def download_file(self, identifier, filename, dest, md5=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00" * 64)
        return dest


def fake_providers(config):
    return {
        "interpret": FakeProvider(completes=[CRITERIA]),
        "score_reviews": FakeProvider(completes=[ASSESSMENTS]),
        "light_research": FakeProvider(researches=["Widely ranked top-5 1973 (example.org)"]),
        "extract_setlist": FakeProvider(),
        "deep_research": FakeProvider(researches=[
            "## Reputation\nLegendary RFK show.\n## Performance highlights\nDark Star.\n"
            "## Context\nPeak 73 tour.\n## Recording notes\nHollister SBD."]),
        "synthesize": FakeProvider(completes=[NOTES]),
        "align_structure": FakeProvider(),
        "vet_research": FakeProvider(completes=[VET]),
    }


def voiced_setup(tmp_path, monkeypatch, cfg_template=VOICED_CFG):
    (tmp_path / "config.toml").write_text(
        cfg_template.format(root=f'root = "{tmp_path}"'))
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    return str(tmp_path / "config.toml")


def find(cfg, *extra):
    return runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--auto",
                                   "--name", "voicerun", *extra])


def test_voiced_find_end_to_end(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch)
    result = find(cfg)
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "shows" / SHOW_DIR / "package"
    dj = pkg / "dj-audio"
    for name in ["set1-intro.mp3", "set2-intro.mp3", "99-outro.mp3"]:
        assert (dj / name).read_bytes() == SILENT_MP3
    assert not (dj / "setencore-intro.mp3").exists()  # encore has no lead-in
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_audio"] == {
        "set_intros": {"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"},
        "outro": "dj-audio/99-outro.mp3",
    }
    assert manifest["set_breaks"] == [{"after_track": 3}, {"after_track": 5}]
    assert manifest["dj_notes"] is not None
    # broadcast.m3u interleaves DJ audio; playlist.m3u stays music-only.
    assert "dj-audio/" not in (pkg / "playlist.m3u").read_text()
    broadcast = (pkg / "broadcast.m3u").read_text().splitlines()
    assert broadcast[0] == "#EXTM3U"
    assert broadcast[1] == "dj-audio/set1-intro.mp3"   # set-1 lead-in opens the show
    assert broadcast[-1] == "dj-audio/99-outro.mp3"    # outro closes it
    dj_lines = [ln for ln in broadcast if ln.startswith("dj-audio/")]
    assert dj_lines == ["dj-audio/set1-intro.mp3", "dj-audio/set2-intro.mp3",
                        "dj-audio/99-outro.mp3"]       # no encore lead-in
    i2 = broadcast.index("dj-audio/set2-intro.mp3")
    assert broadcast[i2 + 1].startswith("audio/")               # a track follows the lead-in
    assert any(ln.startswith("audio/") for ln in broadcast[2:i2])  # set-1 music precedes it
    # run intent + provenance are stamped for replays
    criteria = json.loads((tmp_path / "runs" / "voicerun" / "criteria.json").read_text())
    assert criteria["voice"] == "v-abc"
    prov = json.loads((tmp_path / "shows" / SHOW_DIR / "provenance.json").read_text())
    assert prov["voice"] == "v-abc"


def test_globally_disabled_run_is_unvoiced(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch, cfg_template=UNVOICED_CFG)
    result = find(cfg)
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "shows" / SHOW_DIR / "package"
    assert not (pkg / "dj-audio").exists()
    assert not (pkg / "broadcast.m3u").exists()  # only written for voiced shows
    assert (pkg / "playlist.m3u").exists()
    assert json.loads((pkg / "manifest.json").read_text())["dj_audio"] is None


def test_explicit_voice_flag_opts_in_when_globally_disabled(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch, cfg_template=UNVOICED_CFG)
    result = find(cfg, "--voice")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "shows" / SHOW_DIR / "package" / "dj-audio" / "set1-intro.mp3").exists()


def test_no_voice_flag_opts_out_when_globally_enabled(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch)
    result = find(cfg, "--no-voice")
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "shows" / SHOW_DIR / "package"
    assert not (pkg / "dj-audio").exists()
    assert json.loads((pkg / "manifest.json").read_text())["dj_audio"] is None


def test_voice_implies_script_despite_no_script(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch)
    result = find(cfg, "--no-script")
    assert result.exit_code == 0, result.output
    pkg = tmp_path / "shows" / SHOW_DIR / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_notes"] is not None       # script was forced on
    assert manifest["dj_audio"] is not None
    assert (pkg / "dj-notes.md").exists()


def test_speech_failure_fails_show_but_not_batch(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "speech_provider_for",
                        lambda config, voice, clone_ref=None: FakeSpeechProvider(fail=True))
    result = find(cfg)
    assert result.exit_code == 0, result.output   # batch loop continues; run exits clean
    assert "FAILED GratefulDead/1973-06-10" in result.output
    show_dir = tmp_path / "shows" / SHOW_DIR
    assert not (show_dir / "package" / "manifest.json").exists()  # no half-voiced package
    assert not (tmp_path / "ledger.jsonl").exists()


def test_redo_from_package_reuses_cached_segments(tmp_path: Path, monkeypatch):
    cfg = voiced_setup(tmp_path, monkeypatch)
    assert find(cfg).exit_code == 0
    second = FakeSpeechProvider()  # same fixed fake voice/model -> same cache keys
    monkeypatch.setattr(cli, "speech_provider_for", lambda config, voice, clone_ref=None: second)
    redo = runner.invoke(cli.app, ["--config", cfg, "redo", "gratefuldead", "--from", "package"])
    assert redo.exit_code == 0, redo.output
    assert "packaged" in redo.output              # re-voiced with the original voice
    assert second.calls == []                     # unchanged segments skipped, no re-spend


PRESENTER_CFG = ('{root}\n[jerrybase]\nenabled = false\n'
                 '[tts]\nbackend = "fake"\n')   # enabled = false; no house voice


def presenter_setup(tmp_path, monkeypatch):
    from llama.models import Criteria as CriteriaModel
    from llama.presenters import Presenter, save_presenter
    from llama.profiles import Profile, save_profile

    (tmp_path / "config.toml").write_text(
        PRESENTER_CFG.format(root=f'root = "{tmp_path}"'))
    save_presenter(tmp_path, Presenter(
        id="casey", name="Casey", sex="male", voice="v-casey",
        character="Warm late-night FM veteran with dry humor."))
    save_profile(tmp_path, Profile(
        name="sunday", criteria=CriteriaModel.model_validate_json(CRITERIA),
        script=False, presenter="casey", title="Sunday Morning Dead"))
    made = {"synthesize": []}

    def providers(config):
        p = fake_providers(config)
        made["synthesize"].append(p["synthesize"])
        return p

    monkeypatch.setattr(cli, "make_providers", providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    return str(tmp_path / "config.toml"), made


def test_presenter_profile_run_end_to_end(tmp_path: Path, monkeypatch):
    cfg, made = presenter_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "sunday", "--auto"])
    assert result.exit_code == 0, result.output
    # presenter implies voice even though [tts] enabled is false
    pkg = tmp_path / "shows" / SHOW_DIR / "package"
    assert (pkg / "dj-audio" / "set1-intro.mp3").read_bytes() == SILENT_MP3
    # run intent + provenance stamp the presenter id and title, voice resolved
    run_dir = next((tmp_path / "runs").glob("*-sunday"))
    criteria = json.loads((run_dir / "criteria.json").read_text())
    assert criteria["voice"] == "v-casey"
    assert criteria["presenter"] == "casey"
    assert criteria["title"] == "Sunday Morning Dead"
    assert criteria["script"] is True   # voice implies script (profile had script=False)
    prov = json.loads((tmp_path / "shows" / SHOW_DIR / "provenance.json").read_text())
    assert prov["presenter"] == "casey" and prov["title"] == "Sunday Morning Dead"
    # the synthesize prompt carried the persona, not the neutral narrator
    prompt = made["synthesize"][0].calls[0][1]
    assert "You are Casey" in prompt
    assert 'Your show is called "Sunday Morning Dead"' in prompt
    assert "Every fact must come from the\ninputs below" not in prompt


def test_redo_from_synthesize_picks_up_edited_character(tmp_path: Path, monkeypatch):
    from llama.presenters import Presenter, save_presenter

    cfg, made = presenter_setup(tmp_path, monkeypatch)
    assert runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "sunday", "--auto"]).exit_code == 0
    # hand-tune the character; redo must re-script from the live file
    save_presenter(tmp_path, Presenter(
        id="casey", name="Casey", sex="male", voice="v-casey",
        character="Now grumpy and terse."))
    redo = runner.invoke(cli.app, ["--config", cfg, "redo", "gratefuldead", "--from", "synthesize"])
    assert redo.exit_code == 0, redo.output
    prompt = made["synthesize"][1].calls[0][1]   # providers rebuilt once per invoke
    assert "Now grumpy and terse." in prompt
    assert "Warm late-night FM veteran" not in prompt
