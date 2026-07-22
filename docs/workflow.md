# How llama works: the operator's guide

This is the user-facing map of the whole system: what the pipeline does, what
lands on disk where, the two different human gates and how they differ, every
command, every review flag, and a troubleshooting table from "message you saw"
to "what to do next." The design rationale lives in
`docs/superpowers/specs/`; this document is about *operating* it.

## The big picture

```
llama find "query"          llama profile run <name>
        │                           │
        ▼                           ▼
   interpret ──► search ──► winnow ──► [gate 1: shortlist approval]
                                              │
                              per approved show│
                                              ▼
             select-recording ──► gather ──► research ──► vet
                                              │
                            [gate 2: needs-review can halt here]
                                              │
                                  synthesize (default; --no-script skips)
                                              │
                                              ▼
                                          package ──► llama deliver
```

Every stage reads and writes plain files. Run-level artifacts (criteria,
candidates, shortlist) live in a per-run directory under `~/.llama/runs/`;
show-level artifacts live in a canonical **shows library** at
`~/.llama/shows/<slug>/` — one directory per performance, shared across
runs. Stages **skip work whose output file already exists**, so any command
that touches a run or show is cheap to re-execute — this is the core
mechanic behind resuming, and behind most of the answers in this guide.
Because the library is shared, a performance that surfaces again in a later
run lands on the same directory and reuses the expensive work (research,
package) already done.

Day to day, the workspace is show-centric: `llama status` is the triage
view (what's held, what's packaged and ready to deliver), and
`llama redo <show> --from <stage>` re-runs one show's pipeline tail without
touching its run or any other show.

There are two modes:

- **One-off:** `llama find "GD shows 73-74 with a china>rider"` — interprets
  the query, runs the whole pipeline.
- **Standing profiles:** `llama profile add` / `llama profile run` — a saved
  query re-run for recurring segments, deduplicated against the broadcast
  ledger so the same performance is never shipped twice.

## The on-disk workspace

Everything lives under `~/.llama/` (configurable as `root` in
`~/.llama/config.toml`):

```
~/.llama/
├── config.toml                  # optional; see README
├── ledger.jsonl                 # broadcast history (dedup + audit)
├── cache/                       # archive.org responses + artist index
├── profiles/<name>.toml         # standing profiles
├── runs/<run-name>/             # run-level artifacts only
│   ├── criteria.json            # interpreted query (interpret stage)
│   ├── candidates.json          # every performance found (search stage)
│   ├── shortlist.json           # ranked + scored top shows (winnow stage)
│   └── artists.json             # artist-less queries only: matched artists
└── shows/<slug>/                # canonical shows library: one dir per
    │                            # performance, slug = slugified performance id
    │                            # (gratefuldead-1973-06-10), shared across runs
    ├── provenance.json          # which run processed it, winnow dossier,
    │                            # script setting — what `redo` replays from
    ├── selection.json           # which recording won and why
    ├── show.json                # tracks, sets, flags — THE show state file
    ├── reviews.json             # raw listener reviews
    ├── research.md              # deep-research output
    ├── vetting.json             # grounding-check results
    ├── dj-notes.md/.json        # verbatim DJ script (default; absent with --no-script)
    ├── llm-failure.txt          # raw LLM output if a task failed validation
    └── package/                 # the deliverable
        ├── manifest.json        # schema v2: tracks, sets, durations, context
        ├── playlist.m3u
        ├── audio/               # verified, tagged tracks
        ├── research.md
        ├── reviews.md
        ├── dj-notes.md          # absent only with --no-script
        └── dj-audio/            # opt-in TTS clips; present only when voiced
```

Run names default to `YYYY-MM-DD-<slugified-query>` for `find` and
`YYYY-MM-DD-<profile-name>` for profiles. Show slugs come from the
performance identity (artist + date), so they are stable across runs by
construction.

Two files deserve a callout:

- `show.json` carries `needs_review` and `review_flags`, and it is what
  gate 2 reads. When a show is held, this file says why.
- `provenance.json` is written every time a show is processed: which run
  caused it, the winnow dossier and quality assessment, and the script
  setting. It is what lets `llama redo` re-run a show standalone — the
  originating run directory doesn't even need to exist anymore.

