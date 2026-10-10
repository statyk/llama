# Playout: transmitter + antenna — umbrella design

**Date:** 2026-10-09
**Scope:** two new components — `packages/transmitter` (Python, runs on hugo)
and `antenna` (Cloudflare Worker + static assets). llama, emcee and herder are
untouched; the station-root move is configuration only.
**Review mode:** Fable.
**Status:** umbrella spec. Phase 1 (thin slice) is specified to plan-ready
depth; phases 2–4 are specified at design depth and each gets its own
spec → plan → build cycle before implementation.

## Stakes

What is at risk is **money and on-air continuity**, not data. transmitter only
*reads* the station root and writes its own state (`~/.transmitter/`) and its own
R2 bucket; nothing here deletes or overwrites anything llama or emcee own, and
everything it produces is regenerable from the packages. A bug elsewhere costs
dead air, a glitch, a bad schedule, or a re-render.

**One strict surface: spend.** The operator's ceiling is "a few tens of dollars a
month", after which the station is shut down. The cost guard, the off-air path,
and every mechanism that bounds listener-driven request volume (playlist caching,
the ended-playlist off-air signal, the Worker's past-horizon backstop) are what
enforce that ceiling. A defect there can run up an uncapped bill silently; treat
those paths with the rigor of a migration. Secondary but real: the station must
never list a segment that does not exist (players stall), and must never cut a
performance mid-song (an explicit operator rule).

Context: strictly non-commercial, no ads, no donations, costs paid by the
operator. LMA licensing is a known gray zone (stream-only GD soundboards,
non-commercial-only bands); the operator's stated policy is to shut down on cost
overrun or on an objection from anyone with standing. Crediting sources (archive.org
link, taper lineage) is part of the design, not decoration.

## Goal

A 24/7 internet radio station that airs llama/emcee show packages: one shared
live stream (radio, not on-demand), a web player with now-playing, an embeddable
widget, easy sharing, clock-based scheduling, and tight cost control — with the
library kept off the cloud and only a rolling horizon of rendered audio uploaded.

Audience: designed to scale to an open public audience; realistically under ten
concurrent listeners.

## Measured context (2026-10-09)

- Station root (`~/Documents/llama/delivered`): 256 packages, 129 voiced, 49 GB,
  ~621 h. Median show 155 min (dead 175, range 33–275).
- Profiles: dead 112, bluegrass 65, americana 22, indie 15, southern 14, funk 7,
  livetronica 6, dead-family 6, jam 6, country 2.
- Source track mp3 ~200 kbps VBR; emcee DJ clips 64 kbps.
- Every package path is relative (`broadcast.m3u`, manifest `filename`s), so the
  same directory may be mounted at different absolute paths on different hosts.
- **Schedule feasibility, simulated** on the 256 real durations with a naive
  random-shuffle filler, whole shows only, no repeats within the week, example
  clock (Dead 07:00 & 19:00 daily, bluegrass 12:00 daily, funk Sat 22:30,
  dead-family Sun 15:00), 50 seeded weeks (1,100 gaps):

  | start window | anchor overran next window | gap not fillable |
  |---|---|---|
  | 60 min | 0.4% | 0.6% |
  | 30 min | 0.5% | 4.9% |
  | 15 min | 0.4% | 9.0% |
  | 5 min  | 0.5% | 12.1% |

  Overruns are fixable by length-aware anchor choice; a real search should beat
  the naive filler at narrow windows. Windowed whole-show scheduling is feasible
  today.

### Platform facts (researched 2026-10-09, sourced)

- **R2:** free 10 GB-month Standard storage, 1M Class A, 10M Class B ops/month;
  egress free. Beyond: $0.015/GB-mo, $4.50/M A, $0.36/M B. Edge caching requires
  a custom domain on a Cloudflare zone (r2.dev is uncached); a cache hit does not
  reach R2. Default cache rules do not cache every extension — a Cache Rule must
  cover the segment and playlist types.
- **Workers:** Free 100k req/day, 10 ms CPU. Paid $5/mo: 10M req/mo included,
  then $0.30/M; cron min interval 1 min. Whether a zone-cache hit served in front
  of a route-bound Worker is billed as a Worker request is **not documented** —
  measured in phase 1.
- **ToS:** Cloudflare's 2023 terms change permits serving large/audio files via
  the CDN when hosted on a Cloudflare service such as R2; whether R2's *free* tier
  counts as the required "Paid Service" is ambiguous. **Decision: run on Workers
  Paid ($5/mo)** — removes the ambiguity and provides request headroom.
- **Oracle Always Free** (cut to 2 OCPU/12 GB June 2026, idle reclamation,
  capacity scarcity) and **AzuraCast** (no duration-based gap fill) were evaluated
  and rejected; a Liquidsoap VM (Hetzner ~$6.50/mo + R2 fan-out) is the fallback
  architecture if the serverless design fails phase 1.
- **Browser HLS:** native in Safari/iOS; elsewhere hls.js. Chrome's 2025 native
  HLS rollout shipped a playback bug — prefer hls.js whenever
  `Hls.isSupported()`, native only as fallback.

## Architecture

```
 Mac (llama, emcee)           NAS (Synology)                hugo (Linux, always on)              Cloudflare
 ─────────────────            ───────────────               ───────────────────────              ──────────
 llama deliver ──SMB──▶  /volume1/media/<station>/  ◀──NFS── transmitter                         R2 bucket
 emcee run     ──SMB──▶    <package>/…                        plan → render → publish ──S3 API──▶  seg/, timeline,
                                                              guard ◀──GraphQL analytics──────────  horizon, notes, flags
                                                              alerts ──▶ email + ntfy                   │
                                                                                                    antenna Worker
                                                                                                    (/, /live.m3u8, /now.json,
                                                                                                     /embed, /show/<slug>)
                                                                                                         │
                                                                                                    listeners
```

- **Station root moves to the NAS.** A designated directory on the existing
  Synology `media` share becomes the station root: llama `delivery_path` and emcee
  `[station] root` point at its SMB path on the Mac (`/Volumes/media/<station>`);
  transmitter reads it over NFS on hugo (`/nfs/media/<station>`). The operator
  moves the existing content. No code change in llama or emcee.
  - On macOS an unmounted SMB share's `/Volumes/<name>` disappears and
    `/Volumes` is `root:wheel 755`, so llama's `copytree` cannot silently deliver
    to local disk — verified 2026-10-09.
  - **One-time verification before cut-over:** deliver one show to the NAS path
    and confirm llama's purge succeeds (its `F_FULLFSYNC` flush over SMB). The
    purge fails closed (keeps library audio, warns) if the flush is unsupported.
  - Only 6 AppleDouble `._*` files exist in the share's top four levels (the
    Synology stores Mac metadata natively); transmitter skips dot-prefixed
    entries regardless, as emcee's scanner does.
