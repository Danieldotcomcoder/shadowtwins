"""Answer validation and scoring (``st-eval-1.0.0``).

Check order (the first failing check determines the reported category; every check that can be
computed is still reported so invalid answers remain inspectable):

1. parse                 -> parser category (malformed_json, invalid_ids_or_types, refusal, truncated)
2. id_types              -> invalid_ids_or_types (ID outside 0..len(editable)-1)
3. no_duplicates         -> duplicate_ids (repeat within a list, or an ID in both lists)
4. source_occupancy      -> wrong_source_occupancy (remove must be solid, add must be empty)
5. equal_counts          -> unequal_edit_counts
6. budget                -> budget_exceeded (more than b IDs in either list)
7. immutable_cells       -> immutable_cell_modified
8. silhouette_x/y/z      -> silhouette_changed
9. solid_connected       -> solid_disconnected

A valid answer scores ``100 * v / v_star``; every invalid answer scores 0 with its category.
"""

from __future__ import annotations

from typing import Any

from benchcore.contracts import CompletionMeta

from . import grid
from .contracts import (
    AnswerValidation,
    Check,
    CheckCode,
    CheckStatus,
    Edit,
    InvalidCategory,
    ParseOutcome,
    ShadowTwinsEvaluation,
    ShadowTwinsInstance,
)
from .engine import Compiled, apply_ids, compile_instance, objective
from .parser import parse_answer
from .versions import EVALUATOR_VERSION, PARSER_VERSION, PROTOCOL_VERSION, RULES_VERSION

_ORDER: list[tuple[CheckCode, InvalidCategory]] = [
    (CheckCode.ID_TYPES, InvalidCategory.INVALID_IDS_OR_TYPES),
    (CheckCode.NO_DUPLICATES, InvalidCategory.DUPLICATE_IDS),
    (CheckCode.SOURCE_OCCUPANCY, InvalidCategory.WRONG_SOURCE_OCCUPANCY),
    (CheckCode.EQUAL_COUNTS, InvalidCategory.UNEQUAL_EDIT_COUNTS),
    (CheckCode.BUDGET, InvalidCategory.BUDGET_EXCEEDED),
    (CheckCode.IMMUTABLE_CELLS, InvalidCategory.IMMUTABLE_CELL_MODIFIED),
    (CheckCode.SILHOUETTE_X, InvalidCategory.SILHOUETTE_CHANGED),
    (CheckCode.SILHOUETTE_Y, InvalidCategory.SILHOUETTE_CHANGED),
    (CheckCode.SILHOUETTE_Z, InvalidCategory.SILHOUETTE_CHANGED),
    (CheckCode.SOLID_CONNECTED, InvalidCategory.SOLID_DISCONNECTED),
]

_AXIS_PIXELS = {
    "x": ("y", "z"),
    "y": ("x", "z"),
    "z": ("x", "y"),
}


def versions() -> dict[str, str]:
    return {
        "rules": RULES_VERSION,
        "parser": PARSER_VERSION,
        "evaluator": EVALUATOR_VERSION,
        "protocol": PROTOCOL_VERSION,
    }


def _skipped(code: CheckCode, why: str) -> Check:
    return Check(code=code, status=CheckStatus.SKIPPED, message=why)


def _passed(code: CheckCode, message: str) -> Check:
    return Check(code=code, status=CheckStatus.PASS, message=message)


def _silhouette_check(axis: str, code: CheckCode, before: int, after: int) -> Check:
    rows_a = grid.silhouette_rows(before)[axis]
    rows_b = grid.silhouette_rows(after)[axis]
    u_name, v_name = _AXIS_PIXELS[axis]
    diffs: list[str] = []
    ray_cells: list[tuple[int, int, int]] = []
    changed = before ^ after
    for v in range(grid.N):
        for u in range(grid.N):
            if rows_a[v][u] != rows_b[v][u]:
                state = "gained" if rows_b[v][u] else "lost"
                diffs.append(f"({u_name}={u},{v_name}={v}) {state}")
                for t in range(grid.N):
                    cell = {"x": (t, u, v), "y": (u, t, v), "z": (u, v, t)}[axis]
                    if (changed >> grid.index(*cell)) & 1:
                        ray_cells.append(cell)
    if not diffs:
        return _passed(code, f"view along {axis} unchanged")
    return Check(code=code, status=CheckStatus.FAIL,
                 message=f"view along {axis} changed at " + ", ".join(diffs),
                 cells=ray_cells)


