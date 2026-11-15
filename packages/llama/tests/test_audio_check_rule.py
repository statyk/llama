import csv
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from llama.audio_check import model, rule

ROOT = Path(__file__).resolve().parents[3]
POP2 = ROOT / "docs/superpowers/2026-11-14-audio-check-evidence/population2.tsv"
_DRUMS = ("Drum kit", "Drum", "Percussion", "Snare drum", "Bass drum", "Drum roll")


def scores(F, music=0.0, speech=0.0, drum=0.0):
    a = np.zeros((F, 521))
    a[:, model.CLASS_NAMES.index("Music")] = music
    a[:, model.CLASS_NAMES.index("Speech")] = speech
    for d in _DRUMS:
        a[:, model.CLASS_NAMES.index(d)] = drum
    return a


def test_class_map_has_rule_labels():
    assert len(model.CLASS_NAMES) == 521
    for name in ("Music", "Speech", *_DRUMS):
        assert name in model.CLASS_NAMES


def test_bins_cover_all_frames_no_partial_drop():
    w = rule.windows(np.ones((25, 521)), duration_sec=12.4)
    assert w.shape == (1, 521)


def test_bin_count_from_duration():
    assert rule.windows(np.ones((260, 521)), 125.0).shape[0] == 12


def test_music_run_and_frac():
    m = rule.measure(scores(260, music=0.9, speech=0.0), 125.0)
    assert m == rule.Measure(run_sec=120, frac=1.0) and rule.verdict(m) == "music"


def test_measure_fields_are_python_scalars():
    m = rule.measure(scores(260, music=0.9), 125.0)
    assert type(m.run_sec) is int and type(m.frac) is float
    json.dumps(asdict(m))


def test_speech_blocks_music():
    assert rule.verdict(rule.measure(scores(260, music=0.9, speech=0.5), 125.0)) == "junk"


def test_drum_clause_counts_as_musical():
    assert rule.verdict(rule.measure(scores(260, music=0.1, drum=0.6), 125.0)) == "music"


def test_thresholds_are_strict_and_inclusive_as_spec():
    # one frame per window keeps the value exact (no float averaging noise)
    assert rule.verdict(rule.measure(scores(12, music=0.55), 125.0)) == "junk"
    assert rule.verdict(rule.measure(scores(12, music=0.56), 125.0)) == "music"
    assert rule.verdict(rule.Measure(120, 0.60)) == "music"
    assert rule.verdict(rule.Measure(110, 1.0)) == "junk"
    assert rule.verdict(rule.Measure(120, 0.59)) == "junk"


def test_frac_bar():
    frames = np.vstack([scores(120, music=0.9), scores(90, music=0.0, speech=0.9)])
    m = rule.measure(frames, 210.0)
    assert m == rule.Measure(run_sec=120, frac=12 / 21) and rule.verdict(m) == "junk"


def test_short_track_single_window_is_junk():
    assert rule.verdict(rule.measure(scores(8, music=1.0), 4.0)) == "junk"


def test_zero_frames_is_junk_not_nan():
    for frames, sec in ((np.zeros((0, 521)), 0.0), (np.zeros((0, 521)), 4.0)):
        m = rule.measure(frames, sec)
        assert m == rule.Measure(run_sec=0, frac=0.0) and rule.verdict(m) == "junk"


def test_version_literal():
    assert rule.VERSION == "yamnet-onnx-1/rule-0.55-120-0.60"


def test_rule_and_model_import_load_no_numpy():
    code = (
        "import sys; import llama.audio_check; import llama.audio_check.model; "
        "import llama.audio_check.rule as r; r.VERSION; "
        "assert 'numpy' not in sys.modules, 'numpy loaded'"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_rule_reproduces_spike_on_population2():
    with POP2.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    assert rows
    bad = []
    for r in rows:
        got = rule.verdict(rule.Measure(int(float(r["run_055"])), float(r["frac_055"]))) == "music"
        if got != (r["music_chosen"] == "True"):
            bad.append((r["slug"], r["source_file"], r["run_055"], r["frac_055"], r["music_chosen"]))
    assert not bad, bad


def test_bin_membership_includes_tail_frames():
    # F=25, 20 s -> 2 bins of 12 and 13 frames; only frame 24 (bin 1's last) is non-zero.
    a = np.zeros((25, 521))
    a[24, 0] = 1.3
    w = rule.windows(a, 20.0)
    assert w[0, 0] == 0.0
    assert abs(w[1, 0] - 0.1) < 1e-9


def test_run_is_longest_consecutive_not_total():
    frames = np.vstack(
        [scores(80, music=0.9), scores(10, speech=0.9), scores(50, music=0.9)]
    )
    m = rule.measure(frames, 140.0)  # 14 windows: 8 musical, 1 talk, 5 musical
    assert m == rule.Measure(run_sec=80, frac=13 / 14)


@pytest.mark.parametrize("label", [d for d in _DRUMS if d != "Drum kit"])
def test_each_drum_label_alone_counts_as_musical(label):
    a = scores(260, music=0.0)
    a[:, model.CLASS_NAMES.index(label)] = 0.6
    assert rule.verdict(rule.measure(a, 125.0)) == "music"
