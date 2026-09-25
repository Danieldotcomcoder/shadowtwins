"""Deterministic mock provider (test double). Enabled only with ``ST_ENABLE_MOCK_PROVIDER=1``.

Mock runs are always labelled ``is_mock`` and can never appear on the leaderboard. Each model
exercises one behaviour of the runner: correct answers, invalid answers, refusals, truncation,
transient server errors, rate limits, ambiguous timeouts, slowness, unknown pricing and run-blocking
provider errors.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections import Counter
from collections.abc import Callable

from .base import (
    CompletionRequest,
    CompletionResult,
    EndpointInfo,
    ErrorCategory,
    ModelInfo,
    Provider,
    Usage,
)

PROMPT_PRICE = 1e-6
COMPLETION_PRICE = 2e-6

# model id -> (display name, behaviour note, priced?, supports reasoning?)
MOCK_MODELS: dict[str, tuple[str, str, bool, bool]] = {
    "mock/optimal": ("Mock · optimal", "answers with the certified optimum", True, False),
    "mock/noop": ("Mock · no-op", "always answers the legal empty edit", True, False),
    "mock/random": ("Mock · random", "deterministic pseudo-random edit (legal or not)", True, False),
    "mock/invalid": ("Mock · prose", "answers in prose (malformed)", True, False),
    "mock/refuse": ("Mock · refusal", "declines the task", True, False),
    "mock/truncated": ("Mock · truncated", "hits the length limit mid-answer", True, False),
    "mock/flaky": ("Mock · flaky", "first attempt fails with 503, then optimal", True, False),
    "mock/ratelimit": ("Mock · rate-limited", "two 429s with Retry-After, then random", True, False),
    "mock/ambiguous": ("Mock · ambiguous", "first attempt times out after sending, then optimal", True, False),
    "mock/slow": ("Mock · slow", "optimal after a delay", True, False),
    "mock/reasoner": ("Mock · reasoner", "supports reasoning; optimal with reasoning tokens", True, True),
    "mock/unpriced": ("Mock · unpriced", "no pricing metadata; random answers", False, False),
    "mock/badrequest": ("Mock · bad request", "always 400", True, False),
    "mock/nocredits": ("Mock · no credits", "always 402", True, False),
}

AnswerBook = Callable[[str], tuple[str | None, Callable[[int], str | None]] | None]


class MockProvider(Provider):
    name = "mock"

    def __init__(self, answer_book: AnswerBook, slow_delay_s: float = 0.4) -> None:
        self._book = answer_book
        self._calls: Counter[tuple[str, str]] = Counter()
        self.slow_delay_s = slow_delay_s

    async def list_models(self) -> list[ModelInfo]:
        out = []
        for mid, (name, note, priced, reasoning) in MOCK_MODELS.items():
            params = ["max_tokens", "temperature", "seed"] + (["reasoning"] if reasoning else [])
            out.append(ModelInfo(
                provider="mock", model_id=mid, name=name, context_length=200_000,
                pricing={"prompt": PROMPT_PRICE if priced else None,
                         "completion": COMPLETION_PRICE if priced else None,
                         "internal_reasoning": None, "request": None},
                supported_parameters=params,
                reasoning={"supported_efforts": ["low", "medium", "high"], "mandatory": False}
                if reasoning else None,
                max_completion_tokens=65_536, description=f"Test double: {note}.",
                input_modalities=["text"], output_modalities=["text"], is_mock=True,
            ))
        return out

    async def list_endpoints(self, model_id: str) -> list[EndpointInfo]:
        models = {m.model_id: m for m in await self.list_models()}
        m = models.get(model_id)
        if m is None:
            return []
        return [EndpointInfo(slug="mock-endpoint", provider_name="Mock", context_length=m.context_length,
                             pricing=m.pricing, supported_parameters=m.supported_parameters,
                             max_completion_tokens=m.max_completion_tokens, quantization=None, status=0)]

    def _usage(self, prompt: str, content: str, reasoning_tokens: int = 0, priced: bool = True) -> Usage:
        pt, ct = max(1, len(prompt) // 4), max(1, len(content) // 4) + reasoning_tokens
        cost = pt * PROMPT_PRICE + ct * COMPLETION_PRICE if priced else None
        return Usage(prompt_tokens=pt, completion_tokens=ct, reasoning_tokens=reasoning_tokens, cost_usd=cost)

    def _ok(self, req: CompletionRequest, prompt: str, content: str, finish: str = "stop",
            reasoning_tokens: int = 0) -> CompletionResult:
        priced = MOCK_MODELS.get(req.model_id, ("", "", True, False))[2]
        gid = f"mock-{uuid.uuid4().hex[:12]}"
        usage = self._usage(prompt, content, reasoning_tokens, priced)
        return CompletionResult(
            ok=True, content=content, finish_reason=finish, native_finish_reason=finish,
            usage=usage, provider_name="Mock", response_model=req.model_id, generation_id=gid,
            latency_ms=5.0, http_status=200,
            raw={"id": gid, "model": req.model_id, "provider": "Mock",
                 "choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": content}}],
                 "usage": {"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens,
                           "cost": usage.cost_usd}},
        )

    @staticmethod
    def _err(cat: ErrorCategory, status: int | None, msg: str, retry_after: float | None = None) -> CompletionResult:
        return CompletionResult(ok=False, error_category=cat, http_status=status, error_message=msg,
                                retry_after_s=retry_after)

    async def complete(self, req: CompletionRequest) -> CompletionResult:
        prompt = req.messages[-1]["content"]
        key = hashlib.sha256(prompt.encode()).hexdigest()
        self._calls[(req.model_id, key)] += 1
        n = self._calls[(req.model_id, key)]
        entry = self._book(prompt)
        optimal, sampler = entry if entry else (None, lambda seed: None)
        seed = int(key[:8], 16)
        random_answer = sampler(seed) or '{"remove":[],"add":[]}'
        best = optimal or '{"remove":[],"add":[]}'
        m = req.model_id
        if m == "mock/optimal":
            return self._ok(req, prompt, best)
        if m == "mock/noop":
            return self._ok(req, prompt, '{"remove":[],"add":[]}')
        if m in ("mock/random", "mock/unpriced"):
            return self._ok(req, prompt, random_answer)
        if m == "mock/invalid":
            return self._ok(req, prompt, "I would move the cube in the middle to close the tunnel.")
        if m == "mock/refuse":
            return self._ok(req, prompt, "I can't help with that.")
        if m == "mock/truncated":
            return self._ok(req, prompt, '{"remove":[0', finish="length")
        if m == "mock/flaky":
            if n == 1:
                return self._err(ErrorCategory.SERVER, 503, "mock upstream unavailable")
            return self._ok(req, prompt, best)
        if m == "mock/ratelimit":
            if n <= 2:
                return self._err(ErrorCategory.RATE_LIMITED, 429, "mock rate limit", retry_after=0.05)
            return self._ok(req, prompt, random_answer)
        if m == "mock/ambiguous":
            if n == 1:
                return self._err(ErrorCategory.AMBIGUOUS, None, "ReadTimeout: sent, no complete response")
            return self._ok(req, prompt, best)
        if m == "mock/slow":
            await asyncio.sleep(self.slow_delay_s)
            return self._ok(req, prompt, best)
        if m == "mock/reasoner":
            return self._ok(req, prompt, best, reasoning_tokens=120)
        if m == "mock/badrequest":
            return self._err(ErrorCategory.BAD_REQUEST, 400, "mock: unsupported parameter")
        if m == "mock/nocredits":
            return self._err(ErrorCategory.CREDITS, 402, "mock: insufficient credits")
        return self._err(ErrorCategory.BAD_REQUEST, 404, f"unknown mock model {m}")
