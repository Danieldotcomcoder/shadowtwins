"""OpenRouter adapter.

* Catalog: ``GET /models`` (public) and ``GET /models/{id}/endpoints``; prices are USD per token.
* Completions: ``POST /chat/completions`` with prompt-requested JSON only — no tools, no
  ``response_format``, no ``models`` fallback list. A pinned endpoint is sent as
  ``provider = {order: [slug], allow_fallbacks: false, require_parameters: true}``.
* Errors are normalized into ``ErrorCategory``. A request that may have been processed remotely
  (read timeout, dropped connection, unreadable 200 body) is ``ambiguous`` and never silently
  retried: exactly-once execution across the remote API is not claimed.
* The API key is only placed in the Authorization header; it is never logged or returned.
"""

from __future__ import annotations

import email.utils
import time
from typing import Any

import httpx

from .base import (
    CompletionRequest,
    CompletionResult,
    EndpointInfo,
    ErrorCategory,
    ModelInfo,
    Provider,
    Usage,
)

_MAX_ERROR_CHARS = 500


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


def _retry_after(resp: httpx.Response) -> float | None:
    h = resp.headers.get("retry-after")
    if not h:
        return None
    try:
        return max(0.0, float(h))
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(h)
            return max(0.0, when.timestamp() - time.time())
        except (TypeError, ValueError):
            return None


def _status_category(status: int, message: str) -> ErrorCategory:
    if status == 400 or status == 404 or status == 413 or status == 422:
        return ErrorCategory.BAD_REQUEST
    if status == 401:
        return ErrorCategory.AUTH
    if status == 402:
        return ErrorCategory.CREDITS
    if status == 403:
        return ErrorCategory.FORBIDDEN
    if status == 408:
        return ErrorCategory.SERVER  # provider-side timeout before a completion was produced
    if status == 429:
        return ErrorCategory.RATE_LIMITED
    if status >= 500:
        return ErrorCategory.SERVER
    return ErrorCategory.BAD_REQUEST


def _text(content: Any) -> str | None:
    if content is None or isinstance(content, str):
        return content
    if isinstance(content, list):  # some providers return content parts
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def _redact(body: dict[str, Any]) -> dict[str, Any]:
    """Keep provider metadata; drop bulky reasoning text (its length is recorded separately)."""
    out = dict(body)
    choices = []
    for ch in body.get("choices") or []:
        ch = dict(ch)
        msg = dict(ch.get("message") or {})
        if msg.get("reasoning"):
            msg["reasoning"] = f"<{len(str(msg['reasoning']))} chars omitted>"
        if msg.get("reasoning_details"):
            msg["reasoning_details"] = f"<{len(msg['reasoning_details'])} items omitted>"
        ch["message"] = msg
        choices.append(ch)
    out["choices"] = choices
    return out


class OpenRouterProvider(Provider):
    name = "openrouter"

    def __init__(self, api_key: str | None, base_url: str = "https://openrouter.ai/api/v1",
                 timeout_s: float = 600.0, connect_timeout_s: float = 20.0,
                 transport: httpx.AsyncBaseTransport | None = None, app_title: str = "Shadow Twins") -> None:
        self._key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_s, connect=connect_timeout_s, pool=connect_timeout_s),
            transport=transport,
            headers={"X-Title": app_title, "HTTP-Referer": "http://localhost"},
        )

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}"} if self._key else {}

    async def list_models(self) -> list[ModelInfo]:
        resp = await self._client.get("/models", headers=self._auth())
        resp.raise_for_status()
        out = []
        for d in resp.json().get("data", []):
            m = parse_model(d)
            if (not m.input_modalities or "text" in m.input_modalities) and \
               (not m.output_modalities or "text" in m.output_modalities):
                out.append(m)
        return out

    async def list_endpoints(self, model_id: str) -> list[EndpointInfo]:
        resp = await self._client.get(f"/models/{model_id}/endpoints", headers=self._auth())
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

    async def complete(self, req: CompletionRequest) -> CompletionResult:
        if not self._key:
            return CompletionResult(ok=False, error_category=ErrorCategory.AUTH,
                                    error_message="OPENROUTER_API_KEY is not configured on the server")
        body = self.build_body(req)
        t0 = time.perf_counter()
        try:
            resp = await self._client.post("/chat/completions", json=body, headers=self._auth())
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            return CompletionResult(ok=False, error_category=ErrorCategory.CONNECT,
                                    error_message=f"{type(exc).__name__}: could not connect")
        except (httpx.PoolTimeout, httpx.WriteTimeout, httpx.WriteError) as exc:
            return CompletionResult(ok=False, error_category=ErrorCategory.TIMEOUT_BEFORE_SEND,
                                    error_message=f"{type(exc).__name__}: request not fully sent")
        except (httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError) as exc:
            return CompletionResult(ok=False, error_category=ErrorCategory.AMBIGUOUS,
                                    error_message=f"{type(exc).__name__}: sent, no complete response",
                                    latency_ms=(time.perf_counter() - t0) * 1000)
        latency = (time.perf_counter() - t0) * 1000
        try:
            data = resp.json()
        except ValueError:
            if resp.status_code == 200:
                return CompletionResult(ok=False, http_status=200, latency_ms=latency,
                                        error_category=ErrorCategory.AMBIGUOUS,
                                        error_message="unreadable 200 response; the request may have been processed")
            data = {}
        if resp.status_code != 200 or ("error" in data and not data.get("choices")):
            err = data.get("error") or {}
            msg = str(err.get("message") or resp.reason_phrase)[:_MAX_ERROR_CHARS]
            status = resp.status_code if resp.status_code != 200 else int(err.get("code") or 502)
            return CompletionResult(ok=False, http_status=resp.status_code, latency_ms=latency,
                                    error_category=_status_category(status, msg), error_message=msg,
                                    retry_after_s=_retry_after(resp), raw={"error": err} if err else None)
        return self.parse_completion(data, resp.status_code, latency)

    @staticmethod
    def parse_completion(data: dict[str, Any], status: int, latency_ms: float) -> CompletionResult:
        choices = data.get("choices") or []
        if not choices:
            return CompletionResult(ok=False, http_status=status, latency_ms=latency_ms,
                                    error_category=ErrorCategory.AMBIGUOUS,
                                    error_message="response without choices")
        ch = choices[0]
        msg = ch.get("message") or {}
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        reasoning = msg.get("reasoning")
        result = CompletionResult(
            ok=True,
            content=_text(msg.get("content")),
            finish_reason=ch.get("finish_reason"),
            native_finish_reason=ch.get("native_finish_reason"),
            refusal=msg.get("refusal"),
            reasoning_chars=len(reasoning) if isinstance(reasoning, str) else None,
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                reasoning_tokens=details.get("reasoning_tokens"),
                cost_usd=float(usage["cost"]) if usage.get("cost") is not None else None,
            ),
            provider_name=data.get("provider"),
            response_model=data.get("model"),
            generation_id=data.get("id"),
            latency_ms=latency_ms,
            http_status=status,
            raw=_redact(data),
        )
        if ch.get("finish_reason") == "error" or ch.get("error"):
            err = ch.get("error") or {}
            result.ok = False
            result.error_category = ErrorCategory.PROVIDER_FINISH_ERROR
            result.error_message = str(err.get("message") or "provider finished with error")[:_MAX_ERROR_CHARS]
        return result

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

    async def aclose(self) -> None:
        await self._client.aclose()
