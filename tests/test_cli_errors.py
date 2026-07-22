import pytest

import llama.cli as cli
from llama.catalog import CatalogError
from llama.errors import LlamaError


def _run_with(monkeypatch, boom):
    monkeypatch.setattr(cli, "app", boom)
    with pytest.raises(SystemExit) as excinfo:
        cli.main_cli()
    return excinfo.value


def test_llama_error_prints_clean_message(monkeypatch, capsys):
    exc = _run_with(monkeypatch, lambda: (_ for _ in ()).throw(
        LlamaError("OpenRouter API key missing: set OPENROUTER_API_KEY")))
    err = capsys.readouterr().err
    assert exc.code == 1
    assert err.strip() == "error: OpenRouter API key missing: set OPENROUTER_API_KEY"
    assert "Traceback" not in err


def test_catalog_error_details_are_indented(monkeypatch, capsys):
    _run_with(monkeypatch, lambda: (_ for _ in ()).throw(
        CatalogError("'19' is ambiguous", ["run-a", "run-b"])))
    err = capsys.readouterr().err
    assert "error: '19' is ambiguous" in err
    assert "  run-a" in err
    assert "  run-b" in err


def test_keyboard_interrupt_exits_130(monkeypatch, capsys):
    exc = _run_with(monkeypatch, lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert exc.code == 130
    assert "Traceback" not in capsys.readouterr().err


def test_unexpected_error_shows_plain_traceback(monkeypatch, capsys):
    exc = _run_with(monkeypatch, lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    err = capsys.readouterr().err
    assert exc.code == 1
    assert "Traceback (most recent call last)" in err
    assert "RuntimeError: boom" in err
    assert "Failed to execute script" not in err
