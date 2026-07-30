"""Task 8: offline end-to-end handshake between llama and emcee.

The show-package contract (manifest v3: `schema_version`, the `briefing`
block, `show`, `source.profile`, `tracks`, `set_breaks`, plus the
`dj_notes`/`dj_audio` blocks emcee owns) is the ONLY interface between the
two tools -- emcee never imports llama (`test_no_llama_imports.py` guards
that at both `src/` and `tests/`), so this test proves the handshake using
only a package directory: `tests/helpers.py::build_package` fabricates one
that mirrors llama's real `deliver`d output, and `emcee run` (the real CLI,
with only the TTS/LLM backends faked) is pointed at it. Asserting the
package comes out broadcast-ready afterward is the whole point -- if
`build_package`'s fixture ever drifts from what llama's `manifest.py` /
`models.py` / `stages/package.py` actually write, this test would pass
while the real handshake is broken, which is worse than no test at all.

Fixture-fidelity check performed for this task (not re-run here, since that
would require importing llama): built one package through llama's real
`run_package` (`packages/llama/src/llama/stages/package.py`) against a
`StubIA`, and one through `build_package`, then diffed the two
`manifest.json` outputs field-by-field. Every field `emcee` src code
actually reads (`schema_version`; `briefing.file/json/narration/vetted`;
`show.artist/date/venue/city/context`; `source.profile`;
`tracks[].index/set/title/filename`; `set_breaks[].after_track`;
`dj_notes`/`dj_audio` shapes) matched exactly. llama's manifest additionally
carries `source.identifier/url/lineage` and top-level `research`/
`reviews`/`research_vetted` keys that `build_package` omits -- confirmed by
grepping `packages/emcee/src` that no emcee code reads any of those keys,
so the omission is a deliberate, harmless subset, not a contract gap.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

import emcee.process as process_mod
from emcee.cli import app
from emcee.station import scan

from herder import FakeProvider

from tests.helpers import build_package

runner = CliRunner()


def _write_config(root: Path, station_root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.toml").write_text(
        f'[station]\nroot = "{station_root}"\n\n'
        '[tts]\nbackend = "fake"\nvoice = "test-voice"\n'
    )


def _good_notes_json() -> str:
    # Matches build_package's default fixture (sets=("1", "2"), encore=True):
    # tracks are Morning Dew/Sugaree (set 1), Jack Straw/China Cat Sunflower
    # (set 2), I Know You Rider (encore) -- all valid mentioned_songs.
    return json.dumps({
        "context": "Spring '73 tour",
        "set_intros": {
            "1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
            "2": "China Cat Sunflower leads set two.",
        },
        "outro": "I Know You Rider sends us off. Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"],
    })


def test_emcee_run_voices_a_delivered_package_to_broadcast_ready(tmp_path, monkeypatch):
    """Offline, fake-backend handshake: a package shaped exactly like
    llama's real `deliver`d output (fabricated by `build_package`, never by
    importing llama) comes out broadcast-ready after `emcee run` -- dj_notes
    + dj_audio manifest blocks, `broadcast.m3u`, and dj-audio/*.mp3 files on
    disk, using the real `process_package` pipeline end to end (only the LLM
    provider and the TTS backend are faked; scriptwrite guard, audio
    synthesis, and broadcast-playlist assembly all run for real)."""
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station)
    monkeypatch.setattr(
        process_mod, "provider_for",
        lambda settings, task: FakeProvider(completes=[_good_notes_json()]),
    )

    # Fabricated as an *unvoiced* delivered package -- exactly what llama's
    # `deliver` hands off, per the split-architecture contract (llama never
    # writes dj_notes/dj_audio/dj-audio/broadcast.m3u post-cut).
    pkg_dir = build_package(station, slug="gd1973-06-10", voiced=False, profile="prime-dead")
    assert not (pkg_dir / "broadcast.m3u").exists()
    manifest_before = json.loads((pkg_dir / "manifest.json").read_text())
    assert manifest_before["dj_notes"] is None
    assert manifest_before["dj_audio"] is None

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    assert f"voiced: {pkg_dir.name}" in result.output

    manifest = json.loads((pkg_dir / "manifest.json").read_text())
    assert manifest["dj_notes"] is not None
    assert manifest["dj_audio"] is not None
    assert set(manifest["dj_audio"]["set_intros"]) == {"1", "2"}

    assert (pkg_dir / "broadcast.m3u").exists()
    broadcast = (pkg_dir / "broadcast.m3u").read_text()
    assert broadcast.startswith("#EXTM3U")

    dj_audio_dir = pkg_dir / "dj-audio"
    for rel_path in [*manifest["dj_audio"]["set_intros"].values(), manifest["dj_audio"]["outro"]]:
        assert (pkg_dir / rel_path).exists(), f"missing DJ audio clip: {rel_path}"
    assert (dj_audio_dir / "set1-intro.mp3").exists()
    assert (dj_audio_dir / "set2-intro.mp3").exists()
    assert (dj_audio_dir / "99-outro.mp3").exists()

    # The canonical definition of "broadcast-ready" on the emcee side is
    # `station.readiness` (exercised here through `scan`, the same path
    # `emcee status`/`emcee run` themselves use) -- not just the presence of
    # individual files this test happens to check above.
    statuses = scan(station)
    assert len(statuses) == 1
    assert statuses[0].state == "ready", statuses[0].reasons
    assert statuses[0].reasons == []
