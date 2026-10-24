"""Hugo-side alerts (spec "Alerts and operations"). Every alert is logged at
ERROR (journald under systemd). Once `configure()` has installed a
Dispatcher -- `transmitter run` does it at start -- each alert is also sent by
email (SMTP with STARTTLS) and ntfy, deduped per code in
~/.transmitter/alerts.json: sent when a code first fires, then at most once
per `repeat_hours` while it keeps firing. `resolve(code)` marks a level
condition clear (and says so, if it had been sent) so that its next occurrence
is sent at once. Any other code is an event: it stops counting as active once
`repeat_hours` pass without a new fire, so `status` shows no stale alarms. A
failing channel is logged, never raised, and skipped for a cool-down so a dead
server cannot hold the service loop. A failed "resolved" message keeps the
level code active and the next successful step retries it; `status` can
therefore lag after a channel outage, deliberately.

The codes in `GATED_CODES` (the checks that run about every minute) are
gated: they send, first alert or repeat, only on a streak of `GATE`
consecutive failing OBSERVATIONS ("resolved" is never gated). There are two
observers, the service tick (`TICK`) and the monitor pass (`MONITOR`), each
with its own state; the caller ends each observation explicitly with
`end_observation(observer, steps that ran)`. A gated code's streak advances at
its first fire within an observation (later fires in the same observation are
counted once, and the send decision is made at that first fire, with its
message); ending an observation resets the streaks of the codes its steps
declare (`STEP_CODES`) that were not raised in it, and touches nothing else.
Below the gate a new episode is pending: nothing is sent or written, and the
code is not active. Inside an active episode a due repeat also needs the gate,
except that an episode whose first message was never delivered resends it at
once. Streaks are in-process: a restart starts them afresh. The Dispatcher
takes a lock, since the service tick and the monitor thread both call it."""

import logging
import os
import smtplib
import ssl
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from email.header import Header
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Iterable, Mapping, Protocol

from transmitter.workspace import Workspace, read_json, write_json

log = logging.getLogger("transmitter.alerts")

# Level conditions, resolved explicitly (ruling R16). Every other code is an
# event: active only until `repeat_hours` pass without a new fire.
LEVEL_CODES = frozenset({"dead-clock", "guard-stale", "station-root", "plan", "render"})

# The 3-consecutive gate (operator rule: a check that runs about every minute
# needs 3 consecutive failures before it alerts). Exactly the approved list;
# every other code sends at its first fire.
GATE = 3
GATED_CODES = frozenset({"prune", "publish", "publish-state", "station-root", "plan", "render", "dead-clock-check"})

# The observers, each with its own observation state.
TICK = "tick"
MONITOR = "monitor"

# Which gated codes each step can raise: a step that ran without raising one
# of its codes resets that code's streak.
STEP_CODES: dict[str, frozenset[str]] = {
    "plan": frozenset({"plan", "station-root"}),
    "render": frozenset({"render", "station-root"}),
    "publish": frozenset({"publish", "prune"}),
    "lead": frozenset({"publish-state"}),
    "dead-clock-check": frozenset({"dead-clock-check"}),
}
OBSERVER_STEPS: dict[str, frozenset[str]] = {
    TICK: frozenset({"plan", "render", "publish", "lead"}),
    MONITOR: frozenset({"dead-clock-check"}),
}


# After a channel fails it is skipped for this long, so a down SMTP/ntfy server
# costs the service loop one timeout per cool-down, not one per alert.
CHANNEL_COOLDOWN_S = 300.0


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _expired(code: str, entry: dict, now: float, repeat_s: float) -> bool:
    """An event code that has not fired for longer than `repeat_s`."""
    last = entry.get("last_fired_at", entry.get("first_at"))
    return code not in LEVEL_CODES and (not _is_num(last) or now - last > repeat_s)


def load_state(path: Path) -> dict | None:
    """alerts.json as a dict ({} when absent), or None when it cannot be read:
    unreadable, not JSON, or not a JSON object."""
    try:
        data = read_json(path, {})
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def active_codes(state: dict, now: float, repeat_s: float) -> list[str]:
    """The codes still alarming (what `status` lists): a level code until it is
    resolved, an event code until `repeat_s` passes without a new fire."""
    return sorted(code for code, e in state.items()
                  if isinstance(e, dict) and e.get("active") and not _expired(code, e, now, repeat_s))


class Channel(Protocol):
    name: str

    def send(self, subject: str, body: str, priority: int) -> None: ...


