"""Admission, tier and selection policy (``st-policy-1.0.0``). Owned by P2.

Frozen after the development pilot (docs/research/ADMISSION_POLICY.md) and **before** any
practice or ranked candidate was generated. Changing a threshold, tier rule, seed range or
selection procedure creates a new policy version and new pack versions; existing packs are never
re-selected. No model output is used anywhere in admission or selection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from benchcore.hashing import content_hash

from .tokens import CEILING, PANEL_VERSION
from .versions import GENERATOR_VERSION

POLICY_VERSION = "st-policy-1.0.0"


@dataclass(frozen=True)
class Admission:
    min_v_star: int = 2
    min_partial_levels: int = 1
    max_optimum_density: float = 0.25
    min_shadow_rejection_rate: float = 0.20
    min_shadow_traps: int = 1
    max_tokens: int = CEILING
    token_panel: str = PANEL_VERSION


@dataclass(frozen=True)
class Tier:
    id: str
    name: str
    budget: int
    rule: str


TIERS: tuple[Tier, ...] = (
    Tier("T1", "single relocation", 1, "admitted with budget 1"),
    Tier("T2", "paired relocations", 2,
         "admitted with budget 2 and the optimum needs exactly 2 relocations"),
    Tier("T3", "coordinated search", 3,
         "admitted with budget 3 and (the optimum needs 3 relocations or the deterministic local "
         "search baseline does not reach the optimum)"),
)
TIER_BY_ID = {t.id: t for t in TIERS}


@dataclass(frozen=True)
class Selection:
    seed_bases: dict[str, int] = field(default_factory=lambda: {
        "development": 1_000_000, "practice": 2_000_000, "ranked": 3_000_000})
    per_tier: dict[str, int] = field(default_factory=lambda: {
        "development": 10, "practice": 3, "ranked": 10})
    max_candidates_per_tier: int = 50_000
    procedure: str = (
        "For each tier, iterate seeds base + tier_offset + k for k = 0, 1, 2, ... with the tier's "
        "budget; keep a candidate when it is structurally valid, admitted, matches the tier rule "
        "and its geometry key (48-symmetry canonical form of occupancy + entrance set) was not "
        "used by any earlier accepted instance in any split; stop at the per-tier target."
    )
    tier_offsets: dict[str, int] = field(default_factory=lambda: {"T1": 0, "T2": 100_000, "T3": 200_000})


ADMISSION = Admission()
SELECTION = Selection()


def policy_document() -> dict[str, Any]:
    doc = {
        "policy_version": POLICY_VERSION,
        "generator_version": GENERATOR_VERSION,
        "admission": asdict(ADMISSION),
        "tiers": [asdict(t) for t in TIERS],
        "selection": asdict(SELECTION),
    }
    doc["policy_hash"] = content_hash(doc)
    return doc


def admission_failures(m: dict[str, Any], a: Admission = ADMISSION) -> list[str]:
    """Reasons a measured candidate is not admitted (empty list = admitted)."""
    out = []
    if m["v_star"] < a.min_v_star:
        out.append("v_star_below_min")
    if len(m["partial_levels"]) < a.min_partial_levels:
        out.append("no_partial_credit")
    if m["optimum_density"] > a.max_optimum_density:
        out.append("optimum_too_dense")
    if m["shadow_rejection_rate"] < a.min_shadow_rejection_rate:
        out.append("shadow_inactive")
    if m["shadow_traps"] < a.min_shadow_traps:
        out.append("no_shadow_traps")
    if m.get("tokens_max", 0) > a.max_tokens:
        out.append("token_ceiling")
    return out


def matches_tier(m: dict[str, Any], tier: Tier) -> bool:
    if m["budget"] != tier.budget:
        return False
    if tier.id == "T1":
        return True
    if tier.id == "T2":
        return m["min_moves_for_optimum"] == 2
    return m["min_moves_for_optimum"] == 3 or m["local_search_score"] < 100.0
