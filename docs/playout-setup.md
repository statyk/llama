# Playout setup (phases 1 to 3)

How to stand up the station's cloud side (R2 + one cached hostname + the antenna
clock Worker) and hugo's transmitter, then verify the phase-1 assumptions. The
design is `docs/superpowers/specs/2026-10-09-playout-design.md`. **Do not share
the station publicly until the phase-2 checklist (section 8) passes.**

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
5. Phase 2 replaces this transient unit with the system unit in section 6.1 step 2; follow that instead on an existing install. Start: `transmitter run` with the env file loaded. In phase 1 it runs as the
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
3. `ANTENNA_BUCKET=lma-radio npm run deploy:assets` (the off-air page `offair.html`, JS/CSS and hls.js;
   `node scripts/deploy-assets.mjs --dry-run` with `ANTENNA_BUCKET` set
   prints the `wrangler r2 object put` commands without running them).
   `index.html` is not uploaded: the clock writes it, the player page normally and the off-air page while the station is blocked.
   On a **fresh bucket**, run `deploy:assets` before or alongside the Worker deploy: the clock's `index.html` references `player.js`, `style.css` and hls.js.
4. Off-air: `transmitter offair on --reason "…"` / `transmitter offair off` (section 7). Within about a minute the clock serves the notice and ENDLIST, swaps `index.html` to the off-air page and enables the kill switch, and reverses all three after `off`. **If hugo is down**, write the flag from the Mac instead: from `antenna/`, put `{"offair": true, "reason": "…", "since": "<iso>", "until": null}` in `offair.json` and run `npx wrangler r2 object put lma-radio/state/offair.json --file offair.json --content-type application/json --remote` (`"offair": false` to come back). The guard honours the file within a minute, exactly as if `transmitter offair` had written it. Do **not** toggle the kill-switch rule in the dashboard: the guard reconciles it every minute, undoes the toggle and alerts `waf-corrected`. **If the clock Worker itself is broken** (nothing reconciles, so neither lever acts), first remove the Worker's cron trigger (dashboard: Workers & Pages → `antenna` → Settings → Trigger events; or `npx wrangler triggers deploy` from a config with `"triggers": { "crons": [] }`: merely deleting the `triggers` key does NOT remove the cron). **Confirm Workers & Pages → `antenna` → Settings → Trigger events lists no cron BEFORE enabling the rule**, then enable the kill-switch rule by hand. In that order: a Worker that is still running would undo the rule within a minute. **The way back:** if the station should stay dark, first write `offair on` (the Mac-side `state/offair.json` above); then redeploy with the committed `wrangler.jsonc` (its output ends with `schedule: * * * * *`). On redeploy the guard reconciles the hand-enabled rule: it disables it and alerts `waf-corrected`, unless the station is tripped or off the air. While the hand block stands, expect hugo's `dead-clock` 403 alert after about 17 checks. The `transmitter` commands here need the environment described at the top of section 7.
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
   `fallback render`. The WAF kill switch (section 2 step 7) remains the hard stop. (After phase 2 is deployed the guard reconciles that rule every minute, so a hand toggle is undone and alerted; use `offair` or the broken-Worker order in step 4 instead.)
5. The clock's spend bounds (Cloudflare has no spending cap): at most **10 PUTs per
   invocation** (`MAX_PUTS`), a horizon whose segment duration `d` is not 10.24 s is
   **refused** (nothing written; logged as `horizon-refused`), and the loop never runs
   longer than **75 s** (`LOOP_SECONDS` above 75 is clamped and logged as `loop-clamped`). With the metronome on (step 7), the Durable Object adds bounds of its own: at most 10 playlist PUTs and 12 alarm invocations per rolling minute, a 5 s bound on each PUT, a fixed set of 8 storage keys, and no alarm chain except while the playlist is live (never while blocked, held, or past its 15-minute lease).
6. The playlist (amendment A4, amended 2026-10-12). `live.m3u8` lists `PLAYLIST_WINDOW`
   (16) segments ending `PLAYLIST_LOOKAHEAD` (12) past the one airing, and tells players
   to start `PLAYLIST_HOLD_BACK` (12) segments before the listed end
   (`#EXT-X-START:TIME-OFFSET=-122.880` and `#EXT-X-SERVER-CONTROL:HOLD-BACK=122.880`).
   With lookahead = hold-back, players start at the wall clock with ~123 s of listed
   runway. Measured on a real iPhone (cron lag p99 77 s, max 117 s): playlist freezes up
   to 60 s (a cron fire up to ~75 s late, less guard time) play through with the buffer
   refilling; freezes of 75-90 s (fires ~90-105 s late) gave a 1-3 s drop that
   auto-healed on iOS, also with the screen locked. Players that ignore
   EXT-X-START/HOLD-BACK (e.g. VLC) still start ~3 target durations from the listed
   end (~33 s), i.e. ~90 s ahead of the schedule with only ~30 s of runway. A lookahead alone adds no runway: it moves the listed end and the start
   point together. **Keep `PLAYLIST_LOOKAHEAD` equal to `PLAYLIST_HOLD_BACK`**: hugo's
   dead-clock check dates the playlist by its newest segment minus that hold-back (a
   test pins the equality; a hold-back above the lookahead reads the playlist as older
   and raises false dead-clock alerts, a lower one detects a dead clock late). Do not
   lower the lookahead casually: the off-air notice numbering assumes the configured
   lookahead, so a lower one while an older live playlist is still current can number
   the notice too low for up to a minute. The lookahead is capped at 16 and the hold-back at window − 1;
   the tags are omitted below 3 target durations (hold-back < 4). Every listed segment
   exists (the published lead is ~24 h; `lead-low` alerts at 16 h), and the PUT count is
   unchanged.
7. **The metronome** (`docs/superpowers/specs/2026-10-14-antenna-metronome-design.md`). With `"METRONOME": "on"` in `wrangler.jsonc`, a Durable Object (`Metronome`, one instance) writes `live.m3u8` at every grid boundary from an alarm chain, under a 15-minute lease that the clock renews every minute with the guard's verdict, the horizon and the fallback. The object never reads R2 and never decides blocked. The clock's own loop runs only when the object looks dead (a renew that fails or times out, a play lease not accepted or not written, or two consecutive renews that find the chain stalled), and then raises `metronome-down`. **Any other value is the rollback:** the clock's loop exactly as before, and the object deletes its alarm at its next invocation. Consequences of the lease: while cron is dead, the station keeps playing for up to 15 minutes on the last verdict, and `transmitter offair on` cannot take effect in that window (the WAF kill switch still can). Rollout, rollback and verification are in section 9.

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
      (After phase 2 is deployed, the guard undoes a hand toggle of the rule within a minute and alerts `waf-corrected`: do this step before deploying phase 2, or use `transmitter offair on`.)
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

## 6. Phase 2: the cost guard, alerts and the service

The guard runs in the clock Worker. It reads the account's usage every 15 minutes and prices it (budget $15 a month, including the $5 Workers Paid base). It **blocks** the station (ENDLIST playlist, off-air `index.html`, the WAF kill switch) when actual spend reaches 90% or projected spend reaches 100%, or when it has had no successful reading for 6 hours. It alerts at 50% and 80%. `transmitter offair on` blocks the station too. Design: `docs/superpowers/specs/2026-10-09-playout-design.md` ("Cost guard", "Alerts and operations").