- **transmitter** (Python, `packages/transmitter`, dist `llama-transmitter`, CLI
  `transmitter`) runs on hugo as a systemd service. It imports neither llama nor
  emcee (enforced by a test, as emcee's `test_no_llama_imports.py`); its only
  input is the package directory. It may import `herder` only if it ever needs
  an LLM — it does not in this design.
- **antenna** (TypeScript, top-level `antenna/` directory in this repo) is one
  Worker with static assets and an R2 binding, deployed with `wrangler deploy`.

### The core contract: the stream is a function of the wall clock

transmitter fixes an **epoch** `E` (UTC instant) and a **segment duration** `d`.
Segment `N` always covers `[E + N·d, E + (N+1)·d)`. Every listener hears the same
moment; the Worker holds no per-listener or per-segment state — it computes the
current segment index from the clock.

`d` is a whole number of AAC frames at the output sample rate, so the grid is
sample-exact: at 44.1 kHz, `d = 430 × 1024 / 44100 ≈ 9.9846 s` (the exact value
is fixed by phase 1 and then immutable for the life of an epoch). `E` and `d`
are published in `horizon.json`; changing either is an **epoch change** (rare,
deliberate, documented as a re-render-everything operation).

### R2 object contract (complete)

| key | written by | cache | content |
|---|---|---|---|
| `seg/<N>.<ext>` | publish | immutable, 1 year | one audio segment of the grid |
| `fallback/<k>.<ext>` + `fallback/index.json` | one-time setup | immutable | short station-ID loop, never pruned |
| `horizon.json` | publish | ≤ 5 s | `{epoch, d, first, last, published_at, container}` — `last` is the highest `N` such that every segment `first..last` is present |
| `timeline.json` | publish | ≤ 30 s | items with UTC start/end, show metadata, per-track offsets (DJ clip or track title), upcoming anchors, recently aired |
| `notes/<slug>.json` | publish | ≤ 1 h | briefing text, archive.org URL, lineage, setlist, airtimes |
| `state/offair.json` | guard | ≤ 30 s | `{offair: bool, reason, since, until}` |

**Ordering invariant (strict):** publish uploads segments in ascending `N` and
rewrites `horizon.json` only after every segment it covers is confirmed present.
The Worker never lists `N > horizon.last`.

## Components

### transmitter — state and commands

State in `~/.transmitter/` (local disk on hugo, never the NFS share):
`config.toml`, `plan.jsonl` (scheduled items), `aired.jsonl` (rotation history),
`cache/` (per-file duration + loudness measurements, keyed by path+size+mtime),
`render/` (segments awaiting upload), `alerts.json` (dedupe state).

Commands: `plan`, `render`, `publish`, `guard`, `run` (the service loop running
each on its cadence), `status`, `schedule` (show upcoming plan with window
hits/misses), `library` (pool sizes/hours per anchor vs consumption),
`config init`. Config is strict (unknown keys are errors), like llama and emcee.

**Station-root guard:** the root must contain a marker file (`.station-root`,
created once by the operator on the share). Missing root or missing marker →
`plan` refuses, an alarm fires, and the library is never treated as empty. (On
hugo a down NFS mount is an ordinary empty directory.)

**Eligibility:** a package is eligible iff it is broadcast-ready — transmitter
reimplements emcee's readiness predicate on files alone (v3+ manifest, `dj-notes.md`,
`dj-audio/` clips named in the manifest, `broadcast.m3u`, every manifest track's
audio on disk) — and was not modified within the last few minutes (an emcee run
in progress rewrites the manifest last, but a quiet-period check costs nothing).
The playable unit is the package's `broadcast.m3u`, in order.

