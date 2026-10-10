# Playout: transmitter + antenna — umbrella design

**Date:** 2026-10-09
**Scope:** two new components — `packages/transmitter` (Python, runs on hugo)
and `antenna` (a cron-only Cloudflare Worker plus static objects on one R2
custom-domain hostname). llama, emcee and herder are untouched; the station-root
move is configuration only.
**Review mode:** Fable.
**Status:** umbrella spec. Phase 1 (thin slice) is specified to plan-ready
depth; phases 2–4 are specified at design depth and each gets its own
spec → plan → build cycle before implementation.

## Stakes

What is at risk is **money and on-air continuity**, not data. transmitter only
*reads* the station root; transmitter and antenna write only their own state
(`~/.transmitter/`) and their own R2 bucket. Nothing here deletes or overwrites
anything llama or emcee own, and everything produced is regenerable from the
packages. A bug elsewhere costs dead air, a glitch, a bad schedule, or a re-render.

**One strict surface: spend.** The operator's ceiling is "a few tens of dollars a
month", after which the station is shut down. Cloudflare has no account spending
cap, so the design enforces it: every listener path is a cache-served static
object (no per-listener billing), the clock's `#EXT-X-ENDLIST` playlist stops
players, the WAF kill switch blocks the hostname, and the cost guard fails closed
when it cannot read usage. A defect there can run up an uncapped bill silently;
treat those paths with the rigor of a migration. Secondary but real: the station
must never list a segment that does not exist (players stall), and must never cut
a performance mid-song (an explicit operator rule).

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
- Profiles, delivered: dead 112, bluegrass 65, americana 22, indie 15, southern 14,
  funk 7, livetronica 6, dead-family 6, jam 6, country 2.
- **Broadcast-ready today: 129 — dead 112, indie 15, bluegrass 1, funk 1.** The
  rest await emcee voicing, throttled by the free Voxtral tier at roughly ~100
  shows/month (unmeasured); ~1,000 more shows are packaged in llama and undelivered.
- Source track mp3 ~200 kbps VBR; emcee DJ clips 64 kbps.
- Every package path is relative (`broadcast.m3u`, manifest `filename`s), so the
  same directory may be mounted at different absolute paths on different hosts.
- **Schedule feasibility, simulated** over all 256 delivered packages (voiced or
  not) with a naive random-shuffle filler: whole shows only, no repeats within the
  week, fill excluded dead/funk/dead-family, a no-fit waited to the window start;
  example clock (Dead 07:00 & 19:00 daily, bluegrass 12:00 daily, funk Sat 22:30,
  dead-family Sun 15:00), 50 seeded weeks (1,100 gaps):

  | start window | anchor overran next window | gap not fillable |
  |---|---|---|
  | 60 min | 0.4% | 0.6% |
  | 30 min | 0.5% | 4.9% |
  | 15 min | 0.4% | 9.0% |
  | 5 min  | 0.5% | 12.1% |

  Overruns are fixable by length-aware anchor choice; a real search should beat
  the naive filler at narrow windows. Windowed whole-show scheduling is feasible on
  the delivered library, but the example clock is **not** feasible on today's
  ready library. Library size gates **going on air with the clock**, not
  development: the scheduler is built and measured against every available
  manifest.

### Platform facts (researched 2026-10-09, sourced)

- **R2:** free 10 GB-month Standard storage, 1M Class A, 10M Class B ops/month;
  egress free. Beyond: $0.015/GB-mo, $4.50/M A, $0.36/M B. DeleteObject is free;
  ListObjects is Class A; HeadObject/GetObject are Class B. Edge caching requires
  a custom domain on a Cloudflare zone (r2.dev is uncached); a cache hit does not
  reach R2. Default cache rules do not cache every extension — a Cache Rule must
  cover the hostname.
