import pytest


def cli_invoke(cfg_path, *args):
    """Invoke the app with the callback-level --config."""
    from typer.testing import CliRunner
    import llama.cli as cli
    return CliRunner().invoke(cli.app, ["--config", str(cfg_path), *args])


@pytest.fixture(autouse=True)
def _no_ambient_setlistfm_key(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_ambient_elevenlabs_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_ambient_mistral_key(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
