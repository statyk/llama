# antenna

The cron-only Worker and static player in `antenna/`. The repo overview is the root `CLAUDE.md`; the publishing side is `packages/transmitter/CLAUDE.md`.

## Overview

`antenna/` is a
cron-only Worker (no routes, `workers_dev = false`) that rewrites `live.m3u8`
at every grid boundary, plus the static player; listeners only ever fetch
cache-served R2 objects. Its clock bounds its own spend
(`antenna/src/clock.ts`): `MAX_PUTS = 10` per invocation, a horizon whose `d`
is not 10.24 is refused (`horizon-refused`, nothing written), and
`LOOP_SECONDS` is clamped to 75 (`loop-clamped`). Off-air (from
`state/offair.json`, or a horizon more than 24 h stale) plays the notice from
the fallback, so transmitter publishes NOTHING — no segment, no horizon — until
`fallback render` has recorded a fallback version in the workspace: every
publish pass alerts `no fallback rendered` instead (gated: after 3 consecutive ticks; the fallback check sits before the
first PUT, since segment files are dropped only after a horizon PUT and would
otherwise be re-PUT every tick), and prune likewise refuses to rewrite the
horizon (`stopped: no-fallback`, before any delete) if `fallback.json` is lost
later. Every horizon therefore names a fallback (publish, prune and `fallback
render` are its only writers). If the named fallback is unusable in R2 anyway
(its `index.json` deleted by hand, or `len < 1`), off-air writes an
ENDLIST-only playlist (no notice; players stop) and logs
`offair-without-fallback` once per invocation; the WAF kill switch remains the
hard stop (`docs/playout-setup.md` section 4 step 4).
**Cost guard (phase 2).** It runs first in every antenna invocation
(`antenna/src/guard.ts`), evaluating when its last attempt is 15 min old (or at once after a raise) through
the account-scoped GraphQL API, pricing through the allowances plus the $5
base and projecting each meter from the last 3 h. The `tripped` latch sets at
actual >= 90% or projected >= 100% of `MONTHLY_BUDGET_USD`, and also when blind
(no reading for 6 h). `blocked = tripped OR offair` is reconciled every
invocation (ENDLIST playlist, off-air `index.html`, the kill-switch WAF rule
found by its description) with etag-conditional PUTs so a trip is never lost;
an unreadable state means the invocation writes nothing. Alerts go out after
the last playlist write, and the clock line logs `guardMs`. VLC needs
stop/play at a fallback-to-live switch of a fresh run
(`EXT-X-DISCONTINUITY-SEQUENCE` restarts at 0): a documented limitation. The
spend bounds above (`MAX_PUTS = 10` etc.) are unchanged. **Playlist
hold-back:** live playlists list `PLAYLIST_WINDOW` 16 segments, ending
`PLAYLIST_LOOKAHEAD` 12 past the one airing, with `EXT-X-START` and
`EXT-X-SERVER-CONTROL:HOLD-BACK` at 122.88 s (`PLAYLIST_HOLD_BACK` 12), so
players sit at the wall clock with ~123 s of runway against a late cron fire.
Keep lookahead = hold-back (hugo's dead-clock check dates the playlist by its
own hold-back); a lookahead alone adds no runway. Phase-2 SDD record:
`docs/superpowers/2026-10-12-playout-phase2-sdd/`.


**The metronome** (`antenna/src/metronome{,-core,-engine}.ts`; spec `docs/superpowers/specs/2026-10-14-antenna-metronome-design.md`). With the var `METRONOME` exactly `"on"`, one SQLite-backed Durable Object (`Metronome`, `idFromName("metronome")`, binding `METRONOME_DO`, migration v1 `new_sqlite_classes`) writes `live.m3u8` from an alarm re-armed at every boundary + 25 ms. It works under a 15-minute lease that cron renews every minute over RPC (`renew(play | hold | null)`), carrying the guard's verdict, the horizon and the fallback. The object never reads R2 and never decides blocked. It accepts a blocked lease or a hold unconditionally, and an unblocked one only when it is strictly newer by `verdictAt`; it computes expiry on its own clock. Cron's own loop runs only as the fallback, raising `metronome-down`: when renew throws or times out (15 s), when a play lease is not accepted or not written, or when two consecutive renews find the chain stalled for over 30 s. Its own spend bounds:
- at most 10 PUTs and at most 12 alarms per rolling minute;
- a 5 s bound on each PUT;
- a fixed 8-key storage set;
- the chain ticks only while the playlist is live (never blocked, held or expired).

