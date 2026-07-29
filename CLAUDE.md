# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Implemented. The full pipeline (interpret through package) works offline
against the `fake` LLM backend and real archive.org fixtures; see
`docs/superpowers/plans/2026-07-14-llama.md` for the task-by-task
implementation plan this was built from. The approved design spec is
`docs/superpowers/specs/2026-07-14-llama-design.md`.

## Commands

- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e packages/herder -e "packages/llama[dev]"`
- Test: `pytest -q` (offline, deterministic). Single test: `pytest packages/llama/tests/test_setlist.py::test_parses_sets_segues_and_confidence -q`
- Live tests (real archive.org, no LLM): `pytest -m live -q`
- Refresh a fixture: `python scripts/capture_fixture.py <identifier>`
- Run: `llama get "..."`, `llama get --profile <name>`, `llama artists "..."`,
  `llama status` (global triage view, `--by-run` for session rollups),
  `llama show <name>` (read-only), `llama pipeline` (static stage/state
  teaching command), `llama triage` (interactive held-show walkthrough),
  `llama fix <name> <edit-flags>` (overrides/hold editor, auto-redoes),
  `llama redo <name> --from <stage>`, `llama voice <name>` (TTS sugar over
  `redo --from package`), `llama deliver <name>`, `llama rm <name>`,
  `llama suppress`/`llama unsuppress <performance-id>`, `llama run
  list/approve/resume/rm` (session namespace). Shows/sessions are addressed
  by name or unique substring; paths still work. `llama config init` seeds
  a commented config of the baked-in defaults (config values replace
  defaults; nothing merges).

## What this is

`llama` — a Python CLI that finds concerts on archive.org's Live Music Archive
(LMA), winnows them for quality, researches the specific performance online,
and emits a self-contained "show package" (verified audio, m3u, manifest v2
with track titles/set breaks, vetted research + reviews digest; verbatim DJ
script on by default; --no-script or profile script=false opts out) for an automated in-house radio
station. A profile can name a **presenter** (`presenters/<id>.toml`:
name/sex/character + `voice` XOR `voice_clone`) as its on-air host, which
persona-styles the DJ script (opinions and paraphrased review sentiment
allowed; concert facts stay grounded) and voices that profile's runs even
with TTS off station-wide; with no presenter the script stays in the
neutral house narrator. The script can optionally be spoken via TTS
(`--voice`, opt-in, off by default; hosted Mistral Voxtral by default,
ElevenLabs as an opt-in alternative — presenter voice clones are
Voxtral-only). Usage tilts heavily toward Grateful Dead shows (two sets +
encore).
LLM model choice is tiered (low/medium/high; haiku/sonnet/opus on claude_cli,
gemini-flash/sonnet-4.5/opus-4.1 on openrouter): medium by default, high for
deep_research/synthesize, low for vet_research, overridable per task via
`[llm.<task>]` `tier`/`model` or per backend via `[llm.tiers.<backend>]`; a
failed validation's final retry escalates one tier (pins never escalate).

## Architecture (from the spec — the short version)

- **Staged pipeline over an on-disk workspace** (default `~/.llama/`):
  interpret → search (wide net) → winnow (quality gate + optional human gate)
  → select-recording → gather → research → vet (grounding check) →
  synthesize (default-on) → package. Every stage reads/writes plain files;
  run-level artifacts live in a per-run directory, show-level artifacts in a
  canonical `shows/<slug>/` library (one dir per performance, reused across
  runs); stages write outputs only on success and are individually
  re-runnable (`llama redo <show> --from <stage>`).
- **Parallel-safe workspace:** multiple `llama` processes may run concurrently
  against one local `~/.llama/`. Coordination is advisory `fcntl.flock`
  (`packages/llama/src/llama/locks.py`) at two scopes — a short **ledger lock**
  (`ledger.jsonl.lock`) around every ledger mutation, and a long **per-show
  lock** (`shows/<slug>/.lock`) around `process_show` and every single-show
  mutator (`redo`/`fix`/`voice`/`deliver`/`rm`). Locks auto-release on
  process death (no stale-lock reaping). Same-performance runs serialize
  (first builds, others wait and reuse); independent shows run fully in
  parallel. Readers (`show`/`status`/winnow dedup) never lock. All atomic
  writes use unique temp names. POSIX-only; non-POSIX degrades to no-op
  locking.
- **`overrides.json`:** the one durable, app-edited per-show input —
  excluded source-track filenames, `narration` (`full`/`vague`), and
  metadata corrections (`venue`, `city`, `date`, `titles`: track#→forced
  title, `set_breaks`: track numbers a break falls after, numbered-sets-only)
  — that survive every `redo`. `gather` drops excluded files (reason
  `operator-excluded`), forces `venue`/`city`/`date`/track titles/set
  breaks when their fields are set (bypassing structure alignment entirely
  for `set_breaks`), and `synthesize` reads `narration=vague` to write a
  script that names no songs and asserts no set structure; `show.json`
  stays purely derived and is never itself hand-edited. `llama show` is
  strictly read-only; `llama fix <show> <edit-flags>` (flag-driven, single
  show, auto-runs the correct redo) and `llama triage` (interactive
  walkthrough over held shows, default `--held`) are the only ways to edit
  it — `--exclude`/`--unexclude` (filename or track number, `--tracks` on
  `show` lists them) and `--set-venue`/`--set-city`/`--set-date`/
  `--set-title N=…`/`--set-breaks` (plus their `--clear-*` counterparts) all
  redo from `gather`, and a hold **self-clears** whenever the re-gather no
  longer reproduces the flag that caused it (gather recomputes
  `needs_review`/`review_flags` from scratch every run). The other two
  gate-2 resolutions: **accept-vague** (`fix --narration vague` → redo from
  `synthesize`, clears the hold immediately), and **overrule** (`fix
  --overrule` → redo from `package`, clears the hold without touching
  overrides).
- **App-managed instead of hand-edited:** `llama presenter add/list/show/
  remove` creates and inspects `presenters/<id>.toml` (hand-editing the
  TOML still works — `add` is just the other way in), and `llama profile
  artists <name> [--set "A, B, C"]` views or re-pins a profile's pinned
  artist roster. Between these, `llama fix`/`llama triage`, and
  `overrides.json`, `config.toml` remains the only file this design expects
  a human to hand-edit.
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
  used by llama and (later) the persona tool — task registries and prompts
  stay per-app. Provider abstraction with two capabilities — `complete`
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
  source (`[jerrybase] enabled`, default on). Nine named touchpoints, each
  with a prompt template file under `prompts/` and a Pydantic output schema.
  LLM calls live only at stage boundaries — everything else is deterministic.
- **Presenters:** a profile can name an on-air host defined in
  `presenters/<id>.toml` (`name`/`sex`/`character` + exactly one of
  `voice`/`voice_clone`) via the profile's `presenter`/`title` fields
  (`Profile.voice` doesn't exist — a named presenter fully owns the run's
  voice, including its clone_ref, and opts that profile into voice even
  with `[tts] enabled = false`; no presenter falls back to the house
  `[tts] voice`/`voice_clone` and the neutral narrator). `synthesize` builds
  its `{{style}}` block from `persona_style()` when a presenter is present
  (identity, character, and loosened-but-bounded grounding: opinions and
  paraphrased review/research sentiment are the host's own, concert facts
  stay grounded in the show data, no first-hand attendance claims) or the
  byte-for-byte `NEUTRAL_STYLE` otherwise; `vet`/`factual_guard` are
  untouched by presenters. Character edits are live: edit the TOML, then
  `llama redo <show> --from synthesize` re-scripts.
- **Voice (opt-in TTS):** when a show's voice is active, `package`
  synthesizes per-segment spoken DJ audio through a `SpeechProvider` layer
  (`packages/llama/src/llama/tts/`: `voxtral` — hosted Mistral, default — plus `elevenlabs`
  and a `fake` test backend; self-hosting Voxtral is deferred, no local
  backend yet), emitting `package/dj-audio/` (one MP3 per DJ-notes segment)
  plus a manifest `dj_audio` block. `[tts] voice` is a preset name (Voxtral)
  or voice_id (ElevenLabs); `[tts] voice_clone` points at a 3-25s reference
  WAV to clone a custom voice on Voxtral instead, ignoring `voice` (a
  presenter's `voice_clone` is Voxtral-only — the elevenlabs backend
  rejects it). Per-segment caching (keyed on text+voice+model+chunk) avoids
  re-spending on unchanged text; a TTS failure hard-fails just that show's
  package, same as any other stage failure. `[tts] chunk` (default off)
  synthesizes each segment sentence-by-sentence (via `fmt="wav"` on the
  provider) and concatenates the PCM before one MP3 encode via `lameenc`,
  instead of one call for the whole segment — noticeably better prosody on
  longer patter, at the cost of more provider round-trips per segment;
  toggling it invalidates the cache for affected clips. The chunker folds a
  too-short trailing fragment back into the previous sentence (a tiny
  context-free clip like "Here's set two." makes the backend hallucinate),
  and passes each chunk's neighbor text to the provider as context — ElevenLabs
  conditions on `previous_text`/`next_text` for prosody continuity across
  boundaries; Voxtral has no such field and ignores it. A `[tts] bed`
  (per-presenter override `bed` in `presenters/<id>.toml`) mixes a
  low instrumental bed under each DJ clip — pre-roll, bed-under-voice, then tail,
  at `[tts] bed_gain_db` (default -20 dB); beds must be 24kHz mono 16-bit WAV
  (hard-fail on mismatch), mixed via numpy (no ffmpeg).
- **Broadcast-ready:** a derived (never stored) signal, computed the same way
  as `voiced` — true iff the show is packaged with every manifest track's
  audio file verified on disk, has a DJ script, has DJ audio, has
  `package/broadcast.m3u`, and is not held for review; an unvoiced show can
  never qualify (no DJ audio or `broadcast.m3u` without voice). Surfaced as a
  `broadcast-ready` tag and `--broadcast-ready` filter/JSON field on `llama
  status`, a `--broadcast-ready` selector on `llama
  triage`/`redo`/`voice`/`deliver`/`rm`, and a `broadcast-ready: yes|no`
  (+ reasons when `no`) line on `llama show <name>`. `deliver` requires
  broadcast-ready by default (`--allow-unvoiced` is the sole,
  music-only-ship override; there is no held-show override at all).
  Positive-only — no `--not-broadcast-ready` inverse.
- **Quality philosophy:** the LMA is a completist archive. Winnowing demands
  evidence a show is well received by people who were *not* there (LMA reviews
  are heavily attendance-biased). Suspicious output (unresolved track titles,
  duration mismatches, low-confidence setlist parse, DJ notes contradicting
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
