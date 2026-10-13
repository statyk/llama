### Task 14: Dead-clock and guard-stale monitor

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/deadclock.py`, `packages/transmitter/tests_transmitter/test_deadclock.py`
- Modify: `publish.py` (`guard_blocks_publishing` caches `guard_evaluated_at` and `offair`), `service.py` (`open_monitor`, `Runner(monitor=…)`), `cli.py` (`run`)
- Modify (tests): `test_publish.py` (one assertion), `test_service.py` (append)

**Interfaces:**
- Consumes: `alerts.alert`/`alerts.resolve` (Task 13); `AlertsConfig.dead_clock_seconds`/`guard_stale_minutes` (Task 13); `[antenna] site_url`; `[publish] guard_check_minutes`.
- Produces:
  - `deadclock`: `playlist_age_s(text, now_us, epoch_us) -> float | None`, `fetch_text(url, timeout_s=10) -> (status, body)` (status 0 = no response), and `@dataclass DeadClockMonitor(url, epoch_us, dead_clock_s, guard_stale_s, forbidden_checks=17, fetch=fetch_text)` with `check(now_us, guard_cache)`. It uses the alert codes `dead-clock` and `guard-stale`.
  - `publish.OFFAIR_KEY`. `guard-cache.json` gains `guard_evaluated_at` and `offair`. These are informational: publishing is still gated on `tripped` only.
  - `service.open_monitor(st) -> DeadClockMonitor | None` and `Runner(..., monitor=None)`. The tick runs the step `dead-clock` after `publish`, passing `read_json(ws.guard_cache_path)`.

Rules (ruling R4):
- **Stale:** 120 s on two consecutive checks.
- **Off-air:** an off-air playlist (no PROGRAM-DATE-TIME) is dated by its MEDIA-SEQUENCE.
- **403:** expected while the guard cache says blocked or off the air; otherwise an alert after `guard_check_minutes + 2` consecutive checks (17). The cache is refreshed only every `guard_check_minutes`, so after `offair on` or a trip it can say "not blocked" for that long, and a shorter threshold would alarm then.
- **Unreachable:** network errors alert after 10 consecutive minutes.
- **Guard stale:** `guard_evaluated_at` older than `guard_stale_minutes` (45; or a readable `guard.json` with none) alerts `guard-stale`.

The fetch hits the public `live.m3u8`: a cache hit (measured 2026-10-12, A5), never billed per request; the edge refetches it from R2 at most every 5 s, whoever asks.

- [ ] **Step 1: Write the failing tests**

`packages/transmitter/tests_transmitter/test_deadclock.py`:

```python
import logging

import pytest

from transmitter import alerts, grid
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
    m = _monitor([(200, live_playlist(1000)), (200, live_playlist(990)), (200, live_playlist(1000))])
    m.check(now, _guard(now))
    m.check(now, _guard(now))           # 102 s old... still under 120 s
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
```

Append to `tests_transmitter/test_service.py`:

```python
def test_the_runner_runs_the_dead_clock_check_every_tick_with_the_guard_cache(tmp_path):
    st, _ = make_station(tmp_path)
    calls = []

    class Monitor:
        def check(self, now_us, guard_cache):
            calls.append((now_us, guard_cache))

    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None, monitor=Monitor())
    runner.tick(NOW)
    runner.tick(NOW + 60_000_000)
    assert [c[0] for c in calls] == [NOW, NOW + 60_000_000]
    assert calls[0][1]["blocked"] is False and calls[0][1]["offair"] is False   # written by publish's guard read


def test_open_monitor_needs_site_url(tmp_path):
    st, _ = make_station(tmp_path)
    assert service.open_monitor(st) is None
    st.cfg.antenna.site_url = "https://radio.example.org/"
    m = service.open_monitor(st)
    assert m.url == "https://radio.example.org/live.m3u8" and m.dead_clock_s == 120.0 and m.guard_stale_s == 2700.0
    assert m.forbidden_checks == 17                     # guard_check_minutes 15 + 2
```

In `tests_transmitter/test_publish.py` `test_tripped_guard_stops_publishing_and_is_read_at_most_every_15_minutes`, the guard read now also reads the flag. Change `assert bucket.log == [("get", "state/guard.json")]` to `assert bucket.log == [("get", "state/guard.json"), ("get", "state/offair.json")]`.

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_deadclock.py packages/transmitter/tests_transmitter/test_service.py packages/transmitter/tests_transmitter/test_publish.py -q`
Expected: FAIL. `No module named 'transmitter.deadclock'`; `Runner` has no `monitor` parameter.

