"""`extend` plans concert breaks in two passes (spec "Assembly", "Promises",
"Fallback ladder"): pass 1 proposes the content on estimated lengths, the clip
is assembled and measured with the named shows, pass 2 re-runs with the exact
lengths; any failure falls to the last rung (today's logic) and never raises."""

import dataclasses
import hashlib
import io
import json
import shutil
import wave

import pytest

from tests_transmitter.helpers import NOW, FakeEngine, make_station, mark_awaiting_fix, requires_ffmpeg, write_clock
from tests_transmitter.test_pipeline import library, short_clock
from transmitter import alerts, assemble, concert, pipeline, scheduler
from transmitter.concert import piece_id
from transmitter.errors import PieceUndecodable, RenderError
from transmitter.layout import CONCERT_ROLE
from transmitter.planner import read_plan, write_plan
from transmitter.scheduler import PLACEHOLDER_SLUG
from transmitter.station import Entry, Show, file_set_key_and_sizes

SHOW_FILE_SAMPLES = 84 * 44_100        # 5 files: exactly the estimate (3 x 60 s tracks + 2 x 120 s clips)
CLIP_SAMPLES = 18 * 44_100             # every clip (IDs, assembled breaks) the typical assembled length
ID_TEXT = "You are listening to LMA Radio."
ANNOUNCE = f'enabled = true\nbed = "/nonexistent/bed.wav"\nid_text = "{ID_TEXT}"\n'


class Runaway(BaseException):
    """Past `FakeAssembler.cap` calls: escapes every `except Exception`, so a
    re-proposal loop fails the test at once instead of hanging it."""


class FakeAssembler:
    """`Station.assemble`: writes a small real WAV per content into the
    workspace clip folder and returns its one-clip Show (key = the file's own
    file-set key, as `assemble.Assembler` does); records every call."""

    def __init__(self, ws, *, undecodable_prefix: str | None = None, fail: Exception | None = None,
                 cap: int = 200):
        self.ws = ws
        self.cap = cap
        self.undecodable_prefix = undecodable_prefix
        self.fail = fail
        self.calls: list[concert.BreakContent] = []
        self.by_slug: dict[str, concert.BreakContent] = {}

    def __call__(self, content, settings):
        self.calls.append(content)
        if len(self.calls) > self.cap:
            raise Runaway(f"{len(self.calls)} assemblies in one test")
        if self.fail is not None:
            raise self.fail
        for pid, text in content.pieces:
            if self.undecodable_prefix is not None and text.startswith(self.undecodable_prefix):
                raise PieceUndecodable(pid)
        h = hashlib.sha256(json.dumps(content.pieces).encode()).hexdigest()[:16]
        slug = f"{assemble.CLIP_PREFIX}{h}"
        name = f"{slug}.wav"
        out = self.ws.concert_dir
        out.mkdir(parents=True, exist_ok=True)
        if not (out / name).exists():           # reused untouched (its key hashes its mtime)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(44_100)
                w.writeframes(b"\0\0\0\0" * 441)
            (out / name).write_bytes(buf.getvalue())
        key, sizes = file_set_key_and_sizes(out, [name])
        self.by_slug[slug] = content
        return Show(slug, out, (Entry(name, "clip", "Announcement"),), key,
                    {"role": CONCERT_ROLE, "ann_id": None, "sizes": sizes})


def engine(**kw):
    return FakeEngine(samples_per_file=SHOW_FILE_SAMPLES, clip_samples=CLIP_SAMPLES, **kw)


