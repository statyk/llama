# How llama works: the operator's guide

This is the user-facing map of `llama` — the acquisition half of a two-tool
system. `llama` finds, vets, researches, and packages shows, ending at
`llama deliver`; it never writes a DJ script or touches TTS. Voicing a
delivered package — script, speech, `broadcast.m3u` — is a **separate**
tool, `emcee`, that runs after delivery against the station's watched
folder; see [Voicing packages: emcee, a separate tool](#voicing-packages-emcee-a-separate-tool)
below for the handoff, and [docs/station-brief.md](station-brief.md) for
the full manifest contract both tools honor. This document covers what
llama's pipeline does, what lands on disk where, the two different human
gates and how they differ, every llama command, every review flag, and a
troubleshooting table from "message you saw" to "what to do next." The
design rationale lives in `docs/superpowers/specs/`; this document is about
*operating* it.

## The big picture

```
llama get "query"          llama get --profile <name>
        │                           │
        ▼                           ▼
   interpret ──► search ──► winnow ──► [gate 1: llama run approve]
                                              │
                              per approved show│
                                              ▼
             select-recording ──► gather ──► research ──► vet
                                              │
                            [gate 2: needs-review can halt here]
                                              │
                                       brief (always on)
                                              │
                                              ▼
                                          package ──► llama deliver
                                                            │
                                                            ▼
                                               (separate tool, station-side)
                                                        emcee run
                                            DJ script + TTS + broadcast.m3u
```

`llama pipeline` prints llama's half of this flow (plus the derived states and a redo
cheat-sheet) as a static teaching command — reach for it any time you want a
refresher without leaving the terminal.

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

There are two modes, both under the one `get` verb:

- **One-off:** `llama get "GD shows 73-74 with a china>rider"` — interprets
  the query, runs the whole pipeline.
- **Standing profiles:** `llama profile add` then `llama get --profile
  <name>` — a saved query re-run for recurring segments, deduplicated
  against the library and the history ledger so the same performance is
  never offered (or shipped) twice.

## The on-disk workspace

Everything lives under `~/.llama/` (configurable as `root` in
`~/.llama/config.toml`):

```
~/.llama/
├── config.toml                  # optional; see README
├── ledger.jsonl                 # broadcast history (dedup + audit)
├── cache/                       # archive.org responses + artist index
├── profiles/<name>.toml         # standing profiles
├── runs/<session-id>/            # session-level artifacts only
│   ├── criteria.json            # interpreted query (interpret stage)
│   ├── candidates.json          # every performance found (search stage)
│   ├── shortlist.json           # ranked + scored top shows (winnow stage)
│   ├── session.json             # lifecycle marker: awaiting-approval | complete
│   │                            # (missing/other = incomplete) — read by
│   │                            # `llama run list`/`status`'s attention-list
│   └── artists.json             # artist-less queries only: matched artists
└── shows/<slug>/                # canonical shows library: one dir per
    │                            # performance, slug = slugified performance id
    │                            # (gratefuldead-1973-06-10), shared across runs
    ├── provenance.json          # which run processed it, the profile name
    │                            # (if any), winnow dossier — what `redo`
    │                            # replays from
    ├── overrides.json           # hand-authored or `llama show`-edited, durable:
    │                            # excluded tracks, narration mode, and metadata
    │                            # corrections (venue/city/date/titles/set_breaks);
    │                            # read by gather/brief, survives every redo
    ├── selection.json           # which recording won and why
    ├── show.json                # tracks, sets, flags — THE show state file
    ├── reviews.json             # raw listener reviews
    ├── research.md              # deep-research output
    ├── vetting.json             # grounding-check results
    ├── briefing.md/.json        # neutral vetted briefing (always on) — brief stage
    ├── llm-failure.txt          # raw LLM output if a task failed validation
    └── package/                 # the deliverable llama hands to `llama deliver`
        ├── manifest.json        # schema v3: tracks, sets, durations, context,
        │                        # briefing, and null dj_notes/dj_audio blocks
        │                        # (emcee-written passthrough — llama never
        │                        # populates them)
        ├── playlist.m3u         # music-only play order
        ├── audio/               # verified, tagged tracks
        ├── research.md
        ├── reviews.md
        └── briefing.md/.json    # always present (manifest v3)
```