The billing period starts on day 11 of each month, 00:00 UTC (the committed var `BILLING_ANNIVERSARY_DAY`). Upgrade transmitter and antenna in either order. If transmitter is upgraded first, hugo alerts `guard-stale` until antenna is deployed (no guard has evaluated yet): expected.

### 6.1 transmitter on hugo

1. `cd <repo> && git pull && ~/.venvs/transmitter/bin/pip install -e packages/transmitter`.
2. **System unit.** It replaces the phase-1 `systemd-run --user` unit:
   ```
   systemctl --user stop transmitter                       # the phase-1 transient unit
   sudo install -d -m 755 /etc/transmitter
   sudo install -m 600 -o <user> -g <user> <env file> /etc/transmitter/<user>.env
   sudo cp <repo>/packages/transmitter/systemd/transmitter@.service /etc/systemd/system/
   sudo systemd-analyze verify /etc/systemd/system/transmitter@.service   # if it rejects the bare template path: sudo systemd-analyze verify transmitter@<user>.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now transmitter@<user>
   systemctl status transmitter@<user>                      # active (running)
   journalctl -u transmitter@<user> -f                      # ALERT lines appear here
   ```
   The unit expects the venv at `/home/<user>/.venvs/transmitter`; edit `ExecStart` in the copied file if yours differs. It is `Type=notify` with `WatchdogSec=45min` and `Restart=always`, and it starts at boot (`sudo loginctl enable-linger` is no longer needed for it).
3. **Alerts.** Add to `<env file>`, which is `/etc/transmitter/<user>.env` from now on (mode 600, owned by `<user>`):
   ```
   SMTP_USERNAME=you@example.com
   SMTP_PASSWORD=<a Google App Password, pasted WITHOUT the spaces Google shows (sourcing the file in bash errors on them): Google Account -> Security -> 2-Step Verification -> App passwords>
   NTFY_TOKEN=<optional ntfy access token>
   ```
   and to `config.toml`:
   ```
   [alerts]
   email_to = "you@example.com"
   ntfy_url = "https://ntfy.sh/<your-topic>"
   ```
   `[antenna] site_url` must be set: the dead-clock check fetches `<site_url>/live.m3u8` once a minute, on the monitor thread (section 7.1). Then `sudo systemctl restart transmitter@<user>`.
