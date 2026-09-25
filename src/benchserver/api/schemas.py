"""Public API schemas (``api-1.0.0``). The committed ``contracts/openapi.json`` is generated from the
FastAPI app and checked for drift in tests; the frontend generates its TypeScript types from it."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from benchcore.contracts import RunSpec

API_VERSION = "api-1.0.0"


class Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Compat(Out):
    profile_id: str
    compatible: bool
    problems: list[str]
    warnings: list[str]


class CatalogModel(Out):
    provider: str
    model_id: str
    name: str
    context_length: int | None
    pricing: dict[str, float | None]
    pricing_known: bool
    supported_parameters: list[str]
    reasoning: dict[str, Any] | None
    max_completion_tokens: int | None
    description: str
    is_mock: bool
    favorite: bool = False
    compat: list[Compat] = Field(default_factory=list)


class SnapshotInfo(Out):
    snapshot_id: int
    fetched_at: str
    model_count: int
    stale: bool


class Catalog(Out):
    models: list[CatalogModel]
    snapshots: dict[str, SnapshotInfo]
    errors: dict[str, str]
    favorites: list[str]
    recents: list[str]


class Endpoint(Out):
    slug: str
    provider_name: str
    context_length: int | None
    pricing: dict[str, float | None]
    supported_parameters: list[str]
    max_completion_tokens: int | None
    quantization: str | None
    status: int | None
    compat: list[Compat] = Field(default_factory=list)


class Endpoints(Out):
    model_id: str
    endpoints: list[Endpoint]
    error: str | None


class Profile(Out):
    id: str
    version: str
    label: str
    description: str
    max_tokens: int
    temperature: float | None
    reasoning: dict[str, Any] | None
    requires: list[str]
    enforcement: str


class PackSummary(Out):
    pack_id: str
    benchmark_id: str
    split: str
    ranked: bool
    pack_hash: str
    policy_hash: str | None
    instances: int
    tiers: list[dict[str, Any]]
    token_max: int | None
    versions: dict[str, str]


class Meta(Out):
    api_version: str
    suite: dict[str, Any]
    benchmarks: list[dict[str, Any]]
    auth: dict[str, Any]
    providers: dict[str, Any]
    packs: list[PackSummary]
    profiles: list[Profile]
    modes: list[dict[str, Any]]


class RunCreate(RunSpec):
    pack_id: str | None = Field(default=None, description="Defaults to the loaded pack for the mode.")


class Estimate(Out):
    calls: int
    pricing_known: bool
    max_per_call_usd: float | None
    worst_case_usd: float | None
    typical_usd: float | None
    assumptions: dict[str, Any]


class RunPlan(Out):
    model: dict[str, Any]
    provider: str
    endpoint: dict[str, Any] | None
    endpoint_error: str | None
    profile: Profile
    compatibility: Compat
    pack: dict[str, Any]
    mode: str
    track: str
    repetitions: int
    estimate: Estimate
    ranked: bool
    not_ranked_reasons: list[str]
    blocking: list[str]


class ScoreSummary(Out):
    aggregation_version: str
    scheduled: int
    completed: int
    states: dict[str, int]
    official: bool
    overall: float | None
    provisional_overall: float | None
    tiers: dict[str, float]
    interval_95: list[float] | None
    valid_rate: float | None
    conditional_quality: float | None
    optimal_rate: float | None
    categories: dict[str, int]
    instances: int


class CostSummary(Out):
    spend_limit_usd: float
    spent_usd: float
    reserved_usd: float
    pricing: dict[str, float | None]
    pricing_known: bool
    estimated_cost_attempts: int
    uncertain_cost_attempts: int


class UsageSummary(Out):
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    attempts: int


class LatencySummary(Out):
    mean: float | None
    median: float | None
    n: int


class Consistency(Out):
    observed_providers: list[str]
    observed_models: list[str]
    provider_matches_pin: bool | None
    model_matches_request: bool | None
    provider_unreported_on_some_responses: bool


class RunSummary(Out):
    run_id: str
    created_at: str
    updated_at: str
    completed_at: str | None
    state: str
    state_reason: str | None
    provider: str
    model_id: str
    endpoint: str | None
    profile_id: str
    profile: Profile
    mode: str
    track: str
    pack_id: str
    pack_hash: str
    repetitions: int
    is_mock: bool
    ranked: bool
    not_ranked_reasons: list[str]
    leaderboard_eligible: bool
    ineligible_reasons: list[str]
    suite_version: str
    versions: dict[str, str]
    fingerprint: str
    request: dict[str, Any]
    model_meta: dict[str, Any]
    consistency: Consistency
    cost: CostSummary
    usage: UsageSummary
    latency_ms: LatencySummary
    concurrency: int
    scores: ScoreSummary
    last_event_id: int


class RunItem(Out):
    job_id: int
    instance_id: str
    tier: str
    repetition: int
    ord: int
    state: str
    attempts: int
    last_error: str | None
    valid: bool | None
    category: str | None
    score: float | None
    raw_objective: int | None
    max_objective: int | None
    cost_usd: float | None
    latency_ms: float | None


class ActionBody(BaseModel):
    value: float | None = None


class LeaderboardRow(Out):
    rank: int
    model_id: str
    model_name: str
    endpoint: str | None
    provider_name: str | None
    profile_id: str
    track: str
    overall: float | None
    shadow_twins: float | None
    tiers: dict[str, float]
    interval_95: list[float] | None
    valid_rate: float | None
    conditional_quality: float | None
    optimal_rate: float | None
    completed: int
    scheduled: int
    cost_usd: float
    latency_ms: float | None
    evaluated_at: str | None
    suite_version: str
    pack_id: str
    pack_hash: str
    versions: dict[str, str]
    run_id: str
    runs_in_group: int


class Leaderboard(Out):
    listing_policy: str
    track: str
    profile_id: str | None
    suite: dict[str, Any]
    rows: list[LeaderboardRow]


class ModelRun(Out):
    run_id: str
    created_at: str
    completed_at: str | None
    state: str
    track: str
    profile_id: str
    endpoint: str | None
    ranked: bool
    is_mock: bool
    leaderboard_eligible: bool
    ineligible_reasons: list[str]
    fingerprint: str
    overall: float | None
    provisional_overall: float | None
    valid_rate: float | None
    optimal_rate: float | None
    cost_usd: float


class ModelDetail(Out):
    model_id: str
    model: dict[str, Any] | None = None
    latest_eligible: list[RunSummary]
    runs: list[ModelRun]
    categories: dict[str, int]
    score_histogram: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None


class PracticeSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    remove: list[StrictInt] = Field(max_length=64)
    add: list[StrictInt] = Field(max_length=64)


class InstanceSummary(Out):
    instance_id: str
    pack_id: str
    tier: str
    ord: int
    budget: int | None = None
    entrances: int | None = None
    editable: int | None = None
    tokens_max: int | None = None
