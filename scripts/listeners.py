#!/usr/bin/env python3
"""Estimate station listeners from Cloudflare's zone HTTP analytics.

Every playing HLS client re-fetches live.m3u8 about once per segment (10.24 s),
and only a playing client fetches it (the page itself does not), so per time
bucket:

  est   = playlist requests / (bucket seconds / segment seconds)   (concurrent)
  peers = distinct (client IP, user agent) pairs that fetched it

transmitter's own checks (user agents starting `transmitter-`) and the
ops pollers (metronome verification, lma-radio-capture) are excluded. The adaptive dataset is a sampled estimate,
so `est` is approximate; at a handful of listeners treat it as "nobody / one /
a few". Read-only; stdlib only.

  CF_API_TOKEN=... CF_ZONE_ID=... python3 scripts/listeners.py [--hours 24]
      [--bucket 5m|1h] [--host listen.lma-radio.com] [--path /live.m3u8] [--utc]

Bucket times print in local time unless --utc.

The token needs Zone Analytics: Read on the station zone (the Worker's
CF_ANALYTICS_TOKEN is account-scoped and lives only in Worker secrets).
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
SEGMENT_SECONDS = 10.24
ROW_LIMIT = 10_000
CHUNK_HOURS = 6  # small windows keep bucket x client rows well under ROW_LIMIT
OWN_AGENTS = ("transmitter-", "metronome-verification-poller", "lma-radio-capture-poller")
BUCKETS = {"5m": ("datetimeFiveMinutes", 300), "1h": ("datetimeHour", 3600)}

QUERY = """query Listeners($zone: string!, $start: Time!, $end: Time!, $host: string!, $path: string!) {
  viewer {
    zones(filter: { zoneTag: $zone }) {
      httpRequestsAdaptiveGroups(limit: %d, filter: {
        datetime_geq: $start, datetime_lt: $end,
        clientRequestHTTPHost: $host, clientRequestPath: $path
      }) {
        count
        dimensions { %s clientIP userAgent }
      }
    }
  }
}"""


def own_agent(ua):
    return any((ua or "").startswith(p) for p in OWN_AGENTS)


def summarize(rows, bucket_field, bucket_seconds, segment_seconds=SEGMENT_SECONDS):
    """rows: GraphQL groups. Returns [(bucket, requests, est, peers)] sorted by bucket."""
    per = {}
    for r in rows:
        d = r["dimensions"]
        if own_agent(d.get("userAgent")):
            continue
        b = per.setdefault(d[bucket_field], [0, set()])
        b[0] += r["count"]
        b[1].add((d.get("clientIP"), d.get("userAgent")))
    polls = bucket_seconds / segment_seconds
    return [(k, n, n / polls, len(peers)) for k, (n, peers) in sorted(per.items())]


def windows(start, end, hours=CHUNK_HOURS):
    t = start
    while t < end:
        u = min(t + dt.timedelta(hours=hours), end)
        yield t, u
        t = u


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def label(bucket, utc=False):
    """Display form of a bucket timestamp ("2026-11-06T14:00:00Z"): UTC as-is, else local."""
    if utc:
        return bucket
    t = dt.datetime.fromisoformat(bucket.replace("Z", "+00:00")).astimezone()
    return t.strftime("%Y-%m-%d %H:%M %Z")


def query(token, variables, bucket_field):
    body = json.dumps({"query": QUERY % (ROW_LIMIT, bucket_field), "variables": variables}).encode()
    req = urllib.request.Request(GRAPHQL_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"analytics: HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")
    if payload.get("errors"):
        raise SystemExit("analytics: " + "; ".join(e.get("message", str(e)) for e in payload["errors"]))
    zones = (payload.get("data") or {}).get("viewer", {}).get("zones") or []
    if not zones:
        raise SystemExit("analytics: no zone in the response (check CF_ZONE_ID and the token's zone scope)")
    rows = zones[0]["httpRequestsAdaptiveGroups"]
    if len(rows) >= ROW_LIMIT:
        raise SystemExit(f"analytics: {len(rows)} rows (truncated); lower CHUNK_HOURS")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--bucket", choices=sorted(BUCKETS), default="1h")
    ap.add_argument("--host", default="listen.lma-radio.com")
    ap.add_argument("--path", default="/live.m3u8")
    ap.add_argument("--utc", action="store_true", help="print bucket times in UTC (default: local)")
    a = ap.parse_args(argv)
    token, zone = os.environ.get("CF_API_TOKEN"), os.environ.get("CF_ZONE_ID")
    if not token or not zone:
        raise SystemExit("set CF_API_TOKEN (Zone Analytics: Read) and CF_ZONE_ID")
    field, secs = BUCKETS[a.bucket]
    end = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    start = end - dt.timedelta(hours=a.hours)
    rows = []
    for s, e in windows(start, end):
        rows += query(token, {"zone": zone, "start": iso(s), "end": iso(e),
                              "host": a.host, "path": a.path}, field)
    out = summarize(rows, field, secs)
    print(f"{'bucket (UTC)' if a.utc else 'bucket (local)':<22}{'requests':>9}{'est':>7}{'peers':>7}")
    for b, n, est, peers in out:
        print(f"{label(b, a.utc):<22}{n:>9}{est:>7.1f}{peers:>7}")
    if out:
        peak = max(out, key=lambda r: r[2])
        total = sum(r[1] for r in out)
        hours = total * SEGMENT_SECONDS / 3600
        print(f"\npeak est {peak[2]:.1f} at {label(peak[0], a.utc)}; listening time ~{hours:.1f} h "
              f"over {a.hours:g} h; first data {label(out[0][0], a.utc)}")
    else:
        print("no listener requests in the window")


if __name__ == "__main__":
    main()
