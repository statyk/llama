import csv
from importlib import resources


def test_vendored_csv_is_present_and_well_formed():
    path = resources.files("llama.data").joinpath("set_breaks.csv")
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 18074
    assert list(rows[0].keys()) == [
        "date", "artist", "event_id", "venue", "city", "state", "show_set",
        "time", "song", "song_n", "isong", "next_set", "Nevents", "ievent",
        "break_length",
    ]
    # A known row survives quoted-comma parsing intact.
    cornell = [r for r in rows if r["date"] == "1977-05-08" and r["artist"] == "GratefulDead"]
    assert any(r["venue"] == "Barton Hall, Cornell University" for r in cornell)
