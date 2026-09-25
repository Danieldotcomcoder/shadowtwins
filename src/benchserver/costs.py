"""Cost estimation and conservative reservations (USD).

A reservation is the worst case for one call under the run's profile: an inflated prompt estimate
at the prompt price plus the full output budget at the higher of the completion and internal
reasoning prices, plus any per-request fee. Reservations are taken before dispatch and replaced by
the reported (or, if unreported, token-estimated) cost afterwards. Provider billing can still
differ slightly (template tokens, rounding), so a spending limit is enforced conservatively but
cannot be guaranteed to the cent.
"""

from __future__ import annotations

import math
from typing import Any

from .providers.base import CompletionResult

PROMPT_INFLATION = 1.25
PROMPT_OVERHEAD_TOKENS = 64
TYPICAL_OUTPUT_TOKENS = 1500


def prompt_estimate(tokens_max: int | None) -> int:
    return math.ceil((tokens_max or 800) * PROMPT_INFLATION) + PROMPT_OVERHEAD_TOKENS


def _out_price(p: dict[str, float | None]) -> float | None:
    c = p.get("completion")
    if c is None:
        return None
    return max(c, p.get("internal_reasoning") or 0.0)


def reservation(pricing: dict[str, float | None], tokens_max: int | None, max_tokens: int) -> float | None:
    pp, op = pricing.get("prompt"), _out_price(pricing)
    if pp is None or op is None:
        return None
    return prompt_estimate(tokens_max) * pp + max_tokens * op + (pricing.get("request") or 0.0)


def estimate(pricing: dict[str, float | None], prompt_tokens: list[int | None], max_tokens: int) -> dict[str, Any]:
    calls = len(prompt_tokens)
    per = [reservation(pricing, t, max_tokens) for t in prompt_tokens]
    known = all(r is not None for r in per)
    typical = None
    if known:
        pp, op = pricing["prompt"] or 0.0, _out_price(pricing) or 0.0
        typical = sum(prompt_estimate(t) * pp + min(max_tokens, TYPICAL_OUTPUT_TOKENS) * op
                      + (pricing.get("request") or 0.0) for t in prompt_tokens)
    return {
        "calls": calls,
        "pricing_known": known,
        "max_per_call_usd": max(per) if known and per else None,  # type: ignore[type-var]
        "worst_case_usd": sum(per) if known else None,  # type: ignore[arg-type]
        "typical_usd": typical,
        "assumptions": {
            "prompt_tokens": f"panel max x {PROMPT_INFLATION} + {PROMPT_OVERHEAD_TOKENS}",
            "worst_case_output_tokens": max_tokens,
            "typical_output_tokens": min(max_tokens, TYPICAL_OUTPUT_TOKENS),
        },
    }


def actual_cost(result: CompletionResult, pricing: dict[str, float | None]) -> tuple[float | None, str]:
    """(cost, source): provider-reported when available, else estimated from reported usage."""
    if result.usage.cost_usd is not None:
        return result.usage.cost_usd, "reported"
    pt, ct = result.usage.prompt_tokens, result.usage.completion_tokens
    if pt is not None and ct is not None and pricing.get("prompt") is not None and pricing.get("completion") is not None:
        return (pt * (pricing["prompt"] or 0.0) + ct * (_out_price(pricing) or 0.0)
                + (pricing.get("request") or 0.0)), "estimated"
    return None, "none"
