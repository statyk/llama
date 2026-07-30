# llama + emcee

Two tools that together take an archive.org Live Music Archive recording to
air. **`llama`** finds concerts, vets them for quality, researches the
specific performance (fact-checking the research against the setlist before
it ships), and packages audio + a neutral vetted **briefing** for an
automated radio station — ending at `llama deliver`. It never writes a DJ
script and has no TTS. **`emcee`** (dist `llama-emcee`) is a separate,
station-side CLI that runs *after* delivery: it scans the station's
delivered-packages folder, writes a DJ script from the briefing (optionally
in a named **presenter**'s persona — a reusable on-air host defined in
`presenters/<id>.toml`), speaks it via TTS (hosted Mistral Voxtral by
default, ElevenLabs an opt-in alternative), and assembles `broadcast.m3u` —
writing all of that straight into the package llama delivered. See
[emcee: voicing delivered packages](#emcee-voicing-delivered-packages)
below for emcee's own setup and commands.

## Setup

This is a monorepo of three packages: `packages/llama` (the acquisition CLI
described above), `packages/emcee` (the station-side voicing CLI), and
`packages/herder`, the shared LLM task layer underneath both of them
(tiered provider resolution, schema-validated task runners, retry
escalation). Install all three editable together:

    python3 -m venv .venv && source .venv/bin/activate
    pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee

(Installing `packages/emcee` is optional if you only need llama's
acquisition side — e.g. a dev box that never voices shows — but the
default setup above installs both.)

Optional config at `~/.llama/config.toml` — seed a fully-commented copy of
these defaults with `llama config init` (`--stdout` to print instead):

    root = "/path/to/workdir"        # default ~/.llama
    delivery_path = "/station/inbox" # for `llama deliver`
    audio_format = "mp3"             # or "flac"

    [setlistfm]
    api_key = "..."                  # or SETLISTFM_API_KEY env var; optional —
                                     # without it set-structure recovery is
                                     # best-effort from LMA descriptions only

    [winnow]
    max_metadata_fetch = 40          # review-fetch budget; when survivors exceed it
                                     # the best-evidenced are sampled, bounded by
                                     # artist_cap/year_cap

    # Recording selection ships GD-tuned defaults (shown here); override per
    # collection. Taper bonuses match identifier substrings; among revisions
    # by the same taper the newest gets the full bonus. lineage_eras replace
    # the global sbd/matrix/aud base scores inside a date window.
    [selection.tapers.GratefulDead]
    miller = 2.0                     # Charlie Miller: community gold standard
    seamons = 1.0

    [[selection.lineage_eras]]       # early-80s boards are rough: MTX > AUD > SBD
    collection = "GratefulDead"
    date_from = "1980-01-01"
    date_to = "1987-12-31"
    scores = { matrix = 3.0, aud = 2.0, sbd = 1.0 }

    [llm.default]
    backend = "claude_cli"           # requires the `claude` CLI on PATH
    # backend = "openrouter"         # HTTP alternative; set OPENROUTER_API_KEY
    # Model tiers (low/medium/high): haiku/sonnet/opus on claude_cli;
    # gemini-2.5-flash / claude-sonnet-4.5 / claude-opus-4.1 on openrouter.
    # Defaults: medium for most tasks; high for deep_research and brief;
    # low for vet_research.
    # If a task's output fails validation twice, the final retry runs one
    # tier up (exact `model` pins never escalate).

    [llm.deep_research]
    # backend = "claude_cli"         # recommended when the default backend is
    # openrouter: openrouter research is single-shot web-search grounding,
    # weaker than the claude CLI's agentic multi-step research, and research
    # quality is audible on air. Mixing backends per task is supported.

    [llm.brief]
    # tier = "medium"                # example: cheaper briefing
    # model = "claude-opus-4-8"      # example: exact pin, bypasses tiers

    [llm.tiers.openrouter]
    # medium = "deepseek/deepseek-chat-v3"  # retarget what a tier means per backend

Config values **replace** built-in defaults — nothing merges. Adding any
`[selection.tapers.<Band>]` table replaces the whole taper set (the
GratefulDead bonuses vanish unless restated), and any
`[[selection.lineage_eras]]` block replaces the built-in era list. One
level down, an era's `scores` map replaces the whole lineage table: an
omitted class (`sbd`/`matrix`/`aud`/`unknown`) scores 0.0, not its global
value. `llama config init` writes all defaults out explicitly so additive
edits keep them. The trap runs both ways: deleting a seeded table or block
restores its built-in default (absence = default) — to truly clear one, set
it empty (e.g. `lineage_eras = []` under `[selection]`).

Presenters, TTS, and everything about *voicing* a show now belong to
`emcee` — see
[emcee: voicing delivered packages](#emcee-voicing-delivered-packages)
below. llama has no `[tts]` config, no presenter concept, and no
`--voice`/`--script` flags anywhere.

Release binaries (attached to each GitHub Release, for both `llama` and
`emcee`) are signed: the macOS build is Developer ID-signed and notarized
(Gatekeeper-clean; because it is a bare executable it can't be stapled, so
first run does an online notarization check), and the Windows build is
Authenticode-signed via Azure Trusted Signing. The Linux builds are
unsigned — verify them against `SHA256SUMS`. See
[docs/releasing.md](docs/releasing.md) for the release process.

## Use

    llama get "GD shows 73-74 with a china>rider"
    llama get "top 10 Grateful Dead shows of the 1980s" --auto
    llama get "well-known folk/acoustic performer, 1960s-70s, highly rated"
                                     # artist-less queries match artists against the index first
                                     # (interactive runs let you prune the list)
    llama get "GD 1972" --plan       # cheap preview: winnow + shortlist, nothing processed
                                     # (llama run approve <session-id> to actually process it)
    llama profile add sunday-dead-hour "classic Grateful Dead" --count 1 --human-gate
    llama profile add jazz "well-regarded jazz-adjacent live sets" --count 13 --artist-cap 0.25
                                     # multi-artist profiles: one artist may hold at most
                                     # ceil(count*cap) picks while others have candidates;
                                     # --year-cap does the same per year (default off:
                                     # scores decide the year mix; set it for an era tour);
                                     # --min-score (default 6.0) floors the LLM review score
                                     # so a thinning pool fails loudly, never fades quietly
    llama profile add funky "funk, soul, R&B" --count 13 \
        --artists "Galactic, Lettuce, Soulive, Dumpstaphunk"
                                     # pin the roster: runs skip the LLM artist matcher and
                                     # search exactly these (test-drive with `llama artists`,
                                     # freeze what you like; typos fail at add time)
    llama profile artists funky       # view a profile's pinned roster
    llama profile artists funky --set "Galactic, Lettuce, Soulive"
                                     # re-pin it (validated against the index); --set "" clears
    llama profile list                # every profile: name, count, query
    llama profile show sunday-dead-hour   # inspect one profile (read-only, no LLM call)
    llama get --profile sunday-dead-hour
    llama status                     # attention-list, then every show + its state
    llama status --held              # just the shows waiting on your judgment
    llama status --by-run            # sessions with per-state show counts
    llama run list                   # sessions awaiting approval or incomplete
    llama run approve countryish     # gate 1: approve a session's shortlist, optionally process it
    llama run resume countryish      # resume/replay a session; finished stages are skipped
    llama show 1973-06-10            # inspect one show (its state, artifacts, archive URL, flags)
    llama show 1973-06-10 --tracks   # numbered track list (index, title, filename, duration)
    llama fix 1973-06-10 --exclude 9,10       # exclude by track number (filenames work too);
                                     # auto-runs the redo from gather
    llama fix 1973-06-10 --set-venue "Winterland" --set-city "San Francisco, CA" \
        --set-date 1973-06-10 --set-title 4="Dark Star" --set-breaks "9,17"
                                     # metadata corrections; redoes from gather, hold self-clears
    llama triage                     # walk every held show and resolve each in turn
    llama redo 1973-06-10 --from vet # re-run one show's pipeline from a stage
    llama deliver 1973-06-10         # copy package to the station inbox
    llama deliver --packaged         # deliver everything that's ready
    llama rm old-show --suppress     # delete a show and never offer it again
    llama history list                # broadcast history / dedup

There is no `llama voice` or `llama presenter` command, and no
`--script`/`--voice` on any of the above — llama stops at a packaged,
briefed, unvoiced show. Voicing it is a separate step, done later by
`emcee` (see below), against the delivered copy.

Shows and sessions are addressed by **name or any unique substring** (paths
still work): `llama show 1973-06-10` finds `gratefuldead-1973-06-10`; an
ambiguous substring fails loudly and lists the candidates.
`status`, `triage`, `redo`, `deliver`, and `rm` share one filter
vocabulary (`--held`/`--packaged`/`--state`/`--artist`/`--run`).
A batch action prints a plan and asks before running (`--yes` skips the
prompt); acting on held shows via a selector needs explicit `--held` opt-in.

Two different human gates, easy to conflate: `llama run approve` answers
"which shortlisted shows are worth processing" (gate 1) — sessions awaiting
it show up in `llama status`/`llama run list`'s attention-list. Separately,
a processed show can be held as **needs-review** when a stage flags
something suspicious (`needs-review, skipped: ...`, gate 2). A held show
has **three resolutions**, driven from `llama fix` (flag-by-flag, auto-runs
the redo) or `llama triage` (interactive walkthrough):

- **Correct the data** — `llama fix <s> --exclude <file-or-number>` drops
  junk tracks (e.g. between-set stage announcements; `llama show <s>
  --tracks` lists the numbers), and `--set-venue`/`--set-city`/`--set-date`/
  `--set-title N="..."`/`--set-breaks "9,17"` fix wrong venue, date, a track
  title, or where a set break falls. Either way it redoes from `gather` and
  the hold clears itself if that fixes it.
- **Accept an unknowable setlist** — `llama fix <s> --narration vague` tells
  the briefing to stay general (no song names, no set-structure claims),
  clears the hold, and redoes from `brief` (which regenerates the briefing
  and the package too).
- **Overrule a false alarm** — `llama fix <s> --overrule`, which redoes from
  `package`.

`llama triage` offers these as an interactive prompt over every held show
and runs your choice on the spot. See [docs/workflow.md](docs/workflow.md)
for the full pipeline map, every flag, and a troubleshooting table — start
there if a run didn't do what you expected.

**Running several jobs at once.** `llama` is safe to run as multiple
concurrent processes against the same `~/.llama/` on one machine — kick off
several `llama get`/profile runs (or a cron fan-out) in parallel. If two runs
pick the same performance, one builds it and the others wait and reuse the
result rather than duplicating the work; runs never idle behind each other
on shows they don't share. (Local filesystem only — a network/NFS-shared
workspace is not supported.)

### Explore artists

    llama artists "jangly 80s college rock"     # NL search, ranked with stats
    llama artists                               # deepest catalogs, no LLM call
    llama artists --include-junk "obscure tape scene"    # include the long tail
    llama artists --refresh                     # force an index rebuild

The first call builds a local artist index (one collections request plus
~30 scrape pages over all LMA items, about a minute); it auto-refreshes
after 30 days. Small collections are hidden unless they clear the
`[artists]` thresholds in config (defaults: 25 recordings or 50k
downloads); `--min-recordings` / `--min-downloads` / `--include-junk`
override per invocation.

## Tests

    pytest -q          # offline suite
    pytest -m live -q  # hits real archive.org (no LLM)

See `docs/superpowers/specs/2026-07-14-llama-design.md` for the design.

## Package format (v3)

A package that `llama deliver` hands to the station contains:

- `audio/` — verified, tagged tracks (`01 - Morning Dew.mp3`, ...)
- `playlist.m3u` — music-only play order
- `manifest.json` — `schema_version: 3`; tracks, set breaks, durations,
  source lineage (including `source.profile`, the llama profile name this
  show came from, or `null` for a one-off `get` — this is what emcee's
  `[assign]` config keys on), `show.context`, pointers `research` /
  `reviews`, a required `briefing` block, `research_vetted`, and two
  **always-null-out-of-llama** blocks, `dj_notes`/`dj_audio` (see below)
- `research.md` — web-researched show notes, grounding-checked against the
  setlist (`vet` stage) before packaging
- `reviews.md` — trimmed listener-review digest (top 5, 800 chars each)
- `briefing.md` + `briefing.json` + `manifest.briefing` — the neutral,
  vetted briefing (context, significance, per-set talking points, notable
  moments, review sentiment, cautions); always present, factually guarded,
  and stamped with the `narration` mode (`full`/`vague`) from
  `overrides.json` — llama's **only** text deliverable; llama never writes
  a DJ script

That's the whole package llama produces. There is no `broadcast.m3u`,
`dj-notes.md`, or `dj-audio/` at delivery time, and the manifest's
`dj_notes`/`dj_audio` fields are always `null` — those are written
**station-side, after delivery, by a separate tool** (`emcee`, below),
straight into the same package directory. See
[docs/station-brief.md](docs/station-brief.md) for the full manifest
contract, including the shape those blocks take once emcee has filled
them in.

## emcee: voicing delivered packages

`emcee` (dist `llama-emcee`) is a second CLI, installed alongside llama
(`pip install -e packages/emcee`, part of the default setup above), that
you run **separately, station-side**, after `llama deliver`. It never
imports llama and never touches llama's workspace — its only input is the
delivered package directory's files, and its only config is its own.

**Setup.** Seed emcee's own config with `emcee config init` (`--stdout` to
print instead) and point `[station] root` at the same folder llama's
`delivery_path` writes into:

    [station]
    root = "/station/inbox"    # same folder as llama's delivery_path

    [llm.scriptwrite]
    backend = "claude_cli"     # same backend choices/tiers as llama's [llm.*]

    [tts]
    backend = "voxtral"        # hosted Mistral Voxtral (default); or "elevenlabs"
    voice = "..."              # HOUSE voxtral preset name (or elevenlabs voice_id),
                               # used when a show has no presenter assignment
    # voice_clone = "..."      # 3-25s reference WAV; clones a house voice instead
    api_key = "..."            # or MISTRAL_API_KEY / ELEVENLABS_API_KEY env var
    # chunk = true             # sentence-by-sentence synthesis for better prosody
    # bed = "/path/to/bed.wav" # instrumental bed under every DJ clip (24kHz mono
                               # 16-bit WAV; per-presenter override via its own `bed`)