### Scheduler (phase 2)

Config:

```toml
[station]
root = "/nfs/media/station"
timezone = "America/New_York"

[[anchor]]
name = "Prime-time Dead"
days = "daily"                      # or ["sat"], ["mon","wed"], …
window = ["19:00", "20:00"]         # start somewhere in here (local time)
pool = { profile = ["dead"] }       # also: exclude_profile = [...]
prefer = [ { on_this_day = 3.0 }, { years = "1972-1977", weight = 1.5 } ]

[fill]
pool = { exclude_profile = [] }     # empty = everything eligible
variety = { no_repeat_profile = true, no_repeat_artist = true }
```

- **Pools** filter by `profile` (include list) and/or `exclude_profile`. An empty
  pool is everything eligible.
- **Selection score** = recency (never aired highest, then days since last
  aired) + Σ preference weights. Preferences are soft: a slot never goes unfilled
  because nothing matches one. `on_this_day` matches the show's month-day to the
  slot's local date; `years` matches the show date's year range.
- **Planning** walks anchor to anchor over a ~7-day lookahead:
  1. choose the anchor show by score, excluding (when an alternative exists)
     shows whose length would overrun the *next* anchor's window end;
  2. fill the gap with a set of fill-pool shows whose total length lands the next
     anchor inside its window — bounded search maximizing summed score with a
     preference for landing early in the window, subject to variety guards;
  3. if no set lands inside the window: take the closest fit, start the next
     anchor immediately after it (early or late), and record a **window miss**.
     Never cut a show; never leave silence.
- **Exact timing.** Item durations are measured with ffprobe on the actual files
  (DJ clips and tracks), cached; items are separated by a fixed gap (config,
  default 2 s of silence). The plan therefore matches the render exactly.
- **Frozen vs re-plannable.** Everything at or before the render frontier is
  frozen. Everything after it is re-planned on any config or library change.
- **Overlapping anchors** (an anchor's window passes while a previous anchor
  still plays) resolve as a late start + window miss, never a cut.
- **Rotation history:** `aired.jsonl` gains a row per item once its air time
  passes; it drives recency and the web page's recently-played list.

Phase 1 replaces all of this with a trivial planner: eligible packages in a
fixed shuffled order, back to back with the fixed gap.

### Renderer (phase 1)

- **Output:** AAC-LC, 128 kbps CBR, stereo, 44.1 kHz. Container — fMP4 (CMAF)
  or MPEG-TS — chosen by the phase-1 spike; hls.js and Safari handle both.
- **Loudness:** one static gain per scheduled item to an EBU R128 integrated
  target — music −16 LUFS, DJ clips a configurable speech target — plus a −1 dBTP
  true-peak limiter. **Per show, not per track,** so a concert's internal
  dynamics survive. Measurements cached per file.
