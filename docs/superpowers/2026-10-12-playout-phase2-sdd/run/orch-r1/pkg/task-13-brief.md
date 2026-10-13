### Task 13: hugo alerts — SMTP + ntfy, dedupe

**Model hint:** sonnet

**Files:**
- Modify: `packages/transmitter/src/transmitter/alerts.py` (replace the whole file), `config.py` (`[alerts]`), `workspace.py` (`alerts_path`), `service.py` (`_step`), `cli.py` (`run`)
- Create: `packages/transmitter/tests_transmitter/test_alerts.py`
- Modify (tests): `test_config.py` (append), `test_service.py` (two assertions)

**Interfaces:**
- Consumes: `TransmitterConfig`, `Workspace`.
- Produces:
  - `alerts`:
    - `alert(code, message)` keeps its signature and every call site;
    - `resolve(code)`, `configure(dispatcher | None)`, `dispatcher_from_config(cfg, ws, env=os.environ)`;
    - classes `Dispatcher(path, channels, repeat_s, station="llama radio", now=time.time)` with `fire`, `resolve` and `active() -> list[str]`; `SmtpChannel(host, port, username, password, sender, to)`; `NtfyChannel(url, token=None)`;
    - `LEVEL_CODES` (the codes R16 resolves explicitly) and `active_codes(state, now, repeat_s) -> list[str]`: a level code is active until it is resolved, any other (event) code until `repeat_s` passes without a new fire. `Dispatcher.active()` and `status` (Task 16) both use it.
  - `config.AlertsConfig`: `email_to`, `email_from`, `smtp_host = "smtp.gmail.com"`, `smtp_port = 587`, `ntfy_url`, `repeat_hours = 6.0`, `dead_clock_seconds = 120.0` (ge 31), `guard_stale_minutes = 45.0`. `TransmitterConfig.alerts`, and a `TransmitterConfig` validator: `guard_stale_minutes` ≥ `[publish] guard_check_minutes + 16` (ruling R4).
  - `Workspace.alerts_path` (`<root>/alerts.json`).
  - `Runner._step(name, fn, *, resolves=())`. A `StationRootError` in any step alerts under the code `station-root`. A successful plan step resolves `plan` and `station-root`; a successful render step resolves `render`.

Secrets come from the env file: `SMTP_USERNAME`, `SMTP_PASSWORD` (a Gmail App Password) and `NTFY_TOKEN`. Dedupe follows ruling R16. Without channels the dispatcher only logs. Only `transmitter run` configures the dispatcher, so manual commands keep logging only.

- [ ] **Step 1: Write the failing tests**

`packages/transmitter/tests_transmitter/test_alerts.py`:

