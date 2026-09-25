"""Versioned Pydantic contracts for Shadow Twins instances, answers, evaluations, certificates and
replays. JSON Schemas generated from these models are committed under ``contracts/schemas`` with
their hashes in ``contracts/VERSIONS.json`` (see ``shadowtwins.cli export-contracts``).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from benchcore.hashing import content_hash

from . import grid
from .versions import MAX_BUDGET, MAX_ENTRANCES, MIN_BUDGET, MIN_ENTRANCES

Coord = Annotated[
    tuple[
        Annotated[int, Field(ge=0, le=3)],
        Annotated[int, Field(ge=0, le=3)],
        Annotated[int, Field(ge=0, le=3)],
    ],
    Field(description="Cell (x, y, z); x = column, y = row, z = layer (0 = bottom)."),
]
Rows = Annotated[
    list[list[int]], Field(description="4x4 0/1 array indexed rows[v][u]; see docs/FORMAL_RULES.md")
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- instance ---------------------------------------------------------------------------------

class InstanceMeta(Frozen):
    """Provenance and labels. Excluded from the content hash."""

    label: str | None = None
    tier: str | None = None
    split: Literal["fixture", "development", "practice", "ranked"] | None = None
    generator_version: str | None = None
    seed: int | None = None
    notes: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class InstanceCore(Frozen):
    """The hashed identity of an instance: geometry, entrances, editable list and budget."""

    grid_size: Literal[4] = 4
    occupancy: str = Field(
        min_length=64, max_length=64, pattern=r"^[01]{64}$",
        description="Character i is cell index i = x + 4y + 16z; '1' solid, '0' empty.",
    )
    entrances: list[Coord] = Field(min_length=MIN_ENTRANCES, max_length=MAX_ENTRANCES)
    editable: list[Coord] = Field(min_length=1, max_length=64)
    budget: int = Field(ge=MIN_BUDGET, le=MAX_BUDGET)


class ShadowTwinsInstance(Frozen):
    schema_version: Literal["shadowtwins.instance.v1"] = "shadowtwins.instance.v1"
    instance_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.\-]+$")
    core: InstanceCore
    content_hash: str
    meta: InstanceMeta = Field(default_factory=InstanceMeta)

    @model_validator(mode="after")
    def _check_hash(self) -> ShadowTwinsInstance:
        expected = content_hash(self.core)
        if self.content_hash != expected:
            raise ValueError(f"content_hash mismatch: stored {self.content_hash}, computed {expected}")
        return self

    @classmethod
    def build(
        cls,
        instance_id: str,
        occupancy: int | str,
        entrances: list[tuple[int, int, int]],
        editable: list[tuple[int, int, int]],
        budget: int,
        meta: InstanceMeta | None = None,
    ) -> ShadowTwinsInstance:
        occ = occupancy if isinstance(occupancy, str) else grid.occupancy_to_string(occupancy)
        core = InstanceCore(
            occupancy=occ,
            entrances=[tuple(c) for c in entrances],  # type: ignore[misc]
            editable=[tuple(c) for c in editable],  # type: ignore[misc]
            budget=budget,
        )
        return cls(instance_id=instance_id, core=core, content_hash=content_hash(core),
                   meta=meta or InstanceMeta())

    # convenience accessors (not serialized)
    @property
    def occupancy_mask(self) -> int:
        return grid.occupancy_from_string(self.core.occupancy)

    @property
    def entrance_indices(self) -> list[int]:
        return [grid.index(*c) for c in self.core.entrances]

    @property
    def editable_indices(self) -> list[int]:
        return [grid.index(*c) for c in self.core.editable]


# --- answers ----------------------------------------------------------------------------------

class Edit(Strict):
    """Relocation answer: ``remove`` and ``add`` are editable-cell IDs, applied simultaneously."""

    remove: list[StrictInt] = Field(max_length=64)
    add: list[StrictInt] = Field(max_length=64)


class InvalidCategory(StrEnum):
    MALFORMED_JSON = "malformed_json"  # malformed or ambiguous JSON, prose-wrapped, wrong keys
    INVALID_IDS_OR_TYPES = "invalid_ids_or_types"
    DUPLICATE_IDS = "duplicate_ids"
    WRONG_SOURCE_OCCUPANCY = "wrong_source_occupancy"
    UNEQUAL_EDIT_COUNTS = "unequal_edit_counts"
    BUDGET_EXCEEDED = "budget_exceeded"
    IMMUTABLE_CELL_MODIFIED = "immutable_cell_modified"
    SILHOUETTE_CHANGED = "silhouette_changed"
    SOLID_DISCONNECTED = "solid_disconnected"
    REFUSAL = "refusal"
    TRUNCATED = "truncated"


class ParseOutcome(Strict):
    parser_version: str
    ok: bool
    category: InvalidCategory | None = None
    detail: str | None = Field(default=None, description="Stable machine sub-code, e.g. prose_wrapped.")
    message: str | None = None
    edit: Edit | None = None
    json_text: str | None = Field(default=None, description="The JSON text that was parsed.")


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


class CheckCode(StrEnum):
    PARSE = "parse"
    ID_TYPES = "id_types"
    NO_DUPLICATES = "no_duplicates"
    SOURCE_OCCUPANCY = "source_occupancy"
    EQUAL_COUNTS = "equal_counts"
    BUDGET = "budget"
    IMMUTABLE_CELLS = "immutable_cells"
    SILHOUETTE_X = "silhouette_x"
    SILHOUETTE_Y = "silhouette_y"
    SILHOUETTE_Z = "silhouette_z"
    SOLID_CONNECTED = "solid_connected"


class Check(Strict):
    code: CheckCode
    status: CheckStatus
    message: str
    cells: list[Coord] = Field(default_factory=list, description="Offending cells, if any.")
    ids: list[int] = Field(default_factory=list, description="Offending editable IDs, if any.")


class AnswerValidation(Strict):
    valid: bool
    category: InvalidCategory | None
    checks: list[Check]
    final_occupancy: str | None = Field(
        default=None, description="Occupancy after applying the requested edit, when constructible."
    )


class ShadowTwinsEvaluation(Strict):
    schema_version: Literal["shadowtwins.evaluation.v1"] = "shadowtwins.evaluation.v1"
    instance_id: str
    instance_hash: str
    versions: dict[str, str]
    parse: ParseOutcome
    edit: Edit | None
    valid: bool
    category: InvalidCategory | None
    checks: list[Check]
    final_occupancy: str | None
    raw_objective: int | None = Field(description="v(B): changed entrance pairs; null if invalid.")
    v_star: int = Field(ge=1)
    score: float = Field(ge=0, le=100, description="100 * v / v_star if valid, else 0.")
    opened: int | None = None
    closed: int | None = None
    move_count: int | None = None
    is_optimal: bool = False


# --- certificate ------------------------------------------------------------------------------

class Witness(Strict):
    remove: list[int]
    add: list[int]
    objective: int


class RejectionCounts(Strict):
    """Enumerated candidates rejected, charged to the FIRST failing constraint in order
    (silhouette, then solid connectivity)."""

    silhouette: int
    solid_disconnected: int


class ConstraintTotals(Strict):
    """Independent totals over all enumerated candidates (a candidate can count in both)."""

    silhouette_fail: int
    solid_disconnected: int
    both: int


class NoShadowAblation(Strict):
    """Research diagnostic: the same edit space with the silhouette constraint removed.
    Never part of official scores."""

    legal_count: int
    v_star: int
    histogram: dict[str, int]
    best_witness: Witness | None


class CertificateCore(Strict):
    """Deterministic content of a certificate. Hashed as ``core_hash``."""

    instance_id: str
    instance_hash: str
    versions: dict[str, str]
    budget: int
    solid_editable: int = Field(description="s: editable cells solid in the original.")
    empty_editable: int = Field(description="e: editable cells empty in the original.")
    expected_enumerated_count: int = Field(description="sum_r C(s,r) C(e,r), r <= min(b,s,e).")
    enumerated_count: int
    legal_count: int
    v_star: int
    v_min: int
    optimal_count: int
    min_moves_for_optimum: int | None
    histogram: dict[str, int] = Field(description="Legal candidates by objective value.")
    histogram_by_moves: dict[str, dict[str, int]] = Field(
        description="Legal candidates by move count, then objective value."
    )
    best_witness: Witness = Field(description="Lexicographically first optimum (fewest moves).")
    worst_witness: Witness
    rejections: RejectionCounts
    constraint_totals: ConstraintTotals
    no_shadow: NoShadowAblation
    exhaustive: Literal[True] = True
    admissible: bool
    inadmissible_reason: str | None = None


class VerificationRecord(Strict):
    status: Literal["verified", "mismatch", "error", "not_run"]
    verifier_version: str | None = None
    runtime_ms: float | None = None
    mismatches: list[str] = Field(default_factory=list)
    checked_at: str | None = None


class CertificateRun(Strict):
    """Non-deterministic run facts. Excluded from ``core_hash``."""

    runtime_ms: float
    created_at: str
    python: str


class ShadowTwinsCertificate(Strict):
    schema_version: Literal["shadowtwins.certificate.v1"] = "shadowtwins.certificate.v1"
    core: CertificateCore
    core_hash: str
    run: CertificateRun
    independent_verification: VerificationRecord = Field(
        default_factory=lambda: VerificationRecord(status="not_run")
    )

    @model_validator(mode="after")
    def _check_hash(self) -> ShadowTwinsCertificate:
        expected = content_hash(self.core)
        if self.core_hash != expected:
            raise ValueError(f"core_hash mismatch: stored {self.core_hash}, computed {expected}")
        return self


# --- replay -----------------------------------------------------------------------------------

class Silhouettes(Strict):
    x: Rows = Field(description="View along x: rows[z][y].")
    y: Rows = Field(description="View along y: rows[z][x].")
    z: Rows = Field(description="View along z: rows[y][x].")


class Component(Strict):
    id: int
    cells: list[Coord]
    entrances: list[int] = Field(default_factory=list, description="Entrance indices inside it.")


class PathTrace(Strict):
    i: int
    j: int
    cells: list[Coord] = Field(description="Deterministic shortest empty-cell path from i to j.")


class GridState(Strict):
    occupancy: str
    silhouettes: Silhouettes
    empty_components: list[Component] = Field(
        description="Components of empty cells that contain at least one entrance."
    )
    other_empty_cells: list[Coord] = Field(
        description="Empty cells in components containing no entrance (cavities)."
    )
    solid_components: list[Component]
    entrance_component: list[int] = Field(description="Component id per entrance index.")
    paths: list[PathTrace] = Field(description="One path per connected entrance pair (i < j).")


class PairChange(StrEnum):
    OPENED = "opened"
    CLOSED = "closed"
    UNCHANGED = "unchanged"


class PairStatus(Strict):
    i: int
    j: int
    original: bool
    final: bool
    change: PairChange


class EditableCellInfo(Strict):
    id: int
    cell: Coord
    originally_solid: bool


class EntranceInfo(Strict):
    index: int
    label: str
    cell: Coord


class OutcomeView(Strict):
    """One final object (the model's answer or the optimum) relative to the original."""

    label: Literal["model", "optimal", "noop", "practice", "custom"]
    edit: Edit | None
    valid: bool
    category: InvalidCategory | None
    checks: list[Check]
    final: GridState | None = Field(description="Null when no final object can be constructed.")
    removed: list[Coord]
    added: list[Coord]
    silhouette_mismatch: Silhouettes | None = Field(description="1 where final differs from original.")
    pairs: list[PairStatus]
    raw_objective: int | None
    v_star: int
    score: float
    opened: int | None
    closed: int | None
    move_count: int | None


class ShadowTwinsReplay(Strict):
    schema_version: Literal["shadowtwins.replay.v1"] = "shadowtwins.replay.v1"
    replay_version: str
    evaluator_version: str
    instance_id: str
    instance_hash: str
    certificate_hash: str
    budget: int
    editable: list[EditableCellInfo]
    entrances: list[EntranceInfo]
    original: GridState
    optimal: OutcomeView
    model: OutcomeView | None = None

    @field_validator("entrances")
    @classmethod
    def _labels_unique(cls, v: list[EntranceInfo]) -> list[EntranceInfo]:
        if len({e.label for e in v}) != len(v):
            raise ValueError("entrance labels must be unique")
        return v
