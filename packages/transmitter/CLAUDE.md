# transmitter

Commands and design for `transmitter` (`packages/transmitter/`). The repo overview is the root `CLAUDE.md`; off-air, the fallback and the playlist are `antenna/CLAUDE.md`.

## Overview

`transmitter` (dist `llama-transmitter`, CLI `transmitter`) is the playout
side, reading the station root (over NFS on hugo) and never importing llama or
emcee (enforced by `test_no_llama_or_emcee_imports.py`). The stream is a
function of the wall clock: segment N is AAC frames [441N, 441N+441) of one
frame line whose frame 0 sits at the epoch, d = 10.24 s exactly; each show is
encoded once (ffmpeg native `aac`, ADTS) and cut by counting frames, never by
ffmpeg cut points. Segments go to R2 in ascending N and `state/horizon.json`
only advances past confirmed PUTs: before the horizon PUT a batch persists
its candidate `last` as the local `publish.json` `high_water`
(`state.PublishState`), so a crash between the PUT and the save cannot let
`plan_step` re-plan keys R2 may already list; the horizon is never rewritten
below that mark (a batch under it is a "horizon held" — and `fallback render`
likewise defers its horizon rewrite, the next publish batch carrying the
version). `service.HeldTracker` alerts `horizon-held` after
`HELD_ALERT_AFTER = 3` consecutive `publish_all` passes ending held, since
each pass re-sends the same batch and spends PUT budget. `timeline.json` shows carry `program`, `block` and `nominal_start`; the
document carries `blocks` (spans from the full persisted plan); the publisher
writes `notes/_lineup.json` (nominal occurrences, now -24 h to +8 d, rewritten
only on change, `max-age=300`); and the clock is loaded with
`live_clock(save=False)`. Publish, prune and
`fallback render` share a non-waiting flock (`publish.publish_lock`): when it
is held they raise `PublishLocked`: `run` holds it only during its
once-a-minute publish/prune step, so a manual `transmitter publish` while the
service runs normally succeeds (serialized, spending PUTs from the same
budget) and exits 1 with `error: ...` only when it overlaps that step, while
`run`'s own step just logs a warning and retries next tick.

transmitter must stay Python 3.11-compatible (hugo is Debian 12: Python 3.11,
ffmpeg 5.1); the Debian-12 script (Commands) is the gate for that. Design:
`docs/superpowers/specs/2026-10-09-playout-design.md` (phases 1–3 built; the
phase-4 player is built, see `antenna/CLAUDE.md`).
**Scheduler (phase 3; spec `docs/superpowers/specs/2026-10-25-scheduler-design.md`, measurement
`docs/superpowers/2026-10-25-scheduler-measurement/evidence.md`).** Append-only: it extends the
persisted plan from its end, never rewriting a row, and pieces are shows plus one-clip
interstitials (announcements, station IDs) from `[interstitials] dir` (absolute; default
`<station root>/interstitials`). The clock file is strict; an invalid one alerts `clock` and
planning continues on `clock.last-good.toml`, else a daily 00:00 open block with a ±12 h window. Announcement ids are
a hash of the rendered text, so template edits retire voiced clips; missing audio degrades
two-block, one-block, station ID, gap. `aired.jsonl` (append-only rotation history, backfilled
from `plan.jsonl`) refuses appends on an epoch mismatch (alert `history`). A package manifest
with a non-null `awaiting_fix` is not airable. Plan and render run under the plan lock. Plan
rows tolerate scheduler fields (`4fa87a7`/`af46d72`, the oldest safe rollback once the scheduler
has run).

## Commands

