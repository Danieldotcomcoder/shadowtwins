"""Provider interface. Every provider reuses the same benchmark, parser, scoring and job pipeline;
adapters only translate catalogs, requests, usage and errors into these normalized shapes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    CONNECT = "transport_connect"  # request never reached the provider: safe to retry
    TIMEOUT_BEFORE_SEND = "timeout_before_send"
    AMBIGUOUS = "ambiguous"  # sent, outcome unknown (read timeout, dropped connection)
    RATE_LIMITED = "rate_limited"
    SERVER = "server_error"  # 5xx / provider error
    PROVIDER_FINISH_ERROR = "provider_finish_error"  # choice finished with finish_reason=error
    BAD_REQUEST = "bad_request"
    AUTH = "auth_error"
    CREDITS = "insufficient_credits"
    FORBIDDEN = "forbidden"
    MALFORMED_RESPONSE = "malformed_response"  # unparseable envelope from the provider


RETRYABLE = {ErrorCategory.CONNECT, ErrorCategory.TIMEOUT_BEFORE_SEND, ErrorCategory.RATE_LIMITED,
             ErrorCategory.SERVER, ErrorCategory.PROVIDER_FINISH_ERROR}
# Errors that make further dispatch for the run pointless until an operator acts.
RUN_BLOCKING = {ErrorCategory.AUTH, ErrorCategory.CREDITS}


@dataclass
class ModelInfo:
    provider: str
    model_id: str
    name: str
    context_length: int | None
    pricing: dict[str, float | None]  # USD per token: prompt, completion, internal_reasoning, request
    supported_parameters: list[str]
    reasoning: dict[str, Any] | None = None
    max_completion_tokens: int | None = None
    description: str = ""
    input_modalities: list[str] = field(default_factory=list)
    output_modalities: list[str] = field(default_factory=list)
    is_mock: bool = False

    @property
    def pricing_known(self) -> bool:
        return self.pricing.get("prompt") is not None and self.pricing.get("completion") is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "model_id": self.model_id, "name": self.name,
            "context_length": self.context_length, "pricing": self.pricing,
            "pricing_known": self.pricing_known, "supported_parameters": self.supported_parameters,
            "reasoning": self.reasoning, "max_completion_tokens": self.max_completion_tokens,
            "description": self.description, "input_modalities": self.input_modalities,
            "output_modalities": self.output_modalities, "is_mock": self.is_mock,
        }


@dataclass
class EndpointInfo:
    slug: str  # value accepted in provider.order
    provider_name: str
    context_length: int | None
    pricing: dict[str, float | None]
    supported_parameters: list[str]
    max_completion_tokens: int | None
    quantization: str | None
    status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class CompletionRequest:
    model_id: str
    messages: list[dict[str, str]]
    params: dict[str, Any]  # max_tokens, temperature, reasoning, ...
    endpoint: str | None  # pinned provider endpoint slug, or None
    allow_fallbacks: bool

    def body(self) -> dict[str, Any]:
        """The provider-neutral request actually recorded for provenance."""
        return {"model": self.model_id, "messages": self.messages, **self.params,
                "endpoint": self.endpoint, "allow_fallbacks": self.allow_fallbacks}


@dataclass
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: float | None = None  # as reported by the provider


@dataclass
class CompletionResult:
    ok: bool
    content: str | None = None
    finish_reason: str | None = None
    native_finish_reason: str | None = None
    refusal: str | None = None
    reasoning_chars: int | None = None
    usage: Usage = field(default_factory=Usage)
    provider_name: str | None = None
    response_model: str | None = None
    generation_id: str | None = None
    latency_ms: float | None = None
    http_status: int | None = None
    error_category: ErrorCategory | None = None
    error_message: str | None = None
    retry_after_s: float | None = None
    raw: dict[str, Any] | None = None  # redacted provider envelope for provenance

    @property
    def retryable(self) -> bool:
        return self.error_category in RETRYABLE

    @property
    def ambiguous(self) -> bool:
        return self.error_category == ErrorCategory.AMBIGUOUS


class Provider(ABC):
    name: str

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...

    @abstractmethod
    async def list_endpoints(self, model_id: str) -> list[EndpointInfo]: ...

    @abstractmethod
    async def complete(self, req: CompletionRequest) -> CompletionResult: ...

    def fixed_params(self, model: ModelInfo) -> dict[str, Any]:
        """Provider-specific parameters every request for ``model`` must carry (recorded per run)."""
        return {}

    async def reconcile(self, generation_id: str) -> dict[str, Any] | None:
        """Look up provider-side facts for a generation, where the provider supports it."""
        return None

    async def aclose(self) -> None:
        return None
