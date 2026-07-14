import os

import httpx

from llama.llm.provider import LLMError

API_URL = "https://openrouter.ai/api/v1/chat/completions"
# OpenRouter's web-search plugin: single-shot search grounding for research().
WEB_PLUGIN = [{"id": "web"}]


class OpenRouterProvider:
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        timeout_s: int = 900,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise LLMError("OpenRouter API key missing: set OPENROUTER_API_KEY")
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def _chat(self, prompt: str, plugins: list[dict] | None = None) -> str:
        body: dict = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        if plugins:
            body["plugins"] = plugins
        try:
            resp = self._client.post(
                API_URL, json=body, headers={"Authorization": f"Bearer {self.api_key}"}
            )
        except httpx.HTTPError as e:
            raise LLMError(f"openrouter request failed: {e}") from e
        if resp.status_code != 200:
            raise LLMError(f"openrouter returned {resp.status_code}: {resp.text[:500]}")
        try:
            data = resp.json()
        except ValueError as e:
            raise LLMError(f"openrouter response was not JSON: {resp.text[:200]}") from e
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"openrouter response missing content: {str(data)[:500]}") from e
        if not isinstance(content, str):
            raise LLMError(f"openrouter content is not a string: {str(data)[:500]}")
        return content

    def complete(self, prompt: str) -> str:
        return self._chat(prompt)

    def research(self, brief: str) -> str:
        return self._chat(brief, plugins=WEB_PLUGIN)
