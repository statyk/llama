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
`live_clock(save=False)`. A show's notes JSON gains `dropped` (`{title, set, after_track}`, valid
entries of the manifest's optional `dropped_tracks`, read raw; absent when none) and `site._setlist_html`
strikes those titles through in place without counting them (the now-playing view is unchanged). Publish, prune and
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
  off-air flag and active alerts, plus the `concert` switch line (`announce.toml`, read with `alert=False`) and the
  `pieces` line (dormant / no list yet / needed-present-failed-missing, read from `pieces-needed.json` and the pieces
  folder; never writes, never raises). Production runs the SYSTEM unit
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
- `transmitter/concert.py` (concert announcements, phase A; pure, no IO): the finite inventory of
  piece texts emcee will voice. `piece_id(text)` is `sha256(text)[:12]`; `needed_pieces(clock,
  artists, id_text, from_us, days=8)` returns `NeededPiece(id, text, kind)` deduped by id and sorted
  by id (the ID, 4 block pieces per titled block, a `Then, at <time> Eastern, <title>` per titled
  occurrence, 3 pieces per cleaned artist, 78 time phrases). Times are always spoken in
  `America/New_York` whatever the clock's timezone (`time_phrase` buckets, `then_time`); artists go
  through `clean` (`" ".join(split())`, non-string or empty -> none).
- `transmitter/announce_config.py` (`<TRANSMITTER_ROOT>/announce.toml`, `Workspace.announce_path`): strict
  (`extra="forbid"`, no NaN/inf), off by default. `load_settings(ws, alert=)` never raises and returns
  `LoadedSettings(settings, source "file"|"missing"|"invalid", problem)`; an invalid file (bad TOML, non-UTF-8,
  unreadable, unknown key, out-of-range value, relative `bed`, multi-line `id_text`, `enabled = true` without
  `bed`) yields default (off) settings and, with `alert=True`, one `announce-config` event alert naming the
  cause. The `announce-*` codes are ungated, non-level. `config.toml` and the clock gain no keys.
- `transmitter/piecelist.py` (the needed-piece list, phase A): `pipeline.plan_step` calls `Station.scan_all` once,
  then `write_piece_list` (never raises: any exception is logged and alerts `announce-pieces`), then
  `scan_pieces(shows=)`, all BEFORE its "already covered" early return. It saves `<root>/pieces-needed.json`
  (`Workspace.pieces_needed_path`, rewritten only when the pieces change; artists = eligible shows plus
  `Ineligible.artist`) whether or not announcements are switched on, and writes each missing
  `<interstitials>/pieces/piece-<id>.txt` (temp `.piece-<id>.txt.<pid>-<tok>.tmp` + fsync + rename; at most
  `WRITES_PER_STEP` 250 per step; own temps older than 1 h removed). transmitter never creates `pieces/`: a missing
  folder means no texts and no alert. Only `plan_step` writes; `schedule`/`status`/`library` never do. Present =
  `piece-<12 hex>.mp3` regular, non-empty, quiet; dot files and other names are ignored.
- `transmitter/assemble.py` (concert breaks, phase B): `Assembler(pieces=, out_dir=, settings=).build(content)` joins `piece-<id>.mp3` (decoded 44.1 kHz stereo) with `settings.gaps` (after the ID piece, chosen by `content.phrases[0] == "id"`, `after_id`; else by the piece's last character `,` `after_comma` / `.` `after_period` / `within`), mixes the bed under (RMS `bed_under_db` below the voice's, lead-in/tail, 0.1 s fade in, tail fade out; bed looped) and writes a 16-bit 44.1 kHz stereo WAV `concert-<16 hex>.wav` atomically into `Workspace.concert_dir` (`render/concert`), returning a one-clip `Show` (`Entry(name, "clip", "Announcement")`, meta `role=concert`). The slug hashes the pieces' file-set keys, gaps, bed key, `bed_under_db` and `ASSEMBLY_VERSION`; an existing clip is reused completely untouched (no `os.utime`: its own file-set key hashes its mtime and plan rows carry it). A missing/undecodable piece of any kind is `PieceUndecodable(piece_id)`; any bed problem (incl. a NUL path) is `AssemblyError`. `scan_clips(out_dir)` (no quiet period); `gc_clips(out_dir, cache_dir, keep_slugs, now_s=)` removes unreferenced clips and dot-temps older than 1 h with the clip's `cache/<key>.json`. `scripts/time_assembly.py` times assembly plus analysis on a folder of pieces.
- `transmitter/promises.py` (concert promises, phase B; pure, never raises, never loops): `entries_of(row)` gives a
  `role="concert"` row's `named_shows` as `(slug, occurrence key)` pairs (all in the row's `block`/`nominal_start`,
  except Z in `names[0]` when `names` is set), or None when malformed (non-str/empty slug, 0 or >3 slugs, >1 names
  pair, names with one slug, no block/nominal). `remaining(rows, pool_slugs=, clock=, run_start=)` is the unplaced
  entries of the LIVE promises (show rows after the break a prefix of its entries, interstitials ignored; no
  `run_start` row after it; unplaced slugs in the pool; every named occurrence still yielded by `clock.occurrences`),
  combined oldest first by `merge_remainders(older, newer)` (a prefix agrees and the longer is kept; any differing
  position: the newer wins); `run_start=True` voids all. `first_mismatch(rows, row)` (rows only) is True for the one
  show row that first breaks a promise (a wrong slug, a show row with `run_start`, or the first show row after a
  non-show `run_start` row). Only the plan tail is read (back to a 4th show row; for `remaining` also to the latest
  `run_start`); any exception is logged and degrades to "no promise".