```python
import logging

import pytest

from transmitter import alerts
from transmitter.alerts import Dispatcher, NtfyChannel, SmtpChannel, dispatcher_from_config
from transmitter.config import TransmitterConfig
from transmitter.workspace import Workspace, read_json

H = 3600.0


class Recorder:
    name = "rec"

    def __init__(self, fail: bool = False):
        self.sent: list[tuple[str, str, int]] = []
        self.fail = fail

    def send(self, subject, body, priority):
        if self.fail:
            raise OSError("down")
        self.sent.append((subject, body, priority))


@pytest.fixture(autouse=True)
def _unconfigure():
    yield
    alerts.configure(None)


def _dispatcher(tmp_path, *channels, now=None):
    clock = {"t": 1000.0}
    d = Dispatcher(tmp_path / "alerts.json", list(channels), 6 * H, "llama radio", now=lambda: clock["t"])
    return d, clock


def test_unconfigured_alerts_only_log(caplog):
    with caplog.at_level(logging.ERROR, logger="transmitter.alerts"):
        alerts.alert("render", "boom")
    assert "ALERT render: boom" in caplog.text


def test_first_occurrence_is_sent_then_deduped_until_the_repeat_window(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.alert("publish", "PUT failed")
    clock["t"] += 60
    alerts.alert("publish", "PUT failed again")
    assert [s[0] for s in rec.sent] == ["llama radio: publish"]
    clock["t"] += 6 * H
    alerts.alert("publish", "still failing")
    assert len(rec.sent) == 2
    assert "(1 more since the last message)" in rec.sent[1][1]
    assert read_json(tmp_path / "alerts.json")["publish"]["active"] is True


def test_resolve_says_so_and_rearms_the_code(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.alert("dead-clock", "stale")
    alerts.resolve("dead-clock")
    assert rec.sent[-1][0] == "llama radio: resolved: dead-clock" and rec.sent[-1][2] == 3
    clock["t"] += 60
    alerts.alert("dead-clock", "stale again")                 # sent at once, not after 6 h
    assert [s[0] for s in rec.sent].count("llama radio: dead-clock") == 2
    alerts.resolve("never-fired")                             # a no-op
    assert d.active() == ["dead-clock"]


def test_an_event_code_stops_counting_as_active_after_the_repeat_window(tmp_path):
    rec = Recorder()
    d, clock = _dispatcher(tmp_path, rec)
    alerts.configure(d)
    alerts.alert("publish", "PUT failed")
    alerts.alert("dead-clock", "stale")
    assert d.active() == ["dead-clock", "publish"]
    clock["t"] += 6 * H + 1
    assert d.active() == ["dead-clock"]                       # a level code stays until resolved
    alerts.alert("publish", "PUT failed again")               # a new occurrence: sent at once
    assert d.active() == ["dead-clock", "publish"] and len(rec.sent) == 3


def test_a_failing_channel_never_raises_and_the_next_occurrence_retries(tmp_path, caplog):
    broken, ok = Recorder(fail=True), Recorder()
    d, clock = _dispatcher(tmp_path, broken)
    alerts.configure(d)
    with caplog.at_level(logging.WARNING, logger="transmitter.alerts"):
        alerts.alert("render", "x")
    assert "alert channel rec failed" in caplog.text
    d.channels = [broken, ok]
    clock["t"] += 60
    alerts.alert("render", "x")
    assert len(ok.sent) == 1


def test_dispatcher_from_config_builds_the_configured_channels(tmp_path, caplog):
    cfg = TransmitterConfig(root=tmp_path, alerts={"email_to": "ops@example.com", "ntfy_url": "https://ntfy.example/t"})
    d = dispatcher_from_config(cfg, Workspace(tmp_path), env={"SMTP_USERNAME": "u@example.com", "SMTP_PASSWORD": "pw",
                                                              "NTFY_TOKEN": "tk_x"})
    smtp, ntfy = d.channels
    assert isinstance(smtp, SmtpChannel) and (smtp.host, smtp.port, smtp.sender, smtp.to) == (
        "smtp.gmail.com", 587, "u@example.com", "ops@example.com")
    assert isinstance(ntfy, NtfyChannel) and ntfy.token == "tk_x"
    assert d.repeat_s == 6 * H and d.path == tmp_path / "alerts.json"
    with caplog.at_level(logging.WARNING, logger="transmitter.alerts"):
        d = dispatcher_from_config(cfg, Workspace(tmp_path), env={})
    assert [c.name for c in d.channels] == ["ntfy"] and "email alerts are off" in caplog.text


def test_smtp_channel_uses_starttls_and_login(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, msg):
            calls.append(("send", msg["From"], msg["To"], msg["Subject"], msg.get_content().strip()))

    monkeypatch.setattr(alerts.smtplib, "SMTP", FakeSMTP)
    SmtpChannel("smtp.gmail.com", 587, "u@example.com", "pw", "u@example.com", "ops@example.com").send("subj", "body", 4)
    assert calls == [("connect", "smtp.gmail.com", 587, 20.0), ("starttls",), ("login", "u@example.com", "pw"),
                     ("send", "u@example.com", "ops@example.com", "subj", "body")]


def test_ntfy_channel_posts_with_headers(monkeypatch):
    seen = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen.update(url=req.full_url, method=req.get_method(), headers=dict(req.header_items()), body=req.data,
                    timeout=timeout)
        return Resp()

    monkeypatch.setattr(alerts.urllib.request, "urlopen", fake_urlopen)
    NtfyChannel("https://ntfy.example/t", "tk_1").send("llama radio: dead-clock", "stale", 4)
    assert seen["url"] == "https://ntfy.example/t" and seen["method"] == "POST" and seen["body"] == b"stale"
    assert seen["headers"]["Title"] == "llama radio: dead-clock"
    assert seen["headers"]["Priority"] == "4" and seen["headers"]["Authorization"] == "Bearer tk_1"
```

Append to `tests_transmitter/test_config.py`:

```python
def test_alerts_defaults_and_floors(tmp_path):
    from transmitter.config import AlertsConfig

    a = AlertsConfig()
    assert (a.smtp_host, a.smtp_port, a.repeat_hours, a.dead_clock_seconds, a.guard_stale_minutes) == \
        ("smtp.gmail.com", 587, 6.0, 120.0, 45.0)
    assert a.email_to is None and a.ntfy_url is None
    path = tmp_path / "c.toml"
    for bad in ('[alerts]\ndead_clock_seconds = 30\n', '[alerts]\nguard_stale_minutes = 30\n',
                '[publish]\nguard_check_minutes = 30\n',          # 30 + 16 is above the default 45
                '[alerts]\nsmtp_password = "x"\n'):
        path.write_text(bad)
        with pytest.raises(ConfigError):
            load_config(path)
    path.write_text('[publish]\nguard_check_minutes = 5\n[alerts]\nguard_stale_minutes = 21\n')
    assert load_config(path).alerts.guard_stale_minutes == 21
```

