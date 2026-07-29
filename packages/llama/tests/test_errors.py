import pytest

from llama.errors import ArtistResolutionError, LlamaError
from llama.ia_client import IAError
from llama.catalog import CatalogError
from llama.llm.provider import LLMError, ResearchNotSupported, TaskFailed


def test_custom_exceptions_subclass_llama_error():
    for exc in (IAError, CatalogError, ArtistResolutionError):
        assert issubclass(exc, LlamaError)


def test_llm_errors_independent_of_llama_taxonomy():
    # The LLM layer is bound for extraction into the shared herder package:
    # its exceptions must not depend on llama's taxonomy.
    assert not issubclass(LLMError, LlamaError)
    assert issubclass(TaskFailed, LLMError)
    assert issubclass(ResearchNotSupported, LLMError)


def test_main_cli_renders_llm_error(monkeypatch, capsys):
    from llama import cli

    def boom():
        raise TaskFailed("model exploded")

    monkeypatch.setattr(cli, "app", boom)
    with pytest.raises(SystemExit) as exc:
        cli.main_cli()
    assert exc.value.code == 1
    assert "error: model exploded" in capsys.readouterr().err


def test_llama_error_details_default_empty():
    assert LlamaError("boom").details == []
    assert str(LlamaError("boom")) == "boom"


def test_catalog_error_details_mirror_matches():
    e = CatalogError("no run matches 'x'", ["run-a", "run-b"])
    assert e.matches == ["run-a", "run-b"]
    assert e.details == ["run-a", "run-b"]


def test_catalog_error_without_matches():
    e = CatalogError("boom")
    assert e.matches == []
    assert e.details == []
