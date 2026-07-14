# Model Tiers — Design

**Date:** 2026-07-14
**Status:** Approved design, pending implementation plan
**Extends:** `2026-07-14-llama-design.md` (LLM layer section)

## Problem

Today `Config.llm_for(task)` returns a per-task `{backend, model}` with a
`default` fallback; when no model is configured (the out-of-box state), the
claude CLI backend passes no `--model` flag and every task silently runs on
whatever the user's `claude` session default is — typically the most
expensive model, and not reproducible across machines. The config vocabulary
(exact model strings) is backend-specific and won't port to OpenRouter.

## Design

### Vocabulary

Three tiers: `low`, `medium`, `high`.

`LLMTaskConfig` gains a field alongside `model`:

```python
tier: Literal["low", "medium", "high"] | None = None
```

Invalid tier strings in config fail Pydantic validation at load time.

### Shipped defaults (code, `src/llama/llm/__init__.py`)

```python
DEFAULT_TIERS = {
    "interpret": "medium",
    "score_reviews": "medium",
    "light_research": "medium",
    "extract_setlist": "medium",
    "deep_research": "high",
    "synthesize": "high",
}

TIER_MODELS = {
    "claude_cli": {"low": "haiku", "medium": "sonnet", "high": "opus"},
}
```

Rationale: Sonnet is the workhorse; `deep_research` and `synthesize` are the
two tasks whose quality is audible on air, so they get `high`. The claude CLI
accepts `haiku`/`sonnet`/`opus` aliases, so the table contains no dated model
ids that rot. `low` is defined but unused by defaults — available for user
overrides.

### Resolution (in `provider_for`)

Most specific wins:

1. explicit `model` in the task's config entry (or inherited `default` entry)
2. explicit `tier` in that entry → backend's `TIER_MODELS` table
3. `DEFAULT_TIERS[task]` → backend's table
4. `"medium"` → backend's table (unknown task names)

Unknown backend raises `LLMError` (unchanged). Net effect: `ClaudeCLIProvider`
is always constructed with a concrete model — the silent session-default
inheritance is gone.

### Tunability available immediately

Existing config shapes, no new sections:

```toml
[llm.synthesize]
tier = "medium"            # cheaper synthesis

[llm.interpret]
model = "claude-opus-4-8"  # exact pin, bypasses tiers

[llm.default]
tier = "low"               # floor every unpinned task
```

Note the `default` entry participates in resolution exactly as today: it is
consulted only when the task has no entry of its own, and its `model`/`tier`
follow the same precedence (model beats tier).

### Deferred to the OpenRouter phase

- `[llm.tiers]` config section for retargeting what each tier means globally
- The `openrouter` backend and its `TIER_MODELS` entry
- Auto-select heuristics (e.g. escalate on retry)

## Testing

- Resolution precedence: explicit model beats tier; explicit tier beats task
  default; task default beats the medium fallback; `default`-entry tier
  applies to tasks without their own entry.
- Shipped defaults: `synthesize`/`deep_research` resolve to `opus`,
  `interpret` to `sonnet`.
- Invalid tier string in TOML raises validation error at `load_config`.
- Existing tests are unaffected: provider-level tests construct
  `ClaudeCLIProvider` directly (which still accepts `model=None`), and no
  existing test asserts that `provider_for` returns a model-less provider.
  Add an assertion that out-of-box `provider_for(Config(), "interpret")`
  yields a concrete model ("sonnet").

## Docs

README and CLAUDE.md config examples updated to show tier usage.