## Names and states: the catalog

Every command that takes a show or run accepts a **name, a unique
substring, or a path**: exact match wins, otherwise a substring that
matches exactly one candidate resolves to it, otherwise the command fails
loudly and lists the matches. `llama show 1973-06-10` is the typical form;
`llama run countryish` resolves `2026-07-16-countryish`.

A show's **state** is never stored — it is derived from which artifacts
exist plus the ledger, so it cannot go stale:

| State | Derived from | Meaning |
|---|---|---|
| `held` | `show.json` has `needs_review: true` | Gate 2 hold; sorts first in `llama status`, flags shown inline |
| `delivered` | ledger has a `delivered` entry for the performance | Shipped to the station |
| `packaged` | `package/manifest.json` exists | Ready to deliver |
| `scripted` / `vetted` / `researched` / `gathered` / `selected` | deepest stage artifact present | In-flight (or abandoned mid-pipeline) |

`llama status` is the triage table over these states; `llama runs`
summarizes per-run show counts. Both are in the command reference below.

## The stages

| Stage | LLM? | Writes | What it does |
|---|---|---|---|
| interpret | yes | `criteria.json` | Query → structured criteria (artist, era, count, constraints) |
| discover | yes | `artists.json` | Artist-less queries only: match style against the LMA artist index |
| search | no | `candidates.json` | Wide-net archive.org search via the cursor-paginated scrape API — every matching recording, uncapped; groups recordings by performance identity (artist + date + venue). Complete recording lists matter downstream: siblings feed set-structure recovery and recording selection |
| winnow | yes ×2 | `shortlist.json` | Ledger dedup → mechanical floors (rating/review count, setlist constraints) → LLM review scoring → quality floor (`min_quality_score`, default 6.0: lower-scored shows are dropped with a warning, so a thinning pool comes back short and loud instead of quietly mediocre) → light web research on the top 12+. When survivors exceed the review-fetch budget (`[winnow] max_metadata_fetch`, default 40), it samples the best-evidenced, bounded by `artist_cap`/`year_cap`. The shortlist cut is best-score-first with per-artist share capped at `artist_cap` (default 1/3) and per-year share capped at `year_cap` (default 1.0 = off — scores decide the year mix); equal scores tie-break on review evidence, not date |
| select-recording | no | `selection.json` | Picks the best *recording* of the performance: lineage (SBD > MTX > AUD, era-overridable — early-80s GD inverts to MTX > AUD > SBD), ratings, completeness (scales the score: fragments lose to fuller tapes), and `[selection.tapers]` reputation bonuses (miller/seamons for GD; newest revision of a taper preferred), sibling-relative download popularity, and embedded-title coverage (both small tie-breaker-sized terms) |
| gather | maybe | `show.json`, `reviews.json` | Junk-filters files, resolves track titles (tags → setlist → siblings), builds canonical set structure from all recordings + setlist.fm, aligns it onto tracks; LLM only as alignment/extraction fallback |
| research | yes | `research.md` | Deep web research on the specific performance |
| vet | yes | `vetting.json` | Extracts the research's factual claims; deterministic grounding check against the setlist and date |
| synthesize | yes | `dj-notes.*` | On by default (`--no-script` skips): verbatim DJ script, factually guarded against the manifest |
| package | no | `package/` | Downloads audio (md5-verified), tags it, checks durations, writes manifest v2 + m3u + digests; if voice is active, also synthesizes `dj-audio/` clips (Voxtral by default, or ElevenLabs) and adds the manifest's `dj_audio` block |

Winnow's philosophy: the LMA archives everything, so mere presence means
nothing, and LMA reviews skew toward people who attended the show. The
scoring prompt demands merit-based praise, and light research looks for the
show's reputation *outside* the archive.

