# Playout setup (phase 1)

How to stand up the station's cloud side (R2 + one cached hostname + the antenna
clock Worker) and hugo's transmitter, then verify the phase-1 assumptions. The
design is `docs/superpowers/specs/2026-10-09-playout-design.md`. **Do not share
the station publicly until phase 2 (the cost guard) ships.**

## 0. Preconditions

- A Cloudflare account **dedicated to the station** (phase 2's guard reads
  account-scoped meters; other projects would pollute them). A second account
  under your existing login (dashboard → account dropdown → *Create account*) is
  fine: usage, allowances, billing and tokens are per account. If your login has
  more than one account, every wrangler command must be pinned to the station's
  (section 1 step 1).
- **This repo is public: no account details are ever committed.** The account ID
  lives only in the git-ignored `antenna/.env` and in transmitter's config on
  hugo; R2 keys only in hugo's env file; API tokens only in Worker secrets. Do not
  add `account_id` to `antenna/wrangler.jsonc`.
- **Workers Paid** ($5/month) enabled on that account.
- The station's domain is a **full** Cloudflare zone on that account (registrar NS
  records point at Cloudflare; partial/CNAME setup is Business-only).
- **No paid zone add-ons**: no Argo, Cache Reserve or Load Balancing (the guard
  cannot see them; the Budget alert would be their only backstop).
- Workers observability/logs within the free allowance (the clock logs one line
  per invocation, ~1,440/day).
- hugo: Debian 12, Python 3.11, ffmpeg 5.1, Node 22; NFS mount of the station
  share; **NTP synchronized** — check `timedatectl status` shows
  `System clock synchronized: yes` (systemd-timesyncd or chrony).

## 1. R2 bucket and custom domain

1. `cd antenna && npm ci` (installs the pinned wrangler), then `npx wrangler login`.
   Pin the station account: create the git-ignored `antenna/.env` containing
   `CLOUDFLARE_ACCOUNT_ID=<the station account's ID>` (dashboard → the account's
   home page → *Account ID*), then check `npx wrangler whoami` from `antenna/`
   names the station account and `git status` does not list `.env`. Then
   `npx wrangler r2 bucket create lma-radio`
   (if you choose another name, change it in `antenna/wrangler.jsonc` and
   transmitter's `[publish] bucket`).
2. Dashboard → R2 object storage → `lma-radio` → Settings → **Custom Domains** →
   **Add** → `<host>` (a hostname on the station zone) → Continue → **Connect
   Domain**; Cloudflare creates the DNS record, and the domain goes Initializing →
   Active. Keep **Public Development URL** (r2.dev) **disabled** (Settings → Public
   Development URL → Disable → type `disallow`): r2.dev is uncached and would bill
   every request.
3. R2 → **Manage API tokens** → create a token with *Object Read & Write* scoped to
   `lma-radio` only. Put its key pair on hugo in the service's env file (mode 600,
   owned by the service user):
   ```
   R2_ACCESS_KEY_ID=...
   R2_SECRET_ACCESS_KEY=...
   ```

## 2. Zone configuration (dashboard)

Zone settings live under Domains → the station zone. Dashboard paths and labels
below were checked on 2026-10-11 (Cloudflare moves them; the docs at
developers.cloudflare.com are the authority if they drift again).

1. **Caching → Cache Rules → Create rule** *"station: cache everything"*: custom
   filter expression `http.host eq "<host>"`; Cache eligibility **Eligible for
   cache**; Edge TTL **Use cache-control header if present, use default Cloudflare
   caching behavior if not** (every object the station writes carries its own
   `Cache-Control`; the fallback matters for 404s, which then keep the default
   3-minute edge TTL instead of reaching R2 on every request); Browser TTL
   **Respect origin**; Cache key → **Ignore query string** (available on Free:
   measured 2026-10-11, random `?a=…` values all HIT one object).
2. If the zone shows **Caching → Configuration → Browser Cache TTL**, set it to
   **Respect Existing Headers** too (the Cache Rule's Browser TTL already covers
   the station host; otherwise browsers serve a stale `live.m3u8` from their own
   cache).
