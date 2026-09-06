import pytest


def cli_invoke(cfg_path, *args, **kwargs):
    """Invoke the app with the callback-level --config. Extra kwargs (e.g.
    `input=...` for scripted stdin) pass through to `CliRunner.invoke`."""
    from typer.testing import CliRunner
    import llama.cli as cli
    return CliRunner().invoke(cli.app, ["--config", str(cfg_path), *args], **kwargs)


@pytest.fixture(autouse=True)
def _no_ambient_setlistfm_key(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_ambient_elevenlabs_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_ambient_mistral_key(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_live_usage_meter(monkeypatch):
    """No test may spawn `claude -p "/usage"`.

    A default Config resolves to the claude_cli backend, so without this every
    test reaching _execute shells out to the real CLI once per gate -- slow,
    non-deterministic, and a network call from a suite contracted to be
    offline. Tests that want a reading override this with their own
    monkeypatch, which runs after the autouse fixture.
    """
    import llama.cli as cli
    monkeypatch.setattr(cli, "read_usage", lambda *a, **kw: None, raising=False)