- **Continuity (the main technical risk).** Encoding in independent chunks
  restarts the AAC encoder (priming samples) at every chunk boundary → an audible
  click/gap. Design: one long-lived encoder — transmitter decodes the plan to PCM
  in order (seeking sample-exactly into the first item on start-up) and pipes it
  to a single ffmpeg HLS muxer that runs faster than real time and emits
  grid-aligned segments. A restart (reboot, crash) costs at most one boundary
  glitch. **Phase-1 spike** must demonstrate: (a) segments land exactly on the
  `E + N·d` grid across item boundaries and across an encoder restart; (b) no
  audible gap at item joins; (c) the restart glitch is ≤ one segment. Fallback if
  (a)/(b) fail: overlapped chunk renders that discard the encoder's priming.
- **Lead:** keep `horizon.last` ≥ now + `lead` (default 72 h ≈ 4 GB at 128 kbps);
  render when below a low-water mark. Steady state ≈ 24 h of audio rendered per
  day.

### Publisher (phase 1)

- Uploads via the R2 S3 API (boto3), segments with
  `Cache-Control: public, max-age=31536000, immutable`, small JSON files with the
  short lifetimes in the contract table.
- Enforces the ordering invariant; retries with backoff; a failed segment upload
  blocks the horizon from advancing past it (and the lead alarm catches a stall).
- Prunes `seg/<N>` once `N·d + E < now − prune_margin` (default 10 min) so
  lagging players don't 404.
- Budget: steady storage ≈ lead × 57.6 MB/h (72 h ≈ 4 GB of the 10 GB-month
  free); Class A ≈ 8,640 segment PUTs/day ≈ 260k/month of 1M free. Whether
  DeleteObject is billed is to be confirmed (believed free) — the guard's price
  table carries it either way.

### antenna (phase 1 minimal, phase 4 full)

Routes (one Worker, one hostname on a Cloudflare zone the operator owns —
the domain's NS records at the registrar point to Cloudflare; partial/CNAME
setup is Business-plan only):

- `/live.m3u8` — live playlist computed from the clock + `horizon.json`: the
  most recent `k` segments (default 6) ending at the current index, with
  `EXT-X-MEDIA-SEQUENCE = N`. Response cache lifetime ≈ `d/2`, so concurrent
  polls share one edge-cached response. Phase 1 measures whether those cached
  hits are billed as Worker requests; if they are, the fallback is a static
  playlist published to R2 by transmitter at a coarser cadence (design note
  below).
- `/seg/*` — served from R2 via the custom-domain cache with **no Worker
  involvement** (route excludes it); requires a Cache Rule covering the segment
  extension.
- `/now.json` — now playing (show, current track or DJ segment, elapsed), up
  next, today's anchors, recently aired; derived from `timeline.json` + clock,
  cached a few seconds.
- `/` — player page; HTML generated per request so Open Graph / Twitter-card
  tags carry the station name and *what's on now*.
- `/embed` — compact iframe widget (play/pause + now-playing line); the main
  page offers a copyable `<iframe>` snippet.
- `/show/<slug>` — show notes from llama's **briefing** (not emcee's DJ script —
  that is written for the ear), the archive.org link, taper lineage, setlist,
  airtimes.

Player: hls.js whenever supported, native HLS fallback (Safari/iOS); pause→play
rejoins the live edge; Media Session API for lock-screen/OS controls; the direct
stream URL (`/live.m3u8`) shown for VLC and apps.

**Failure states (Worker-side, no hugo needed):**
- `now > horizon.last` (hugo behind/down) → serve the fallback loop, aligned to
  the same clock; page says "back shortly".
- `now > horizon.last + offair_after` (default 24 h) → treat as off-air.
- `state/offair.json` says off-air → off-air.
- **Off-air** = a playlist carrying `#EXT-X-ENDLIST` (players stop polling, so
  request volume falls to ~zero) and an off-air notice on the page.

*Fallback design if cached playlist hits bill as Worker requests:* transmitter
publishes `live.m3u8` to R2 itself every `d` seconds as a static object served
by the cache (no Worker on that path). Cost moves to Class A writes
(~8,640 playlist PUTs/day ≈ 260k/month; with segment PUTs ≈ 520k/month, still
inside the free 1M) and the off-air/past-horizon
logic moves to transmitter plus a Worker-free stale-detection fallback in the
player. Chosen only if phase 1's measurement forces it.

