import asyncio
import json
from pathlib import Path

import httpx
import pytest

from benchcore.contracts import RunMode, RunSpec
from benchserver import runs
from benchserver.config import RetryPolicy, load_settings
from benchserver.context import AppContext
from benchserver.profiles import PROFILE_BY_ID, compatibility, request_params
from benchserver.providers.base import CompletionRequest, ErrorCategory
from benchserver.providers.groq import GroqProvider, parse_model

from .conftest import drain, make_ctx, make_settings, q, summary

DATA = Path(__file__).parent / "data"
MODELS = json.loads((DATA / "groq_models_sample.json").read_text(encoding="utf-8"))
KEY = "gsk-test-key"


def provider(handler, key: str | None = KEY, plan: str = "free") -> GroqProvider:
    return GroqProvider(key, "https://groq.test/openai/v1", plan=plan, transport=httpx.MockTransport(handler))


def run(coro):
    return asyncio.run(coro)


def completion(content='{"remove":[],"add":[]}', model="openai/gpt-oss-120b", finish="stop"):
    return {
        "id": "chatcmpl-1", "object": "chat.completion", "model": model, "service_tier": "on_demand",
        "choices": [{"index": 0, "finish_reason": finish,
                     "message": {"role": "assistant", "content": content, "reasoning": "r" * 40}}],
        "usage": {"queue_time": 0.01, "prompt_tokens": 655, "completion_tokens": 900, "total_tokens": 1555,
                  "completion_tokens_details": {"reasoning_tokens": 880}},
        "x_groq": {"id": "req_01abc"},
    }


def test_catalog_lists_text_models_under_a_groq_namespace():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"], seen["auth"] = request.url.path, request.headers.get("authorization")
        return httpx.Response(200, json=MODELS)

    models = {m.model_id: m for m in run(provider(handler).list_models())}
    assert seen == {"path": "/openai/v1/models", "auth": f"Bearer {KEY}"}  # Groq's catalog needs the key
    # audio models and inactive models are not offered; ids never collide with OpenRouter's
    assert set(models) == {"groq:openai/gpt-oss-120b", "groq:qwen/qwen3.8-27b", "groq:allam-2-7b"}
    oss = models["groq:openai/gpt-oss-120b"]
    assert oss.provider == "groq" and oss.name == "GPT OSS 120B (Groq)"
    assert oss.context_length == 131072 and oss.max_completion_tokens == 65536
    assert "reasoning" in oss.supported_parameters and "temperature" in oss.supported_parameters
    assert oss.reasoning is not None and oss.reasoning["supported_efforts"] == ["low", "medium", "high"]
    assert oss.reasoning["mandatory"] is True
    qwen = models["groq:qwen/qwen3.8-27b"]
    assert qwen.reasoning is not None and "none" in qwen.reasoning["supported_efforts"]
    assert models["groq:allam-2-7b"].reasoning is None


def test_pricing_follows_the_account_plan():
    raw = MODELS["data"][0]
    free = parse_model(raw, "free")
    assert free.pricing == {"prompt": 0.0, "completion": 0.0, "internal_reasoning": None, "request": 0.0}
    assert free.pricing_known and "$0.15 / $0.6 per million" in free.description
    dev = parse_model(raw, "developer")
    assert dev.pricing["prompt"] == pytest.approx(1.5e-7) and dev.pricing["completion"] == pytest.approx(6e-7)
    unpriced = parse_model(MODELS["data"][2], "developer")  # allam lists no price
    assert not unpriced.pricing_known and parse_model(MODELS["data"][2], "free").pricing_known
    with pytest.raises(ValueError):
        provider(lambda r: httpx.Response(200), plan="enterprise")


