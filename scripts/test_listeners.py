import datetime as dt

from listeners import own_agent, summarize, windows


def row(bucket, ip, ua, count):
    return {"count": count, "dimensions": {"datetimeHour": bucket, "clientIP": ip, "userAgent": ua}}


def test_own_checks_are_excluded():
    assert own_agent("transmitter-dead-clock-check")
    assert own_agent("metronome-verification-poller")
    assert own_agent("lma-radio-capture-poller")
    assert not own_agent("Mozilla/5.0")
    assert not own_agent(None)


def test_summarize_estimates_concurrency_and_counts_peers():
    rows = [
        row("2026-11-04T01:00:00Z", "1.1.1.1", "Mozilla", 352),  # one listener all hour
        row("2026-11-04T01:00:00Z", "2.2.2.2", "VLC", 176),       # one for half an hour
        row("2026-11-04T01:00:00Z", "3.3.3.3", "transmitter-dead-clock-check", 60),
        row("2026-11-04T00:00:00Z", "1.1.1.1", "Mozilla", 10),
    ]
    out = summarize(rows, "datetimeHour", 3600, segment_seconds=3600 / 352)
    assert [r[0] for r in out] == ["2026-11-04T00:00:00Z", "2026-11-04T01:00:00Z"]
    b, n, est, peers = out[1]
    assert (n, peers) == (528, 2)
    assert est == 1.5


def test_windows_cover_the_range_without_gaps():
    s = dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc)
    w = list(windows(s, s + dt.timedelta(hours=13), hours=6))
    assert w[0][0] == s and w[-1][1] == s + dt.timedelta(hours=13)
    assert all(a[1] == b[0] for a, b in zip(w, w[1:]))
    assert len(w) == 3


def test_label_utc_passthrough_and_local_conversion(monkeypatch):
    import time
    from listeners import label
    assert label("2026-11-06T14:00:00Z", utc=True) == "2026-11-06T14:00:00Z"
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        assert label("2026-11-06T14:00:00Z") == "2026-11-06 09:00 EST"
        assert label("2026-07-06T14:00:00Z") == "2026-07-06 10:00 EDT"
    finally:
        monkeypatch.undo()
        time.tzset()
