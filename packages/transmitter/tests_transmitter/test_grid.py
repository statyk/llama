import pytest

from transmitter import grid


def test_segment_duration_is_exact():
    assert grid.SEGMENT_SAMPLES == 451_584
    assert grid.D_US == 10_240_000
    assert grid.D_MS == 10_240
    assert grid.TS_PER_SEGMENT == 921_600


def test_segment_timestamp_wraps_at_2_pow_33():
    assert grid.segment_timestamp(0) == 0
    assert grid.segment_timestamp(1) == 921_600
    assert grid.segment_timestamp(9320) == 8_589_312_000
    assert grid.segment_timestamp(9321) == 299_008
    assert grid.segment_timestamp(9321) == (9321 * 921_600) % (1 << 33)


def test_segment_timestamp_rejects_negative():
    with pytest.raises(ValueError):
        grid.segment_timestamp(-1)


def test_index_at_floors_and_goes_negative_before_the_epoch():
    e = 1_000_000_000_000
    assert grid.segment_index_at(e, e) == 0
    assert grid.segment_index_at(e, e + grid.D_US - 1) == 0
    assert grid.segment_index_at(e, e + grid.D_US) == 1
    assert grid.segment_index_at(e, e - 1) == -1


def test_first_segment_at_or_after_is_a_ceiling():
    assert grid.first_segment_at_or_after(0, 0) == 0
    assert grid.first_segment_at_or_after(0, 1) == 1
    assert grid.first_segment_at_or_after(0, grid.D_US) == 1
    assert grid.first_segment_at_or_after(0, grid.D_US + 1) == 2


def test_gap_frames_round_up_to_whole_frames():
    assert grid.gap_frames(2.0) == 87      # 88200 samples / 1024 = 86.13
    assert grid.gap_frames(0.75) == 33     # 33075 / 1024 = 32.3
    assert grid.gap_frames(0.0) == 0


def test_iso_round_trip():
    us = grid.iso_to_us("2026-10-10T12:00:00Z")
    assert grid.us_to_iso(us) == "2026-10-10T12:00:00.000Z"
    assert grid.iso_to_us(grid.us_to_iso(us + grid.D_US)) == us + grid.D_US


def test_iso_requires_an_offset():
    with pytest.raises(ValueError):
        grid.iso_to_us("2026-10-10T12:00:00")