def concert_station(tmp_path, *, announce=ANNOUNCE, pieces=True, voiced=True, lead_hours=1.5, eng=None,
                    **asm):
    """`clock_station`'s world (8 acts, short titled blocks, 3 IDs) with 7-minute shows,
    announcements switched on and every needed piece voiced."""
    st, logs = make_station(tmp_path, engine=eng or engine(), clock=short_clock(), lead_hours=lead_hours,
                            packages=library(8), ids=("a", "b", "c"))
    if announce is not None:
        st.ws.root.mkdir(parents=True, exist_ok=True)
        st.ws.announce_path.write_text(announce)
    folder = st.cfg.station.root / "interstitials" / "pieces"
    if pieces:
        folder.mkdir()
        pipeline.write_piece_list(st, NOW, *st.scan_all(NOW))
        if voiced:
            for txt in folder.glob("piece-*.txt"):
                txt.with_suffix(".mp3").write_bytes(b"ID3voiced")
    st.assemble = FakeAssembler(st.ws, **asm)
    return st, logs


@pytest.fixture
def fired(monkeypatch):
    got: list[tuple[str, str]] = []
    monkeypatch.setattr(alerts, "alert", lambda code, msg: got.append((code, msg)))
    monkeypatch.setattr(alerts, "resolve", lambda code: None)
    return got


def concert_rows(rows):
    return [r for r in rows if r.role == CONCERT_ROLE]


def show_rows_after(rows, r):
    return [x for x in rows[rows.index(r) + 1:] if x.kind == "show"]


def exact_frames(st, show):
    return st.planned_frames(st.engine.analyze(show))


def assert_well_formed(st, rows):
    """No placeholder ever reaches the plan; every concert row is a real clip in the workspace."""
    assert all(r.slug != PLACEHOLDER_SLUG and r.dir != "concert" for r in rows)
    for r in concert_rows(rows):
        assert r.kind == "interstitial" and r.dir == str(st.ws.concert_dir)
        assert r.slug.startswith("concert-") and (st.ws.concert_dir / f"{r.slug}.wav").is_file()
        assert r.named_shows and r.piece_ids
    assert read_plan(st.ws.plan_path) == rows


class ProjectSpy:
    """Wraps `pipeline.project`: records each input; `alter(inp, pieces)` may change the result."""

    def __init__(self, monkeypatch, alter=None, events=None):
        self.real = pipeline.project
        self.inputs = []
        self.alter = alter
        self.events = events
        monkeypatch.setattr(pipeline, "project", self)

    def __call__(self, inp, **kw):
        self.inputs.append(inp)
        if self.events is not None:
            first = inp.concert.first_break if inp.concert is not None else None
            self.events.append(("project", None if first is None else first.slug))
        got = self.real(inp, **kw)
        return self.alter(inp, got) if self.alter is not None else got


def is_pass2(inp):
    return inp.concert is not None and inp.concert.first_break is not None


# --- the switch ---------------------------------------------------------------------

@pytest.mark.parametrize("variant", ["no-announce-toml", "disabled", "no-pieces-folder"])
def test_feature_off_extends_exactly_as_today(tmp_path, monkeypatch, fired, variant):
    kw = {"no-announce-toml": {"announce": None},
          "disabled": {"announce": ANNOUNCE.replace("enabled = true", "enabled = false")},
          "no-pieces-folder": {"pieces": False}}[variant]
    st, _ = concert_station(tmp_path, **kw)
    spy = ProjectSpy(monkeypatch)
    rows = pipeline.plan_step(st, NOW)
    assert all(i.concert is None for i in spy.inputs)
    assert st.assemble.calls == [] and not concert_rows(rows)
    # the same station with the feature never set up at all plans the same rows
    st.ws.announce_path.unlink(missing_ok=True)
    shutil.rmtree(st.cfg.station.root / "interstitials" / "pieces", ignore_errors=True)
    st.ws.plan_path.unlink()
    today = pipeline.plan_step(dataclasses.replace(st, lengths=None, assemble=None), NOW)
    assert rows == today
    assert fired == []


def test_invalid_announce_toml_alerts_and_plans_as_today(tmp_path, monkeypatch, fired):
    st, _ = concert_station(tmp_path, announce="enabled = maybe\n")
    spy = ProjectSpy(monkeypatch)
    rows = pipeline.plan_step(st, NOW)
    assert rows[-1].end_frame >= st.until_frame(NOW)
    assert all(i.concert is None for i in spy.inputs) and not concert_rows(rows)
    assert {c for c, _ in fired} == {"announce-config"}


