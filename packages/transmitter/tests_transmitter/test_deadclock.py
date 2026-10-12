import io
import urllib.request

import pytest

from transmitter import alerts, grid
from transmitter import deadclock
from transmitter.deadclock import DeadClockMonitor, playlist_age_s

E = grid.iso_to_us("2026-10-10T12:00:00Z")
D = grid.D_US


def live_playlist(cur: int) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:11", f"#EXT-X-MEDIA-SEQUENCE:{cur - 5}",
             "#EXT-X-DISCONTINUITY-SEQUENCE:0"]
    for n in range(cur - 5, cur + 1):
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
    m.check(now, _guard(now))
    m.check(now, _guard(now))           # 20 intervals old: genuinely stale, but only once
    m.check(now, _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    assert ("resolve", "dead-clock") in fired and ("resolve", "guard-stale") in fired


def test_two_stale_reads_in_a_row_alert(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(985))] * 2)
    m.check(now, _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    m.check(now, _guard(now))
    assert [e[1] for e in fired if e[0] == "alert"] == ["dead-clock"]


def test_a_403_is_expected_while_blocked_and_alarms_only_once_the_guard_cache_has_caught_up(fired):
    now = E + 1000 * D
    m = _monitor([(403, "")] * 18)
    m.check(now, _guard(now, offair=True))
    assert not [e for e in fired if e[0] == "alert"]
    for _ in range(16):                     # the cache may say "not blocked" for guard_check_minutes after `offair on`
        m.check(now, _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    m.check(now, _guard(now))
    alerted = [e for e in fired if e[0] == "alert"]
    assert alerted[0][1] == "dead-clock" and "kill switch" in alerted[0][2]


def test_network_errors_alert_only_when_they_persist(fired):
    now = E + 1000 * D
    m = _monitor([(0, "")] * 9 + [(200, live_playlist(1000))] + [(0, "")] * 10)
    for _ in range(10):
        m.check(now, _guard(now))
    assert not [e for e in fired if e[0] == "alert"]
    for _ in range(10):
        m.check(now, _guard(now))
    assert [e[1] for e in fired if e[0] == "alert"] == ["dead-clock"]


def test_a_stale_guard_alerts(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(1000))] * 2)
    m.check(now, _guard(now, minutes_ago=46))
    assert [e[1] for e in fired if e[0] == "alert"] == ["guard-stale"]
    fired.clear()
    m.check(now, {**FRESH_GUARD})                     # guard.json read fine but carries no evaluation
    assert [e[1] for e in fired if e[0] == "alert"] == ["guard-stale"]


def test_stale_fresh_stale_fresh_never_alerts(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(980)), (200, live_playlist(1000))] * 2)
    for _ in range(4):
        m.check(now, _guard(now))
    assert not [e for e in fired if e[0] == "alert"]


def test_403_while_the_guard_says_blocked_never_alerts_even_past_the_threshold(fired):
    now = E + 1000 * D
    m = _monitor([(403, "")] * 20)
    for _ in range(20):
        m.check(now, _guard(now, blocked=True, offair=False))
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
    m.check(now, _guard(now))
    assert not [e for e in fired if e[0] == "alert"]


def test_an_unreadable_guard_alerts_once_it_has_persisted_and_recovers(fired):
    now = E + 1000 * D
    m = DeadClockMonitor("https://radio.example.org/live.m3u8", E, 120.0, 2700.0, 17,
                         fetch=lambda url: (200, live_playlist(1000 + (m_clock[0] - now) // D)))
    m_clock = [now]
    bad = {"blocked": True, "offair": None, "error": "AccessDenied", "guard_evaluated_at": None}
    m.check(now, bad)
    m_clock[0] = now + 44 * 60_000_000
    m.check(m_clock[0], bad)
    assert not [e for e in fired if e[0] == "alert"]
    m_clock[0] = now + 45 * 60_000_000
    m.check(m_clock[0], bad)
    alerted = [e for e in fired if e[0] == "alert"]
    assert [e[1] for e in alerted] == ["guard-stale"] and "AccessDenied" in alerted[0][2]
    fired.clear()
    later = m_clock[0] = now + 46 * 60_000_000
    m.check(later, _guard(later))
    assert ("resolve", "guard-stale") in fired and m.guard_error_since_us is None
    m.check(later, bad)                              # a new failure restarts the timer
    assert m.guard_error_since_us == later and not [e for e in fired if e[0] == "alert"]


def test_a_cache_without_the_evaluation_key_is_unknown_but_a_null_one_alerts(fired):
    now = E + 1000 * D
    m = _monitor([(200, live_playlist(1000))] * 2)
    m.check(now, {"blocked": False, "offair": None, "error": None})      # pre-upgrade shape
    assert not [e for e in fired if e[0] == "alert"] and ("resolve", "guard-stale") not in fired
    m.check(now, {"blocked": False, "offair": False, "error": None, "guard_evaluated_at": None})
    assert [e[1] for e in fired if e[0] == "alert"] == ["guard-stale"]
