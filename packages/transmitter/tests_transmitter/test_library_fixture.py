import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

from tests_transmitter.helpers import LIBRARY_DURATIONS, library_pieces

MIN_FRAMES = 60 * 44_100 / 1024


def test_fixture_reproduces_the_measured_profile_shape():
    pieces = library_pieces()
    assert len(pieces) == 300 and len({p.slug for p in pieces}) == 300
    counts = Counter(p.profile for p in pieces)
    assert counts["dead"] == 44 and counts["country"] == 2
    dead = [p.frames / MIN_FRAMES for p in pieces if p.profile == "dead"]
    assert abs(statistics.median(dead) - 168) < 1
    assert {p.artist for p in pieces if p.profile == "dead"} == {"Grateful Dead"}
    assert all(len({p.artist for p in pieces if p.profile == prof}) >= 2
               for prof in counts if prof != "dead")


def test_generator_is_byte_identical(tmp_path):
    script = LIBRARY_DURATIONS.with_name("make_library_durations.py")
    copy = tmp_path / script.name
    copy.write_text(script.read_text())
    subprocess.run([sys.executable, str(copy)], check=True, cwd=tmp_path)
    assert (tmp_path / "library_durations.json").read_bytes() == LIBRARY_DURATIONS.read_bytes()