Anything but `"on"` is the rollback: cron's loop exactly as before, and the object deletes its alarm. The cost guard prices three DO meters (requests, duration in GB-s, rows written); while the switch is `"on"`, an empty recent DO window is a failed reading. Tests: `antenna/test/metronome*.test.ts` and `clock-metronome.test.ts`. **`@cloudflare/vitest-plugin` 1.4.0 does not isolate DO storage per test**, so DO tests `reset()` after each test. Real alarms fire on time in tests, so leases put `now` mid-segment. Rollout and rollback: `docs/playout-setup.md` section 9.

## Commands

- antenna (cron-only Cloudflare Worker + static player): `cd antenna && npm
  ci && npm test` (vitest in the Workers runtime via
  `@cloudflare/vitest-plugin`; `npm test` first checks `src/pages.ts` is fresh,
  `npm run pages` regenerates it), `npx wrangler deploy` (run `--dry-run`
  first; `--var` overrides for the verification items; see the runbook),
  `ANTENNA_BUCKET=<bucket> npm run deploy:assets`, `npm run smoke` (Playwright against a local fake station; needs system Chrome and ffmpeg). Secrets go in with
  `wrangler secret put`: `CF_ACCOUNT_ID`, `CF_ZONE_ID`, `CF_ANALYTICS_TOKEN`,
  `CF_WAF_TOKEN`, `ALERT_EMAIL_FROM`,
  `ALERT_EMAIL_TO` (the Worker sends no ntfy; an existing deploy deletes its old
  `NTFY_URL`/`NTFY_TOKEN` secrets); `BILLING_ANNIVERSARY_DAY` is a committed var. The committed
  `send_email` binding `ALERT_EMAIL` is unrestricted, the destination exists
  only as the `ALERT_EMAIL_TO` secret: never put `account_id` or an address in
  `wrangler.jsonc` (a test enforces this). Cloud setup and the phase-1/2
  verification checklists: `docs/playout-setup.md`. The metronome's switch is the var `METRONOME` (`"on"` enables it; rollback `npx wrangler deploy --var METRONOME:off`, then commit `"off"`): `docs/playout-setup.md` section 9.
- The player page (phase 4; spec `docs/superpowers/specs/2026-11-01-player-design.md`, measurements
  `docs/superpowers/2026-11-01-player-probe.md`, rollout `docs/playout-setup.md` section 4 step 3):
  `deploy-assets.mjs` takes only `--dry-run`, `--preview <n>` and `--remove-preview <n>` (any
  other argument exits 2; `--remove-preview` deletes only keys under `assets/preview/<n>/`).
  Layout in `antenna/public/assets/`: `timeline`, `recovery`, `media`, `notes` and `programs` are pure
  (unit-tested under vitest); `app.js` is the entry and owns the one once-a-second loop; `player`, `page`, `panel`
  and `show` touch the DOM. New helpers go in a new module, never as new exports of a deployed one: a
  stale cached module would lack them and fail the import. Assets and `index.html` deploy separately,
  so `page.js` and `panel.js` must also work against the previous `index.html` (no `#lineup`; a
  `#coming-up` that is itself the `.tickets` grid gets flat tickets). Tickets show the show's
  `program` (fallback `LMA RADIO PRESENTS`, as in `show.html`'s `$presents` and the panel). Coming up
  groups its tickets by block occurrence (`block` + `nominal_start`) under the timeline's `blocks`
  headings; Just aired stays flat. The weekly lineup comes from `notes/_lineup.json`, refetched
  every 30 minutes with the timeline; a failed fetch keeps the last one, and the section is hidden
  until one is good. **`antenna/public/player.js`, `nowplaying.js` and `style.css` are frozen:
  byte-identical to the old player and still published (rollback); `assets/player.js` is the live
  one.** `npm run smoke` runs the browser scenarios (`antenna/e2e/`). Notes files carry `sections`
  (transmitter `site.py`); the Cautions section is cut from public pages by matching the literal
  heading `site.CAUTIONS_PREFIX`, which pins llama's briefing heading, so renaming it there breaks
  the cut silently. Launch preview is round 3; rounds 1 and 2 are removed with `--remove-preview`
  from the player worktree (their lists are gitignored and live only there).
  *Play* while a session is on waits for an HTTP answer before rejoining; with none it leaves the
  element alone. `site.py`'s `parse_briefing` drops a bare `(see cautions)` pointer from published
  text (217 longer or unparenthesised mentions remain, by decision). Known iOS limits: after Stop
  or a Bluetooth disconnect the page sleeps within about a minute; in the home-screen app once
  stopped, lock-screen and car Play reach the page but audio loads only when the app is opened
  (WebKit bug 243258); with several home-screen web apps the lock-screen player may open a
  different one.