- **Workers:** Free 100k req/day, 10 ms CPU. Paid $5/mo: 10M req/mo included,
  then $0.30/M; cron min interval 1 min. A Worker in front of the cache is billed
  for cached responses too — the Workers pricing page: "Since Cloudflare Workers
  runs before the Cloudflare cache, the caching of a request still incurs costs",
  and Workers Cache hits "are billed at the same per-request rate". Hence no
  Worker on any listener path.
- **Billing:** no account spending cap. Cloudflare Budget alerts are
  informational, email-only and next-day; usage-based billing notifications need
  a Pro zone and are not available here. Billing periods are anniversary-based
  (UTC), not calendar months; allowances are account-wide.
- **ToS:** Cloudflare's 2023 terms change permits serving large/audio files via
  the CDN when hosted on a Cloudflare service such as R2; whether R2's *free* tier
  counts as the required "Paid Service" is ambiguous. **Decision: run on Workers
  Paid ($5/mo)** — removes the ambiguity and gives the clock Worker Paid limits.
- **Oracle Always Free** (cut to 2 OCPU/12 GB June 2026, idle reclamation,
  capacity scarcity) and **AzuraCast** (no duration-based gap fill) were evaluated
  and rejected; a Liquidsoap VM (Hetzner ~$6.50/mo + R2 fan-out) is the fallback
  architecture if the serverless design fails phase 1.
- **Browser HLS:** native in Safari/iOS; elsewhere hls.js. Chrome's 2025 native
  HLS rollout shipped a playback bug — prefer hls.js whenever
  `Hls.isSupported()`, native only as fallback.

## Architecture

```
 Mac (llama, emcee)         NAS (Synology)                 hugo (Linux, always on)
 ──────────────────         ──────────────                 ───────────────────────
 llama deliver ──SMB──▶  /volume1/media/<station>/  ◀──NFS── transmitter
 emcee run     ──SMB──▶    <package>/…                        plan → render → publish
                                                              alerts ──▶ email + ntfy
                                                                    │ S3 API: audio + data only
                                                                    ▼ (seg/, horizon.json, timeline.json, notes/)
 Cloudflare ──────────────────────────────────────────────────────────────────────────────
                                                              R2 bucket
 antenna clock Worker (cron only, no routes) ◀─R2 binding─▶    + live.m3u8, index.html,
   playlist at every grid boundary                               show/<slug>.html, assets,
   HTML at show boundaries                                       fallback/, state/
   cost guard ──▶ GraphQL analytics, WAF kill switch                 │
   alerts (spend, stall) ──▶ ntfy + email                           │ R2 custom domain
                                                                     ▼
                                                 zone cache — one hostname, static objects only
                                                                     │
                                                                 listeners
```

- **Station root moves to the NAS.** A designated directory on the existing
  Synology `media` share becomes the station root: llama `delivery_path` and emcee
  `[station] root` point at its SMB path on the Mac (`/Volumes/media/<station>`);
  transmitter reads it over NFS on hugo (`/nfs/media/<station>`). The operator
  moves the existing content. No code change in llama or emcee.
  - On macOS an unmounted SMB share's `/Volumes/<name>` normally disappears and
    `/Volumes` is `root:wheel 755`, so llama's `copytree` cannot silently deliver
    to local disk — verified 2026-10-09. Limitation: after an unclean SMB drop
    macOS can leave a stale user-owned `/Volumes/media` and remount at
    `/Volumes/media-1`; the operator confirms `.station-root` is visible from the
    Mac before delivering.
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
  an LLM — it does not in this design. It publishes only audio and data.
- **antenna** (TypeScript, top-level `antenna/` directory in this repo) is one
  cron-only Worker with an R2 binding and **no request routes**, plus the static
  app assets its deploy script uploads to R2; deployed with `wrangler deploy`.
  antenna owns presentation and the cloud-side clock, guard and alerts.
- **One public hostname**, the R2 bucket's custom domain, served entirely through
  Cloudflare's cache. Every object a listener or crawler fetches is a static R2
  object. A cache hit costs nothing and egress is free; a miss costs one Class B.

