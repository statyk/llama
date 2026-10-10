# Round-1 decisions for docs/superpowers/specs/2026-10-09-playout-design.md

Apply every decision exactly. Keep the spec's voice (what and why; no review/round
labels, no history). Keep it tight: where a section is replaced, replace it; do not
leave the old design alongside. The operator approved the foundation change (group A).

## A. Spend architecture — NOTHING BILLED ON ANY LISTENER PATH (foundation change)

A0. Evidence to cite in Platform facts (replace the "not documented — measured in
phase 1" bullet): Cloudflare's Workers pricing page: "Since Cloudflare Workers runs
before the Cloudflare cache, the caching of a request still incurs costs", and Workers
Cache hits "are billed at the same per-request rate". There is no account spending cap;
Cloudflare Budget alerts are informational, email-only, next-day. Also: DeleteObject is
free on R2 (resolved; remove the "to be confirmed" note); ListObjects is Class A;
HeadObject/GetObject Class B. Usage-based billing notifications require a Pro zone —
not available; the usable product is Budget alerts. Billing periods are anniversary-
based (UTC), not calendar months; allowances are account-wide.

A1. One public hostname, served entirely from the R2 custom domain through Cloudflare's
cache. Every object a listener or crawler fetches is a static R2 object: `index.html`,
`embed.html`, app assets (JS/CSS incl. hls.js), `show/<slug>.html`, `live.m3u8`,
segments, `timeline.json`, `notes/<slug>.json`. A cache hit costs nothing and egress is
free; a miss costs one Class B. **antenna has no request routes at all** — the Worker is
cron-only. Remove: the `/live.m3u8` Worker route, `/now.json` (route and object), the
per-request HTML generation, the route-exclusion text for `/seg/*`, Workers Cache, and
the phase-1 measurement of whether cached Worker hits are billed. Remove the old
"Fallback design if cached playlist hits bill" paragraph (its idea is now the primary
design, below).

A2. **The clock (antenna's scheduled Worker).** Cron `* * * * *` (Workers Paid; a cron
invocation may run for minutes and only CPU time is billed, so waiting is free — listed
as a phase-1 verification). Each invocation loops for its minute and, at every grid
boundary `E + N·d`, writes `live.m3u8` to R2 computed from the clock + `horizon.json` +
off-air state (read once per invocation via the R2 binding). Overlapping invocations are
harmless: the playlist is a pure function of the clock and inputs. Playlist rules:
the last `k` (default 6) segments ending at the current index; `EXT-X-MEDIA-SEQUENCE` =
first listed index; `EXT-X-PROGRAM-DATE-TIME` on every segment (= `E + N·d`); object
`Cache-Control: max-age` ≈ d/2. Grace: while `0 < cur − horizon.last ≤ 3` list up to
`horizon.last` (a publish retry is not an outage); beyond that, the fallback loop.
Fixed cost independent of listeners: ~43k invocations + ~260k Class A/month for the
playlist, plus per-region cache refreshes of `live.m3u8` (Class B, well inside free).
If the clock stops entirely, the playlist goes stale, players stall, and requests become
cache hits — the cloud side fails toward zero cost.

A3. **The clock Worker also renders the HTML.** antenna owns presentation: it rewrites
`index.html` at each show boundary from a bundled template (so Open Graph tags carry
the station name and the show on air — ~tens of writes/day), and writes
`show/<slug>.html` (static, with per-show OG tags) when a show is first scheduled into
the published horizon. transmitter publishes only audio and data (segments, `horizon.json`,
`timeline.json`, `notes/<slug>.json`). App assets (JS/CSS/embed) are uploaded to R2 by
antenna's deploy script.

A4. **Now-playing is computed client-side.** The player reads the program-date-time of
its current playback position (hls.js / native) and looks it up in `timeline.json`
(cached, short TTL). `timeline.json` is refetched only while playing, at most every few
minutes, and never while the tab is hidden or paused. The embed is a static page doing
the same. On ENDLIST or a 403 the player stops, shows the off-air notice, and does not
auto-reconnect (manual retry button). No request stream exists that bills per listener.

A5. **The cost guard runs in the clock Worker** (every 15 min), not on hugo, so hugo
being down cannot blind it.
- Reads Cloudflare GraphQL analytics **account-scoped** (all Workers and buckets):
  Workers requests and CPU-ms, R2 Class A/B ops, R2 storage (datasets
  `workersInvocationsAdaptive`, `r2OperationsAdaptiveGroups`, `r2StorageAdaptiveGroups`;
  sampled estimates) with an analytics-read-only token held as a Worker secret.
- Prices usage through the allowances with a price table in config (includes the $5
  base and CPU-ms), for the current billing period (UTC anniversary date, configured
  from the Billing page).
- Projects period-end spend **per meter from a recent window** (last 3 h rate) through
  the allowances (not a linear month-to-date dollar average).
- Alerts at actual or projected 50% / 80% of `monthly_budget_usd`.
- **Trips** when actual ≥ 90% or projected ≥ 100%.
- **Fails closed:** no successful analytics reading for `blind_after` (default 6 h) →
  trips with reason "guard blind".
- Trip action, both at once: (1) write `state/offair.json` → the clock publishes an
  ENDLIST playlist (one fallback-notice segment then `#EXT-X-ENDLIST`) so players stop
  gracefully; (2) **enable a pre-created, disabled WAF custom rule** that blocks every
  path on the hostname except the static off-air page and its assets, via an API token
  scoped to that zone's WAF rules. Blocked requests never reach R2 or a Worker. This is
  the actual kill switch.
- Clearing: never on a local date alone. At a new billing period the guard
  re-evaluates and clears only if the new period's actual and projection are under the
  thresholds. A bare manual clear does not exist: `transmitter budget --raise-to <usd>`
  writes `state/budget.json {budget_usd, expires: period end}` which the guard reads
  (the guard stays armed at the raised ceiling). `transmitter offair on|off` exists for
  deliberate manual control; `off` is refused while the guard would immediately re-trip.
- Alert channels from the Worker: ntfy (HTTP POST) and email via Cloudflare Email
  Routing's send-email binding to a verified address (availability = phase-1/3
  verification). Dedupe state in `state/alerts.json`.
