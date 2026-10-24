import io
import urllib.request

import pytest

from transmitter import alerts, grid
from transmitter import deadclock
from transmitter.deadclock import DeadClockMonitor, playlist_age_s

E = grid.iso_to_us("2026-10-10T12:00:00Z")
D = grid.D_US


def live_playlist(cur: int, lookahead: int = 0, hold_back: int | None = None, window: int = 6,
                  start_tag: bool = True, server_control: bool = True) -> str:
    """The antenna clock's live playlist written while segment `cur` airs:
    `window` segments ending at cur + lookahead, with the hold-back tags."""
    end = cur + lookahead
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:11", f"#EXT-X-MEDIA-SEQUENCE:{end - window + 1}",
             "#EXT-X-DISCONTINUITY-SEQUENCE:0"]
    if hold_back is not None:
        offset = f"{hold_back * 10.24:.3f}"
        if start_tag:
            lines.append(f"#EXT-X-START:TIME-OFFSET=-{offset}")
        if server_control:
            lines.append(f"#EXT-X-SERVER-CONTROL:HOLD-BACK={offset}")
    for n in range(end - window + 1, end + 1):
        lines += [f"#EXT-X-PROGRAM-DATE-TIME:{grid.us_to_iso(E + n * D)}", "#EXTINF:10.240,", f"seg/e1/{n}.aac"]
    return "\n".join(lines) + "\n"


def offair_playlist(seq: int) -> str:
    return (f"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:11\n#EXT-X-MEDIA-SEQUENCE:{seq}\n"
            "#EXT-X-DISCONTINUITY-SEQUENCE:3\n#EXT-X-DISCONTINUITY\n#EXTINF:10.240,\nfallback/v1/notice.aac\n"
            "#EXT-X-ENDLIST\n")


def test_age_from_the_newest_program_date_time():
    assert playlist_age_s(live_playlist(100), E + 100 * D + 4_000_000, E) == pytest.approx(4.0)


def test_age_of_an_offair_playlist_from_its_media_sequence():
    # The clock numbers it indexAt(scheduledTime + 75 s): ahead of now, so negative while fresh.
    assert playlist_age_s(offair_playlist(107), E + 100 * D, E) < 0
    assert playlist_age_s(offair_playlist(100), E + 120 * D, E) == pytest.approx(20 * 10.24)


def test_age_of_a_lookahead_playlist_counts_from_the_held_back_start_not_its_newest_segment():
    # Lookahead 12 = hold-back 12 (the deployment rule): the newest segment
    # starts ~123 s in the future, but the playlist is as old as the segment
    # airing when it was written.
    for kw in ({}, {"server_control": False}, {"start_tag": False}):
        text = live_playlist(100, lookahead=12, hold_back=12, window=16, **kw)
        assert playlist_age_s(text, E + 100 * D + 4_000_000, E) == pytest.approx(4.0)
    # No tag (lookahead 0, the phase-1 playlist): the newest segment, as before.
    assert playlist_age_s(live_playlist(100), E + 100 * D + 4_000_000, E) == pytest.approx(4.0)


def test_a_malformed_or_positive_offset_is_ignored():
    text = live_playlist(100, lookahead=12, hold_back=12, window=16)
    bad = text.replace("TIME-OFFSET=-122.880", "TIME-OFFSET=nonsense").replace("HOLD-BACK=122.880", "HOLD-BACK=x")
    assert playlist_age_s(bad, E + 112 * D, E) == pytest.approx(0.0)    # dated by its newest segment
    positive = (text.replace("TIME-OFFSET=-122.880", "TIME-OFFSET=122.880")
                .replace("HOLD-BACK=122.880", "HOLD-BACK=40.960"))
    # Positive START ignored; HOLD-BACK (40.96 s) is read: newest segment 112 starts at now - 40.96 s + age.
    assert playlist_age_s(positive, E + 112 * D, E) == pytest.approx(40.96)
    neg_inf = text.replace("TIME-OFFSET=-122.880", "TIME-OFFSET=-inf").replace("HOLD-BACK=122.880", "HOLD-BACK=40.960")
    # -inf is not finite: START ignored, falls through to HOLD-BACK.
    assert playlist_age_s(neg_inf, E + 112 * D, E) == pytest.approx(40.96)
    only_inf = text.replace("TIME-OFFSET=-122.880", "TIME-OFFSET=-inf").replace("HOLD-BACK=122.880", "HOLD-BACK=x")
    assert playlist_age_s(only_inf, E + 112 * D, E) == pytest.approx(0.0)


def test_start_wins_over_server_control_when_both_differ():
    text = live_playlist(100, lookahead=12, hold_back=12, window=16)
    text = text.replace("HOLD-BACK=122.880", "HOLD-BACK=40.960")
    # START (122.88 s) wins: age 0 when now = segment 100 start (HOLD-BACK would give -81.92).
    assert playlist_age_s(text, E + 100 * D, E) == pytest.approx(0.0)


