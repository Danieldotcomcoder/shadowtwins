"""Shared transport for OpenAI-style ``POST /chat/completions`` providers (OpenRouter, Groq).

Subclasses translate the catalog and the request body; sending, error normalization and response
parsing are shared. A request that may have been processed remotely (read timeout, dropped
connection, unreadable 200 body) is ``ambiguous`` and never silently retried: exactly-once execution
across the remote API is not claimed. The API key is only placed in the Authorization header; it is
never logged or returned.
"""

from __future__ import annotations

import email.utils
import re
import time
from abc import abstractmethod
from typing import Any

import httpx

from .base import CompletionRequest, CompletionResult, ErrorCategory, Provider, Usage

MAX_ERROR_CHARS = 500
# "Please try again in 1h2m3.5s" / "in 7m12s" / "in 850ms": used when a 429 carries no Retry-After.
_TRY_AGAIN = re.compile(r"try again in\s+((?:\d+(?:\.\d+)?(?:ms|h|m|s))+)", re.I)
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")


def retry_after(resp: httpx.Response, message: str = "") -> float | None:
    h = resp.headers.get("retry-after")
    if h:
        try:
            return max(0.0, float(h))
        except ValueError:
            try:
                when = email.utils.parsedate_to_datetime(h)
                return max(0.0, when.timestamp() - time.time())
            except (TypeError, ValueError):
                pass
    m = _TRY_AGAIN.search(message)
    if not m:
        return None
    scale = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
    return sum(float(n) * scale[u] for n, u in _DURATION_PART.findall(m.group(1)))


def status_category(status: int, message: str) -> ErrorCategory:
    if status in (400, 404, 413, 422):
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
    if status == 498:
        return ErrorCategory.SERVER  # Groq: capacity exceeded for the service tier
    if status >= 500:
        return ErrorCategory.SERVER
    return ErrorCategory.BAD_REQUEST


def text_of(content: Any) -> str | None:
    if content is None or isinstance(content, str):
        return content
    if isinstance(content, list):  # some providers return content parts
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def redact(body: dict[str, Any]) -> dict[str, Any]:
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


class ChatCompletionsProvider(Provider):
    key_env = "API_KEY"  # environment variable named in the "not configured" error
    default_provider_name: str | None = None  # when the response does not name the serving provider

    def __init__(self, api_key: str | None, base_url: str, timeout_s: float = 600.0,
                 connect_timeout_s: float = 20.0, transport: httpx.AsyncBaseTransport | None = None,
                 headers: dict[str, str] | None = None) -> None:
        self._key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_s, connect=connect_timeout_s, pool=connect_timeout_s),
            transport=transport,
            headers=headers or {},
        )

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}"} if self._key else {}

    @abstractmethod
    def build_body(self, req: CompletionRequest) -> dict[str, Any]: ...

    async def complete(self, req: CompletionRequest) -> CompletionResult:
        if not self._key:
            return CompletionResult(ok=False, error_category=ErrorCategory.AUTH,
                                    error_message=f"{self.key_env} is not configured on the server")
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
            msg = str(err.get("message") or resp.reason_phrase)[:MAX_ERROR_CHARS]
            code = str(err.get("code") or "")
            status = resp.status_code if resp.status_code != 200 else (int(code) if code.isdigit() else 502)
            return CompletionResult(ok=False, http_status=resp.status_code, latency_ms=latency,
                                    error_category=status_category(status, msg), error_message=msg,
                                    retry_after_s=retry_after(resp, msg), raw={"error": err} if err else None)
        return self.parse_completion(data, resp.status_code, latency)

    def parse_completion(self, data: dict[str, Any], status: int, latency_ms: float) -> CompletionResult:
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
            content=text_of(msg.get("content")),
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
            provider_name=data.get("provider") or self.default_provider_name,
            response_model=data.get("model"),
            generation_id=data.get("id"),
            latency_ms=latency_ms,
            http_status=status,
            raw=redact(data),
        )
        if ch.get("finish_reason") == "error" or ch.get("error"):
            err = ch.get("error") or {}
            result.ok = False
            result.error_category = ErrorCategory.PROVIDER_FINISH_ERROR
            result.error_message = str(err.get("message") or "provider finished with error")[:MAX_ERROR_CHARS]
        return result

    async def aclose(self) -> None:
        await self._client.aclose()
