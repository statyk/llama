"""The antenna alert relay (spec Part 2, hugo side). antenna's Worker cannot
use ntfy (ntfy.sh limits a tierless account per IP and Workers share egress
IPs), so it emails each alert and appends it to `state/alert-relay.json`; hugo,
whose own ntfy works, reads that document once a minute on the monitor thread
(monitor.MonitorLoop) and pushes each new message to its ntfy channel only
(email already went from the Worker).

The document (antenna/src/alerts.ts `RelayDoc`) is `{"stream": str, "ring":
[...]}`, the ring holding antenna's last 50 messages `{seq, at, key, kind,
priority, title, message}`, `seq` strictly increasing within a stream; title
and message are already redacted and carry no station prefix.

The relay bypasses the Dispatcher entirely (antenna already deduped): its own
NtfyChannel instance, no gate, no alerts.json, no shared channel cool-down. A
relay failure is never a station alert: a WARNING log only (email covers it).

The cursor rule: the in-memory cursor `(stream, seq)` is authoritative. It is
read once at startup from `Workspace.relay_cursor_path` (absent: no cursor;
unreadable or malformed: no cursor and one WARNING) and written best-effort
after each pass that moves it (a failed write is a WARNING and never causes a
re-send). No cursor, or a document whose stream differs from the cursor's,
means seq 0 in the document's stream. A message above the cursor is sent when
it is younger than `RELAY_MAX_AGE_S`: that bound is what stops hugo, back
after an outage (or starting with no cursor), from paging the operator with a
backlog of stale alerts. The cursor advances past every message the pass
handled: sent; refused by ntfy with a 4xx other than 429 (one WARNING with the
status); skipped for age (one INFO line, once, since the cursor then moves past
it); or unusable (a field not a string, an unparseable `at`, or a ValueError
from the channel itself, which is local and deterministic: one WARNING). On
429, 5xx, a redirect or a transport error the pass stops, and the next pass
retries from that message. A pass sends for at most `RELAY_PASS_BUDGET_S`
(checked before each send, so one more send's timeout can follow); the rest
waits for the next pass.

This module reads R2 only through the `get_json` it is handed (the monitor's
get-only reader) and writes nothing but its own cursor file."""

import logging
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, NamedTuple

from transmitter.alerts import NtfyChannel
from transmitter.workspace import read_json, write_json

log = logging.getLogger("transmitter.relay")

RELAY_KEY = "state/alert-relay.json"     # antenna's RELAY_KEY (a test reads alerts.ts)
RELAY_MAX_AGE_S = 3600.0                 # older messages are skipped, never paged
RELAY_PASS_BUDGET_S = 30.0               # one pass stops sending after this long
PRIORITY = {"urgent": 5, "high": 4, "default": 3}
TAGS = {"urgent": "rotating_light", "high": "warning", "default": "information_source"}
RESOLVED_TAGS = "white_check_mark"
TEXT_FIELDS = ("at", "key", "kind", "priority", "title", "message")

_ABSENT = object()


def _is_int(v) -> bool:
    """A JSON integer: never a bool (an int subclass in Python) and never a
    float, even an integral one (antenna never writes `1.0`)."""
    return isinstance(v, int) and not isinstance(v, bool)


def doc_problem(doc: object) -> str | None:
    """Why a relay document is unusable, or None: antenna's `relayDocProblem`
    rule, message for message. Not an object, `stream` not a string, `ring`
    not an array, or a ring entry that is not an object with an integer
    (never boolean, never float) `seq`."""
    if not isinstance(doc, dict):
        return "not an object"
    if not isinstance(doc.get("stream"), str):
        return "stream is not a string"
    ring = doc.get("ring")
    if not isinstance(ring, list):
        return "ring is not an array"
    for i, m in enumerate(ring):
        if not isinstance(m, dict):
            return f"ring[{i}] is not an object"
        if not _is_int(m.get("seq")):
            return f"ring[{i}].seq is not an integer"
    return None


def format_message(m: dict, station: str) -> tuple[str, str, int, str]:
    """(subject, body, priority, tags) for one relayed message. A "resolved"
    is priority 3 with the check mark whatever its priority says; any other
    kind maps its priority (an unknown one reads as default), so a
    default-priority alert never carries the check mark. The subject goes
    into ntfy's Title header, so CR and LF become spaces (http.client refuses
    them); subject and body are made UTF-8-encodable."""
    if m["kind"] == "resolved":
        prefix, priority, tags = "resolved: ", 3, RESOLVED_TAGS
    else:
        prefix = ""
        priority = PRIORITY.get(m["priority"], PRIORITY["default"])
        tags = TAGS.get(m["priority"], TAGS["default"])
    subject = f"{station}: {prefix}{m['title']}".replace("\r", " ").replace("\n", " ")
    body = f"{m['message']}\n\n-- relayed from antenna ({m['key']}, {m['at']})"
    return _encodable(subject), _encodable(body), priority, tags


