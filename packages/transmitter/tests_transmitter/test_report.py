"""Pure report formatting: block views and the summary."""

from tests_transmitter.helpers import show_piece
from transmitter import report
from transmitter.announce import Needed
from transmitter.clock import BlockConfig, ClockConfig
from transmitter.grid import frame_to_us, iso_to_us, us_to_iso
from transmitter.layout import PlanRow
from transmitter.pieces import Piece
from transmitter.scheduler import PlannedPiece
from transmitter.workspace import Epoch

E = iso_to_us("2026-11-02T00:00:00Z")
EPOCH = Epoch("etest", E)
CLOCK = ClockConfig(timezone="UTC", block=[
    BlockConfig(name="a", title="Alpha", start="00:00", profiles=["p"]),
    BlockConfig(name="b", title="Beta", start="02:00", profiles=["p"])])
NOM_A = "2026-11-02T00:00:00Z"
NOM_B = "2026-11-02T02:00:00Z"
FR_MIN = 60 * 44_100 // 1024 + 1


def row(seq, slug, start_min, minutes, *, block="a", nominal=NOM_A, miss=None, fill=None, bends=(),
        degraded=False, kind="show", role="show"):
    return PlanRow(seq=seq, slug=slug, dir=slug, key=f"k-{slug}", start_frame=start_min * FR_MIN,
                   frames=minutes * FR_MIN, kind=kind, block=block, nominal_start=nominal, role=role, miss=miss,
                   fill=fill, bends=tuple(bends), degraded=degraded, package=slug if kind == "show" else None)


def planned(slug, start_min, minutes, *, block="b", nominal=NOM_B, exact=False, miss=None, fill=None, bends=()):
    p = show_piece(slug, artist=slug.upper(), date="1977-05-08", profile="p", frames=minutes * FR_MIN, exact=exact)
    return PlannedPiece(p, start_min * FR_MIN, False, block, nominal, "show", miss=miss, fill=fill, bends=tuple(bends))


def test_block_views_report_slip_fill_cause_and_bends():
    rows = [row(0, "s1", 10, 50, miss=True, bends=("gap",)),               # starts 10 min late
            row(1, "s2", 62, 40, fill="pool-short", bends=("era",)),
            row(2, "id-x", 104, 1, kind="interstitial", role="id", block="b", nominal=NOM_B)]
    proj = [planned("s3", 106, 60, miss=False)]
    miss_ann = Needed("abc123", "Coming up", "next_one", "b", NOM_B)
    views = report.block_views(rows, proj, CLOCK, EPOCH, missing=[miss_ann],
                               meta_of=lambda pkg: ("Band", "1977-05-08"))
    a, b = views
    assert (a.block, a.title, a.miss, a.persisted) == ("a", "Alpha", True, True)
    assert round(a.slip_minutes, 2) == 10 and a.start_local == "Mon 11-02 00:10"
    assert a.bends == ("gap", "era")                         # once per block, in RULES order
    assert [s.fill for s in a.shows] == [None, "pool-short"]
    assert a.shows[0].artist == "Band" and not a.shows[0].estimated
    assert (b.block, b.persisted, b.miss) == ("b", False, False)
    assert b.shows[0].estimated and b.breaks == ("station ID id-x",)
    assert [n.id for n in b.missing] == ["abc123"] and a.missing == ()
    assert abs(b.slip_minutes - (106 * FR_MIN * 1024 / 44_100 - 120 * 60) / 60) < 1e-6


def test_summary_counts():
    rows = [row(0, "s1", 10, 50, miss=True, bends=("gap",)),
            row(1, "s2", 62, 40, fill="pool-short"),
            row(2, "s3", 104, 30, fill="structural", miss=False, block="b", nominal=NOM_B, degraded=True),
            row(3, "s4", 140, 20, miss=True, block="b", nominal=NOM_B, bends=("gap",))]   # not the first show
    views = report.block_views(rows, [], CLOCK, EPOCH)
    s = report.summary(views, 4 * 3_600_000_000)
    assert s.misses == 1                                     # first-show rows only
    assert round(s.fill_minutes["pool-short"]) == 40 and round(s.fill_minutes["structural"]) == 30
    assert abs(s.fill_share - 70 / 240) < 0.001
    assert s.bends == {"gap": 2} and s.degraded == 1


def test_summary_shortest_repeat_gap():
    rows = [row(0, "s1", 0, 30), row(1, "s2", 40, 30),
            row(2, "s1", 24 * 60 + 5, 30, block="b", nominal=NOM_B)]
    s = report.summary(report.block_views(rows, [], CLOCK, EPOCH), 86_400_000_000)
    assert round(s.shortest_gap_days, 1) == 1.0
    assert report.summary(report.block_views(rows[:2], [], CLOCK, EPOCH), 1).shortest_gap_days is None