def validate_edit(c: Compiled, edit: Edit) -> AnswerValidation:
    """All legality checks for a syntactically valid edit."""
    checks: list[Check] = []
    n_ed = len(c.editable)
    bad = sorted({k for k in [*edit.remove, *edit.add] if not 0 <= k < n_ed})
    if bad:
        checks.append(Check(code=CheckCode.ID_TYPES, status=CheckStatus.FAIL,
                            message=f"IDs out of range 0..{n_ed - 1}: {bad}", ids=bad))
        for code, _ in _ORDER[1:]:
            checks.append(_skipped(code, "IDs out of range; no final object can be built"))
        return AnswerValidation(valid=False, category=InvalidCategory.INVALID_IDS_OR_TYPES,
                                checks=checks)
    checks.append(_passed(CheckCode.ID_TYPES, "all IDs are integers in range"))

    dup = sorted({k for k in edit.remove if edit.remove.count(k) > 1}
                 | {k for k in edit.add if edit.add.count(k) > 1}
                 | (set(edit.remove) & set(edit.add)))
    if dup:
        checks.append(Check(code=CheckCode.NO_DUPLICATES, status=CheckStatus.FAIL,
                            message=f"IDs repeated or in both lists: {dup}", ids=dup,
                            cells=[grid.coords(c.editable[k]) for k in dup]))
    else:
        checks.append(_passed(CheckCode.NO_DUPLICATES, "no repeated IDs"))

    wrong_rm = sorted({k for k in edit.remove if not (c.occ >> c.editable[k]) & 1})
    wrong_add = sorted({k for k in edit.add if (c.occ >> c.editable[k]) & 1})
    if wrong_rm or wrong_add:
        parts = []
        if wrong_rm:
            parts.append(f"remove IDs not originally solid: {wrong_rm}")
        if wrong_add:
            parts.append(f"add IDs not originally empty: {wrong_add}")
        ids = sorted(set(wrong_rm) | set(wrong_add))
        checks.append(Check(code=CheckCode.SOURCE_OCCUPANCY, status=CheckStatus.FAIL,
                            message="; ".join(parts), ids=ids,
                            cells=[grid.coords(c.editable[k]) for k in ids]))
    else:
        checks.append(_passed(CheckCode.SOURCE_OCCUPANCY, "removed cells were solid, added were empty"))

    if len(edit.remove) != len(edit.add):
        checks.append(Check(code=CheckCode.EQUAL_COUNTS, status=CheckStatus.FAIL,
                            message=f"remove has {len(edit.remove)} IDs, add has {len(edit.add)}"))
    else:
        checks.append(_passed(CheckCode.EQUAL_COUNTS, f"{len(edit.remove)} removed, {len(edit.add)} added"))

    moves = max(len(edit.remove), len(edit.add))
    if moves > c.budget:
        checks.append(Check(code=CheckCode.BUDGET, status=CheckStatus.FAIL,
                            message=f"{moves} relocations exceed the budget of {c.budget}"))
    else:
        checks.append(_passed(CheckCode.BUDGET, f"{moves} of {c.budget} relocations used"))

    final = apply_ids(c, edit.remove, edit.add)

    changed = c.occ ^ final
    illegal = changed & ~c.editable_mask
    ent_filled = final & c.entrance_mask
    if illegal or ent_filled:
        cells = [grid.coords(i) for i in grid.bits(illegal | ent_filled)]
        checks.append(Check(code=CheckCode.IMMUTABLE_CELLS, status=CheckStatus.FAIL,
                            message="cells outside the editable list or entrances changed",
                            cells=cells))
    else:
        checks.append(_passed(CheckCode.IMMUTABLE_CELLS, "only editable cells changed; entrances empty"))

    checks.append(_silhouette_check("x", CheckCode.SILHOUETTE_X, c.occ, final))
    checks.append(_silhouette_check("y", CheckCode.SILHOUETTE_Y, c.occ, final))
    checks.append(_silhouette_check("z", CheckCode.SILHOUETTE_Z, c.occ, final))

    comps = grid.components(final)
    if len(comps) == 1:
        checks.append(_passed(CheckCode.SOLID_CONNECTED, "solid cubes form one face-connected piece"))
    else:
        largest = max(comps, key=lambda m: (grid.popcount(m), -(m & -m)))
        stray = [grid.coords(i) for comp in comps if comp != largest for i in grid.bits(comp)]
        msg = "no solid cubes remain" if not comps else f"solid cubes split into {len(comps)} pieces"
        checks.append(Check(code=CheckCode.SOLID_CONNECTED, status=CheckStatus.FAIL,
                            message=msg, cells=stray))

    category: InvalidCategory | None = None
    by_code = {ch.code: ch for ch in checks}
    for code, cat in _ORDER:
        if by_code[code].status == CheckStatus.FAIL:
            category = cat
            break
    return AnswerValidation(valid=category is None, category=category, checks=checks,
                            final_occupancy=grid.occupancy_to_string(final))


