"""Development-only no-shadow ablation (research diagnostic, never an official score).

The ablation keeps the same geometry, entrances, editable list and budget but removes the
silhouette rule from both the prompt and the evaluation. Scores are normalized by the certificate's
``no_shadow.v_star`` — the ablation's own exhaustively computed optimum — never by ``v*``.
"""

from __future__ import annotations

from benchcore.contracts import ChatMessage, CompletionMeta, RenderedPrompt
from benchcore.hashing import content_hash

from . import grid
from .contracts import (
    Check,
    CheckCode,
    CheckStatus,
    InvalidCategory,
    ShadowTwinsCertificate,
    ShadowTwinsEvaluation,
    ShadowTwinsInstance,
)
from .engine import compile_instance, objective
from .evaluate import evaluate_text
from .prompt import render_user_text
from .versions import BENCHMARK_ID, PROTOCOL_VERSION

ABLATION_PROTOCOL_VERSION = f"{PROTOCOL_VERSION}+noshadow"
_SHADOW_RULE = (
    "2. The three shadows: every straight line of 4 cells parallel to the x, y or z axis "
    "contains a solid cube after the moves exactly when it did before."
)
_SILHOUETTE_CODES = {CheckCode.SILHOUETTE_X, CheckCode.SILHOUETTE_Y, CheckCode.SILHOUETTE_Z}


def render_prompt_no_shadow(inst: ShadowTwinsInstance) -> RenderedPrompt:
    text = render_user_text(inst)
    if _SHADOW_RULE not in text:  # pragma: no cover - guards against prompt drift
        raise RuntimeError("standard prompt changed; update the ablation renderer")
    text = text.replace(_SHADOW_RULE + "\n", "").replace(
        "3. All solid cubes as one piece", "2. All solid cubes as one piece")
    messages = [ChatMessage(role="user", content=text)]
    return RenderedPrompt(benchmark_id=BENCHMARK_ID, instance_id=inst.instance_id,
                          protocol_version=ABLATION_PROTOCOL_VERSION, messages=messages,
                          text_hash=content_hash([m.model_dump() for m in messages]))


def evaluate_no_shadow(
    inst: ShadowTwinsInstance, cert: ShadowTwinsCertificate, raw_text: str | None,
    meta: CompletionMeta | None = None,
) -> ShadowTwinsEvaluation:
    """Evaluate with the silhouette rule removed and normalize by the ablation optimum."""
    ns_star = cert.core.no_shadow.v_star
    if ns_star <= 0:
        raise ValueError("ablation optimum is 0; instance cannot be scored in the ablation")
    # Use a large v_star so the standard evaluator never rejects an ablation-only objective.
    base = evaluate_text(inst, 10**6, raw_text, meta)
    checks = [
        Check(code=ch.code, status=CheckStatus.SKIPPED, message="silhouette rule removed (ablation)")
        if ch.code in _SILHOUETTE_CODES else ch
        for ch in base.checks
    ]
    failing = [ch for ch in checks if ch.status == CheckStatus.FAIL and ch.code != CheckCode.PARSE]
    if not base.parse.ok or base.final_occupancy is None or failing:
        category = base.category
        if category == InvalidCategory.SILHOUETTE_CHANGED:
            category = InvalidCategory.SOLID_DISCONNECTED if failing else None
        return base.model_copy(update={"checks": checks, "v_star": ns_star, "category": category,
                                       "valid": False, "score": 0.0, "raw_objective": None})
    c = compile_instance(inst)
    v, opened, closed = objective(c, grid.occupancy_from_string(base.final_occupancy))
    assert base.edit is not None
    return base.model_copy(update={
        "checks": checks, "v_star": ns_star, "valid": True, "category": None, "raw_objective": v,
        "score": 100.0 * v / ns_star, "opened": opened, "closed": closed,
        "move_count": len(base.edit.remove), "is_optimal": v == ns_star,
    })
