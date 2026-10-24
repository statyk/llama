"""The dead-clock monitor's own loop (spec Part 3). `DeadClockMonitor.check`
(and, from the relay task on, the antenna alert relay) run on a dedicated
daemon thread every `MONITOR_INTERVAL_S`, independent of plan, render and
publish, so a long fill cannot starve the dead-clock check.

What the thread may do is deliberately narrow:
- it reads R2 only, through an `R2Reader` (a JSON get and nothing else) built
  on its own boto3 client, made on the main thread before the thread starts
  (boto3 clients are thread-safe once made; making one concurrently from the
  default session is not), with short timeouts;
- it builds its own guard view (`publish.guard_view`) and never touches the
  publisher's guard cache, which stays publish's spend control;
- it never pings the systemd watchdog: WATCHDOG=1 must keep meaning "the main
  loop is alive", so a hung main loop is still killed and restarted;
- it calls the Dispatcher only through `alerts.alert`/`resolve`/
  `end_observation`; the playlist fetch, the guard reads and the relay run
  outside the Dispatcher's lock.

The main tick watches the thread through `stalled()` (the level code
`monitor-stalled`). This module must not import `service`."""

import json
import logging
import threading
import time
from typing import Callable

from transmitter import alerts, publish, r2
from transmitter.deadclock import DeadClockMonitor

log = logging.getLogger("transmitter.monitor")

MONITOR_INTERVAL_S = 60.0        # one pass a minute
MONITOR_STALL_S = 300.0          # no completed pass for this long: monitor-stalled
MONITOR_JOIN_S = 5.0             # how long shutdown waits for the thread (a daemon: it never holds the process)
READER_CONNECT_TIMEOUT_S = 5     # the reader's boto3 timeouts: a slow R2 must not stretch a pass toward
READER_READ_TIMEOUT_S = 10       # MONITOR_STALL_S


def _wall_us() -> int:
    return time.time_ns() // 1000


class R2Reader:
    """A get-only view of the bucket: the monitor thread's whole access to R2."""

    def __init__(self, client, bucket: str):
        self.client, self.bucket = client, bucket

    def get_json(self, key: str) -> dict | None:
        """The document, or None when absent; any other error, and a body that
        is not JSON, propagates (as publish.Uploader.get_json)."""
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if r2.error_code(exc) in ("NoSuchKey", "404"):
                return None
            raise
        return json.loads(resp["Body"].read())


class MonitorLoop:
    def __init__(self, deadclock: DeadClockMonitor | None, reader: R2Reader, relay=None, *,
                 clock: Callable[[], int] = _wall_us, monotonic: Callable[[], float] = time.monotonic,
                 interval_s: float = MONITOR_INTERVAL_S):
        self.deadclock, self.reader, self.relay = deadclock, reader, relay
        self.clock, self.monotonic, self.interval_s = clock, monotonic, interval_s
        self.started = False
        self.last_pass: float | None = None      # monotonic time of the last completed pass (or of start())
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_pass(self, *, relay: bool = True) -> None:
        """One pass: the dead-clock check (one observation of
        `dead-clock-check`), then the relay unless `relay` is False. Never
        raises: a failing check fires the gated event code `dead-clock-check`,
        a failing relay is a WARNING only."""
        if self.deadclock is not None:
            try:
                self.deadclock.check(self.clock(), lambda: publish.guard_view(self.reader.get_json))
            except Exception as exc:
                log.exception("dead-clock check failed")
                alerts.alert("dead-clock-check", f"{type(exc).__name__}: {exc}")
            finally:
                alerts.end_observation(alerts.MONITOR, ["dead-clock-check"])
        if relay and self.relay is not None:
            try:
                self.relay.run_pass()
            except Exception:
                log.warning("alert relay pass failed", exc_info=True)
        self.last_pass = self.monotonic()

    def _loop(self) -> None:
        while not self._stop.is_set():
            began = self.monotonic()
            try:
                self.run_pass()
            except Exception:                    # run_pass never raises; belt and braces for the thread
                log.warning("dead-clock monitor pass failed", exc_info=True)
            self._stop.wait(max(0.0, self.interval_s - (self.monotonic() - began)))

    def start(self) -> None:
        """Start the thread. `_thread` and `started` are set only once
        `Thread.start()` has succeeded, so a thread that could not start leaves
        `stop()` harmless (no join of an unstarted thread masking the error)
        and `stalled()` silent."""
        self.last_pass = self.monotonic()        # stalled() counts from the start until the first pass
        self._stop.clear()
        thread = threading.Thread(target=self._loop, name="transmitter-monitor", daemon=True)
        thread.start()
        self._thread, self.started = thread, True

    def stop(self, timeout_s: float = MONITOR_JOIN_S) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout_s)
            if self._thread.is_alive():
                log.warning("the dead-clock monitor thread did not stop within %.0f s (a daemon: exiting anyway)",
                            timeout_s)

    def stalled(self) -> str | None:
        """The `monitor-stalled` message, or None: the thread has died, or has
        completed no pass for more than MONITOR_STALL_S (counting from start()
        until its first pass). None before start()."""
        if not self.started:
            return None
        if self._thread is None or not self._thread.is_alive():
            return "the dead-clock monitor thread is not running"
        age = self.monotonic() - (self.last_pass if self.last_pass is not None else 0.0)
        if age > MONITOR_STALL_S:
            return f"the dead-clock monitor has completed no pass for {age / 60:.0f} minutes"
        return None
