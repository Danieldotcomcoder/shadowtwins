"""Benchmark-agnostic contracts shared by the suite runner, the API and every benchmark module.

These models are versioned public contracts (``CONTRACTS_VERSION``). Benchmark-specific payloads
(instances, certificates, replays) live in each module; the runner only ever touches the generic
envelope defined here, so it never hardcodes Shadow Twins geometry.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACTS_VERSION = "1.0.0"
SUITE_ID = "llmbench-suite"
# Suite version 1 contains exactly one benchmark. Adding a benchmark to ranked aggregation creates
# a new suite version; historical one-benchmark results are never recomputed as a larger suite.
SUITE_VERSION = "suite-1"
SUITE_BENCHMARKS: tuple[str, ...] = ("shadow_twins",)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatMessage(Strict):
    role: Literal["system", "user"]
    content: str


class RenderedPrompt(Strict):
    """The exact authored text sent to a model for one instance."""

    benchmark_id: str
    instance_id: str
    protocol_version: str
    messages: list[ChatMessage]
    text_hash: str = Field(description="sha256 of the canonical JSON of `messages`.")


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALLS = "tool_calls"
    ERROR = "error"
    UNKNOWN = "unknown"


class CompletionMeta(Strict):
    """Provider facts the parser may use. Never contains credentials."""

    finish_reason: FinishReason = FinishReason.UNKNOWN
    native_finish_reason: str | None = None
    refusal: str | None = Field(
        default=None, description="Provider-reported refusal text, when the API exposes one."
    )


class ScoreSemantics(Strict):
    """How a benchmark's per-item score is defined, for display and documentation."""

    scale_min: float = 0.0
    scale_max: float = 100.0
    formula: str
    higher_is_better: bool = True
    invalid_scores_zero: bool = True
    notes: str = ""


class BenchmarkMetadata(Strict):
    benchmark_id: str
    display_name: str
    description: str
    versions: dict[str, str]
    score: ScoreSemantics


class EvaluationEnvelope(Strict):
    """Generic view of one scored answer. ``detail`` holds the benchmark-specific evaluation."""

    benchmark_id: str
    instance_id: str
    instance_hash: str
    valid: bool
    category: str | None = Field(
        default=None, description="Invalid-answer category; null for valid answers."
    )
    score: float = Field(ge=0.0, le=100.0)
    raw_objective: int | None = None
    max_objective: int
    versions: dict[str, str]
    detail: dict[str, Any]


class InstanceValidation(Strict):
    ok: bool
    problems: list[str] = Field(default_factory=list)


class VerificationReport(Strict):
    status: Literal["verified", "mismatch", "error"]
    verifier_version: str
    runtime_ms: float
    mismatches: list[str] = Field(default_factory=list)
    recomputed: dict[str, Any] = Field(default_factory=dict)


# --- run-level contracts (initial versions; P3 owns the persisted implementation) --------------

class RunMode(StrEnum):
    QUICK_CHECK = "quick_check"  # practice instances, unranked
    STANDARD = "standard"  # ranked pack, one repetition
    REPEATED = "repeated"  # ranked pack, three repetitions, separate track


class JobState(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"  # claimed by a worker; request may be in flight
    RETRY_WAIT = "retry_wait"  # eligible transport/server/rate-limit failure, waiting to retry
    COMPLETED = "completed"  # a model answer was received and evaluated (valid or invalid)
    UNCERTAIN = "uncertain"  # request may have been processed remotely; outcome unknown
    CANCELLED = "cancelled"
    FAILED = "failed"  # final infrastructure failure after the fixed retry policy


TERMINAL_JOB_STATES = frozenset(
    {JobState.COMPLETED, JobState.UNCERTAIN, JobState.CANCELLED, JobState.FAILED}
)


class RunState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    BUDGET_STOPPED = "budget_stopped"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"  # every scheduled item has a completed, evaluated answer
    INCOMPLETE = "incomplete"  # nothing left to dispatch but some items failed or are uncertain


class RunSpec(Strict):
    """Operator request to start a run."""

    model_id: str
    provider: str | None = Field(
        default=None, description="Pinned provider endpoint slug, where supported."
    )
    profile_id: str
    mode: RunMode
    spend_limit_usd: float = Field(gt=0)
    concurrency: int = Field(default=2, ge=1, le=16)
    allow_unknown_pricing: bool = Field(
        default=False,
        description="Explicit unranked override to dispatch when model pricing is unknown.",
    )
    note: str | None = Field(default=None, max_length=500)
