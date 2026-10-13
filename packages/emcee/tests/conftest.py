"""No emcee test may see the operator's real API keys: the missing-key tests
and the strict-surface tests set exactly the keys they mean."""
import pytest


@pytest.fixture(autouse=True)
def _no_ambient_tts_keys(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