def test_profiles_fit_groq_limits():
    models = {m["id"]: parse_model(m) for m in MODELS["data"]}
    oss, qwen, allam = models["openai/gpt-oss-120b"], models["qwen/qwen3.8-27b"], models["allam-2-7b"]
    assert all(compatibility(oss, p, 1064)["compatible"] for p in PROFILE_BY_ID.values())
    params, _ = request_params(oss, PROFILE_BY_ID["reasoning-high"], None, 1064)
    assert params["max_tokens"] == 65536 and params["reasoning"] == {"effort": "high"}
    low = compatibility(qwen, PROFILE_BY_ID["reasoning-low"], 1064)
    assert low["compatible"] and any("16,384" in w for w in low["warnings"])  # capped at Qwen's own limit
    assert not compatibility(allam, PROFILE_BY_ID["standard"], 1064)["compatible"]  # 4k context is too small


def test_request_is_translated_to_groq_parameters():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=completion())

    p = provider(handler)
    qwen = parse_model(MODELS["data"][1])
    assert p.fixed_params(qwen) == {"reasoning_format": "parsed"}  # keep <think> text out of the answer
    assert p.fixed_params(parse_model(MODELS["data"][0])) == {}  # GPT-OSS reports reasoning separately
    req = CompletionRequest(model_id="groq:qwen/qwen3.8-27b", messages=[{"role": "user", "content": "hi"}],
                            params={"max_tokens": 16384, "temperature": 0.0, "reasoning": {"effort": "low"},
                                    "reasoning_format": "parsed"}, endpoint=None, allow_fallbacks=False)
    res = run(p.complete(req))
    assert captured["body"] == {"model": "qwen/qwen3.8-27b", "messages": [{"role": "user", "content": "hi"}],
                                "stream": False, "max_completion_tokens": 16384, "temperature": 0.0,
                                "reasoning_effort": "low", "reasoning_format": "parsed"}
    assert captured["auth"] == f"Bearer {KEY}"
    assert res.ok and res.content == '{"remove":[],"add":[]}' and res.finish_reason == "stop"
    assert res.provider_name == "Groq" and res.generation_id == "req_01abc" and res.reasoning_chars == 40
    assert res.usage.prompt_tokens == 655 and res.usage.reasoning_tokens == 880 and res.usage.cost_usd is None
    assert res.raw is not None and res.raw["choices"][0]["message"]["reasoning"] == "<40 chars omitted>"


@pytest.mark.parametrize(("status", "headers", "message", "category", "retry_after"), [
    (429, {"retry-after": "37"}, "Rate limit reached on tokens per minute (TPM)", ErrorCategory.RATE_LIMITED, 37.0),
    (429, {}, "Rate limit reached on tokens per day (TPD): Limit 200000, Used 199000. Please try again in 1h2m3.5s.",
     ErrorCategory.RATE_LIMITED, 3723.5),
    (413, {}, "Request too large for model on tokens per minute (TPM)", ErrorCategory.BAD_REQUEST, None),
    (401, {}, "Invalid API Key", ErrorCategory.AUTH, None),
    (498, {}, "Capacity exceeded for the flex tier", ErrorCategory.SERVER, None),
])
def test_errors_are_normalized(status, headers, message, category, retry_after):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers,
                              json={"error": {"message": message, "type": "tokens", "code": "rate_limit_exceeded"}})

    req = CompletionRequest(model_id="groq:openai/gpt-oss-20b", messages=[{"role": "user", "content": "hi"}],
                            params={"max_tokens": 100}, endpoint=None, allow_fallbacks=False)
    res = run(provider(handler).complete(req))
    assert not res.ok and res.error_category == category and res.http_status == status
    assert res.retry_after_s == (pytest.approx(retry_after) if retry_after is not None else None)
    missing = run(provider(handler, key=None).complete(req))
    assert missing.error_category == ErrorCategory.AUTH and "GROQ_API_KEY" in (missing.error_message or "")