def test_age_of_an_offair_playlist_subtracts_the_last_live_hold_back():
    # A late invocation numbers the notice indexAt(write) + lookahead + 1.
    written = E + 985 * D
    text = offair_playlist(985 + 13)
    assert playlist_age_s(text, E + 1000 * D, E) == pytest.approx(2 * 10.24)
    assert playlist_age_s(text, E + 1000 * D, E, live_hold_back_s=122.88) == pytest.approx(14 * 10.24)
    assert playlist_age_s(text, E + 1000 * D, E, live_hold_back_s=122.88) <= (E + 1000 * D - written) / 1e6


def test_age_is_none_without_dates_or_sequence():
    assert playlist_age_s("#EXTM3U\n", E, E) is None
    assert playlist_age_s("<html>", E, E) is None


@pytest.fixture
def fired(monkeypatch):
    events = []
    monkeypatch.setattr(alerts, "alert", lambda code, msg: events.append(("alert", code, msg)))
    monkeypatch.setattr(alerts, "resolve", lambda code: events.append(("resolve", code)))
    return events


FRESH_GUARD = {"blocked": False, "offair": False, "error": None, "guard_evaluated_at": None}


def _monitor(responses):
    it = iter(responses)
    return DeadClockMonitor("https://radio.example.org/live.m3u8", E, 120.0, 2700.0, 17, fetch=lambda url: next(it))


def _guard(now_us, minutes_ago=5, **kw):
    return {**FRESH_GUARD, "guard_evaluated_at": grid.us_to_iso(now_us - minutes_ago * 60_000_000), **kw}


def test_a_fresh_playlist_resolves_and_one_stale_read_is_not_a_death(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(1000)), (200, live_playlist(980)), (200, live_playlist(1000))])
    m.check(now, lambda: _guard(now))
    m.check(now, lambda: _guard(now))           # 20 intervals old: genuinely stale, but only once
    m.check(now, lambda: _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    assert ("resolve", "dead-clock") in fired and ("resolve", "guard-stale") in fired


def test_two_stale_reads_in_a_row_alert(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(985))] * 2)
    m.check(now, lambda: _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    m.check(now, lambda: _guard(now))
    assert [e[1] for e in fired if e[0] == "alert"] == ["dead-clock"]


def test_a_dead_clock_with_lookahead_alerts_as_soon_as_without(fired):
    # Written while segment 985 aired, read at 1000: 153.6 s stale. Dated by
    # its newest PROGRAM-DATE-TIME alone it would read 30.7 s and never alert.
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(985, lookahead=12, hold_back=12, window=16))] * 2)
    m.check(now, lambda: _guard(now))
    m.check(now, lambda: _guard(now))
    assert [e[1] for e in fired if e[0] == "alert"] == ["dead-clock"]


def test_a_dead_clock_while_off_air_uses_the_hold_back_last_seen_live(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(980, lookahead=12, hold_back=12, window=16))]
                 + [(200, offair_playlist(985 + 13))] * 2)
    m.check(E + 980 * D, lambda: _guard(now))   # fresh live read: remembers the 122.88 s hold-back
    m.check(now, lambda: _guard(now))
    m.check(now, lambda: _guard(now))           # the notice was written 153.6 s ago
    assert [e[1] for e in fired if e[0] == "alert"] == ["dead-clock"]


def test_a_403_is_expected_while_blocked_and_alarms_only_once_the_guard_cache_has_caught_up(fired):
    now = E + 1000 * D
    m = _monitor([(403, "")] * 18)
    m.check(now, lambda: _guard(now, offair=True))
    assert not [e for e in fired if e[0] == "alert"]
    for _ in range(16):                     # the cache may say "not blocked" for guard_check_minutes after `offair on`
        m.check(now, lambda: _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    m.check(now, lambda: _guard(now))
    alerted = [e for e in fired if e[0] == "alert"]
    assert alerted[0][1] == "dead-clock" and "kill switch" in alerted[0][2]


def test_network_errors_alert_only_when_they_persist(fired):
    now = E + 1000 * D
    m = _monitor([(0, "")] * 9 + [(200, live_playlist(1000))] + [(0, "")] * 10)
    for _ in range(10):
        m.check(now, lambda: _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    for _ in range(10):
        m.check(now, lambda: _guard(now))
    assert [e[1] for e in fired if e[0] == "alert"] == ["dead-clock"]


def test_a_stale_guard_alerts(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(1000))] * 2)
    m.check(now, lambda: _guard(now, minutes_ago=46))
    assert [e[1] for e in fired if e[0] == "alert"] == ["guard-stale"]
    fired.clear()
    m.check(now, lambda: {**FRESH_GUARD})                     # guard.json read fine but carries no evaluation
    assert [e[1] for e in fired if e[0] == "alert"] == ["guard-stale"]


def test_stale_fresh_stale_fresh_never_alerts(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(980)), (200, live_playlist(1000))] * 2)
    for _ in range(4):
        m.check(now, lambda: _guard(now))
    assert not [e for e in fired if e[0] == "alert"]


