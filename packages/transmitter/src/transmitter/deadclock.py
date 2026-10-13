"""The dead-clock check (spec "Alerts and operations"). If the antenna clock
stops, live.m3u8 goes stale, players stall and the cloud side fails toward
zero cost -- but silently, so `transmitter run` watches it: once a minute it
fetches the public live.m3u8 (a cache hit: the edge refetches it from R2 at
most every 5 s, whoever asks) and alerts when its newest segment is older than
`dead_clock_seconds` on two checks in a row (the measured cron lag reaches
~117 s, so one stale read is not a death). A live playlist lists
PLAYLIST_LOOKAHEAD segments past the one airing, so its newest segment starts
in the future; it is dated instead by its newest PROGRAM-DATE-TIME minus its
own hold-back (#EXT-X-START:TIME-OFFSET, else #EXT-X-SERVER-CONTROL:HOLD-BACK),
which the antenna deploys equal to the lookahead (wrangler.jsonc, pinned by
antenna's test/wrangler-config.test.ts). An off-air playlist has no
PROGRAM-DATE-TIME; its MEDIA-SEQUENCE (a grid index the clock computes per
invocation, lookahead + 1 past the write) dates it instead, less the hold-back
last seen on a live playlist. A 403 is the kill switch: expected while the
guard says blocked, alarming otherwise -- but only after `forbidden_checks`
checks, because the guard cache that says "blocked" can be one
guard_check_minutes late. It also alerts when state/guard.json's last
evaluation is older than `guard_stale_minutes` (the guard evaluates every 15)."""

import http.client
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from transmitter import alerts, grid

PROGRAM_DATE_TIME = "#EXT-X-PROGRAM-DATE-TIME:"
MEDIA_SEQUENCE = "#EXT-X-MEDIA-SEQUENCE:"
START = "#EXT-X-START:"
SERVER_CONTROL = "#EXT-X-SERVER-CONTROL:"
STALE_CHECKS = 2           # consecutive stale reads before alerting
TROUBLE_CHECKS = 10        # consecutive unreachable reads before alerting


def _attribute(line: str, tag: str, name: str) -> float | None:
    """A decimal attribute of a playlist tag line, or None when absent or malformed."""
    for attr in line[len(tag):].split(","):
        key, _, value = attr.partition("=")
        if key.strip() == name:
            try:
                x = float(value.strip())
            except ValueError:
                return None
            return x if math.isfinite(x) else None
    return None


def playlist_hold_back_s(text: str) -> float:
    """Where the playlist tells players to start, in seconds before its listed
    end: EXT-X-START's negative TIME-OFFSET, else SERVER-CONTROL's HOLD-BACK,
    else 0 (none, or malformed: dated by the newest segment as in phase 1)."""
    hold_back = 0.0
    for line in text.splitlines():
        if line.startswith(START):
            offset = _attribute(line, START, "TIME-OFFSET")
            if offset is not None and offset < 0:
                return -offset
        elif line.startswith(SERVER_CONTROL):
            value = _attribute(line, SERVER_CONTROL, "HOLD-BACK")
            if value is not None and value > 0:
                hold_back = value
    return hold_back


def playlist_age_s(text: str, now_us: int, epoch_us: int, live_hold_back_s: float = 0.0) -> float | None:
    """Seconds since the playlist was written, or None if it names no segment.

    Live: since its newest segment started, less its own hold-back -- with
    hold-back = lookahead, that is the segment airing when it was written, so
    a dead clock is noticed as soon as without a lookahead. Off-air: since its
    MEDIA-SEQUENCE started, less `live_hold_back_s` (the hold-back last seen live):
    the clock numbers the notice lookahead + 1 past its write, so this
    under-reads by at least one segment and never false-alarms."""
    dates = [line[len(PROGRAM_DATE_TIME):].strip() for line in text.splitlines()
             if line.startswith(PROGRAM_DATE_TIME)]
    if dates:
        try:
            newest_us = max(grid.iso_to_us(d) for d in dates)
        except ValueError:
            return None
        return (now_us - newest_us) / 1e6 + playlist_hold_back_s(text)
    for line in text.splitlines():
        if line.startswith(MEDIA_SEQUENCE):
            try:
                n = int(line[len(MEDIA_SEQUENCE):].strip())
            except ValueError:
                return None
            return (now_us - grid.segment_start_us(epoch_us, n)) / 1e6 + live_hold_back_s
    return None


def fetch_text(url: str, timeout_s: float = 10.0) -> tuple[int, str]:
    """(HTTP status, body); status 0 = no response (network error)."""
    req = urllib.request.Request(url, headers={"User-Agent": "transmitter-dead-clock-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status, resp.read(1 << 20).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError):
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
    # NOTE: stale/unreachable/forbidden count CONSECUTIVE bad checks and reset
    # only on a good read (a fresh 200, or an expected 403) -- intended: a
    # different kind of bad read must not hide a persisting outage.
    guard_error_since_us: int | None = None
    # The hold-back of the last live playlist read, which dates an off-air one
    # (it carries none). 0 until a live read: after a restart while off-air the
    # check is late by up to the lookahead, never early.
    live_hold_back_s: float = 0.0

    def check(self, now_us: int, guard_cache: dict | None) -> None:
        blocked = bool(guard_cache and (guard_cache.get("blocked") or guard_cache.get("offair")))
        status, text = self.fetch(self.url)
        if status == 200:
            self.unreachable = self.forbidden = 0
            if PROGRAM_DATE_TIME in text:
                self.live_hold_back_s = playlist_hold_back_s(text)
            age = playlist_age_s(text, now_us, self.epoch_us, self.live_hold_back_s)
            if age is None or age > self.dead_clock_s:
                self.stale += 1
                if self.stale >= STALE_CHECKS:
                    alerts.alert("dead-clock", f"{self.url} is stale ("
                                 + ("no segment in it" if age is None else f"newest segment {age:.0f} s old")
                                 + "): the antenna clock may have stopped or be writing nothing (Workers dashboard, wrangler tail)")
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
        if not guard_cache:
            return
        error = guard_cache.get("error")
        if error is not None:
            # guard.json unreadable: the cache fails closed and carries no
            # evaluation time, so time how long the read has been failing.
            if self.guard_error_since_us is None:
                self.guard_error_since_us = now_us
            if (now_us - self.guard_error_since_us) / 1e6 >= self.guard_stale_s:
                alerts.alert("guard-stale", f"state/guard.json has been unreadable for "
                                            f"{(now_us - self.guard_error_since_us) / 60e6:.0f} minutes: {error}")
            return
        self.guard_error_since_us = None
        if "guard_evaluated_at" not in guard_cache:
            return                                   # a pre-upgrade cache: unknown, say nothing
        at = guard_cache["guard_evaluated_at"]
        try:
            age_s = (now_us - grid.iso_to_us(at)) / 1e6 if at else None
        except ValueError:
            age_s = None
        if age_s is None:
            alerts.alert("guard-stale", "state/guard.json has no evaluation time: is the antenna clock deployed?")
        elif age_s > self.guard_stale_s:
            alerts.alert("guard-stale", f"the cost guard last evaluated {age_s / 60:.0f} minutes ago (at {at}); "
                                        "it should every 15: the antenna clock may have stopped")
        else:
            alerts.resolve("guard-stale")