# --- the two passes ---------------------------------------------------------------------

def test_appends_a_concert_row_with_the_assembled_clip(tmp_path, fired):
    st, _ = concert_station(tmp_path)
    rows = pipeline.plan_step(st, NOW)
    breaks = concert_rows(rows)
    assert len(breaks) >= 3
    assert_well_formed(st, rows)
    clips = {s.slug: s for s in assemble.scan_clips(st.ws.concert_dir)}
    eligible = {s.slug: s for s in st.scan_now(NOW)}
    for r in breaks:
        clip = clips[r.slug]
        assert r.key == clip.key and r.frames == st.frames_of(clip)
        content = st.assemble.by_slug[r.slug]
        assert r.piece_ids == tuple(i for i, _ in content.pieces)
        assert r.named_shows == content.named and r.names == content.names
        after = [x.slug for x in show_rows_after(rows, r)]
        assert after[:len(r.named_shows)] == list(r.named_shows)[:len(after)]   # the promise is kept
    for r in rows:
        if r.kind == "show":
            assert r.frames == exact_frames(st, eligible[r.slug])
        else:
            assert r.frames == st.frames_of(clips[r.slug] if r.role == CONCERT_ROLE else
                                            next(p.show for p in st.scan_pieces(NOW) if p.slug == r.slug))
    assert any(len(r.named_shows) == 3 for r in breaks) and any("followed" in json.dumps(
        st.assemble.by_slug[r.slug].phrases) for r in breaks)
    assert not any(r.announcement_broken for r in rows)
    assert fired == []


def test_scan_pieces_includes_the_assembled_clips(tmp_path, fired, monkeypatch):
    st, _ = concert_station(tmp_path)
    assert st.concert_pieces() == []                               # no clip folder yet
    rows = pipeline.plan_step(st, NOW)
    got = {p.slug: p for p in st.concert_pieces()}
    assert {r.slug for r in concert_rows(rows)} <= set(got)
    for p in got.values():
        assert p.kind == "interstitial" and p.dir == str(st.ws.concert_dir) and p.role == CONCERT_ROLE
    assert set(got) <= {p.slug for p in st.scan_pieces(NOW)}
    assert set(got) <= {p.slug for p in st.scan_pieces(NOW, read_only=True)}
    monkeypatch.setattr(assemble, "scan_clips", lambda d: (_ for _ in ()).throw(ValueError("NUL")))
    assert st.concert_pieces() == []


def _swap_y_bucket(content):
    """`content` with Y's time phrase in another bucket (same shows, names, phrases)."""
    old = content.y_time_id
    alt = next(t for t in concert.ALL_TIME_PHRASES if piece_id(t) != old)
    pieces = tuple((piece_id(alt), alt) if pid == old else (pid, t) for pid, t in content.pieces)
    return dataclasses.replace(content, pieces=pieces, y_time_id=piece_id(alt))


def test_pass2_bucket_only_difference_keeps_pass1_wording(tmp_path, monkeypatch, fired):
    st, _ = concert_station(tmp_path)
    swapped = []

    def alter(inp, got):
        pp = got[0]
        if is_pass2(inp) and pp.concert is not None and pp.concert.y_time_id is not None:
            new = _swap_y_bucket(pp.concert)
            assert new.same_shape(pp.concert) and new != pp.concert
            swapped.append(new)
            return [dataclasses.replace(pp, concert=new)] + got[1:]
        return got

    ProjectSpy(monkeypatch, alter)
    rows = pipeline.plan_step(st, NOW)
    assert swapped
    swapped_ids = {tuple(i for i, _ in c.pieces) for c in swapped}
    breaks = concert_rows(rows)
    assert len(breaks) >= len(swapped) >= 1
    for r in breaks:
        assert r.piece_ids == tuple(i for i, _ in st.assemble.by_slug[r.slug].pieces)   # pass 1's wording
        assert r.piece_ids not in swapped_ids
    assert len(st.assemble.calls) == len(breaks)              # one assembly per break, none for pass 2
    assert_well_formed(st, rows)
    assert fired == []


