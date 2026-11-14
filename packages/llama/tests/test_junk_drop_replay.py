"""Replay rows carry the junk-title drops; the cascade record is remapped to kept positions."""
import json

from fixture_library import IDENT
from fixture_library import library_show as _library_show
from fixture_library import replay_config as _config
from llama.replay import CacheOnlyIA, ShowReplay, _cascade_dict, replay_show
from llama.stages.gather import CascadeRecord


def _record(**kw) -> CascadeRecord:
    base = dict(wholly_untagged=False, fetch_siblings=False, s_positions=(),
                lossless=None, s_plan=None,
                d=None, short4=(), short4_declined={}, gap_filled=(), deferred_applied=())
    base.update(kw)
    return CascadeRecord(**base)


class _Plan:
    mode = "tags"
    fills = (0, 1, 3)
    declined = (2,)


def test_cascade_dict_remaps_positions():
    rec = _record(s_plan=_Plan(), short4=(3,), short4_declined={1: "x", 3: "y"},
                  gap_filled=(0, 1), deferred_applied=(2, 3))
    out = _cascade_dict(rec, keep=(0, 2, 3))
    assert out["s_fills"] == [1, 3]            # 0 -> 1, 3 -> 3, 1 omitted
    assert out["s_declined"] == [2]
    assert out["short4"] == [3]
    assert out["short4_declined"] == {"3": "y"}
    assert out["gap_filled"] == [1]
    assert out["deferred_applied"] == [2, 3]


def test_cascade_dict_identity_without_keep():
    rec = _record(s_plan=_Plan(), short4=(3,), short4_declined={1: "x"})
    out = _cascade_dict(rec)
    assert out["s_fills"] == [1, 2, 4] and out["short4_declined"] == {"2": "x"}
    assert out == _cascade_dict(rec, keep=None) == _cascade_dict(rec, keep=(0, 1, 2, 3))


def test_replay_row_lists_junk_drops(tmp_path):
    ws, _ = _library_show(tmp_path, held=False)
    cache = tmp_path / "cache" / f"md_{IDENT}.json"
    md = json.loads(cache.read_text())
    for f in md["files"]:
        if f["name"] == "gd73-06-10d1t02.mp3":
            f["title"], f["length"] = "Tuning", "3:00"
    cache.write_text(json.dumps(md))
    r = replay_show(ws, config=_config(tmp_path), ia=CacheOnlyIA(tmp_path / "cache"), slfm=None,
                    scratch=tmp_path / "scratch" / ws.dir.name, delivered=set())
    assert r.unreplayable is None
    assert len(r.junk_drops) == 1
    d = r.junk_drops[0]
    assert d == {"filename": "gd73-06-10d1t02.mp3", "title": "Tuning", "set": "1",
                 "after_track": 1, "duration_sec": 180.0, "rule": "A", "held": False}
    assert "gd73-06-10d1t02.mp3" not in r.filenames
    assert len(r.title_paths) == len(r.filenames)
    assert all(p <= len(r.filenames) for k in ("s_fills", "s_declined", "deferred_applied")
               for p in r.cascade[k])
    assert ShowReplay(slug="x", state="missing").junk_drops == []