def test_profile_stats_and_reason_key():
    st = report.profile_stats([("p", 100.0, False), ("p", 200.0, True), ("p", 150.0, False), (None, 90.0, False)])
    p = next(x for x in st if x.profile == "p")
    assert (p.count, p.median, p.estimated) == (3, 150.0, 1) and p.p10 <= p.median <= p.p90
    assert any(x.profile == "(none)" for x in st)
    assert report.reason_key("awaiting fix from llama: pending") == "awaiting fix from llama"
    assert report.reason_key("changed 12s ago (quiet period 1800s)") == "changed within the quiet period"
    assert report.reason_key("3 DJ clip(s) missing") == report.reason_key("1 DJ clip(s) missing")
    assert report.reason_key("3 of 12 track file(s) missing") == report.reason_key("1 of 9 track file(s) missing")
    assert report.fill_label("pool-short") == "pool short" and report.fill_label("structural") == "longer than max_shows"


# --- rotation ------------------------------------------------------------------

DAY = 86_400_000_000
T0 = iso_to_us("2026-10-01T00:00:00Z")


def test_rotation_counts_played_never_repeats_and_gaps():
    eligible = [("a1", "dead"), ("a2", "dead"), ("a3", "dead"), ("b1", "indie"), ("b2", None)]
    airings = [("a1", T0), ("a1", T0 + 10 * DAY), ("a1", T0 + 60 * DAY), ("a2", T0 + 5 * DAY),
               ("b1", T0 + 1 * DAY), ("gone", T0 + 2 * DAY), ("gone", T0 + 3 * DAY)]
    rep = report.rotation(eligible, airings, gap_days=45)
    by = {p.profile: p for p in rep.profiles}
    assert list(by) == ["(none)", "dead", "indie"]
    d = by["dead"]
    assert (d.eligible, d.played, d.never, d.plays, d.repeated) == (3, 2, 1, 4, 1)
    assert d.never_slugs == ("a3",)
    assert (d.gap_min, d.gap_median, d.gap_mean) == (10.0, 30.0, 30.0)
    assert d.under_gap == 1
    assert by["(none)"].never_slugs == ("b2",) and by["(none)"].gap_min is None
    t = rep.total
    assert (t.eligible, t.played, t.never, t.plays, t.repeated, t.under_gap) == (5, 3, 2, 5, 1, 1)
    assert (rep.gone_shows, rep.gone_plays, rep.gone_under_gap) == (1, 2, 1)
    assert rep.first_us == T0 and rep.last_us == T0 + 60 * DAY
    assert [(s.package, s.plays, s.last_us) for s in rep.top] == [("a1", 3, T0 + 60 * DAY), ("gone", 2, T0 + 3 * DAY)]


def test_rotation_since_window_and_gap_rule_off():
    airings = [("a1", T0), ("a1", T0 + 10 * DAY), ("a1", T0 + 20 * DAY)]
    rep = report.rotation([("a1", "dead")], airings, gap_days=45, since_us=T0 + 5 * DAY)
    (d,) = rep.profiles
    assert (d.plays, d.gap_min, d.under_gap) == (2, 10.0, 1)
    assert report.rotation([("a1", "dead")], airings, gap_days=0).total.under_gap == 0


def test_rotation_lines():
    eligible = [("a1", "dead"), ("a3", "dead")]
    airings = [("a1", T0), ("a1", T0 + 10 * DAY), ("gone", T0)]
    rep = report.rotation(eligible, airings, gap_days=45)
    out = "\n".join(report.rotation_lines(rep, tz="UTC", never=False))
    assert "concert gap 45 days" in out and "dead" in out and "total" in out
    assert "aired, no longer eligible  1 show(s), 1 play(s)" in out
    assert "a1  2 plays" in out
    assert "a3" not in out
    out = "\n".join(report.rotation_lines(rep, tz="UTC", never=True))
    assert "never played" in out and "a3" in out
    empty = "\n".join(report.rotation_lines(report.rotation([], [], gap_days=45), tz="UTC", never=True))
    assert "nothing aired" in empty
    windowed = "\n".join(report.rotation_lines(report.rotation([], [], gap_days=45, since_us=T0), tz="UTC",
                                                never=False))
    assert "nothing aired in the window (window from" in windowed


def test_rotation_top_marks_eligible_show_without_profile_as_none_not_gone():
    rep = report.rotation([("a", None)], [("a", T0), ("a", T0 + 50 * DAY), ("g", T0), ("g", T0 + DAY)], gap_days=45)
    assert {s.package: s.profile for s in rep.top} == {"a": "(none)", "g": None}