def _parse_check(parse: ParseOutcome) -> Check:
    if parse.ok:
        return _passed(CheckCode.PARSE, "one JSON object with integer ID arrays")
    return Check(code=CheckCode.PARSE, status=CheckStatus.FAIL,
                 message=f"{parse.detail}: {parse.message}")


def evaluate_parsed(
    inst: ShadowTwinsInstance, v_star: int, parse: ParseOutcome, compiled: Compiled | None = None
) -> ShadowTwinsEvaluation:
    if v_star <= 0:
        raise ValueError("instances with v_star = 0 are inadmissible and cannot be scored")
    c = compiled or compile_instance(inst)
    checks = [_parse_check(parse)]

    def result(**kw: Any) -> ShadowTwinsEvaluation:
        return ShadowTwinsEvaluation(instance_id=inst.instance_id, instance_hash=inst.content_hash,
                                     versions=versions(), parse=parse, v_star=v_star,
                                     checks=checks, **kw)

    if not parse.ok or parse.edit is None:
        checks += [_skipped(code, "answer did not parse") for code, _ in _ORDER]
        return result(edit=None, valid=False, category=parse.category, final_occupancy=None,
                      raw_objective=None, score=0.0)
    validation = validate_edit(c, parse.edit)
    checks += validation.checks
    if not validation.valid:
        return result(edit=parse.edit, valid=False, category=validation.category,
                      final_occupancy=validation.final_occupancy, raw_objective=None, score=0.0)
    assert validation.final_occupancy is not None
    final = grid.occupancy_from_string(validation.final_occupancy)
    v, opened, closed = objective(c, final)
    if v > v_star:
        raise RuntimeError(
            f"certificate inconsistency: answer reaches v={v} above certified v_star={v_star}")
    return result(edit=parse.edit, valid=True, category=None,
                  final_occupancy=validation.final_occupancy, raw_objective=v,
                  score=100.0 * v / v_star, opened=opened, closed=closed,
                  move_count=len(parse.edit.remove), is_optimal=v == v_star)


def evaluate_text(
    inst: ShadowTwinsInstance, v_star: int, raw_text: str | None,
    meta: CompletionMeta | None = None, compiled: Compiled | None = None,
) -> ShadowTwinsEvaluation:
    return evaluate_parsed(inst, v_star, parse_answer(raw_text, meta), compiled)


def evaluate_edit(
    inst: ShadowTwinsInstance, v_star: int, edit: Edit, compiled: Compiled | None = None
) -> ShadowTwinsEvaluation:
    """Score an already-structured edit (e.g. human practice or a certified witness)."""
    parse = ParseOutcome(parser_version=PARSER_VERSION, ok=True, edit=edit,
                         json_text=edit.model_dump_json())
    return evaluate_parsed(inst, v_star, parse, compiled)