- [ ] **Step 3: Implement**

`packages/transmitter/src/transmitter/deadclock.py`:

```python
"""The dead-clock check (spec "Alerts and operations"). If the antenna clock
stops, live.m3u8 goes stale, players stall and the cloud side fails toward
zero cost -- but silently, so `transmitter run` watches it: once a minute it
fetches the public live.m3u8 (a cache hit: the edge refetches it from R2 at
most every 5 s, whoever asks) and alerts when its newest segment is older than
`dead_clock_seconds` on two checks in a row (the measured cron lag reaches
~60 s, so one stale read is not a death). An off-air playlist has no
PROGRAM-DATE-TIME; its MEDIA-SEQUENCE (a grid index the clock computes per
invocation) dates it instead. A 403 is the kill switch: expected while the
guard says blocked, alarming otherwise -- but only after `forbidden_checks`
checks, because the guard cache that says "blocked" can be one
guard_check_minutes late. It also alerts when state/guard.json's last
evaluation is older than `guard_stale_minutes` (the guard evaluates every 15)."""

import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from transmitter import alerts, grid

PROGRAM_DATE_TIME = "#EXT-X-PROGRAM-DATE-TIME:"
MEDIA_SEQUENCE = "#EXT-X-MEDIA-SEQUENCE:"
STALE_CHECKS = 2           # consecutive stale reads before alerting
TROUBLE_CHECKS = 10        # consecutive unreachable reads before alerting


def playlist_age_s(text: str, now_us: int, epoch_us: int) -> float | None:
    """Seconds since the playlist's newest segment started, or None if it names none."""
    dates = [line[len(PROGRAM_DATE_TIME):].strip() for line in text.splitlines()
             if line.startswith(PROGRAM_DATE_TIME)]
    if dates:
        try:
            return (now_us - max(grid.iso_to_us(d) for d in dates)) / 1e6
        except ValueError:
            return None
    for line in text.splitlines():
        if line.startswith(MEDIA_SEQUENCE):
            try:
                n = int(line[len(MEDIA_SEQUENCE):].strip())
            except ValueError:
                return None
            return (now_us - grid.segment_start_us(epoch_us, n)) / 1e6
    return None


def fetch_text(url: str, timeout_s: float = 10.0) -> tuple[int, str]:
    """(HTTP status, body); status 0 = no response (network error)."""
    req = urllib.request.Request(url, headers={"User-Agent": "transmitter-dead-clock-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, OSError):
        return 0, ""


@dataclass
class DeadClockMonitor:
    url: str                       # https://<host>/live.m3u8
    epoch_us: int
    dead_clock_s: float
    guard_stale_s: float
    forbidden_checks: int = 17     # unexpected 403s before alerting: guard_check_minutes + 2
    fetch: Callable[[str], tuple[int, str]] = fetch_text
    stale: int = 0
    unreachable: int = 0
    forbidden: int = 0

    def check(self, now_us: int, guard_cache: dict | None) -> None:
        blocked = bool(guard_cache and (guard_cache.get("blocked") or guard_cache.get("offair")))
        status, text = self.fetch(self.url)
        if status == 200:
            self.unreachable = self.forbidden = 0
            age = playlist_age_s(text, now_us, self.epoch_us)
            if age is None or age > self.dead_clock_s:
                self.stale += 1
                if self.stale >= STALE_CHECKS:
                    alerts.alert("dead-clock", f"{self.url} is stale ("
                                 + ("no segment in it" if age is None else f"newest segment {age:.0f} s old")
                                 + "): the antenna clock Worker may have stopped (Workers dashboard, wrangler tail)")
            else:
                self.stale = 0
                alerts.resolve("dead-clock")
        elif status == 403 and blocked:
            self.stale = self.unreachable = self.forbidden = 0
            alerts.resolve("dead-clock")
        elif status == 403:
            # The guard cache is refreshed only every guard_check_minutes, so a
            # fresh `offair on` or trip reads "not blocked" here for that long.
            self.forbidden += 1
            if self.forbidden >= self.forbidden_checks:
                alerts.alert("dead-clock", f"{self.url} answers 403 although the guard says the station is not "
                                           f"blocked (kill switch left on?) for {self.forbidden} minutes")
        else:
            self.unreachable += 1
            if self.unreachable >= TROUBLE_CHECKS:
                alerts.alert("dead-clock", f"{self.url} cannot be fetched (status {status or 'none'}) "
                                           f"for {self.unreachable} minutes")
        self._check_guard(now_us, guard_cache)

    def _check_guard(self, now_us: int, guard_cache: dict | None) -> None:
        at = (guard_cache or {}).get("guard_evaluated_at")
        try:
            age_s = (now_us - grid.iso_to_us(at)) / 1e6 if at else None
        except ValueError:
            age_s = None
        if age_s is None:
            if guard_cache and guard_cache.get("error") is None:
                alerts.alert("guard-stale", "state/guard.json has no evaluation time: is the antenna clock deployed?")
        elif age_s > self.guard_stale_s:
            alerts.alert("guard-stale", f"the cost guard last evaluated {age_s / 60:.0f} minutes ago (at {at}); "
                                        "it should every 15: the antenna clock may have stopped")
        else:
            alerts.resolve("guard-stale")
```