3. **Caching → Tiered Cache** → on, topology **Smart** (one upper tier near the
   bucket, so each segment is read from R2 about once however many locations serve
   it).
4. **Rules → Overview → Create rule → URL Rewrite Rule** *"station: index"*: when
   `http.host eq "<host>" and http.request.uri.path eq "/"` → Path **Rewrite to →
   Static** `/index.html`, Query **Preserve** (R2 custom domains serve no index
   document; measured: the rewrite applies before the cache lookup).
5. **Rules → Overview → Create rule → Response Header Transform Rule** *"station:
   cors"*: when `http.host eq "<host>"` → **Set static** `Access-Control-Allow-Origin`
   = `*` (R2's CORS policy answers only requests carrying `Origin`, so a cached
   non-CORS response would lack it; measured: the header is present on cache hits).
   Free allows 10 Transform Rules in total; steps 4–5 use 2.
6. **Security → Security rules → Create rule → Custom rules**, rule *"station:
   allowlist"*, action **Block**, expression via **Edit expression**, then **Deploy**:
   ```
   http.host eq "<host>" and not (
     http.request.uri.path in {"/" "/index.html" "/embed.html" "/offair.html" "/live.m3u8"
                               "/timeline.json" "/player.js" "/nowplaying.js" "/style.css"}
     or starts_with(http.request.uri.path, "/seg/")
     or starts_with(http.request.uri.path, "/fallback/")
     or starts_with(http.request.uri.path, "/notes/")
     or starts_with(http.request.uri.path, "/show/")
     or starts_with(http.request.uri.path, "/assets/")
   )
   ```
   (`state/` is not allowlisted, so it is blocked. Use only `eq`/`in`/`starts_with`/
   `ends_with`; `matches` is Business+. Try `wildcard` in a scratch rule as part of the
   verification below.)
7. Second custom rule *"station: kill switch"*, action **Block** (phase 2's guard
   toggles it). The dashboard offers only **Deploy** for custom rules (no draft), so
   deploy it and **switch it off immediately** in the rules list; while it is on,
   everything except the paths below returns 403. Free allows 5 custom rules; steps
   6–7 use 2.
   ```
   http.host eq "<host>" and not (http.request.uri.path in {"/" "/index.html" "/offair.html" "/style.css"})
   ```
8. **Security → Security rules → Create rule → Rate limiting rules** (Free allows
   exactly one): the Free plan matches on **URI Path** (and Verified Bot) only, not
   host, so use *URI Path starts with* `/` (the whole zone; the station host is the
   only one serving anything); characteristics IP (fixed on Free), **100 requests
   per 10 seconds** (period fixed), action **Block** for **10 seconds** (fixed).
   (A playing stream makes ~2 requests per 10 s; ~50 listeners behind one IP fit.)
