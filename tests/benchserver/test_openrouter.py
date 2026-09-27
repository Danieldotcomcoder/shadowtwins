import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest

from benchserver.profiles import PROFILE_BY_ID, compatibility, output_budget, request_params
from benchserver.providers.base import CompletionRequest, ErrorCategory
from benchserver.providers.openrouter import OpenRouterProvider, parse_endpoint, parse_model

DATA = Path(__file__).parent / "data"
MODELS = json.loads((DATA / "openrouter_models_sample.json").read_text(encoding="utf-8"))
ENDPOINTS = json.loads((DATA / "openrouter_endpoints_sample.json").read_text(encoding="utf-8"))
KEY = "sk-or-test-key"


def provider(handler, key: str | None = KEY) -> OpenRouterProvider:
    return OpenRouterProvider(key, "https://openrouter.test/api/v1", transport=httpx.MockTransport(handler))


def req(endpoint: str | None = "groq") -> CompletionRequest:
    return CompletionRequest(model_id="meta-llama/llama-3.1-8b-instruct",
                             messages=[{"role": "user", "content": "hi"}], params={"max_tokens": 8192, "temperature": 0.0},
                             endpoint=endpoint, allow_fallbacks=endpoint is None)


def run(coro):
    return asyncio.run(coro)


def completion(content="{\"remove\":[],\"add\":[]}", finish="stop", **extra):
    body = {
        "id": "gen-123", "provider": "Groq", "model": "meta-llama/llama-3.1-8b-instruct",
        "choices": [{"finish_reason": finish, "native_finish_reason": finish,
                     "message": {"role": "assistant", "content": content, "reasoning": "x" * 50,
                                 "reasoning_details": [{"type": "reasoning.text", "text": "secret thoughts"}]}}],
        "usage": {"prompt_tokens": 600, "completion_tokens": 20, "total_tokens": 620, "cost": 0.0000316,
                  "completion_tokens_details": {"reasoning_tokens": 12}},
    }
    body.update(extra)
    return body


def test_catalog_parsing_from_live_sample():
    models = {m["id"]: parse_model(m) for m in MODELS["data"]}
    llama = models["meta-llama/llama-3.1-8b-instruct"]
    assert llama.pricing["prompt"] == pytest.approx(5e-8) and llama.pricing["completion"] == pytest.approx(8e-8)
    assert llama.context_length == 131072 and llama.max_completion_tokens == 117964 and llama.pricing_known
    auto = models["openrouter/auto"]
    assert auto.pricing["prompt"] is None and not auto.pricing_known  # "-1" = dynamic pricing
    r1 = models["deepseek/deepseek-r1"]
    assert r1.reasoning == {"mandatory": True}
    eps = [parse_endpoint(e) for e in ENDPOINTS["data"]["endpoints"]]
    assert [e.slug for e in eps][:3] == ["deepinfra/fp8", "novita/fp8", "groq"]
    groq = next(e for e in eps if e.slug == "groq")
    assert groq.provider_name == "Groq" and "temperature" in groq.supported_parameters


def test_profile_compatibility_uses_real_limits():
    models = {m["id"]: parse_model(m) for m in MODELS["data"]}
    mini = models["openai/gpt-4o-mini"]
    assert compatibility(mini, PROFILE_BY_ID["standard"], 1000)["compatible"]
    hi = compatibility(mini, PROFILE_BY_ID["reasoning-high"], 1000)
    assert not hi["compatible"] and any("reasoning" in p for p in hi["problems"])
    r1 = models["deepseek/deepseek-r1"]
    # A model whose own output limit is below the profile ceiling gets its own maximum, not a refusal.
    low = compatibility(r1, PROFILE_BY_ID["reasoning-low"], 1000)
    assert low["compatible"] and any("16,000" in w and "max completion" in w for w in low["warnings"])
    std = compatibility(r1, PROFILE_BY_ID["standard"], 1000)
    assert std["compatible"] and any("always reasons" in w for w in std["warnings"])
    params, record = request_params(r1, PROFILE_BY_ID["standard"], None, 1000)
    assert params == {"max_tokens": 16000, "temperature": 0.0} and record["temperature"]["sent"]
    assert record["profile_max_tokens"] == 65536 and "16,000" in record["max_tokens_capped_by"]
    import dataclasses

    no_temp = dataclasses.replace(r1, supported_parameters=[p for p in r1.supported_parameters if p != "temperature"])
    params, record = request_params(no_temp, PROFILE_BY_ID["standard"], None, 1000)
    assert "temperature" not in params and record["temperature"]["sent"] is False
    # A limit (output or context) below the minimum useful budget is still a hard incompatibility.
    tiny = dataclasses.replace(r1, max_completion_tokens=4096)
    bad = compatibility(tiny, PROFILE_BY_ID["standard"], 1000)
    assert not bad["compatible"] and any("below the minimum" in p for p in bad["problems"])
    small_ctx = dataclasses.replace(r1, context_length=40_000, max_completion_tokens=None)
    assert output_budget(small_ctx, PROFILE_BY_ID["standard"], 1000) == (39_000, "the context window (40,000 minus the prompt)")
    big = dataclasses.replace(r1, context_length=1_000_000, max_completion_tokens=None)
    assert output_budget(big, PROFILE_BY_ID["reasoning-high"], 1000) == (131_072, None)