- Layered backstops become: (1) structural — listener paths are cache-served static
  objects, so traffic costs ~nothing; (2) the guard's kill switch with fail-closed
  blindness rule; (3) Cloudflare Budget alerts configured at 50%/100% (setup docs;
  note next-day latency, informational only, armed from the next cycle).

A6. **Zone hardening (phase-1 setup docs, configuration only):** Cache Rule on the
hostname: eligible for cache, **ignore query string**, respect origin TTL; short edge
TTL for 404s (~60 s); Smart Tiered Cache on. A WAF custom rule allowlisting the known
path shapes (everything else blocked). One per-IP rate-limiting rule (the free
allowance) at a generous threshold — default ~100 requests / 10 s, block — sized so
dozens of listeners behind one NAT are fine (a playing stream makes ~2 req/10 s).
**CORS: `Access-Control-Allow-Origin: *` on stream and data objects**, deliberately:
browser-based aggregators and third-party web players must work (shareability goal);
native apps are unaffected by CORS either way; in this design third-party polling is
cache hits and costs nothing.

A7. **Spend budget paragraph** (replace the old one): fixed ≈ $5/month (Workers Paid);
Class A ≈ segments (~8.4k/day at d = 10.24 s) + playlist (~8.4k/day) + small JSON
rewrites ≈ 520k/month of 1M free; storage ≈ lead × 57.6 MB/h; Class B ≈ clock reads +
per-region cache refreshes, well inside 10M; marginal cost per listener ≈ 0. State that
this is a computation from documented prices, verified by phase 1's week of counts.

