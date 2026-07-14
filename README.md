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
