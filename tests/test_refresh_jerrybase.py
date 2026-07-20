import importlib.util
from pathlib import Path

import pytest

# scripts/ is not an importable package; load the module directly by path.
_PATH = Path(__file__).resolve().parent.parent / "scripts" / "refresh_jerrybase.py"
_spec = importlib.util.spec_from_file_location("refresh_jerrybase", _PATH)
refresh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refresh)


def test_require_artist_column_accepts_valid_csv():
    # No raise when the header has an artist column.
    refresh._require_artist_column("artist,date,show_set\nGratefulDead,1977-05-08,Set 1\n")


def test_require_artist_column_exits_without_artist():
    with pytest.raises(SystemExit) as excinfo:
        refresh._require_artist_column("date,venue\n1977-05-08,Barton Hall\n")
    assert excinfo.value.code == 1


def test_require_artist_column_exits_on_empty_input():
    with pytest.raises(SystemExit) as excinfo:
        refresh._require_artist_column("")
    assert excinfo.value.code == 1