A8. Stakes paragraph: update the list of spend-enforcing mechanisms to match (static
listener paths, the clock's ENDLIST, the WAF kill switch, fail-closed guard), and keep
"spend" as the one strict surface.

## B. Rendering and the R2 contract

B1. **Replace the long-lived encoder with per-show encode + frame-count segmentation.**
d = 441 × 1024 / 44100 = **10.24 s exactly** (exact in µs, ms and 90 kHz ticks). Each
show (its whole `broadcast.m3u`, gapless-decoded, resampled to 44.1 kHz stereo) is
encoded once to an AAC-LC frame sequence and cached; between shows, pre-encoded silent
frames fill the gap; the station stream is the concatenation, and segment N is frames
[441N, 441N+441) — grid alignment by counting, not by ffmpeg cut points. A restart
resumes at any N with no glitch; encoder priming at a show start lands in the inter-show
silence. Rendering is idempotent and parallelisable. Container candidates: packed audio
(ADTS `.aac` with the ID3 timestamp per RFC 8216) first, fMP4 second. Remove the
"continuity is the main technical risk" paragraph, the restart-glitch criterion and the
overlapped-chunk fallback. New phase-1 spike criteria: (a) frame-count segments play
gaplessly in hls.js, Safari/iOS and VLC across segment and show boundaries; (b) each
segment's timestamp equals `E + N·d` and players accept it; (c) container chosen.

B2. **Joins, defined:** track→track: zero inserted silence, gapless decode honouring
LAME encoder-delay/padding (segues stay seamless); DJ clip↔track: a configurable pause
(default 0.75 s); show→show: the inter-show gap (default 2 s). Use "show" consistently
as the unit of scheduling and loudness, "file" for tracks/clips; remove the ambiguous
"item".

B3. **Durations are decoded sample counts** (from the same decode the renderer uses),
cached; the plan uses them and `timeline.json` offsets come from actual frame positions.
Remove "measured with ffprobe … matches the render exactly".

B4. **Loudness:** per-show gain = min(target − I_show, −1 dBTP − TP_show) — the target
is a ceiling, so dynamic tapes are not pushed into the limiter; the limiter is a safety
only. Measured over the whole-show decode (same pass as B3), cached keyed by the show's
file set (paths + sizes + mtimes). DJ clips have their own speech target.

B5. **Keys are namespaced by epoch:** `seg/<epoch_id>/<N>.aac` (and an init key per
epoch if fMP4); `fallback/<version>/<k>.aac`. `horizon.json` carries `epoch_id`. This
also makes immutable 1-year edge caching safe across epoch changes.

B6. **Fallback loop:** rendered by `transmitter fallback render <audio-file>` with the
identical encoder settings; the clock lists fallback segment `N mod len` aligned to the
same grid, with `EXT-X-DISCONTINUITY` at the switch in each direction. Documented
limitation: the stateless discontinuity sequence means a live↔fallback transition may
cost listeners one player reload or glitch.

B7. **Publisher:** presence = the PUT's 200 (no List calls in steady state); prune by
computed key range after advancing `horizon.first`; rewrite `horizon.json` /
`timeline.json` once per publish batch, not per segment.

B8. **Clocks and DST:** hugo runs NTP (setup docs); windows resolve via `zoneinfo`
(nonexistent local time → next valid instant; ambiguous → first occurrence).

## C. Scheduler, library and operations

C1. **Feasibility premise restated.** The table was computed over all 256 delivered
packages, but only **129 are broadcast-ready today: dead 112, indie 15, bluegrass 1,
funk 1** (the rest await emcee voicing, throttled by the free Voxtral tier at roughly
~100 shows/month, unmeasured; ~1,000 more shows are packaged in llama and undelivered).
The example clock is **not** feasible on today's ready library. Label the table with
the simulation's rules (fill excluded dead/funk/dead-family; a no-fit waited to the
window start; all delivered packages, voiced or not). Library size gates **going on air
with the clock**, not development: the scheduler is built and measured against every
available manifest. `transmitter library --include-unready` reports projected pools and
feasibility counting unvoiced packages (delivering llama's packaged shows, unvoiced, adds
manifests to measure against; they stay ineligible to air).

C2. **Empty anchor rule:** an anchor whose pool has no eligible show is skipped; its
time becomes fill; `status` warns. A package with no `source.profile` is fill-only.