**Assigning a presenter to a llama profile.** `[assign]` maps the llama
profile name stamped at `manifest["source"]["profile"]` to a presenter and
an on-air title — this is the entire handoff between the two tools:

    [assign]
    default = "waldo"                    # presenter used when a show's profile
                                         # has no entry below (or no profile at all)

    [assign.profiles.prime-dead]
    presenter = "waldo"
    title = "The Primal Dead Hour"

**Presenters.** A **presenter** is a reusable on-air host — TTS voice +
authored character — managed entirely by emcee:

    emcee presenter add casey --name Casey --sex male --voice american-dj \
        --character "Warm late-night FM veteran, dry humor, deep tape-collector knowledge."
                                     # writes presenters/casey.toml; hand-editing it still works
    emcee presenter list               # every presenter, one line each
    emcee presenter show casey         # one presenter's full fields
    emcee presenter remove casey       # refuses if any [assign] entry still names it

Presenters live under emcee's **own** workspace root (`~/.emcee/presenters/`
by default, or `EMCEE_ROOT`/`root` in config — distinct from `[station]
root`, the delivered-packages folder). The TOML shape is the same one
llama's presenters used to have: `name`/`sex`/`character` + exactly one of
`voice`/`voice_clone`, plus an optional `bed` override. The character
loosens grounding (opinions and paraphrased review sentiment are the
host's own; concert facts stay grounded in the manifest) — enforced by
emcee's own factual guard, not llama's.

**Voicing.**

    emcee run                          # scan [station] root, voice every not-yet-ready package
    emcee run --force                  # re-synthesize every DJ clip even if cached
    emcee voice /station/inbox/gratefuldead-1973-06-10
                                       # script + voice + assemble ONE package directly
    emcee voice /station/inbox/gratefuldead-1973-06-10 --fresh set1-intro
                                       # re-roll just this DJ clip (repeatable) --
                                       # in practice, with a real LLM, emcee
                                       # re-scripts on every call and the
                                       # regenerated text usually changes EVERY
                                       # clip's cache key, so normally every clip
                                       # re-renders anyway, not just the named one
    emcee status                       # table of every package: ready / pending / unsupported
    emcee status --json

`emcee run` is the everyday command — "not broadcast-ready" *is* the work
predicate, so there's nothing to track separately: every pending package
gets a script, speech, and a `broadcast.m3u`, written straight into the
package directory llama delivered, and the manifest's `dj_notes`/`dj_audio`
blocks are rewritten in place. A pre-v3 package (from before this split, or
otherwise malformed) is reported `unsupported` and left untouched —
re-deliver it from llama rather than trying to upgrade it in place.

**Single-writer station, no lock.** Unlike llama (safe to run as multiple
concurrent processes against one `~/.llama/`, see "Running several jobs at
once" above), `emcee run`
assumes **exactly one instance at a time** against a given station root —
it takes no lock. Nothing gets corrupted if you run two at once (every
write in both tools is unique-temp-file-plus-atomic-rename), but an
overlapping run will find and voice the same pending package twice,
**doubling LLM/TTS spend** for no benefit. Run it from one place — a
single cron entry, one operator — not fanned out.

## Licensing

Both llama and emcee are licensed under **GPL-3.0-or-later**; see
[LICENSE](LICENSE) (and `packages/emcee/LICENSE`, an identical copy) for
the full text. `packages/llama/src/llama/data/set_breaks.csv` is vendored
from the [eichblatt/deadstream](https://github.com/eichblatt/deadstream)
project (also GPL-3.0) — see `packages/llama/src/llama/data/README.md` for
vendoring details and attribution.
