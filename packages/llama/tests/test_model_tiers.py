import pytest

from llama.llm import (
    TIER_MODELS,
    LLMSettings,
    TaskConfig,
    provider_for,
    provider_ladder,
    resolve_model,
)
from llama.llm.openrouter import OpenRouterProvider
from llama.llm.provider import LLMError


def settings(**kw):
    return LLMSettings(default_tiers={"deep_research": "high", "vet_research": "low"}, **kw)


def test_task_default_tier_resolves():
    assert resolve_model(settings(), "deep_research") == ("claude_cli", "opus")


def test_unknown_task_defaults_to_medium():
    assert resolve_model(settings(), "interpret") == ("claude_cli", "sonnet")


def test_explicit_model_pin_wins():
    s = settings(tasks={"interpret": TaskConfig(model="claude-opus-4-8")})
    assert resolve_model(s, "interpret") == ("claude_cli", "claude-opus-4-8")


def test_tier_table_overlay():
    s = settings(tiers={"openrouter": {"medium": "deepseek/deepseek-chat-v3"}},
                 tasks={"default": TaskConfig(backend="openrouter")})
    assert resolve_model(s, "interpret") == ("openrouter", "deepseek/deepseek-chat-v3")


def test_explicit_tier_beats_task_default():
    s = settings(tasks={"synthesize": TaskConfig(tier="medium")})
    assert resolve_model(s, "synthesize") == ("claude_cli", "sonnet")
    s = settings(tasks={"interpret": TaskConfig(tier="low")})
    assert resolve_model(s, "interpret") == ("claude_cli", "haiku")


def test_explicit_model_beats_tier_even_when_both_set():
    s = settings(tasks={"synthesize": TaskConfig(tier="low", model="claude-opus-4-8")})
    assert resolve_model(s, "synthesize") == ("claude_cli", "claude-opus-4-8")


def test_default_entry_tier_floors_unpinned_tasks():
    s = settings(tasks={"default": TaskConfig(tier="low")})
    assert resolve_model(s, "interpret") == ("claude_cli", "haiku")
    # synthesize has no entry of its own, so the default entry's tier wins
    assert resolve_model(s, "synthesize") == ("claude_cli", "haiku")
    # ...but a task with its own entry ignores the default entry entirely
    s = settings(tasks={"default": TaskConfig(tier="low"),
                         "synthesize": TaskConfig(tier="high")})
    assert resolve_model(s, "synthesize") == ("claude_cli", "opus")


def test_unknown_backend_still_raises():
    s = settings(tasks={"default": TaskConfig(backend="nope")})
    with pytest.raises(LLMError):
        provider_for(s, "interpret")


def test_resolve_model_returns_backend_and_model():
    s = LLMSettings(default_tiers={"synthesize": "high"})
    assert resolve_model(s, "synthesize") == ("claude_cli", "opus")


def test_tables_match_spec():
    assert TIER_MODELS["claude_cli"] == {"low": "haiku", "medium": "sonnet", "high": "opus"}


def test_openrouter_tier_table_matches_spec():
    assert TIER_MODELS["openrouter"] == {
        "low": "google/gemini-2.5-flash",
        "medium": "anthropic/claude-sonnet-4.5",
        "high": "anthropic/claude-opus-4.1",
    }


def test_openrouter_backend_resolves_and_constructs(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    s = settings(tasks={"default": TaskConfig(backend="openrouter")})
    assert resolve_model(s, "interpret") == ("openrouter", "anthropic/claude-sonnet-4.5")
    assert resolve_model(s, "deep_research") == ("openrouter", "anthropic/claude-opus-4.1")
    p = provider_for(s, "interpret")
    assert isinstance(p, OpenRouterProvider)
    assert p.model == "anthropic/claude-sonnet-4.5"


def test_openrouter_without_key_fails_fast(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    s = settings(tasks={"default": TaskConfig(backend="openrouter")})
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        provider_for(s, "interpret")


def test_config_tiers_overlay_beats_shipped_table():
    s = settings(tiers={"openrouter": {"medium": "deepseek/deepseek-chat-v3"}},
                 tasks={"default": TaskConfig(backend="openrouter")})
    assert resolve_model(s, "interpret") == ("openrouter", "deepseek/deepseek-chat-v3")
    # tiers the overlay doesn't touch still come from the shipped table
    assert resolve_model(s, "deep_research") == ("openrouter", "anthropic/claude-opus-4.1")


def test_overlay_applies_to_claude_cli_too():
    s = settings(tiers={"claude_cli": {"high": "sonnet"}})
    assert resolve_model(s, "deep_research") == ("claude_cli", "sonnet")


def test_missing_tier_raises_llmerror_not_keyerror():
    s = settings(tasks={"default": TaskConfig(backend="custom")},
                 tiers={"custom": {"low": "x/y"}})
    with pytest.raises(LLMError, match="tier"):
        resolve_model(s, "interpret")  # interpret needs medium; table only has low


def test_tiers_only_backend_fails_at_provider_construction():
    s = settings(tasks={"default": TaskConfig(backend="custom", tier="low")},
                 tiers={"custom": {"low": "x/y"}})
    assert resolve_model(s, "interpret") == ("custom", "x/y")
    with pytest.raises(LLMError, match="unknown LLM backend"):
        provider_for(s, "interpret")


def test_ladder_escalates_final_attempt(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    s = settings(tasks={"default": TaskConfig(backend="openrouter")})
    ladder = provider_ladder(s, "interpret")  # medium task: final rung one tier up
    assert [p.model for p in ladder] == [
        "anthropic/claude-sonnet-4.5",
        "anthropic/claude-sonnet-4.5",
        "anthropic/claude-opus-4.1",
    ]


def test_ladder_high_tier_has_no_headroom():
    ladder = provider_ladder(settings(), "deep_research")
    assert [p.model for p in ladder] == ["opus", "opus", "opus"]


def test_ladder_model_pin_never_escalates():
    s = settings(tasks={"interpret": TaskConfig(model="claude-opus-4-8")})
    ladder = provider_ladder(s, "interpret")
    assert [p.model for p in ladder] == ["claude-opus-4-8"] * 3


def test_ladder_low_tier_escalates_to_medium():
    s = settings(tasks={"default": TaskConfig(backend="claude_cli", tier="low")},
                 tiers={"claude_cli": {"medium": "sonnet-cheap"}})
    # low escalates to medium, and the escalated rung honors the config overlay
    assert [p.model for p in provider_ladder(s, "interpret")] == [
        "haiku", "haiku", "sonnet-cheap"]