C3. **Changed packages under the plan:** before rendering a show, re-validate it (all
`broadcast.m3u` entries exist; cache keys match). On mismatch, skip the whole show at
its boundary, re-plan from there, and log a `plan-changed` event. Frozen means
*rendered*, not planned.

C4. **Lead default 24 h** (configurable). State the trade-off: the lead is both how
long the station survives hugo being down and how long any plan/library change takes to
reach air. No re-plan-from-now command (published segment keys are immutable).

C5. **Eligibility, exactly:** emcee's four legs (manifest v3+ with non-null
`dj_notes` and `dj-notes.md` present; non-null `dj_audio` with every named clip on disk;
`broadcast.m3u` present; every manifest track's audio on disk) **plus** every
`broadcast.m3u` entry exists; quiet period on the newest mtime among `manifest.json`,
`broadcast.m3u`, `dj-audio/*`. Note that emcee's atomic manifest rename is the real
guarantee; the quiet period is belt-and-braces.

C6. **Stall detection from the cloud:** the clock Worker alerts (same channels) when the
published lead (`horizon.last` − now) falls below a floor — this catches a hung hugo
(e.g. a hard NFS mount hang) that cannot alert for itself. The transmitter service also
runs under systemd `WatchdogSec`.

C7. **Recovery after an outage longer than the lead:** start a fresh contiguous run
(`horizon.first` = resume index), re-plan from the next show boundary after now, and
log `aired.jsonl` rows only for shows that were published and whose air time passed.

C8. **Documented limitation (no mechanism):** after an unclean SMB drop macOS can leave
a stale user-owned `/Volumes/media` and remount at `/Volumes/media-1`; the operator
confirms `.station-root` is visible from the Mac before delivering.

C9. transmitter state no longer includes `alerts.json` or guard state (moved to R2
`state/`); transmitter's alerts cover only hugo-side conditions (marker missing, render
or publish errors, window misses) via email + ntfy; the cloud covers spend and stalls.
Remove `guard` from transmitter's command list; add `budget`, `offair`, `fallback
render`.

## D. Phases and verification (update)

D1. Phase 1 (thin slice) now: trivial in-order planner over ready packages; per-show
renderer + frame-count segmenter; publisher; antenna clock Worker writing `live.m3u8`
(incl. fallback and off-air via a hand-written `state/offair.json`); static player page;
fallback loop; the zone hardening and R2 custom-domain setup docs. Phase 3 (guard) adds
the guard + kill switch + alerts to the clock Worker. Keep "not public until phase 3".

D2. Replace phase 1's "must measure" list with a **phase-1 verification list**:
cron invocation may loop ~60 s with only CPU billed; R2 custom-domain cache hits incur
no Class B; a 5 s origin max-age is honoured for `live.m3u8`; ignore-query-string Cache
Rule works on this plan; hls.js, Safari/iOS and VLC play the chosen container with
PROGRAM-DATE-TIME and stop on ENDLIST and on 403; Email Routing send-email binding is
available; GraphQL account-scoped queries work with a read-only token and their lag is
minutes; llama's purge flush over SMB to the Synology; a week of real op counts at ~1
listener.

D3. Testing section: antenna tests become: clock playlist math (grid boundaries, grace,
fallback, ENDLIST, epoch keys), guard pricing/projection/trip/fail-closed/rollover/raise
against canned GraphQL responses (vitest, Workers pool); Playwright smoke of the static
player against a local R2 emulation. transmitter tests: remove guard tests; add per-show
encode + frame segmentation (gapless joins, segue joins, show gap), re-validation skip,
outage recovery.

D4. Non-goals: remove "an Icecast endpoint" from non-goals' wording only if needed —
keep Icecast relay in Future work, adding that many aggregators expect an Icecast/MP3
URL.

## E. Rejected (do not apply)
- Restricting CORS on stream paths (operator ruling: shareability; cost is moot).
- A per-hugo guard with publish-fails-closed-on-guard-staleness (superseded by A5).
- A `replan --from now` command (immutable published keys; lead shortened instead).
- Weekly guard-vs-invoice reconciliation mechanism (manual runbook check only).
