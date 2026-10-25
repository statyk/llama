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
