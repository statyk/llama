from test_replay import _legs
from fixture_library import library_show
def test_p(tmp_path):
    ws,_=library_show(tmp_path, held=True, alignment="llm")
    l=_legs(tmp_path, ws)
    print("OWNED", l.gather.taper_owned, l.gather.taper.reason, l.needs_llm, l.gather.show.structure.alignment)
