import json

import httpx
import pytest

from llama.llm.openrouter import OpenRouterProvider
from llama.llm.provider import LLMError, LLMProvider


def ok_payload(text="hi"):
    return {"choices": [{"message": {"content": text}}]}


def make_provider(handler):
    return OpenRouterProvider(
        model="test/model", api_key="k", transport=httpx.MockTransport(handler)
    )


def test_complete_posts_model_and_prompt():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json=ok_payload("hello"))

    p = make_provider(handler)
    assert p.complete("say hello") == "hello"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["body"]["model"] == "test/model"
    assert seen["body"]["messages"] == [{"role": "user", "content": "say hello"}]
    assert "plugins" not in seen["body"]
    assert seen["auth"] == "Bearer k"


def test_research_adds_web_plugin():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_payload("found"))

    assert make_provider(handler).research("dig") == "found"
    assert seen["body"]["plugins"] == [{"id": "web"}]


def test_missing_api_key_raises_at_construction(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider(model="test/model")


def test_env_var_supplies_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    p = OpenRouterProvider(model="test/model")
    assert p.api_key == "from-env"


def test_non_200_raises():
    p = make_provider(lambda r: httpx.Response(429, text="rate limited"))
    with pytest.raises(LLMError, match="429"):
        p.complete("x")


def test_transport_error_raises():
    def handler(request):
        raise httpx.ConnectError("no route to host")

    with pytest.raises(LLMError, match="request failed"):
        make_provider(handler).complete("x")


def test_bad_json_raises():
    p = make_provider(lambda r: httpx.Response(200, text="not json"))
    with pytest.raises(LLMError, match="not JSON"):
        p.complete("x")


def test_missing_content_raises():
    p = make_provider(lambda r: httpx.Response(200, json={"choices": []}))
    with pytest.raises(LLMError, match="missing content"):
        p.complete("x")


def test_non_string_content_raises():
    p = make_provider(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
    )
    with pytest.raises(LLMError):
        p.complete("x")


def test_satisfies_protocol():
    p = make_provider(lambda r: httpx.Response(200, json=ok_payload()))
    assert isinstance(p, LLMProvider)