### Cost guard (phase 3)

- `transmitter guard` every ~15 min reads Cloudflare GraphQL analytics (Worker
  invocations, R2 Class A/B ops, storage) with an analytics-read-only token, and
  converts to month-to-date dollars via a price table in config ($5 base,
  allowances, overage rates, billing day).
- Projects month-end spend from the run rate. Alerts at actual **or projected**
  50% / 80% of `[guard] monthly_budget_usd`.
- At 100% actual: writes `state/offair.json`. Clears automatically at the
  billing-period rollover, or via `transmitter guard --clear`.
- Estimates concurrent listeners from playlist request rate for `status`.
- **Layered backstops** for when the guard itself is blind: (1) the Worker's
  past-horizon off-air rule bounds unguarded exposure to `lead + offair_after`;
  (2) an "analytics unreadable > 1 h" alarm; (3) setup docs enable Cloudflare's
  own usage-based billing notifications.

### Alerts and operations (phase 3)

- Channels: email (SMTP) and ntfy, both configured; deduplicated per condition.
- Conditions: budget thresholds (actual/projected), off-air tripped, lead below
  floor, station-root marker missing, upcoming window misses, analytics
  unreadable > 1 h, render/publish errors.
- systemd unit runs `transmitter run` (`Restart=always`, logs to journald);
  secrets (R2 keys, CF token, SMTP creds) in an env file readable only by the
  service user.
- `transmitter status`: on air now, lead, next anchors, misses, month-to-date and
  projected cost, listener estimate, active alarms.

## Phases

1. **Thin slice** — trivial in-order planner; renderer with the continuity
   spike; publisher with the ordering invariant and pruning; minimal Worker
   (`/live.m3u8`, past-horizon fallback, off-air via a hand-written
   `state/offair.json`); bare player page; fallback loop; R2 + custom domain +
   Cache Rule setup docs. **Must measure:** segment container; long-lived encoder
   grid alignment and gaplessness; whether edge-cached playlist hits bill as
   Worker requests; a week of real request/op counts at ~1 listener.
   Not public until phase 3 ships.
2. **Scheduler** — anchors, windows, pools (include/exclude), preferences
   (`on_this_day`, `years`), fill search, variety guards, misses, rotation
   history, `schedule`/`library` commands.
3. **Guard + operations** — analytics, budget, projection, automatic off-air,
   email + ntfy alerts, systemd unit, `status`. **Gate:** the station is not
   shared publicly before this ships.
4. **Full antenna** — designed player page, embed, show notes, Open Graph,
   schedule and history, Media Session, stream URL display.

## Testing

- **transmitter:** offline, deterministic pytest, per repo convention. Scheduler
  is pure (library + config + history + clock → plan), tested on fixture
  libraries built from real manifest durations (incl. the 256-show
  distribution). Render tests use short synthetic audio: grid alignment,
  sample-continuity across item joins and across an encoder restart, loudness
  targets. Publish tests use a fake bucket: ordering invariant (horizon never
  ahead of segments), retry, pruning. Guard tests feed canned GraphQL responses
  through every threshold, projection, rollover and `--clear`.
  `test_no_llama_or_emcee_imports.py`.
- **antenna:** vitest with Cloudflare's Workers pool: playlist math at segment
  boundaries and epoch edges, horizon/fallback/off-air transitions,
  `EXT-X-ENDLIST` on off-air, `now.json` derivation. Playwright smoke test of the
  player against `wrangler dev`.

## Non-goals (v1)

On-demand playback; DVR/rewind beyond pause→live; listener accounts; ads or
donations; an Icecast endpoint; any change to llama or emcee code; storing the
library in the cloud; dayparted fill pools; single-set fill; pins.

## Future work

- **Dayparted fill pools** — `[fill]` pools per time range; the selection
  machinery already supports it.
- **Single-set fill** to tighten windows — needs emcee to voice a standalone
  set intro that does not reference unplayed sets.
- **Pins** — a one-off anchor with a fixed show ("Cornell '77, Sat 19:00").
- **Runtime-targeted acquisition in llama** — grow the library at the runtimes
  the scheduler's window misses say it lacks.
- **Icecast relay** for legacy apps, if HLS proves insufficient.
- **Station IDs / interstitials** as short filler to tighten windows further.