def _encodable(text: str) -> str:
    """`text` with anything UTF-8 cannot encode (a lone surrogate, valid in
    JSON as `\\ud800`) replaced by `?`, so the channel's encode never raises."""
    return text.encode("utf-8", "replace").decode("utf-8")


def _parse_at(at: str) -> float:
    """antenna's ISO time (toISOString: `...Z`) as epoch seconds; a naive time
    reads as UTC. Raises ValueError (or OverflowError) when unparseable."""
    d = datetime.fromisoformat(at)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


class Cursor(NamedTuple):
    stream: str
    seq: int


def _read_cursor(path: Path) -> Cursor | None:
    try:
        data = read_json(path, _ABSENT)
    except (OSError, ValueError) as exc:
        log.warning("alert relay cursor %s is unreadable (%s): starting with no cursor", path, exc)
        return None
    if data is _ABSENT:
        return None
    if (not isinstance(data, dict) or not isinstance(data.get("stream"), str)
            or not _is_int(data.get("seq")) or data["seq"] < 0):
        log.warning("alert relay cursor %s is malformed (%.100r): starting with no cursor", path, data)
        return None
    return Cursor(data["stream"], data["seq"])


class Relay:
    def __init__(self, get_json: Callable[[str], dict | None], channel: NtfyChannel, station: str,
                 cursor_path: Path, *, now: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic):
        self.get_json, self.channel, self.station, self.cursor_path = get_json, channel, station, cursor_path
        self.now, self.monotonic = now, monotonic
        self.cursor: Cursor | None = _read_cursor(cursor_path)     # in memory, authoritative

    def run_pass(self) -> None:
        """One relay pass (see the module docstring). Never raises for a bad
        document or a failing channel; those are WARNING logs."""
        try:
            doc = self.get_json(RELAY_KEY)
            if doc is None:
                return                              # nothing to relay; the cursor stays
            problem = doc_problem(doc)              # inside the try: a checker bug is a WARNING too
        except Exception as exc:
            log.warning("alert relay: cannot read %s: %s: %s", RELAY_KEY, type(exc).__name__, exc)
            return
        if problem is not None:
            log.warning("alert relay: %s is malformed (%s); nothing relayed", RELAY_KEY, problem)
            return
        stream = doc["stream"]
        start = self.cursor.seq if self.cursor is not None and self.cursor.stream == stream else 0
        handled = start
        began = self.monotonic()
        for m in sorted((m for m in doc["ring"] if m["seq"] > start), key=lambda m: m["seq"]):
            seq = m["seq"]
            if self.monotonic() - began >= RELAY_PASS_BUDGET_S:
                log.info("alert relay: pass budget of %.0f s spent; relayed alert %d onwards wait for the next pass",
                         RELAY_PASS_BUDGET_S, seq)
                break
            bad = [f for f in TEXT_FIELDS if not isinstance(m.get(f), str)]
            if bad:
                log.warning("relayed alert %d skipped: %s not a string", seq, ", ".join(bad))
                handled = seq
                continue
            try:
                at = _parse_at(m["at"])
            except (ValueError, OverflowError) as exc:
                log.warning("relayed alert %d (%s) skipped: unparseable at %r (%s)", seq, m["key"], m["at"], exc)
                handled = seq
                continue
            if self.now() - at >= RELAY_MAX_AGE_S:
                log.info("skipped relayed alert %d (%s): older than 1 h (at %s)", seq, m["key"], m["at"])
                handled = seq
                continue
            try:
                self.channel.send(*format_message(m, self.station))
            except urllib.error.HTTPError as exc:
                if 400 <= exc.code < 500 and exc.code != 429:
                    log.warning("ntfy refused relayed alert %d (%s) with HTTP %d; skipped", seq, m["key"], exc.code)
                    handled = seq
                    continue
                log.warning("relay stopped at %d (%s): ntfy HTTP %d; the next pass retries it", seq, m["key"],
                            exc.code)
                break
            except ValueError as exc:               # local and deterministic (a header or encoding the
                # channel refuses, incl. UnicodeError): this message can never be
                # sent, so skip it like a 4xx rather than wedge every later one.
                # (HTTPError, URLError and OSError are not ValueErrors.)
                log.warning("relayed alert %d (%s) skipped: the ntfy channel refused it: %s: %s", seq, m["key"],
                            type(exc).__name__, exc)
                handled = seq
                continue
            except Exception as exc:                # transport, a redirect (OSError), anything else: retry later
                log.warning("relay stopped at %d (%s): %s: %s; the next pass retries it", seq, m["key"],
                            type(exc).__name__, exc)
                break
            handled = seq
        new = Cursor(stream, handled)
        if new != self.cursor:
            self.cursor = new
            try:
                write_json(self.cursor_path, {"stream": new.stream, "seq": new.seq})
            except OSError as exc:
                log.warning("alert relay cursor %s not saved (%s); the in-memory cursor still holds",
                            self.cursor_path, exc)
