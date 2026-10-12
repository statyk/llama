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
