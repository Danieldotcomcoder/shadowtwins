"""Frozen run profiles (generation-budget tracks) and model compatibility.

Profiles state what is *requested*. Whether a provider applies a setting is recorded per attempt
(observed provider, finish reasons, reasoning tokens); reasoning controls differ across models and
are never presented as equivalent when they are not.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .providers.base import EndpointInfo, ModelInfo


@dataclass(frozen=True)
class RunProfile:
    id: str
    version: str
    label: str
    description: str
    max_tokens: int
    temperature: float | None
    reasoning: dict[str, Any] | None
    requires: tuple[str, ...]
    enforcement: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["requires"] = list(self.requires)
        return d


# Output budgets are ceilings that should rarely bind: thinking models spend most of their output
# reasoning, and a budget that cuts them off measures the budget, not the model (v1 profiles gave
# 8,192 tokens and truncated a free Nemotron 3 Ultra on every item). A model whose own output or
# context limit is lower gets its own maximum instead (recorded per run), down to MIN_OUTPUT_TOKENS.
MIN_OUTPUT_TOKENS = 8192

PROFILES: tuple[RunProfile, ...] = (
    RunProfile(
        id="standard", version="prof-standard-2", label="Standard",
        description="Prompt-requested JSON, up to 65,536 output tokens (reasoning included; capped at "
                    "the model's own limit), temperature 0 where supported, reasoning left at the "
                    "model default.",
        max_tokens=65536, temperature=0.0, reasoning=None, requires=(),
        enforcement="Reasoning is not controlled: each model uses its own default. Temperature is "
                    "sent only when the model lists it as supported.",
    ),
    RunProfile(
        id="reasoning-low", version="prof-reasoning-low-2", label="Reasoning: low effort",
        description="reasoning.effort = low, up to 65,536 output tokens (reasoning included; capped at "
                    "the model's own limit).",
        max_tokens=65536, temperature=None, reasoning={"effort": "low"}, requires=("reasoning",),
        enforcement="Effort is a request; OpenRouter maps it per model, so equal labels do not imply "
                    "equal reasoning budgets across models.",
    ),
    RunProfile(
        id="reasoning-high", version="prof-reasoning-high-2", label="Reasoning: high effort",
        description="reasoning.effort = high, up to 131,072 output tokens (reasoning included; capped "
                    "at the model's own limit).",
        max_tokens=131072, temperature=None, reasoning={"effort": "high"}, requires=("reasoning",),
        enforcement="Effort is a request; OpenRouter maps it per model, so equal labels do not imply "
                    "equal reasoning budgets across models.",
    ),
)
PROFILE_BY_ID = {p.id: p for p in PROFILES}


def output_budget(model: ModelInfo, profile: RunProfile, prompt_tokens: int,
                  endpoint: EndpointInfo | None = None) -> tuple[int, str | None]:
    """(output tokens to request, what capped it below the profile ceiling, if anything)."""
    budget, capped_by = profile.max_tokens, None
    max_out = endpoint.max_completion_tokens if endpoint else model.max_completion_tokens
    if max_out is not None and max_out < budget:
        budget, capped_by = max_out, f"the model's max completion tokens ({max_out:,})"
    ctx = endpoint.context_length if endpoint and endpoint.context_length else model.context_length
    if ctx is not None and ctx - prompt_tokens < budget:
        budget, capped_by = max(0, ctx - prompt_tokens), f"the context window ({ctx:,} minus the prompt)"
    return budget, capped_by


def compatibility(model: ModelInfo, profile: RunProfile, prompt_tokens: int,
                  endpoint: EndpointInfo | None = None) -> dict[str, Any]:
    """Whether ``profile`` can be honoured by ``model`` (and a pinned endpoint)."""
    problems: list[str] = []
    warnings: list[str] = []
    params = set(endpoint.supported_parameters if endpoint else model.supported_parameters)
    for req in profile.requires:
        if req not in params:
            problems.append(f"model does not support '{req}'")
    ctx = endpoint.context_length if endpoint and endpoint.context_length else model.context_length
    if ctx is None:
        warnings.append("context length unknown")
    budget, capped_by = output_budget(model, profile, prompt_tokens, endpoint)
    if budget < MIN_OUTPUT_TOKENS:
        problems.append(f"output budget {budget:,} (limited by {capped_by}) is below the minimum "
                        f"{MIN_OUTPUT_TOKENS:,}")
    elif capped_by:
        warnings.append(f"output budget {budget:,} tokens (limited by {capped_by}; profile allows "
                        f"{profile.max_tokens:,})")
    if profile.reasoning and model.reasoning:
        efforts = model.reasoning.get("supported_efforts")
        eff = profile.reasoning.get("effort")
        if efforts and eff not in efforts:
            problems.append(f"effort '{eff}' not in supported efforts {efforts}")
    if profile.temperature is not None and "temperature" not in params:
        warnings.append("temperature not supported; it will be omitted")
    if profile.reasoning is None and model.reasoning and model.reasoning.get("mandatory"):
        warnings.append("model always reasons; the standard profile does not change that")
    return {"profile_id": profile.id, "compatible": not problems, "problems": problems, "warnings": warnings}


def request_params(model: ModelInfo, profile: RunProfile, endpoint: EndpointInfo | None,
                   prompt_tokens: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """(params sent, record of requested vs applied settings)."""
    budget, capped_by = output_budget(model, profile, prompt_tokens, endpoint)
    params: dict[str, Any] = {"max_tokens": budget}
    supported = set(endpoint.supported_parameters if endpoint else model.supported_parameters)
    record: dict[str, Any] = {"profile": profile.id, "profile_version": profile.version,
                              "max_tokens": budget, "profile_max_tokens": profile.max_tokens,
                              "max_tokens_capped_by": capped_by}
    if profile.temperature is not None:
        if "temperature" in supported:
            params["temperature"] = profile.temperature
            record["temperature"] = {"requested": profile.temperature, "sent": True}
        else:
            record["temperature"] = {"requested": profile.temperature, "sent": False,
                                     "reason": "not in supported_parameters"}
    if profile.reasoning is not None:
        params["reasoning"] = dict(profile.reasoning)
        record["reasoning"] = {"requested": profile.reasoning, "sent": True,
                               "note": "applied reasoning is observable only through reasoning tokens"}
    else:
        record["reasoning"] = {"requested": None, "sent": False, "note": "model default"}
    return params, record
