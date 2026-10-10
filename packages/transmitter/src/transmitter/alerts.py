"""Alert seam (spec "Alerts and operations", phase 2). Phase 1 logs at ERROR
(journald picks it up under systemd); phase 2 adds SMTP + ntfy channels and
per-condition dedupe in ~/.transmitter/alerts.json behind this same call."""

import logging

log = logging.getLogger("transmitter.alerts")


def alert(code: str, message: str) -> None:
    log.error("ALERT %s: %s", code, message)
