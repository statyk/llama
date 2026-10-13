### Task 15: sd_notify, watchdog, systemd unit

**Model hint:** sonnet

**Files:**
- Create: `packages/transmitter/src/transmitter/sdnotify.py`, `packages/transmitter/systemd/transmitter@.service`, `packages/transmitter/tests_transmitter/test_systemd.py`
- Modify: `service.py` (`Runner(notify=…)`; pings)

**Interfaces:**
- Consumes: `Runner` and `publish_all` (Task 14 state).
- Produces:
  - `sdnotify.notify(message, env=os.environ) -> bool` (no-op without `NOTIFY_SOCKET`; `@` = an abstract socket; errors are logged, never raised).
  - `Runner(..., notify=sdnotify.notify)`: `READY=1` when `run` starts, `WATCHDOG=1` after every step (in `_step`'s `finally`) and `STOPPING=1` when `run` ends.
  - `publish_all(p, t_us, held=None, notify=None)`: `WATCHDOG=1` after every publish batch, so a long catch-up publish (up to `MAX_BATCHES` batches after a stop) is not killed by `WatchdogSec`; the runner passes its notifier.
  - The template unit `transmitter@<user>.service` (ruling R15).

- [ ] **Step 1: Write the failing test**

`packages/transmitter/tests_transmitter/test_systemd.py`:

```python
import configparser
import socket
import tempfile
from pathlib import Path

from tests_transmitter.helpers import FakeBucket, make_station
from tests_transmitter.test_service import _publisher
from transmitter import sdnotify, service

UNIT = Path(__file__).resolve().parents[1] / "systemd" / "transmitter@.service"


def test_notify_is_a_no_op_outside_systemd():
    assert sdnotify.notify("READY=1", env={}) is False


def test_notify_sends_one_datagram_to_notify_socket():
    with tempfile.TemporaryDirectory(dir="/tmp") as d:      # AF_UNIX paths are short (104 bytes on macOS)
        path = str(Path(d) / "n")
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
            server.bind(path)
            assert sdnotify.notify("WATCHDOG=1", env={"NOTIFY_SOCKET": path}) is True
            assert server.recv(64) == b"WATCHDOG=1"


def test_notify_failure_is_logged_not_raised():
    assert sdnotify.notify("READY=1", env={"NOTIFY_SOCKET": "/nonexistent/socket"}) is False


def test_the_runner_says_ready_pings_the_watchdog_after_every_step_and_says_stopping(tmp_path):
    st, _ = make_station(tmp_path)
    sent: list[str] = []
    runner = service.Runner(st, _publisher(st, FakeBucket()), sleep=lambda s: None,
                            notify=lambda m: sent.append(m) or True)
    runner.run(max_ticks=1)
    assert sent[0] == "READY=1" and sent[-1] == "STOPPING=1"
    assert sent.count("WATCHDOG=1") == 4                    # plan, render, publish, and its one batch


def test_publish_all_feeds_the_watchdog_after_every_batch(tmp_path, monkeypatch):
    from transmitter import publish

    st, _ = make_station(tmp_path)
    batches = iter([publish.PublishReport(uploaded=[1]), publish.PublishReport(uploaded=[2]), publish.PublishReport()])
    monkeypatch.setattr(publish, "publish_batch", lambda p, t_us: next(batches))
    monkeypatch.setattr(publish, "prune", lambda p, t_us: publish.PruneReport())
    sent: list[str] = []
    service.publish_all(_publisher(st, FakeBucket()), 0, notify=lambda m: sent.append(m) or True)
    assert sent == ["WATCHDOG=1"] * 3


def test_the_unit_runs_transmitter_under_a_watchdog_and_always_restarts():
    unit = configparser.ConfigParser(strict=False, interpolation=None)
    unit.optionxform = str
    unit.read_string(UNIT.read_text())
    s = unit["Service"]
    assert s["Type"] == "notify" and s["NotifyAccess"] == "main"
    assert s["Restart"] == "always" and s["RestartSec"] == "30"
    assert s["WatchdogSec"] == "45min"
    assert s["User"] == "%i"
    assert s["EnvironmentFile"] == "/etc/transmitter/%i.env"
    assert s["ExecStart"].endswith("/bin/transmitter run")
    assert s["StandardOutput"] == "journal"
    assert unit["Install"]["WantedBy"] == "multi-user.target"
    assert "network-online.target" in unit["Unit"]["After"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter/test_systemd.py -q`
Expected: FAIL. `cannot import name 'sdnotify'`.

- [ ] **Step 3: Implement**

`packages/transmitter/src/transmitter/sdnotify.py`:

```python
"""systemd notifications without libsystemd (sd_notify(3)): one datagram to
$NOTIFY_SOCKET (a leading "@" names an abstract socket). The unit is
Type=notify with WatchdogSec: `transmitter run` sends READY=1 once, then
WATCHDOG=1 after every step of every tick and after every publish batch, so a
hang longer than WatchdogSec (e.g. a hard NFS mount) gets the service killed
and restarted. Outside systemd (no NOTIFY_SOCKET) every call is a no-op."""

import logging
import os
import socket
from typing import Mapping

log = logging.getLogger("transmitter")


def notify(message: str, env: Mapping[str, str] = os.environ) -> bool:
    addr = env.get("NOTIFY_SOCKET")
    if not addr:
        return False
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(addr)
            sock.sendall(message.encode())
        return True
    except OSError as exc:
        log.warning("sd_notify(%s) failed: %s", message, exc)
        return False
```

`packages/transmitter/systemd/transmitter@.service`:

```ini
# transmitter as a system service: `transmitter@<user>.service` runs
# `transmitter run` as <user> (the account that owns ~/.transmitter and can
# read the station root over NFS). Install: docs/playout-setup.md, section 6.
[Unit]
Description=llama station playout (transmitter run) as %i
After=network-online.target remote-fs.target
Wants=network-online.target

[Service]
Type=notify
NotifyAccess=main
User=%i
# R2 keys, SMTP credentials, NTFY_TOKEN; owned by %i, mode 600.
EnvironmentFile=/etc/transmitter/%i.env
ExecStart=/home/%i/.venvs/transmitter/bin/transmitter run
Restart=always
RestartSec=30
# transmitter pings after every step and every publish batch; the longest gap is one
# show's encode (~10-20 min on hugo).
WatchdogSec=45min
TimeoutStartSec=2min
StandardOutput=journal
StandardError=journal
SyslogIdentifier=transmitter

[Install]
WantedBy=multi-user.target
```

`service.py`, five edits:

1. Add `sdnotify` to `from transmitter import …`.
2. `Runner.__init__` becomes:

```python
    def __init__(self, st: pipeline.Station, p: publish.Publisher, *, clock: Callable[[], int] = now_us,
                 sleep: Callable[[float], None] = time.sleep, tick_s: float = 60.0,
                 monitor: DeadClockMonitor | None = None, notify: Callable[[str], bool] = sdnotify.notify):
        self.st, self.p, self.clock, self.sleep, self.tick_s = st, p, clock, sleep, tick_s
        self.monitor, self.notify = monitor, notify
```

3. In `_step`, extend the docstring's last sentence to "… resolves `resolves`; every step ends with a watchdog ping." and add a `finally` after the last `except` clause:

```python
        except Exception as exc:
            log.exception("%s step failed", name)
            alerts.alert(name, f"{type(exc).__name__}: {exc}")
        finally:
            self.notify("WATCHDOG=1")
```

4. `publish_all` feeds the watchdog after every batch. Its signature and loop head become:

```python
def publish_all(p: publish.Publisher, t_us: int, held: HeldTracker | None = None,
                notify: Callable[[str], object] | None = None
                ) -> tuple[list[publish.PublishReport], publish.PruneReport]:
    reports = []
    for _ in range(MAX_BATCHES):
        r = publish.publish_batch(p, t_us)
        reports.append(r)
        if notify is not None:
            notify("WATCHDOG=1")    # a catch-up is many batches: one step must not outlast WatchdogSec
```

   (the rest of the loop is unchanged), and in `tick` the publish step passes the notifier: `self._step("publish", lambda: publish_all(self.p, t_us, self.held, self.notify))`.

5. `run` becomes:

```python
    def run(self, max_ticks: int | None = None) -> None:
        self.notify("READY=1")
        ticks = 0
        try:
            while max_ticks is None or ticks < max_ticks:
                started = time.monotonic()
                self.tick(self.clock())
                ticks += 1
                if max_ticks is not None and ticks >= max_ticks:
                    break
                self.sleep(max(0.0, self.tick_s - (time.monotonic() - started)))
        finally:
            self.notify("STOPPING=1")
```

- [ ] **Step 4: Run the transmitter suite on both Pythons (and the Debian-12 gate)**

Run: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q && ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q`
Expected: PASS. If Docker is available, also run `packages/transmitter/scripts/test-in-debian12.sh -q`, which exercises the real AF_UNIX datagram on Linux.

- [ ] **Step 5: Commit**

```bash
git add packages/transmitter
git commit -m "feat(transmitter): systemd unit (Type=notify, WatchdogSec, Restart=always) and sd_notify pings"
```

---

