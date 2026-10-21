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
    # gemini-2.5-flash / claude-sonnet-5 / claude-opus-5 on openrouter.
    # Defaults: medium for most tasks; high for interpret, deep_research and
    # brief;
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
    llama status                     # every show + its state (pipes: one row per show)
    llama status --packaged --profile funk   # what `deliver --packaged --profile funk` would ship
    llama run list                   # sessions needing attention (awaiting approval, incomplete, paused)
    llama status --held              # just the shows waiting on your judgment
                                     # (--no-flags: one line per show, for piping)
    llama status --by-run            # sessions with per-state show counts
    llama run list                   # sessions awaiting approval or incomplete,
                                     # with what each run lost and why
    llama run approve countryish     # gate 1: approve a session's shortlist, optionally process it
    llama run resume countryish      # resume/replay a session; finished stages are skipped
    llama run resume --all           # one unattended pass over every resumable run (paused past
                                     # its reset, or incomplete from a download/archive failure
                                     # or a crash); --no-wait by default, stops at the first
                                     # usage pause. Loop it:
                                     #   while true; do llama run resume --all; sleep 600; done
                                     # `run list` marks a run another process is working
                                     # `running`; a run that fails any other way waits for an
                                     # explicit `run resume <id>`
    llama show 1973-06-10            # inspect one show (its state, artifacts, archive URL, flags)
    llama show 1973-06-10 --tracks   # numbered track list (index, title, filename, duration)
    llama fix 1973-06-10 --exclude 9,10       # exclude by track number (filenames work too);
                                     # auto-runs the redo from gather
    llama fix 1973-06-10 --include x1         # re-admit a file the junk filter dropped
                                     # (x-handles come from `llama show ... --tracks`)
    llama fix 1973-06-10 --set-venue "Winterland" --set-city "San Francisco, CA" \
        --set-date 1973-06-10 --set-title 4="Dark Star" --set-breaks "9,17"
                                     # metadata corrections; redoes from gather, hold self-clears
    llama triage                     # walk every held show and resolve each in turn
    llama redo 1973-06-10 --from vet # re-run one show's pipeline from a stage
    llama deliver 1973-06-10         # copy package to the station inbox
    llama deliver --packaged         # deliver everything that's ready
                                     # (deliver then drops the library's copy of the
                                     # audio; `llama redo <show> --from package`
                                     # re-downloads it if you need to re-deliver)
    llama deliver --packaged --profile funk  # only shows the `funk` profile acquired
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
it show up in `llama run list`'s attention-list. Separately,
a processed show can be held as **needs-review** when a stage flags
something suspicious (`needs-review, skipped: ...`, gate 2). A held show
has **three resolutions** (plus a fourth for tapes with no titles, below), driven from `llama fix` (flag-by-flag, auto-runs
the redo) or `llama triage` (interactive walkthrough):

- **Correct the data** — `llama fix <s> --exclude <file-or-number>` drops
  junk tracks (e.g. between-set stage announcements; `llama show <s>
  --tracks` lists the numbers), and `--set-venue`/`--set-city`/`--set-date`/
  `--set-title N="..."`/`--set-breaks "9,17"` fix wrong venue, date, a track
  title, or where a set break falls. Either way it redoes from `gather` and
  the hold clears itself if that fixes it. The reverse also works: `llama
  show <s> --tracks` lists every excluded file — most often ones the junk
  filter dropped — with an `x`-handle, and `llama fix <s> --include x1`
  puts one back — the junk thresholds are measured and stay put, so a
  wrongly-dropped track is fixed per show, not by loosening the filter.
- **Accept an unknowable setlist** — `llama fix <s> --narration vague` tells
  the briefing to stay general (no song names, no set-structure claims),
  clears the hold, and redoes from `brief` (which regenerates the briefing
  and the package too).
- **Overrule a false alarm** — `llama fix <s> --overrule`, which redoes from
  `package`.

