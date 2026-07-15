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
                                  synthesize (opt-in --script)
                                              │
                                              ▼
                                          package ──► llama deliver
```

Every stage reads and writes plain files in a per-run directory under
`~/.llama/runs/`. Stages **skip work whose output file already exists**, so any
command that touches a run is cheap to re-execute — this is the core mechanic
behind resuming, and behind most of the answers in this guide.

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
└── runs/<run-name>/             # one directory per run
    ├── criteria.json            # interpreted query (interpret stage)
    ├── candidates.json          # every performance found (search stage)
    ├── shortlist.json           # ranked + scored top shows (winnow stage)
    ├── artists.json             # artist-less queries only: matched artists
    └── shows/<artist-date>/     # one directory per processed show
        ├── selection.json       # which recording won and why
        ├── show.json            # tracks, sets, flags — THE show state file
        ├── reviews.json         # raw listener reviews
        ├── research.md          # deep-research output
        ├── vetting.json         # grounding-check results
        ├── dj-notes.md/.json    # verbatim DJ script (only with --script)
        ├── llm-failure.txt      # raw LLM output if a task failed validation
        └── package/             # the deliverable
            ├── manifest.json    # schema v2: tracks, sets, durations, context
            ├── playlist.m3u
            ├── audio/           # verified, tagged tracks
            ├── research.md
            ├── reviews.md
            └── dj-notes.md      # only with --script
```

Run names default to `YYYY-MM-DD-<slugified-query>` for `find` and
`YYYY-MM-DD-<profile-name>` for profiles.

`show.json` deserves a callout: it carries `needs_review` and `review_flags`,
and it is what gate 2 reads. When a show is held, this file says why.

## The stages

| Stage | LLM? | Writes | What it does |
|---|---|---|---|
| interpret | yes | `criteria.json` | Query → structured criteria (artist, era, count, constraints) |
| discover | yes | `artists.json` | Artist-less queries only: match style against the LMA artist index |
| search | no | `candidates.json` | Wide-net archive.org search; groups recordings by performance identity (artist + date + venue) |
| winnow | yes ×2 | `shortlist.json` | Ledger dedup → mechanical floors (rating/review count, setlist constraints) → LLM review scoring → light web research on the top 12+ |
| select-recording | no | `selection.json` | Picks the best *recording* of the performance (lineage, track completeness) |
| gather | maybe | `show.json`, `reviews.json` | Junk-filters files, resolves track titles (tags → setlist → siblings), builds canonical set structure from all recordings + setlist.fm, aligns it onto tracks; LLM only as alignment/extraction fallback |
| research | yes | `research.md` | Deep web research on the specific performance |
| vet | yes | `vetting.json` | Extracts the research's factual claims; deterministic grounding check against the setlist and date |
| synthesize | yes | `dj-notes.*` | Opt-in (`--script`): verbatim DJ script, factually guarded against the manifest |
| package | no | `package/` | Downloads audio (md5-verified), tags it, checks durations, writes manifest v2 + m3u + digests |

Winnow's philosophy: the LMA archives everything, so mere presence means
nothing, and LMA reviews skew toward people who attended the show. The
scoring prompt demands merit-based praise, and light research looks for the
show's reputation *outside* the archive.

## The two human gates (don't confuse them)

This is the single most confusing part of the system, so here it is plainly:

|  | Gate 1: shortlist approval | Gate 2: needs-review |
|---|---|---|
| **Question it asks** | "Which of these shows should we spend money processing?" | "Is this processed show clean enough to air?" |
| **Granularity** | The run's shortlist | One show |
| **Lives in** | `shortlist.json` (`approved: true/false/null`) | `shows/<show>/show.json` (`needs_review` + `review_flags`) |
| **Set by** | You (interactive prompt, or `llama review`) | The pipeline (gather/vet/synthesize/package flags) |
| **Cleared by** | `llama review <run-dir>` | `llama show <show-dir> --clear` (after you inspect) |
| **What it blocks** | Processing starting at all | Packaging (or delivery, if flagged during packaging) |

