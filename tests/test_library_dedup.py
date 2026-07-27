from pathlib import Path

from llama.catalog import library_performance_ids
from llama.ledger import Ledger
from llama.models import Candidate, Criteria, Provenance, Show
from llama.stages.winnow import run_winnow
from llama.workspace import RunWorkspace, ShowWorkspace, write_artifact


def _prov(pid: str) -> Provenance:
    return Provenance(performance_id=pid, run="r1", processed_at="2026-07-27T00:00:00+00:00",
                      candidate=Candidate(performance_id=pid, collection=pid.split("/")[0],
                                          date=pid.split("/")[1], recordings=[]))


def test_library_ids_from_provenance_and_show(tmp_path: Path):
    a = ShowWorkspace(tmp_path / "shows" / "a")
    write_artifact(a.provenance, _prov("GratefulDead/1973-06-10"))
    b = ShowWorkspace(tmp_path / "shows" / "b")
    write_artifact(b.show, Show(performance_id="GratefulDead/1977-05-08", identifier="x",
                                artist="Grateful Dead", date="1977-05-08"))
    (tmp_path / "shows" / "empty").mkdir()          # unresolvable: skipped
    (tmp_path / "shows" / "stray.txt").write_text("")  # non-dir: skipped
    assert library_performance_ids(tmp_path) == {
        "GratefulDead/1973-06-10", "GratefulDead/1977-05-08"}


def test_no_shows_dir_is_empty_set(tmp_path: Path):
    assert library_performance_ids(tmp_path) == set()