A fourth route exists for a tape with **no resolved titles at all** (a wholly
improvised set whose tags read `Track 01`...`Track 09`, or a tape with no
setlist anywhere): `llama fix <s> --untitled` (or `[u]` in `llama triage`,
offered only on such a show). It lists every track's filename first, so a tape
whose filenames carry the titles is not thrown away unseen, then on ONE
confirmation titles every track `Untitled (track N)`, sets narration to vague,
puts the tape in a single set, overrules whatever flags remain and builds the
package. It takes no other edit flag. For a show that is already delivered
with placeholder tags (for example `eotoband-2007-10-09`), run `llama redo <s>
--from gather`, then `llama fix <s> --untitled`, then `llama deliver <s>`.

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

### Re-checking the held backlog (replay harness and `reapply`)

Many holds were false alarms of guards that have since been narrowed (venue
spelling, short real titles, the briefing guard, adjacent-day research dates).
Two tools re-check them without spending LLM calls on the guesswork.

`scripts/replay_holds.py` is read-only against `~/.llama`: it recomputes every
held show's flags offline, from the stored files and the archive.org cache,
under the code of the tree you run it from. Use that tree's own interpreter
and keep the output outside the library (for example `~/.llama-harness`):

    ./.venv/bin/python scripts/replay_holds.py run --out ~/.llama-harness/base.json
    ./.venv/bin/python scripts/replay_holds.py compare ~/.llama-harness/base.json ~/.llama-harness/cand.json --out ~/.llama-harness/cmp

(`base.json` from the main checkout, `cand.json` from the branch to measure.)
`compare` writes reports (`summary.txt`, the hand-check sample, closest calls,
title and structure changes, shows a redo would change that are already
packaged or delivered, and a `narration_candidates.html` page) and three lists
for `reapply`: `predicted_list.json`, `structure_changed_list.json` and a
10-show `pilot_list.json`. A show that would need any other LLM call is listed
as needs-LLM and left alone.

`llama reapply` applies a list. It re-processes held shows in place with the
harness's own computation, reuses a stored briefing when it still holds
(otherwise it asks for one fresh briefing, its only LLM work: one brief task
of up to two attempts), downloads any missing audio (first-time packages are
the bulk), and writes `show.json` last, so an interrupted show is still held
and a re-run finishes it. It never delivers: on a delivered show that clears,
it prints `re-deliver with: llama deliver <name>`.

    llama reapply <show>...                      # named shows
    llama reapply --from-list predicted_list.json --dry-run   # first: writes nothing
    llama reapply --from-list pilot_list.json    # then a 10-show pilot
    llama reapply --from-list predicted_list.json   # then the rest, in waves

A show whose replay changes its sets, segues or breaks is skipped
(`skipped: structure changed`, retryable) unless you pass
`--allow-structure-change`, to the names form and `--from-list` alike. After
hand-checking each row of `structure_changed_list.json`, apply it with
`llama reapply --from-list structure_changed_list.json --allow-structure-change`.

Always dry-run first and read the summary (fresh briefs, downloads
and their size). Run the pilot, compare each show's actual outcome and meter
cost with the prediction, then run the full list: re-running the same list
resumes where it stopped, and a usage-limit pause prints the command to
continue. A list is accepted only from the same commit and config that wrote
it, and a show edited since the harness ran is skipped. Afterwards re-run the
harness; any difference on a predicted clear is a defect to look at.

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
                               # or "mlx_audio": local, on this Mac (see "Local TTS" below)
    voice = "..."              # HOUSE voxtral preset name (or elevenlabs voice_id),
                               # used when a show has no presenter assignment
    # voice_clone = "..."      # 3-25s reference WAV; clones a house voice instead
    api_key = "..."            # or MISTRAL_API_KEY / ELEVENLABS_API_KEY env var
    # chunk = false            # one call per segment (default: per sentence, loudness-normalized)
    # bed = "/path/to/bed.wav" # instrumental bed under every DJ clip (24kHz mono
                               # 16-bit WAV; per-presenter override via its own `bed`)

**Preparing a bed file.** A bed must be a 24 kHz, mono, 16-bit PCM WAV — it is
mixed sample-for-sample with the voice PCM, and emcee does not resample: any
other format is refused with an error naming what it found. Convert with either

    ffmpeg -i input.mp3 -ac 1 -ar 24000 -c:a pcm_s16le bed.wav
    sox input.mp3 -r 24000 -c 1 -b 16 bed.wav    # needs sox built with mp3 support

