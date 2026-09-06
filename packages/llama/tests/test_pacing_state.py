from datetime import datetime, timedelta, timezone

from herder.usage import Meter, UsageReading
from llama import pacing_state as ps

NOW = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
RESET = NOW + timedelta(hours=2)
OTHER_RESET = NOW + timedelta(hours=4, minutes=59)


def _r(percent, reset=RESET):
    return UsageReading(five_hour=Meter(percent, reset), seven_day=None,
                        per_model={}, fetched_at=NOW)


def test_first_observation_seeds_the_estimate():
    out = ps.observe(_r(10), _r(14), ps.PacingState(None, 0))
    assert out.per_show_delta == 4.0
    assert out.samples == 1


def test_later_observations_are_smoothed():
    seeded = ps.PacingState(4.0, 1)
    out = ps.observe(_r(10), _r(20), seeded)
    expected = 4.0 + ps.EWMA_ALPHA * (10.0 - 4.0)
    assert out.per_show_delta == expected


def test_a_window_rollover_contributes_nothing():
    # resets_at changed, so the delta spans a reset and is meaningless.
    # Folding it in would drag the estimate toward zero -- an UNDER-estimate,
    # which is what walks a run into the wall.
    seeded = ps.PacingState(4.0, 3)
    assert ps.observe(_r(90), _r(2, OTHER_RESET), seeded) == seeded


def test_a_failed_reading_at_either_end_contributes_nothing():
    seeded = ps.PacingState(4.0, 3)
    assert ps.observe(None, _r(14), seeded) == seeded
    assert ps.observe(_r(10), None, seeded) == seeded
    assert ps.observe(_r(10), UsageReading(None, None, {}, NOW), seeded) == seeded


def test_a_negative_delta_contributes_nothing():
    seeded = ps.PacingState(4.0, 3)
    assert ps.observe(_r(20), _r(10), seeded) == seeded


def test_a_rollover_with_a_positive_delta_still_contributes_nothing():
    # The resets_at check must fire on its own -- a delta that happens to
    # look plausible (positive) must not slip past it just because the
    # negative-delta guard alone would have let it through.
    seeded = ps.PacingState(4.0, 3)
    assert ps.observe(_r(10), _r(14, OTHER_RESET), seeded) == seeded


def test_a_zero_delta_is_folded_in_normally():
    # A show that used none of the meter is a real, useful sample -- distinct
    # from a negative delta, which is corruption/rollover evidence and must
    # be declined instead.
    seeded = ps.PacingState(4.0, 1)
    out = ps.observe(_r(10), _r(10), seeded)
    expected = 4.0 + ps.EWMA_ALPHA * (0.0 - 4.0)
    assert out.per_show_delta == expected
    assert out.samples == 2


def test_ewma_alpha_is_pinned_at_point_4():
    # Other tests compute their expectation from ps.EWMA_ALPHA itself, which
    # pins the FORMULA but not the chosen constant. Pin the literal value
    # too, since it is policy (see the module docstring) and an accidental
    # retune should fail a test, not just look different.
    assert ps.EWMA_ALPHA == 0.4


def test_state_round_trips_through_disk(tmp_path):
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)
    out = ps.record(tmp_path, _r(10), _r(14))
    assert out.per_show_delta == 4.0
    assert ps.read_state(tmp_path) == out


def test_unreadable_state_degrades_to_empty(tmp_path):
    (tmp_path / "pacing-state.json").write_text("{ not json")
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)


def test_negative_persisted_delta_degrades_to_empty(tmp_path):
    # observe() never writes a negative delta, so a negative one on disk is
    # corruption -- not a signal to clamp or repair.
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": -4.0, "samples": 3}')
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)


def test_non_numeric_persisted_delta_degrades_to_empty(tmp_path):
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": "oops", "samples": 3}')
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)


def test_list_persisted_delta_degrades_to_empty(tmp_path):
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": [1, 2], "samples": 3}')
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)


def test_bool_persisted_delta_degrades_to_empty(tmp_path):
    # bool is a subclass of int in Python; True/False are not deltas that
    # observe() could ever have produced, so they are rejected too.
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": true, "samples": 3}')
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)


def test_non_finite_persisted_delta_degrades_to_empty(tmp_path):
    # json.loads accepts the non-standard Infinity/NaN literals; neither is
    # a usable non-negative real number, and NaN >= 0 is False in a way that
    # would silently pass a naive sign-only check.
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": NaN, "samples": 3}')
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": Infinity, "samples": 3}')
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)


def test_null_persisted_delta_is_the_valid_empty_sentinel(tmp_path):
    # An explicit JSON null (what record() writes before the first
    # observation) is the legitimate "no estimate yet" state, not corruption.
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": null, "samples": 0}')
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)


def test_null_persisted_delta_preserves_the_samples_field(tmp_path):
    # None is accepted independent of whatever `samples` happens to be on
    # disk -- read_state must not zero samples out just because the delta
    # is the empty sentinel. (record() never actually writes this
    # combination itself, but read_state's validation must not conflate
    # "delta is None" with "reset the whole state".)
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": null, "samples": 5}')
    assert ps.read_state(tmp_path) == ps.PacingState(None, 5)


def test_positive_persisted_delta_round_trips_as_float(tmp_path):
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": 4, "samples": 1}')
    out = ps.read_state(tmp_path)
    assert out == ps.PacingState(4.0, 1)
    assert isinstance(out.per_show_delta, float)


def test_zero_persisted_delta_is_accepted(tmp_path):
    # 0 is a legitimate non-negative delta (a show that cost nothing) --
    # distinguishes the >= 0 bound from a stricter > 0 that would wrongly
    # reject it.
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": 0, "samples": 2}')
    assert ps.read_state(tmp_path) == ps.PacingState(0.0, 2)


def test_top_level_json_array_degrades_to_empty(tmp_path):
    # A JSON array decodes fine but has no .get -- exercises the
    # AttributeError arm of read_state's except tuple, which is distinct
    # from the JSONDecodeError (a ValueError) a malformed parse raises.
    (tmp_path / "pacing-state.json").write_text("[1, 2, 3]")
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)


def test_non_convertible_samples_degrades_to_empty(tmp_path):
    # int(["x"]) raises TypeError -- exercises the TypeError arm.
    (tmp_path / "pacing-state.json").write_text(
        '{"per_show_delta": 4.0, "samples": ["x"]}')
    assert ps.read_state(tmp_path) == ps.PacingState(None, 0)
