# Round-2 decisions for docs/superpowers/specs/2026-10-09-playout-design.md

Apply exactly; keep it tight (the spec is ~520 lines; aim to stay under ~590). Replace,
don't append. Keep the spec's voice (no review/round labels).

## G. Guard / off-air: replace with ONE simple state model (write it as a short block)

G1. Replace the "Trips…", "Trip action…", "Clearing…" bullets and the
`state/offair.json`/`state/guard.json` semantics with this model, stated in a few lines:

- Two independent flags. **`tripped`** — a latch owned by the guard, stored in
  `state/guard.json` with its reason (`spend` or `blind`) and the latest evaluation.
  **`offair`** — owned only by the operator (`transmitter offair on|off` writes
  `state/offair.json`); the guard never writes or clears it.
- **Blocked = `tripped` OR `offair`.** Every clock invocation (not only on a trip)
  reconciles reality to that: when blocked, the playlist is the ENDLIST off-air
  playlist, `index.html` is the off-air page, and the WAF kill-switch rule is enabled;
  when not blocked, the opposite. Level-triggered: each guard run reads the rule's
  actual state and corrects it; any Rulesets API failure raises a deduped alert and is
  retried next run.
- **Set** `tripped` when actual ≥ 90% or projected ≥ 100% (reason `spend`), or no
  successful analytics reading for `blind_after` 6 h (reason `blind`).
- **Clear** `tripped` only: (a) reason `blind` — on the first successful reading that
  is under the thresholds; (b) reason `spend` — at a new billing period, or after
  `transmitter budget --raise-to <usd>`, in either case only if the guard's next
  evaluation is under the thresholds. Nothing else clears it; `offair off` clears only
  the operator's flag.
- `offair on` therefore blocks fully (kill switch included) — the takedown path for
  an objection is not cooperative-only.
- Limitation, stated: if the WAF API is unreachable, the block is cooperative-only
  (ENDLIST + off-air page) until a later run succeeds; the alert repeats meanwhile.

G2. **Guard runs first and independently** in each invocation: whenever
`state/guard.json`'s evaluation time is ≥ 15 min old (not on a minute modulo), in its
own try/finally; any exception in reading/pricing counts as a failed reading, and the
blind rule and reconciliation run in the finally. Playlist writing follows; HTML/notes
work never precedes the guard.

G3. **Cap the station's own billed writers** (they are the only Class A sources):
- clock: at most `ceil(60/d) + 2` playlist PUTs per invocation; skip a PUT whose bytes
  equal the last written.
- transmitter: a local daily PUT budget (default 2× the expected count); exceeding it
  stops publishing and alerts. transmitter also **stops publishing while
  `state/guard.json` says tripped** (it reads it via the S3 API at most every 15 min —
  ~3k Class B/month).

