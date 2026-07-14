# llama

Finds concerts on archive.org's Live Music Archive, vets them for quality,
researches the specific performance, and packages audio + DJ notes for an
automated radio station.

## Setup

    python3 -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev]"

Optional config at `~/.llama/config.toml`:

    root = "/path/to/workdir"        # default ~/.llama
    delivery_path = "/station/inbox" # for `llama deliver`
    audio_format = "mp3"             # or "flac"

    [llm.default]
    backend = "claude_cli"           # requires the `claude` CLI on PATH
    # Model tiers: low=haiku, medium=sonnet, high=opus (claude_cli).
    # Defaults: sonnet for most tasks; opus for deep_research and synthesize.

    [llm.synthesize]
    # tier = "medium"                # example: cheaper synthesis
    # model = "claude-opus-4-8"      # example: exact pin, bypasses tiers

## Use

    llama find "GD shows 73-74 with a china>rider"
    llama find "top 10 Grateful Dead shows of the 1980s" --auto
    llama find "well-known folk/acoustic performer, 1960s-70s, highly rated"
                                     # artist-less queries propose artists first
                                     # (interactive runs let you prune the list)
    llama profile add sunday-dead-hour "classic Grateful Dead" --count 1 --human-gate
    llama profile run sunday-dead-hour
    llama review <run-dir>           # approve/prune a shortlist
    llama deliver <show-dir>         # copy package to the station inbox
    llama ledger list                # broadcast history / dedup

## Tests

    pytest -q          # offline suite
    pytest -m live -q  # hits real archive.org (no LLM)

See `docs/superpowers/specs/2026-07-14-llama-design.md` for the design.
