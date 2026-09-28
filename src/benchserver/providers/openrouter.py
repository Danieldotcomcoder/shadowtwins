"""OpenRouter adapter.

* Catalog: ``GET /models`` (public) and ``GET /models/{id}/endpoints``; prices are USD per token.
* Completions: ``POST /chat/completions`` with prompt-requested JSON only — no tools, no
  ``response_format``, no ``models`` fallback list. A pinned endpoint is sent as
  ``provider = {order: [slug], allow_fallbacks: false, require_parameters: true}``.
* Sending, error normalization and response parsing are shared with other OpenAI-style providers
  (``openai_compat``).
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import CompletionRequest, EndpointInfo, ModelInfo
from .openai_compat import ChatCompletionsProvider


def _price(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f < 0 else f  # "-1" marks router models with dynamic pricing


def _pricing(p: dict[str, Any] | None) -> dict[str, float | None]:
    p = p or {}
    return {
        "prompt": _price(p.get("prompt")),
        "completion": _price(p.get("completion")),
        "internal_reasoning": _price(p.get("internal_reasoning")),
        "request": _price(p.get("request")),
    }


def parse_model(d: dict[str, Any]) -> ModelInfo:
    arch = d.get("architecture") or {}
    top = d.get("top_provider") or {}
    return ModelInfo(
        provider="openrouter",
        model_id=d["id"],
        name=d.get("name") or d["id"],
        context_length=d.get("context_length"),
        pricing=_pricing(d.get("pricing")),
        supported_parameters=list(d.get("supported_parameters") or []),
        reasoning=d.get("reasoning"),
        max_completion_tokens=top.get("max_completion_tokens"),
        description=(d.get("description") or "")[:600],
        input_modalities=list(arch.get("input_modalities") or []),
        output_modalities=list(arch.get("output_modalities") or []),
    )


def parse_endpoint(e: dict[str, Any]) -> EndpointInfo:
    return EndpointInfo(
        slug=e.get("tag") or (e.get("provider_name") or "").lower(),
        provider_name=e.get("provider_name") or "",
        context_length=e.get("context_length"),
        pricing=_pricing(e.get("pricing")),
        supported_parameters=list(e.get("supported_parameters") or []),
        max_completion_tokens=e.get("max_completion_tokens"),
        quantization=e.get("quantization"),
        status=e.get("status"),
    )


class OpenRouterProvider(ChatCompletionsProvider):
    name = "openrouter"
    key_env = "OPENROUTER_API_KEY"

    def __init__(self, api_key: str | None, base_url: str = "https://openrouter.ai/api/v1",
                 timeout_s: float = 600.0, connect_timeout_s: float = 20.0,
                 transport: httpx.AsyncBaseTransport | None = None, app_title: str = "Shadow Twins") -> None:
        super().__init__(api_key, base_url, timeout_s=timeout_s, connect_timeout_s=connect_timeout_s,
                         transport=transport, headers={"X-Title": app_title, "HTTP-Referer": "http://localhost"})

    async def list_models(self) -> list[ModelInfo]:
        # The catalog is public: never send the key where it is not needed.
        resp = await self._client.get("/models")
        resp.raise_for_status()
        out = []
        for d in resp.json().get("data", []):
            m = parse_model(d)
            if (not m.input_modalities or "text" in m.input_modalities) and \
               (not m.output_modalities or "text" in m.output_modalities):
                out.append(m)
        return out

    async def list_endpoints(self, model_id: str) -> list[EndpointInfo]:
        resp = await self._client.get(f"/models/{model_id}/endpoints")
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        return [parse_endpoint(e) for e in data.get("endpoints") or []]

    def build_body(self, req: CompletionRequest) -> dict[str, Any]:
        body: dict[str, Any] = {"model": req.model_id, "messages": req.messages, "stream": False,
                                "usage": {"include": True}, **req.params}
        if req.endpoint:
            body["provider"] = {"order": [req.endpoint], "allow_fallbacks": False,
                                "require_parameters": True}
        else:
            body["provider"] = {"allow_fallbacks": req.allow_fallbacks, "require_parameters": True}
        return body

    async def reconcile(self, generation_id: str) -> dict[str, Any] | None:
        if not self._key:
            return None
        try:
            resp = await self._client.get("/generation", params={"id": generation_id}, headers=self._auth())
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        return resp.json().get("data")
