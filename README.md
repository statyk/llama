# llama

Finds concerts on archive.org's Live Music Archive, vets them for quality,
researches the specific performance (fact-checking the research against the
setlist before it ships), and packages audio + notes for an automated radio
station. A verbatim DJ script is included by default (`--no-script`, or
`script = false` on a profile, opts out).

## Setup

    python3 -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev]"

Optional config at `~/.llama/config.toml`:

    root = "/path/to/workdir"        # default ~/.llama
    delivery_path = "/station/inbox" # for `llama deliver`
    audio_format = "mp3"             # or "flac"

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
    # Defaults: medium for most tasks; high for deep_research and synthesize.
    # If a task's output fails validation twice, the final retry runs one
    # tier up (exact `model` pins never escalate).

    [llm.deep_research]
    # backend = "claude_cli"         # recommended when the default backend is
    # openrouter: openrouter research is single-shot web-search grounding,
    # weaker than the claude CLI's agentic multi-step research, and research
    # quality is audible on air. Mixing backends per task is supported.

    [llm.synthesize]
    # tier = "medium"                # example: cheaper synthesis
    # model = "claude-opus-4-8"      # example: exact pin, bypasses tiers

    [llm.tiers.openrouter]
    # medium = "deepseek/deepseek-chat-v3"  # retarget what a tier means per backend

## Use

    llama find "GD shows 73-74 with a china>rider"
    llama find "top 10 Grateful Dead shows of the 1980s" --auto
    llama find "well-known folk/acoustic performer, 1960s-70s, highly rated"
                                     # artist-less queries match artists against the index first
                                     # (interactive runs let you prune the list)
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
    llama profile run sunday-dead-hour
    llama review <run-dir>           # approve a shortlist, optionally process it
    llama run <run-dir>              # resume/replay a run; finished stages are skipped
    llama show <show-dir> [--clear]  # inspect (or overrule) a needs-review hold
    llama deliver <show-dir>         # copy package to the station inbox
    llama ledger list                # broadcast history / dedup

Two different human gates, easy to conflate: `llama review` answers "which
shortlisted shows are worth processing" (gate 1). Separately, a processed
show can be held as **needs-review** when a stage flags something suspicious
(`needs-review, skipped: ...`, gate 2) — inspect and clear that with
`llama show`. See [docs/workflow.md](docs/workflow.md) for the full pipeline
map, every flag, and a troubleshooting table — start there if a run didn't
do what you expected.

### Explore artists

    llama artists "jangly 80s college rock"     # NL search, ranked with stats
    llama artists                               # deepest catalogs, no LLM call
    llama artists --all "obscure tape scene"    # include the long tail
    llama artists --refresh                     # force an index rebuild

The first call builds a local artist index (one collections request plus
~30 scrape pages over all LMA items, about a minute); it auto-refreshes
after 30 days. Small collections are hidden unless they clear the
`[artists]` thresholds in config (defaults: 25 recordings or 50k
downloads); `--min-recordings` / `--min-downloads` / `--all` override
per invocation.

## Tests

    pytest -q          # offline suite
    pytest -m live -q  # hits real archive.org (no LLM)

See `docs/superpowers/specs/2026-07-14-llama-design.md` for the design.

## Package format (v2)

A delivered show package contains:

- `audio/` — verified, tagged tracks (`01 - Morning Dew.mp3`, ...)
- `playlist.m3u`
- `manifest.json` — `schema_version: 2`; tracks, set breaks, durations,
  source lineage, `show.context`, pointers `research` / `reviews`, and
  `research_vetted`
- `research.md` — web-researched show notes, grounding-checked against the
  setlist (`vet` stage) before packaging
- `reviews.md` — trimmed listener-review digest (top 5, 800 chars each)
- `dj-notes.md` + `manifest.dj_notes` — verbatim DJ script, present by
  default; absent when the run opted out (`--no-script`, or `script = false`
  on a profile)

### Script mode does not change the data

Whether a run generated a script has no effect on the content or quality of
anything else in the package. Research runs before the script decision is
consulted (same prompt, same inputs, same model tier), the vet grounding
check runs unconditionally right after it, and `reviews.md` and the
manifest's show data (including `show.context`, which comes from the vet
extraction) are built identically in both modes. `research.md` is the same
bytes either way.

The two modes differ only in scrutiny and availability, and both
differences err safe:

- **Script-on packages cleared one extra gate.** The generated script is
  cross-checked against the setlist (`factual_guard`), which occasionally
  catches prose-level research contamination that assertion-level vetting
  can't see — a wrong-show anecdote surfacing as a bad song name in the
  patter. A script-on run may therefore hold a subtly-bad show for review
  that a script-off run would ship.
- **Script-on runs have one extra failure point.** A synthesize call that
  exhausts its retries skips the show entirely — it affects whether a
  package is produced, never what's inside one.

Consumers can rely on `research.md`, `reviews.md`, and the manifest meaning
exactly the same thing regardless of mode; the script setting only
determines whether the script artifacts exist.

### Downstream synthesis contract

If your DJ (human or LLM) writes its own spoken copy from this package, it
inherits the factual guard this pipeline applies to its own scripts:

- every song mentioned must match a track title in `manifest.tracks`
- set intros must cover exactly the sets present in `manifest.tracks[].set`
- one break note per entry in `manifest.set_breaks`

Copy that names songs or sets not in the manifest must not air.
