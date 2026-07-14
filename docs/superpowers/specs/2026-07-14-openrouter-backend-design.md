# OpenRouter Backend — Design

**Date:** 2026-07-14
**Status:** Approved design, pending implementation plan
**Extends:** `2026-07-14-llama-design.md` (LLM layer), `2026-07-14-model-tiers-design.md`
(implements everything that spec deferred to "the OpenRouter phase")

## Problem

The LLM layer has one real backend (`claude_cli`, a subprocess) plus the `fake`
test backend. The provider protocol, tier vocabulary, and config shapes were
built to accommodate a second, HTTP-based backend; this design adds it. Three
items were explicitly deferred to this phase and are all in scope, plus one
rider:

1. The `openrouter` backend and its `TIER_MODELS` entry.
2. `[llm.tiers]` config retargeting of what each tier resolves to.
3. Auto-select heuristics — specifically escalate-on-retry.
4. (Rider) Converting the tier-table `KeyError` in `resolve_model` to
   `LLMError` — reachable now that a tier table can be user-modified.

## Provider

`OpenRouterProvider` in `src/llama/llm/openrouter.py`, implementing the
existing `LLMProvider` protocol. Direct `httpx` (already a dependency) against
OpenRouter's OpenAI-compatible endpoint — no new packages, no SDK.

- `complete(prompt)` — POST `https://openrouter.ai/api/v1/chat/completions`
  with `{"model": <model>, "messages": [{"role": "user", "content": prompt}]}`;
  returns `choices[0].message.content`.