### The core contract: the stream is a function of the wall clock

transmitter fixes an **epoch** `E` (UTC instant) and a **segment duration** `d`.
Segment `N` always covers `[E + N·d, E + (N+1)·d)`. Every listener hears the same
moment; the playlist is a pure function of the clock and the published inputs,
so nothing holds per-listener state.

`d` is a whole number of AAC frames at 44.1 kHz:
`d = 441 × 1024 / 44100 = 10.24 s` exactly (exact in µs, ms and 90 kHz ticks),
immutable for the life of an epoch. An epoch is identified by `epoch_id`; `E`,
`d` and `epoch_id` are published in `horizon.json`. Changing `E` or `d` is an
**epoch change** (rare, deliberate, documented as a re-render-everything
operation) under a new `epoch_id`.

### R2 object contract (complete)

| key | written by | cache | content |
|---|---|---|---|
| `seg/<epoch_id>/<N>.aac` | transmitter publish | immutable, 1 year | one segment of the grid (plus one init object per epoch if the container is fMP4) |
| `fallback/<version>/<k>.aac` + `fallback/<version>/index.json` | `transmitter fallback render` | immutable | short station-ID loop, never pruned |
| `horizon.json` | transmitter publish | ≤ 5 s | `{epoch_id, epoch, d, first, last, published_at, container}` — `last` is the highest `N` such that every segment `first..last` is present |
| `timeline.json` | transmitter publish | ≤ 30 s | shows with UTC start/end, show metadata, per-file offsets from actual frame positions (DJ clip or track title), upcoming anchors, recently aired |
| `notes/<slug>.json` | transmitter publish | ≤ 1 h | briefing text, archive.org URL, lineage, setlist, airtimes |
| `live.m3u8` | antenna clock | ≈ `d/2` | the live playlist |
| `index.html` | antenna clock, each show boundary | ≤ 60 s | player page with Open Graph tags for the show on air |
| `show/<slug>.html` | antenna clock, when first scheduled into the published horizon | ≤ 1 h | show notes page with per-show Open Graph tags |
| `embed.html`, `offair.html`, app assets (JS/CSS incl. hls.js) | antenna deploy script | ≤ 1 h | static |
| `state/guard.json` | antenna clock (guard) | not served | latest evaluation: time, actual, projected, budget, tripped, reason |
| `state/offair.json` | guard, `transmitter offair` | not served | `{offair: bool, reason, since, until}` |
| `state/budget.json` | `transmitter budget --raise-to` | not served | `{budget_usd, expires}` |
| `state/alerts.json` | antenna clock | not served | alert dedupe state |