- Scheduler concert breaks (phase B): `SchedulerInput.concert: concert.ConcertInput | None = None` (None, the default:
  output byte-identical to before, pinned by `tests_transmitter/fixtures/concert_off_golden.jsonl`). When set and the
  boundary's start is not in `no_assembly_at`, `boundary()` first tries a `role="concert"` break: X is judged with the
  concert clip's own length (`first_break.frames` at `start_frame`, else `typical_frames`), so it may open the next
  occurrence where an ID would not (or the reverse); the row's `block`/`nominal_start` are X's occurrence, and X's
  occurrence past the horizon stops the projection. Untitled X (`concert.title_of` = `clean(title)` is None, the same
  helper the inventory uses), degraded X or a missing Next/continues block piece: today's logic, state untouched.
  Phrases kept only when all their pieces are present: ID; block piece; `with X,` (Followed) or `with X.` (absent:
  the clip ends on the `.`-variant block piece, else the plain one, naming only X); Followed (Y = next show of X's run,
  cleaned artist differs; same artist: Y named but unspoken); Then (Z = first show of the next occurrence when the
  last named show ends X's run, a different, titled, undegraded block, landing in its window; drawn with the named
  shows in the history and `used`, never a named show). `PlannedPiece.concert: BreakContent` (`same_shape` ignores
  a Y-bucket-only difference); `to_row` writes `named_shows`, `piece_ids`, and `names` = Z's occurrence only with
  Then. Pass 1 uses the `PLACEHOLDER_SLUG = "concert-pending"` piece (`exact=False`). With concert set the block
  search's boundary estimate is `2 * gap + typical_frames`. The scheduler does not catch exceptions here (the
  caller's guard does).
  **Live promises** (concert on or off): `_Projection.promise` starts as `promises.remaining(rows, ...)` (none with
  `SchedulerInput.promises=False`, for the caller's guard), grows by `promises.merge_remainders(promise,
  entries)` at each projected break (never overwritten, so preview and a live continuation agree), and its head
  is placed at the next show slot (current occurrence, or the next one, entered), even outside its window (`miss`).
  When the run's own pick is another show, the row's `fill` is derived from own-pool membership (`None`, also in a
  degraded block; else the run's cause or `"structural"`), `bends=()`, and the run is re-planned. Under a promise the boundary kind,
  `next`/`later` judgments and a new break's X/Y/Z use the promised shows (`_PromisedRun`); a new break names the
  same shows or fewer. A head whose occurrence is neither the current one nor the next one (the next only once the current one has a
  show placed, so an inserted block is void alike in preview and live) voids the promise (never raises).
- `pipeline.extend` concert breaks (phase B): `concert_input(st, now_us, read_only=, no_assembly_at=)` is None unless
  `announce.toml` is on and the pieces folder exists (`present` = voiced pieces past the quiet period, `typical_frames` =
  18 s). Per concert row: pass 1's content is assembled (`Station.assemble`, else one call-scoped `assemble.Assembler`)
  and measured, every named show is measured (`frames_of`, watchdog fed), and pass 2 re-runs with the clip as
  `first_break`; same shape -> the row is appended with pass 1's wording, else that start goes into `no_assembly_at`
  (last rung). `PieceUndecodable(id)`: alert `announce-assembly`; an id the break offered leaves `present` for the
  call (re-proposed), any other id sends that start to the last rung; any other assembly failure or an unmeasurable named show (skipped as today): that start at the last rung. The guard: a
  non-`PlanError` exception from a projection with concert input or live promises (or from extend's own
  `promises.remaining`) alerts `announce-assembly`/`announce-promise` and the call goes on with `concert=None`,
  `promises=False`. A show row that `promises.first_mismatch` flags gets `announcement_broken`, logs
  `promise-broken: <slug> at <block> <nominal>` and alerts `announce-promise`. `scan_pieces` adds
  `Station.concert_pieces()` (the workspace clips, lengths from the length cache; never raises).
- `schedule`/`status` and concert breaks: `schedule_report` calls `concert_input(st, t, read_only=True)` (no alert) and projects with the pass-1 placeholder, never an assembler (it runs outside `plan_lock`, which gc protection relies on); a projected break prints its `BreakContent` texts, a persisted one its `piece_ids` through `report.block_views(texts_of=)` (from `piecelist.load_needed`; unknown id `<id>`, non-str element `<?>`). `status` adds `breaks     next 24 h: A assembled, F fallback` (interstitial rows, role `concert` vs other; `0 assembled` with the feature off) and `promises   B broken announcement(s) (last 24 h and planned)`. Neither view writes texts or clips.
- `pipeline.render_step` concert rows (phase B): a `role="concert"` row renders like any interstitial, its piece from
  the scan (which includes `Workspace.concert_dir`). Any skip-path reason on it (missing, key changed, frames changed,
  render failed) adds its start to the call's `no_assembly`, passed as `extend(no_assembly_at=)` to every re-plan of
  the call (only once non-empty, so feature-off calls are unchanged), so that boundary is planned at the last rung;
  after each re-plan the clips it assembled join the call's piece map (`concert_pieces()`, existing keys kept), so new
  breaks render with no further re-plan. On-air lost encode: `LayoutError` as for any piece. At the end
  `_gc_assembled` calls `assemble.gc_clips` with keep = slugs of concert rows (or rows with `dir` the clip folder)
  ending after `(listed_bound + 1) * 441` (all of them when nothing is published); it runs after the plan is written
  under the plan lock, so a reused old clip of an unappended candidate may go (the next build re-makes it); any
  exception is logged, never raised.