def test_pass2_different_names_falls_to_the_last_rung(tmp_path, monkeypatch, fired):
    st, _ = concert_station(tmp_path)
    changed = []

    def alter(inp, got):
        pp = got[0]
        if is_pass2(inp) and pp.concert is not None and not changed and len(pp.concert.entries) > 1:
            c = pp.concert
            fewer = dataclasses.replace(c, entries=c.entries[:1], names=(), y_time_id=None,
                                        phrases=tuple(p for p in c.phrases if p not in ("followed", "then")))
            changed.append(pp.start_frame)
            return [dataclasses.replace(pp, concert=fewer, names=())] + got[1:]
        return got

    ProjectSpy(monkeypatch, alter)
    rows = pipeline.plan_step(st, NOW)
    assert len(changed) == 1
    at = next(r for r in rows if r.start_frame == changed[0])
    assert at.role in ("id", "next", "later") and at.kind == "interstitial"
    assert concert_rows(rows)                                  # later boundaries assemble again
    assert_well_formed(st, rows)
    assert fired == []


def test_assembly_failure_alerts_and_falls_to_the_last_rung(tmp_path, fired):
    st, logs = concert_station(tmp_path, fail=RuntimeError("disk on fire"))
    rows = pipeline.plan_step(st, NOW)
    assert rows[-1].end_frame >= st.until_frame(NOW)
    assert not concert_rows(rows) and st.assemble.calls
    assert any(r.role in ("id", "next", "later") for r in rows)
    assert {c for c, _ in fired} == {"announce-assembly"}
    assert any("disk on fire" in m for _, m in fired)
    assert any("disk on fire" in m for m in logs)
    assert_well_formed(st, rows)


def test_assembly_error_alerts_and_falls_to_the_last_rung(tmp_path, fired):
    from transmitter.errors import AssemblyError
    st, _ = concert_station(tmp_path, fail=AssemblyError("bed /x is unreadable"))
    rows = pipeline.plan_step(st, NOW, max_new=2)
    assert len(rows) == 2 and rows[1].role in ("id", "next", "later")
    assert {c for c, _ in fired} == {"announce-assembly"} and len(st.assemble.calls) == 1


def test_an_undecodable_piece_never_offered_falls_to_the_last_rung_and_terminates(tmp_path, fired):
    # an id the break did not offer: discarding it from `present` makes no progress, so
    # only putting that start at the last rung ends the re-proposals
    st, _ = concert_station(tmp_path, fail=PieceUndecodable("0123456789ab"), cap=60)
    rows = pipeline.plan_step(st, NOW)
    assert rows[-1].end_frame >= st.until_frame(NOW)
    assert not concert_rows(rows)
    assert len(st.assemble.calls) <= sum(r.kind == "interstitial" for r in rows)   # one try per boundary
    assert {c for c, _ in fired} == {"announce-assembly"}
    assert_well_formed(st, rows)


def test_typical_frames_is_the_typical_assembled_length(tmp_path):
    from transmitter import aacenc, grid
    st, _ = concert_station(tmp_path, eng=engine(extra=3))
    ci, settings = pipeline.concert_input(st, NOW, read_only=True)
    want = aacenc.frames_for(aacenc.pad_to_frame(grid.samples_for_seconds(concert.ASSEMBLED_TYPICAL_SECONDS)), 3)
    assert ci.typical_frames == want and settings.enabled and ci.id_text == ID_TEXT


