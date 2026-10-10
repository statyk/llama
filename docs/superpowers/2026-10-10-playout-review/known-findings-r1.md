# Known findings from round 1 (4 reviewers) and how the spec now handles each

## Spend (strict)
- Worker runs before cache; cached Worker hits are billed; no spending cap → no Worker on any listener path; one R2 custom-domain hostname, all listener objects static/cached; antenna is a cron-only clock Worker.
- Off-air (ENDLIST) only stops cooperative players → guard trip also enables a pre-created WAF block rule (kill switch); blocked requests reach neither R2 nor a Worker.
- Blind guard while hugo publishes = unbounded → guard moved into the clock Worker (independent of hugo) and fails closed after `blind_after` (6 h) without a reading.
- Backstop "usage-based billing notifications" needs a Pro zone → replaced by Cloudflare Budget alerts (informational, next-day).
- now.json / embed / page polling unbounded and billed → no now.json; now-playing computed client-side from cached timeline.json via program-date-time; embed and pages static; polling only while playing/visible; no auto-reconnect after ENDLIST/403.
- Per-request R2 binding reads per poll → none; the clock reads R2 once per invocation.
- Cache-busting query strings / key enumeration → Cache Rule ignores query string; WAF path allowlist; short 404 edge TTL; Smart Tiered Cache.
- Per-IP abuse → one generous rate-limit rule (~100 req/10 s/IP; operator wants NAT'd offices and multi-room homes to work).
- CORS → deliberately `*` (operator ruling: shareability; third-party polling is free cache hits). Reviewers proposed restricting; rejected.
- Trip at 100% actual = overspend; MTD-average projection blind to surges → projection per meter from last-3h rate through allowances; trip at actual ≥ 90% or projected ≥ 100%.
- Allowance scope, billing day, CPU-ms → account-scoped GraphQL queries incl. CPU-ms; UTC anniversary billing period; rollover re-evaluates rather than auto-clearing.
- --clear semantics → no bare clear; `budget --raise-to` (expires at period end); `offair off` refused while latest guard evaluation is over threshold (state/guard.json).
- Flag write failure / Worker reading flag → guard and clock are the same Worker; state in R2; clock failure → stale playlist → cache hits (fails toward zero cost).
- Fallback through billed Worker → no routes exist; fallback segments are static objects.
- Prune vs hugo clock skew → hugo NTP in setup docs; prune margin 10 min. (No further mechanism.)
- List ops Class A; DeleteObject free → presence = PUT 200, no List; prune by computed key range; DeleteObject resolved free.
- Epoch key collision under immutable caching → keys namespaced by epoch_id; fallback by version.

## Rendering / contract
- Long-lived encoder risk; hls_time can't represent 430×1024/44100; TS 90 kHz rounding; restart PTS → per-show encode + frame-count segmentation, d = 10.24 s exactly (441 frames), timestamps E+N·d; restart trivial.
- "Item" ambiguity → 2 s gaps between tracks would kill segues → joins defined: track→track zero silence (gapless, LAME trims), clip↔track 0.75 s, show→show 2 s.
- ffprobe durations not exact → decoded sample counts.
- Loudness pushes dynamic tapes into limiter → gain = min(target−I, −1−TP) over tracks only; clips own target.
- fMP4 init, discontinuity handling → init per epoch if fMP4; EXT-X-DISCONTINUITY at live↔fallback; documented limitation (stateless discontinuity sequence may cost one reload).
- Transient publish lag flips to fallback → grace of 3 segments.
- MEDIA-SEQUENCE ambiguity, now-playing ahead of audio → MEDIA-SEQUENCE = first listed; PROGRAM-DATE-TIME; client-side lookup by playback position.

## Scheduler / ops
- Feasibility used all 256 delivered; only 129 ready (dead 112, indie 15, bluegrass 1, funk 1) → premise restated; clock not feasible on today's ready library; library gates going on air, not development; `library --include-unready`. (Operator: voicing throttled by free Voxtral tier ~100/month; ~1000 more packaged in llama.)
- Empty anchor pools → skipped, time becomes fill, status warns; null profile = fill-only.
- Package replaced/re-voiced/removed under the plan → re-validate before render; skip whole show at its boundary; re-plan; frozen = rendered.
- 72 h lead = 72 h reaction latency → default 24 h, trade-off stated; no replan-from-now (immutable keys).
- Readiness legs / m3u entries / quiet-period mtime → specified exactly.
- NFS hard-mount hang silences hugo → clock Worker alerts on lead below floor; systemd WatchdogSec.
- Outage longer than lead → fresh contiguous run; aired.jsonl only for published+aired shows.
- Stale macOS mount after unclean SMB drop → documented limitation.
- DST / NTP → zoneinfo rules; NTP in setup docs.

## Removed by the revision
Worker routes (/live.m3u8, /now.json, per-request HTML), Workers Cache, the phase-1 "are cached Worker hits billed" measurement, the static-playlist contingency (now primary), long-lived encoder + overlapped-chunk fallback + restart-glitch criterion, d = 430 frames, 72 h lead, hugo-side guard (`transmitter guard`, `--clear`), listener-count estimate, usage-based-billing-notifications backstop.