**Gate 1** appears interactively during `llama find` ("Process which
ranks?"), or — for a `--human-gate` profile run with `--auto` — as the printed
message `Shortlist awaits review: llama review <run-dir>`. `llama review`
records your picks and then offers to process them on the spot; decline and
it prints the resume command (`llama run <run-dir>`) instead.

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
| `single-set structure for a long show` | gather | 100+ minutes (configurable) with zero set breaks |
| `no playable tracks` | gather | Junk filtering left nothing |
| `research asserts unknown song: X` | vet | Research names a song that isn't in this show |
| `research asserts wrong date: X` | vet | Research names a date that isn't this show's date |
| `research asserts unparseable date: X` | vet | Research names a date the checker couldn't normalize (year-less dates like "December 2" are matched against the show's month and day, not flagged) |
| `dj notes mention unknown song / nonexistent set / missing set intros / break count mismatch` | synthesize | The DJ script contradicts the manifest |
| `duration mismatch on <file>` | package | Downloaded audio's real length disagrees with metadata |

**Clearing gate 2.** There is deliberately no `--force`-through-processing
flag: a flagged show stays held until a human looks. Looking means
`llama show <run-dir>/shows/<show>` — it prints the flags and state. Then:

- **Fix the input and re-run the stage that flagged it.** Vet flags are
  self-clearing: `llama run <run-dir> --stage vet --force` re-vets and
  recomputes (its own old flags are dropped first). Gather flags likewise
  clear if a re-gather (`--stage gather --force`) produces clean structure —
  e.g. after adding a setlist.fm API key.
- **Overrule it.** If the flags are false alarms:
  `llama show <run-dir>/shows/<show> --clear`, then `llama run <run-dir>`.
  Later stages skip finished work and packaging proceeds.
- **Deliver-time-only flags** (`duration mismatch`) are the one case where a
  package already exists; `llama deliver <show-dir> --force` overrides the
  delivery refusal.

## Command reference

### `llama find "query" [--limit N] [--auto] [--script] [--run-name NAME]`
One-off end-to-end run. Interactive by default: artist-less queries let you
prune the matched-artist list, and the shortlist prompt asks which ranks to
process (empty answer = top picks). `--auto` skips all prompts and takes the
top-ranked shows. `--script` adds the verbatim DJ script (extra high-tier LLM
call).

### `llama run <run-dir> [--stage S --force] [--interactive] [--script]`
**The resume/replay command.** Re-executes a run from its artifacts; every
stage skips work whose output already exists, so this is how you continue
after a crash, after `llama review`, or after fixing something by hand.

- `--stage <name> --force` deletes that stage's outputs **and everything
  downstream of it** (for every show in the run), then re-runs — later
  stages can never reuse artifacts derived from the pre-force state. Valid
  stages: `search`, `winnow`, `select`, `gather`, `research`, `vet`,
  `synthesize`, `package`. Forcing `search` also drops the shortlist.
- Bare `--force` re-runs **everything**, including winnow — this rebuilds
  `shortlist.json`. If approvals were recorded on it, llama asks for
  confirmation before wiping them. Reach for `--stage X --force` first.
- Defaults to `--auto` (no prompts), unlike `find`.

### `llama review <run-dir>`
Gate 1 only: prints the shortlist, asks which ranks to approve, and writes
the answer into `shortlist.json`. Ranks you don't name are left undecided
(once anything is approved, only approved entries are processed). It then
offers to process the approved shows immediately; decline and it prints the
`llama run` command to do it later. Empty input changes nothing. It has no
connection to needs-review (gate 2).

### `llama show <show-dir> [--clear]`
Gate 2: inspect one show's needs-review state — flags, recording, whether a
package exists. `--clear` overrules the hold (clears `needs_review` and the
flags) after you've judged them false alarms; follow with
`llama run <run-dir>` to package. Takes the show directory
(`<run-dir>/shows/<artist-date>/`).

