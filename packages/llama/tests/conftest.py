import importlib.util

import pytest


def pytest_collection_modifyitems(config, items):
    """`real_model` tests load the bundled ONNX model: skip them without onnxruntime."""
    if importlib.util.find_spec("onnxruntime") is not None:
        return
    skip = pytest.mark.skip(reason="onnxruntime is not installed")
    for item in items:
        if "real_model" in item.keywords:
            item.add_marker(skip)


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

    REDACTS the root rather than dropping the lines that mention it, and the
    difference is not cosmetic: dropping whole lines removed more than the
    vector, and made `test_default_selector_walks_held_only` VACUOUS -- for a
    non-held show the slug appears ONLY on the `state: ... path: ...` line, so
    the assertion could no longer fail. Caught by review, with the mutant that
    proved it (triage's default selector also walking packaged shows) leaving
    the converted test green. Redaction removes exactly the injected substring
    and nothing else.

    Prefer scoping a negative to the ONE line it is really about; use this when
    the claim genuinely is "nowhere in the output".
    """
    return result.output.replace(str(tmp_path), "<ROOT>")


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


@pytest.fixture(autouse=True)
def _no_ambient_adjudication(monkeypatch):
    """No test may adjudicate on the config default.

    `[adjudicate] enabled` defaults to true, so without this every test whose show
    ends held in `get`, `run approve`, `run resume` or `redo` would make an
    adjudicator call -- a hook the test never asked for, spending from a provider
    map that has no `adjudicate` entry. Only an explicit `--adjudicate` (or a test
    re-patching `cli._adjudicate_enabled` to `runner.hook_enabled`, which runs
    after this autouse fixture) adjudicates.
    """
    import llama.cli as cli
    monkeypatch.setattr(cli, "_adjudicate_enabled", lambda config, flag: bool(flag),
                        raising=False)


class _NoRealAudioModel:
    """What the faked `classify.get_model` returns: running it is a test bug."""

    def frame_scores(self, wave):
        raise AssertionError("a test ran the audio classifier model; take `real_classify` "
                             "and fake `model.load`, or mark it `real_model`")


@pytest.fixture(autouse=True)
def _no_real_audio_classifier(request, monkeypatch):
    """No test loads the real YAMNet runtime or classifies real audio (Task 6).

    `classify.get_model` returns a stub that refuses to run, and
    `classify.classify_file` returns a fixed `junk` verdict, so a pipeline test whose
    gather checks a junk-title drop gets an ordinary `junk` outcome: no hold, no
    change. Tests marked `real_model` keep both real. A test that needs the real
    `classify_file` over a faked `model.load` takes `real_classify`. Yields the real
    functions (empty for `real_model` tests)."""
    if "real_model" in request.keywords:
        yield {}
        return
    from llama.audio_check import classify

    real = {"get_model": classify.get_model, "classify_file": classify.classify_file}
    monkeypatch.setattr(classify, "get_model", lambda: _NoRealAudioModel())
    monkeypatch.setattr(classify, "classify_file",
                        lambda path: classify.Result("junk", 0, 0.0))
    yield real


@pytest.fixture
def real_classify(monkeypatch, _no_real_audio_classifier):
    """Restore the real `classify.get_model` and `classify.classify_file` after the
    autouse fake (the test still fakes `model.load`, so nothing real loads)."""
    from llama.audio_check import classify

    for name, fn in _no_real_audio_classifier.items():
        monkeypatch.setattr(classify, name, fn)