def test_undecodable_piece_is_treated_absent_for_the_call(tmp_path, fired):
    st, _ = concert_station(tmp_path, undecodable_prefix="followed by")
    rows = pipeline.plan_step(st, NOW, max_new=2)
    first, second = st.assemble.calls
    bad = next(pid for pid, t in first.pieces if t.startswith("followed by"))
    assert "followed" in first.phrases and "followed" not in second.phrases
    assert rows[1].role == CONCERT_ROLE and bad not in rows[1].piece_ids
    assert rows[1].piece_ids == tuple(i for i, _ in second.pieces)
    assert [c for c, _ in fired] == ["announce-assembly"]
    assert f"piece {bad} undecodable" in fired[0][1]
    assert_well_formed(st, rows)


def test_unmeasurable_named_show_is_skipped_and_the_break_falls(tmp_path, fired):
    probe, _ = concert_station(tmp_path / "probe")
    y = pipeline.plan_step(probe, NOW, max_new=2)[1].named_shows[1]

    class Bad(FakeEngine):
        def analyze(self, show):
            if show.slug == y:
                self.analyzed.append(y)
                raise RenderError(f"{y}: not audio")
            return super().analyze(show)

    st, logs = concert_station(tmp_path / "real", eng=Bad(samples_per_file=SHOW_FILE_SAMPLES,
                                                            clip_samples=CLIP_SAMPLES))
    rows = pipeline.plan_step(st, NOW, max_new=2)
    assert rows[1].role in ("id", "next", "later")             # this boundary at the last rung
    assert any(m.startswith(f"skipping {y}: ") for m in logs)
    assert st.engine.analyzed.count(y) == 1
    n = len(st.assemble.calls)
    st.engine.analyzed.clear()
    rows = pipeline.plan_step(st, NOW)
    assert y not in {r.slug for r in rows} and y not in {s for r in rows for s in r.named_shows}
    # out of the pool for the rest of the call (today's skip): tried once, never proposed again
    assert st.engine.analyzed.count(y) == 1 and sum(y in c.named for c in st.assemble.calls[n:]) <= 1
    assert_well_formed(st, rows)
    assert fired == []                                         # today's skip: logged, not alerted


def test_named_shows_are_measured_before_pass_2(tmp_path, monkeypatch, fired):
    events = []

    class Spy(FakeEngine):
        def analyze(self, show):
            events.append(("analyze", show.slug))
            return super().analyze(show)

    st, _ = concert_station(tmp_path, eng=Spy(samples_per_file=SHOW_FILE_SAMPLES, clip_samples=CLIP_SAMPLES))
    st.notify = lambda m: events.append(("ping", m))
    ProjectSpy(monkeypatch, events=events)
    events.clear()
    rows = pipeline.plan_step(st, NOW, max_new=2)
    brk = rows[1]
    assert brk.role == CONCERT_ROLE and len(brk.named_shows) >= 2
    p2 = events.index(("project", brk.slug))
    before = [s for e, s in events[:p2] if e == "analyze"]
    assert brk.slug in before
    assert set(brk.named_shows) <= set(before)
    for i, e in enumerate(events):
        if e[0] == "analyze":
            assert events[i + 1] == ("ping", "WATCHDOG=1")      # the watchdog after each analysis
    # the named shows are exact now: the next rows need no measuring
    events.clear()
    rows = pipeline.plan_step(st, NOW, max_new=1)
    assert len(rows) == 3 and rows[2].slug == brk.named_shows[0]
    assert ("analyze", brk.named_shows[0]) not in events


def test_named_shows_are_placed_by_later_steps(tmp_path, fired):
    st, _ = concert_station(tmp_path, lead_hours=3)
    rows = []
    for _ in range(40):
        rows = pipeline.plan_step(st, NOW, max_new=1)
        if rows[-1].end_frame >= st.until_frame(NOW):
            break
    full = next(r for r in concert_rows(rows) if len(r.named_shows) == 3)
    seq = [x for x in rows[rows.index(full) + 1:]][:5]
    assert [x.slug for x in seq if x.kind == "show"] == list(full.named_shows)
    assert [x.kind for x in seq] == ["show", "interstitial", "show", "interstitial", "show"]
    for r in concert_rows(rows):
        after = [x.slug for x in show_rows_after(rows, r)]
        assert after[:len(r.named_shows)] == list(r.named_shows)[:len(after)]
    assert not any(r.announcement_broken for r in rows)
    assert_well_formed(st, rows)
    assert fired == []