G4. **Nobody is silent about a dead clock:** `transmitter run` fetches the public
`live.m3u8` once a minute (a cache hit) and alerts when its newest
`EXT-X-PROGRAM-DATE-TIME` is older than ~3·d, and alerts when `state/guard.json` is
older than ~30 min. (Optional second channel: Cloudflare's Worker-error notification.)

G5. **workers.dev:** antenna's wrangler config sets `workers_dev = false` and
`preview_urls = false` (a routeless Worker otherwise gets a public, billed
`*.workers.dev` URL the zone's kill switch cannot reach); phase-1 verification curls
that URL expecting no Worker.

## Z. Zone configuration corrections (Free-zone realities)

Z1. CORS header comes from a **Response Header Transform Rule** setting a static
`Access-Control-Allow-Origin: *` on the hostname (R2's own CORS policy only answers
requests carrying `Origin`, so a cached non-CORS response would lack it). Remove any
reliance on a bucket CORS policy.
Z2. Free zones cannot customise block pages, so the kill-switch rule exempts `/`,
`/index.html`, `offair.html` and its assets; while blocked, the clock writes the
off-air page into `index.html` (already in G1).
Z3. Rules use `eq`/`in`/`starts_with`/`ends_with` (and `wildcard` if phase 1 confirms
it on Free) — **no `matches` (regex is Business+)**. Reword "path shapes" accordingly.
Z4. **Browser Cache TTL = Respect Existing Headers** (else browsers serve a stale
`live.m3u8` from local cache); add to the phase-1 verification list.
Z5. **Remove** the "short edge TTL for 404s (~60 s)" item (not settable on Free, and
it would add misses); note the default 3-min 404 TTL is accepted.
Z6. Setup preconditions, stated once: a Cloudflare account dedicated to the station
(the guard's account-scoped meters then mean what they say); no paid zone add-ons
(Argo, Cache Reserve, Load Balancing — the guard cannot see them; the Budget alert is
their only backstop); Workers observability/logs off or within the free allowance.
**Arm Cloudflare Budget alerts in phase-1 setup** (not phase 3), thresholds set at
`budget − $5` because Budget alerts exclude subscription fees.
Z7. Guard meters: **drop CPU-ms** (the GraphQL dataset exposes CPU only as
percentiles, and the clock's CPU is bounded by design — G3); keep Workers requests,
R2 Class A/B and storage.

## H. HLS / renderer details

H1. Spike criterion (b) becomes: the segment's embedded timestamp is
`(N·d·90000) mod 2^33` in 90 kHz ticks for packed audio (or `tfdt = N·d` for fMP4);
the wall clock is carried by `EXT-X-PROGRAM-DATE-TIME`. Add "plays across a 2^33
wrap (E seeded so a wrap falls in the test window)" to the spike.
H2. Frame accounting: a show's frame count is the encoder's output including the
flush frames; `timeline.json` offsets subtract the encoder's declared priming delay.
Add "archive.org MP3 derivatives carry LAME/Xing gapless info (check one segued pair)"
to phase-1 verification.
H3. Fallback: segments rendered with timestamps `k·d`; the clock emits
`EXT-X-DISCONTINUITY` before segment 0 of **every loop iteration** as well as at each
switch, with discontinuity sequence `floor(N/len)` during pure fallback.
`horizon.json` carries `fallback_version`; `fallback/<version>/index.json` carries
`len` and the off-air notice segment key `fallback/<version>/notice.aac`.
H4. Cron timing: each invocation writes the current playlist immediately on start
and loops until ~fire+75 s (overlap is idempotent; budget +~43k Class A/month — update
the Spend budget line). Phase 1 logs scheduled-vs-actual fire times for a day.
H5. Clock input rules: segments with `N < horizon.first` are absent; `timeline.json`
is bounded to [now − 24 h, horizon.last].
H6. Player: **native HLS on Apple WebKit** (`canPlayType('application/vnd.apple.mpegurl')`
— keeps AirPlay and lock-screen playback), hls.js elsewhere; update Platform facts'
"prefer hls.js whenever supported" rationale (the Chrome native-HLS bug is why
non-Apple browsers use hls.js). Add iOS lock-screen (10 min) and AirPlay to the spike.

## P. Publisher / contract / phasing

P1. `horizon.json` moves under `state/` (not served; no listener reads it); update the
contract table, WAF allowlist and every reference.
P2. A local flock in `~/.transmitter/` serialises publish/prune (a manual `publish`
while `run` publishes would otherwise race on `horizon.json`).
P3. `show/<slug>.html` is rendered and uploaded **by transmitter** from a template
file that lives in `antenna/` (antenna owns the template; transmitter reads it), in the
same publish step as `notes/<slug>.json`, both before the `timeline.json` that first
references the slug (ordering invariant). Removes the clock's show-page code path and
its "first scheduled" bookkeeping. The clock still writes `index.html` and
`live.m3u8`.
P4. Recovery wording: "the fresh run begins a new show at the resume index" (not the
old plan's next boundary).
P5. **Phase order becomes 1 → 3 → 2 → 4** (guard + operations before the scheduler):
the scheduler is gated on library growth anyway, and this lets the trivial planner go
public sooner. Renumber/reorder the Phases section accordingly and keep "not public
until the guard ships" as the gate.

## Rejected (do not apply)
- Moving HTML rendering to a second cron Worker (G2 ordering suffices).
- Pricing CPU as requests × P99 (dropped instead, Z7).
