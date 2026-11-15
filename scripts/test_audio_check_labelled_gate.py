"""scripts/audio_check_labelled_gate.py (audio-check plan Task 11; spec "Pass bar").
Assembly reads the committed evidence; evaluation uses synthetic results (no binary)."""
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audio_check_labelled_gate as gate


def test_assembles_the_145_labelled_tracks_by_group():
    tracks = gate.assemble()
    assert len(tracks) == gate.EXPECTED_TRACKS == 145
    assert len({t.key for t in tracks}) == 145
    assert Counter(t.group for t in tracks) == {
        gate.GROUP_DROPS: 118, gate.GROUP_SONGS: 12, gate.GROUP_SPACE: 12, gate.GROUP_GOMEZ: 3}
    assert all(t.pop is not None for t in tracks if t.group == gate.GROUP_DROPS)
    assert all(t.title == "Silence" and t.slug.startswith("gomez-")
               for t in tracks if t.group == gate.GROUP_GOMEZ)


@pytest.mark.parametrize("rc, out, err, verdict", [
    (0, "verdict=music run=130 frac=0.84\n", "", "music"),
    (0, "verdict=junk run=0 frac=0.00\n", "a warning\n", "junk"),
    (2, "", "unchecked: cannot load\n", "unchecked"),
    (0, "", "warning\n", "unchecked"),
])
def test_parse_reads_stdout_and_exit_code(rc, out, err, verdict):
    assert gate.parse(rc, out, err)["verdict"] == verdict


def _pop(chosen, label, run, frac):
    return {"music_chosen": "True" if chosen else "False", "operator_label": label,
            "run_055": str(run), "frac_055": f"{frac:.2f}", "slug": "s"}


def _res(verdict, run=0, frac=0.0):
    return {"verdict": verdict, "run": run, "frac": frac,
            "error": None if verdict != "unchecked" else "x"}


def _t(group, pop=None, result=None, title="Tuning", slug="s"):
    t = gate.Track(group, slug, "01 - x.mp3", title, pop)
    t.result = result
    return t


def test_caught_song_flipping_to_junk_blocks():
    r = gate.evaluate([_t(gate.GROUP_DROPS, _pop(True, "song", 300, 0.95), _res("junk", 50, 0.3))])
    assert len(r["blockers"]) == 1


def test_caught_song_unchecked_blocks():
    r = gate.evaluate([_t(gate.GROUP_DROPS, _pop(True, "song", 300, 0.95), _res("unchecked"))])
    assert len(r["blockers"]) == 1


def test_at_bar_caught_song_flip_is_listed_not_blocking():
    r = gate.evaluate([_t(gate.GROUP_DROPS, _pop(True, "song", 120, 0.95), _res("junk", 110, 0.9))])
    assert r["blockers"] == [] and r["groups"][gate.GROUP_DROPS]["listed"]


def test_silence_and_unlabelled_flips_are_listed_only():
    r = gate.evaluate([
        _t(gate.GROUP_DROPS, _pop(True, "song", 300, 0.95), _res("junk"), title="Silence"),
        _t(gate.GROUP_DROPS, _pop(True, "junk", 300, 0.95), _res("junk")),
        _t(gate.GROUP_DROPS, _pop(False, "", 0, 0.0), _res("music", 200, 0.9)),
    ])
    assert r["blockers"] == [] and len(r["groups"][gate.GROUP_DROPS]["flips"]) == 3


def test_control_song_must_read_music_with_at_bar_exemption():
    r = gate.evaluate([
        _t(gate.GROUP_SONGS, None, _res("junk", 60, 0.4)),
        _t(gate.GROUP_SONGS, None, _res("junk", 110, 0.9)),
        _t(gate.GROUP_SONGS, None, _res("music", 300, 1.0)),
    ])
    assert len(r["blockers"]) == 1
    assert len(r["groups"][gate.GROUP_SONGS]["listed"]) == 1


def test_space_and_gomez_never_block():
    r = gate.evaluate([_t(gate.GROUP_SPACE, None, _res("junk")),
                       _t(gate.GROUP_GOMEZ, _pop(True, "song", 300, 1.0), _res("unchecked"))])
    assert r["blockers"] == []
    assert r["groups"][gate.GROUP_SPACE]["listed"] and r["groups"][gate.GROUP_GOMEZ]["listed"]