In `tests_transmitter/test_service.py`, make two changes:

1. In `test_runner_alerts_and_keeps_publishing_when_planning_fails`, change `assert "ALERT plan" in caplog.text and ".station-root" in caplog.text` to `assert "ALERT station-root" in caplog.text and ".station-root" in caplog.text`.
2. In `test_plan_errors_alert_and_the_loop_continues`, replace the line `assert f"ALERT plan: {type(exc).__name__}: {exc}" in caplog.text` with:

```python
    code = "station-root" if isinstance(exc, StationRootError) else "plan"
    assert f"ALERT {code}: {type(exc).__name__}: {exc}" in caplog.text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_alerts.py packages/transmitter/tests_transmitter/test_config.py packages/transmitter/tests_transmitter/test_service.py -q`
Expected: FAIL. `cannot import name 'Dispatcher'`, `AlertsConfig` is unknown, and the `ALERT station-root` assertion fails.

- [ ] **Step 3: Implement**

Replace `packages/transmitter/src/transmitter/alerts.py` with:

```python
"""Hugo-side alerts (spec "Alerts and operations"). Every alert is logged at
ERROR (journald under systemd). Once `configure()` has installed a
Dispatcher -- `transmitter run` does it at start -- each alert is also sent by
email (SMTP with STARTTLS) and ntfy, deduped per code in
~/.transmitter/alerts.json: sent when a code first fires, then at most once
per `repeat_hours` while it keeps firing. `resolve(code)` marks a level
condition clear (and says so, if it had been sent) so that its next occurrence
is sent at once. Any other code is an event: it stops counting as active once
`repeat_hours` pass without a new fire, so `status` shows no stale alarms. A
failing channel is logged, never raised: alerting must not take the service
down."""

import logging
import os
import smtplib
import ssl
import time
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Mapping, Protocol

from transmitter.workspace import Workspace, read_json, write_json

log = logging.getLogger("transmitter.alerts")

# Level conditions, resolved explicitly (ruling R16). Every other code is an
# event: active only until `repeat_hours` pass without a new fire.
LEVEL_CODES = frozenset({"dead-clock", "guard-stale", "station-root", "plan", "render"})


def _expired(code: str, entry: dict, now: float, repeat_s: float) -> bool:
    """An event code that has not fired for longer than `repeat_s`."""
    last = entry.get("last_fired_at", entry.get("first_at"))
    return code not in LEVEL_CODES and (not isinstance(last, (int, float)) or now - last > repeat_s)


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
        headers = {"Title": subject, "Priority": str(priority), "Tags": "warning" if priority >= 4 else "white_check_mark"}
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

    def _load(self) -> dict:
        data = read_json(self.path, {})
        return data if isinstance(data, dict) else {}

    def _send(self, subject: str, body: str, priority: int) -> bool:
        delivered = False
        for ch in self.channels:
            try:
                ch.send(subject, body, priority)
                delivered = True
            except Exception as exc:              # never let alerting break the service
                log.warning("alert channel %s failed: %s", ch.name, exc)
        return delivered

    def fire(self, code: str, message: str) -> None:
        state = self._load()
        now = self.now()
        entry = state.get(code) or {"active": False, "first_at": now, "last_sent_at": None, "count": 0}
        if not entry.get("active") or _expired(code, entry, now, self.repeat_s):
            entry.update(active=True, first_at=now, last_sent_at=None, count=0)
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_fired_at"] = now
        last = entry.get("last_sent_at")
        if self.channels and (last is None or now - last >= self.repeat_s):
            suppressed = entry["count"] - 1
            body = message + (f"\n\n({suppressed} more since the last message)" if last and suppressed else "")
            if self._send(f"{self.station}: {code}", body, 4):
                entry["last_sent_at"], entry["count"] = now, 0
        state[code] = entry
        write_json(self.path, state)

    def resolve(self, code: str) -> None:
        state = self._load()
        entry = state.get(code)
        if not entry or not entry.get("active"):
            return
        if entry.get("last_sent_at") is not None:
            self._send(f"{self.station}: resolved: {code}", f"{code} has cleared.", 3)
        entry["active"] = False
        state[code] = entry
        write_json(self.path, state)

    def active(self) -> list[str]:
        return active_codes(self._load(), self.now(), self.repeat_s)


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
```

`workspace.py`: add after the `lock_path` property:

```python

    @property
    def alerts_path(self) -> Path:
        return self.root / "alerts.json"
```

`config.py`: add the model before `class AntennaConfig`:

