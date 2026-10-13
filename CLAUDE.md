# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Implemented. The full pipeline (interpret through package) works offline
against the `fake` LLM backend and real archive.org fixtures; see
`docs/superpowers/plans/2026-07-14-llama.md` for the task-by-task
implementation plan this was built from. The approved design spec is
`docs/superpowers/specs/2026-07-14-llama-design.md`.
The repo also holds `transmitter` (playout, phases 1-2; not a released/signed
binary — `.github/workflows/release.yml` has no transmitter) and `antenna/`
(a Cloudflare Worker + static player).

## Commands

- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
- Test: `pytest -q` (offline, deterministic). Single test: `pytest packages/llama/tests/test_setlist.py::test_parses_sets_segues_and_confidence -q`
  **In a git worktree, give the worktree its own `.venv` and run `./.venv/bin/pytest`.**
  The repo-root `.venv` installs llama editable against the *main* checkout, so a
  bare `pytest` from a worktree collects the worktree's tests but imports the main
  checkout's source — it silently tests the wrong code and still passes.
  **And never run a `.venv/bin/*` console script from a COPY of the tree.** `pytest`, `pip`, `llama`, `emcee` and `transmitter` are all shebanged with an absolute path to the original venv's interpreter, so from a copy they act on the original: `.venv/bin/pytest` tests the worktree instead of the copy (so a mutation you applied does nothing and the suite stays green), and `.venv/bin/pip install -e` reinstalls into the worktree's venv and repoints its `_editable_impl_*.pth` at your copy — poisoning every other process using that worktree, invisibly to `git status`. Use `python -m <tool>`, or shadow with `PYTHONPATH`. To check: `./.venv/bin/python -c "import llama; print(llama.__file__)"` must resolve inside the tree you meant to test.
- Live tests (real archive.org, no LLM): `pytest -m live -q`
- Refresh a fixture: `python scripts/capture_fixture.py <identifier>`
- Stitch a playlist into one mp3: `python3 scripts/stitch_m3u.py <playlist.m3u>`
  (standalone, stdlib-only, needs ffmpeg/ffprobe; stream-copies uniform mp3
  input and re-encodes otherwise, writing ID3 chapters per entry and pulling
  tags from a sibling `manifest.json` when there is one). `scripts` is in
  pytest `testpaths`, so its tests run under plain `pytest -q`.
  `python scripts/backfill_voiced_by.py [--station-root P] [--apply]` is a
  one-off (imports emcee): it fills `dj_audio.presenter` on packages voiced
  before emcee recorded it, by whole-word matching each presenter's `name`
  in the script text — exactly one match writes, zero or several leave `?`.
  Dry run unless `--apply`.
  `python scripts/purge_delivered_audio.py [--config P] [--dest P] [--apply]`
  is a one-off (imports llama): it applies deliver's audio purge, same
  verification, to shows delivered before deliver did it. Dry run unless
  `--apply`.
- Run (llama, acquisition): `llama get "..."`, `llama get --profile <name>`,
  `llama get` takes `--wait/--no-wait`, `--max-wait <dur>` and `--no-pacing`
  (also on `run approve`/`run resume`): when the claude_cli backend refuses
  because a usage window is exhausted, the run pauses at the show boundary
  rather than failing every remaining show — sleeping until the reset the
  refusal names, or checkpointing the session as `paused` when the wait
  exceeds `--max-wait` (default 6h). Resuming costs nothing for shows already
  packaged: stage-level `should_run` skips them.
  `llama artists "..."`, `llama status` (global triage view, `--by-run` for
  session rollups), `llama show <name>` (read-only), `llama pipeline`
  (static stage/state teaching command), `llama pacing` (read-only:
  the usage meters, the learned per-show cost, how many shows fit
  before the reset, and the verdict — `would proceed`, or
  `would pause: <reason>`), `llama triage` (interactive
  held-show walkthrough -- `[t] suggest titles`, offered only on a hold
  flagged "unresolved track titles", proposes a full set of titles from
  the setlist correspondence and writes them all on confirmation;
  `[i]nclude dropped`, offered only when the show has `excluded_files`,
  re-admits by x-handle or filename and shares `fix --include`'s
  operator-excluded routing via `_split_include_targets`), `llama
  fix <name> <edit-flags>` (overrides/hold editor, auto-redoes;
  `--suggest-titles` is the same title-proposal resolution, one
  invocation, one confirmation, refuses to combine with
  `--exclude`/`--unexclude`/`--include`), `llama redo <name> --from <stage>`,
  `llama deliver <name>` (refuses to overwrite an emcee-voiced destination
  unless `--replace-voiced`, which replaces the destination wholesale and
  discards its DJ script and audio; a batch confirmation marks or counts the
  voiced destinations; after a successful copy it **purges the library's
  `package/audio/*`** — only once `catalog.purge_package_audio` verifies the
  station copy holds every manifest track at the same size and as a different
  file (a hardlink or a `delivery_path` inside the library deletes nothing);
  a skipped or partial purge only warns. A purged show re-delivers via
  `llama redo <name> --from package`, which re-downloads what is missing —
  the deliver gate's "audio files missing" refusal already points there; so
  does any `fix`/`triage` edit of a delivered show, since its auto-redo runs
  through `package` — a full re-download where it used to be an in-place
  retag. The verification also requires the station manifest's `tracks` to
  equal the library's (same-size files are not the same package: a retag
  keeps sizes) and flushes each station file to disk (`F_FULLFSYNC`) before
  the first delete. A voiced-destination refusal is checked BEFORE the gate,
  so a purged show is not sent to re-download only to be refused anyway),
  `llama rm <name>`, `llama suppress`/
  `llama unsuppress <performance-id>`, `llama run list/approve/resume/rm`
  (session namespace; a run that lost shows to a failure ends
  `incomplete`, not `complete`, so it stays on `run list`'s attention list
  — with the per-show reasons recorded in `session.json` — until a
  `run resume` finishes cleanly). Shows/sessions are addressed by name or unique
  substring; paths still work. `llama config init` seeds a commented config
  of the baked-in defaults (config values replace defaults; nothing
  merges). **An unknown key in `config.toml` is now an ERROR, not a silent
  drop** (`extra="forbid"`, 2026-09-07): a typo'd knob used to parse to its
  default and leave the operator's edit with no effect and no message. It is
  set on a shared strict base because pydantic does NOT propagate
  `model_config` to nested models — on `Config` alone every section below it
  stays permissive, which is most of the value. Mapping KEYS stay free-form
  (task names under `[llm.*]`, backend names under `[llm.tiers.*]`); only
  their values are strict. `herder`'s `TaskConfig` is deliberately left
  permissive (cross-package blast radius), and so are the PERSISTED state
  artifacts — `Criteria`/`criteria.json`, `session.json`, `show.json`, the
  manifest — where permissiveness is load-bearing forward compatibility:
  strictness there would break `llama run resume` on run dirs written by a
  different version, which is the thing T6b exists to protect. emcee has the
  same treatment on its own six models via its own base (it must never import
  llama). No `voice`/`presenter` commands — that's emcee's job now.