def test_403_while_the_guard_says_blocked_never_alerts_even_past_the_threshold(fired):
    now = E + 1000 * D
    m = _monitor([(403, "")] * 20)
    for _ in range(20):
        m.check(now, lambda: _guard(now, blocked=True, offair=False))
    assert not [e for e in fired if e[0] == "alert"]


@pytest.mark.parametrize("exc", [__import__("http.client").client.IncompleteRead(b"x"),
                                 __import__("http.client").client.BadStatusLine("x"),
                                 ValueError("bad url"), OSError("boom")])
def test_fetch_text_turns_transport_errors_into_status_zero(monkeypatch, exc):
    def boom(req, timeout=None):
        raise exc
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert deadclock.fetch_text("https://radio.example.org/live.m3u8") == (0, "")


def test_fetch_text_keeps_the_http_status_of_a_403(monkeypatch):
    import urllib.error

    def forbidden(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "no", {}, io.BytesIO(b""))
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    assert deadclock.fetch_text("https://radio.example.org/live.m3u8") == (403, "")


def test_an_odd_transport_error_does_not_alert_on_the_first_call(fired, monkeypatch):
    import http.client
    now = E + 1000 * D

    def boom(req, timeout=None):
        raise http.client.IncompleteRead(b"")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    m = DeadClockMonitor("https://radio.example.org/live.m3u8", E, 120.0, 2700.0, 17)
    m.check(now, lambda: _guard(now))
    assert not [e for e in fired if e[0] == "alert"]


def test_an_unreadable_guard_alerts_once_it_has_persisted_and_recovers(fired):
    now = E + 1000 * D
    m = DeadClockMonitor("https://radio.example.org/live.m3u8", E, 120.0, 2700.0, 17,
                         fetch=lambda url: (200, live_playlist(1000 + (m_clock[0] - now) // D)))
    m_clock = [now]
    bad = {"blocked": True, "offair": None, "error": "AccessDenied", "guard_evaluated_at": None}
    m.check(now, lambda: bad)
    m_clock[0] = now + 44 * 60_000_000
    m.check(m_clock[0], lambda: bad)
    assert not [e for e in fired if e[0] == "alert"]
    m_clock[0] = now + 45 * 60_000_000
    m.check(m_clock[0], lambda: bad)
    alerted = [e for e in fired if e[0] == "alert"]
    assert [e[1] for e in alerted] == ["guard-stale"] and "AccessDenied" in alerted[0][2]
    fired.clear()
    later = m_clock[0] = now + 46 * 60_000_000
    m.check(later, lambda: _guard(later))
    assert ("resolve", "guard-stale") in fired and m.guard_error_since_us is None
    m.check(later, lambda: bad)                              # a new failure restarts the timer
    assert m.guard_error_since_us == later and not [e for e in fired if e[0] == "alert"]


def test_a_cache_without_the_evaluation_key_is_unknown_but_a_null_one_alerts(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(1000))] * 2)
    m.check(now, lambda: {"blocked": False, "offair": None, "error": None})      # pre-upgrade shape
    assert not [e for e in fired if e[0] == "alert"] and ("resolve", "guard-stale") not in fired
    m.check(now, lambda: {"blocked": False, "offair": False, "error": None, "guard_evaluated_at": None})
    assert [e[1] for e in fired if e[0] == "alert"] == ["guard-stale"]


def test_the_playlist_is_fetched_before_the_guard_view_is_built(fired):
    order = []
    now = E + 1000 * D

    def fetch(url):
        order.append("fetch")
        return 200, live_playlist(1000)

    def guard():
        order.append("guard")
        return _guard(now)
    DeadClockMonitor("https://radio.example.org/live.m3u8", E, 120.0, 2700.0, 17, fetch=fetch).check(now, guard)
    assert order == ["fetch", "guard"]


def test_a_failing_guard_read_cannot_stop_the_playlist_check(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(980))] * 2)
    bad = {"blocked": True, "error": "boom", "guard_evaluated_at": None, "offair": None}
    m.check(now, lambda: bad)
    assert m.guard_error_since_us == now
    m.check(now, lambda: bad)
    assert [e[1] for e in fired if e[0] == "alert"] == ["dead-clock"]


def test_a_raising_guard_view_cannot_stop_the_playlist_check(fired):
    # Any guard_view callable, not only publish.guard_view (which never raises): a raise fails closed
    # like a failed read, so the playlist check proceeds and guard-stale's timer starts.
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(980))] * 2)

    def boom():
        raise OSError("read timed out")

    m.check(now, boom)
    assert m.guard_error_since_us == now and not [e for e in fired if e[0] == "alert"]
    m.check(now, boom)
    assert [e[1] for e in fired if e[0] == "alert"] == ["dead-clock"]


def test_a_raising_guard_view_with_no_message_is_named_by_its_type(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(1000))])
    m.guard_error_since_us = now - 46 * 60_000_000          # unreadable for 46 minutes already

    def boom():
        raise TimeoutError

    m.check(now, boom)
    alerted = [e for e in fired if e[0] == "alert"]
    assert [e[1] for e in alerted] == ["guard-stale"] and "TimeoutError" in alerted[0][2]
