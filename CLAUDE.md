# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Implemented. The full pipeline (interpret through package) works offline
against the `fake` LLM backend and real archive.org fixtures; see
`docs/superpowers/plans/2026-07-14-llama.md` for the task-by-task
implementation plan this was built from. The approved design spec is
`docs/superpowers/specs/2026-07-14-llama-design.md`.

## Commands

- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee`
- Test: `pytest -q` (offline, deterministic). Single test: `pytest packages/llama/tests/test_setlist.py::test_parses_sets_segues_and_confidence -q`
- Live tests (real archive.org, no LLM): `pytest -m live -q`
- Refresh a fixture: `python scripts/capture_fixture.py <identifier>`
- Stitch a playlist into one mp3: `python3 scripts/stitch_m3u.py <playlist.m3u>`
  (standalone, stdlib-only, needs ffmpeg/ffprobe; stream-copies uniform mp3
  input and re-encodes otherwise, writing ID3 chapters per entry and pulling
  tags from a sibling `manifest.json` when there is one). `scripts` is in
  pytest `testpaths`, so its tests run under plain `pytest -q`.
- Run (llama, acquisition): `llama get "..."`, `llama get --profile <name>`,
  `llama artists "..."`, `llama status` (global triage view, `--by-run` for
  session rollups), `llama show <name>` (read-only), `llama pipeline`
  (static stage/state teaching command), `llama triage` (interactive
  held-show walkthrough), `llama fix <name> <edit-flags>` (overrides/hold
  editor, auto-redoes), `llama redo <name> --from <stage>`,
  `llama deliver <name>`, `llama rm <name>`, `llama suppress`/
  `llama unsuppress <performance-id>`, `llama run list/approve/resume/rm`
  (session namespace). Shows/sessions are addressed by name or unique
  substring; paths still work. `llama config init` seeds a commented config
  of the baked-in defaults (config values replace defaults; nothing
  merges). No `voice`/`presenter` commands — that's emcee's job now.
- Run (emcee, station-side, post-`llama deliver`): `emcee run` (scan
  `[station] root` and voice every not-yet-broadcast-ready package),
  `emcee voice <package-path>` (script + voice + assemble one package;
  `--fresh <clip-stem>` deletes just that cached clip, but since emcee
  re-scripts on every call, a real LLM's regenerated text usually
  invalidates every clip's cache too — in practice `--fresh` normally
  re-renders every clip, not just the named one; `--force` re-synthesizes
  all of them unconditionally), `emcee status` (table of every package's
  state: ready/pending/unsupported), `emcee presenter add/list/show/remove`
  (`presenters/<id>.toml`), `emcee config init`.

## What this is

Two Python CLIs — `llama` and `emcee` — that together carry an archive.org
Live Music Archive (LMA) recording all the way to air. They ship as separate
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
not held for review, and every manifest track's audio file present on disk.

`emcee` (dist name `llama-emcee`, bare CLI `emcee`) is station-side and runs
**after** `llama deliver` — it operates on the delivered-packages folder
(`[station] root`), never on llama's own library. "Not broadcast-ready" IS
the work predicate: `emcee run` scans the station root and voices every
package that isn't yet broadcast-ready, no separate state file needed.
emcee owns presenters (`presenters/<id>.toml`: name/sex/character +
`voice` XOR `voice_clone`), the script LLM task and its own factual guard,
`speech_text` normalization, TTS (hosted Mistral Voxtral by default,
ElevenLabs as an opt-in alternative — presenter voice clones are
Voxtral-only), instrumental beds, the per-segment render cache, and
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
gemini-flash/sonnet-4.5/opus-4.1 on openrouter): medium by default, high for
llama's deep_research/brief and emcee's scriptwrite, low for vet_research,
overridable per task via `[llm.<task>]` `tier`/`model` or per backend via
`[llm.tiers.<backend>]`; a failed validation's final retry escalates one
tier (pins never escalate).

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
  title, `set_breaks`: track numbers a break falls after, numbered-sets-only)
  — that survive every `redo`. `gather` drops excluded files (reason
  `operator-excluded`), forces `venue`/`city`/`date`/track titles/set
  breaks when their fields are set (bypassing structure alignment entirely
  for `set_breaks`), and `brief` reads `narration=vague` to write a
  briefing that names no songs and asserts no set structure (the LLM's own
  opinion of `narration` is never trusted — stamped from `overrides.json`
  after generation); `show.json` stays purely derived and is never itself
  hand-edited. `llama show` is strictly read-only; `llama fix <show>
  <edit-flags>` (flag-driven, single show, auto-runs the correct redo) and
  `llama triage` (interactive walkthrough over held shows, default
  `--held`) are the only ways to edit it — `--exclude`/`--unexclude`
  (filename or track number, `--tracks` on `show` lists them) and
  `--set-venue`/`--set-city`/`--set-date`/`--set-title N=…`/`--set-breaks`
  (plus their `--clear-*` counterparts) all redo from `gather`, and a hold
  **self-clears** whenever the re-gather no longer reproduces the flag that
  caused it (gather recomputes `needs_review`/`review_flags` from scratch
  every run). The other two gate-2 resolutions: **accept-vague** (`fix
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
  backend serves tests. Set/segue structure is performance-level: gather builds
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
  `docs/superpowers/specs/2026-08-01-jerrybase-anchoring-design.md`. Nine named touchpoints (one
  per file under `packages/llama/src/llama/prompts/` — `synthesize` is gone,
  emcee has its own separate `scriptwrite` prompt), each with a Pydantic
  output schema. LLM calls live only at stage boundaries — everything else
  is deterministic.
- **emcee (station-side voicing), architecture:** `emcee run`/`emcee status`
  scan `[station] root` for delivered packages (`packages/emcee/src/emcee/
  station.py`); `readiness()` computes the same "broadcast-ready" signal
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
  directory llama delivered (`package_io.py:rewrite_manifest`). Everything
  else in a package is llama-owned and read-only from emcee's side.
  `presenters.py` manages `presenters/<id>.toml` (`emcee presenter
  add/list/show/remove`) — the same TOML shape llama's presenters used to
  have (`name`/`sex`/`character` + exactly one of `voice`/`voice_clone`,
  optional `bed` override). emcee never imports llama (enforced by
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
- Track filenames (`gd73-06-10d1t04.mp3`) don't carry song titles; disc/track
  numbering doesn't map to sets. Titles resolve via cascade: embedded tags →
  setlist parsed from the item description → sibling recordings of the same
  performance. Never guess — flag unresolved.
- Setlists in descriptions are convention, not schema; the parser must be
  defensive and report confidence, with an LLM extraction fallback.
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
- Test fixtures are captured real archive.org API responses (gd73-06-10 is the
  canonical one). Pipeline tests use the `fake` LLM backend and run offline;
  the only live end-to-end test is manual/opt-in.