- Run (emcee, station-side, post-`llama deliver`): `emcee run` (scan
  `[station] root` and voice every not-yet-broadcast-ready package;
  `--profile <name>` (repeatable) limits it to those llama
  profiles' packages, `--assigned` to packages whose profile has its OWN
  `[assign.profiles.<name>]` entry (not those falling to `[assign] default`
  or the house voice), `--dry-run` lists what
  would be voiced and by whom — an explicit assignment prints `<id>`, the
  default `<id> (default)`, none `house`; a pinned presenter's row also shows
  `[<backend> <model>]`, an unloadable presenter file
  `[invalid presenters/<id>.toml]`, a failed TTS resolution
  `[unresolved: …]`),
  `emcee voice <package>` (script + voice + assemble one package —
  a path, or a name/unique substring under `[station] root`, overridable
  with `--station-root`, exact name beating substring hits;
  `--fresh <clip-stem>` deletes just that cached clip, but since emcee
  re-scripts on every call, a real LLM's regenerated text usually
  invalidates every clip's cache too — in practice `--fresh` normally
  re-renders every clip, not just the named one; `--force` re-synthesizes
  all of them unconditionally), `emcee status` (default: a summary by profile; `--list`/`-l`
  gives the per-package table of ready/pending/unsupported/`error`, `--profile`
  and `--state` filter and switch to that table on their own, `--json` is
  always per-show; a `--profile` no package carries prints a `note:` rather
  than looking like an empty queue; the voicing presenter is the
  recorded `dj_audio.presenter` — null is the house narrator, an absent key
  means voiced before it was recorded and shows `?`), `emcee say <text-file>` (ad-hoc
  narration: text file in, MP3 out, no package/script/LLM — voice via
  `--clone`/`--voice`/`--presenter` else the house `[tts] voice`, bed via
  `--bed`/`--bed-gain`/`--no-bed` else the package rules, chunking ON by
  default like `[tts] chunk`; `--no-chunk` without a bed is the one render
  that is not loudness-normalized), `emcee presenter add/edit/list/show/remove`
  (`presenters/<id>.toml`; `edit` changes any field with set/`--clear-*`
  flags, `--transcribe` drafts `voice_clone_text` on the mlx-audio server's
  STT model and writes it only on confirmation; `voice_clone` is stored as an
  absolute path), `emcee config init`.
- Run (transmitter, playout on hugo — phases 1-2): `transmitter run` (service
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
  `<site_url>/live.m3u8`. State in `~/.transmitter/` (`TRANSMITTER_ROOT`); R2 keys from
  `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`. Tests:
  `packages/transmitter/tests_transmitter/` (a package, NOT `tests/`: llama's
  test modules are top-level and emcee's are the `tests` package, so the name
  would collide); ffmpeg-dependent tests skip without ffmpeg;
  `packages/transmitter/scripts/test-in-debian12.sh` runs them on hugo's
  Python 3.11 + ffmpeg 5.1 (needs docker). Container spike:
  `python -m transmitter.spike build|serve <dir>`.
- antenna (cron-only Cloudflare Worker + static player): `cd antenna && npm
  ci && npm test` (vitest in the Workers runtime via
  `@cloudflare/vitest-plugin`; `npm test` first checks `src/pages.ts` is fresh,
  `npm run pages` regenerates it), `npx wrangler deploy` (run `--dry-run`
  first; `--var` overrides for the verification items; see the runbook),
  `ANTENNA_BUCKET=<bucket> npm run deploy:assets`. Secrets go in with
  `wrangler secret put`: `CF_ACCOUNT_ID`, `CF_ZONE_ID`, `CF_ANALYTICS_TOKEN`,
  `CF_WAF_TOKEN`, `NTFY_URL`, `NTFY_TOKEN` (optional), `ALERT_EMAIL_FROM`,
  `ALERT_EMAIL_TO`; `BILLING_ANNIVERSARY_DAY` is a committed var. The committed
  `send_email` binding `ALERT_EMAIL` is unrestricted, the destination exists
  only as the `ALERT_EMAIL_TO` secret: never put `account_id` or an address in
  `wrangler.jsonc` (a test enforces this). Cloud setup and the phase-1/2
  verification checklists: `docs/playout-setup.md`.

## What this is

Two Python CLIs — `llama` and `emcee` — that together carry an archive.org
Live Music Archive (LMA) recording all the way to air (the playout side,
`transmitter` + `antenna/`, is described at the end of this section). They ship as separate
signed binaries and know nothing of each other's internals; the only
contract between them is the delivered package on disk. Usage tilts heavily
toward Grateful Dead shows (two sets + encore).

`llama` finds concerts on the LMA, winnows them for quality, researches the
specific performance online, and emits a self-contained "show package"
(verified audio, m3u, manifest v3 with track titles/set breaks, vetted
research + reviews digest, and a required neutral vetted `briefing` for
scriptwriters) for an automated in-house radio station. `brief` is llama's
sole text stage — llama does not write DJ scripts, has no presenters, no
TTS, and no `[tts]`/presenter config. Its `deliver` gate is just: packaged,
not held for review, and every manifest track's audio file present on disk
— plus it refuses an emcee-voiced destination unless `--replace-voiced`.
After delivering it drops the library's own copy of the audio (the
station copy is the one that airs; archive.org is the re-fetch source), so
a delivered show in `~/.llama/shows/` normally has an empty `package/audio/`.

`emcee` (dist name `llama-emcee`, bare CLI `emcee`) is station-side and runs
**after** `llama deliver` — it operates on the delivered-packages folder
(`[station] root`), never on llama's own library. "Not broadcast-ready" IS
the work predicate: `emcee run` scans the station root and voices every
package that isn't yet broadcast-ready, no separate state file needed.
The one exception to the package-shaped rule is `emcee say`, which voices
an arbitrary text file to an MP3 — no package, no manifest, no LLM call —
reusing the same voice/bed resolution and `audio.render_speech_mp3`
renderer as the DJ clips.
emcee owns presenters (`presenters/<id>.toml`: name/sex/character +
`voice` XOR `voice_clone`), the script LLM task and its own factual guard,
`speech_text` normalization, TTS (hosted Mistral Voxtral by default,
ElevenLabs as an opt-in alternative, and a free local `mlx_audio` backend
over mlx-audio's server; a presenter may pin any of the three with `tts`, and
clones are voiced on voxtral or mlx_audio, never elevenlabs), instrumental
beds, the per-segment render cache, and
assembling `dj-audio/`/`broadcast.m3u`. Its `[assign]` config maps a llama
profile name to a presenter + on-air title, keyed off
`manifest["source"]["profile"]`, which llama stamps on every package it
delivers. emcee writes `dj-notes.md`, `dj-audio/`, and `broadcast.m3u`
straight into the package directory llama delivered, and rewrites the
manifest's `dj_notes`/`dj_audio` blocks in place (llama writes both as
`null` — they are emcee-written passthrough blocks in the shared manifest
model). emcee never imports llama.