and check with `ffprobe -hide_banner bed.wav` (expect `pcm_s16le, 24000 Hz,
mono`). `bed_gain_db` (default −20) attenuates relative to the file's own level,
so a hot or quiet source stays hot or quiet under the voice; adding
`-af loudnorm=I=-16` to the ffmpeg line gives every bed the same starting point.

**Assigning a presenter to a llama profile.** `[assign]` maps the llama
profile name stamped at `manifest["source"]["profile"]` to a presenter and
an on-air title (an `emcee move` or `[assign.artists]` rule can change which profile a show is voiced as; see "Moving shows between profiles") — this is the entire handoff between the two tools:

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
    emcee presenter edit casey --tts voxtral
                                     # change any field; --clear-tts/--clear-tts-model/
                                     # --clear-bed/--clear-voice-clone-text; --transcribe
                                     # drafts voice_clone_text on the mlx-audio server
    emcee presenter remove casey       # refuses if any [assign] entry still names it

Presenters live under emcee's **own** workspace root (`~/.emcee/presenters/`
by default, or `EMCEE_ROOT`/`root` in config — distinct from `[station]
root`, the delivered-packages folder). The TOML shape is the same one
llama's presenters used to have: `name`/`sex`/`character` + exactly one of
`voice`/`voice_clone`, plus an optional `bed` override. Three optional keys
pin a presenter's TTS: `tts` (`voxtral`, `elevenlabs` or `mlx_audio`; absent
= `[tts] backend`, except never mlx_audio: pin it explicitly), `tts_model`
(mlx_audio only) and `voice_clone_text` (the clip's transcript, required by
mlx_audio). The file is strict: an unknown key is a load error. `emcee run
--dry-run` shows each pinned presenter's backend and model. The character
loosens grounding (opinions and paraphrased review sentiment are the
host's own; concert facts stay grounded in the manifest) — enforced by
emcee's own factual guard, not llama's.

**Voicing.**

    emcee run                          # scan [station] root, print the plan, ask, then voice
    emcee run --yes                    # same, without the question (the plan still prints)
    emcee run --dry-run                # the would-voice rows and the plan; never asks or writes
    emcee run --force                  # re-synthesize every DJ clip even if cached
    emcee voice gratefuldead-1973-06-10
                                       # script + voice + assemble ONE package directly;
                                       # a name or unique substring under [station] root,
                                       # or a path
    emcee voice gratefuldead-1973-06-10 --fresh set1-intro
                                       # re-roll just this DJ clip (repeatable) --
                                       # in practice, with a real LLM, emcee
                                       # re-scripts on every call and the
                                       # regenerated text usually changes EVERY
                                       # clip's cache key, so normally every clip
                                       # re-renders anyway, not just the named one
    emcee status                       # summary by (effective) profile: ready / pending / other
    emcee status --list                # per show; a moved show reads "southern (from funk)"
    emcee status --json
    emcee move tedeschitrucksband-2012-11-29 southern
                                       # voice this show as southern from the next run on
    emcee move tedeschitrucksband-2012-11-29 --delivered
                                       # back to llama's profile (exempts it from an artist rule)
    emcee move tedeschitrucksband-2012-11-29 --clear
    emcee move --list                  # every recorded move; `missing` = no package has it

**Ad-hoc narration.** Apart from the package pipeline entirely — no package,
no script, no LLM, so it works on a station with no `[llm]` backend
configured at all:

    emcee say notes.txt                # -> notes.mp3, in the house [tts] voice
    emcee say notes.txt --clone ref.wav -o read.mp3
                                       # clone a 3-25s reference clip (voxtral or
                                       # mlx_audio; under an mlx_audio house add
                                       # --clone-text "<transcript>")
    emcee say notes.txt --presenter casey
                                       # read it in a presenter's voice (and bed)
    emcee say notes.txt --no-bed       # dry read; --bed FILE / --bed-gain DB override
    emcee say notes.txt --no-chunk     # one call for the whole passage
    emcee say notes.txt --raw          # verbatim: no symbol expansion, no lexicon

Voice sources are mutually exclusive (`--clone` / `--voice` / `--presenter`);
with none of them the house `[tts] voice`/`voice_clone` reads it. The bed
resolves as a voiced package's does — the presenter's own bed, else
`[tts] bed` — with `--bed`/`--bed-gain`/`--no-bed` overriding on the command
line. As with DJ clips, chunking is **on** by default: an arbitrary text file
routinely exceeds the backend's per-request character cap, which a single
whole-passage call cannot survive. `--no-chunk` without a bed is the one render
that is not loudness-normalized (it ships the provider's own MP3).

`emcee run` is the everyday command — "not broadcast-ready" *is* the work
predicate, so there's nothing to track separately: every pending package
gets a script, speech, and a `broadcast.m3u`, written straight into the
package directory llama delivered, and the manifest's `dj_notes`/`dj_audio`
blocks are rewritten in place. A pre-v3 package (from before this split, or
otherwise malformed) is reported `unsupported` and left untouched —
re-deliver it from llama rather than trying to upgrade it in place.

**Moving shows between profiles.** Two ways, both emcee-side (llama's own
records and `llama status`/`deliver --profile` keep the profile that found
the show):

- **Artist rules** in `~/.emcee/config.toml`, for every show by an artist:

      [assign.artists]
      "Tedeschi Trucks Band" = "southern"                         # from any profile
      "JJ Grey and MOFRO"    = { profile = "southern", from = ["funk"] }

  Names match loosely (case, `&`/`and`, apostrophes, one trailing `[...]`,
  a leading "The"). A rule's profile needs its own `[assign.profiles.<name>]`
  entry, or every emcee command refuses to start. So the order is: create
  the presenter (`emcee presenter add`), add its `[assign.profiles.<name>]`
  entry, then add rules.
- **One-off moves** with `emcee move` (above), kept in
  `~/.emcee/moves.json`, keyed by the show's performance id, so they survive
  a `llama deliver --replace-voiced`. A move beats a rule; `--delivered` is
  how one show is exempted from a rule. Back up `moves.json`: an unreadable
  one stops `emcee run`/`voice`/`status`/`move`, and a missing one does too
  while any package was voiced under a move. A move not yet voiced lives
  only there.

A show whose effective profile changes goes `pending` (it keeps airing its
old voicing until the re-voice lands), and the next `emcee run` lists it
under `re-voice` in the plan, with the reason, before asking. Each voiced
manifest records the profile it was voiced as, where that came from, and
the TTS backend, model and voice (`dj_audio.profile`, `profile_source`,
`tts`). Changing a presenter, a presenter's TTS pin or the house voice does
not trigger a re-voice.

**Running `emcee run` from an agent** (no terminal): run `emcee run
--dry-run`, show the operator the plan, and pass `--yes` only after they
approve. The `--yes` run scans again, so anything delivered, moved or
edited in between is voiced without having been shown: keep that gap
short, and run nothing else against the station meanwhile.

**Single-writer station, no lock.** Unlike llama (safe to run as multiple
concurrent processes against one `~/.llama/`, see "Running several jobs at
once" above), `emcee run`
assumes **exactly one instance at a time** against a given station root —
it takes no lock. No single file is left half-written if you run two at
once (every write in both tools is unique-temp-file-plus-atomic-rename),
but an overlapping run will find and voice the same pending package twice:
run A's `dj-notes.md` can end up beside run B's manifest `dj_notes` block
and B's clips, leaving the package internally inconsistent — and it still
**doubles LLM/TTS spend** for no benefit. Run it from one place — a single
cron entry, one operator — not fanned out.

**Local TTS on this Mac (`mlx_audio`).** A presenter (or the house voice) can
be voiced by a free local model served by [mlx-audio](https://github.com/Blaizzy/mlx-audio)'s
`mlx_audio.server`, instead of hosted Voxtral. Only calibrated models resolve
(today: `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16`; evidence in
`docs/superpowers/2026-10-12-mlx-audio-calibration.md`), and an `mlx_audio`
voice never falls back to another backend: if the server is down, its
packages fail (before any LLM spend, and without touching a voiced package)
and the rest of `emcee run` carries on.

1. **Install the new emcee release before pinning any presenter.** An older
   binary does not know `tts`/`tts_model` and would voice the presenter on
   Voxtral from the newly edited clip. (Older binaries silently ignore these
   keys; from this release an unknown key is a load error.)
2. **A dedicated venv, pinned to the evaluated mlx-audio**, whose server-side
   sampling defaults (temperature, top_k, top_p) define the evaluated voice —
   emcee does not send them. From a checkout of this repo (the constraints
   file is the evaluated environment's `pip freeze`):

       mkdir -p ~/.mlx-audio/logs
       uv venv --python 3.12 ~/.mlx-audio/venv
       uv pip install --python ~/.mlx-audio/venv/bin/python \
           "mlx-audio[server,tts,stt]==0.5.8" \
           -c docs/superpowers/2026-10-12-mlx-audio-requirements.txt

3. **Download the models once, while online** (the service runs offline, so a
   mistyped model id fails fast instead of starting a download):

       ~/.mlx-audio/venv/bin/python -c "
       from huggingface_hub import snapshot_download as d
       d('mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16')
       d('mlx-community/whisper-large-v3-turbo-asr-fp16')"

4. **A launchd agent**, bound to 127.0.0.1, with a working directory and log
   directory that exist (launchd starts jobs in `/`, where the server's
   default relative `logs` directory cannot be created). Paste this as-is:
   the shell fills in your home directory, and `plutil` checks what it wrote:

   ```sh
   cat > ~/Library/LaunchAgents/com.lma-radio.mlx-audio.plist <<EOF
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
     <key>Label</key><string>com.lma-radio.mlx-audio</string>
     <key>ProgramArguments</key>
     <array>
       <string>$HOME/.mlx-audio/venv/bin/python</string>
       <string>-m</string><string>mlx_audio.server</string>
       <string>--host</string><string>127.0.0.1</string>
       <string>--port</string><string>8000</string>
       <string>--log-dir</string><string>$HOME/.mlx-audio/logs</string>
     </array>
     <key>WorkingDirectory</key><string>$HOME/.mlx-audio</string>
     <key>EnvironmentVariables</key>
     <dict><key>HF_HUB_OFFLINE</key><string>1</string></dict>
     <key>RunAtLoad</key><true/>
     <key>KeepAlive</key><true/>
     <key>StandardOutPath</key><string>$HOME/.mlx-audio/server.log</string>
     <key>StandardErrorPath</key><string>$HOME/.mlx-audio/server.log</string>
   </dict>
   </plist>
   EOF
   plutil -lint ~/Library/LaunchAgents/com.lma-radio.mlx-audio.plist
   ```

   Start it once. launchd then loads it by itself at every login and
   restarts it if it dies, so there is no per-session start command:

       launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.lma-radio.mlx-audio.plist

   `curl -s http://127.0.0.1:8000/` answers when it is up. Later, only as
   needed (not part of setup):

       # restart a running server, e.g. after upgrading mlx-audio:
       launchctl kickstart -k gui/$(id -u)/com.lma-radio.mlx-audio
       # stop and unregister it (killing the process alone won't do;
       # KeepAlive restarts it). Start it again with `bootstrap`, not
       # `kickstart`. It also comes back at the next login unless you
       # `launchctl disable gui/$(id -u)/com.lma-radio.mlx-audio`:
       launchctl bootout gui/$(id -u)/com.lma-radio.mlx-audio

   A generation
   failure's details are in `~/.mlx-audio/server.log` — emcee's error points
   you there. `Bootstrap failed: 5: Input/output error` is launchd's
   catch-all: usually the plist does not parse (`plutil -lint` it) or the job
   is already loaded (`bootout` first); for anything else, read
   `~/.mlx-audio/server.log`.
5. **emcee config:**

       [tts.mlx_audio]
       model = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
       # for verification and --transcribe:
       stt_model = "mlx-community/whisper-large-v3-turbo-asr-fp16"
       # url = "http://127.0.0.1:8000"   timeout_s = 600 (defaults)

       # optional: transcribe every new clip, re-synthesize once on a gross
       # mismatch. Adding "voxtral" makes Voxtral presenters depend on this
       # server too.
       # [tts.verify]
       # backends = ["mlx_audio"]

   Verification is OFF by default. The recommendation is to enable it for
   `mlx_audio` when the first presenter is pinned to it, and to keep
   `voxtral` off for now: 10 Voxtral takes are too few, the disfluency effect
   on the thresholds is unmeasured, and enabling it makes hosted voicing
   depend on this server (see Memory, item 6). The measured thresholds are in
   `emcee/tts/verify.py` and the evidence doc.

   Hosted keys can move into `[tts.voxtral] api_key` / `[tts.elevenlabs]
   api_key` (they apply wherever that backend voices); your existing `[tts]
   api_key` keeps working while `[tts] backend` is hosted. Don't set the same
   key in both places.
6. **Memory.** The server keeps every model it has served resident until it
   restarts: presenters pinned to different mlx models hold all of them, and
   with verification on it also holds the STT model (`--transcribe` unloads
   the STT model again when verification is off). Measured on the 16 GB mini
   (evidence doc, "Memory headroom"): with Qwen 1.7B plus Whisper resident and
   verification on, chunk-rendering a 1200-character segment kept the server at
   6.6-7.0 GB between sentences with spikes of 10-12 GB during generation
   (`phys_footprint_peak` 12 GB), and swap grew from 1.4 GB to 5.5 GB used on
   the cold run under a light desktop; the host is at its memory limit.
   Whisper alone (Qwen unloaded) left the server at 2786 MB, against 5068 MB
   with Qwen resident and Whisper unloaded. For a voicing run, close browser
   tabs and other apps; verification costs the Whisper resident set.
7. **Moving a presenter** (`<id>`) to mlx_audio, with its reference clip and
   that clip's exact transcript saved beside it (for the four drafted clones,
   the corrected `~/tts-bakeoff/refs/<stem>.draft.txt`):

       emcee presenter edit <id> --tts mlx_audio \
           --voice-clone ~/.emcee/samples/<clip>.wav \
           --voice-clone-text "$(cat ~/.emcee/samples/<clip>.txt)"
       emcee run --dry-run                 # <id>'s rows end [mlx_audio <model>]
       emcee say notes.txt --presenter <id>    # the go-live listen
       emcee voice <one of its packages>       # then one real package

   **Go-live prerequisites:**
   - **The transcript must be right.** It is sent with the clip on every
     request. Calibration used five clones: Phil's (`phil_ex`) transcript was
     checked by ear; the four Whisper drafted
     (`~/tts-bakeoff/refs/{monroe1,kurt1,troymcclure2,billgraham2}.draft.txt`)
     likely contain mishearings and must be corrected first.
   - **Listen before relying on the pin.** Render one `emcee say` and listen
     with no `emcee run` in between; unpin (`--clear-tts`) if it does not
     pass. A clone outside those five is unmeasured, so this listen is the
     only check it gets.
   - **Take a memory reading** during the first real `emcee voice` (TTS, STT
     and `claude -p` all resident), from another terminal —
     `footprint -p $(lsof -tiTCP:8000 -sTCP:LISTEN)` and `vm_stat` — and
     record it beside the calibration doc's `footprint` reading.

   For a NEW presenter, `--transcribe` drafts the transcript (`emcee
   presenter add … --voice-clone clip.wav --tts mlx_audio --transcribe`) and
   writes it only after you confirm it. Without a server-loadable STT model,
   draft it by hand with `mlx_whisper clip.wav --model
   mlx-community/whisper-large-v3-turbo --language en` (from `pip install
   mlx-whisper`) and pass it as `--voice-clone-text`. Reference clips may be
   any rate or channel count (the server resamples and down-mixes them).
8. **Moving the house voice to mlx_audio** (`[tts] backend = "mlx_audio"`,
   plus `[tts] voice_clone` and `voice_clone_text`; drop `[tts] api_key`/`model`
   into the hosted tables): pin every presenter first, e.g. `emcee presenter
   edit roydemure --tts voxtral` — an unpinned presenter under an mlx_audio
   house is an error, never a silent move. With `[assign] default =
   "roydemure"` every package has a presenter, so moving "the default voice"
   means pinning Roy, not changing the house.
9. **Rollback.** Do all of this BEFORE downgrading the emcee binary:

   - **Unpin every presenter pinned to mlx_audio** back to a Voxtral-suitable
     reference clip (the one it aired with before), e.g.

         emcee presenter edit <id> --clear-tts --clear-tts-model \
             --voice-clone ~/.emcee/samples/<aired clip>.wav

   - **Re-voice every presenter pinned to elevenlabs** for the house backend.
     The old binary ignores pins and voices every presenter on the house
     backend, so an ElevenLabs `voice` id would be sent to Voxtral and fail
     the package. Clear the pin and give it a Voxtral voice in one command:

         emcee presenter edit <id> --clear-tts --voice <voxtral voice>
         # or: --clear-tts --voice-clone ~/.emcee/samples/<clip>.wav

     Only a pin to the house backend itself (e.g. roydemure's `voxtral` pin
     under a voxtral house) is harmless to leave.
   - **Edit `~/.emcee/config.toml`.** The old binary's `[tts]` is strict and
     refuses any key it does not know. Remove `[tts.mlx_audio]`,
     `[tts.verify]` and `[tts.voxtral]`/`[tts.elevenlabs]`; move a hosted key
     back to `[tts] api_key` (or rely on the env var), and a hosted `model`
     back to `[tts] model` if one is set; and if the house voice was moved
     (item 8), restore `[tts] backend` and drop `[tts] voice_clone_text`.

   A re-pinned presenter never reuses the other backend's clips (the render
   cache keys on backend voice and model), so its next packages re-render.

**Upgrading from a pre-split llama.** If you ran llama before scripting/
presenters/TTS moved to emcee ("the cut"), three settings in your existing
`~/.llama/` are now **silently ignored** — pydantic drops unknown fields
without a warning, so nothing errors, shows just stop being voiced:

- `~/.llama/config.toml`'s `[tts]` block. Move it into emcee's own config
  (`emcee config init`), under emcee's own `[tts]` — same keys (`backend`,
  `voice`, `voice_clone`, `chunk`, `bed`, `bed_gain_db`, etc.), different
  file.
- Each `~/.llama/profiles/<name>.toml`'s `presenter =` / `title =` fields.
  Translate each one into an `[assign.profiles.<profile-name>]` block in
  emcee's config (`presenter = "..."`, optional `title = "..."`) — see
  "Assigning a presenter to a llama profile" above.
- `~/.llama/presenters/*.toml`. Copy them to `~/.emcee/presenters/` (or
  `EMCEE_ROOT`/`root`'s `presenters/` if you've relocated emcee's
  workspace) — the TOML shape is unchanged, so a straight file copy works;
  `emcee presenter list` will pick them up from there.

The reassuring corollary: this is purely additive risk, not a data-loss
one. Packages you already delivered under the old llama, whose manifests
carry llama-written `dj_notes`/`dj_audio` blocks, are seen as `ready` by
`station.readiness` and `emcee run` leaves them untouched (with no artist rules and no moves; a rule or move that changes a show's profile makes it pending, and `emcee run` asks before re-voicing it) — there is no
re-spend on your existing library. Only shows delivered *after* the cut,
still `pending`, are affected by the silent-ignore above.

## Licensing

Both llama and emcee are licensed under **GPL-3.0-or-later**; see
[LICENSE](LICENSE) (and `packages/emcee/LICENSE`, an identical copy) for
the full text. `packages/llama/src/llama/data/set_breaks.csv` is vendored
from the [eichblatt/deadstream](https://github.com/eichblatt/deadstream)
project (also GPL-3.0) — see `packages/llama/src/llama/data/README.md` for
vendoring details and attribution.