`publish.py`: add `OFFAIR_KEY = "state/offair.json"` after `GUARD_KEY`. In `guard_blocks_publishing`, replace:

```python
    try:
        doc = uploader.get_json(GUARD_KEY)
        blocked, error = bool(doc and doc.get("tripped")), None
    except Exception as exc:                        # cannot see the guard: do not spend
        blocked, error = True, str(exc)
    write_json(ws.guard_cache_path, {"checked_at": now_s, "blocked": blocked, "error": error})
    return blocked
```

with:

```python
    evaluated_at = offair = None
    try:
        doc = uploader.get_json(GUARD_KEY)
        blocked, error = bool(doc and doc.get("tripped")), None
        evaluated_at = doc.get("evaluated_at") if doc else None
    except Exception as exc:                        # cannot see the guard: do not spend
        blocked, error = True, str(exc)
    try:                                            # for the dead-clock check only: never gates publishing
        flag = uploader.get_json(OFFAIR_KEY)
        offair = bool(flag and flag.get("offair") is True)
    except Exception:
        offair = None
    write_json(ws.guard_cache_path, {"checked_at": now_s, "blocked": blocked, "error": error,
                                     "guard_evaluated_at": evaluated_at, "offair": offair})
    return blocked
```

`service.py`, five edits:

1. Add `import math` and `from transmitter.deadclock import DeadClockMonitor`.
2. Extend the workspace import with `read_json`.
3. Add before `class Runner`:

```python
def open_monitor(st: pipeline.Station) -> DeadClockMonitor | None:
    """The dead-clock check, when [antenna] site_url says where live.m3u8 is."""
    url = st.cfg.antenna.site_url
    if not url:
        log.warning("[antenna] site_url is not set: the dead-clock check is off")
        return None
    a = st.cfg.alerts
    # An unexpected 403 must outlast the guard cache (refreshed every
    # guard_check_minutes) before it alarms.
    return DeadClockMonitor(url.rstrip("/") + "/live.m3u8", st.epoch.epoch_us, a.dead_clock_seconds,
                            a.guard_stale_minutes * 60, math.ceil(st.cfg.publish.guard_check_minutes) + 2)
```

4. `Runner.__init__` gains the parameter:

```python
    def __init__(self, st: pipeline.Station, p: publish.Publisher, *, clock: Callable[[], int] = now_us,
                 sleep: Callable[[float], None] = time.sleep, tick_s: float = 60.0,
                 monitor: DeadClockMonitor | None = None):
        self.st, self.p, self.clock, self.sleep, self.tick_s = st, p, clock, sleep, tick_s
        self.monitor = monitor
```

5. In `tick`, after `self._step("publish", lambda: publish_all(self.p, t_us, self.held))`:

```python
        if self.monitor is not None:
            monitor = self.monitor
            self._step("dead-clock", lambda: monitor.check(t_us, read_json(self.st.ws.guard_cache_path)))
```

`cli.py` `run`: `service.Runner(st, service.open_publisher(st), monitor=service.open_monitor(st)).run(max_ticks=1 if once else None)`.

- [ ] **Step 4: Run the transmitter suite on both Pythons**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): dead-clock check on the public live.m3u8 and a stale-guard alert"
```

---