**Single-writer station, no lock.** Unlike llama (parallel-safe via flock,
below), emcee assumes exactly one `emcee run` at a time against a given
station root — it takes no lock. Overlapping runs can't corrupt a package
(unique-temp + atomic rename everywhere, in both tools), but they *will*
double LLM/TTS spend by voicing the same pending package twice
concurrently. Don't fan out `emcee run` the way llama's workspace tolerates
concurrent `llama get`s.

LLM model choice is tiered (low/medium/high; haiku/sonnet/opus on claude_cli,
gemini-flash/sonnet-5/opus-5 on openrouter): medium by default, high for
llama's interpret/deep_research/brief and emcee's scriptwrite, low for
vet_research,
overridable per task via `[llm.<task>]` `tier`/`model` or per backend via
`[llm.tiers.<backend>]`; a failed validation's final retry escalates one
tier (pins never escalate).

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
each pass re-sends the same batch and spends PUT budget. Publish, prune and
`fallback render` share a non-waiting flock (`publish.publish_lock`): when it
is held they raise `PublishLocked`: `run` holds it only during its
once-a-minute publish/prune step, so a manual `transmitter publish` while the
service runs normally succeeds (serialized, spending PUTs from the same
budget) and exits 1 with `error: ...` only when it overlaps that step, while
`run`'s own step just logs a warning and retries next tick. `antenna/` is a
cron-only Worker (no routes, `workers_dev = false`) that rewrites `live.m3u8`
at every grid boundary, plus the static player; listeners only ever fetch
cache-served R2 objects. Its clock bounds its own spend
(`antenna/src/clock.ts`): `MAX_PUTS = 10` per invocation, a horizon whose `d`
is not 10.24 is refused (`horizon-refused`, nothing written), and
`LOOP_SECONDS` is clamped to 75 (`loop-clamped`). Off-air (from
`state/offair.json`, or a horizon more than 24 h stale) plays the notice from
the fallback, so transmitter publishes NOTHING — no segment, no horizon — until
`fallback render` has recorded a fallback version in the workspace: every
publish pass alerts `no fallback rendered` instead (the gate sits before the
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
transmitter must stay Python 3.11-compatible (hugo is Debian 12: Python 3.11,
ffmpeg 5.1); the Debian-12 script above is the gate for that. Design:
`docs/superpowers/specs/2026-10-09-playout-design.md` (phases 1–2 built; the
scheduler and the full player are phases 3–4).

## Architecture (from the spec — the short version)

- **Staged pipeline over an on-disk workspace** (default `~/.llama/`):
  interpret → search (wide net) → winnow (quality gate + optional human gate)
  → select-recording → gather → research → vet (grounding check) →
  brief (always on) → package. Every stage reads/writes plain files;
  run-level artifacts live in a per-run directory, show-level artifacts in a
  canonical `shows/<slug>/` library (one dir per performance, reused across
  runs); stages write outputs only on success and are individually
  re-runnable (`llama redo <show> --from <stage>`). `brief` is llama's sole
  text stage — it emits a neutral vetted briefing (`briefing.md`/
  `briefing.json`) for scriptwriters — no flag, no config gate, factually
  guarded (retry-once-then-hold), and stamped with the `narration`
  directive from `overrides.json`. The show-package contract is **manifest
  v3**: a required `briefing` block (`file`, `json`, `narration`, `vetted`)
  alongside the existing fields; `package` copies both briefing files into
  `package/` and hard-fails if a show has no briefing artifacts. The
  manifest model also carries `dj_notes`/`dj_audio` fields, which llama
  always writes as `null` — they are **emcee-written passthrough blocks**,
  filled in station-side after delivery; llama itself never populates them.
  `stages/synthesize.py` (the in-house DJ script/voice path) was cut
  entirely in this split — scriptwriting and voicing moved wholesale to
  `emcee` (umbrella spec:
  `docs/superpowers/specs/2026-07-28-split-architecture-design.md`).
- **Parallel-safe workspace:** multiple `llama` processes may run concurrently
  against one local `~/.llama/`. Coordination is advisory `fcntl.flock`
  (`packages/llama/src/llama/locks.py`) at two scopes — a short **ledger lock**
  (`ledger.jsonl.lock`) around every ledger mutation, and a long **per-show
  lock** (`shows/<slug>/.lock`) around `process_show` and every single-show
  mutator (`redo`/`fix`/`deliver`/`rm`). Locks auto-release on
  process death (no stale-lock reaping). Same-performance runs serialize
  (first builds, others wait and reuse); independent shows run fully in
  parallel. Readers (`show`/`status`/winnow dedup) never lock. All atomic
  writes use unique temp names. POSIX-only; non-POSIX degrades to no-op
  locking. **`emcee` does not share this locking scheme** — see emcee's
  bullet below.
- **`overrides.json`:** the one durable, app-edited per-show input —
  excluded source-track filenames, `narration` (`full`/`vague`), and
  metadata corrections (`venue`, `city`, `date`, `titles`: track#→forced
  title, `set_breaks`: track numbers a break falls after, numbered-sets-only,
  `encore_after`: track number past which every remaining track relabels
  "encore") — that survive every `redo`. `gather` drops excluded files (reason
  `operator-excluded`), forces `venue`/`city`/`date`/track titles/set
  breaks when their fields are set (bypassing structure alignment entirely
  for `set_breaks`/`encore_after`; `encore_after` must exceed every
  `set_breaks` entry), and `brief` reads `narration=vague` to write a
  briefing that names no songs and asserts no set structure (the LLM's own
  opinion of `narration` is never trusted — stamped from `overrides.json`
  after generation); `show.json` stays purely derived and is never itself
  hand-edited. `llama show` is strictly read-only; `llama fix <show>
  <edit-flags>` (flag-driven, single show, auto-runs the correct redo) and
  `llama triage` (interactive walkthrough over held shows, default
  `--held`) are the only ways to edit it — `--exclude`/`--unexclude`
  (filename or track number, `--tracks` on `show` lists them) and
  `--set-venue`/`--set-city`/`--set-date`/`--set-title N=…`/`--set-breaks`/
  `--set-encore` (plus their `--clear-*` counterparts) all redo from
  `gather`, and a hold **self-clears** whenever the re-gather no longer
  reproduces the flag that caused it (gather recomputes
  `needs_review`/`review_flags` from scratch every run). `--exclude`/
  `--unexclude` are joined by **`--include xN|FILE`** (`overrides.include`),
  which re-admits a file the junk filter dropped and redoes from `gather`
  like the other two — applied inside
  `filter_files` after the junk arms and after duplicate-listing dedupe but
  **before** play-order derivation, so the floor cannot move and order is
  derived over the final set (a re-admitted file with no track tag reverts
  the recording to filename order). A file in both lists is excluded; the
  CLI keeps the lists mutually exclusive so that never happens through it.
  `--include` on an `operator-excluded` row un-excludes instead. **Do not
  loosen the junk constants instead** — this override is why they stay put.
  A hold flagged "unresolved track titles" additionally gets **`--suggest-titles`**
  (`fix`) / **`[t] suggest titles`** (`triage`, same helper, offered only
  under that flag): both build a canonical setlist via
  `build_canonical(..., provider=None)` — deliberately **not** the same
  call `gather` itself makes: `run_gather` passes gather's real provider
  (`gather.py:616-618`), and `provider=None` is precisely what stops this
  CLI-side proposal path from ever firing the `extract_setlist` LLM
  fallback. The difference is benign, not weaker — an unrankable setlist
  yields an infeasible proposal rather than a silently worse one — and
  then render a per-track proposal table, for tracks the DP can propose
  for, via the correspondence DP (`llama/correspondence.py` —
  **proposal-only, never auto-adopted**; unanchored monotone
  correspondence measured 45-52% wrong, so a human confirmation is the
  only thing standing between a proposed title and adoption). **The DP is
  gated by an accountability guard that declines rather than renders**
  (`correspondence._unaccounted` / `_contradicts_forced_gaps`): each
  maximal run of still-`unresolved` tracks — the only adoptable ones —
  must be **count-forced between anchors**, exactly as `setlist-gap`
  requires, and the DP's own solution must not contradict a forced gap.
  Both checks are exact structural counts, never a margin/score/coverage
  threshold; they reuse `structure.anchor_spans`/`gap_span`/
  `unresolved_runs`, extracted from `adopt_gap_titles` so the silent rung
  and the confirmed one cannot drift apart on what an anchor is. What
  they do NOT share is the `_hygienic` veto — an operator reads this
  table — which is the command's whole residual value over `setlist-gap`.
  **Consequence, deliberate and load-bearing: a WHOLLY UNTAGGED tape is
  no longer proposable at all**, since nothing anchors the setlist to it.
  That is the population this feature was aimed at, and the M3 gate
  measured it 13-of-22 wrong via a uniform off-by-one with nothing in the
  table saying so. **A whole-tape count comparison cannot substitute for
  the per-run one**: `yondermountainstringband-2005-12-31` (declines) and
  `trampledbyturtles-2007-07-20` (renders, correctly) are both 24
  song-like tracks against 23 canonical items — measured, don't retry it.
  On
  confirmation, the proposed titles for still-`unresolved` tracks are
  written into `overrides.titles` at once (a filler row gets no proposal
  and stays `(unresolved - hand-edit)`; a track that already carries a
  title is never overwritten), then redo from `gather` like every other
  metadata edit. `--suggest-titles` refuses to combine with
  `--exclude`/`--unexclude`/`--include` in the same `fix` invocation (any
  of the three renumbers tracks before the proposal's numbering would
  apply), and an
  explicit `--set-title N="..."` on the same invocation always wins over
  the proposal for that track. On a multi-set show,
  `--set-encore` must be combined with `--set-breaks` to keep set labelling
  correct — the override path skips alignment entirely rather than layering
  on it, so `--set-encore` alone flattens every set into `"1"`. Any
  structure override (`--set-breaks` and/or `--set-encore`) takes that same
  path and loses every segue regardless — combining the flags fixes set
  labelling but does not bring segues back. The other
  two gate-2 resolutions: **accept-vague** (`fix
  --narration vague` → redo from `brief`, regenerating the briefing and
  package too, clears the hold immediately), and **overrule** (`fix
  --overrule` → redo from `package`, clears the hold without touching
  overrides).
- **App-managed instead of hand-edited:** `llama profile artists <name>
  [--set "A, B, C"]` views or re-pins a profile's pinned artist roster.
  Between this, `llama fix`/`llama triage`, and `overrides.json`,
  `config.toml` remains the only file this design expects a human to
  hand-edit — for llama. (emcee has its own equivalent: `emcee presenter
  add/list/show/remove` manages `presenters/<id>.toml`, and its
  `[assign]` config table is the one thing a human hand-edits there.)
- **Two modes:** one-off queries, and standing criteria profiles for recurring
  segments, deduped against the on-disk show library ∪ a `ledger.jsonl`
  history keyed by performance identity (artist + date + venue), not
  archive.org item id — winnow skips anything already in the library or
  logged played/rejected. A date carrying two performances (early/late show)
  splits at grouping time into one show per jerrybase event, keyed
  `collection/date/eN` (e1 = first show); single-event dates and dates with
  no jerrybase data are unchanged. There is deliberately NO ledger migration
  and NO legacy-id compatibility for pre-split `collection/date` rows — purge
  and re-run. Run names auto-unique: a same-day collision gets a `-2`/`-3`
  suffix instead of silently resuming the earlier run.
- **LLM layer:** lives in the shared `herder` package (`packages/herder/`),
  used by both llama and emcee — task registries and prompts stay per-app.
  Provider abstraction with two capabilities — `complete`
  (schema-validated, no tools) and `research` (needs web search). Dev backend
  shells out to headless `claude -p`; `openrouter` is the HTTP alternative
  (opt-in, needs `OPENROUTER_API_KEY`, research via the web plugin); a `fake`
  backend serves tests.
  A usage-window refusal is classified as `herder.limits.RateLimited` (measured
  signature: `You've hit your session limit · resets 11:10am (America/New_York)`),
  carrying the reset instant parsed from the message itself — so pausing needs no
  access to Claude Code's internal state. It is excluded from
  `_with_transport_retry`, which would otherwise spend three more calls against
  an empty window. Every failed `claude -p` is captured whole under
  `~/.llama/llm-failures/`; the 7-day refusal's wording is still unobserved and
  that capture is how it will be learned.
  **Pacing has two halves.** *Reactive* (phase 1): the refusal above pauses the
  run. *Proactive* (phase 2): a live meter read decides, BEFORE spending
  anything, whether the window can finish the next unit of work. The meter is
  `claude -p "/usage"` via `herder.usage` — a live `GET /api/oauth/usage`, zero
  tokens, NOT an inference call, so it is affordable at every show boundary;
  `~/.claude.json`'s cached utilization is deliberately not read (it was
  measured serving an already-expired window). What a show costs is learned
  from the meter across show boundaries and persisted as an EWMA in
  `pacing-state.json` (`llama.pacing_state`), and `pacing.decide()` turns a
  reading plus that estimate into `Proceed` or `PauseUntil`. Gates sit at the
  top of `_execute` (pre-flight, before the opening burst), before each
  show's lock, and — since T6b — ahead of `run_interpret` at both of its
  in-run call sites (`_get_query`, and `run resume`'s criteria-less
  re-interpret branch). `llama pacing` prints the same picture read-only. `--no-pacing`
  opts out of both halves; a failed meter read degrades to the reactive
  backstop alone and says so.
  **Three boundaries on what that pause guarantee covers, all confirmed in
  review:** **(a) it is `claude_cli`-specific.**
  `packages/herder/src/herder/openrouter.py:37` raises a plain `HerderError` on
  any non-200 response, so an HTTP 429 on the `openrouter` backend is still
  retried three times by `_with_transport_retry` like any other transient
  failure and then fails the show — nothing recognizes an openrouter response
  as a usage-window exhaustion, and `openrouter.py` was deliberately left
  untouched. **(b) `_execute`'s run-level catch covers three stages, not four —
  and `run_interpret`, the fourth, has a catch of its own.** Phase 2
  closed phase 1's per-show-only gap: `cli._execute` wraps `run_discover`,
  `run_search` and `run_winnow` in an `except RateLimited` arm — which must
  stay above any `except HerderError`, since it subclasses it — that
  checkpoints the session `paused` with a `resume_after` instead of exiting 1.
  The resume is recoverable but not cheap: those stages gate on `should_run` at
  WHOLE-STAGE granularity, so the interrupted one re-runs from the top. That
  arm does **not** cover `run_interpret`, which runs outside `_execute`
  entirely. **`interpret` and `discover` are DIFFERENT stages and both exist** —
  the phrase `interpret (run_discover)`, inherited from phase 1's spec, conflated
  them and is the origin of every muddle about what this catch covers; read the
  call sites, not the phrase (`_PIPELINE_RUN_STAGES` is a third, different
  triple that excludes `discover`). **T6b is BUILT**, and `run_interpret` is
  covered by `cli._interpret_with_pause` instead: the pre-flight gate runs
  BEFORE interpret is paid for, and a refusal on the call itself parks the
  session `paused` rather than exiting 1. Both halves apply at both in-run
  call sites — `_get_query` and `run resume`'s criteria-less re-interpret
  branch — because a resume that died on a limit would be the same defect on
  the one command that exists to recover from it, and an account-wide meter
  reading that passed can still be followed by a refusal. What made the
  checkpoint worth writing is the resumability design, not the catch:
  `run_interpret` writes `criteria.json` only on success, so `_get_query`
  persists the raw query and the flags stamped onto criteria as
  `runs/<id>/request.json` at run-claim time, before any LLM call, and
  `run resume` re-interprets from it whenever a session has a request but no
  criteria (`iter_sessions` reads that request too, so a run parked at
  interpret still lists its query).
  **`request.json` is a MODE-AGNOSTIC invocation record (2026-09-07), and
  `--plan` survives a pause in both modes.** It carries an explicit
  `mode: "query"|"profile"` — never inferred from which of `query`/`profile`
  is set, since a reader that infers eventually meets a run where both or
  neither is populated and picks silently — and a MISSING `mode` reads as
  `"query"`, because every artifact written before the field existed was one
  by construction. `_get_profile` writes the record too; without it a
  `--plan` profile run parked by the run-level catch resumed with
  `plan=False` and performed a full acquisition, from the recovery path the
  CLI itself prints, and profiles are the unattended recurring path.
  `run resume` replays the persisted `plan` as
  `bool(req.get("plan")) and not ws.shortlist.exists()`: `--plan` means "stop
  AT the shortlist", so the directive is SATISFIED once one exists — replaying
  it unconditionally is worse than dropping it, because the artifact carries
  `plan: true` for the life of the run and every later resume would re-park
  the session forever, including the one `run approve` recommends.
  **Four readers, not three** (`run_resume`, `_interpret_with_pause`,
  `iter_sessions`, `_by_run_rollup`); the last was missed twice in two
  consecutive features, so check it when adding a fifth. The two SWEEP
  readers go through `sessions.read_request()`, which treats an unreadable or
  non-object file as "no request" so one bad file cannot blind the whole
  triage listing — **`run_resume`'s two reads deliberately do NOT**, because
  there a malformed request must fail loudly rather than silently resume with
  `plan=False`. That asymmetry is pinned by a test asserting the exception
  TYPE (rerouting still exits non-zero, via a downstream `KeyError`), because
  `read_request`'s docstring names the sweep call sites and "unify the
  readers" is the signposted next cleanup. `--no-pacing` restores the pre-pacing
  behaviour here as it does at every other site, though what that MEANS
  differs per site and only two of them literally re-raise: this catch and
  `_execute`'s run-level one do, the per-show loop records a per-show
  failure instead, and the pre-flight gate simply never reads a meter (a
  missing reading proceeds). Note `profile add`
  DOES call `run_interpret`, against a scratch workspace with no session to
  park — so **that one call site still exits 1**, and it is the only
  `run_interpret` call the pause guarantee does not reach; it is `llama get
  --profile`, which reads stored criteria, that never calls it at all.
  **(c) all four pause sites honour
  `--wait`** — the pre-flight gate, the reactive run-level catch above, the
  interpret catch, and the per-show
  loop, through one shared `_render_pause`. This was T7b and is BUILT; the
  asymmetry that preceded it (run-level sites checkpointing even when the wait
  fit inside `--max-wait`, so `llama get --wait` shortly before a reset exited
  having done nothing) is gone. Two things about the run-level sites remain
  worth knowing: after a nap they **re-decide** rather than proceed — the
  pre-flight re-reads the meter, the catch re-runs the stages — because the
  meter is account-wide and the reset may have moved; and they sleep **at most
  once**, since nothing can change between naps at a site where no work has
  completed. That guard is load-bearing rather than tidy: a `when` already in
  the past makes `sleep_until` return without sleeping, so without it the
  second pause is a HOT spin, not a nap — and no sleep-budget guard in a test
  can see it (it hangs rather than failing).
  Set/segue structure is performance-level: gather builds
  a canonical setlist from every recording's description plus setlist.fm
  (optional, key via `SETLISTFM_API_KEY` or `[setlistfm] api_key`; absent key
  = best-effort LMA-only) and aligns it onto the chosen recording's tracks
  (`structure.py`), falling back to the `align_structure` LLM touchpoint for
  messy alignments. Structure evidence for the Garcia universe also comes from
  a vendored, offline jerrybase-derived dataset
  (`packages/llama/src/llama/data/set_breaks.csv`, GPL-3.0 from deadstream; refresh via
  `scripts/refresh_jerrybase.py`): gather uses it after alignment as a
  tripwire (multi-event dates, venue mismatch, contradicted set breaks, wrong
  set count) and a deterministic break-anchoring corrector, never as a setlist
  source (`[jerrybase] enabled`, default on). **Anchoring runs on its own
  evidence and wins whenever it resolves** — it is not gated on
  `align_coverage_threshold`, which now only triggers the LLM realignment
  fallback and the low-confidence flag. Closers match merged tracks on their
  last component and tolerate `&`/`and` and dropped subtitles; a repeated
  closer resolves to its latest occurrence before the next set's closer; a
  trailing encore jerrybase has no row for is preserved, not absorbed. The
  closer tripwire only speaks when anchoring declines. Design:
  `docs/superpowers/specs/2026-08-01-jerrybase-anchoring-design.md`.
  **`align()` matches fuzzily, at the matching layer only**: it normalizes both
  the track and the setlist item at compare time via `fuzzy_norm_title`
  (bypassing the precomputed `SetlistItem.normalized`), folding `&`→`and`,
  tolerating dropped subtitles, matching merged tracks as consecutive runs, and
  dropping credit-only parentheticals. **`songs.normalize_song` and
  `DEFAULT_ALIASES` are deliberately NOT part of this** — folding there would
  also move `grouping`/`vet_research`/`brief`/`setlistfm`, two of which generate
  holds, so don't "simplify" it down a layer. Dead-canon shorthand
  (`songs.GD_SHORTHAND`: `scarlet`→`scarlet begonias`, `chinacat`, …) is
  **gated on artist family** — `jerrybase.is_family_artist`, derived from the
  vendored CSV's own artist keys plus a small extras set — because `scarlet`,
  `help`, `dew`, `eyes` and `saint` are ordinary English words off-family; the
  jerrybase closer path applies it ungated since an event only exists for
  artists in the dataset. `structure._NEVER_EQUAL` blocklists subphrase pairs
  that are genuinely different songs (`It's All Over Now` vs `… Baby Blue`).
  Design: `docs/superpowers/specs/2026-08-01-fuzzy-title-matching-design.md`.
  **`align()`'s lookahead window defaults to 8** (raised from 3), paired with a
  **tail-exhaustion guard** — `structure._tail_guard_declines`, constants
  `TAIL_GUARD_ITEMS=3` / `TRACKS_REMAINING=3` / `MAX_SKIP=6`. `j` advances only
  on a match, so without the guard one far-ahead match can consume the last
  canonical item, exhaust the two-pointer walk and mislabel a show's whole
  tail. The guard declines a hit landing in the final few items while many
  tracks remain unprocessed. **`MAX_SKIP >= lookahead` makes the guard
  structurally unreachable** — that is why it is inert at the old default of 3,
  and `test_align_default_lookahead_is_8` deliberately pins the shipped value
  (reverting it fails that test plus one gather fixture). `TRACKS_REMAINING` is
  measured INERT on both corpora and kept anyway: it is the only thing
  protecting a legitimate tail match on a short tape — do not "simplify" it
  away; its comment records the measurement. Evidence for the change lives in
  `docs/superpowers/2026-08-03-tail-guard-sanity-check.md` and
  `2026-08-04-tail-guard-family-sample.md`.
  **Known gap, filed not fixed:** coverage is matched-tracks over
  song-like-tracks and never inspects UNMATCHED ITEMS, so a partial recording
  can score ~1.0 while missing half the show; `select_recording`'s completeness
  is RELATIVE (best sibling), not absolute.
  Nine named touchpoints (one
  per file under `packages/llama/src/llama/prompts/` — `synthesize` is gone,
  emcee has its own separate `scriptwrite` prompt), each with a Pydantic
  output schema. LLM calls live only at stage boundaries — everything else
  is deterministic.
