# Platform research notes (Sonnet research subagent, 2026-10-09) — the evidence behind the spec's "Platform facts"
Items marked [UNVERIFIED] came from background knowledge or secondary sources.

R2 (developers.cloudflare.com/r2/pricing/): free/month (Standard only) 10 GB storage, 1M Class A, 10M Class B; egress free. Beyond: $0.015/GB-mo, $4.50/M A, $0.36/M B. Cache hits on a custom domain: R2 pricing page silent; billing page (via search summary) says cache hit avoids origin fetch / Workers execution / R2 ops — no explicit "cache hit != Class B" sentence found. Caching requires a custom domain (r2.dev not cached). Default cache only caches certain extensions; Cache Everything rule needed for .m3u8/.ts/.aac/.mp4.

Workers (workers/platform/pricing, limits): Free 100k req/day (reset 00:00 UTC), 10 ms CPU, 5 cron triggers. Paid $5/mo min: 10M req/mo incl then $0.30/M; 30M CPU-ms incl then $0.02/M ms; 250 cron. Static assets free & unlimited. Worker's own Cache API hit still billed as a request (no CPU). Route-bound Worker runs on every request. Whether a zone-cache hit served before a route Worker is billed: NOT documented. Cron min interval 1 min. Durable Objects on Free (SQLite only): 100k req/day.

ToS (cloudflare.com/service-specific-terms-application-services/, dated Sept 28 2026, fragments): CDN "can be used to cache and serve web pages and websites"; "Unless you are an Enterprise customer, Cloudflare offers specific Paid Services (e.g., the Developer Platform, Images, and Stream) [...] that you must use in order to serve video and other large files via the CDN"; may limit if serving "a disproportionate percentage of pictures, audio files, or other large files" without such Paid Services. 2023 blog (blog.cloudflare.com/updated-tos): large files OK when hosted on a Cloudflare service like Stream, Images, or R2. Gray: whether R2 free tier counts as "Paid Service". Anecdote: an account flagged for R2-over-CDN was unflagged after showing paid R2.

Pages free: 500 builds/mo, 20k files, 25 MiB/asset, no bandwidth cap listed.

Oracle Always Free: A1 2 OCPU/12 GB (cut from 4/24 on 2026-06-15 per blogs), 200 GB block, 10 TB/mo egress; idle reclamation (7-day p95 CPU<20% and network<20%, A1 also memory); capacity scarcity.
Hetzner CX23 ~$6.49/mo (EU only). GCP e2-micro: 1 GB/mo free egress. Fly.io: no free tier, egress $0.02/GB.

AzuraCast: 2 GB RAM min; scheduled playlists/time windows/priorities; NO documented gap-fill by duration; HLS supported since 2022; REST API [UNVERIFIED this session].
Liquidsoap 2.4.x: output.file.hls (fMP4/TS/packed audio), on_file_change hook for S3 sync, request.queue, harbor HTTP; timed switches [UNVERIFIED].
Browser HLS: native Safari/iOS; Chrome 141/142 native HLS rollout had a playback bug (Mux status, Nov 2025); prefer hls.js where Hls.isSupported(). Android Chrome native: no authoritative statement.
Gaps: DeleteObject billing on R2 not checked; zone-cache-hit-before-route-Worker billing unknown.
