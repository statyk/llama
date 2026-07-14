import pytest

from llama.config import Config, LLMTaskConfig
from llama.llm import DEFAULT_TIERS, TIER_MODELS, provider_for, resolve_model
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