```python
class AlertsConfig(_StrictModel):
    """hugo's alert channels (spec "Alerts and operations"). Secrets come from
    the service's env file: SMTP_USERNAME, SMTP_PASSWORD, NTFY_TOKEN."""
    email_to: str | None = None
    email_from: str | None = None                  # default: SMTP_USERNAME
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    ntfy_url: str | None = None                    # https://ntfy.sh/<topic>
    repeat_hours: float = Field(default=6.0, gt=0)
    # Dead clock: the public live.m3u8's newest segment older than this, twice
    # in a row. At least 3 d (spec); the default allows the measured cron lags.
    dead_clock_seconds: float = Field(default=120.0, ge=31)
    # Dead guard: state/guard.json last evaluated longer ago than this. hugo
    # sees the evaluation time through a cache refreshed every [publish]
    # guard_check_minutes, and the guard evaluates every 15 minutes plus the
    # cron lag: at least guard_check_minutes + 16 (TransmitterConfig checks).
    guard_stale_minutes: float = Field(default=45.0, gt=0)
```

Then add `alerts: AlertsConfig = Field(default_factory=AlertsConfig)` as the last field of `TransmitterConfig`, followed by this validator (the floor spans two sections, so it lives on `TransmitterConfig`):

```python

    @model_validator(mode="after")
    def _guard_stale_outlasts_the_cache(self):
        floor = self.publish.guard_check_minutes + 16
        if self.alerts.guard_stale_minutes < floor:
            raise ValueError(f"alerts.guard_stale_minutes must be at least publish.guard_check_minutes + 16 ({floor:g}): "
                             "anything shorter alarms while the guard is healthy")
        return self
```

In `DEFAULT_CONFIG_TOML`, replace the `[antenna]` tail:

```
# public base URL, for Open Graph links on show pages
# site_url = "https://radio.example.org"
station_name = "llama radio"
"""
```

with:

```
# public base URL, for Open Graph links on show pages and the dead-clock
# check (which fetches <site_url>/live.m3u8 once a minute; unset = no check)
# site_url = "https://radio.example.org"
station_name = "llama radio"

[alerts]
# Email over SMTP with STARTTLS (credentials from the env file: SMTP_USERNAME,
# SMTP_PASSWORD -- for Gmail an App Password) and ntfy (NTFY_TOKEN, optional).
# With neither, alerts only reach the log (journald).
# email_to = "you@example.com"
# email_from = "station@example.com"      # default: SMTP_USERNAME
smtp_host = "smtp.gmail.com"
smtp_port = 587
# ntfy_url = "https://ntfy.sh/<your-topic>"
# re-send a still-firing alert at most this often
repeat_hours = 6.0
# the public live.m3u8 older than this (twice in a row): the clock is dead
dead_clock_seconds = 120.0
# state/guard.json not evaluated for this long: the guard is dead
# (at least [publish] guard_check_minutes + 16)
guard_stale_minutes = 45.0
"""
```

`service.py`, three edits:

1. Change the errors import to `from transmitter.errors import ConfigError, FrameCountDrift, PublishLocked, StationRootError, TransmitterError`.
2. Replace the head of `Runner._step`, through `fn()`:

```python
    def _step(self, name: str, fn: Callable[[], object]) -> None:
        """Run one step; no error ends the loop (the next tick retries)."""
        try:
            fn()
        except FrameCountDrift as exc:
```

   with:

```python
    def _step(self, name: str, fn: Callable[[], object], *, resolves: tuple[str, ...] = ()) -> None:
        """Run one step; no error ends the loop (the next tick retries). A step
        that succeeds resolves `resolves`."""
        try:
            fn()
            for code in resolves:
                alerts.resolve(code)
        except StationRootError as exc:
            log.error("%s step: %s", name, exc)
            alerts.alert("station-root", f"{type(exc).__name__}: {exc}")
        except FrameCountDrift as exc:
```

3. In `tick`, the fill steps resolve their codes:

```python
        if self.filling:
            self._step("plan", lambda: pipeline.plan_step(self.st, t_us, max_new=1),
                       resolves=("plan", "station-root"))
            self._step("render", lambda: pipeline.render_step(
                self.st, t_us, limit=self.st.cfg.publish.batch_segments), resolves=("render",))
```

`cli.py` `run`: configure the dispatcher for the service's lifetime:

```python
    """The service loop: plan/render below low water, publish and prune every minute."""
    from transmitter import alerts

    cfg = load_config(config)
    t = service.now_us()
    st = service.open_station(cfg, t)
    alerts.configure(alerts.dispatcher_from_config(cfg, st.ws))
    try:
        service.Runner(st, service.open_publisher(st)).run(max_ticks=1 if once else None)
    finally:
        alerts.configure(None)
```

- [ ] **Step 4: Run the transmitter suite on both Pythons**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS. Then run `./.venv/bin/transmitter config init --stdout | grep -A3 '\[alerts\]'`. Expected: it prints the commented `[alerts]` section with placeholder addresses only.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): hugo alerts by SMTP (STARTTLS) and ntfy, deduped per code in alerts.json"
```

---