- Read-only scheduler views (no lock, never write; `schedule` uses `load_epoch`, so with no
  `epoch.json` it previews from a provisional in-memory epoch and says so):
  `transmitter schedule [--days 7] [--clock FILE] [--library eligible|delivered]` (the persisted
  plan from now, then what the scheduler would append: per block its nominal/actual start and slip,
  shows with `~` on estimated lengths, fill cause, station breaks, MISS, degraded, bent rules and
  missing announcement audio, then a summary; a block entered mid-way, i.e. the phase-1 cutover or
  a fresh run after an outage, may record a MISS on its first show: only with a clock file, and only when the plan's end lands outside that block's window),
  `transmitter library` (eligible shows by profile with count/median/p10/p90, the interstitial
  pool, ineligible packages by first reason incl. `awaiting fix from llama`),
  `transmitter rotation [--days N] [--never]` (airplay by profile from `aired.jsonl` joined to the
  eligible pool: eligible, played, never, plays, repeated, days between airings min/median/mean and
  how many fall under `concert_gap_days`; airings of now-ineligible packages counted apart; the 10
  most played; `--never` lists the never-played slugs; a show's profile is its CURRENT voiced one). `status` reads
  persisted rows, the clock files and the interstitials folder only: clock source, current/next block, misses and
  fill minutes by cause for the last and next 24 h, bends, degraded blocks, missing announcement
  audio; none of it alerts. `packages/transmitter/scripts/probe_estimates.py --config <config.toml> --time-one SLUG` prints an ineligible
  package's reasons (or `not found`). `transmitter announcements [--days 8] [--clock FILE] [--export DIR]` lists
  the announcements the clock needs and writes `ann-<id>.txt` for the missing ones; voice them on
  the Mac with `emcee say` into `<station root>/interstitials` (`id-*.mp3` are station IDs).
  Clock: `<TRANSMITTER_ROOT>/clock.toml` + `clock.last-good.toml`; edit a draft and check it with
  `schedule --clock draft.toml` first. `plan` and `render` share a non-waiting plan lock
  (`PlanLocked`). Runbook: `docs/playout-setup.md` 7.2-7.3.
- Run (transmitter, playout on hugo — phases 1-3): `transmitter run` (service
  loop: plan/render once the lead drops below `low_water_hours`, and keep
  filling until it is back at `lead_hours`; publish + prune every minute;
  `--once` runs one tick), `transmitter plan|render|publish|status`,
  `transmitter fallback render <loop> [--notice <file>]`, `transmitter config
  init`, `transmitter offair on --reason … | off` and `transmitter budget
  [--raise-to <usd>]` (`offair` and `budget --raise-to` write `state/` directly,
  bypassing the publish lock, the guard and the PUT budget); `transmitter status` also shows the cost guard, kill switch,
  off-air flag and active alerts. Production runs the SYSTEM unit
  `packages/transmitter/systemd/transmitter@.service` (`Type=notify`,
  `WatchdogSec=45min`, env file `/etc/transmitter/<user>.env`), so it is
  `sudo systemctl … transmitter@<user>` with no `--user`. hugo's alerts:
  `[alerts]` in config.toml; `SMTP_USERNAME`/`SMTP_PASSWORD`/`NTFY_TOKEN` in the
  env file; dedupe in `~/.transmitter/alerts.json`; the dead-clock check fetches
  `<site_url>/live.m3u8`. **The dead-clock check and the relay run on a daemon
  monitor thread** (`monitor.py`) every 60 s, off the service tick, with its own
  get-only R2 reader (never writes, never touches `guard-cache.json`, never pings
  the watchdog); `monitor-stalled` (level, sent at once) fires from the main tick
  when its last pass is over 5 min old; `run --once` checks once on the main
  thread and does not relay; the plan step pings the watchdog after each show
  analysis (`Station.frames_of`). **Alert gate:** every-minute alert keys
  (antenna `GATED_KEYS`, transmitter `GATED_CODES`) send only after `GATE` = 3
  consecutive failing observations (antenna: minutes; transmitter: ticks, or
  monitor passes for `dead-clock-check`); spend/off-air keys and one-shot keys are
  never gated, and two antenna raise sites (the metronome stall branch of
  `metronome-down`, `guard-unknown` after an unblock) send at once. **Relay:**
  antenna appends each invocation's sent alerts to `state/alert-relay.json` (a
  ring of 50, stream + seq) after the email; hugo's monitor thread relays them to
  its ntfy (cursor `~/.transmitter/alert-relay-cursor.json`, `RELAY_MAX_AGE_S` 1 h);
  the Worker sends no ntfy. State in `~/.transmitter/` (`TRANSMITTER_ROOT`); R2 keys from
  `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`. Tests:
  `packages/transmitter/tests_transmitter/` (a package, NOT `tests/`: llama's
  test modules are top-level and emcee's are the `tests` package, so the name
  would collide); ffmpeg-dependent tests skip without ffmpeg;
  `packages/transmitter/scripts/test-in-debian12.sh` runs them on hugo's
  Python 3.11 + ffmpeg 5.1 (needs docker). Container spike:
  `python -m transmitter.spike build|serve <dir>`.