# --- broken and void promises -----------------------------------------------------------

def test_broken_promise_marks_only_the_first_mismatched_row_and_alerts(tmp_path, fired):
    st, logs = concert_station(tmp_path)
    rows = pipeline.plan_step(st, NOW, max_new=3)            # show, break(X, Y, ...), X
    brk = rows[1]
    assert brk.role == CONCERT_ROLE and len(brk.named_shows) >= 2 and rows[2].slug == brk.named_shows[0]
    y = brk.named_shows[1]
    shutil.rmtree(st.cfg.station.root / y)
    n = len(rows)
    for _ in range(6):
        rows = pipeline.plan_step(st, NOW, max_new=1)
    new_shows = [r for r in rows[n:] if r.kind == "show"]
    assert len(new_shows) >= 2
    assert new_shows[0].announcement_broken and not any(r.announcement_broken for r in new_shows[1:])
    assert not any(r.announcement_broken for r in rows if r.kind != "show")
    assert [c for c, _ in fired] == ["announce-promise"]
    s = new_shows[0]
    assert f"promise-broken: {s.slug} at {s.block} {s.nominal_start}" in logs
    assert_well_formed(st, rows)


def test_void_promise_never_stalls_planning(tmp_path, fired):
    st, _ = concert_station(tmp_path)
    rows = pipeline.plan_step(st, NOW, max_new=2)
    brk = rows[1]
    assert brk.role == CONCERT_ROLE and len(brk.named_shows) >= 2
    mark_awaiting_fix(st.cfg.station.root / brk.named_shows[1])
    write_clock(st.ws, short_clock(hours=(1, 3, 6, 8, 11, 13, 16, 18, 21, 23), prefix="c"))
    rows = pipeline.plan_step(st, NOW)
    assert rows[-1].end_frame >= st.until_frame(NOW)
    assert brk.named_shows[1] not in {r.slug for r in rows}
    assert_well_formed(st, rows)
    assert [c for c, _ in fired] == ["announce-promise"]       # the show at Y's slot breaks the promise


@pytest.mark.parametrize("bad", [{"named_shows": [5, None]}, {"piece_ids": [1, {"x": 2}]},
                                 {"named_shows": ["", "x", "y", "z"]}])
def test_a_malformed_concert_row_never_raises(tmp_path, fired, bad):
    st, _ = concert_station(tmp_path)
    rows = pipeline.plan_step(st, NOW, max_new=2)
    assert rows[1].role == CONCERT_ROLE
    data = rows[1].to_json()
    data.update(bad)
    write_plan(st.ws.plan_path, [rows[0], type(rows[1]).from_json(data)])
    rows = pipeline.plan_step(st, NOW)
    assert rows[-1].end_frame >= st.until_frame(NOW)


# --- the guard: a raising concert or promise path is today's logic ----------------------

@pytest.mark.parametrize("path", ["concert", "promise"])
def test_a_raising_concert_or_promise_path_falls_to_todays_logic(tmp_path, monkeypatch, fired, path):
    st, _ = concert_station(tmp_path)
    if path == "promise":
        rows = pipeline.plan_step(st, NOW, max_new=2)        # a live promise in the plan
        assert rows[1].role == CONCERT_ROLE
        st.ws.announce_path.unlink()                          # announcements off: promises still kept

        def boom(self, *a, **k):
            raise RuntimeError("promise path bug")
        monkeypatch.setattr(scheduler._Projection, "_promised_show", boom)
    else:
        def boom(self, *a, **k):
            raise RuntimeError("concert path bug")
        monkeypatch.setattr(scheduler._Projection, "_try_concert", boom)
    spy = ProjectSpy(monkeypatch)
    before = read_plan(st.ws.plan_path)
    rows = pipeline.plan_step(st, NOW, max_new=4)
    assert len(rows) == len(before) + 4 and rows[:len(before)] == before
    code = "announce-assembly" if path == "concert" else "announce-promise"
    assert [c for c, _ in fired] == [code] and "bug" in fired[0][1]
    first_off = next(i for i, inp in enumerate(spy.inputs) if inp.concert is None and not inp.promises)
    assert first_off >= 1
    assert all(inp.concert is None and not inp.promises for inp in spy.inputs[first_off:])
    assert not concert_rows(rows[len(before):])
    assert_well_formed(st, rows)


