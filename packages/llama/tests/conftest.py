import pytest


def cli_invoke(cfg_path, *args, **kwargs):
    """Invoke the app with the callback-level --config. Extra kwargs (e.g.
    `input=...` for scripted stdin) pass through to `CliRunner.invoke`."""
    from typer.testing import CliRunner
    import llama.cli as cli
    return CliRunner().invoke(cli.app, ["--config", str(cfg_path), *args], **kwargs)


def output_without_paths(result, tmp_path) -> str:
    """`result.output` with every line mentioning the workspace root removed.

    A whole-output negative -- `assert "x" not in result.output` -- can match
    pytest's `tmp_path`, which embeds THE TEST'S OWN NAME truncated to 30
    characters. `test_no_dropped_clause_when_nothing_was_dropped` gets the
    directory `test_no_dropped_clause_when_no0`, so `assert "dropped" not in
    result.output` was matching its own path and grading itself. That one
    failed loudly by luck of naming; the silent form is one rename away.

    `llama show` prints the workspace path on its `state:` line, which is the
    whole injection vector, so removing lines that mention the root leaves a
    view a negative can safely be asserted over. Prefer scoping a negative to
    the ONE line it is really about; use this when the claim genuinely is
    "nowhere in the output".
    """
    root = str(tmp_path)
    return "\n".join(ln for ln in result.output.splitlines() if root not in ln)


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