Quality earns the slots; caps only bound dominance. The shortlist cut and
the final auto-pick fill best-score-first with two optional bounds: while
other artists still have candidates, no artist may hold more than a share
of the batch (`--artist-cap` on `find`/`profile add`, default 1/3 — at
most ⌈n×cap⌉ slots), and `--year-cap` does the same per year (on
multi-artist runs, within each artist's own slots). `year_cap`
defaults to 1.0 (off): an unranged Dead query comes back 70s-heavy if
that's what the scores say. Set it for an era tour — `--year-cap 0.25`
keeps any year to a quarter of the batch; at or below 1/count it's strict
one-per-year rotation ("1969-1977" as a spread). Either cap at 1.0
restores pure top-N; a dominant artist or year is bounded, not rationed,
and if everything else runs out the cap relaxes rather than
under-delivering. The review-fetch sampling honors the same caps, and
equal scores tie-break on review evidence rather than date (score bands
cluster, and a date tie-break would quietly favor the earliest years).

Variety guarantees exist within a single batch only — nothing rotates
across runs, and the ledger's job is dedup, not rotation. Want no artist
repeated across your next N shows? Generate the N in one run. Explicit
`llama review` approvals are never capped; your picks are your picks.

## The two human gates (don't confuse them)

This is the single most confusing part of the system, so here it is plainly:

|  | Gate 1: shortlist approval | Gate 2: needs-review |
|---|---|---|
| **Question it asks** | "Which of these shows should we spend money processing?" | "Is this processed show clean enough to air?" |
| **Granularity** | The run's shortlist | One show |
| **Lives in** | `runs/<run>/shortlist.json` (`approved: true/false/null`) | `shows/<slug>/show.json` (`needs_review` + `review_flags`) |
| **Set by** | You (interactive prompt, or `llama review`) | The pipeline (gather/vet/synthesize/package flags) |
| **Cleared by** | `llama review <run>` | `llama show <show> --clear` (after you inspect) |
| **Surfaced by** | `Shortlist awaits review:` message | `llama status --held` |
| **What it blocks** | Processing starting at all | Packaging (or delivery, if flagged during packaging) |

**Gate 1** appears interactively during `llama find` ("Process which
ranks?"), or — for a `--human-gate` profile run with `--auto` — as the printed
message `Shortlist awaits review: llama review <run>`. `llama review`
records your picks and then offers to process them on the spot; decline and
it prints the resume command (`llama run <run>`) instead.

**Gate 2** fires per show, any time a stage records a review flag in
`show.json`. The pipeline checks it at three points (after vet, after
synthesize, after package) and prints `needs-review, skipped: <show>`. The
flags that can be set, and by which stage:

| Flag | Stage | Meaning |
|---|---|---|
| `unresolved track titles` | gather | Some filenames could not be mapped to song titles by any source |
| `low-confidence setlist` | gather | The best setlist parse is shaky |
| `low-confidence structure alignment` | gather | Setlist found, but it doesn't line up with the actual tracks (even after LLM fallback) |
| `setlist evidence shows multiple sets but alignment found none` | gather | Sources say multi-set; the aligned tracks came out flat |
| `single-set structure for a long show (N min)` | gather | 150+ minutes (configurable `guard_min_minutes`) with zero set breaks — past the plausible length of one uninterrupted set |
| `no playable tracks` | gather | Junk filtering left nothing |
| `research asserts unknown song: X` | vet | Most of the research's song assertions don't match this show's tracks (≥2 unknown and more than a third of all assertions — the wrong-show signal). Titles match loosely: segue chains ("A > B") check per-song, and prose variants ("Caution", "One More Saturday Night") match tracks by containment. One or two strays never block |
| `research asserts wrong date: X` | vet | Research names a date that isn't this show's date (year-less forms like "December 2" or "3/2" compare against the show's month and day) |
| ~~unparseable date~~ | vet | No longer blocks: a date the checker can't parse is recorded in `vetting.json` but can't-verify is not a contradiction |
| `dj notes mention unknown song / nonexistent set / missing set intros / break count mismatch` | synthesize | The DJ script contradicts the manifest |
| `duration mismatch on <file>` | package | Downloaded audio's real length disagrees with metadata |

**Clearing gate 2.** There is deliberately no `--force`-through-processing
flag: a flagged show stays held until a human looks. Looking means
`llama show <show>` — it prints the flags, state, and a table of which
stage artifacts exist. Then:

- **Fix the input and re-run the stage that flagged it.** Vet flags are
  self-clearing: `llama redo <show> --from vet` re-vets and recomputes
  (its own old flags are dropped first). Gather flags likewise clear if a
  re-gather (`llama redo <show> --from gather`) produces clean structure —
  e.g. after adding a setlist.fm API key. `redo` keeps the expensive
  `research.md` by default.
- **Overrule it.** If the flags are false alarms:
  `llama show <show> --clear`, then `llama redo <show> --from package`
  (the `--clear` output prints exactly this next step). Earlier stages'
  artifacts are reused and packaging proceeds.
- **Deliver-time-only flags** (`duration mismatch`) are the one case where a
  package already exists; `llama deliver <show> --force` overrides the
  delivery refusal.

## Voice (opt-in text-to-speech)

The DJ script can additionally be **spoken** during `package` — off by
default. The default backend is hosted Mistral Voxtral
(`voxtral-mini-tts-2603`); set `[tts] backend = "elevenlabs"` to speak via
ElevenLabs instead. Turn voice on globally (`[tts] enabled = true` +
`[tts] voice` in config), per invocation (`--voice` on `find`/`run`/
`review`/`redo`), or per profile (`--voice VOICE_ID` on `profile add`,
which opts that profile in even when `[tts] enabled` is false, so
different profiles can use different voices). `--no-voice` always turns it
off for that invocation. **Voice implies script**: turning voice on forces
the DJ script on even against `--no-script`, since there is nothing to
voice otherwise.

`[tts] voice` is a preset name on Voxtral (or a voice_id on ElevenLabs).
For a custom station voice, set `[tts] voice_clone` to a 3-25s reference
WAV instead — Voxtral clones it and ignores `voice`. (Voxtral's open
weights are CC BY-NC, but that only matters for self-hosting; llama's
non-commercial project only ever calls Mistral's hosted API, so the
license is irrelevant here. Self-hosting is deliberately out of scope.)

Voiced shows gain `package/dj-audio/` (one MP3 per script segment) and the
manifest's `dj_audio` block — see [docs/station-brief.md](station-brief.md)
for the exact contract. Segments are cached per show by a hash of (text,
voice, model), so re-packaging with unchanged text doesn't re-spend on the
paid API.

**Re-voicing an already-packaged show:** `llama redo <show> --from package
--voice` re-voices with the show's recorded voice (or, if it had none yet,
the current `[tts] voice`/profile voice). `--voice`/`--no-voice` on
`find`/`run`/`review`/`redo` only toggle voice on or off — there's no
per-invocation voice-id override; to actually switch to a different voice,
change `[tts] voice` (or the profile's `voice`) first. `--force` re-renders
every clip instead of reusing the cache. A plain `llama run <run> --voice`
on a run whose shows are already packaged does **not** re-voice them — the
package stage is skipped because its output already exists — it prints a
note pointing at `redo --from package --voice`.

**Failure holds the show, not the batch.** If the TTS backend fails (bad
key, rate limit, missing key while voice is active), that show produces no
package (no manifest) and isn't delivered; llama prints `FAILED <show>: …`
and moves on to the rest of the batch. Retry with
`llama redo <show> --from package` once the API issue is resolved — the
cache means a retry only re-renders what didn't finish.

## Command reference

In every command below, `<show>` and `<run>` mean "name, unique substring,
or path" — see [Names and states](#names-and-states-the-catalog).

### `llama find "query" [--limit N] [--auto] [--no-script] [--voice/--no-voice] [--run-name NAME]`
One-off end-to-end run. Interactive by default: artist-less queries let you
prune the matched-artist list, and the shortlist prompt asks which ranks to
process (empty answer = top picks). `--auto` skips all prompts and takes the
top-ranked shows. The verbatim DJ script is generated by default (one extra
high-tier LLM call per show); `--no-script` skips it. `--voice` synthesizes
spoken DJ audio (Voxtral by default, or ElevenLabs; default follows
`[tts] enabled`; implies `--script`) — see
[Voice](#voice-opt-in-text-to-speech) above. Winnow knobs:
`--artist-cap`, `--year-cap`, `--min-score` (see the winnow discussion
above). `--full-rationale` prints each shortlisted show's complete
selection rationale instead of the first few lines (also available on
`run`, `review`, and `profile run`).

### `llama status [--held] [--packaged] [--run NAME] [--artist SUBSTR] [--all] [--json]`
The triage table: every show in the library with its derived state, artist,
date, and originating run; held shows sort first with their flags indented
beneath. By default only the 5 most recently delivered shows are kept in
the listing — `--all` shows every delivered show. `--held` / `--packaged`
filter to one state ("what needs my judgment" / "what's ready to ship"),
`--run` filters to shows processed by that exact run name, `--artist`
substring-matches the artist, and `--json` emits the records for scripting.

### `llama runs`
One line per run: name, show-state counts (via each show's provenance), and
the run's query. The run-side companion to `llama status`.

### `llama run <run> [--stage S --force] [--interactive] [--no-script] [--voice/--no-voice]`
**The resume/replay command.** Re-executes a run from its artifacts; every
stage skips work whose output already exists, so this is how you continue
after a crash, after `llama review`, or after fixing something by hand.
To re-run a stage for a *single show*, reach for `llama redo` instead —
`--stage --force` here applies to every show the run processes.

- `--stage <name> --force` deletes that stage's outputs **and everything
  downstream of it**, then re-runs — later stages can never reuse artifacts
  derived from the pre-force state. Deletion happens **per show, at process
  time, only for the shows chosen this run** — shows not selected for
  reprocessing keep their artifacts and packages intact. Valid stages:
  `search`, `winnow`, `select`, `gather`, `research`, `vet`, `synthesize`,
  `package`. Forcing `search` also drops the shortlist.
- Bare `--force` re-runs **everything**, including winnow — this rebuilds
  `shortlist.json`. If approvals were recorded on it, llama asks for
  confirmation before wiping them. Reach for `--stage X --force` first.
- Replays are faithful: the run's `criteria.json` carries the `count`,
  `script`, and `voice` settings it was created with (`find
  --limit/--no-script/--voice` and `profile run` stamp them), so `llama
  run` processes the same number of shows with the same script/voice
  settings. `--script`/`--no-script` and `--voice`/`--no-voice` explicitly
  override the persisted values.
- `--voice` only re-voices shows this invocation actually reprocesses. On an
  already-packaged show the package stage is skipped (its output already
  exists), so plain `llama run <run> --voice` is a no-op for it — llama
  prints a note pointing at `llama run <run> --stage package --force
  --voice` (forces just the package stage, for every show this run
  processes) or `llama redo <show> --from package --voice` (one show,
  standalone).
- Defaults to `--auto` (no prompts), unlike `find`.

### `llama review <run> [--script/--no-script] [--voice/--no-voice]`
Gate 1 only: prints the shortlist, asks which ranks to approve, and writes
the answer into `shortlist.json`. Ranks you don't name are left undecided
(once anything is approved, only approved entries are processed). It then
offers to process the approved shows immediately; decline and it prints the
`llama run` command to do it later. Empty input changes nothing. It has no
connection to needs-review (gate 2). `--script`/`--no-script` and
`--voice`/`--no-voice` override the run's persisted settings if you process
immediately.

### `llama show <show> [--clear]`
Gate 2: inspect one show — artist/date/venue, chosen recording, derived
state, a table of stage artifacts (present + age, or missing), and the
needs-review flags. `--clear` overrules the hold (clears `needs_review` and
the flags) after you've judged them false alarms, and prints the follow-up
(`llama redo <show> --from package`).

### `llama redo <show> --from STAGE [--with-research] [--script/--no-script] [--voice/--no-voice]`
Re-run one show's pipeline from a stage onward, standalone — no run replay,
no other show touched. `--from` is required; stages:
`select | gather | research | vet | synthesize | package`. It deletes that
stage's artifacts **and everything downstream**, then re-runs the tail
using the show's `provenance.json` (candidate, winnow dossier, script/voice
settings) — the originating run directory is not needed.

- **`research.md` is kept by default** on `--from select`/`--from gather`:
  it's the expensive high-tier call and depends on performance identity,
  not recording choice; vet's grounding checks are the safety net if a
  structural fix leaves it slightly stale. `--with-research` drops it too;
  `--from research` redoes it by definition.
- The script setting recorded at process time is replayed;
  `--script`/`--no-script` overrides it.
- **`--from package --voice` is the standard way to (re-)voice one show**:
  `--voice` re-voices using the recorded (or given) voice, `--no-voice`
  strips voice from the package. Unchanged segments aren't re-synthesized
  (cached by text+voice+model) unless the recorded voice actually changed;
  there is no separate `--force` needed here since `redo` always rebuilds
  the stage it starts from.
- A show without `provenance.json` (hand-built dir) errors — reprocess it
  via its run once.

### `llama deliver <show> [--dest DIR] [--force]`
Copies the show's `package/` into the station's watched folder
(`delivery_path` from config, or `--dest`) and records a `delivered` ledger
entry (run attribution from `provenance.json`). Refuses if the show is
marked needs-review; `--force` overrides. `llama status --packaged` lists
what's ready to deliver.

### `llama config init [--stdout] [--config PATH]`
Seed `~/.llama/config.toml` (or `--config PATH`) with the baked-in
defaults as a fully-commented TOML file. Refuses to overwrite an existing
file; `--stdout` prints the template instead. Exists because config
values **replace** defaults rather than merging: any
`[selection.tapers.*]` or `[[selection.lineage_eras]]` you add replaces
the built-in GD tuning unless the defaults are restated — which the
seeded file does for you.

### `llama artists ["query"] [--limit N] [--all] [--refresh]`
Search the LMA artist index with a natural-language query, or with no query
list the deepest catalogs. `--all` bypasses the junk-filter floors.

This is the **test-drive** for a profile/find query: it calls the same LLM
matcher on the same request text with the same budget (20; `[artists]
max_matched` in config governs the pipeline side), so its list previews what
a run would search. The matcher is still an LLM — two calls can rank
differently — so when you've settled on a roster, pin it (below) and runs
stop consulting the matcher at all.

### `llama profile add <name> "query" [--count N] [--human-gate] [--no-script] [--voice VOICE_ID] [--artists "..."]`
Interprets the query once and saves it as a standing profile.
`--human-gate` makes `profile run --auto` stop at gate 1 instead of
self-approving. `--voice VOICE_ID` gives this profile its own voice (a
Voxtral preset name by default, or an ElevenLabs voice_id when
`[tts] backend = "elevenlabs"`), saved on the profile; it voices every run
of this profile even when `[tts] enabled` is false globally, so different
profiles can speak in different voices (voice implies script). `--artists
"Galactic, Lettuce, ..."` pins the roster: names resolve against the
artist index at add time (typos and ambiguity fail immediately), and every
run of the profile searches exactly those artists — deterministic, no LLM
matching, no prune prompt. Edit the `artists` list under `[criteria]` in
the profile TOML to change it later.

### `llama profile run <name> [--auto]`
Runs the profile as a new dated run, skipping performances already in the
ledger. With `--human-gate` and `--auto`, stops at
`Shortlist awaits review: llama review <run>`; approve, then
`llama run <run>`.

### `llama profile list` / `llama ledger list` / `llama ledger add` / `llama ledger remove`
Housekeeping. The ledger is the dedup memory: `selected` and `delivered`
entries suppress a performance in future winnows; `rejected` entries do too.
`ledger remove <performance-id>` un-suppresses one.

## Recipes

**What's the state of everything? / What came in overnight?**
`llama status` — held shows first with their flags, then packaged
(ready to deliver), then in-flight. `llama status --packaged` is the
ship-it worklist; `llama deliver <show>` each one.

**A run printed `needs-review, skipped` for a show I want.**
`llama show <show>` to read the flags. If a flag is a false alarm,
`llama show <show> --clear` and then `llama redo <show> --from package`.
If it's real (e.g. unresolved titles), fix the cause and
`llama redo <show> --from <stage>`.

**I approved via `llama review` — now what?**
Say yes when it offers to process, or `llama run <run>` later.

**A stage failed with an LLM error.**
The raw output is in `shows/<slug>/llm-failure.txt`. Just re-run
`llama run <run>` — completed stages are skipped, the failed one retries.

**I want a different recording of the same show.**
`llama redo <show> --from select` — the drop cascades, so gather through
package rebuild from the newly picked recording. `research.md` is kept
(it's about the performance, not the recording); add `--with-research` if
you want it redone too.

**Re-research a show.**
`llama redo <show> --from research` — this also deletes `vetting.json`,
so the new research gets re-vetted.

**I want to add (or change) the spoken DJ voice on an already-packaged show.**
`llama redo <show> --from package --voice`. To switch to a *different*
voice, set `[tts] voice` (or the profile's `voice`) to the new id first —
`--voice` itself just turns voicing on, it replays the show's already-
recorded voice if it has one. Unchanged script segments aren't
re-synthesized, so this is cheap even against the paid API. `llama redo
<show> --from package --no-voice` strips voice audio back out.

**The same show keeps coming back in every profile run.**
It's not in the ledger. Deliver it, or `llama ledger add <performance-id>
--artist A --date D --status rejected` to suppress it.

**A search or winnow decision looks wrong (run-level, not one show).**
Stage forcing at the run level still exists:
`llama run <run> --stage winnow --force` rebuilds the shortlist
(confirming first if approvals would be lost); `--stage search --force`
re-searches and drops the shortlist with it.

## Troubleshooting: message → meaning → action

| You see | It means | Do |
|---|---|---|
| `Shortlist awaits review: llama review <run>` | Gate 1 is waiting (human-gate profile) | `llama review <run>` (it offers to process after) |
| `approved: [1]` (from review) | Picks recorded | Say yes at the process prompt, or `llama run <run>` later |
| `needs-review, skipped: <show>` | Gate 2: a flag was set during processing | `llama show <show>`; fix (`llama redo --from <stage>`) or `--clear`, then `llama redo <show> --from package` |
| `skipping <show>: needs review (…)` (log line) | Same as above, with the flags inline | Same |
| `holding <show>: flagged during packaging (…)` | Package built but audio verification flagged it | Inspect; `llama deliver --force` if acceptable |
| `refusing to deliver: … use --force` | Delivering a needs-review show | Inspect, then `--force` if intended |
| `FAILED <show>: …` | LLM/network failure mid-show | `llama run <run>` retries just the missing pieces; see `llm-failure.txt` |
| `FAILED <show>: …` (voice active) | TTS backend failed (bad key, rate limit, missing key — Voxtral needs `MISTRAL_API_KEY`, ElevenLabs needs `ELEVENLABS_API_KEY`) — show gets no package, batch continues | `llama redo <show> --from package` once the API issue clears; the segment cache means only the unfinished clips re-render |
| `note: already-packaged shows won't be re-voiced without --force …` | `llama run <run> --voice` on a run whose shows are already packaged is a no-op for them | `llama run <run> --stage package --force --voice`, or `llama redo <show> --from package --voice` for one show |
| `'x' is ambiguous` + a list | Substring matched several shows/runs | Use a longer substring or a full name from the list |
| `no show matches 'x'` / `no run matches 'x'` | Resolver found nothing | `llama status` / `llama runs` to see what exists |
| `no provenance.json in … - reprocess it via its run` | `redo` on a hand-built show with no provenance | Reprocess once via its run to write `provenance.json` |
| `No shows survived winnowing.` | Nothing passed dedup + mechanical floors + scoring | Broaden the query, lower floors, or check the ledger |
| `winnow: N of M scored shows fell below the quality floor` | LLM scores under `min_quality_score` (default 6.0) were dropped | Expected while a pool is healthy; if it recurs and runs come back short, the well is drying — broaden criteria, or lower `--min-score` if you'd rather ship marginal shows |
| `no matching artists found on the LMA` | Artist-less query matched nothing in the index | Name an artist or broaden the style terms |
| `winnow: sampling N of M survivors for review fetch` | More candidates than the review-fetch budget; the best-evidenced are scored, bounded by `artist_cap`/`year_cap` | Fine for most runs; raise `[winnow] max_metadata_fetch` in config to score more |
