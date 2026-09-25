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


PROFILES: tuple[RunProfile, ...] = (
    RunProfile(
        id="standard", version="prof-standard-1", label="Standard",
        description="Prompt-requested JSON, 8,192 output tokens (reasoning included), temperature 0 "
                    "where supported, reasoning left at the model default.",
        max_tokens=8192, temperature=0.0, reasoning=None, requires=(),
        enforcement="Reasoning is not controlled: each model uses its own default. Temperature is "
                    "sent only when the model lists it as supported.",
    ),
    RunProfile(
        id="reasoning-low", version="prof-reasoning-low-1", label="Reasoning: low effort",
        description="reasoning.effort = low, 16,384 output tokens (reasoning included).",
        max_tokens=16384, temperature=None, reasoning={"effort": "low"}, requires=("reasoning",),
        enforcement="Effort is a request; OpenRouter maps it per model, so equal labels do not imply "
                    "equal reasoning budgets across models.",
    ),
    RunProfile(
        id="reasoning-high", version="prof-reasoning-high-1", label="Reasoning: high effort",
        description="reasoning.effort = high, 32,768 output tokens (reasoning included).",
        max_tokens=32768, temperature=None, reasoning={"effort": "high"}, requires=("reasoning",),
        enforcement="Effort is a request; OpenRouter maps it per model, so equal labels do not imply "
                    "equal reasoning budgets across models.",
    ),
)
PROFILE_BY_ID = {p.id: p for p in PROFILES}


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
    elif ctx < prompt_tokens + profile.max_tokens:
        problems.append(f"context {ctx} < prompt ~{prompt_tokens} + output budget {profile.max_tokens}")
    max_out = endpoint.max_completion_tokens if endpoint else model.max_completion_tokens
    if max_out is not None and max_out < profile.max_tokens:
        problems.append(f"max completion tokens {max_out} < output budget {profile.max_tokens}")
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


def request_params(model: ModelInfo, profile: RunProfile, endpoint: EndpointInfo | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """(params sent, record of requested vs applied settings)."""
    params: dict[str, Any] = {"max_tokens": profile.max_tokens}
    supported = set(endpoint.supported_parameters if endpoint else model.supported_parameters)
    record: dict[str, Any] = {"profile": profile.id, "profile_version": profile.version,
                              "max_tokens": profile.max_tokens}
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
