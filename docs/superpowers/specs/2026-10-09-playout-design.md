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
  HLS rollout shipped a playback bug, so non-Apple browsers use hls.js even where
  native HLS exists; Apple WebKit keeps native HLS for AirPlay and lock-screen
  playback.

## Architecture

```
 Mac (llama, emcee)         NAS (Synology)                 hugo (Linux, always on)
 ──────────────────         ──────────────                 ───────────────────────
 llama deliver ──SMB──▶  /volume1/media/<station>/  ◀──NFS── transmitter
 emcee run     ──SMB──▶    <package>/…                        plan → render → publish
                                                              alerts ──▶ email + ntfy
                                                                    │ S3 API: audio, data, show pages
                                                                    ▼ (seg/, timeline.json, notes/, show/, state/horizon.json)
 Cloudflare ──────────────────────────────────────────────────────────────────────────────
                                                              R2 bucket
 antenna clock Worker (cron only, no routes) ◀─R2 binding─▶    + live.m3u8, index.html,
   cost guard first ──▶ GraphQL analytics, WAF kill switch       assets, fallback/, state/
   playlist at every grid boundary                                   │
   index.html at show boundaries                                     │
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
  an LLM — it does not in this design. It publishes audio, data, and the show
  notes pages rendered from antenna's template.
- **antenna** (TypeScript, top-level `antenna/` directory in this repo) is one
  cron-only Worker with an R2 binding, **no request routes** and no public URL
  (`workers_dev = false`, `preview_urls = false`: a routeless Worker otherwise
  gets a public, billed `*.workers.dev` URL the zone's kill switch cannot reach),
  plus the static app assets its deploy script uploads to R2 and the show-page
  template; deployed with `wrangler deploy`. antenna owns presentation and the
  cloud-side clock, guard and alerts.
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
`d` and `epoch_id` are recorded in `state/horizon.json`. Changing `E` or `d` is an
**epoch change** (rare, deliberate, documented as a re-render-everything
operation) under a new `epoch_id`.

### R2 object contract (complete)

| key | written by | cache | content |
|---|---|---|---|
| `seg/<epoch_id>/<N>.aac` | transmitter publish | immutable, 1 year | one segment of the grid (plus one init object per epoch if the container is fMP4) |
| `fallback/<version>/<k>.aac`, `…/notice.aac`, `…/index.json` | `transmitter fallback render` | immutable | short station-ID loop (segment timestamps `k·d`) and the off-air notice segment; `index.json` carries `len` and the notice key; never pruned |
| `timeline.json` | transmitter publish | ≤ 30 s | shows covering [now − 24 h, `horizon.last`] with UTC start/end, show metadata, per-file offsets from actual frame positions (DJ clip or track title); upcoming anchors; recently aired |
| `notes/<slug>.json` | transmitter publish | ≤ 1 h | briefing text, archive.org URL, lineage, setlist, airtimes |
| `show/<slug>.html` | transmitter publish, from antenna's template | ≤ 1 h | show notes page with per-show Open Graph tags |
| `live.m3u8` | antenna clock | ≈ `d/2` | the live playlist |
| `index.html` | antenna clock | ≤ 60 s | player page with Open Graph tags for the show on air; the off-air page while blocked |
| `embed.html`, `offair.html`, app assets (JS/CSS incl. hls.js) | antenna deploy script | ≤ 1 h | static |
| `state/horizon.json` | transmitter publish | not served | `{epoch_id, epoch, d, first, last, published_at, container, fallback_version}` — `last` is the highest `N` such that every segment `first..last` is present |
| `state/guard.json` | antenna clock (guard) | not served | `tripped`, its reason (`spend`/`blind`), and the latest evaluation: time, actual, projected, budget |
| `state/offair.json` | `transmitter offair` only | not served | the operator's flag: `{offair: bool, reason, since, until}` |
| `state/budget.json` | `transmitter budget --raise-to` | not served | `{budget_usd, expires}` |
| `state/alerts.json` | antenna clock | not served | alert dedupe state |

**Ordering invariant (strict):** publish uploads segments in ascending `N` and
rewrites `state/horizon.json` only after every segment it covers is confirmed
present (the PUT's 200); a show's `notes/<slug>.json` and `show/<slug>.html` are
uploaded before the `timeline.json` that first references the slug. The clock
never lists `N > horizon.last`, and treats `N < horizon.first` as absent.

## Components

### transmitter — state and commands

State in `~/.transmitter/` (local disk on hugo, never the NFS share):
`config.toml`, `plan.jsonl` (scheduled shows), `aired.jsonl` (rotation history),
`cache/` (per-show decoded sample counts and loudness, keyed by the show's file
set — paths + sizes + mtimes), `render/` (encoded shows and segments awaiting
upload), `alerts.json` (dedupe for hugo-side alerts), the daily PUT count, and a
flock serialising publish and prune (a manual `publish` while `run` publishes
would otherwise race on `state/horizon.json`).

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

### Scheduler (phase 3)

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

- **Output:** AAC-LC, 128 kbps CBR, stereo, 44.1 kHz. *(As built, 2026-10-10:
  ffmpeg's native `aac` encoder is ABR-like — silence encodes to small frames —
  so output is ~128 kbps on average, not strict CBR. Nothing depends on a
  constant frame size: the grid counts frames, not bytes, and storage should come
  in at or under the estimate below (not yet measured).)* Container candidates:
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
  lands in the inter-show silence. A show's frame count is the encoder's output
  including its flush frames; `timeline.json` offsets add the encoder's
  declared priming delay to a show's frame position (content sample `s` airs at
  stream sample `start + priming + s`). Rendering is idempotent and parallelisable.
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
  segment's embedded timestamp is `(N·d·90000) mod 2^33` in 90 kHz ticks for
  packed audio (or `tfdt = N·d` for fMP4), the wall clock being carried by
  `EXT-X-PROGRAM-DATE-TIME`, and players accept it, including across a 2^33 wrap
  (`E` seeded so a wrap falls in the test window); (c) the container; (d) iOS
  lock-screen playback for 10 min, and AirPlay.
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
- Rewrites `state/horizon.json` and `timeline.json` once per publish batch, not
  per segment. Publish and prune hold the local flock.
- Renders `show/<slug>.html` from antenna's template (in `antenna/`; transmitter
  reads it) and uploads it with `notes/<slug>.json`, under the ordering invariant.
- **Own-write caps:** a local daily PUT budget (default 2× the expected count);
  exceeding it stops publishing and alerts. Publishing also stops while
  `state/guard.json` says tripped (read via the S3 API at most every 15 min,
  ~3k Class B/month).
- Prunes once `E + N·d < now − prune_margin` (default 10 min, so lagging players
  don't 404): advances `horizon.first`, then deletes by computed key range.
  *(As built, 2026-10-10: `prune_margin_minutes` has a floor of 4 minutes,
  `PRUNE_MARGIN_FLOOR_MINUTES`, derived from the live window + grace (9 × 10.24 s),
  the playlist's max-age and a 120 s player-lag allowance; a value below it is a
  `ConfigError`, not merely `≥ 0`.)*
- *(As built, 2026-10-10: transmitter never writes a horizon without a recorded
  fallback version. Publish uploads nothing — no segment, no horizon — until
  `transmitter fallback render` has recorded one; prune stops (`no-fallback`,
  before its horizon PUT and before any delete) if the record is lost later; and
  `fallback render` writes the horizon only with its own version. So every
  `state/horizon.json` names a `fallback_version`.)*
- **Recovery after an outage longer than the lead:** a fresh contiguous run
  starts a short margin after now (the old run is left to prune) and begins a new
  show there;
  `aired.jsonl` gets rows only for shows published and past their air time.

### antenna (phase 1 minimal, phase 4 full)

The hostname is on a Cloudflare zone the operator owns (the domain's NS records
at the registrar point to Cloudflare; partial/CNAME setup is Business-plan only).
Listener-facing objects, all static R2 objects behind the cache:

- `live.m3u8` — the stream URL, written by the clock (below); shown on the page
  for VLC and apps.
- `index.html` — the player page. The clock rewrites it at each show boundary
  from a bundled template, so Open Graph / Twitter-card tags carry the station
  name and the show on air (~tens of writes/day); while the station is blocked
  it holds the off-air page.
- `embed.html` — compact iframe widget (play/pause + now-playing line); the main
  page offers a copyable `<iframe>` snippet.
- `show/<slug>.html` — show notes from llama's **briefing** (not emcee's DJ
  script — that is written for the ear), the archive.org link, taper lineage,
  setlist, with per-show Open Graph tags; published by transmitter from antenna's
  template. Airtimes are rendered client-side from `notes/<slug>.json`, so the
  static page never goes stale.

**The clock (scheduled Worker).** Cron `* * * * *`. Each invocation first runs
the cost guard step (below), which also reconciles the blocked state; then reads
`state/horizon.json`, `timeline.json` and `state/` once via the R2 binding,
writes the current playlist immediately, and loops until ~fire + 75 s (only CPU
time is billed, so waiting is free), writing `live.m3u8` at every grid boundary
`E + N·d` — at most `ceil(75/d) + 2` PUTs per invocation, skipping any whose
bytes equal the last written — *(as built, 2026-10-10: the cap does not trust its
inputs: it is `min(MAX_PUTS, ceil(loopMs/d) + 2)` with a hard `MAX_PUTS = 10`; a
horizon whose `d` is not exactly 10.24 is refused (nothing written, logged
`horizon-refused`); and a configured `LOOP_SECONDS` above 75 is clamped to 75 s,
logged `loop-clamped`)* — and rewriting `index.html` at a show boundary or
a change of blocked state. Overlapping invocations are harmless: the playlist is
a pure function of the clock and its inputs. Playlist rules:

- the last `k` (default 6) segments ending at the current index;
  `EXT-X-MEDIA-SEQUENCE` = the first listed index; `EXT-X-PROGRAM-DATE-TIME` on
  every segment (= `E + N·d`); object `Cache-Control: max-age` ≈ `d/2`;
- **grace:** while `0 < cur − horizon.last ≤ 3`, list up to `horizon.last` (a
  publish retry is not an outage);
- beyond grace, the **fallback loop** named by `fallback_version`: fallback
  segment `N mod len`, aligned to the same grid, with `EXT-X-DISCONTINUITY`
  before segment 0 of every loop iteration and at each switch in either
  direction; during pure fallback the discontinuity sequence is `floor(N/len)`.
  *(As built, 2026-10-10: fallback segment `N` carries discontinuity number
  `floor(N/len) + 1`, and `EXT-X-DISCONTINUITY-SEQUENCE` is chosen so that it
  does. With `floor(N/len)` the sequence had to be clamped at 0 early in an
  epoch (`N < len`), which renumbered segments between reloads — RFC 8216
  §6.2.2 requires every remaining segment to keep its number.)*
  A live↔fallback transition may cost listeners one player reload or glitch;
- blocked (see Cost guard), or `now > horizon.last + offair_after` (default
  24 h) → **off-air**: the notice segment `fallback/<version>/notice.aac`, then
  `#EXT-X-ENDLIST`. *(As built, 2026-10-10: when off-air applies but no usable
  fallback exists — `fallback_version` null, its `index.json` missing or
  unreadable, or `len < 1` — the clock writes an ENDLIST-only playlist: header,
  `EXT-X-MEDIA-SEQUENCE` by the same rule as the notice playlist, and
  `#EXT-X-ENDLIST`, with no segments. Players stop without the notice; the clock
  logs `offair-without-fallback` once per invocation. Outside off-air, a window
  that would need a missing fallback is still not written at all.)*

