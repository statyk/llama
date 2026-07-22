from llama.errors import ArtistResolutionError, LlamaError
from llama.ia_client import IAError
from llama.catalog import CatalogError
from llama.llm.provider import LLMError, ResearchNotSupported, TaskFailed


def test_custom_exceptions_subclass_llama_error():
    for exc in (IAError, CatalogError, LLMError, ResearchNotSupported,
                TaskFailed, ArtistResolutionError):
        assert issubclass(exc, LlamaError)


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