- **emcee (station-side voicing), architecture:** `emcee run`/`emcee status`
  scan `[station] root` for delivered packages (`packages/emcee/src/emcee/
  station.py`; scans skip dot-prefixed dirs, which are llama's replace-swap
  siblings); `readiness()` computes the same "broadcast-ready" signal
  llama used to (script present, DJ audio present, `broadcast.m3u` present,
  every manifest track's audio on disk) — but as emcee's own derived,
  never-stored state (`ready`/`pending`, plus `unsupported` for a pre-v3
  manifest), not llama's. There is no separate work-queue file: "not
  broadcast-ready" *is* the predicate `emcee run` sweeps on.
  `process.py:process_package` orchestrates one package: resolve presenter
  assignment (`resolve_assignment`, keyed off `manifest["source"]["profile"]`
  against `[assign]`) → `scriptwrite.py` (script LLM task + `script_guard`,
  emcee's own port of llama's old `factual_guard`, persona-styled when a
  presenter is assigned, byte-for-byte neutral otherwise) → render
  `dj-notes.md` → TTS via a `SpeechProvider` (`packages/emcee/src/emcee/tts/`:
  `voxtral` default, `elevenlabs` alternative, `fake` for tests; same
  per-segment cache, `[tts] chunk`, and `[tts] bed` instrumental-bed mixing
  llama used to have) → assemble `broadcast.m3u` → atomically rewrite the
  manifest's `dj_notes`/`dj_audio` blocks last, in place, in the package
  directory llama delivered (`package_io.py:rewrite_manifest`).
  Chunked and bed-active clips are loudness-normalized per sentence/segment
  before the gap and the bed mix (`tts/loudness.py`: −20 dBFS speech-active,
  −1 dBFS peak ceiling, ±10 dB clamp; module constants, no config), because
  Voxtral returns every call at its own level; the unchunked no-bed path ships
  the provider's MP3 untouched and is not normalized.
  Everything else in a package is llama-owned and read-only from emcee's side.
  A Voxtral content-filter refusal (403 `guardrail_violation`) is `SpeechBlocked`:
  emcee narrows it to the sentence, rewords just that segment with the small
  `rephrase` task (2 attempts, gated by `rephrase_problems` + `script_guard`),
  and re-voices only that segment (the task has its own `[llm.rephrase]` config key and does not inherit scriptwrite's backend); a block that exists only across sentences
  fails with "re-run with `[tts] chunk = true`". Blocks are deterministic
  (measured 7/7), so they are never retried identically; transport errors, 429
  and 5xx get one retry.
  **Per-presenter TTS pinning + the local `mlx_audio` backend**
  (`docs/superpowers/specs/2026-10-12-local-tts-presenter-pinning-design.md`).
  A presenter's `tts` pins its backend; an unpinned presenter inherits
  `[tts] backend` — EXCEPT that a presenter never inherits `mlx_audio` (a
  resolution error, `pin tts explicitly`), so moving the house voice never
  moves a presenter. `tts/resolve.py:resolve_tts` is pure and runs before any
  spend; `speech_provider_for(config, resolution, *, voice, clone_ref,
  clone_text)` takes no defaults, so no call site can fall back to `[tts]
  backend` or drop the transcript. Hosted keys/models live in
  `[tts.voxtral]`/`[tts.elevenlabs]` (legacy `[tts] api_key`/`model` still mean
  the HOUSE hosted backend's; the env var still wins). `tts/mlx_audio.py` is
  clone-only, sends `ref_audio` as an ABSOLUTE path (the server reads it from
  its own cwd) plus `ref_text` (`voice_clone_text`), always requests WAV, and
  never falls back. Every mlx clip passes the per-model runaway guard
  (`tts/calibration.py`: `max_tokens` capped in proportion to the text, the
  duration checked; `CALIBRATED_MODELS` holds MEASURED entries only, and an
  uncalibrated model is a resolution error). The quality layer
  (`tts/quality.py`) owns the ONE re-synthesis; a second guard or
  verification failure is a `SpeechDefect` that fails the package. Optional
  transcript verification (`[tts.verify] backends`, `tts/verify.py`) fails only
  gross mismatches and never re-verifies cached clips. `preflight()` runs in
  `cli._process_one` before the `--fresh` unlink, the manifest clear and any
  LLM spend: a no-op on hosted providers, one fixed sentence on mlx, and the
  STT path end to end when verification applies (hosted: the bundled
  `emcee/data/preflight_en.wav`). Evidence: `docs/superpowers/2026-10-12-mlx-audio-probe.md`
  and `…-mlx-audio-calibration.md` (adding a model means a calibration run,
  `scripts/mlx_audio_calibrate.py`). Runbook: README "Local TTS on this Mac".
  `presenters.py` manages `presenters/<id>.toml` (`emcee presenter
  add/edit/list/show/remove`) — the same TOML shape llama's presenters used to
  have (`name`/`sex`/`character` + exactly one of `voice`/`voice_clone`,
  optional `bed` override, plus the optional `tts`/`tts_model`/`voice_clone_text` pin; strict — an unknown key is a load error). emcee never imports llama (enforced by
  `packages/emcee/tests/test_no_llama_imports.py`) — its only input is the
  delivered package directory's files.
- **Quality philosophy:** the LMA is a completist archive. Winnowing demands
  evidence a show is well received by people who were *not* there (LMA reviews
  are heavily attendance-biased). Suspicious output (unresolved track titles,
  duration mismatches, low-confidence setlist parse, a briefing contradicting
  the setlist, a long show with zero set breaks, research asserting songs or
  dates that don't belong to the show) marks a show `needs-review` rather
  than shipping; `--auto` runs skip such shows.

## Domain gotchas

- archive.org items contain junk: `gd73-06-10.sbd.hollister.174.sbeok.shnf`
  (the canonical test fixture) includes a spam file `FOLLOW-ME @BYPIKENO.mp3`
  that would play on air if file lists were trusted. Filter to originals (or
  derivatives of originals) matching the item's dominant filename convention
  with plausible durations.
  **"Plausible duration" is RELATIVE to the tape, never absolute.** The floor is
  `junk.SHORT_FRACTION_OF_MEDIAN` (0.25) × that tape's own median track length,
  falling back to `MIN_PLAUSIBLE_SEC` (90 s) only below `MIN_MEDIAN_SAMPLE` (5)
  usable durations. The old absolute 90 s floor sat *above* the median track
  length of short-song bands and amputated them: `minutemen1983-03-09` has 38
  audio files matching a 38-song description one-for-one, 27 of them under 90 s,
  so llama kept 11 tracks, aligned at coverage **1.00**, and shipped a
  29%-complete show with **no review flag** — the tape was whole and the filter
  made it partial. The two-pass structure in `_keep_and_exclude` is load-bearing:
  the median is taken over files passing every OTHER junk arm, so an item padded
  with spam clips cannot drag the threshold down and license itself. The 0.25/90/5
  constants were measured over 2,030 cached items (see the comment above them) and
  are the same do-not-retune class as the tail-guard constants.
- Track filenames (`gd73-06-10d1t04.mp3`) don't carry song titles; disc/track
  numbering doesn't map to sets. Titles resolve via cascade: recovered-format
  tags → own tags → setlist parsed from the item description → **sibling
  recordings of the same performance (`sibling-align`)** → **setlist-gap** →
  unresolved, with `title_source` recording which fired. Never guess — flag
  unresolved.
  **`setlist-gap`** fills a run of unresolved tracks ONLY when it is
  count-forced (the gap's canonical-item count exactly equals its file count,
  so no shift can hide in it) and anchored by tracks that independently
  matched, plus per-title hygiene; trailing-edge runs are declined outright.
  Measured on 960 cached items it adopts ONCE, so treat it as a slow-burn
  asset: the candidate population (17 items) skews 16:1 toward non-Dead acts,
  where a taper tagging all but a couple of songs is common.
  **Both tautological rungs are excluded from alignment evidence.** A title
  taken from the canonical setlist IS that item's own text, so `align()`
  matching it back is circular — `structure.TAUTOLOGICAL_TITLE_SOURCES`
  (`setlist-gap`, `setlist`) is filtered out of `_songish_coverage`, and those
  tracks carry `matched=None`, not `True`. Without this a mis-adoption raises
  coverage and suppresses the very `low-confidence structure alignment` flag
  that would have caught it.
  **`sibling-align` (v2.4.0) replaced a positional rung, and the old one was
  dangerous.** It aligns the target's tracks against a **tagged sibling
  recording of the same performance** on the *duration sequence*
  (`packages/llama/src/llama/siblings.py`, pure; IO stays in `gather`),
  tolerating merges, splits and filler. The rung it replaced required the
  sibling's track count to equal the target's **exactly** and then transferred
  **by position** — so it declined usable donors, and when it did fire on a
  shifted sibling it shipped the whole tape rotated one song over (pinned by a
  backward mutation in `test_siblings.py`). Adoption is intersected with the
  **unresolved set at application time**, so a real tape tag is never
  overwritten.
  **Three-band anchor-reproduction guard**, of the target's own surviving tags
  ("anchors") that the alignment reproduces: **>= AUTO (0.80)** adopts
  automatically; **FLOOR (0.50) .. AUTO**, or fewer than **MIN_ANCHORS (2)**,
  routes to an operator proposal; **< FLOOR** declines with a show-note. The
  anchor-count clause is evaluated **first** — below `MIN_ANCHORS` the ratio is
  not a measurement, and `declined`'s error basis was never measured there.
  On top of the ratio sits **shape C+**: a run of fills is adopted only when
  agreeing anchors **bracket it on both sides** (`structure.gap_span`'s rule
  reused verbatim, not reimplemented) **and** the span is count-forced; an
  unbracketed run declines **alone** rather than sinking the pair.
  **C+ gates the automatic band and NEVER the proposal display** — applied to
  the renderer it shows a wholly untagged tape nothing, destroying the case the
  work exists for. Do not unify those paths.
  `sibling-align` is deliberately **NOT** in `TAUTOLOGICAL_TITLE_SOURCES`:
  another taper's text assigned by durations is cross-source evidence, not the
  item's own text. Operator-path adoptions land as `override`.
  **The four constants are do-not-retune** and cite
  `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`, which also records
  the honest limits: C+ is **quantified-cost insurance, not measured
  necessity** (it blocks ~28.7 correct titles per error prevented, over a
  population 4x more error-prone), the automatic library yield is **1 track**,
  and the localised-slide class is **real at 136 pairs** but is selected away by
  donor ordering rather than caught by C+. Reviewer verdicts:
  `docs/superpowers/2026-09-02-phase-c-verdicts/`.
  **"Recovered-format tags" is `title_source="sibling-format"`** (the literal
  string a manifest carries), produced by `gather._recover_format_titles` via
  `titles.sibling_format_titles`. Its defining property, and the thing that
  makes it a *different* rung from the "sibling recordings" one four words
  later: the tags come from a **different-format copy of the SAME archive.org
  item** — the FLAC originals beside the MP3 derivatives — matched by a
  **filename-stem bijection** (anything less than a bijection declines rather
  than guessing by position). It is read straight out of cached item metadata:
  **no download, no tag parsing**. The "sibling" rung, by contrast, is a
  *different item* — another taper's recording of the same performance.
  Recovery fires only when the delivered format's `title_fraction` is
  **< 0.5** (`gather._RECOVER_BELOW`) and the other format's clears **>= 0.9**
  (`_RECOVER_SIBLING_ABOVE`). Those two are the values the spec's 166-item
  measurement was taken at and were **not** independently swept — changing
  them invalidates it, the same do-not-retune class as the tail guard's
  constants above. **Recovery is
  wholesale, not gap-filling**: when it fires, the delivered format's own
  tags are not consulted at all, and a recovered title that is still
  unusable falls through to the setlist/sibling cascade rather than back to
  the bad tags. `titles.clean_tag_titles` (the recording-level cleaner;
  `clean_tag_title` remains the per-string one) gates the
  leading-track-number strip on whether the *recording* looks enumerated
  (`>=3` numbered files and `>=80%` coverage) — the `\d{1,3}` bound in
  `titles._TRACK_NUM_PREFIX` is what protects `1952 Vincent Black Lightning`
  and a bare `2001`, and must never be widened to `\d+`. The gate's
  destructive mode — a real numeric title tagged without its own track number
  on an enumerated tape (`100 Years` → `Years`) — is an **accepted, ruled-on
  gap**, pinned by test not fixed; do not tighten the gate.
  `FORMAT_BY_AUDIO`'s values are ordered
  preference tuples, tried in order, never unioned (a
  union would keep every track of a both-formats item twice). The winner is
  the first format whose **kept** set is non-empty — decided *after* junk
  filtering, because one corpus item's every `Flac` entry is junk while 15
  clean tracks sit under `24bit Flac`; when no format survives filtering, the
  first with any audio at all is returned so `excluded` still says why.
  `LOSSLESS_TITLE_FORMATS` is the broader, read-only set used for title
  recovery and deliberately includes `Shorten`, which is not a delivery
  format — measured load-bearing (sole lossless source for 209 of 2,095
  items in a decade-stratified `iacache` sample, not a rate over shows
  llama would select; the numbers and the sample's provenance caveat are
  in its comment), so don't "simplify" it away.
- Setlists in descriptions are convention, not schema; the parser must be
  defensive and report confidence, with an LLM extraction fallback.
  **`parse_setlist`'s items are NOT a reliable "was this song played" oracle,
  and its confidence does not tell you when they aren't.** Plenty of
  descriptions separate non-segued songs with nothing at all — `"Bertha &gt;
  Greatest Story Ever Told West L.A. Fadeaway C.C. Rider ... My Brother Esau"`
  — so only the `&gt;` chains and set markers can be split on; the parser
  merges the rest into one blob, drops it, and still reports
  `confidence="high"` (65 of 67 items in the 1984 GD corpus were "high").
  Anything asking *does this performance contain song X* must therefore match
  the **description text**, via `structure.contains_sequence`, never parsed
  items: on that corpus, of the 27 shows that played "My Brother Esau",
  item equality found **0**, item containment 8, and text containment 27.
  The 0 is not hypothetical — it shipped, as a populated
  `setlist_constraints` that silently emptied the shortlist.
  `contains_sequence` requires order but deliberately **not** adjacency:
  normalization leaves segue markers behind as tokens (`&gt;` → `and gt`), so
  genuinely adjacent songs are almost never adjacent in the normalized text.
  It is a matching-layer function and uses `fuzzy_norm_title` — the same
  `&`/`and` folding as `align()`, for the same reason, and `normalize_song`
  stays untouched (see the fuzzy-matching note above).
- Multiple recordings of the same performance are the norm; show-level merit
  (winnow) and recording-level quality (select-recording) are deliberately
  separate decisions.
- One archive date can hold two performances (early/late show). jerrybase
  `Nevents`/`ievent` is the ground truth; grouping partitions recordings by
  early/late text then description set-closer matching. A tape that spans the
  evening (`.../spans`) or resists assignment (`.../unassigned`) is held for
  review, never split or auto-shipped. gather re-checks the split and flags a
  per-event tape whose tracks actually span both events.

## Conventions

- Audio files (`*.mp3`, `*.flac`, `*.shn`) are gitignored; never commit audio.
  One exception: `packages/emcee/src/emcee/data/preflight_en.wav`, the ~2.6 s
  bundled check clip for the verification preflight (provenance in
  `docs/superpowers/2026-10-12-mlx-audio-calibration.md`).
- Test fixtures are captured real archive.org API responses (gd73-06-10 is the
  canonical one). Pipeline tests use the `fake` LLM backend and run offline;
  the only live end-to-end test is manual/opt-in.
