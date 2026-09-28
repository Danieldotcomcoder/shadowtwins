"""Groq adapter (GroqCloud, OpenAI-compatible API).

* Model ids are namespaced ``groq:<groq model id>`` inside this app, because Groq serves models whose
  ids collide with OpenRouter's (``openai/gpt-oss-120b``); the prefix is stripped on the wire.
* Catalog: ``GET /models`` (needs the key). Name, context, max completion tokens, list prices,
  sampling parameters and a ``reasoning`` feature flag come from Groq itself. Only active text-in /
  text-out models are listed.
* Pricing depends on the account plan (``GROQ_PLAN``): on the free plan nothing is billed, so prices
  are $0 and the list price is noted in the description; on the developer plan the list prices apply.
  Groq does not report per-request cost, so cost is computed from reported token usage.
* Groq serves its models itself: there are no endpoints to pin and no fallbacks.
* Requests: ``max_tokens`` is sent as ``max_completion_tokens`` and ``reasoning.effort`` as
  ``reasoning_effort``. Reasoning models other than GPT-OSS would otherwise put their reasoning in the
  answer inside ``<think>`` tags, which the strict parser rejects; runs therefore request
  ``reasoning_format = "parsed"`` for them (see ``fixed_params``), which returns reasoning in a separate
  field. GPT-OSS returns reasoning separately by default.
* Free-plan limits (per model: requests and tokens per minute and per day) surface as 429s with a
  Retry-After, and right after a long answer also as 413 "Request too large" with the same
  ``rate_limit_exceeded`` code; both are rate limits the runner waits out. The daily check counts the
  requested output budget (prompt + ``max_completion_tokens``), not only tokens used.
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import CompletionRequest, CompletionResult, EndpointInfo, ErrorCategory, ModelInfo
from .openai_compat import ChatCompletionsProvider

PREFIX = "groq:"
PLANS = ("free", "developer")


def app_model_id(groq_id: str) -> str:
    return PREFIX + groq_id


def groq_model_id(model_id: str) -> str:
    return model_id[len(PREFIX):] if model_id.startswith(PREFIX) else model_id


def _price(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def _is_gpt_oss(groq_id: str) -> bool:
    return groq_id.startswith("openai/gpt-oss")


def _reasoning(groq_id: str, features: list[str]) -> dict[str, Any] | None:
    """Reasoning controls per model family (Groq's catalog flags reasoning but not the efforts)."""
    if "reasoning" not in features:
        return None
    if _is_gpt_oss(groq_id):
        return {"supported_efforts": ["low", "medium", "high"], "mandatory": True, "reasoning_field": "default"}
    if groq_id.startswith("qwen/qwen3"):
        return {"supported_efforts": ["none", "default", "low", "medium", "high"], "mandatory": False,
                "reasoning_field": "reasoning_format=parsed"}
    return {"supported_efforts": None, "mandatory": False, "reasoning_field": "reasoning_format=parsed"}


def parse_model(d: dict[str, Any], plan: str = "free") -> ModelInfo:
    gid = d["id"]
    features = list(d.get("supported_features") or [])
    params = list(d.get("supported_sampling_parameters") or ["temperature", "top_p", "stop", "seed", "max_tokens"])
    if "max_tokens" not in params:
        params.append("max_tokens")
    reasoning = _reasoning(gid, features)
    if reasoning:
        params.append("reasoning")
    p = d.get("pricing") or {}
    listed = {"prompt": _price(p.get("prompt")), "completion": _price(p.get("completion")),
              "internal_reasoning": None, "request": _price(p.get("request"))}
    if plan == "free":
        pricing: dict[str, float | None] = {"prompt": 0.0, "completion": 0.0, "internal_reasoning": None,
                                            "request": 0.0}
        note = "Groq free plan: not billed, rate-limited per model."
        if listed["prompt"] is not None and listed["completion"] is not None:
            note += (f" List price ${listed['prompt'] * 1e6:.3g} / ${listed['completion'] * 1e6:.3g} "
                     "per million input/output tokens on the developer plan.")
    else:
        pricing, note = listed, "Groq developer plan: billed at list price."
    return ModelInfo(
        provider="groq",
        model_id=app_model_id(gid),
        name=f"{d.get('name') or gid} (Groq)",
        context_length=d.get("context_window") or d.get("context_length"),
        pricing=pricing,
        supported_parameters=params,
        reasoning=reasoning,
        max_completion_tokens=d.get("max_completion_tokens") or d.get("max_output_length"),
        description=f"{note} Owned by {d.get('owned_by') or 'unknown'}; features: {', '.join(features) or 'none'}.",
        input_modalities=list(d.get("input_modalities") or ["text"]),
        output_modalities=list(d.get("output_modalities") or ["text"]),
    )


class GroqProvider(ChatCompletionsProvider):
    name = "groq"
    key_env = "GROQ_API_KEY"
    default_provider_name = "Groq"

    def __init__(self, api_key: str | None, base_url: str = "https://api.groq.com/openai/v1",
                 plan: str = "free", timeout_s: float = 600.0, connect_timeout_s: float = 20.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        if plan not in PLANS:
            raise ValueError(f"GROQ_PLAN must be one of {PLANS}")
        super().__init__(api_key, base_url, timeout_s=timeout_s, connect_timeout_s=connect_timeout_s,
                         transport=transport)
        self.plan = plan

    async def list_models(self) -> list[ModelInfo]:
        resp = await self._client.get("/models", headers=self._auth())
        resp.raise_for_status()
        out = []
        for d in resp.json().get("data", []):
            if d.get("active") is False:
                continue
            m = parse_model(d, self.plan)
            if "text" in m.input_modalities and "text" in m.output_modalities:
                out.append(m)
        return out

    async def list_endpoints(self, model_id: str) -> list[EndpointInfo]:
        return []  # Groq serves its models itself: nothing to pin, no fallbacks

    def fixed_params(self, model: ModelInfo) -> dict[str, Any]:
        if model.reasoning and model.reasoning.get("reasoning_field") == "reasoning_format=parsed":
            return {"reasoning_format": "parsed"}
        return {}

    def build_body(self, req: CompletionRequest) -> dict[str, Any]:
        params = dict(req.params)
        body: dict[str, Any] = {"model": groq_model_id(req.model_id), "messages": req.messages, "stream": False}
        if "max_tokens" in params:
            body["max_completion_tokens"] = params.pop("max_tokens")
        reasoning = params.pop("reasoning", None)
        if isinstance(reasoning, dict) and reasoning.get("effort"):
            body["reasoning_effort"] = reasoning["effort"]
        body.update(params)
        return body

    def classify_error(self, status: int, err: dict[str, Any], message: str) -> ErrorCategory:
        # Right after a long answer, Groq's per-minute limiter also refuses the next request with
        # 413 "Request too large ... tokens per minute", carrying the same rate_limit_exceeded code as
        # its 429s. It clears once the window moves on (observed live), so it is a rate limit to wait
        # out, not a malformed request.
        if err.get("code") == "rate_limit_exceeded":
            return ErrorCategory.RATE_LIMITED
        return super().classify_error(status, err, message)

    def parse_completion(self, data: dict[str, Any], status: int, latency_ms: float) -> CompletionResult:
        result = super().parse_completion(data, status, latency_ms)
        x_groq = data.get("x_groq") or {}
        if x_groq.get("id"):
            result.generation_id = x_groq["id"]
        return result