**Ordering invariant (strict):** publish uploads segments in ascending `N` and
rewrites `horizon.json` only after every segment it covers is confirmed present
(the PUT's 200). The clock never lists `N > horizon.last`.

## Components

### transmitter — state and commands

State in `~/.transmitter/` (local disk on hugo, never the NFS share):
`config.toml`, `plan.jsonl` (scheduled shows), `aired.jsonl` (rotation history),
`cache/` (per-show decoded sample counts and loudness, keyed by the show's file
set — paths + sizes + mtimes), `render/` (encoded shows and segments awaiting
upload), `alerts.json` (dedupe for hugo-side alerts).

Commands: `plan`, `render`, `publish`, `run` (the service loop running each on
its cadence), `status`, `schedule` (show upcoming plan with window hits/misses),
`library` (pool sizes/hours per anchor vs consumption; `--include-unready`
reports projected pools and feasibility counting unvoiced packages, which stay
ineligible to air), `budget --raise-to <usd>`, `offair on|off`,
`fallback render <audio-file>`, `config init`. Config is strict (unknown keys are
errors), like llama and emcee.

**Station-root guard:** the root must contain a marker file (`.station-root`,
created once by the operator on the share). Missing root or missing marker →
`plan` refuses, an alarm fires, and the library is never treated as empty. (On
hugo a down NFS mount is an ordinary empty directory.)

**Eligibility:** a package is eligible iff it passes emcee's four readiness legs,
reimplemented on files alone — manifest v3+ with non-null `dj_notes` and
`dj-notes.md` present; non-null `dj_audio` with every named clip on disk;
`broadcast.m3u` present; every manifest track's audio on disk — **plus** every
`broadcast.m3u` entry exists, and the newest mtime among `manifest.json`,
`broadcast.m3u` and `dj-audio/*` is older than a quiet period. emcee's atomic
manifest rename is the real guarantee; the quiet period is belt-and-braces. The
playable unit is the package's `broadcast.m3u`, in order.

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
  pool is everything eligible. A package with no `source.profile` is fill-only.
  An anchor whose pool has no eligible show is skipped: its time becomes fill and
  `status` warns.
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
- **Exact timing.** Durations are decoded sample counts from the same decode the
  renderer uses, cached; the plan uses them with the fixed joins (below), and
  `timeline.json` offsets come from actual frame positions.
- **Local time.** Windows resolve via `zoneinfo`: a nonexistent local time (DST
  spring-forward) → the next valid instant; an ambiguous one → its first
  occurrence. hugo runs NTP (setup docs).
- **Frozen means rendered.** Everything already rendered is frozen; everything
  after the render frontier is re-planned on any config or library change. Before
  rendering a show, transmitter re-validates it (every `broadcast.m3u` entry
  exists; cache keys match). On mismatch it skips the whole show at its boundary,
  re-plans from there, and logs a `plan-changed` event.
- **Overlapping anchors** (an anchor's window passes while a previous anchor
  still plays) resolve as a late start + window miss, never a cut.
- **Rotation history:** `aired.jsonl` gains a row per show once its air time
  passes; it drives recency and the web page's recently-played list.

Phase 1 replaces all of this with a trivial planner: eligible packages in a
fixed shuffled order, back to back with the inter-show gap.

### Renderer (phase 1)

- **Output:** AAC-LC, 128 kbps CBR, stereo, 44.1 kHz. Container candidates:
  packed audio (ADTS `.aac` with the ID3 timestamp per RFC 8216) first, fMP4
  second; the phase-1 spike chooses.
- **Per-show encode, frame-count segmentation.** Each show — its whole
  `broadcast.m3u`, gapless-decoded, resampled to 44.1 kHz stereo — is encoded
  once to an AAC-LC frame sequence and cached. Between shows, pre-encoded silent
  frames fill the gap. The station stream is the concatenation, and segment `N`
  is frames `[441N, 441N+441)`: grid alignment by counting, not by ffmpeg cut
  points. Frame 0 is at `E`; each show's last partial frame is padded with
  silence to a whole frame, and the inter-show gap is rounded up to whole frames.
  A restart resumes at any `N` with no glitch; encoder priming at a show start
  lands in the inter-show silence. Rendering is idempotent and parallelisable.
- **Joins:** track→track, zero inserted silence, gapless decode honouring LAME
  encoder delay/padding (segues stay seamless); DJ clip↔track, a configurable
  pause (default 0.75 s); show→show, the inter-show gap (default 2 s). "Show" is
  the unit of scheduling and loudness; "file" is a track or clip.
- **Loudness:** per-show gain = min(target − I_show, −1 dBTP − TP_show), music
  target −16 LUFS, measured over the show's tracks only (DJ clips excluded; same
  decode pass as the durations) and cached keyed by the show's file set. The target is a ceiling, so
  dynamic tapes are not pushed into the limiter; the −1 dBTP true-peak limiter is
  a safety only. Per show, not per track, so a concert's internal dynamics
  survive. DJ clips have their own configurable speech target.
- **Phase-1 spike** must demonstrate: (a) frame-count segments play gaplessly in
  hls.js, Safari/iOS and VLC across segment and show boundaries; (b) each
  segment's timestamp equals `E + N·d` and players accept it; (c) the container.