### `llama deliver <show-dir> [--dest DIR] [--force]`
Copies `<show-dir>/package/` into the station's watched folder
(`delivery_path` from config, or `--dest`) and records a `delivered` ledger
entry. Refuses if the show is marked needs-review; `--force` overrides.
Takes the **show directory** (the one containing `show.json`), not the
package directory.

### `llama artists ["query"] [--limit N] [--all] [--refresh]`
Search the LMA artist index with a natural-language query, or with no query
list the deepest catalogs. `--all` bypasses the junk-filter floors.

### `llama profile add <name> "query" [--count N] [--human-gate] [--script]`
Interprets the query once and saves it as a standing profile.
`--human-gate` makes `profile run --auto` stop at gate 1 instead of
self-approving.

### `llama profile run <name> [--auto]`
Runs the profile as a new dated run, skipping performances already in the
ledger. With `--human-gate` and `--auto`, stops at
`Shortlist awaits review: llama review <run-dir>`; approve, then
`llama run <run-dir>`.

### `llama profile list` / `llama ledger list` / `llama ledger add` / `llama ledger remove`
Housekeeping. The ledger is the dedup memory: `selected` and `delivered`
entries suppress a performance in future winnows; `rejected` entries do too.
`ledger remove <performance-id>` un-suppresses one.

## Recipes

**A `find` printed `needs-review, skipped` for a show I want.**
`llama show <run-dir>/shows/<show>` to read the flags. If a flag is a false
alarm, `llama show <show-dir> --clear` and `llama run <run-dir>`. If it's
real (e.g. unresolved titles), fix the cause and `--stage <stage> --force`.

**I approved via `llama review` — now what?**
Say yes when it offers to process, or `llama run <run-dir>` later.

**A stage failed with an LLM error.**
The raw output is in `shows/<show>/llm-failure.txt`. Just re-run
`llama run <run-dir>` — completed stages are skipped, the failed one retries.

**I want a different recording of the same show.**
`llama run <run-dir> --stage select --force` — forcing cascades, so
gather through package rebuild from the newly picked recording.

**Re-research a show.**
`llama run <run-dir> --stage research --force` — this also deletes
`vetting.json`, so the new research gets re-vetted.

**The same show keeps coming back in every profile run.**
It's not in the ledger. Deliver it, or `llama ledger add <performance-id>
--artist A --date D --status rejected` to suppress it.

## Troubleshooting: message → meaning → action

| You see | It means | Do |
|---|---|---|
| `Shortlist awaits review: llama review <dir>` | Gate 1 is waiting (human-gate profile) | `llama review <dir>` (it offers to process after) |
| `approved: [1]` (from review) | Picks recorded | Say yes at the process prompt, or `llama run <dir>` later |
| `needs-review, skipped: <show>` | Gate 2: a flag was set during processing | `llama show <show-dir>`; fix or `--clear`, then `llama run <dir>` |
| `skipping <show>: needs review (…)` (log line) | Same as above, with the flags inline | Same |
| `holding <show>: flagged during packaging (…)` | Package built but audio verification flagged it | Inspect; `llama deliver --force` if acceptable |
| `refusing to deliver: … use --force` | Delivering a needs-review show | Inspect, then `--force` if intended |
| `FAILED <show>: …` | LLM/network failure mid-show | `llama run <dir>` retries just the missing pieces; see `llm-failure.txt` |
| `No shows survived winnowing.` | Nothing passed dedup + mechanical floors + scoring | Broaden the query, lower floors, or check the ledger |
| `no matching artists found on the LMA` | Artist-less query matched nothing in the index | Name an artist or broaden the style terms |
| `winnow: truncating N survivors to 40` | More candidates than the review-fetch budget | Fine for most runs; narrow the query if the cut worries you |