llama's package has no `dj-notes.md`, `dj-audio/`, or `broadcast.m3u` — those,
and the manifest's `dj_notes`/`dj_audio` content, are written station-side by
`emcee` **after** `llama deliver` copies this directory into the station's
watched folder; see
[Voicing packages: emcee, a separate tool](#voicing-packages-emcee-a-separate-tool)
below.

Session ids default to `YYYY-MM-DD-<slugified-query>` for a one-off `get`
and `YYYY-MM-DD-<profile-name>` for `get --profile`, with `-2`, `-3`, …
appended on same-day collisions (`--name` overrides it explicitly). Show
slugs come from the performance identity (artist + date), so they are
stable across runs by construction.

Three files deserve a callout:

- `show.json` carries `needs_review` and `review_flags`, and it is what
  gate 2 reads. When a show is held, this file says why.
- `provenance.json` is written every time a show is processed: which run
  caused it, the profile name it came from (if any — `package` stamps this
  into the manifest's `source.profile`, which emcee later reads to pick a
  presenter), and the winnow dossier and quality assessment. It is what
  lets `llama redo` re-run a show standalone — the originating run
  directory doesn't even need to exist anymore.
- `overrides.json` is the opposite of both: it is never written by a stage,
  only by you (via `llama show`), and it is never derived away. It holds
  excluded source filenames, the narration mode (`full`/`vague`), and
  metadata corrections — `venue`, `city`, `date`, `titles` (track number →
  forced title), and `set_breaks` (track numbers a break falls after,
  numbered sets only). `gather` reads the exclude/titles/venue/city/date/
  set_breaks fields; `brief` reads `narration` and stamps it onto its own
  output (the LLM's own opinion of it is never trusted); it survives every
  `redo`, including ones that drop everything else downstream of a stage.

## Names and states: the catalog

Every command that takes a show or session accepts a **name, a unique
substring, or a path**: exact match wins, otherwise a substring that
matches exactly one candidate resolves to it, otherwise the command fails
loudly and lists the matches. `llama show 1973-06-10` is the typical form;
`llama run resume countryish` resolves `2026-07-16-countryish`.

A show's **state** is never stored — it is derived from which artifacts
exist plus the ledger, so it cannot go stale:

| State | Derived from | Meaning |
|---|---|---|
| `held` | `show.json` has `needs_review: true` | Gate 2 hold; sorts first in `llama status`, flags shown inline |
| `delivered` | ledger has a `delivered` entry for the performance | Shipped to the station |
| `packaged` | `package/manifest.json` exists | Ready to deliver |
| `briefed` / `vetted` / `researched` / `gathered` / `selected` | deepest stage artifact present | In-flight (or abandoned mid-pipeline) |

`llama status` is the triage table over these states; `llama status
--by-run` summarizes per-session show counts. Both are in the command
reference below.

## The stages

| Stage | LLM? | Writes | What it does |
|---|---|---|---|
| interpret | yes | `criteria.json` | Query → structured criteria (artist, era, count, constraints) |
| discover | yes | `artists.json` | Artist-less queries only: match style against the LMA artist index |
| search | no | `candidates.json` | Wide-net archive.org search via the cursor-paginated scrape API — every matching recording, uncapped; groups recordings by performance identity (artist + date + venue). Complete recording lists matter downstream: siblings feed set-structure recovery and recording selection |
| winnow | yes ×2 | `shortlist.json` | Ledger dedup → mechanical floors (rating/review count, setlist constraints) → LLM review scoring → quality floor (`min_quality_score`, default 6.0: lower-scored shows are dropped with a warning, so a thinning pool comes back short and loud instead of quietly mediocre) → light web research on the top 12+. When survivors exceed the review-fetch budget (`[winnow] max_metadata_fetch`, default 40), it samples the best-evidenced, bounded by `artist_cap`/`year_cap`. The shortlist cut is best-score-first with per-artist share capped at `artist_cap` (default 1/3) and per-year share capped at `year_cap` (default 1.0 = off — scores decide the year mix); equal scores tie-break on review evidence, not date |
| select-recording | no | `selection.json` | Picks the best *recording* of the performance: lineage (SBD > MTX > AUD, era-overridable — early-80s GD inverts to MTX > AUD > SBD), ratings, completeness (scales the score: fragments lose to fuller tapes), and `[selection.tapers]` reputation bonuses (miller/seamons for GD; newest revision of a taper preferred), sibling-relative download popularity, and embedded-title coverage (both small tie-breaker-sized terms) |
| gather | maybe | `show.json`, `reviews.json` | Junk-filters files, resolves track titles (`sibling-format` tags recovered from a different-format copy → own tags → setlist → siblings), builds canonical set structure from all recordings + setlist.fm, aligns it onto tracks; LLM only as alignment/extraction fallback |
| research | yes | `research.md` | Deep web research on the specific performance |
| vet | yes | `vetting.json` | Extracts the research's factual claims; deterministic grounding check against the setlist and date |
| brief | yes | `briefing.*` | Neutral vetted briefing for scriptwriters — llama's sole text stage (always on, no flag/config gate) |
| package | no | `package/` | Downloads audio (md5-verified), tags it, checks durations, writes manifest v3 + m3u + digests (hard-fails if `briefing.*` is missing); stamps the manifest's `source.profile`; leaves `dj_notes`/`dj_audio` as `null` for emcee to fill in later |

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
across runs, and the history ledger's job is dedup, not rotation. Want no
artist repeated across your next N shows? Generate the N in one run.
Explicit `llama run approve` picks are never capped; your picks are your
picks.

## The two human gates (don't confuse them)

This is the single most confusing part of the system, so here it is plainly:

|  | Gate 1: shortlist approval | Gate 2: needs-review |
|---|---|---|
| **Question it asks** | "Which of these shows should we spend money processing?" | "Is this processed show clean enough to air?" |
| **Granularity** | The session's shortlist | One show |
| **Lives in** | `runs/<session>/shortlist.json` (`approved: true/false/null`) | `shows/<slug>/show.json` (`needs_review` + `review_flags`) |
| **Set by** | You (interactive prompt, or `llama run approve`) | The pipeline (gather/vet/brief/package flags) |
| **Cleared by** | `llama run approve <session>` | `llama fix`/`llama triage` (after you inspect) |
| **Surfaced by** | `llama run list` (the attention-list), also fronting `llama status` | `llama status --held` |
| **What it blocks** | Processing starting at all | Packaging (or delivery, if flagged during packaging) |

**Gate 1** appears interactively during `llama get` ("Process which
ranks?"), or — with `--plan`, or a `--human-gate` profile run with `--auto`
— as a parked session showing up in `llama run list`/`llama status`'s
attention-list with a `llama run approve <session-id>` hint. `llama run
approve` records your picks and then offers to process them on the spot;
decline and it prints the resume command (`llama run resume <session-id>`)
instead.

**Gate 2** fires per show, any time a stage records a review flag in
`show.json`. The pipeline checks it at three points (after vet, after brief,
after package) and prints `needs-review, skipped: <show>`
during first-time processing (`llama get`), or `still held: <show>` when a
`redo`/`fix`/`triage` re-run comes back held. The flags that can be
set, and by which stage:

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
| `briefing mentions unknown song` / `references nonexistent set` / claims the wrong set count / vague-narration violation (names songs or asserts set structure under `narration: vague`) / has no per-set talking points under `full` | brief | The briefing contradicts the setlist, the real set structure, or the vague-narration contract; retried once with feedback before holding |
| `duration mismatch on <file>` | package | Downloaded audio's real length disagrees with metadata |

(emcee's own scriptwriting has its own, separate factual guard — a bad DJ
script never holds a llama show, since llama never generates one; see
[Voicing packages: emcee, a separate tool](#voicing-packages-emcee-a-separate-tool).)

**Clearing gate 2.** There is deliberately no bypass anywhere else: a
flagged show stays held until `llama fix` or `llama triage` resolves it —
`llama deliver` has no hold override at all (§ below). Looking means
`llama show <show>` — strictly read-only: it prints the flags, state, a
table of which stage artifacts exist, the archive URL, and (if non-default)
the current `overrides.json`, plus a hint pointing at `llama fix <show>
--overrule` if it looks like a false alarm. From there you're choosing one
of three resolutions, either flag-by-flag with `llama fix <show> <flags>`
(auto-runs the correct redo) or interactively with `llama triage` (walks
every held show with an `[e]xclude / [m]etadata / [v]ague / [o]verrule /
[s]kip / [q]uit` prompt):

| Resolution | When | Do (`fix`) | Do (`triage`) | Clears the hold? |
|---|---|---|---|---|
| **Correct** | The flag is real and fixable — e.g. junk tracks slipped past the filter, a setlist source is missing, or the venue/date/a title/a set break is wrong | `llama fix <show> --exclude 9,10` (track numbers or filenames; `--unexclude` to undo one) or `--set-venue`/`--set-city`/`--set-date`/`--set-title N="..."`/`--set-breaks "9,17"` | `[e]xclude` or `[m]etadata` | No — a clean re-gather self-clears by producing structure with no flags |
| **Accept as vague** | The setlist genuinely can't be resolved, but the show is otherwise fine to air without naming songs | `llama fix <show> --narration vague` | `[v]ague` | Yes, immediately (narration mode also survives future redos) |
| **Overrule** | The flag is a false alarm | `llama fix <show> --overrule` | `[o]verrule` | Yes, immediately |

`llama show <show> --tracks` lists the numbered track table first if you
need the numbers for `--exclude`/`--set-breaks`/`--set-title`.

Each resolution edits `overrides.json` (except overrule, which only clears
`show.json`'s flags) and, on `fix`, runs the correct redo automatically —
`--no-run` stages the edit and prints `next: llama redo <show> --from
<stage>` instead, for batching several edits before one redo. Stage
precedence when multiple flags are combined on one `fix` call: an exclude
or metadata edit redoes from `gather`, a narration edit (with neither)
redoes from `brief` (regenerating the briefing and the package too), and
`--overrule` alone redoes from `package`.

## Voicing packages: emcee, a separate tool

llama's job ends at `llama deliver`: a delivered package has audio, a
manifest, and a neutral vetted briefing — no DJ script, no speech, no
`broadcast.m3u`. **llama has no `voice`/`presenter` command, no `[tts]`
config, and no `--script`/`--voice` flags anywhere** — that whole surface
moved to a separate CLI, `emcee` (dist `llama-emcee`), installed alongside
llama (`pip install -e packages/herder -e "packages/llama[dev]" -e
packages/emcee`) but run independently, station-side, against the folder
llama delivers into.

emcee scans `[station] root` (its own config, distinct from llama's — see
`emcee config init`) for delivered packages and works the ones that aren't
yet broadcast-ready — "not broadcast-ready" *is* the work predicate, there's
no separate queue file to fall out of sync:

- `emcee run` — voice every pending package in the station in one sweep.
- `emcee voice <package-path>` — script + voice + assemble one package
  directly (`--fresh <clip-stem>` deletes just one cached clip, e.g.
  `set1-intro` or `99-outro`, so *that* clip re-renders — but emcee
  re-scripts on every call, and with a real LLM the regenerated text
  usually changes every clip's cache key too, so in practice `--fresh`
  normally re-renders the whole show anyway, not just the named clip;
  `--force` re-synthesizes every clip unconditionally).
- `emcee status` — a table of every package's state (`ready` / `pending` /
  `unsupported` for a pre-v3 manifest, which needs re-delivering from
  llama, not upgrading in place).

For each pending package, emcee writes a DJ script (its own scriptwrite LLM
task, factually guarded against that package's manifest — persona-styled
when a **presenter** is assigned, neutral otherwise), synthesizes it via
TTS (hosted Mistral Voxtral by default, ElevenLabs an opt-in alternative;
same per-segment caching, sentence-level `[tts] chunk`, and instrumental
`[tts] bed` mixing this feature used to have when it lived in llama), and
assembles `broadcast.m3u` — writing `dj-notes.md`, `dj-audio/`, and
`broadcast.m3u` straight into the delivered package directory, and
rewriting the manifest's `dj_notes`/`dj_audio` blocks (which llama left
`null`) in place. See [docs/station-brief.md](station-brief.md) for the
exact package contract both tools honor.

**Presenters and assignment.** A **presenter** is a reusable on-air host —
TTS voice + authored character — created with `emcee presenter add <id>
--name NAME --sex SEX (--voice ID | --voice-clone WAV) --character "..."`
or by hand in `presenters/<id>.toml` (same shape llama's presenters used to
have: `name`/`sex`/`character` + exactly one of `voice`/`voice_clone`, plus
an optional `bed` override). emcee decides *which* presenter voices *which*
package via its `[assign]` config, keyed off the llama profile name
stamped at `manifest["source"]["profile"]` (llama's `package` stage stamps
this on every show; a one-off `llama get` with no `--profile` stamps
`null`, which falls through to `[assign] default`):

```
[assign]
default = "waldo"

[assign.profiles.prime-dead]
presenter = "waldo"
title = "The Primal Dead Hour"
```

No entry for a profile falls back to `[assign] default`'s presenter with no
title. This is the entire handoff — llama never needs to know a presenter
exists, and emcee never needs to know how the show was acquired.

**Single-writer station, no lock.** emcee assumes exactly one `emcee run`
(or `emcee voice`) at a time against a given station root — it takes **no
lock**, unlike llama's flock-based workspace (see "Running several jobs at
once" in the [README](../README.md#use)). Two llama processes can safely
share `~/.llama/` concurrently; two `emcee run`s against the
same station root cannot safely run at once. No single file is left
half-written either way — every write in both tools is unique-temp-file-
plus-atomic-rename — but an overlapping `emcee run` will find the same
pending package twice and voice it twice: run A's `dj-notes.md` can end up
next to run B's manifest `dj_notes` block and B's clips, leaving the
package internally inconsistent, and it still **doubles LLM/TTS spend** for
no benefit. Run `emcee run` from one place (a single cron entry, one
operator), not fanned out.

Full emcee usage (all flags, config, and presenter management) is in the
project [README](../README.md#emcee-voicing-delivered-packages); this
section only covers the llama-side handoff.

## Command reference

In every command below, `<show>` and `<session>` mean "name, unique
substring, or path" — see [Names and states](#names-and-states-the-catalog).

### The shared selector vocabulary

`status`, `triage`, `redo`, `deliver`, and `rm` all accept the same
filter flags, reconciled by one implementation (`llama.cli_select`):

```
--held                 selector: shows in state held
--packaged             selector: packaged, undelivered shows
--state NAME           selector: one derived state (repeatable; validated
                       enum: held|selected|gathered|researched|vetted|
                       briefed|packaged|delivered)
--artist SUBSTR        selector: case-insensitive substring on artist
--run NAME             selector: shows processed by this session
```

All filters AND together; repeated `--state` values OR together. A
positional show name and any selector flag are mutually exclusive ("give a
show OR selectors, not both"). Neither given is an error naming an example
selector, except `status` (defaults to every show) and `triage` (defaults
to `--held`). A batch action (`triage`/`redo`/`deliver`/`rm`) prints
a plan and asks `Proceed? [y/N]` (`--yes` skips); per-show failures print
`FAILED <slug>: …` and the sweep continues.

**The held opt-in rule:** for an *acting* command (`triage`, `redo`,
`deliver`, `rm` — not the read-only `status`/`show`), a selector's
matches in state `held` are dropped unless the selector explicitly included
held (`--held` or `--state held`); when any are dropped the plan prints
`note: N held show(s) excluded (add --held to include them)`. `triage`'s
default selector *is* held, so no opt-in applies there. Naming a single
show positionally is itself explicit opt-in — `redo gd73 --from gather` on
a held show runs (that's how holds self-clear); `deliver gd73` on a held
show reaches the per-show gate and is refused there with the reason.

### `llama get "query" [--limit N] [--auto] [--plan] [--name NAME] [--artist-cap F] [--min-score F] [--year-cap F] [--full-rationale]`
### `llama get --profile NAME [--auto] [--plan] [--full-rationale]`
One verb replaces `find` + `profile run`; honest that it spends. Exactly
one of `"query"` / `--profile` is required.

- **Query mode** interprets the query, prunes artist-less matches
  interactively (discovery path), searches, winnows, prints the shortlist,
  and prompts which ranks to process (empty answer = top picks); `--auto`
  skips all prompts and takes the top-ranked shows. Winnow
  knobs: `--artist-cap`, `--year-cap`, `--min-score` (see the winnow
  discussion above). `--full-rationale` prints each shortlisted show's
  complete selection rationale instead of the first few lines (also
  available on `run approve`/`run resume`). Query-mode-only flags error on
  profile mode ("set these on the profile"). There is no `--script`/
  `--voice` here — llama always writes a briefing and never a DJ script;
  voicing is `emcee`'s job, after delivery.
- **Profile mode** (`--profile NAME`) loads the profile and runs it as a new
  session, stamping its count and profile name (read from the manifest's
  `source.profile` by emcee's `[assign]` config); only `--auto`,
  `--plan`, `--full-rationale` apply.
- **`--plan`** stops after the shortlist prints — winnow's LLM scoring and
  light research still spend (that's what produces the shortlist), but
  nothing is downloaded, researched further, or packaged. The session parks
  `awaiting-approval` and llama prints:

  ```
  shortlist ready — nothing processed.
  to approve & process:  llama run approve <session-id>
  to discard:            llama run rm <session-id>
  ```

  `--plan` composes with `--auto` (`--auto --plan` = "spend on winnow,
  never prompt, park it").
- `--name` gives the session an explicit id instead of the auto-unique
  `YYYY-MM-DD-<slug>` (mainly for tests/scripting).
- The winnow pool now also excludes every show already in the library, not
  just the ledger (§ [Dedup](#dedup-library--history) below).

### `llama artists ["query"] [--limit N] [--include-junk] [--min-recordings N] [--min-downloads N] [--refresh]`
Search the LMA artist index with a natural-language query, or with no query
list the deepest catalogs. `--include-junk` skips the junk-filter floors
entirely (`--min-recordings`/`--min-downloads` override them instead).

This is the **test-drive** for a `get`/profile query: it calls the same LLM
matcher on the same request text with the same budget (20; `[artists]
max_matched` in config governs the pipeline side), so its list previews what
a run would search. The matcher is still an LLM — two calls can rank
differently — so when you've settled on a roster, pin it (`profile
artists --set`) and runs stop consulting the matcher at all.

### `llama status [SELECTOR] [--all] [--by-run] [--json]`
Global triage view: the session **attention-list** first, then the show
table. Read-only — never prompts, never writes.

- **Attention-list:** whenever any session is awaiting approval or
  incomplete, prints before the show table:

  ```
  sessions needing attention:
    2026-07-27-sunday-dead-hour-2       awaiting approval   llama run approve sunday-dead-hour-2
    2026-07-27-china-rider              incomplete          llama run resume china-rider
  ```

  Complete sessions never appear. In `--json` this becomes the `sessions`
  key alongside `shows` (or `runs` with `--by-run`).
- **Selectors:** the shared vocabulary above (read-only class — no held
  opt-in needed; every show is shown). `--all` includes every delivered
  show instead of the recent-5 tail.
- **`--by-run`** replaces the deleted `runs` command: one row per session —
  id, per-state show counts, query. Exclusive with selectors/`--all`.
- Show rows: state, artist, date, session, held-for-review first, flags
  indented beneath; inline annotations for anything non-default
  (`[vague, 3x-excl]`). llama's `status` has no `voiced`/`broadcast-ready`
  concept — packaging (llama's job) and voicing (emcee's job) are now
  reported by two separate tools; see `emcee status` for a package's
  ready/pending state.

### `llama show <show> [--tracks] [--json]`
Inspect one show. **Strictly read-only — never prompts, never edits.** Use
`llama fix` to edit overrides or resolve a hold, and `llama triage` for the
interactive walkthrough.

Prints artist/date/venue, the chosen recording **with its archive.org URL**,
a `considered:` block of every other recording weighed (identifier + score,
descending — omitted when there was only one candidate), derived state, a
table of stage artifacts (present + age, or missing), the current
`overrides:` line (only shown when non-default), and the needs-review
flags. On a held show it also prints `to overrule after inspecting: llama
fix <slug> --overrule`. `--tracks` appends the numbered track table (index,
set, title, title source, duration, filename) — the numbers `fix`'s
`--exclude`/`--set-title`/`--set-breaks` take. `--json` emits the full
machine-readable record (`archive_url`, `considered`, `stages`, `overrides`,
etc.). A show that hasn't reached `gather` yet (state `selected`) still
prints what exists instead of erroring. There is no broadcast-ready line
here — that check moved to `emcee status`/`emcee voice`, which look at the
*delivered* package, not the workspace show.

### `llama pipeline`
Teaching command: prints the stage flow with both gates marked, the eight
derived `--state` values, and a redo cheat-sheet (which `fix` flag redoes
from which stage). Static text, read-only — no config, no I/O, never
prompts, never writes. Reach for it as a refresher any time.

### `llama triage [<show>|SELECTOR]`
The interactive resolution walkthrough — always interactive, requires a
TTY (`triage is interactive; use status/show for scripted reads` off a
TTY). Default selector `--held`; a broader selector walks held shows for
resolution and just prints-and-skips non-held matches. Per held show,
prints the full inspection block (as `show <name>`, including the archive
URL) then prompts:

```
[e]xclude tracks / [m]etadata / [v]ague / [o]verrule / [s]kip / [q]uit
```

- **`[e]xclude`** — numbered track list, pick indices to add to
  `overrides.exclude`, redo from `gather`.
- **`[m]etadata`** — a mini-editor over `venue`, `city`, `date
  (YYYY-MM-DD)`, `title overrides (N=Title, comma-separated)`, `set breaks
  after tracks (e.g. 9,17)` — each shows the current effective value, empty
  input keeps it; any change writes the overrides and redoes from `gather`.
- **`[v]ague`** — sets `overrides.narration = "vague"`, clears the hold,
  redoes from `brief` (regenerating the briefing, any script, and the
  package too).
- **`[o]verrule`** — clears the hold, redoes from `package`.
- **`[s]kip`** / **`[q]uit`** — next show / stop the walk.

After each action it reports `packaged: <path>` or `still held: <slug>`
before advancing to the next show.

### `llama fix <show> <edit-flags...> [--no-run]`
The flag-driven editor for `overrides.json` and hold resolution — **runs
the correct redo automatically** by default (earliest-affected stage wins
when flags are combined: `gather` < `brief` < `package`); `--no-run`
stages the edit and prints `staged; next: llama redo <show> --from <stage>`
instead, for batching several edits before one redo. At least one flag is
required (bare `fix <show>` errors, pointing at `show`/`triage`). Works on
non-held shows too — overrides are general inputs, not hold-only.

| Flag | Effect | Redo stage |
|---|---|---|
| `--exclude FILE\|N` (repeatable, comma groups) | add to `overrides.exclude` (filename or track number) | gather |
| `--unexclude FILE\|N` | remove from `overrides.exclude` | gather |
| `--set-venue V` / `--set-city C` / `--set-date YYYY-MM-DD` | force the field | gather |
| `--set-title N="Song"` / `--clear-title N` | force/drop a track title | gather |
| `--set-breaks "9,17"` / `--clear-set-breaks` | force/drop set breaks (the track numbers a break falls *after*; numbered-sets-only) | gather |
| `--narration vague\|full` | set `overrides.narration`; `vague` also clears the hold | brief |
| `--overrule` | clear `needs_review`/`review_flags`: "I've reviewed it, ship it" | package |

Excludes/metadata do **not** pre-clear a hold (the re-gather decides,
self-clearing only if the derivation comes out clean); `--narration vague`
and `--overrule` clear immediately. On a jerrybase-covered (Garcia-universe)
show, `--set-breaks` still runs the jerrybase cross-checks against your
breaks (closer tripwire, set-count guard), so a manual break that
contradicts jerrybase can still raise a flag rather than self-clearing.
`--overrule` on a non-held show is a no-op + note. Single-show only — bulk
blind edits to per-show overrides are a foot-gun, so batch resolution is
`triage`, not `fix`.

### `llama redo <show> | --run SESSION | SELECTOR --from STAGE [--redo-research] [--yes]`
The single re-execution verb. `--from` is required. Three addressing forms
(exactly one):

1. **Single show:** `llama redo <show> --from STAGE` — drops that stage's
   artifacts and everything downstream, then re-runs the tail using
   `provenance.json` (candidate, winnow dossier) — the originating session
   doesn't need to exist anymore. Stage ∈
   `select | gather | research | vet | brief | package`. A
   show without `provenance.json` errors — reprocess it via its session
   once.
2. **Selector batch:** `llama redo SELECTOR --from STAGE` — shared
   vocabulary above, acting class (held opt-in), plan + confirm + per-show
   `FAILED <slug>: …` isolation.
3. **Session scope (`--run`, the new home for the old whole-run force):**
   `llama redo --run <session> --from STAGE`.
   - `STAGE ∈ {search, winnow}` (valid **only** with `--run`): rebuilds the
     session's shortlist from that stage — deletes the stale downstream
     artifacts (`candidates.json`+`shortlist.json` for `search`,
     `shortlist.json` for `winnow`), then replays `get`'s processing tail
     with the session's own criteria. If the doomed shortlist carries
     approvals, confirms first ("this rebuilds the shortlist and discards
     the approvals recorded on it"). This is the old `run --stage X --force`
     for the whole run.
   - Any show-level stage: batch-redo the session's shows — identical to
     the selector form with `--run` as the only filter.

`--redo-research` (renamed from `--with-research`, which *sounded* additive
but deletes `research.md`) also drops research when redoing from
`select`/`gather` — kept by default otherwise (it's the expensive
performance-level call; vet's grounding check is the safety net if a
structural fix leaves it slightly stale). Result per show: `packaged:
<path>` or `still held: <slug>`. There is no `--script`/`--voice` here —
re-voicing a *delivered* package (if you want a different DJ take) is
`emcee voice <package-path>`, not a llama `redo`.

### `llama deliver <show> | SELECTOR [--dest DIR] [--yes]`
Copies a show's `package/` into the station's watched folder
(`delivery_path` from config, or `--dest`) and records a `delivered`
history row.

**Requires a clean package** (packaged, file-complete, not held for
review). None of these three legs is overridable — there is no
`--allow-unvoiced` and no `--force`; voicing isn't llama's concern
anymore, so it isn't part of llama's delivery gate at all (that's
`emcee status`'s ready/pending distinction, checked station-side, after
delivery). Held shows and shows with missing audio files must be resolved
first — `fix`/`triage` for a hold, `redo --from package` for missing
audio. Refusals print the failing reasons and a pointer, e.g. `refusing to
deliver <slug>: held for review — resolve with llama triage`.

- **Single-show form:** `llama deliver <show> ...`.
- **Batch form:** the shared selector vocabulary. `llama deliver --packaged`
  is the ship-everything-ready sweep. Same plan/`Proceed? [y/N]`/
  `--yes`, same held-opt-in rule, same per-show `FAILED <slug>: …`
  isolation.
- `llama status --packaged` (or `llama deliver --packaged` itself, before
  confirming) lists what's ready to deliver.

### `llama rm <show> | SELECTOR [--forget | --suppress] [--yes]`
Deletes `shows/<slug>/` — the one irreversible local operation, so it
confirms by default (`--yes` skips). Leaves history in an intentional,
*stated* state rather than a stale row:

| Mode | Ledger effect | Net effect |
|---|---|---|
| default (no flag) | untouched | held/pre-package show (no ledger row): **re-eligible**. Packaged/delivered show: **stays excluded** (history dedup) |
| `--forget` | purge all history rows for this performance | fully re-eligible, a clean slate |
| `--suppress` | additionally append a `rejected` row (`run="manual"`) | guaranteed out, reversibly (`llama unsuppress`) — the only way to keep a *held* show (which has no keep-out row) from returning |

Echoes what it did to history, e.g. `removed shows/gd1972-08-27 — no
history rows; this show can be re-offered` / `… — history kept (selected,
delivered): stays excluded from future gets` / `… — forgot 2 history rows:
re-eligible` / `… — suppressed: will not be offered again (undo: llama
unsuppress …)`. Selector form: shared vocabulary, acting class (`rm --held`
is the legitimate "purge my junk holds" sweep, and must be spelled
explicitly). Delivered copies already at the station are out of scope —
`rm` only touches the workspace.

### `llama suppress <show-or-performance-id>` / `llama unsuppress <show-or-performance-id>`
The standalone deliberate reject / undo. `suppress` appends a `rejected`
history row (repeats are harmless); the show, if on disk, is left
untouched. `unsuppress` removes this performance's `rejected` rows only
(0 removed is a clean no-op message). Both resolve an on-disk show like
other acting commands, or accept a raw performance id
(`collection/date[/eN]`) for a performance that isn't (or is no longer) on
disk — the only way to keep "never offer me this again" usable for shows
long gone. No confirmation prompts (reversible by construction).

### `llama config init [--stdout] [--config PATH]`
Seed `~/.llama/config.toml` (or `--config PATH`) with the baked-in
defaults as a fully-commented TOML file. Refuses to overwrite an existing
file; `--stdout` prints the template instead. Exists because config
values **replace** defaults rather than merging: any
`[selection.tapers.*]` or `[[selection.lineage_eras]]` you add replaces
the built-in GD tuning unless the defaults are restated — which the
seeded file does for you. (This is the one `--config` that means *target
file to write*, not *config to load* — the app-wide `llama --config PATH
<command>` spelling is unaffected.)

### `llama run list [--json]`
The session **attention-list**: sessions awaiting approval or incomplete,
newest first (complete sessions never show here — their dirs remain on
disk harmlessly). Columns: session id, state, age (from the
`session.json` marker, else dir mtime), criteria (`profile: <name>` or the
truncated query).

### `llama run approve <session> [--full-rationale]`
Gate 1: prints the session's persisted shortlist, prompts `Approve which
ranks?` (unnamed ranks stay undecided), then confirms `Process approved
shows now? [Y/n]`. Declining keeps `awaiting-approval` and prints `next:
llama run resume <session-id>`. The shortlist approval **persists**
(winnow is non-deterministic — a deferred approval must approve the exact
list shown).

### `llama run resume <session> [--auto/--interactive] [--full-rationale]`
Resume a crashed or incomplete session from its artifacts — stages skip
work already done. To force a stage re-run (run-wide or per-show), use
`llama redo --run` instead; there's no `--stage`/`--force` here anymore.
Defaults to `--auto` (no prompts).

### `llama run rm <session> [--yes]`
Discard a session directory (`runs/<id>/`, after a y/N confirmation showing
the id and state). Shows it already processed are untouched — they live in
`shows/` and carry `provenance.json`; sessions have no ledger history of
their own.

### `llama profile add <name> "query" [--count N] [--human-gate] [--artist-cap F] [--min-score F] [--year-cap F] [--artists "..."]`
Interprets the query once and saves it as a standing profile.
`--human-gate` makes `get --profile --auto` stop at gate 1 instead of
self-approving. `--artist-cap`/`--min-score`/`--year-cap` set this
profile's own winnow knobs (same meaning as `get`'s, see the winnow
discussion above). `--artists "Galactic, Lettuce, ..."` pins the roster:
names resolve against the artist index at add time (typos and ambiguity
fail immediately), and every run of the profile searches exactly those
artists — deterministic, no LLM matching, no prune prompt. Edit the
`artists` list under `[criteria]` in the profile TOML to change it later.
There is no `--presenter`/`--title`/`--no-script` here — a profile has no
opinion about voicing; a llama profile's *name* is all emcee needs (its
`[assign]` config maps that name to a presenter and on-air title, see
[Voicing packages](#voicing-packages-emcee-a-separate-tool) above).

### `llama profile list`
One line per profile: name, count, query (truncated).

### `llama profile show <name>`
Inspect one profile's fields — query, count, human_gate, pinned roster,
and the interpreted criteria highlights. Strictly read-only — never
prompts, never edits, no LLM call.

### `llama profile remove <name> [--yes]`
Delete `profiles/<name>.toml` with a y/N confirmation. Sessions and shows
already created are untouched.

### `llama profile artists <name> [--set "A, B, C"]`
View or re-pin a profile's pinned artist roster — the same `artists` list
under `[criteria]` in the profile TOML that `profile add --artists` writes.
With no `--set`, prints the current roster, or "no pinned roster (uses the
LLM matcher)" if unpinned. `--set "Galactic, Lettuce, Soulive"` resolves
each name against the local artist index (typos or ambiguity fail loudly,
same as `profile add --artists`) and re-pins it; `--set ""` clears the pin,
reverting future runs of the profile to the LLM artist matcher.

There is no `llama presenter` command — presenters, and the config that
assigns them, are entirely emcee's: `emcee presenter add/list/show/remove`
manages `presenters/<id>.toml`, station-side. See
[Voicing packages: emcee, a separate tool](#voicing-packages-emcee-a-separate-tool)
above.

### `llama history list [--log] [--json]`
Dispositions for shows no longer on disk — the library covers what's on
disk. Renamed from `ledger`; `add`/`remove` are gone (`suppress` covers
reject, `unsuppress`/`rm --forget` cover removal). Default: one row per
performance, its latest disposition:

```
2026-07-25  delivered  GratefulDead/1977-06-09      (2026-07-20-china-rider)
2026-07-26  rejected   DelMcCouryBand/2003-04-19    (manual)
```

`--log` prints the full append-only trail instead. `--json` emits the
corresponding rows.

## Dedup: library ∪ history

A performance is excluded from future `get`s if it's **in the library**
(any show currently on disk, in any state — held, mid-pipeline, packaged,
delivered) **or** it has a `played`/`delivered`/`rejected` row in the
history ledger. This closes a gap the old ledger-only check had: a held
show (no ledger row until it clears both gates) used to re-surface in every
future run. `redo`/`fix`/`triage`/`deliver`/`rm` don't run winnow,
so none of them are affected — only `get` and a `redo --run --from
search|winnow` re-winnow. Gone from *both* the library and the ledger (the
`rm` default for a held show) is genuinely re-eligible — that's deliberate.

## Recipes

**What's the state of everything? / What came in overnight?**
`llama status` — the attention-list first (sessions awaiting approval or
incomplete), then held shows with their flags, then packaged (ready to
deliver), then in-flight. `llama status --packaged` is the ship-it
worklist; `llama deliver <show>` each one (or `llama deliver --packaged` to
ship the whole worklist at once).

**What's actually ready to go on air right now?**
`llama status --packaged` only means `package/manifest.json` exists in
llama's workspace — llama has no broadcast-ready concept anymore (voicing
moved to emcee, so llama's delivery gate doesn't ask about it). Once a
package is delivered, `emcee status` answers the airable question
station-side: `ready` (scripted, voiced, has `broadcast.m3u`) vs.
`pending`.

**Clear my overnight holds.**
`llama triage` — walks every held show one at a time with the interactive
prompt (`[e]xclude tracks / [m]etadata / [v]ague / [o]verrule / [s]kip /
[q]uit`), resolving and re-processing each one on the spot as you answer.
`s` to leave one for later, `q` to stop the walk early.

**A run printed `needs-review, skipped` for a show I want.**
`llama show <show>` to read the flags (strictly read-only). If a flag is a
false alarm, `llama fix <show> --overrule`. If it's real (e.g. unresolved
titles), fix the cause with the matching `llama fix` flag (it auto-runs the
redo) — see the three resolutions in
[Clearing gate 2](#the-two-human-gates-dont-confuse-them) above, or drive
it interactively with `llama triage`.

**This show has junk announcement tracks.**
`llama show <show> --tracks` to see the numbered track list, then `llama
fix <show> --exclude 9,10` (track numbers or filenames both work,
comma-lists ok, repeatable too) — adds them to `overrides.exclude` and
re-gathers immediately; gather drops them with reason `operator-excluded`
and warns if an entry doesn't match any source file. A clean re-gather with
the junk gone self-clears the hold.

**Wrong venue, city, date, a track title, or where a set break falls.**
`llama fix <show> --set-venue "Winterland" --set-city "San Francisco, CA"
--set-date 1973-06-10 --set-title 4="Dark Star" --set-breaks "9,17"` — give
only the flags you need; each forces the matching `overrides.json` field
and (once, for the combined edit) re-gathers. `--clear-title N` drops one
forced title, `--clear-set-breaks` drops the forced break list.
`--set-breaks` takes the track numbers a break falls *after*,
numbered-sets-only (no way to name an encore this way). Same self-clearing
rule as excludes: a clean re-gather drops the hold on its own.

**This show's setlist is unknowable.**
`llama fix <show> --narration vague` — sets `overrides.narration =
"vague"`, clears the hold, and redoes from `brief` immediately (regenerating
the briefing and the package); the briefing names no songs and asserts no
set structure, but is otherwise normal. Any script emcee later writes from
it inherits the same constraint.

**I ran `get --plan` (or a human-gate profile) — now what?**
`llama run list` (or `llama status`) shows it in the attention-list with a
`llama run approve <session-id>` hint. Approve, say yes when it offers to
process, or `llama run resume <session-id>` later if you decline.

**A stage failed with an LLM error.**
The raw output is in `shows/<slug>/llm-failure.txt`. Just
`llama run resume <session>` — completed stages are skipped, the failed one
retries.

**I want a different recording of the same show.**
`llama redo <show> --from select` — the drop cascades, so gather through
package rebuild from the newly picked recording. `research.md` is kept
(it's about the performance, not the recording); add `--redo-research` if
you want it redone too.

**Re-research a show.**
`llama redo <show> --from research` — this also deletes `vetting.json`,
so the new research gets re-vetted.

**I want to voice a delivered-but-silent package, or give it a new host.**
None of this is llama's job anymore — once `llama deliver` hands a package
off, voicing it is `emcee`'s: `emcee run` sweeps every not-yet-voiced
package in the station; `emcee voice <package-path>` does one directly
(`--fresh <clip-stem>` re-rolls just one clip *in principle* — in
practice emcee re-scripts every call, and a real LLM's regenerated text
usually invalidates every clip's cache, so expect the whole show to
re-render, not just the named clip). Presenters
(`emcee presenter add/list/show/remove`) and the profile→presenter mapping
(`[assign]` in emcee's own config) live entirely station-side — see
[Voicing packages: emcee, a separate tool](#voicing-packages-emcee-a-separate-tool)
above for the full handoff.

**Re-pin a profile's artist roster.**
`llama profile artists funky --set "Galactic, Lettuce, Soulive"` resolves
and re-pins the roster (typos/ambiguity fail loudly, same as `profile add
--artists`); `llama profile artists funky` alone shows the current roster;
`--set ""` clears it back to the LLM matcher.

**The same show keeps coming back in every `get`.**
It's neither in the library nor the history ledger. Deliver it, or `llama
suppress <performance-id>` to reject it without touching disk (works even
for a show that's no longer on disk, given a raw `collection/date[/eN]`
id).

**A search or winnow decision looks wrong (session-level, not one show).**
`llama redo --run <session> --from winnow` rebuilds the shortlist
(confirming first if approvals would be lost); `--from search` re-searches
and drops the shortlist with it.

**I want to clean up a stale or abandoned session.**
`llama run list` to see what's awaiting attention; `llama run rm <session>`
discards the session directory (shows it already processed live on in
`shows/`, untouched).

## Troubleshooting: message → meaning → action

| You see | It means | Do |
|---|---|---|
| `shortlist ready — nothing processed.` (`get --plan`) | Session parked awaiting approval | `llama run approve <session-id>`, or `llama run rm <session-id>` to discard |
| `sessions needing attention:` (on `status`/`run list`) | A session is awaiting approval or incomplete | Follow the printed `llama run approve`/`llama run resume` hint |
| `needs-review, skipped: <show>` | Gate 2: a flag was set during first-time processing | `llama show <show>` to read the flags; `llama fix <show> --overrule` if a false alarm, or the matching `fix` flag if real, or `llama triage` interactively |
| `still held: <slug>` (from `redo`/`fix`/`triage`) | Gate 2: the show came back held after a re-run | Same as above |
| `skipping <show>: needs review (…)` (log line) | Same as above, with the flags inline | Same |
| `holding <show>: flagged during packaging (…)` | Package built but audio verification flagged it | `llama show <show>`; `llama fix <show> --overrule` if acceptable |
| `refusing to deliver <slug>: held for review — resolve with llama triage` | Delivering a held show | `llama triage`/`llama fix <slug> --overrule`, then `llama deliver` again — there is no delivery-time override |
| `FAILED <show>: …` | LLM/network failure mid-show | `llama run resume <session>` retries just the missing pieces; see `llm-failure.txt` |
| `'x' is ambiguous` + a list | Substring matched several shows/sessions | Use a longer substring or a full name from the list |
| `no show matches 'x'` / `no session matches 'x'` | Resolver found nothing | `llama status` / `llama run list` (or `llama status --by-run`) to see what exists |
| `no provenance.json in … - reprocess it via its run` | `redo` on a hand-built show with no provenance | Reprocess once via its session to write `provenance.json` |
| `No shows survived winnowing.` | Nothing passed dedup + mechanical floors + scoring | Broaden the query, lower floors, or check the library/history |
| `winnow: N candidates -> M after library+ledger -> K after mechanical` | Dedup + mechanical-floor progression | Informational; a big drop at the first arrow means most candidates are already on disk or in history |
| `winnow: N of M scored shows fell below the quality floor` | LLM scores under `min_quality_score` (default 6.0) were dropped | Expected while a pool is healthy; if it recurs and runs come back short, the well is drying — broaden criteria, or lower `--min-score` if you'd rather ship marginal shows |
| `no matching artists found on the LMA` | Artist-less query matched nothing in the index | Name an artist or broaden the style terms |
| `winnow: sampling N of M survivors for review fetch` | More candidates than the review-fetch budget; the best-evidenced are scored, bounded by `artist_cap`/`year_cap` | Fine for most runs; raise `[winnow] max_metadata_fetch` in config to score more |