def test_list_models_filters_to_text_and_uses_public_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=MODELS)

    models = run(provider(handler).list_models())
    assert seen["path"] == "/api/v1/models" and {m.model_id for m in models} >= {"openai/gpt-4o-mini"}
    assert seen["auth"] is None  # the public catalog never receives the key


def test_request_pins_endpoint_and_disables_fallbacks():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=completion())

    res = run(provider(handler).complete(req("groq")))
    body = captured["body"]
    assert body["provider"] == {"order": ["groq"], "allow_fallbacks": False, "require_parameters": True}
    assert "models" not in body and "tools" not in body and "response_format" not in body
    assert body["stream"] is False and body["max_tokens"] == 8192 and captured["auth"] == f"Bearer {KEY}"
    assert res.ok and res.content == '{"remove":[],"add":[]}' and res.provider_name == "Groq"
    assert res.usage.cost_usd == pytest.approx(0.0000316) and res.usage.reasoning_tokens == 12
    assert res.generation_id == "gen-123" and res.reasoning_chars == 50
    # reasoning text is not kept in the stored provider envelope
    assert "secret thoughts" not in json.dumps(res.raw) and "chars omitted" in json.dumps(res.raw)
    unpinned = run(provider(handler).complete(req(None)))
    assert unpinned.ok and captured["body"]["provider"] == {"allow_fallbacks": True, "require_parameters": True}


@pytest.mark.parametrize("status, category, retryable", [
    (400, ErrorCategory.BAD_REQUEST, False), (401, ErrorCategory.AUTH, False),
    (402, ErrorCategory.CREDITS, False), (403, ErrorCategory.FORBIDDEN, False),
    (408, ErrorCategory.SERVER, True), (429, ErrorCategory.RATE_LIMITED, True),
    (500, ErrorCategory.SERVER, True), (502, ErrorCategory.SERVER, True), (503, ErrorCategory.SERVER, True),
])
def test_http_error_mapping(status, category, retryable):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": status, "message": f"err {status} {KEY[:3]}"}},
                              headers={"retry-after": "7"} if status == 429 else {})

    res = run(provider(handler).complete(req()))
    assert not res.ok and res.error_category == category and res.retryable == retryable
    if status == 429:
        assert res.retry_after_s == 7


def test_transport_failures_distinguish_unsent_from_ambiguous():
    def boom(exc):
        def handler(request: httpx.Request) -> httpx.Response:
            raise exc
        return handler

    r = run(provider(boom(httpx.ConnectError("refused"))).complete(req()))
    assert r.error_category == ErrorCategory.CONNECT and r.retryable
    r = run(provider(boom(httpx.ReadTimeout("slow"))).complete(req()))
    assert r.error_category == ErrorCategory.AMBIGUOUS and not r.retryable
    r = run(provider(boom(httpx.RemoteProtocolError("dropped"))).complete(req()))
    assert r.error_category == ErrorCategory.AMBIGUOUS


def test_odd_but_valid_responses():
    def finish_error(request):
        return httpx.Response(200, json=completion(finish="error", content="partial"))
    r = run(provider(finish_error).complete(req()))
    assert not r.ok and r.error_category == ErrorCategory.PROVIDER_FINISH_ERROR and r.retryable

    def parts(request):
        body = completion()
        body["choices"][0]["message"]["content"] = [{"type": "text", "text": '{"remove":[],'},
                                                    {"type": "text", "text": '"add":[]}'}]
        return httpx.Response(200, json=body)
    assert run(provider(parts).complete(req())).content == '{"remove":[],"add":[]}'

    def error_in_200(request):
        return httpx.Response(200, json={"error": {"code": 502, "message": "upstream"}})
    r = run(provider(error_in_200).complete(req()))
    assert r.error_category == ErrorCategory.SERVER

    def garbage(request):
        return httpx.Response(200, content=b"<html>oops")
    assert run(provider(garbage).complete(req())).error_category == ErrorCategory.AMBIGUOUS

    def length(request):
        return httpx.Response(200, json=completion(finish="length", content='{"remove":['))
    r = run(provider(length).complete(req()))
    assert r.ok and r.finish_reason == "length"  # a completed answer: scored as truncated, never retried


def test_missing_key_never_calls_the_network():
    def handler(request):  # pragma: no cover - must not be called
        raise AssertionError("network call without a key")
    r = run(provider(handler, key=None).complete(req()))
    assert r.error_category == ErrorCategory.AUTH


@pytest.mark.skipif(os.environ.get("ST_LIVE_TESTS") != "1", reason="set ST_LIVE_TESTS=1 for live catalog checks")
def test_live_catalog_smoke():
    async def go():
        p = OpenRouterProvider(None)
        try:
            return await p.list_models(), await p.list_endpoints("meta-llama/llama-3.1-8b-instruct")
        finally:
            await p.aclose()

    models, eps = run(go())
    assert len(models) > 50 and any(m.model_id == "openai/gpt-4o-mini" for m in models)
    assert eps and all(e.slug for e in eps)