@dataclass
class SmtpChannel:
    host: str
    port: int
    username: str
    password: str
    sender: str
    to: str
    timeout_s: float = 20.0
    name: str = "email"

    def send(self, subject: str, body: str, priority: int) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, self.to, subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_s) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(self.username, self.password)
            smtp.send_message(msg)


@dataclass
class NtfyChannel:
    url: str
    token: str | None = None
    timeout_s: float = 10.0
    name: str = "ntfy"

    def send(self, subject: str, body: str, priority: int) -> None:
        if subject.isascii():
            title = subject
        else:                                    # ntfy decodes RFC 2047, not raw latin-1; no obs-fold
            title = Header(subject, "utf-8").encode(maxlinelen=0)
        headers = {"Title": title, "Priority": str(priority), "Tags": "warning" if priority >= 4 else "white_check_mark"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.url, data=body.encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            if resp.status >= 300:
                raise OSError(f"ntfy: HTTP {resp.status}")


@dataclass
class Dispatcher:
    path: Path                         # ~/.transmitter/alerts.json
    channels: list
    repeat_s: float
    station: str = "llama radio"
    now: Callable[[], float] = time.time
    cooldown_s: float = CHANNEL_COOLDOWN_S
    # What this process has recorded, kept beside the file: when alerts.json
    # cannot be written (disk full) the newer of the two wins, so dedupe holds
    # instead of turning into a message per tick.
    _mem: dict = field(default_factory=dict, init=False, repr=False)
    _failed: dict = field(default_factory=dict, init=False, repr=False)   # id(channel) -> failure time
    # Both the service tick and the monitor thread fire and resolve.
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    # The gate, in-process: consecutive failing observations per gated code,
    # and the gated codes already fired in each observer's current observation.
    _streak: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _fired: dict[str, set[str]] = field(default_factory=lambda: {TICK: set(), MONITOR: set()},
                                        init=False, repr=False)

    def _load(self) -> dict:
        # A corrupt or hand-edited file must not wedge alerting: start afresh.
        state = load_state(self.path)
        if state is None:
            log.warning("alerts state %s is unreadable; starting afresh", self.path)
            return {}
        return state

    def _state(self) -> dict:
        """alerts.json merged with this process's own record, the newer entry
        per code winning."""
        state = self._load()
        for code, mem in self._mem.items():
            disk = state.get(code)
            disk_at = disk.get("updated_at") if isinstance(disk, dict) else None
            if not _is_num(disk_at) or mem["updated_at"] >= disk_at:
                state[code] = dict(mem)
        return state

    def _remember(self, state: dict, code: str, entry: dict, now: float) -> None:
        entry["updated_at"] = now
        self._mem[code] = dict(entry)
        state[code] = entry

    def _send(self, subject: str, body: str, priority: int) -> bool:
        """True when at least one channel accepted the message. A channel that
        failed in the last `cooldown_s` is skipped (and counts as not having
        delivered)."""
        delivered = False
        now = self.now()
        for ch in self.channels:
            failed_at = self._failed.get(id(ch))
            if failed_at is not None and now - failed_at < self.cooldown_s:
                continue
            try:
                ch.send(subject, body, priority)
                delivered = True
                self._failed.pop(id(ch), None)
            except Exception as exc:              # never let alerting break the service
                self._failed[id(ch)] = now
                log.warning("alert channel %s failed: %s", ch.name, exc)
        return delivered

    def fire(self, code: str, message: str) -> None:
        with self._lock:
            self._fire(code, message)

    def _fire(self, code: str, message: str) -> None:
        gated = code in GATED_CODES
        gate_ok = True
        if gated:
            observer = MONITOR if code in STEP_CODES["dead-clock-check"] else TICK
            if code in self._fired[observer]:
                return                  # counted once per observation; alert() already logged it
            self._fired[observer].add(code)
            self._streak[code] = self._streak.get(code, 0) + 1
            gate_ok = self._streak[code] >= GATE
        state = self._state()
        now = self.now()
        entry = state.get(code)
        if not isinstance(entry, dict):
            entry = {"active": False, "first_at": now, "last_sent_at": None, "count": 0}
        if not _is_num(entry.get("last_sent_at")):
            entry["last_sent_at"] = None
        if not entry.get("active") or _expired(code, entry, now, self.repeat_s):
            if not gate_ok:
                return                  # pending: nothing written, not active
            entry.update(active=True, first_at=now, last_sent_at=None, count=0)
        count = entry.get("count")
        entry["count"] = (count if isinstance(count, int) and not isinstance(count, bool) else 0) + 1
        entry["last_fired_at"] = now
        last = entry.get("last_sent_at")
        # A due repeat of a gated code needs the gate too; an episode whose
        # first message was never delivered resends it at once, never re-gated.
        due = last is None or (now - last >= self.repeat_s and gate_ok)
        if self.channels and due:
            suppressed = entry["count"] - 1
            since = "the last message" if last is not None else "the first"
            body = message + (f"\n\n({suppressed} more since {since})" if suppressed else "")
            if gated and last is None:
                body += f"\n\n(alerted after {GATE} consecutive failures)"
            if self._send(f"{self.station}: {code}", body, 4):
                entry["last_sent_at"], entry["count"] = now, 0
        self._remember(state, code, entry, now)
        write_json(self.path, state)

    def end_observation(self, observer: str, steps: Iterable[str]) -> None:
        """End `observer`'s current observation: each gated code declared by a
        step that ran and not raised in this observation has its streak reset;
        codes raised in it keep theirs; no other code is touched."""
        with self._lock:
            allowed = OBSERVER_STEPS.get(observer)
            if allowed is None:
                raise ValueError(f"unknown alert observer {observer!r}")
            steps = list(steps)
            foreign = [s for s in steps if s not in allowed]
            if foreign:
                raise ValueError(f"step(s) {foreign} do not belong to observer {observer!r}")
            codes = frozenset().union(*(STEP_CODES[s] for s in steps))
            for c in codes - self._fired[observer]:
                self._streak[c] = 0
            self._fired[observer].clear()

    def resolve(self, code: str) -> None:
        with self._lock:
            self._resolve(code)

    def _resolve(self, code: str) -> None:
        state = self._state()
        entry = state.get(code)
        if not isinstance(entry, dict) or not entry.get("active"):
            return
        if entry.get("last_sent_at") is not None and self.channels:
            # Deliberate, do not "fix" back: unless some channel took the
            # "resolved" message the level code stays active and the next
            # successful step retries it, so `status` can show a cleared code
            # as active for as long as a channel outage (and the fill) lasts.
            if not self._send(f"{self.station}: resolved: {code}", f"{code} has cleared.", 3):
                return
        entry["active"] = False
        self._remember(state, code, entry, self.now())
        write_json(self.path, state)

    def active(self) -> list[str]:
        with self._lock:
            return active_codes(self._state(), self.now(), self.repeat_s)


_dispatcher: Dispatcher | None = None


def configure(dispatcher: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = dispatcher


def alert(code: str, message: str) -> None:
    log.error("ALERT %s: %s", code, message)
    if _dispatcher is not None:
        try:
            _dispatcher.fire(code, message)
        except Exception:
            log.warning("alert dispatch failed for %s", code, exc_info=True)


def resolve(code: str) -> None:
    if _dispatcher is not None:
        try:
            _dispatcher.resolve(code)
        except Exception:
            log.warning("alert resolve failed for %s", code, exc_info=True)


def end_observation(observer: str, steps: Iterable[str]) -> None:
    """End an observation of the gated codes (see the module docstring); a
    no-op without a dispatcher, and never raises."""
    if _dispatcher is not None:
        try:
            _dispatcher.end_observation(observer, steps)
        except Exception:
            log.warning("alert end_observation failed for %s", observer, exc_info=True)


def dispatcher_from_config(cfg, ws: Workspace, env: Mapping[str, str] = os.environ) -> Dispatcher:
    """Channels from `[alerts]` and the environment (SMTP_USERNAME,
    SMTP_PASSWORD, NTFY_TOKEN). A half-configured channel is skipped with a
    warning; with no channel the dispatcher only dedupes the log."""
    a = cfg.alerts
    channels: list = []
    if a.email_to:
        user, password = env.get("SMTP_USERNAME"), env.get("SMTP_PASSWORD")
        if user and password:
            channels.append(SmtpChannel(a.smtp_host, a.smtp_port, user, password, a.email_from or user, a.email_to))
        else:
            log.warning("[alerts] email_to is set but SMTP_USERNAME/SMTP_PASSWORD are not: email alerts are off")
    if a.ntfy_url:
        channels.append(NtfyChannel(a.ntfy_url, env.get("NTFY_TOKEN") or None))
    if not channels:
        log.warning("no alert channel configured ([alerts] in config.toml): alerts go to the log only")
    return Dispatcher(ws.alerts_path, channels, a.repeat_hours * 3600, cfg.antenna.station_name)
