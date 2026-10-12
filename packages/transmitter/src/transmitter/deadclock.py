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