- **Lead:** keep `horizon.last` ≥ now + `lead` (default 24 h ≈ 1.4 GB at
  128 kbps, configurable); render when below a low-water mark. Steady state
  ≈ 24 h of audio rendered per day. The lead is both how long the station
  survives hugo being down and how long any plan or library change takes to reach
  air. There is no re-plan-from-now: published segment keys are immutable.

### Publisher (phase 1)

- Uploads via the R2 S3 API (boto3), segments with
  `Cache-Control: public, max-age=31536000, immutable`, small JSON files with the
  short lifetimes in the contract table. Epoch-namespaced keys keep 1-year
  immutable caching safe across epoch changes.
- Enforces the ordering invariant; presence is the PUT's 200 (no List calls in
  steady state); retries with backoff; a failed segment upload blocks the horizon
  from advancing past it (and the cloud's lead-floor alert catches a stall).
- Rewrites `horizon.json` and `timeline.json` once per publish batch, not per
  segment.
- Prunes once `E + N·d < now − prune_margin` (default 10 min, so lagging players
  don't 404): advances `horizon.first`, then deletes by computed key range.
- **Recovery after an outage longer than the lead:** start a fresh contiguous run
  (`horizon.first` = resume index), re-plan from the next show boundary after now,
  and log `aired.jsonl` rows only for shows that were published and whose air
  time passed.

### antenna (phase 1 minimal, phase 4 full)

The hostname is on a Cloudflare zone the operator owns (the domain's NS records
at the registrar point to Cloudflare; partial/CNAME setup is Business-plan only).
Listener-facing objects, all static R2 objects behind the cache:

- `live.m3u8` — the stream URL, written by the clock (below); shown on the page
  for VLC and apps.
- `index.html` — the player page. The clock rewrites it at each show boundary
  from a bundled template, so Open Graph / Twitter-card tags carry the station
  name and the show on air (~tens of writes/day).
- `embed.html` — compact iframe widget (play/pause + now-playing line); the main
  page offers a copyable `<iframe>` snippet.
- `show/<slug>.html` — show notes from llama's **briefing** (not emcee's DJ
  script — that is written for the ear), the archive.org link, taper lineage,
  setlist, with per-show Open Graph tags; airtimes are rendered client-side from
  `notes/<slug>.json`, so the static page never goes stale.

**The clock (scheduled Worker).** Cron `* * * * *`. Each invocation reads
`horizon.json`, `timeline.json` and `state/` once via the R2 binding, loops for
its minute (only CPU time is billed, so waiting is free), and at every grid
boundary `E + N·d` writes `live.m3u8`. Overlapping invocations are harmless: the
playlist is a pure function of the clock and its inputs. Playlist rules:

- the last `k` (default 6) segments ending at the current index;
  `EXT-X-MEDIA-SEQUENCE` = the first listed index; `EXT-X-PROGRAM-DATE-TIME` on
  every segment (= `E + N·d`); object `Cache-Control: max-age` ≈ `d/2`;
- **grace:** while `0 < cur − horizon.last ≤ 3`, list up to `horizon.last` (a
  publish retry is not an outage);
- beyond grace, the **fallback loop**: fallback segment `N mod len`, aligned to
  the same grid, with `EXT-X-DISCONTINUITY` at the switch in each direction. The
  stateless discontinuity sequence means a live↔fallback transition may cost
  listeners one player reload or glitch;
- `now > horizon.last + offair_after` (default 24 h), or `state/offair.json`
  says off-air → **off-air**: one fallback-notice segment then `#EXT-X-ENDLIST`.

The clock also alerts when the published lead (`horizon.last` − now) falls below
a floor — catching a hung hugo (e.g. a hard NFS mount hang) that cannot alert for
itself — and runs the cost guard. If the clock stops entirely, the playlist goes stale, players stall, and
requests become cache hits: the cloud side fails toward zero cost.

**Player.** hls.js whenever supported, native HLS fallback (Safari/iOS);
pause→play rejoins the live edge; Media Session API for lock-screen/OS controls.
Now-playing is computed client-side: the player reads the program-date-time of
its current playback position and looks it up in `timeline.json`, refetched only
while playing, at most every few minutes, never while the tab is hidden or
paused. When the playback time has no `timeline.json` entry (the fallback loop),
the page says the station will be back shortly. The embed is a static page doing
the same. On ENDLIST or a 403 the player
stops, shows the off-air notice, and does not auto-reconnect (a manual retry
button). No request stream bills per listener.

**Zone configuration (phase-1 setup docs).** Cache Rule on the hostname:
eligible for cache, ignore query string, respect origin TTL; short edge TTL for
404s (~60 s); Smart Tiered Cache on. A URL-rewrite Transform Rule maps `/` to
`/index.html` (R2 custom domains serve no index document). A WAF custom rule allowlisting the known
path shapes (everything else blocked). One per-IP rate-limiting rule (the free
allowance) at a generous threshold — default ~100 requests / 10 s, block — so
dozens of listeners behind one NAT are fine (a playing stream makes ~2 req/10 s).
`Access-Control-Allow-Origin: *` on stream and data objects, deliberately:
browser-based aggregators and third-party web players must work; native apps are
unaffected by CORS; third-party polling is cache hits and costs nothing.

### Spend budget

Fixed ≈ $5/month (Workers Paid), independent of listeners: ~43k clock
invocations/month; Class A ≈ segments (~8.4k/day) + playlist (~8.4k/day) + small
JSON and HTML rewrites ≈ 520k/month of 1M free; storage ≈ lead × 57.6 MB/h
(24 h ≈ 1.4 GB of 10 GB-month free); Class B ≈ clock reads + per-region cache
refreshes of `live.m3u8`, well inside 10M. Marginal cost per listener ≈ 0. This
is a computation from documented prices, verified by phase 1's week of real
counts.

### Cost guard (phase 3)

Runs in the clock Worker every 15 min, not on hugo, so hugo being down cannot
blind it.

- Reads Cloudflare GraphQL analytics **account-scoped** (all Workers and
  buckets): Workers requests and CPU-ms, R2 Class A/B ops, R2 storage
  (`workersInvocationsAdaptive`, `r2OperationsAdaptiveGroups`,
  `r2StorageAdaptiveGroups`; sampled estimates), with an analytics-read-only token
  held as a Worker secret.
- Prices usage through the allowances with a price table in antenna's config
  (including the $5 base and CPU-ms) for the current billing period (UTC
  anniversary date, configured from the Billing page).
- Projects period-end spend **per meter from a recent window** (last 3 h rate)
  through the allowances, not as a linear month-to-date dollar average.
- Alerts at actual or projected 50% / 80% of `monthly_budget_usd`.
- **Trips** when actual ≥ 90% or projected ≥ 100%. **Fails closed:** no
  successful analytics reading for `blind_after` (default 6 h) → trips with
  reason "guard blind".
- **Trip action, both at once:** (1) write `state/offair.json`, so the clock
  publishes the ENDLIST playlist and players stop gracefully; (2) enable a
  pre-created, disabled WAF custom rule that blocks every path on the hostname
  except `offair.html` and its assets, via an API token scoped to that
  zone's WAF rules. Blocked requests never reach R2 or a Worker. This is the
  actual kill switch.
- **Clearing** is never on a local date alone. At a new billing period the guard
  re-evaluates and clears only if the new period's actual and projection are
  under the thresholds. There is no bare manual clear: `transmitter budget
  --raise-to <usd>` writes `state/budget.json {budget_usd, expires: period end}`,
  which the guard reads, so it stays armed at the raised ceiling; at its next run
  it re-evaluates against that ceiling and clears if under the thresholds.
  Clearing deletes the off-air state and disables the WAF rule. Each run writes
  its evaluation to `state/guard.json`. `transmitter offair on|off` is deliberate
  manual control; `off` reads `state/guard.json` and is refused while the latest
  evaluation is over a trip threshold.
- **Backstops:** (1) structural — listener paths are cache-served static
  objects, so traffic costs ~nothing; (2) the guard's kill switch with its
  fail-closed blindness rule; (3) Cloudflare Budget alerts at 50%/100% (setup
  docs; next-day, informational only, armed from the next cycle).

### Alerts and operations (phase 3)

- **Cloud (clock Worker):** budget thresholds (actual/projected), trip and guard
  blind, published lead below floor. Channels: ntfy (HTTP POST) and email via
  Cloudflare Email Routing's send-email binding to a verified address; deduped
  per condition in `state/alerts.json`.
- **hugo (transmitter):** station-root marker missing, render or publish errors,
  upcoming window misses; email (SMTP) and ntfy.
- systemd unit runs `transmitter run` (`Restart=always`, `WatchdogSec`, logs to
  journald); secrets (R2 keys, SMTP creds) in an env file readable only by the
  service user. The analytics and WAF tokens are Worker secrets.
- `transmitter status`: on air now, lead, next anchors, misses, empty-anchor
  warnings, off-air state, active alarms.

## Phases

1. **Thin slice** — trivial in-order planner over ready packages; per-show
   renderer + frame-count segmenter; publisher with the ordering invariant and
   pruning; antenna clock Worker writing `live.m3u8` (incl. fallback and off-air
   via a hand-written `state/offair.json`); static player page; fallback loop;
   zone configuration and R2 custom-domain setup docs. **Phase-1 verification
   list:** a cron invocation may loop ~60 s with only CPU billed; R2
   custom-domain cache hits incur no Class B; a 5 s origin max-age is honoured
   for `live.m3u8`; the ignore-query-string Cache Rule works on this plan; hls.js,
   Safari/iOS and VLC play the chosen container with PROGRAM-DATE-TIME and stop on
   ENDLIST and on 403; the Email Routing send-email binding is available; GraphQL
   account-scoped queries work with a read-only token and lag by minutes; llama's
   purge flush over SMB to the Synology; a week of real op counts at ~1 listener.
   Not public until phase 3 ships.
2. **Scheduler** — anchors, windows, pools (include/exclude), preferences
   (`on_this_day`, `years`), fill search, variety guards, misses, rotation
   history, `schedule`/`library` commands. Built and measured against every
   available manifest; going on air with the clock waits on the ready library.
3. **Guard + operations** — the guard, kill switch and alerts in the clock
   Worker; `budget` and `offair` commands; hugo alerts, systemd unit, `status`.
   **Gate:** the station is not shared publicly before this ships.
4. **Full antenna** — designed player page, embed, show notes pages, Open Graph,
   schedule and history, Media Session, stream URL display.

## Testing

- **transmitter:** offline, deterministic pytest, per repo convention. Scheduler
  is pure (library + config + history + clock → plan), tested on fixture
  libraries built from real manifest durations (incl. the 256-show
  distribution). Render tests use short synthetic audio: per-show encode +
  frame-count segmentation (gapless track joins, segue joins, DJ pauses, show
  gap), grid timestamps, loudness targets. Publish tests use a fake bucket:
  ordering invariant (horizon never ahead of segments), retry, pruning. Also:
  re-validation skip, outage recovery, `test_no_llama_or_emcee_imports.py`.
- **antenna:** vitest with Cloudflare's Workers pool: clock playlist math (grid
  boundaries, grace, fallback, ENDLIST, epoch keys); guard pricing, projection,
  trip, fail-closed, rollover and raise against canned GraphQL responses.
  Playwright smoke test of the static player against a local R2 emulation.

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
- **Icecast relay** for legacy apps and the many aggregators that expect an
  Icecast/MP3 URL, if HLS proves insufficient.
- **Station IDs / interstitials** as short filler to tighten windows further.