def test_settings_routing_and_long_retry_after(tmp_path, monkeypatch):
    assert AppContext.provider_name_for("groq:openai/gpt-oss-120b") == "groq"
    assert AppContext.provider_name_for("openai/gpt-oss-120b") == "openrouter"
    assert AppContext.provider_name_for("mock/optimal") == "mock"
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    monkeypatch.setenv("GROQ_PLAN", "Developer")
    s = load_settings(data_dir=tmp_path, auth_mode="open")
    assert s.groq_configured and s.groq_plan == "developer" and KEY not in repr(s)
    monkeypatch.setenv("GROQ_PLAN", "gold")
    with pytest.raises(ValueError, match="GROQ_PLAN"):
        load_settings(data_dir=tmp_path, auth_mode="open")
    # a daily quota's Retry-After is honoured (up to a day), not cut to minutes
    policy = RetryPolicy()
    assert policy.rate_limit_delay(1, 3 * 3600) == 3 * 3600
    assert policy.rate_limit_delay(1, 3 * 86400) == 86400
    assert policy.rate_limit_delay(1, None) == 15.0


def _groq_ctx(tmp_path, bodies: list[dict]) -> AppContext:
    """A context whose only real provider is Groq, answered by a fake Groq API."""
    ctx = make_ctx(make_settings(tmp_path, groq_api_key=KEY))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS)
        body = json.loads(request.content)
        bodies.append(body)
        book = ctx.answer_book(body["messages"][-1]["content"])
        assert book is not None
        return httpx.Response(200, json=completion(book[0] or "", model=body["model"]))

    ctx.providers["groq"] = GroqProvider(KEY, "https://groq.test/openai/v1", transport=httpx.MockTransport(handler))
    return ctx


def test_a_full_run_through_the_groq_adapter(tmp_path):
    bodies: list[dict] = []
    ctx = _groq_ctx(tmp_path, bodies)
    conn = ctx.connect()
    try:
        spec = RunSpec(model_id="groq:openai/gpt-oss-120b", profile_id="standard", mode=RunMode.QUICK_CHECK,
                       spend_limit_usd=1.0, concurrency=3)
        plan = asyncio.run(runs.plan(ctx, conn, spec))
        # Groq has no fallbacks, so only the practice pack keeps this run unranked; the free plan costs $0
        assert plan["blocking"] == [] and plan["not_ranked_reasons"] == ["quick check uses unranked practice instances"]
        assert plan["estimate"]["worst_case_usd"] == 0.0
        with pytest.raises(runs.RunError, match="no endpoint to pin"):
            asyncio.run(runs.plan(ctx, conn, spec.model_copy(update={"provider": "groq"})))
        run_id = asyncio.run(runs.create(ctx, conn, spec))
        qwen_spec = spec.model_copy(update={"model_id": "groq:qwen/qwen3.8-27b"})
        qwen_run = asyncio.run(runs.create(ctx, conn, qwen_spec))
    finally:
        conn.close()
    drain(ctx)
    s = summary(ctx, run_id)
    assert s["state"] == "completed" and s["scores"]["completed"] == 9 and s["scores"]["overall"] == pytest.approx(100)
    assert s["cost"]["spent_usd"] == 0.0 and s["consistency"]["model_matches_request"] is True
    assert s["consistency"]["observed_providers"] == ["Groq"]
    oss = [b for b in bodies if b["model"] == "openai/gpt-oss-120b"]
    assert len(oss) == 9 and all(b["max_completion_tokens"] == 65536 and "reasoning_format" not in b for b in oss)
    qwen = [b for b in bodies if b["model"] == "qwen/qwen3.8-27b"]
    assert len(qwen) == 9 and all(b["reasoning_format"] == "parsed" and b["max_completion_tokens"] == 16384 for b in qwen)
    stored = q(ctx, "SELECT request_template_json FROM runs WHERE run_id=?", (qwen_run,))[0]
    assert json.loads(stored["request_template_json"])["settings"]["provider_params"] == {"reasoning_format": "parsed"}