4. **Config keys added in phase 2** (defaults as in `transmitter config init`; the config is strict, so a typo'd key is an error):

   | key | default | meaning |
   |---|---|---|
   | `[alerts] email_to` | unset | where hugo's email alerts go; unset = no email |
   | `[alerts] email_from` | unset (falls back to `SMTP_USERNAME`) | the From address |
   | `[alerts] smtp_host` | `smtp.gmail.com` | SMTP server (STARTTLS) |
   | `[alerts] smtp_port` | `587` | SMTP port (1-65535) |
   | `[alerts] ntfy_url` | unset | `https://ntfy.sh/<your-topic>`; unset = no ntfy. It now also carries antenna's pushes: hugo's relay (section 7.1) sends them here, and the Worker sends no ntfy of its own. With it unset the relay is off (one startup warning) and antenna's alerts arrive by email only |
   | `[alerts] repeat_hours` | `6.0` | re-send a still-firing alert at most this often |
   | `[alerts] dead_clock_seconds` | `120.0` (minimum 31) | the public `live.m3u8` older than this, on two consecutive checks, means the clock is dead. It is dated by its newest segment's start minus its own hold-back (`#EXT-X-START`, section 4 step 6), i.e. the segment airing when it was written; an off-air playlist is dated by its MEDIA-SEQUENCE less the hold-back last seen live |
   | `[alerts] guard_stale_minutes` | `45.0` | `state/guard.json` not evaluated for this long means the guard is dead. It must be at least `[publish] guard_check_minutes + 16` (the cache refresh plus the guard's 15-minute cadence and the cron lag), or the config is refused |
   | `[publish] guard_check_minutes` | `15.0` | how often hugo refreshes its cache of the guard's state; an unexpected 403 alerts only after `guard_check_minutes + 2` consecutive checks |
   | `[antenna] site_url` | unset | public base URL: Open Graph links and the dead-clock check (unset = no check) |
   | `[antenna] station_name` (phase 1) | `llama radio` | the station name in alert subjects and in the titles of relayed pushes |

   Env-file secrets (`/etc/transmitter/<user>.env`): `SMTP_USERNAME`, `SMTP_PASSWORD` (a Gmail App Password) and `NTFY_TOKEN` (optional; it covers both hugo's own pushes and the relayed antenna ones). With no channel configured, alerts reach only the journal.
5. **The watchdog.** transmitter pings systemd after every step, every publish batch, every batch of prune deletes and every show encode, so the longest silence is one show's encode (~10-20 min) or one show's analysis in the plan step (~8 min on 10-23) against `WatchdogSec=45min`. After restoring `~/.transmitter` **without** `cache/`, the first publish recomputes analyses for about 48 h of shows and may meet `WatchdogSec`: the service restarts and continues (each analysis is cached as it completes; at most one batch, up to 360 segments, is re-PUT per kill, within the daily PUT budget).

### 6.2 Tokens and email (dashboard)

1. **WAF token.** My Profile → API Tokens → Create Token → Custom token. Permissions: *Zone · WAF · Edit*. Zone resources: *Include · Specific zone · <zone>*. Keep the token for 6.3.
2. **Analytics token.** The existing *Account Analytics: Read* token (phase 1).
3. **Zone ID.** The zone's overview page → API → *Zone ID*.
4. **Email.** Email Routing must be enabled on the zone, with the destination address verified (phase 1). The sender is `alerts@lma-radio.com`, on the zone's domain. The `send_email` binding `ALERT_EMAIL` in `wrangler.jsonc` is unrestricted: it can only reach the account's verified destinations, and the one the Worker uses is the `ALERT_EMAIL_TO` secret (6.3), so the destination never enters the repo.
5. **Kill switch.** The custom rule *"station: kill switch"* (section 2 step 7) must exist **exactly once**, with action Block. The guard finds it by that description and refuses to touch it if it is missing, duplicated or not a Block rule. (Its description is the Worker var `KILL_SWITCH_DESCRIPTION`.)
6. **`STATION_NAME`** (a Worker var in `wrangler.jsonc`) no longer needs to be ASCII: the Worker sends no ntfy (it was the raw ntfy `Title` header). Relayed push titles use hugo's `[antenna] station_name`, while email subjects use the Worker's `STATION_NAME`: keep the two identical.

### 6.3 antenna

From `antenna/`, with `.env` holding `CLOUDFLARE_ACCOUNT_ID`:

1. Secrets (each command prompts for the value; nothing is echoed or committed):
   ```
   npx wrangler secret put CF_ACCOUNT_ID
   npx wrangler secret put CF_ZONE_ID
   npx wrangler secret put CF_ANALYTICS_TOKEN
   npx wrangler secret put CF_WAF_TOKEN
   npx wrangler secret put ALERT_EMAIL_FROM            # alerts@lma-radio.com
   npx wrangler secret put ALERT_EMAIL_TO              # the verified destination (its only copy)
   npx wrangler secret list
   ```
   A new deploy sets no ntfy secret: the Worker sends email only, and hugo relays its alerts to ntfy. An existing deploy deletes the two old secrets after this release: `npx wrangler secret delete NTFY_URL` and `npx wrangler secret delete NTFY_TOKEN`.
2. `npm ci && npm test`, then `npx wrangler deploy --dry-run` and check the output (it bundles and lists the bindings, `ALERT_EMAIL` among them). Then `npx wrangler deploy`.
3. `ANTENNA_BUCKET=lma-radio npm run deploy:assets` (the player's stall watch is in `player.js`/`nowplaying.js`).
4. Within two minutes, `npx wrangler r2 object get lma-radio/state/guard.json --remote --pipe` shows the following. `transmitter status` shows the same picture from hugo.
   - `evaluated_at` recent, `last_error: null`;
   - an `evaluation` with `actual_usd` ≈ 5 plus usage, and `budget_usd: 15`;
   - `waf.enabled: false`, `waf.error: null`;
   - `evaluation.unknown_action_types: []`.
5. Optional second channel for a dead clock: Notifications → Add → Workers → the Worker-error alert for `antenna`.

### 6.4 Deploys (alert gate and relay release)

1. Worker: `cd antenna && npx wrangler deploy --dry-run`, then `npx wrangler deploy`; then delete the `NTFY_URL` and `NTFY_TOKEN` secrets (6.3 step 1).
2. hugo: update the checkout, reinstall transmitter (6.1 step 1), `sudo systemctl restart transmitter@<user>`.

Between the Worker deploy and hugo's update, cloud alerts arrive by email only, with no push. The order does not matter. Before hugo updates, `state/alert-relay.json` simply accumulates; on first start hugo sends only messages younger than `RELAY_MAX_AGE_S` (1 h), so nothing older pages.

## 7. Operating

Run the `transmitter` commands below as `<user>` on hugo with the env file loaded and the venv on the path: `set -a; . /etc/transmitter/<user>.env; set +a` (the file is owned by `<user>`, mode 600), then `~/.venvs/transmitter/bin/transmitter …` (or put that `bin` on `PATH`). They need `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`, which live only in that file after 6.1.

- **Take the station off the air / back on:** `transmitter offair on --reason "…" [--until <iso>]` / `transmitter offair off`. These work while the guard is tripped and whatever the daily PUT budget says. With hugo down, write `state/offair.json` from the Mac; with the clock Worker broken, remove its cron trigger, then enable the kill switch by hand (both in section 4 step 4).
- **The guard tripped for spend:** it clears only in the next billing period, or after `transmitter budget --raise-to <usd>`. Either way it clears only if the guard's next evaluation is under the thresholds. `transmitter budget` shows the guard's state. A raise must exceed the current budget and may not exceed $100. It expires at the period's end. A raise must exceed BOTH the projected figure `transmitter budget` shows AND the actual spend divided by 0.9 (the guard trips at actual >= 90% of the budget OR projected >= 100%), or the next evaluation re-trips and consumes the raise. A `state/budget.json` that expires after the current billing period is ignored and alerted (`budget-file-invalid`); `transmitter budget --raise-to` always writes the period's end. The station's policy is to shut down on overrun, not to keep raising.
- **Tripped "blind"** (no reading for 6 h): fix the cause (analytics token, `CF_ACCOUNT_ID`, a Cloudflare API outage; see `last_error` in `transmitter budget`). The first successful reading under the thresholds clears it.
- **`transmitter status` / `budget` reading guide.** A `CORRUPT (…)` guard line means the clock treats the document as a spend trip; `offair CORRUPT` means the clock treats the station as off the air; a `<doc> unreadable: …` line states the clock's reading of that document; a raise shows whether the Worker honours it: `honoured`, `expired`, `ignored: …`, or `honoured (period end unknown)` when the period end cannot be read.
- **While `guard.json` is corrupt** and readings fail, `transmitter budget --raise-to` refuses (no period is known), even though the `guard-state-corrupt` alert recommends a raise: wait for the next successful evaluation.
- **All-clears are slow.** Every "resolved", including `tripped-spend` after `--raise-to`, arrives about 15 minutes after the condition clears: it must stay clear for the 15-minute cooldown first.
- **Alerts.** Cloud alerts are emailed by the clock Worker and pushed to ntfy by hugo's relay (up to ~1 min after the email). hugo alerts come from transmitter (email + ntfy). A check on the approved list that runs about every minute (never the spend or off-air alerts) alerts only after 3 consecutive failing observations (the gate; section 7.1). Each repeats every 6 h while active and says "resolved" when a latch or outage clears. The 50% and 80% spend alerts come once per billing period (and budget). A dashboard toggle of the kill switch is undone and alerted (`waf-corrected`). `transmitter status` lists both sets; a hugo event alert (a publish error, the PUT budget) drops off once 6 h pass without a new one.
- **Known limitations.**
  - *VLC at a fallback→live switch.* At a fresh run — the first start, an outage longer than the published lead, or a re-epoch — `EXT-X-DISCONTINUITY-SEQUENCE` restarts at 0. hls.js and Safari follow it; VLC goes silent and needs stop/play once.
  - *Cloud alerts need R2.* While R2 itself is unreadable, the cloud cannot send alerts (their state lives in R2); an R2 outage that hits the read of `state/alerts.json` silences cloud alerts for that minute, and hugo's dead-clock check is the cover for that case. An invocation whose guard could not read its state (`blocked: null`) may still try to read `state/alerts.json`.
  - *`guard-unknown` is not only an unknown outcome.* It can also appear when the guard did return a known outcome (a race between overlapping invocations).
  - *Overlapping cron runs.* When overlapping runs race, a one-minute unblocked window is possible after a trip. The trip is never lost: the next run re-blocks, and it is alerted. (See also the next bullet.)
  - *ENDLIST may lag a trip.* The same race: with two invocations overlapping right after a trip, the ENDLIST playlist can lag by up to about a minute. That matters only while the WAF API is also failing (a cooperative-only block).
  - *`lead-low` on a fresh start.* A fresh run (first start, or a restart after an outage longer than the lead) builds its lead from zero, so `lead-low` fires and later resolves while the lead grows (about 10 minutes of encoding per show on hugo). That alert is expected after a fresh start and needs no action.
  - *A pre-upgrade `guard-cache.json`.* On hugo, a `guard-cache.json` written before the upgrade lacks the `guard_evaluated_at` key and is treated as unknown (no false `guard-stale`). Expected.
  - *A future-dated budget raise.* If `state/budget.json`'s `written_at` is ahead of the Worker's clock (hugo's clock skewed ahead), the guard re-evaluates every minute until that time passes. Those are GraphQL reads, which are not billed; NTP on hugo keeps the window to seconds.

### 7.1 Alert keys

What each alert means and how to respond: `docs/playout-incident-runbook.md`.

**Cloud** (antenna, `state/alerts.json`). The "guard" family resolves whenever the guard returned a known outcome; the "clock" family (the Worker's playlist clock; unrelated to hugo's `clock` code below and to `clock.toml`) only on a complete invocation; a key in neither family is treated as clock. Titles are in the alert text; `waf-api` redacts ids.

| key | family | priority | kind | gate |
|---|---|---|---|---|
| `tripped-spend` | guard | urgent | resolvable | sent at once |
| `tripped-blind` | guard | urgent | resolvable | sent at once |
| `budget-50:<period>:<budget>` | guard | default | once per period and budget | sent at once |
| `budget-80:<period>:<budget>` | guard | high | once per period and budget | sent at once |
| `guard-reading-failing` | guard | high | resolvable | unchanged |
| `guard-unknown` | guard | high | resolvable | gated at 3 (read branch); sent at once from the post-unblock re-check |
| `budget-unreadable` | guard | high | resolvable | gated at 3 |
| `offair-corrupt` | guard | high | resolvable | sent at once |
| `budget-file-invalid` | guard | high | once | sent at once |
| `guard-state-corrupt` | guard | urgent | resolvable; its "resolved" text says the spend trip stays | sent at once |
| `waf-api` | guard | high | resolvable (ids redacted in alert text) | gated at 3 |
| `waf-corrected` | guard | high | sent on appearance, never "resolved" | sent at once |
| `guard-write` | guard | high | resolvable | gated at 3 |
| `guard-crashed` | clock | urgent | resolvable | gated at 3 |
| `index-write` | clock | high | resolvable | gated at 3 |
| `clock-inputs` | clock | urgent | resolvable | gated at 3 |
| `horizon-missing` | clock | default | resolvable | gated at 3 |
| `horizon-refused` | clock | urgent | resolvable | sent at once |
| `lead-low` | clock | high | resolvable | unchanged |
| `offair-without-fallback` | clock | high | resolvable | unchanged |
| `clock-failed` | clock | urgent | resolvable | gated at 3 |
| `metronome-down` | clock | high | resolvable | gated at 3; sent at once from the stall branch (2 consecutive stalled renews) |

**Gate.** A check that runs about every minute alerts only after `GATE` = 3 consecutive failing observations; a single failure is logged, not sent. The first message of a gated episode says it followed 3 consecutive failures. After that the episode behaves as before (repeats every 6 h, "resolved" for resolvable keys), except that a repeat also needs the streak to still be at 3, so a single blip inside an active episode never sends a repeat. The antenna list is `GATED_KEYS` in `antenna/src/alerts.ts` (observations are minutes, streaks live in `state/alerts.json`); the transmitter list is `GATED_CODES` in `alerts.py` (observations are service ticks, or monitor passes for `dead-clock-check`; streaks are in process and reset by a restart). The spend and off-air alerts, the one-shot keys and anything already debounced are never gated. The two immediate raise sites on antenna are `metronome-down` from the stall branch and `guard-unknown` from the re-check after turning the kill switch off.

**hugo** (transmitter, `~/.transmitter/alerts.json`):

- **Level codes**, active until resolved: `dead-clock` and `guard-stale` (resolved by the monitor), `station-root` and `plan` (by a successful plan step), `render` (by a successful render step), `monitor-stalled` (new: fired by the main tick when the monitor thread has completed no pass for 5 min or is not alive, **sent at once**; resolved by the main tick once passes are fresh again).
- **Event codes**, re-sent at most every `repeat_hours` and dropped from the active list once `repeat_hours` pass without a new fire: `publish`, `prune`, `publish-state`, `put-budget`, `horizon-held`, `frame-count-drift`, `dead-clock-check` (the dead-clock monitor itself raised an error; not the same as `dead-clock`), `clock` (phase 3: `clock.toml` is invalid and planning runs on the last-good copy, else the implicit open block; this is hugo's scheduler clock, not the cloud "clock" family; unlike the other event codes it sends "resolved", at the next fill once the clock is valid or absent), `history` (phase 3: `aired.jsonl` was not appended, e.g. the `publish.json` epoch differs from the station epoch; it also sends "resolved", on the next successful tick).
- **Gate.** Gated at 3: `prune`, `publish`, `publish-state`, `station-root`, `plan`, `render`, `dead-clock-check`. Sent at once: `put-budget` (spend), `frame-count-drift` (latches `halted`, fires once), `monitor-stalled`, `clock`, `history`. Unchanged (already debounced): `dead-clock`, `guard-stale`, `horizon-held`.

**The monitor thread.** The dead-clock check and the relay run on a daemon thread every 60 s, independent of plan, render and publish (a plan step analysing shows over NFS used to delay `dead-clock` by 13+ min). The thread starts when `[antenna] site_url` or hugo's ntfy is configured; each part runs only if its own configuration is present. It has its own get-only R2 reader (short timeouts), never writes to R2, never touches `guard-cache.json` and never pings the watchdog, so the watchdog still means "the main loop is alive". It reads `state/guard.json` and `state/offair.json` itself (2 class-B GETs a minute; with the relay's GET of `state/alert-relay.json`, about 3 a minute, ~130k a month, ~1.3% of the 10M allowance) instead of using hugo's 15-minute cache. `transmitter run --once` runs one tick and then one dead-clock check on the main thread; it does not relay and starts no thread.

**Relay.** After emailing, the Worker appends all of an invocation's sent messages (redacted) to `state/alert-relay.json`: a random `stream` id and a ring of the last 50 `{seq, at, key, kind, priority, title, message}`, `seq` strictly increasing within the stream, written in one write (at most 2 PUTs on a lost race), bounded at 10 s. A message counts as delivered if its email was accepted or the relay write succeeded. Each monitor pass GETs the object and sends qualifying messages to hugo's ntfy only: title `<station_name>: [resolved: ]<title>`, priorities urgent 5, high 4, default and resolved 3, tags matching antenna, and a body ending `-- relayed from antenna (<key>, <at>)`. hugo's cursor `(stream, seq)` is kept in memory and written best-effort to `~/.transmitter/alert-relay-cursor.json`; no cursor, or a different stream, means start from `seq` 0. A message is sent only when younger than `RELAY_MAX_AGE_S` (1 h), which is what prevents a backlog storm after hugo was down. The cursor advances past every message handled: sent, skipped for age, or refused by ntfy with a 4xx other than 429 (a WARNING). A message ntfy can never accept (a CR/LF in the title, a lone surrogate) is cleaned (CR/LF to a space, a surrogate to `?`) or, failing that, skipped with a WARNING. A 429, a 5xx or a transport error stops the pass and the next minute retries from that message. A pass stops sending after 30 s. A missing object means nothing to relay; a malformed or unreadable one is a WARNING only, never an alert (email covers it). With no ntfy configured on hugo the relay is off.

**Limits.**

- A gated key failing in alternate minutes never alerts (the consecutive rule), and antenna writes `alerts.json` about once a minute while it does (within the spend bounds).
- One R2 problem whose symptom rotates between gated antenna keys minute to minute (`guard-unknown`, `clock-inputs`, `index-write`) resets each key's streak, so it may never alert; hugo's `dead-clock` is the cover.
- transmitter gates count ticks, not minutes: during a fill a tick can run 17+ min, so a gated `publish`/`prune`/`publish-state` failure can take ~50 min to page. Harmless with a ~20 h lead.
- During an R2 write outage a pending antenna streak cannot be saved, so the gated keys that report it (`guard-write`, `index-write`, `clock-failed`) stay silent, and an ungated alert goes by email only (its relay write fails). During an R2 read outage antenna sends nothing at all, as before (dispatch reads `alerts.json` first). hugo's `dead-clock` is the cover in both.
- Pushes arrive up to ~1 min after antenna's email.
- hugo down means no relay; email covers it. If email also fails while hugo is down (or its ntfy is failing), the relay write still counts as a delivery, so the alert is not re-sent until `repeat_hours`.
- A cursor file that is lost, or left behind by failed writes, can re-send up to an hour of relayed messages once, at the next start.
- On antenna, an undelivered first message resent after a clean minute goes out at once without the "3 consecutive" note (wording only).
- **Operator ruling (2026-10-24):** the five playlist keys (`clock-inputs`, `clock-failed`, `guard-crashed`, `guard-unknown` read branch, `horizon-missing`) stay gated. They mean cron did not write the playlist that minute, which matters only when cron is the only writer (`METRONOME` off, or the Durable Object judged down); the 3-minute gate exceeds the ~123 s player runway, and hugo's `dead-clock` (~3-4 min) is the independent cover.

### 7.2 Clock and schedule (phase 3)

The scheduler appends to the persisted plan from the plan's end, driven by the clock: `<TRANSMITTER_ROOT>/clock.toml` (default `~/.transmitter/clock.toml`). Each time it loads a valid clock it keeps a copy as `clock.last-good.toml`. The pieces it plans are shows plus one-clip interstitials (announcements, station IDs) from the interstitials folder.

- **No clock file:** planning uses the implicit clock, a daily 00:00 open block with a ±12 h window (so `schedule` shows seven `open` occurrences a week), and `transmitter status` says `no clock: open all week`.
- **The clock is strict.** Unknown keys and bad values are errors; non-finite numbers are rejected; window fields may not exceed one week. `Prefer.weight` must be > 0 and `on_this_day` >= 0. `concert_gap_days = 0` disables the gap rule (the least recently aired show still ranks first, over a 365-day horizon). `max_shows` defaults to 2 for a profile block and is unbounded for an open block; a long profile block whose pool cannot fill it at `max_shows` gets fill; `schedule` labels the cause "pool short" or "longer than max_shows". Raising `max_shows` is a clock choice (real blocks will mostly be 2-3 h).
- **A block runs until the next block's start; every hour of the week belongs to some block.**
- **Edit a draft, never the live file.** The first time, write `draft.toml` from the example below; afterwards copy `clock.toml` to a draft. Edit it, check it, then move it into place:
  ```
  transmitter schedule --clock draft.toml      # previews the next --days (default 7) under the draft
  mv draft.toml ~/.transmitter/clock.toml
  ```
  `schedule` and `library` are read-only (nothing written). `schedule --library delivered` previews against all delivered packages, not only the eligible ones.
- **An invalid live clock** alerts `clock` (first at the next fill, not at once; it clears at the next fill after the fix). `status` shows `clock      last-good (invalid clock at …)`, or `clock      no clock: open all week (invalid clock at …)` when there is no last-good copy. Planning continues on `clock.last-good.toml`, else on the implicit clock.
- **Edits reach air after the persisted plan:** about one lead plus one show (the plan is append-only; rows already persisted are never rewritten).
- **Reading `schedule` / `status`.** A block entered mid-way (the phase-1 cutover, a fresh run after an outage) records a MISS on its first show by design. Bends are counted once per block and only for options the bounded search offered, so they may undercount. `transmitter library` lists eligible shows by profile, the interstitial pool, and ineligible packages by first reason.
- **`awaiting_fix`.** A delivered package whose manifest carries a non-null top-level `awaiting_fix` is not airable: `library` lists it under `awaiting fix from llama` (without the reason; `packages/transmitter/scripts/probe_estimates.py --config <config.toml> --time-one SLUG` prints it, and is where to see the reason). A planned row not yet encoded is dropped by render's skip path; a show already encoding or on air finishes. Known limitation: if a marked show is on air and its `render/shows/<key>.aac` is lost by hand, render refuses to re-make it (`LayoutError`) until recovery cuts a new run.
- **Rotation history.** `aired.jsonl` in the workspace is append-only, one row per published-and-past piece, idempotent across restarts, and backfilled from `plan.jsonl` on first run. A crash can leave a partial last line; it is skipped with a warning on every load (harmless; remove that one fragment by hand, with the service stopped, if the warning bothers you). History appends refuse (alert `history`) when `publish.json`'s epoch differs from the station epoch.
- **Plan lock.** The service holds one non-waiting plan lock only during its plan/render steps while filling; a manual `transmitter plan`/`render` normally succeeds otherwise, and refuses with `PlanLocked` only on overlap.

Minimal annotated `clock.toml` (keys and defaults from `packages/transmitter/src/transmitter/clock.py`; only `timezone` and at least one `[[block]]` are required; `profiles` are llama profile names, and a block with none is an open block):

```toml
# Required: the zone block start times are written in.
timezone = "America/New_York"
# Default window around each block's nominal start (minutes early and late).
wiggle_minutes = 15

[announce]
# Optional. Defaults shown. Editing any of these retires voiced clips.
# next = "Coming up next, {title}. Then at {next_time}, {next_title}."
# next_one = "Coming up next, {title}."
# later = "Stay tuned for {title} at {time}, followed by {next_title} at {next_time}."
# later_one = "Stay tuned for {title} at {time}."
time_format = "short12"            # short12 | hm12 | 24h
zones = [
  { tz = "America/New_York", label = "Eastern" },
  { tz = "America/Los_Angeles", label = "Pacific" },
]

[open]
# Profiles left out of open time and of profile blocks' fill. The exclusion bends,
# and only when the open pool would otherwise be empty.
exclude_profiles = []

[rotation]
concert_gap_days = 45              # 0 disables the gap rule
on_this_day_weight = 3.0

# A block runs until the next block's start. A block with no profiles is an open block (max_shows unbounded).
[[block]]
name = "evening-dead"
title = "Dead Evening"
days = ["fri", "sat"]              # or "daily"
start = "20:00"                    # HH:MM local
profiles = ["dead"]                # llama profile names
max_shows = 2                      # default 2 for a profile block
wiggle_minutes = 20                # or early_minutes + late_minutes together, not both
prefer = [
  { years = "1972-1974", weight = 2.0 },
  { on_this_day = 3.0 },           # this block's own on-this-day weight (overrides [rotation])
]

[[block]]
name = "late-open"
title = "Late Mix"
days = "daily"
start = "23:00"
early_minutes = 10
late_minutes = 30
```

### 7.3 Announcements and station IDs

Announcement texts and ids derive from the clock alone: the id is a hash of the rendered text, so editing the templates, titles, `time_format` or zones retires the clips already voiced (re-export and re-voice). The two-block forms (`next`, `later`) are used only when the following occurrence is a DIFFERENT block starting within 12 h of X's start (`announce.TWO_BLOCK_MAX_HOURS`); otherwise the one-block forms. A time names every zone in `[announce] zones` (default Eastern, Pacific).

`[interstitials] dir` must be an absolute path (default `<station root>/interstitials`). Station IDs are any `id-*.mp3` in it. The station's on-air name is "LMA Radio" (exact capitalisation): use it in the station IDs; the player shows it between shows (its page title).

Copy-paste workflow:

1. On hugo, export the scripts still missing audio: `transmitter announcements [--clock FILE] --export <dir>` (writes `ann-<id>.txt`; pass `--clock draft.toml` to voice a draft clock's announcements before moving it into place, so new blocks are announced from the first occurrence; without `--export` it lists what the clock needs, present or missing, over `--days`, default 8). Copy the files to the Mac's interstitials folder.
2. On the Mac, voice them:
   ```
   cd /Volumes/media/lma-radio/delivered/interstitials && for f in ann-*.txt; do [ -e "${f%.txt}.mp3" ] || emcee say "$f"; done
   ```
   The `-e` test skips scripts already voiced: re-voicing costs TTS spend, takes the clip out of the pool for the quiet period, and re-plans unencoded rows that use it. `emcee say` mixes the house `[tts] bed` under the clip unless given `--no-bed`; that is the operator's choice.
3. A clip is used only once it is older than the quiet period (`[station] quiet_minutes`, default 10), so a half-written file is never picked up.

Missing audio degrades gracefully: two-block form, then one-block form, then a station ID, then a plain gap. `status` and `schedule` list what is missing. A broken promise (an announcement that named a block that then did not air) is logged `announcement-broken` and never alerted.

### 7.4 Phase-3 cutover checklist

1. Deploy HEAD to hugo and restart the service (`sudo systemctl restart transmitter@<user>`).
2. The first tick backfills `aired.jsonl` from `plan.jsonl`.
3. The scheduler appends from the end of the phase-1 plan, which runs about a lead (~a day) ahead of air. The MISS therefore lands on the block where that plan ends, at the first fill after the deploy, not on the block airing at cutover; that is by design, not a fault.
4. `clock.toml` is optional: without it the station runs the implicit open clock (open all week). Add one later from the example in 7.2.
5. Create the interstitials folder (`[interstitials] dir`, absolute; default `<station root>/interstitials`), then voice station IDs (`id-*.mp3`) and the announcements (7.3).
6. Check with `transmitter status` and `transmitter schedule`.
7. The player change (`antenna/public/nowplaying.js` and `player.js`, commit `6e0e282`) reaches listeners only after the assets deploy; run it from `antenna/` (operator step): `ANTENNA_BUCKET=<bucket> npm run deploy:assets`. Until then station breaks show "We'll be back shortly."

### 7.5 Rolling transmitter back

- The commit that made plan rows tolerate scheduler fields (`4fa87a7`, "tolerant plan rows with scheduler fields; non-show rows skipped downstream (deploy before the scheduler)", plus its fix `af46d72`, "serialise phase-1 plan rows byte-identically") writes phase-1-shaped rows only (a scheduler field is written only when it differs from its default). `af46d72` was deployed to hugo before the scheduler. Rolling back from it to the build before it stays safe until a scheduler build writes its first scheduler row.
- A build from before that commit cannot read a plan that holds scheduler rows: plan, render and publish wedge. Once the scheduler has run, `af46d72` is the oldest safe rollback target. It is also the commit that keeps interstitial rows out of `timeline.json`, `notes/` and `show/`.
- Never truncate `plan.jsonl` by hand: a shortened plan restarts the run over segment keys already published (and immutable).
- Before rolling back past `684d323` ("interstitials folder scan, announcement texts with time zones, announcements command"), the commit adding `[interstitials]`, remove `[interstitials]` from `config.toml`, or the older build refuses the unknown section.

## 8. Phase-2 verification checklist

Run with the station up and **not yet shared**. Run the `transmitter` commands as described at the top of section 7. Record each result (date, observation) in `docs/superpowers/<date>-playout-phase2-verification.md`. Restore the normal deploy (`npx wrangler deploy`, with no `--var`) after each item that changes it.

- [ ] **The guard reads and prices usage.** `guard.json` → `evaluation`: compare `period_to_date` with the dashboard's R2 metrics for the period (sampled; expect agreement within a few percent). Read Worker requests on the **billing page**, which lags `guard.json` by about a day (it is daily data published late): compare it against `guard.json`'s figure from a day earlier, not the current one. antenna has no routes, so its requests are its cron invocations, about 1,440 a day; there is no requests graph under Workers & Pages → `antenna`. `unknown_action_types` is `[]`; otherwise record the strings. Also confirm the **first** `state/guard.json` write succeeded on production R2: there is no `guard-write` alert and the document exists. The create-only precondition itself (`onlyIf: { etagDoesNotMatch: "*" }`, verified only in miniflare) is not observable from outside: the Worker falls back to an unconditional put.
- [ ] **Off-air blocks fully and comes back.** `transmitter offair on --reason test`. Within ~1 min:
      - `curl -s -o /dev/null -w '%{http_code}\n' https://<host>/live.m3u8` → 403 (kill switch);
      - the dashboard shows the kill-switch rule enabled;
      - `curl -s https://<host>/` → the off-air page (`/` is cached up to 60 s, `max-age=60`, so at the edge and in a browser this can take about 2 minutes). Do **not** test with `grep -i 'off the air'`: it always matches, because the notice is a hidden div in the normal player page. Grep for something only the off-air `index.html` carries (compare the two pages' bodies and pick a string that differs);
      - `transmitter status` → `offair ON`, `killswitch enabled`.

      Then `transmitter offair off`. Within ~1 min everything reverses and players can tune in again. Repeat once with the Mac-side write of `state/offair.json` (section 4 step 4) in place of `transmitter offair`.
      - Also confirm the WAF block answers **403** on the R2 custom domain; any other status counts as "unreachable" to hugo and alarms after 10 checks.
      - After an off-air on/off, confirm the kill-switch PATCH kept the rule whole: its expression, action and description in the dashboard are unchanged, and only `enabled` toggled.
- [ ] **An already-playing page shows the notice** (amendment A2). Play in Chrome and in Safari, then `transmitter offair on`. Chrome (hls.js) shows "The station is off the air." with *Try again* at its next playlist reload (the 403 or the ENDLIST playlist), within about a minute. Safari keeps playing what it has buffered first: with the hold-back that is up to ~120 s (section 4 step 6), then the 15 s stall watch and two probes 10 s apart, so expect up to about 2.5 minutes. VLC stops on ENDLIST. Then `offair off`. Record the measured times.
- [ ] **Joining on iPhone and Chrome starts near the wall clock (now-playing matches the schedule).** Press *Play* on an iPhone (Safari) and in Chrome on the Mac. Within a few seconds of starting, the now-playing line names what `timeline.json` (or `transmitter status`) schedules for the current wall-clock time, not the item from about two minutes earlier; `curl -s https://<host>/live.m3u8` shows `#EXT-X-START:TIME-OFFSET=-122.880`, `#EXT-X-SERVER-CONTROL:HOLD-BACK=122.880` and its last `PROGRAM-DATE-TIME` about 2 minutes ahead of the wall clock. Record each player's offset from the schedule. **Not measurable until phase 3:** `transmitter status` shows the show on air, not a position inside it, and no player yet shows a position readout (hls.js `playingDate` against `Date.now()`, or a timestamped now-playing line). Until then, record only that the two players are close to each other and the START/HOLD-BACK values above.
- [ ] **A network blip shows no notice.** While playing in Chrome, toggle the Mac's Wi-Fi off for ~20 s, then on. The page says "Reconnecting…" while stalled, never the off-air notice, and resumes (or needs one *Play*).
- [ ] **A spend trip and a raise.**
      1. `npx wrangler deploy --var MONTHLY_BUDGET_USD:5.5`. Within 15 min (the next evaluation), the actual $5+ is ≥ 90% of $5.50, so you see:
         - an urgent email "Station blocked: spend" (the push follows via hugo's relay within ~1 min; `tripped-spend` is never gated);
         - the station blocked as above;
         - `transmitter budget` → `TRIPPED (spend)`.
      2. `transmitter budget --raise-to 7` (or any figure above both the projected one that `transmitter budget` shows and actual / 0.9: the trip is actual >= 90% OR projected >= 100%). Within ~1 min the raise triggers an evaluation; it is under the thresholds, so the station is unblocked within ~1 min, and the "resolved" message arrives about 15 minutes later (section 7's cooldown).
      3. Restore: `npx wrangler deploy` (the budget is back to 15; the $7 raise is below it and ignored). Also delete the test raise: `npx wrangler r2 object delete lma-radio/state/budget.json --remote`; otherwise a re-run of this item in the same period never trips and `--raise-to 7` is refused. Extra once-only spend-level alerts are expected (their key carries the budget): the 50% alert at $7 is expected; the 80% one appears only if max(actual, projected) >= $5.60, so its absence is not a failure.
- [ ] **A blind trip.**
      1. Have the real token value at hand (or be ready to roll the token in the dashboard): secrets cannot be read back. Set `CF_ANALYTICS_TOKEN` to a wrong value (`npx wrangler secret put CF_ANALYTICS_TOKEN`), then `npx wrangler deploy --var BLIND_AFTER_SECONDS:900 --var GUARD_EVAL_SECONDS:60`. About 15 min after the last success the station blocks with "Station blocked: guard blind", and `guard.json` `last_error` names the failure.
      2. Restore the real token. The next evaluation unblocks the station.
      3. Restore the deploy.
- [ ] **A dashboard toggle is undone and alerted.** Enable the kill-switch rule in the dashboard while the station is on air. Within ~1 min it is disabled again and a "Kill switch corrected" (`waf-corrected`) alert arrives.
- [ ] **A Rulesets failure.** Have the real `CF_WAF_TOKEN` value at hand (or be ready to roll the token): secrets cannot be read back. Set `CF_WAF_TOKEN` to a wrong value. `guard.json` `waf.error` is set within ~1 min. `waf-api` is gated, so the "Kill switch not reconciled" alert arrives after 3 consecutive failing minutes (~3 min), by email and then the relayed push (allow a few extra minutes after the `wrangler secret put`: the old version may keep firing briefly, and its clean minutes reset the streak). With `offair on` at the same time, `live.m3u8` is the ENDLIST playlist and `/` is the off-air page (the block is cooperative). Restore the token: the rule is enabled within a minute, then `offair off`.
- [ ] **Lead floor.** `npx wrangler deploy --var LEAD_FLOOR_HOURS:30`: a "Published lead below floor" alert (`lead-low`, not gated) arrives by email within a minute. **Relay (a):** the same alert reaches the phone through hugo's ntfy within ~2 minutes of its email, with a body ending `-- relayed from antenna (lead-low, <time>)`. If it does not, check `[alerts] ntfy_url` on hugo, the journal for relay WARNINGs (`grep transmitter.relay`) and that `state/alert-relay.json` exists. Restore.
- [ ] **Relay (b): a gated key does not page on a single failure.** Have the real `CF_WAF_TOKEN` value at hand: secrets cannot be read back. Set `CF_WAF_TOKEN` to a wrong value, wait for one failing minute (`npx wrangler tail`, a `waf-api` line, or `guard.json` `waf.error`), then restore the real token before the next cron invocation: nothing is sent, by email or push. Break it again and leave it for three consecutive minutes: exactly one `waf-api` alert arrives (email, then the push), and its text notes that it followed 3 consecutive failures. Restore the token; "resolved" arrives ~15 minutes later. Allow a few extra minutes after each `wrangler secret put`: it deploys a new version, the old one may keep firing briefly (measured 10-23), and its clean minutes reset the streak.
- [ ] **`site_url` serves the playlist at its root.** `curl -s <site_url>/live.m3u8` returns the playlist: the dead-clock check fetches exactly that URL once a minute.
- [ ] **A dead clock.** Workers & Pages → `antenna` → Settings → Trigger events → delete the cron trigger. Dashboard propagation of the deletion is slow (9 minutes measured on 10-23, up to ~15 documented). With the metronome on, the playlist freezes when the last lease (15 min) expires, and hugo's `dead-clock` follows ~17-18 min after cron actually stops (plus the propagation delay), about 27 min after the deletion in all, given the 9-minute propagation measured on 10-23 (when it was due; the alert itself came at ~40 min then, because of the tick starvation this release fixes). The monitor thread runs the check every 60 s, whatever plan or render are doing. hugo sends `dead-clock` by email + ntfy itself. Within about an hour it sends `guard-stale`. Restore with `npx wrangler deploy`; both send "resolved".
- [ ] **The watchdog.** The order matters: a `systemctl edit` `WatchdogSec` drop-in does **not** reach a running service (measured 10-23: the first run waited 7 minutes and tested nothing). Edit, then restart, then stop it.
      1. `sudo systemctl edit transmitter@<user>` → `[Service]` `WatchdogSec=2min`.
      2. `sudo systemctl restart transmitter@<user>` and wait ~1 min for a tick.
      3. `sudo systemctl kill -s STOP transmitter@<user>; date`.
      4. `sudo journalctl -u transmitter@<user> -f`. Every `journalctl` here needs `sudo`: without it the PID-1 lines (the watchdog timeout) are hidden, and transmitter logs nothing at startup. Expect `Watchdog timeout (limit 2min)!` within 2 min of the STOP, an immediate SIGABRT kill, and a restart 30 s later: about 2.5 min from the hang to a running service (2 min 26 s measured). Publishing pauses ~3 min, with no effect on air.
      5. `sudo systemctl revert transmitter@<user> && sudo systemctl restart transmitter@<user>`, and reboot hugo once to see it come back by itself.

      With a 2-minute limit, a plan or render step (one analysis or one encode, several minutes each; the plan step now pings after each analysis, the render after each encode) could itself trip the watchdog. If a restart comes before the STOP, check whether a fill was running.
- [ ] **Cron lag, 24 h** (carried from phase 1): median, p99, max, and the count over 25 s, from the phase-1 capture.
- [ ] **Cron lag plus guard time, 24 h** (Task 18's input): from a day of phase-2 clock lines, the median, p99 and max of `lagMs` and of `lagMs + guardMs`, and the count with `lagMs + guardMs` over 25 s, together with the Task 18 decision.
- [ ] **A week of op counts** (carried from phase 1, due 2026-10-18), now with the guard's own reads and writes: compare with `guard.json`'s `period_to_date`.

**Notes (expected, not pass/fail).** (1) When overlapping cron runs race, a one-minute unblocked window is possible after a trip; the trip is never lost, the next run re-blocks, and it is alerted: record any occurrence (section 7, known limitations). (2) After the upgrade, a `guard-cache.json` without the `guard_evaluated_at` key is treated as unknown, so no false `guard-stale` should arrive.

When every item passes, the station may be shared publicly (spec, Phases item 2).

## 9. The metronome: rollout, rollback, verification

Spec: `docs/superpowers/specs/2026-10-14-antenna-metronome-design.md` (Rollout). Record results in `docs/superpowers/<date>-metronome-verification.md`. Run from the main checkout's `antenna/` with `.env` loaded (`set -a; . ./.env; set +a`: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_ANALYTICS_TOKEN`). `.env` is gitignored, so a worktree has none.

1. **Tear down the alarm probe** (its Durable Object would otherwise appear in the account-wide DO meters). From `~/lma-radio-ops/do-alarm-probe`:
   ```
   npx wrangler deploy --var STOP:1     # cron deletes the alarm; alarms stop re-arming
   # wait ~1 min; confirm no new "event":"alarm" lines arrive in tail.jsonl, then:
   pkill -f 'cli.js tail alarm-probe'
   npx wrangler delete                  # removes the Worker (name from its wrangler.jsonc)
   ```
   If `wrangler delete` refuses because of the Durable Object class, add `{ "tag": "v2", "deleted_classes": ["Probe"] }` to the probe's `migrations`, remove its `durable_objects` binding and its `ensure` call, `npx wrangler deploy`, then `npx wrangler delete`.
2. **Deploy with `"METRONOME": "off"`** (as committed): `npm ci && npm test && npm run typecheck`, `npx wrangler deploy --dry-run` (it lists `env.METRONOME_DO (Metronome)` and `env.METRONOME ("off")`), then `npx wrangler deploy` (its output ends with `schedule: * * * * *`). The class now exists, and the guard reads the three DO meters. **Pass** only when, at the guard's next evaluation (within 15 min), `npx wrangler r2 object get lma-radio/state/guard.json --remote --pipe | python3 -m json.tool` shows `last_error: null` and `evaluation.period_to_date` carrying all seven meters (`workersRequests`, `r2ClassA`, `r2ClassB`, `r2StorageGbMonth`, `doRequests`, `doDurationGbS`, `doRowsWritten`). Nothing on air changes: the clock's loop writes as before.
3. **Flip on:** set `"METRONOME": "on"` in `wrangler.jsonc`, commit, `npx wrangler deploy`. Within two minutes, `npx wrangler tail antenna --format pretty` shows clock lines with `"metronome":{"sent":"play","status":{"applied":"accepted",...},"fallback":null}` and `"puts":0`, and Durable Object alarm events about every 10 s. The guard's first evaluation after the flip may fail with `the metronome is on but the recent window reads doRequests=0`, and `guard.json` shows that failure until the next evaluation (≤ ~20 min): expected, and harmless (the blind rule needs 6 h).
4. **Verification day:** a 24 h `wrangler tail antenna` and `live.m3u8` poller, including a weekday daytime (section 9.1 below). Deploy twice during the day (`npx wrangler deploy`, no change) and note the times.

**Rollback.** Immediate: `npx wrangler deploy --var METRONOME:off`. The next cron invocation runs its own loop, and the object's next alarm reads `off`, deletes its alarm and writes nothing. A `--var` lasts only until the next plain deploy, so make it durable by committing `"METRONOME": "off"`. If the Worker itself is broken, section 4 step 4's broken-Worker order applies unchanged. Roll back the same way, rather than ride it out, when `metronome-down` persists while `METRONOME` is `"on"` (the object absent or broken): with no Durable Object activity, every guard reading also fails (`doRequests=0`), and the station trips blind after 6 h.

**A dead cron, now.** The object keeps the station playing for at most 15 minutes on its lease, then stops writing and re-arming. The playlist freezes, and hugo's `dead-clock` check alerts (newest segment older than `dead_clock_seconds`, 120 s, on two checks a minute apart); independently hugo alerts `guard-stale` once `guard.json`'s evaluation is older than `guard_stale_minutes` (45). A cron outage is therefore detected ~17-18 minutes after the last renew, against ~3-4 minutes before the metronome. Accepted (spec, Decision 3).

**Known limitations.** An alarm chain that breaks with no error freezes the playlist until the next renew, up to one cron gap (≤ ~200 s on a bad day). It shows on the clock line as `metronome.status.stalledMs` with no alert; two in a row fall back and alert. During a fallback minute both writers may write, and their off-air MEDIA-SEQUENCE can differ (cosmetic: both end in ENDLIST). The object's "logged once" marks are memory only and the object is evicted between ticks, so a persisting anomaly may log every tick (inside the Workers Logs allowance). An R2 PUT the object has waited 5 s for is counted as failed (`metronome-put-failed`, `lastBody` cleared, the next tick retries), but R2's `put` cannot be aborted, so it may still land, even after a later successful PUT: the playlist can then show an older MEDIA-SEQUENCE until the next tick (≤ ~10 s). The slot was counted against the PUT cap before it was issued, so this costs no extra spend.

### 9.1 Verification-day capture and pass criteria

```
mkdir -p ~/lma-radio-ops/metronome-tail
nohup npx wrangler tail antenna --format json > ~/lma-radio-ops/metronome-tail/tail.jsonl \
  2> ~/lma-radio-ops/metronome-tail/tail.err < /dev/null &
```

Alongside it, an independent poller fetches `live.m3u8` as a listener does, every ~5 s, and logs the fetch time, `MEDIA-SEQUENCE` and the last `PROGRAM-DATE-TIME`. Freezes are measured from it: the Durable Object logs anomalies only once per episode, so its lines are diagnostic, not a freeze record.

```
cat > ~/lma-radio-ops/metronome-tail/poll.py <<'EOF'
import datetime as dt, os, re, time, urllib.request
URL = "https://listen.lma-radio.com/live.m3u8"
OUT = os.path.expanduser("~/lma-radio-ops/metronome-tail/poll.tsv")
while True:
    t0 = time.time()
    try:
        req = urllib.request.Request(URL, headers={"user-agent": "metronome-verification-poller"})
        body = urllib.request.urlopen(req, timeout=10).read().decode()
        seq = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", body)
        pdt = re.findall(r"#EXT-X-PROGRAM-DATE-TIME:(\S+)", body)
        row = f"{seq.group(1) if seq else '-'}\t{pdt[-1] if pdt else '-'}"
    except Exception as e:
        row = f"error\t{type(e).__name__}: {e}"
    with open(OUT, "a") as f:
        f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds')}\t{row}\n")
    time.sleep(max(0.0, 5 - (time.time() - t0)))
EOF
nohup python3 ~/lma-radio-ops/metronome-tail/poll.py > ~/lma-radio-ops/metronome-tail/poll.err 2>&1 < /dev/null &
```

`poll.tsv` has one row per fetch: UTC fetch time, `MEDIA-SEQUENCE`, last `PROGRAM-DATE-TIME` (or `error` and the reason). A freeze is a run of fetches with the same `MEDIA-SEQUENCE`, from the first fetch that shows it to the first that shows the next; normal is ~10 s, give or take the 5 s poll and the 5 s `max-age`.

The capture holds three kinds of event: cron invocations (`executionModel: "stateless"`, `event.cron`, with the `clock` line in `logs`); Durable Object alarms (`executionModel: "durableObject"`, `event.scheduledTime`, `outcome`); and renew RPCs (`executionModel: "durableObject"`, `event.rpcMethod: "renew"`). **Pass:**

- no playlist freeze over 45 s in `poll.tsv` outside a reported `metronome-down`, except silent chain breaks: at most 1-2 in the day, each tied to a single stall on the clock line (provisional: the probe's handler did no R2 PUT);
- the DO meters in `guard.json` (`evaluation.period_to_date.doRequests`, `doDurationGbS`, `doRowsWritten`) agree with the dashboard's billable usage for the period;
- playlist PUTs at most ~one per boundary plus one per renew (≈ 7/min, ≈ 10k/day), counted from the DO and clock lines; below the cron-only rate is expected;
- after each deliberate deploy, the alarm chain continues within ~10 s, or the next renew repairs it within a minute.