9. **Manage Account → Billing → Billable Usage → Create budget alert**: two alerts at
   **50%** and **100%** of
   (your monthly ceiling, phase 2's `monthly_budget_usd`, minus $5; it is not a transmitter config key, so do not add it to `config.toml`) — they exclude subscription fees, and are next-day and
   informational only.

## 3. transmitter on hugo

1. Clone the repo; `python3 -m venv ~/.venvs/transmitter && ~/.venvs/transmitter/bin/pip install -e <repo>/packages/transmitter`.
2. On the share, once: `touch /nfs/media/<station>/.station-root` (create it from the
   Mac side on the SMB path if hugo's mount is read-only). Without the marker, `plan`
   refuses — a down NFS mount is an empty directory on hugo.
3. `transmitter config init`, then edit the config file, always
   `$TRANSMITTER_ROOT/config.toml` when that is set, else `~/.transmitter/config.toml`:
   `[station] root`, `[publish] account_id` and `bucket`, `[antenna] dir = "<repo>/antenna"`
   and `site_url = "https://<host>"`. Unknown keys are errors, not ignored.
   - The show-page template is read from `<[antenna] dir>/templates/show.html`; without
     `[antenna] dir` (or with an unreadable template) publishing fails with a config error.
   - `[publish] prune_margin_minutes` (default 10) has a floor of **4**: a smaller value
     is refused at config load (a validation error), not silently raised. The floor is the
     time a player may still request a segment (live window + grace + CDN max-age + lag
     allowance); do not go below it.
4. Fallback loop and off-air notice (once; re-run only to change them):
   `transmitter fallback render station-id.mp3 --notice offair-notice.mp3`, run with the
   env file loaded (`set -a; . <env file>; set +a`) since it uploads to R2.
   It prints `horizon updated` when `state/horizon.json` now names the fallback, or
   `horizon deferred` when there is no horizon yet (or the high-water rule applies); in
   the deferred case the next publish batch carries the version. The antenna only sees the
   fallback once `state/horizon.json` names it. **Run this before step 5:** until a
   fallback version is recorded in the workspace, `run`/`publish` upload nothing at all
   (no segment, no horizon) and every publish pass logs an `ALERT publish: no fallback
   rendered …` line — a horizon without a fallback would leave off-air with no notice.
5. Start: `transmitter run` with the env file loaded. In phase 1 it runs as the
   operator's own user (phase 2 ships a system unit, with `WatchdogSec` and journald).
   Once: `sudo loginctl enable-linger <user>`, so the user's services keep running
   after logout (a transient `systemd-run` unit does not survive a reboot: re-run
   this step after one). Then run it under `systemd-run --user
   --unit=transmitter --property=EnvironmentFile=<env file> --property=Restart=always
   --property=RestartSec=30 ~/.venvs/transmitter/bin/transmitter run` (restarted 30 s
   after any crash), and check `journalctl --user -u transmitter` for `ALERT` lines.
   **First start:** the first show begins `[planner] start_delay_minutes` (default 10)
   after `run` starts, but its analyse + encode on hugo (two full decodes over NFS plus
   loudness measurement, then the first batch's uploads) can take longer than that; the
   first minutes of the first show then never air (nothing is listed until its first
   batch is up). If that matters, raise `start_delay_minutes` in `config.toml` for the
   first start (e.g. 20–30) and put it back afterwards; it only affects fresh runs.
   **While the service runs, do not run `transmitter plan` or `transmitter render` by
   hand:** they take no lock against `run`'s own plan/render step, so both can rewrite
   `plan.jsonl` at once. `transmitter publish` and `transmitter status` are safe.
6. `transmitter status` shows the epoch, plan, the show on air, the published lead
   and the fallback version.
7. **The epoch is fixed at first start.** The first command that opens the station
   (`plan`, `render`, `publish`, `run`, `fallback render`) creates `epoch.json` in the
   workspace (`root` in config; default `~/.transmitter` or `$TRANSMITTER_ROOT`) and every later run reuses it. There is no command to change it, and
   publishing refuses (`published state belongs to epoch …`) if `publish.json` names a
   different one. **Avoid** accidental re-epoching: do not delete `epoch.json`, and do not
   point `root`/`TRANSMITTER_ROOT` at a fresh directory (that creates a new epoch there).
   A deliberate re-epoch is a manual re-render-everything operation (stop the service,
   start a fresh workspace, then **before the first publish** re-run
   `transmitter fallback render …` (step 4) in it, render and publish again under
   `seg/<new epoch_id>/`). The fallback version is recorded per workspace
   (`<root>/fallback.json`); without that step the new workspace publishes nothing
   (publish alerts `no fallback rendered`, step 4) and the old epoch's horizon stays
   in R2 until it goes stale. If the new workspace comes from moving `TRANSMITTER_ROOT`, copy `config.toml` there too (it is
   read from that directory). The old epoch's `seg/<old epoch_id>/` objects are orphaned
   (prune only deletes what the local `publish.json` records, ~1.4 GB at a 24 h lead):
   delete them by hand (dashboard or an R2 lifecycle rule) once listeners have moved.
   Consequence for listeners: segment numbering restarts at 0, so `EXT-X-MEDIA-SEQUENCE`
   drops, and players must **reload the page** to follow it.

## 4. antenna

1. `cd antenna && npm test` (after `npm ci`, section 1 step 1)
2. **On a new account, open Workers & Pages in the dashboard once first.** Cron
   schedules cannot be saved until the account has a `workers.dev` subdomain (wrangler
   error 10063, "You need a workers.dev subdomain"), even though this Worker disables
   `workers.dev`; opening that page creates the subdomain. A deploy that hits 10063
   has uploaded the Worker but registered no cron: re-run it.
   `npx wrangler deploy --dry-run` first (bundling and config check), then
   `npx wrangler deploy` (cron `* * * * *`, R2 binding, `workers_dev = false`,
   `preview_urls = false`, no routes); its output ends with `schedule: * * * * *`.
3. `ANTENNA_BUCKET=lma-radio npm run deploy:assets` (player page, off-air page,
   JS/CSS, hls.js; `node scripts/deploy-assets.mjs --dry-run` with `ANTENNA_BUCKET` set
   prints the `wrangler r2 object put` commands without running them).
4. Off-air by hand (phase 1 has no `transmitter offair`): write
   `{"offair": true, "reason": "maintenance", "since": "<iso>", "until": null}` to
   `state/offair.json`:
   `npx wrangler r2 object put lma-radio/state/offair.json --file offair.json --content-type application/json --remote`;
   back on air: same with `"offair": false` (or delete the object). Within a minute
   `live.m3u8` becomes the notice + `#EXT-X-ENDLIST`, and back.
   **The notice needs a usable fallback.** transmitter never writes a horizon without
   one (section 3 step 4: it publishes nothing until `fallback render` has run, and
   prune stops with `ALERT prune: stopped: no-fallback …` rather than rewrite the
   horizon if the workspace's `fallback.json` is lost later), so every
   `state/horizon.json` names a version. If that fallback is unusable in R2 anyway (its
   `index.json` deleted by hand, or with `len < 1`), off-air writes an **ENDLIST-only
   playlist (no notice)**: no segments, just `#EXT-X-ENDLIST`, so players stop (on
   hls.js browsers the player page shows its off-air notice; native HLS players such as
   Safari may instead show "The stream is unavailable right now."). The clock still logs a structured
   `offair-without-fallback` `console.error` once per invocation; fix it by re-running
   `fallback render`. The WAF kill switch (section 2 step 7) remains the hard stop.
5. The clock's spend bounds (Cloudflare has no spending cap): at most **10 PUTs per
   invocation** (`MAX_PUTS`), a horizon whose segment duration `d` is not 10.24 s is
   **refused** (nothing written; logged as `horizon-refused`), and the loop never runs
   longer than **75 s** (`LOOP_SECONDS` above 75 is clamped and logged as `loop-clamped`).

## 5. Phase-1 verification checklist

Run these with the station up; record each result (date, observation). Each needs
the real account. The first run's results (2026-10-11) are in
`docs/superpowers/2026-10-11-playout-phase1-verification.md`.

- [ ] **A cron invocation may loop ~75 s with only CPU billed.** Workers → antenna →
      Metrics: wall time per invocation ≈ 75 s, CPU time a few ms; Billing → usage
      shows CPU-ms, not duration.
- [ ] **Scheduled vs actual cron fire times over a day.** `npx wrangler tail antenna`
      (or the dashboard logs): the clock logs `{"event":"clock","lagMs":…}` per
      invocation; summarize lagMs over 24 h (median, p99, any missed minutes).
- [ ] **R2 custom-domain cache hits incur no Class B.** Fetch one segment 50× via
      `https://<host>/seg/…` (`curl -sI` shows `cf-cache-status: HIT` after the first);
      R2 metrics show ~1 Class B read for it, not 50.
- [ ] **A 5 s origin max-age is honoured for `live.m3u8`** at the edge (`curl -sI
      https://<host>/live.m3u8` twice within 5 s: `HIT` with `age` ≤ 5; after 6 s,
      `EXPIRED`/`MISS` and new content) and in browsers under Respect Existing
      Headers (DevTools: no "from disk cache" for `live.m3u8` older than 5 s).
- [ ] **The ignore-query-string Cache Rule works on this plan:** `curl -sI
      'https://<host>/timeline.json?a=1'` then `?a=2` → the second is a `HIT`.
- [ ] **Whether `wildcard` rule expressions are available on Free:** save a scratch
      WAF rule using `http.request.uri.path wildcard "/seg/*"`; record accept/reject,
      then delete it.
- [ ] **The Worker's `*.workers.dev` URL serves no Worker:** `curl -sI
      https://antenna.<account-subdomain>.workers.dev/` → not served by the Worker
      (an error/404 from Cloudflare, no clock output); likewise no preview URL.
- [ ] **hls.js, Safari/iOS and VLC play the chosen container with PROGRAM-DATE-TIME,
      and stop on ENDLIST and on 403:** play `https://<host>/` in Chrome, Safari (macOS,
      iOS) and `https://<host>/live.m3u8` in VLC; set `state/offair.json` → every player
      stops with the notice; clear it, **start playback again first, and only then**
      temporarily enable the kill-switch rule → `live.m3u8` returns 403 and the
      already-loaded page shows the off-air notice with a manual retry; disable it. The
      order matters: the kill-switch rule (section 2 step 7) blocks `player.js`,
      `nowplaying.js` and `assets/hls.min.js`, so a page loaded *after* it is enabled
      shows a dead Play button, not the notice — that is expected, not a failure.
- [ ] **Players survive the fallback→live switch, where
      `EXT-X-DISCONTINUITY-SEQUENCE` restarts at 0.** The trigger is a window that
      mixes fallback and live and then becomes pure live, which happens at a fresh
      run's start: on the **first start** (section 3 step 5) the first horizon is
      normally published minutes before its first segment airs, and until then the
      window is the fallback loop (a larger `start_delay_minutes`, as above, widens
      that interval). Attach players (Chrome/hls.js, Safari, VLC) as soon as
      `transmitter status` first shows `published segments …` while `on air` still
      says not started, and keep them playing through the switch to live and for at least
      70 s after (until the 6-segment window holds only live segments and the
      discontinuity sequence drops to 0); confirm each player returns to live on its
      own or needs exactly one reload, and record which. (Merely stopping
      `transmitter run` does **not** exercise this: the published lead, 24 h by
      default, keeps the clock serving live. The other trigger is a restart after an
      outage longer than the lead, which reaches the same switch via the grace
      window and a new run.)
- [ ] **archive.org MP3 derivatives carry LAME/Xing gapless info (one segued pair):**
      for two consecutive segued tracks in a delivered package,
      `ffprobe -v debug "<track>.mp3" 2>&1 | grep -E '^\[mp3 .*\] pad '` prints
      `pad <delay> <padding>` for each; then listen across that join on air.
- [ ] **The Email Routing send-email binding is available** on the account (for
      phase 2 alerts): Email → Email Routing enabled on the zone with a verified
      destination address; a throwaway Worker with a `send_email` binding deploys.
- [ ] **GraphQL account-scoped queries work with a read-only token and lag by
      minutes** (for phase 2): create an *Account Analytics: Read* token; query
      `workersInvocationsAdaptive`, `r2OperationsAdaptiveGroups` and
      `r2StorageAdaptiveGroups` for the account over the last hour; note how far
      behind real time the newest datapoint is.
- [ ] **llama's purge flush over SMB to the Synology:** deliver one show to the NAS
      path with `llama deliver`; confirm the purge succeeds (or fails closed with its
      warning and keeps the library audio) — the one-time cut-over check from the spec.
- [ ] **A week of real op counts at ~1 listener:** after 7 days, record Workers
      requests, R2 Class A/B ops and storage from Billing/R2 metrics; compare with the
      spec's budget (Class A ≈ 620k/month, storage ≈ 1.4 GB at a 24 h lead, Workers
      ≈ 43k invocations/month).