*(As built, 2026-10-12, amendment A4: the cron measurably lags. A 13.6 h
`wrangler tail` capture (846 invocations, 2026-10-11/12) gave lag median 15 s,
p99 77 s, max 117 s, with every daytime :00/:30 fire over 25 s, so the 6-segment
window above let players stall. A lookahead alone adds no runway (it moves the
listed end and a player's start point together); runway comes from where players
start relative to the listed end. The live playlist therefore lists
`PLAYLIST_WINDOW` 16 segments, ending `PLAYLIST_LOOKAHEAD` 12 past the one
airing (cap 16), with the grace hold and the fallback switch applied to that end
(cur + lookahead), and carries `#EXT-X-START:TIME-OFFSET=-122.880` and
`#EXT-X-SERVER-CONTROL:HOLD-BACK=122.880` (`PLAYLIST_HOLD_BACK` 12 segments;
emitted only when hold-back·d >= 3·TARGETDURATION, clamped to the listed
entries − 1). Players that honour them start ~123 s from the listed end (113–120 s measured on iOS), i.e.
near the wall clock (0-10 s ahead); players that ignore the tags (VLC) sit ~90 s
ahead with ~30 s of runway. Keep lookahead = hold-back: hugo's dead-clock check
dates the playlist by its newest segment minus its own hold-back. Measured on a
real iPhone: playlist freezes up to 60 s play through, 75-90 s freezes give a
1-3 s self-healing drop. The off-air notice is numbered
`indexAt(max(scheduledTime + loopMs, now)) + lookahead + 1`, strictly above any
live segment an earlier write could list. An already-playing native-Safari page
therefore shows the off-air/kill-switch state only after its ~120 s buffer plays
out (~2.5 min, against the plan's ~45 s estimate for A2; spend is unaffected). hls.js takes its
latency from the playlist's HOLD-BACK (`maxBufferLength` 130).)*

*(As built, 2026-10-12, amendment A1, a documented limitation with no code: at a
fallback→live switch of a fresh run — the first start, an outage longer than the
published lead, or a re-epoch — `EXT-X-DISCONTINUITY-SEQUENCE` restarts at 0.
hls.js and Safari follow it; VLC goes silent and needs stop/play once.)*

The clock also alerts when the published lead (`horizon.last` − now) falls below
a floor — catching a hung hugo (e.g. a hard NFS mount hang) that cannot alert for
itself. If the clock stops entirely, the playlist goes stale, players stall, and
requests become cache hits: the cloud side fails toward zero cost, and
transmitter alerts on the stale playlist (Alerts, below).

**Player.** Native HLS on Safari and every iOS browser (all iOS browsers are
WebKit; detected by platform/vendor, not by `canPlayType` alone, which is also true
on Chrome with native HLS) — keeps AirPlay and lock-screen playback; hls.js
elsewhere; pause→play rejoins the live edge; Media Session API
for lock-screen/OS controls. Now-playing is computed client-side: the player
reads the program-date-time of its current playback position and looks it up in
`timeline.json`, refetched only while playing, at most every few minutes, never
while the tab is hidden or paused. When the playback time has no `timeline.json`
entry (the fallback loop), the page says the station will be back shortly. The
embed is a static page doing the same. On ENDLIST or a 403 the player stops,
shows the off-air notice, and does not auto-reconnect (a manual retry button).
No request stream bills per listener.
*(As built, 2026-10-12, amendment A2: the player also watches playback progress
itself. After 15 s without progress it probes `live.m3u8` with
`cache: "no-store"` (a cache hit or the WAF's 403, at most every 10 s, one at a
time); two consecutive definitive verdicts — a 403, or a playlist ending in
`#EXT-X-ENDLIST` — show the off-air notice. Network errors, 5xx, 429 or a live
playlist are not verdicts, and any progress resets the watch. While stalled the
now-playing line reads "Reconnecting…", and an hls.js error with
`networkDetails.status` 403 maps to off-air.)*

**Zone configuration (phase-1 setup docs).** Preconditions: a Cloudflare account
dedicated to the station (the guard's account-scoped meters then mean what they
say); no paid zone add-ons (Argo, Cache Reserve, Load Balancing — the guard
cannot see them; the Budget alert is their only backstop); Workers
observability/logs off or within the free allowance; Budget alerts at 50%/100%
of `monthly_budget_usd − $5` (they exclude subscription fees). Cache Rule on the
hostname: eligible for cache, ignore query string, respect origin TTL (404s keep
the default 3-min edge TTL, not settable on Free); Browser Cache TTL = Respect
Existing Headers (else browsers serve a stale `live.m3u8` from local cache);
Smart Tiered Cache on. A URL-rewrite Transform Rule maps `/` to `/index.html`
(R2 custom domains serve no index document). A WAF custom rule allowlists the
served keys with `eq`/`in`/`starts_with`/`ends_with` (`wildcard` if phase 1
confirms it on Free; `matches` is Business+) and blocks everything else,
`state/` included. The kill-switch rule, pre-created and disabled, blocks
everything except `/`, `/index.html`, `offair.html` and its assets (Free zones
cannot customise block pages). One per-IP rate-limiting rule (the free
allowance) at a generous threshold — default ~100 requests / 10 s, block — so
dozens of listeners behind one NAT are fine (a playing stream makes ~2 req/10 s).
A Response Header Transform Rule sets a static `Access-Control-Allow-Origin: *`
on the hostname (R2's own CORS policy answers only requests carrying `Origin`,
so a cached non-CORS response would lack it), deliberately: browser-based
aggregators and third-party web players must work; native apps are unaffected by
CORS; third-party polling is cache hits and costs nothing.

### Spend budget

Fixed ≈ $5/month (Workers Paid), independent of listeners: ~43k clock
invocations/month; Class A ≈ segments (~8.4k/day ≈ 255k/month) + playlist
(boundaries plus each invocation's immediate write and overlap, ≤ ~12k/day
≈ 360k/month) + small JSON and HTML rewrites ≈ 620k/month of 1M free; storage ≈ lead × 57.6 MB/h (24 h ≈ 1.4 GB of
10 GB-month free); Class B ≈ clock reads + transmitter's guard-state reads (~3k)
+ per-region cache refreshes of `live.m3u8`, well inside 10M. Marginal cost per
listener ≈ 0. This is a computation from documented prices, verified by phase 1's
week of real counts.

### Cost guard (phase 2)

Runs in the clock Worker, not on hugo, so hugo being down cannot blind it —
first in every invocation, in its own try/finally. It evaluates (reads and prices
usage) whenever `state/guard.json`'s evaluation is ≥ 15 min old, not on a minute
modulo; any exception there counts as a failed reading. The blind rule and
reconciliation run in the finally, every invocation; playlist and `index.html`
work follow, never precede it.

- Reads Cloudflare GraphQL analytics **account-scoped** (all Workers and
  buckets): Workers requests, R2 Class A/B ops, R2 storage
  (`workersInvocationsAdaptive`, `r2OperationsAdaptiveGroups`,
  `r2StorageAdaptiveGroups`; sampled estimates), with an analytics-read-only token
  held as a Worker secret. CPU is not metered: the dataset exposes it only as
  percentiles, and the clock's CPU is bounded by design (capped writes).
- Prices usage through the allowances with a price table in antenna's config
  (including the $5 base) for the current billing period (UTC anniversary date,
  configured from the Billing page).
- Projects period-end spend **per meter from a recent window** (last 3 h rate)
  through the allowances, not as a linear month-to-date dollar average.
- Alerts at actual or projected 50% / 80% of `monthly_budget_usd`.
- *(As built, 2026-10-12, amendment A5, free-plan facts: a free zone has at most
  5 custom rules and 2 are already used, so the guard creates no rules and only
  toggles the existing kill switch, found by its exact description (zero or
  several matches, or an action other than `block`, is an error). GraphQL
  operations lag 1-2 minutes and storage about 45 minutes, so the 3 h rate window
  ends 5 minutes before now. Storage is priced at the period's peak bytes, an
  upper bound on R2's average-of-daily-peaks. An R2 action type the code does not
  know is priced as Class A and listed in `guard.json`. The player's probe and
  hugo's dead-clock check are cache hits on `live.m3u8`.)*

**Blocking** rests on two independent flags:

- **`tripped`** — a latch owned by the guard, in `state/guard.json` with its
  reason. **Set** when actual ≥ 90% or projected ≥ 100% (reason `spend`), or
  when no analytics reading has succeeded for `blind_after` (default 6 h; reason
  `blind`). A successful reading over a threshold always leaves (or sets) the
  latch with reason `spend`. **Cleared** only: for `blind`, by the first
  successful reading under the thresholds; for `spend`, at a new billing period or after `transmitter
  budget --raise-to <usd>` (which writes `state/budget.json {budget_usd, expires:
  period end}`), in either case only if the guard's next evaluation is under the
  thresholds. Nothing else clears it.
- **`offair`** — owned by the operator alone: `transmitter offair on|off` writes
  `state/offair.json`; the guard never writes or clears it, and `offair off`
  clears only this flag.

**Blocked = `tripped` OR `offair`**, reconciled every invocation: blocked means
the ENDLIST off-air playlist, the off-air page in `index.html` and the
kill-switch WAF rule enabled (an API token scoped to the zone's WAF rules;
blocked requests never reach R2 or a Worker); not blocked, the opposite.
Level-triggered: each run reads the rule's actual state and corrects it; a
Rulesets API failure raises a deduped alert and is retried next run. So
`offair on` blocks fully — the takedown path for an objection is not
cooperative-only. Limitation: while the WAF API is unreachable a block is
cooperative-only (ENDLIST + off-air page), the alert repeating, until a later
run succeeds.

**Backstops:** (1) structural — listener paths are cache-served static objects,
so traffic costs ~nothing; (2) caps on the station's own writers, its only
Class A sources; (3) the kill switch with its fail-closed blindness rule;
(4) Cloudflare Budget alerts (phase-1 setup; next-day, informational only).

### Alerts and operations (phase 2)

- **Cloud (clock Worker):** budget thresholds (actual/projected), `tripped`
  (spend or blind), Rulesets API failures, published lead below floor. Channels:
  ntfy (HTTP POST) and email via Cloudflare Email Routing's send-email binding to
  a verified address; deduped per condition in `state/alerts.json`.
  *(As built, 2026-10-12, amendment A3: `antenna/wrangler.jsonc` commits an
  unrestricted `send_email` binding `ALERT_EMAIL`, which can only reach the
  account's verified addresses. The destination exists only as the Worker secret
  `ALERT_EMAIL_TO` and the sender as `ALERT_EMAIL_FROM`; `wrangler.jsonc` holds no
  address and no `account_id`, and a test enforces both. Mail is a minimal
  RFC 5322 `text/plain` sent with `EmailMessage` from `cloudflare:email`.)*
- **hugo (transmitter):** station-root marker missing, render or publish errors,
  daily PUT budget exceeded, upcoming window misses; email (SMTP) and ntfy.
- **Dead clock:** `transmitter run` fetches the public `live.m3u8` once a minute
  (a cache hit) and alerts when its newest `EXT-X-PROGRAM-DATE-TIME` is older
  than ~3·d, or `state/guard.json` is older than ~30 min (optional second
  channel: Cloudflare's Worker-error notification). *(As built, 2026-10-12:
  `dead_clock_seconds` defaults to 120 s on two consecutive checks (minimum 31),
  because of the measured cron lag, and the playlist is dated by its newest
  segment's start minus its own hold-back; `guard_stale_minutes` defaults to 45.)*
- systemd unit runs `transmitter run` (`Restart=always`, `WatchdogSec`, logs to
  journald); secrets (R2 keys, SMTP creds) in an env file readable only by the
  service user. The analytics and WAF tokens are Worker secrets.
- `transmitter status`: on air now, lead, next anchors, misses, empty-anchor
  warnings, `tripped` (with reason) and `offair`, active alarms.

## Phases

1. **Thin slice** — trivial in-order planner over ready packages; per-show
   renderer + frame-count segmenter; publisher with the ordering invariant,
   pruning and own-write caps; antenna clock Worker writing `live.m3u8` (incl.
   fallback and off-air via a hand-written `state/offair.json`); static player
   page; fallback loop; zone configuration, R2 custom-domain setup docs and
   Budget alerts. **Phase-1 verification list:** a cron invocation may loop ~75 s
   with only CPU billed; scheduled-vs-actual cron fire times over a day; R2
   custom-domain cache hits incur no Class B; a 5 s origin max-age is honoured
   for `live.m3u8` at the edge and, under Browser Cache TTL = Respect Existing
   Headers, in browsers; the ignore-query-string Cache Rule works on this plan;
   whether `wildcard` rule expressions are available on Free; the Worker's
   `*.workers.dev` URL serves no Worker (curl); hls.js, Safari/iOS and VLC play
   the chosen container with PROGRAM-DATE-TIME and stop on ENDLIST and on 403;
   archive.org MP3 derivatives carry LAME/Xing gapless info (check one segued
   pair); the Email Routing send-email binding is available; GraphQL
   account-scoped queries work with a read-only token and lag by minutes; llama's
   purge flush over SMB to the Synology; a week of real op counts at ~1 listener.
2. **Guard + operations** — the guard, blocking and kill switch, and alerts in
   the clock Worker; `budget` and `offair` commands; hugo alerts incl. the
   dead-clock check, systemd unit, `status`. **Gate:** the station is not shared
   publicly before this ships; once it has, the trivial planner can go public.
3. **Scheduler** — anchors, windows, pools (include/exclude), preferences
   (`on_this_day`, `years`), fill search, variety guards, misses, rotation
   history, `schedule`/`library` commands. Built and measured against every
   available manifest; going on air with the clock waits on the ready library,
   which is why it follows the guard.
4. **Full antenna** — designed player page, embed, show notes pages and their
   template, Open Graph, schedule and history, Media Session, stream URL display.

## Testing

- **transmitter:** offline, deterministic pytest, per repo convention. Scheduler
  is pure (library + config + history + clock → plan), tested on fixture
  libraries built from real manifest durations (incl. the 256-show
  distribution). Render tests use short synthetic audio: per-show encode +
  frame-count segmentation (gapless track joins, segue joins, DJ pauses, show
  gap, flush frames, priming offset), grid timestamps incl. the 2^33 wrap,
  loudness targets. Publish tests use a fake bucket: ordering invariant (horizon
  never ahead of segments; notes and show page before their timeline), retry,
  pruning, flock, daily PUT budget, stop while tripped. Also: re-validation
  skip, outage recovery, dead-clock alert, `test_no_llama_or_emcee_imports.py`.
- **antenna:** vitest with Cloudflare's Workers pool: clock playlist math (grid
  boundaries, grace, `N < horizon.first`, fallback discontinuities, ENDLIST,
  epoch keys), PUT cap and identical-bytes skip; guard-first ordering and its
  finally; pricing, projection, `tripped` set/clear per reason, `offair`
  independence, WAF reconciliation and API-failure retry, rollover and raise,
  against canned GraphQL responses.
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
