"""emcee reads and preserves the manifest's optional `dropped_tracks`
(llama's junk-tag drop): scriptwrite sees a short note, and every manifest
rewrite path leaves the field alone. Absent, null and [] all mean none."""

import json
from pathlib import Path

import pytest
from herder import FakeProvider

from emcee import retitle
from emcee.config import EmceeConfig
from emcee.models import DJAudioBlock, ScriptNotes
from emcee.package_io import Package, rewrite_manifest
from emcee.prompts import load_prompt
from emcee.scriptwrite import dropped_note, write_script
from emcee.station import readiness, scan

from tests.helpers import build_package, no_moves, set_dj_audio
from tests.test_scriptwrite import notes_dict

DROPPED = [
    {"title": "Tuning", "duration_sec": 280, "set": "1", "after_track": 0,
     "source_file": "t00.mp3", "reason": "junk tag"},
    {"title": "Crowd", "duration_sec": 125, "set": "2", "after_track": 11,
     "source_file": "t12.mp3", "reason": "junk tag"},
]

NOTE = (
    'Cut from this broadcast as non-music: "Tuning" (4:40, before track 1); '
    '"Crowd" (2:05, after track 11). These are normally not worth mentioning; '
    "mention one only when it matters, for example a long cut that explains a "
    "jump in the show.\n"
    "Dropped titles are not songs: never put one in mentioned_songs.\n"
)

NONE_FORMS = ["absent", None, []]


def _set_dropped(pkg_dir: Path, value) -> None:
    path = pkg_dir / "manifest.json"
    data = json.loads(path.read_text())
    data.pop("dropped_tracks", None)
    if value != "absent":
        data["dropped_tracks"] = value
    path.write_text(json.dumps(data, indent=2) + "\n")


def _prompt(tmp_path: Path, value) -> str:
    pkg_dir = build_package(tmp_path)
    _set_dropped(pkg_dir, value)
    fake = FakeProvider(completes=[json.dumps(notes_dict())])
    write_script(Package(pkg_dir), fake, presenter=None, title=None)
    return fake.calls[0][1]


def test_dropped_note_text():
    assert dropped_note({"dropped_tracks": DROPPED}) == NOTE


def test_dropped_note_variants():
    m = {"dropped_tracks": [
        {"title": "A", "duration_sec": 65.4, "after_track": 3},
        {"title": "B", "after_track": 0},
        {"title": "C", "duration_sec": 10},
    ]}
    assert dropped_note(m).startswith(
        'Cut from this broadcast as non-music: "A" (1:05, after track 3); '
        '"B" (before track 1); "C" (0:10). ')


@pytest.mark.parametrize("form", NONE_FORMS)
def test_dropped_note_none_forms(form):
    m = {} if form == "absent" else {"dropped_tracks": form}
    assert dropped_note(m) == ""


def test_dropped_note_damaged_values():
    assert dropped_note({"dropped_tracks": "Tuning"}) == ""
    assert dropped_note({"dropped_tracks": {"title": "Tuning"}}) == ""
    assert dropped_note({"dropped_tracks": [{"duration_sec": 5}, "x", None,
                                            {"title": ""}, {"title": 3}]}) == ""
    # Entry without a title is skipped; the rest still render.
    got = dropped_note({"dropped_tracks": [{"duration_sec": 5}, {"title": "Ok"}]})
    assert '"Ok"' in got and "0:05" not in got
    # after_track that is not a real position is omitted.
    for bad in (True, False, -1, "3", 2.5, None):
        got = dropped_note({"dropped_tracks": [{"title": "X", "after_track": bad}]})
        assert got.startswith('Cut from this broadcast as non-music: "X"; ') \
            or got.startswith('Cut from this broadcast as non-music: "X". '), (bad, got)
        assert "track" not in got.split("These")[0]
    # Non-numeric / bool duration omitted.
    got = dropped_note({"dropped_tracks": [{"title": "X", "duration_sec": True},
                                           {"title": "Y", "duration_sec": "4"}]})
    assert '"X"; "Y".' in got


def test_prompt_byte_identical_without_drops(tmp_path):
    # Today's render is the template with the new slot removed.
    old_template = load_prompt("scriptwrite").replace("{{dropped_note}}", "")
    assert "{{dropped_note}}{{encore_note}}" in load_prompt("scriptwrite")
    renders = [_prompt(tmp_path / str(i), form) for i, form in enumerate(NONE_FORMS)]
    assert len(set(renders)) == 1
    assert "Cut from this broadcast" not in renders[0]
    pkg = Package(build_package(tmp_path / "x"))
    fake = FakeProvider(completes=[json.dumps(notes_dict())])
    import emcee.scriptwrite as sw
    orig = sw.load_prompt
    sw.load_prompt = lambda name: old_template
    try:
        write_script(pkg, fake, presenter=None, title=None)
    finally:
        sw.load_prompt = orig
    assert fake.calls[0][1] == renders[0]


def test_prompt_carries_note_with_drops(tmp_path):
    prompt = _prompt(tmp_path, DROPPED)
    assert NOTE in prompt
    assert NOTE + "This show ends with an encore" in prompt


def test_rewrite_manifest_preserves_dropped_tracks(tmp_path):
    pkg_dir = build_package(tmp_path)
    _set_dropped(pkg_dir, DROPPED)
    pkg = Package(pkg_dir)
    notes = ScriptNotes(**notes_dict())
    rewrite_manifest(pkg, dj_notes=notes, dj_audio=None)
    assert json.loads((pkg_dir / "manifest.json").read_text())["dropped_tracks"] == DROPPED
    rewrite_manifest(pkg, dj_notes=None, dj_audio=None)
    assert json.loads((pkg_dir / "manifest.json").read_text())["dropped_tracks"] == DROPPED


def test_retitle_plan_accepts_dropped_tracks(tmp_path):
    cfg = EmceeConfig.model_validate({"assign": {"profiles": {
        "dead": {"presenter": "p", "title": "Gravel"}}}})
    pkg = build_package(tmp_path, "show", voiced=True, profile="dead")
    set_dj_audio(pkg, profile="dead", profile_source="llama")
    for form in (DROPPED, [], None):
        _set_dropped(pkg, form)
        # Normalize into emcee's encoding, as a voiced manifest is on disk.
        data = json.loads((pkg / "manifest.json").read_text())
        (pkg / "manifest.json").write_bytes(retitle.encode(data))
        plan = retitle.plan_retitle(tmp_path, cfg)
        assert plan.refused == [], form
        raw = (pkg / "manifest.json").read_bytes()
        out = retitle.write_title(pkg, expect=raw, title="Gravel")
        assert json.loads(out).get("dropped_tracks") == form


@pytest.mark.parametrize("form", ["absent", None, [], DROPPED])
def test_status_and_readiness_with_each_form(tmp_path, form):
    pkg_dir = build_package(tmp_path, "show", voiced=True)
    _set_dropped(pkg_dir, form)
    pkg = Package(pkg_dir)
    ok, reasons = readiness(pkg, EmceeConfig(), no_moves())
    assert (ok, reasons) == (True, [])
    [status] = scan(tmp_path, EmceeConfig(), no_moves())
    assert status.state == "ready"
