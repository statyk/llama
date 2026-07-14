import pytest

from llama.config import Config, LLMTaskConfig
from llama.llm import DEFAULT_TIERS, TIER_MODELS, provider_for, resolve_model
from llama.llm.openrouter import OpenRouterProvider
from llama.llm.provider import LLMError


def test_out_of_box_defaults_are_concrete():
    cfg = Config()
    assert provider_for(cfg, "interpret").model == "sonnet"
    assert provider_for(cfg, "score_reviews").model == "sonnet"
    assert provider_for(cfg, "deep_research").model == "opus"
    assert provider_for(cfg, "synthesize").model == "opus"
    assert provider_for(cfg, "some_future_task").model == "sonnet"  # medium fallback


def test_explicit_tier_beats_task_default():
    cfg = Config(llm={"synthesize": LLMTaskConfig(tier="medium")})
    assert provider_for(cfg, "synthesize").model == "sonnet"
    cfg = Config(llm={"interpret": LLMTaskConfig(tier="low")})
    assert provider_for(cfg, "interpret").model == "haiku"


def test_explicit_model_beats_tier():
    cfg = Config(llm={"synthesize": LLMTaskConfig(tier="low", model="claude-opus-4-8")})
    assert provider_for(cfg, "synthesize").model == "claude-opus-4-8"


def test_default_entry_tier_floors_unpinned_tasks():
    cfg = Config(llm={"default": LLMTaskConfig(tier="low")})
    assert provider_for(cfg, "interpret").model == "haiku"
    # synthesize has no entry of its own, so the default entry's tier wins
    assert provider_for(cfg, "synthesize").model == "haiku"
    # ...but a task with its own entry ignores the default entry entirely
    cfg = Config(llm={"default": LLMTaskConfig(tier="low"),
                      "synthesize": LLMTaskConfig(tier="high")})
    assert provider_for(cfg, "synthesize").model == "opus"


def test_unknown_backend_still_raises():
    cfg = Config(llm={"default": LLMTaskConfig(backend="nope")})
    with pytest.raises(LLMError):
        provider_for(cfg, "interpret")


def test_resolve_model_returns_backend_and_model():
    assert resolve_model(Config(), "synthesize") == ("claude_cli", "opus")


def test_tables_match_spec():
    assert TIER_MODELS["claude_cli"] == {"low": "haiku", "medium": "sonnet", "high": "opus"}
    assert DEFAULT_TIERS == {
        "interpret": "medium", "score_reviews": "medium",
        "light_research": "medium", "extract_setlist": "medium",
        "deep_research": "high", "synthesize": "high",
        "propose_artists": "medium",
        "align_structure": "medium",
    }


def test_openrouter_tier_table_matches_spec():
    assert TIER_MODELS["openrouter"] == {
        "low": "google/gemini-2.5-flash",
        "medium": "anthropic/claude-sonnet-4.5",
        "high": "anthropic/claude-opus-4.1",
    }


def test_openrouter_backend_resolves_and_constructs(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    cfg = Config(llm={"default": LLMTaskConfig(backend="openrouter")})
    assert resolve_model(cfg, "interpret") == ("openrouter", "anthropic/claude-sonnet-4.5")
    assert resolve_model(cfg, "synthesize") == ("openrouter", "anthropic/claude-opus-4.1")
    p = provider_for(cfg, "interpret")
    assert isinstance(p, OpenRouterProvider)
    assert p.model == "anthropic/claude-sonnet-4.5"


def test_openrouter_without_key_fails_fast(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = Config(llm={"default": LLMTaskConfig(backend="openrouter")})
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        provider_for(cfg, "interpret")


def test_config_tiers_overlay_beats_shipped_table():
    cfg = Config(llm={"default": LLMTaskConfig(backend="openrouter")},
                 tiers={"openrouter": {"medium": "deepseek/deepseek-chat-v3"}})
    assert resolve_model(cfg, "interpret") == ("openrouter", "deepseek/deepseek-chat-v3")
    # tiers the overlay doesn't touch still come from the shipped table
    assert resolve_model(cfg, "synthesize") == ("openrouter", "anthropic/claude-opus-4.1")


def test_overlay_applies_to_claude_cli_too():
    cfg = Config(tiers={"claude_cli": {"high": "sonnet"}})
    assert resolve_model(cfg, "synthesize") == ("claude_cli", "sonnet")


def test_missing_tier_raises_llmerror_not_keyerror():
    cfg = Config(llm={"default": LLMTaskConfig(backend="custom")},
                 tiers={"custom": {"low": "x/y"}})
    with pytest.raises(LLMError, match="tier"):
        resolve_model(cfg, "interpret")  # interpret needs medium; table only has low


def test_tiers_only_backend_fails_at_provider_construction():
    cfg = Config(llm={"default": LLMTaskConfig(backend="custom", tier="low")},
                 tiers={"custom": {"low": "x/y"}})
    assert resolve_model(cfg, "interpret") == ("custom", "x/y")
    with pytest.raises(LLMError, match="unknown LLM backend"):
        provider_for(cfg, "interpret")