- `research(brief)` — same call plus `"plugins": [{"id": "web"}]`
  (OpenRouter's web-search plugin). Both capabilities are supported;
  `ResearchNotSupported` is not raised by this backend. The plugin is
  single-shot search grounding, not agentic multi-step research — acceptable
  per the approving decision, with claude_cli remaining the default backend.
- Constructor: `model: str` (required — resolution always yields a concrete
  model), `api_key: str | None = None` (falls back to the `OPENROUTER_API_KEY`
  env var; missing key raises `LLMError` at construction, so a misconfigured
  run fails at `make_providers` time, not mid-pipeline), `timeout_s: int = 900`
  (parity with `ClaudeCLIProvider`).
- Error posture mirrors `ClaudeCLIProvider`: transport failure or timeout,
  non-200 status, unparseable JSON body, or a missing/non-string content field
  each raise `LLMError` carrying a truncated (~500 char) excerpt of the
  offending payload. No transport-level retries in v1 — stages are resumable
  and the claude_cli backend has none either.

### Shipped tier defaults

Cross-vendor value picks (exact slugs verified against the live OpenRouter
catalog during implementation; these are the intended targets):

```python
TIER_MODELS["openrouter"] = {
    "low": "google/gemini-2.5-flash",
    "medium": "anthropic/claude-sonnet-4.5",
    "high": "anthropic/claude-opus-4.1",
}
```

The default backend remains `claude_cli`. OpenRouter is opt-in:

```toml
[llm.default]
backend = "openrouter"        # everything via OpenRouter

[llm.deep_research]
backend = "claude_cli"        # ...except agentic research, if desired
```

## Config: `[llm.tiers]` retargeting

Per-backend overlay on the shipped tier tables:

```toml
[llm.tiers.openrouter]
medium = "deepseek/deepseek-chat-v3"

[llm.tiers.claude_cli]
high = "sonnet"
```

Implementation: `Config.llm` is `dict[str, LLMTaskConfig]`, and TOML nests
`[llm.tiers.*]` inside that table. A `model_validator(mode="before")` on
`Config` pops the `"tiers"` key from the raw `llm` mapping into a new field:

```python
tiers: dict[str, dict[str, str]] = Field(default_factory=dict)
```

`tiers` is thereby a reserved name in the `[llm]` section (no task is named
that). Tier keys are validated against `{"low", "medium", "high"}` at load
time — an unknown tier key is a config error, consistent with existing
strictness. Backend names and model values are free strings (a typo'd backend
name is inert, matching how `[llm.<task>] backend` behaves today).

### Resolution

`resolve_model` order is unchanged — explicit task `model` → explicit task
`tier` → `DEFAULT_TIERS[task]` → `"medium"` — but every tier lookup consults
the merged table:

```python
table = TIER_MODELS.get(backend, {}) | config.tiers.get(backend, {})
```

Consequences:

- A config overlay can retarget individual tiers without restating the rest.
- A backend unknown to `TIER_MODELS` but fully defined under `[llm.tiers]`
  still fails at `provider_for` (no constructor for it) — the merge does not
  invent backends.
- A tier missing from the merged table raises `LLMError` naming the backend
  and tier (the deferred `KeyError` conversion).

## Escalate-on-retry

Policy (as approved): attempts 1–2 of a JSON task run at the resolved tier
(the existing error-feedback retry); the final attempt runs **one tier up**
(`low→medium`, `medium→high`, `high→high`), always on the same backend.
Explicit per-task `model` pins never escalate. Research tasks have no
validation loop and never escalate.

Mechanism:

- New `provider_ladder(config, task) -> list[LLMProvider]` in
  `llama/llm/__init__.py` returns one provider per attempt:
  `[base, base, escalated]` for the standard `retries=2`. When the escalated
  tier equals the base tier (already `high`, or model-pinned), the ladder is
  `[base, base, base]` — construction may reuse the same provider instance.
- `make_providers` in `pipeline.py` builds ladders instead of single
  providers; stage call sites pass them through unchanged.
- `run_json_task(provider, ...)` accepts either a single `LLMProvider`
  (unchanged behavior — existing tests and `FakeProvider` usage keep working)
  or a sequence of them; attempt *i* uses `ladder[min(i, len(ladder) - 1)]`.
  `run_research_task` accepts the same union for call-site uniformity and uses
  the first element.
- `TaskFailed` on exhaustion is unchanged (message + raw output preserved).

## Testing

All offline, per project convention. No live OpenRouter test in CI; the live
smoke test remains manual/opt-in.

- **Provider** (`httpx.MockTransport`): happy path returns content;
  `research()` sends `plugins=[{"id": "web"}]` and `complete()` does not;
  non-200 → `LLMError`; missing API key → `LLMError` at construction;
  malformed/contentless body → `LLMError`.
- **Resolution:** `[llm.tiers.openrouter]` overlay beats the shipped table;
  shipped openrouter defaults resolve per tier; missing tier in merged table →
  `LLMError` (not `KeyError`); unknown tier key under `[llm.tiers.*]` fails
  `load_config`; `provider_for` constructs `OpenRouterProvider` for
  `backend = "openrouter"`.
- **Escalation:** with a two-fake ladder, two schema-invalid responses from
  the base fake are followed by a valid response served by the escalated fake;
  a model-pinned task's ladder contains only base-tier providers; a high-tier
  task retries at high. Bare-provider calls to `run_json_task` still pass
  (regression).

## Docs

README and CLAUDE.md: OpenRouter setup (`OPENROUTER_API_KEY`, opt-in backend
selection), `[llm.tiers]` example, escalation semantics (one tier up on final
attempt; pins never escalate).

## Out of scope

- Transport-level retry/backoff for HTTP errors (stages are resumable).
- A generic OpenAI-compatible backend (`base_url` config) — the web plugin is
  OpenRouter-specific; revisit if a third backend ever appears.
- OpenRouter structured-output/`response_format` support — the existing
  `extract_json` + validation-retry loop already handles output discipline
  uniformly across backends.
- The deferred pipeline/CLI minors from the 2026-07-14 build session (winnow
  artist label, `discover` stage re-run, replay drift, untested paths) — none
  touch the LLM layer.
