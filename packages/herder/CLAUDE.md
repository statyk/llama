# herder

The shared LLM layer (`packages/herder/`), used by llama and emcee. Task registries and prompts stay per-app. How llama acts on usage limits is `packages/llama/CLAUDE.md`, "LLM pacing".

LLM model choice is tiered (low/medium/high; haiku/sonnet/opus on claude_cli,
gemini-flash/sonnet-5/opus-5 on openrouter): medium by default, high for
llama's interpret/deep_research/brief and emcee's scriptwrite, low for
vet_research,
overridable per task via `[llm.<task>]` `tier`/`model` or per backend via
`[llm.tiers.<backend>]`; a failed validation's final retry escalates one
tier (pins never escalate).

- **LLM layer:** lives in the shared `herder` package (`packages/herder/`),
  used by both llama and emcee — task registries and prompts stay per-app.
  Provider abstraction with two capabilities — `complete`
  (schema-validated, no tools) and `research` (needs web search). Dev backend
  shells out to headless `claude -p`; `openrouter` is the HTTP alternative
  (opt-in, needs `OPENROUTER_API_KEY`, research via the web plugin); a `fake`
  backend serves tests.
  A usage-window refusal is classified as `herder.limits.RateLimited` (measured
  signature: `You've hit your session limit · resets 11:10am (America/New_York)`),
  carrying the reset instant parsed from the message itself — so pausing needs no
  access to Claude Code's internal state. It is excluded from
  `_with_transport_retry`, which would otherwise spend three more calls against
  an empty window. Every failed `claude -p` is captured whole under
  `~/.llama/llm-failures/`; the 7-day refusal's wording is still unobserved and
  that capture is how it will be learned.