def test_a_raising_promise_lookup_in_extend_falls_to_todays_logic(tmp_path, monkeypatch, fired):
    from transmitter import promises
    st, _ = concert_station(tmp_path)
    pipeline.plan_step(st, NOW, max_new=2)

    def boom(*a, **k):
        raise RuntimeError("remaining bug")
    monkeypatch.setattr(promises, "remaining", boom)
    spy = ProjectSpy(monkeypatch)
    rows = pipeline.plan_step(st, NOW, max_new=3)
    assert len(rows) == 5
    assert all(inp.concert is None and not inp.promises for inp in spy.inputs)
    assert [c for c, _ in fired] == ["announce-promise"]


def test_a_plan_error_from_a_guarded_projection_propagates(tmp_path, monkeypatch, fired):
    from transmitter.errors import PlanError
    st, _ = concert_station(tmp_path)

    def boom(self, *a, **k):
        raise PlanError("planning impossible")
    monkeypatch.setattr(scheduler._Projection, "_try_concert", boom)
    with pytest.raises(PlanError, match="planning impossible"):
        pipeline.plan_step(st, NOW)
    assert not st.ws.plan_path.exists()


# --- the real assembler (call-scoped, over the pieces folder) ----------------------------

def _voice_all_for_real(st, tmp_path, *, bed: bool):
    import numpy as np

    from tests_transmitter.helpers import stereo_sine, write_mp3
    one = tmp_path / "one.mp3"
    write_mp3(one, stereo_sine(0.3, 440, 0.3))
    data = one.read_bytes()
    for mp3 in (st.cfg.station.root / "interstitials" / "pieces").glob("piece-*.mp3"):
        mp3.write_bytes(data)
    bed_path = tmp_path / "bed.mp3"
    if bed:
        t = np.arange(44_100, dtype=np.float64) / 44_100
        write_mp3(bed_path, np.stack([(0.5 * np.sin(2 * np.pi * 100 * t)).astype(np.float32)] * 2, axis=1))
    st.ws.announce_path.write_text(f'enabled = true\nbed = "{bed_path}"\nid_text = "{ID_TEXT}"\n')
    st.assemble = None


@requires_ffmpeg
def test_the_real_assembler_writes_the_clip_into_the_workspace(tmp_path, fired):
    st, _ = concert_station(tmp_path)
    _voice_all_for_real(st, tmp_path, bed=True)
    rows = pipeline.plan_step(st, NOW, max_new=2)
    brk = rows[1]
    assert brk.role == CONCERT_ROLE
    clip = {s.slug: s for s in assemble.scan_clips(st.ws.concert_dir)}[brk.slug]
    assert brk.key == clip.key and brk.dir == str(st.ws.concert_dir)
    with wave.open(str(st.ws.concert_dir / f"{brk.slug}.wav")) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (2, 44_100, 2)
    assert_well_formed(st, rows)
    assert fired == []


@requires_ffmpeg
def test_the_real_assembler_with_a_missing_bed_falls_to_the_last_rung(tmp_path, fired):
    st, _ = concert_station(tmp_path)
    _voice_all_for_real(st, tmp_path, bed=False)
    rows = pipeline.plan_step(st, NOW, max_new=2)
    assert rows[1].role in ("id", "next", "later")
    assert [c for c, _ in fired] == ["announce-assembly"] and "bed" in fired[0][1]
    assert not st.ws.concert_dir.exists() or not any(st.ws.concert_dir.glob("concert-*.wav"))
