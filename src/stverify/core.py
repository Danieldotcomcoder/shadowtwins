"""Independent Shadow Twins verifier.

Deliberately simple and separate from the optimized engine: it imports nothing from
``shadowtwins`` or ``benchcore``. Geometry is a set of solid (x, y, z) tuples; projections are
explicit loops over rays; connectivity is breadth-first search over an explicit neighbour list;
relocation subsets are enumerated by counting through bitmasks rather than itertools. It reads
plain JSON dictionaries so it can check stored packs without trusting the code that wrote them.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any

VERIFIER_VERSION = "stverify-1.0.0"
SIZE = 4

Cell = tuple[int, int, int]


# --- loading ---------------------------------------------------------------------------------

def _hash_core(core: dict[str, Any]) -> str:
    text = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def cell_of_position(position: int) -> Cell:
    # character position p in the occupancy string: p = x + 4*y + 16*z
    z, rest = divmod(position, SIZE * SIZE)
    y, x = divmod(rest, SIZE)
    return (x, y, z)


class Puzzle:
    def __init__(self, data: dict[str, Any]) -> None:
        core = data["core"]
        self.instance_id: str = data["instance_id"]
        self.stored_hash: str = data["content_hash"]
        self.computed_hash: str = _hash_core(core)
        occupancy: str = core["occupancy"]
        if len(occupancy) != SIZE ** 3:
            raise ValueError("occupancy must have 64 characters")
        self.solid: frozenset[Cell] = frozenset(
            cell_of_position(p) for p, ch in enumerate(occupancy) if ch == "1"
        )
        self.entrances: list[Cell] = [tuple(c) for c in core["entrances"]]  # type: ignore[misc]
        self.editable: list[Cell] = [tuple(c) for c in core["editable"]]  # type: ignore[misc]
        self.budget: int = core["budget"]


def in_grid(c: Cell) -> bool:
    return all(0 <= v < SIZE for v in c)


def face_neighbours(c: Cell) -> list[Cell]:
    x, y, z = c
    candidates = [(x - 1, y, z), (x + 1, y, z), (x, y - 1, z), (x, y + 1, z), (x, y, z - 1), (x, y, z + 1)]
    return [n for n in candidates if in_grid(n)]


ALL_CELLS: list[Cell] = [(x, y, z) for z in range(SIZE) for y in range(SIZE) for x in range(SIZE)]


def on_boundary(c: Cell) -> bool:
    return any(v == 0 or v == SIZE - 1 for v in c)


# --- the rules, written plainly ---------------------------------------------------------------

def shadows(solid: frozenset[Cell] | set[Cell]) -> tuple[frozenset, frozenset, frozenset]:
    along_x = set()
    along_y = set()
    along_z = set()
    for y in range(SIZE):
        for z in range(SIZE):
            for x in range(SIZE):
                if (x, y, z) in solid:
                    along_x.add((y, z))
                    break
    for x in range(SIZE):
        for z in range(SIZE):
            for y in range(SIZE):
                if (x, y, z) in solid:
                    along_y.add((x, z))
                    break
    for x in range(SIZE):
        for y in range(SIZE):
            for z in range(SIZE):
                if (x, y, z) in solid:
                    along_z.add((x, y))
                    break
    return frozenset(along_x), frozenset(along_y), frozenset(along_z)


def reachable(start: Cell, passable: set[Cell] | frozenset[Cell]) -> set[Cell]:
    seen = {start}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for n in face_neighbours(cur):
            if n in passable and n not in seen:
                seen.add(n)
                queue.append(n)
    return seen


def solid_is_one_piece(solid: frozenset[Cell] | set[Cell]) -> bool:
    if not solid:
        return False
    first = next(iter(solid))
    return len(reachable(first, solid)) == len(solid)


def linked_pairs(solid: frozenset[Cell] | set[Cell], entrances: list[Cell]) -> set[tuple[int, int]]:
    empty = {c for c in ALL_CELLS if c not in solid}
    linked: set[tuple[int, int]] = set()
    for i, a in enumerate(entrances):
        if a not in empty:
            continue
        region = reachable(a, empty)
        for j in range(i + 1, len(entrances)):
            if entrances[j] in region:
                linked.add((i, j))
    return linked


def changed_pairs(original: set[tuple[int, int]], final: set[tuple[int, int]]) -> tuple[int, int]:
    opened = len(final - original)
    closed = len(original - final)
    return opened, closed


def structural_problems(p: Puzzle) -> list[str]:
    problems = []
    if p.stored_hash != p.computed_hash:
        problems.append("content hash does not match instance core")
    if len(set(p.entrances)) != len(p.entrances):
        problems.append("duplicate entrances")
    if len(set(p.editable)) != len(p.editable):
        problems.append("duplicate editable cells")
    for e in p.entrances:
        if e in p.solid:
            problems.append(f"entrance {e} is solid")
        if not on_boundary(e):
            problems.append(f"entrance {e} is not on the boundary")
        if e in p.editable:
            problems.append(f"entrance {e} is editable")
    if not solid_is_one_piece(p.solid):
        problems.append("original solid is not one face-connected piece")
    return problems


def evaluate_answer(p: Puzzle, remove: list[int], add: list[int]) -> dict[str, Any]:
    """Independent legality and objective for an already-parsed answer."""
    reasons: list[str] = []
    n = len(p.editable)
    if any(not isinstance(k, int) or isinstance(k, bool) or k < 0 or k >= n for k in remove + add):
        return {"valid": False, "reasons": ["invalid_ids_or_types"], "objective": None}
    if len(set(remove)) != len(remove) or len(set(add)) != len(add) or set(remove) & set(add):
        reasons.append("duplicate_ids")
    if any(p.editable[k] not in p.solid for k in remove) or any(p.editable[k] in p.solid for k in add):
        reasons.append("wrong_source_occupancy")
    if len(remove) != len(add):
        reasons.append("unequal_edit_counts")
    if len(remove) > p.budget or len(add) > p.budget:
        reasons.append("budget_exceeded")
    final = set(p.solid)
    for k in remove:
        final.discard(p.editable[k])
    for k in add:
        final.add(p.editable[k])
    touched = final.symmetric_difference(p.solid)
    if any(c not in p.editable for c in touched) or any(e in final for e in p.entrances):
        reasons.append("immutable_cell_modified")
    if shadows(final) != shadows(p.solid):
        reasons.append("silhouette_changed")
    if not solid_is_one_piece(final):
        reasons.append("solid_disconnected")
    if reasons:
        return {"valid": False, "reasons": reasons, "objective": None}
    opened, closed = changed_pairs(linked_pairs(p.solid, p.entrances), linked_pairs(final, p.entrances))
    return {"valid": True, "reasons": [], "objective": opened + closed, "opened": opened, "closed": closed}


def _subsets(items: list[int], size: int) -> list[tuple[int, ...]]:
    """All ``size``-subsets of ``items`` (ascending), by counting through bitmasks."""
    out = []
    for mask in range(1 << len(items)):
        if bin(mask).count("1") == size:
            out.append(tuple(items[b] for b in range(len(items)) if mask >> b & 1))
    return sorted(out)


def _choose(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    num = den = 1
    for t in range(k):
        num *= n - t
        den *= t + 1
    return num // den


def recompute_certificate(p: Puzzle) -> dict[str, Any]:
    solid_ids = [k for k, c in enumerate(p.editable) if c in p.solid]
    empty_ids = [k for k, c in enumerate(p.editable) if c not in p.solid]
    s, e = len(solid_ids), len(empty_ids)
    max_r = min(p.budget, s, e)
    original_shadows = shadows(p.solid)
    original_links = linked_pairs(p.solid, p.entrances)

    enumerated = legal = 0
    hist: dict[int, int] = {}
    by_moves: dict[int, dict[int, int]] = {}
    legal_list: list[tuple[int, tuple[int, ...], tuple[int, ...], int]] = []
    rej_sil = rej_solid = tot_sil = tot_solid = tot_both = 0
    ns_legal = 0
    ns_hist: dict[int, int] = {}
    ns_list: list[tuple[int, tuple[int, ...], tuple[int, ...], int]] = []

    for r in range(max_r + 1):
        add_sets = _subsets(empty_ids, r)
        for rm in _subsets(solid_ids, r):
            for ad in add_sets:
                enumerated += 1
                final = set(p.solid)
                for k in rm:
                    final.discard(p.editable[k])
                for k in ad:
                    final.add(p.editable[k])
                sil_ok = shadows(final) == original_shadows
                one_piece = solid_is_one_piece(final)
                if not sil_ok:
                    tot_sil += 1
                    rej_sil += 1
                if not one_piece:
                    tot_solid += 1
                    if sil_ok:
                        rej_solid += 1
                    else:
                        tot_both += 1
                    continue
                opened, closed = changed_pairs(original_links, linked_pairs(final, p.entrances))
                v = opened + closed
                ns_legal += 1
                ns_hist[v] = ns_hist.get(v, 0) + 1
                ns_list.append((r, rm, ad, v))
                if not sil_ok:
                    continue
                legal += 1
                hist[v] = hist.get(v, 0) + 1
                by_moves.setdefault(r, {})
                by_moves[r][v] = by_moves[r].get(v, 0) + 1
                legal_list.append((r, rm, ad, v))

    v_star = max(v for *_, v in legal_list)
    v_min = min(v for *_, v in legal_list)
    best = min((r, rm, ad) for r, rm, ad, v in legal_list if v == v_star)
    worst = min((r, rm, ad) for r, rm, ad, v in legal_list if v == v_min)
    ns_v_star = max(v for *_, v in ns_list)
    ns_best = min((r, rm, ad) for r, rm, ad, v in ns_list if v == ns_v_star)
    min_moves = min(r for r, _, _, v in legal_list if v == v_star)

    def w(t: tuple[int, tuple[int, ...], tuple[int, ...]], v: int) -> dict[str, Any]:
        return {"remove": list(t[1]), "add": list(t[2]), "objective": v}

    return {
        "instance_hash": p.computed_hash,
        "budget": p.budget,
        "solid_editable": s,
        "empty_editable": e,
        "expected_enumerated_count": sum(_choose(s, r) * _choose(e, r) for r in range(max_r + 1)),
        "enumerated_count": enumerated,
        "legal_count": legal,
        "v_star": v_star,
        "v_min": v_min,
        "optimal_count": hist[v_star],
        "min_moves_for_optimum": min_moves if v_star > 0 else 0,
        "histogram": {str(k): hist[k] for k in sorted(hist)},
        "histogram_by_moves": {str(r): {str(k): h[k] for k in sorted(h)} for r, h in sorted(by_moves.items())},
        "best_witness": w(best, v_star),
        "worst_witness": w(worst, v_min),
        "rejections": {"silhouette": rej_sil, "solid_disconnected": rej_solid},
        "constraint_totals": {"silhouette_fail": tot_sil, "solid_disconnected": tot_solid, "both": tot_both},
        "no_shadow": {
            "legal_count": ns_legal,
            "v_star": ns_v_star,
            "histogram": {str(k): ns_hist[k] for k in sorted(ns_hist)},
            "best_witness": w(ns_best, ns_v_star),
        },
        "admissible": v_star > 0,
    }


def compare_certificate(instance: dict[str, Any], certificate: dict[str, Any]) -> dict[str, Any]:
    """Recompute everything and list every disagreement with the stored certificate."""
    p = Puzzle(instance)
    mismatches = [f"instance: {msg}" for msg in structural_problems(p)]
    core = certificate["core"]
    stored_core_hash = certificate.get("core_hash")
    if stored_core_hash != _hash_core(core):
        mismatches.append("certificate core_hash does not match certificate core")
    if core.get("instance_id") != p.instance_id:
        mismatches.append("certificate instance_id differs from instance")
    if core.get("exhaustive") is not True:
        mismatches.append("certificate is not marked exhaustive")
    try:
        recomputed = recompute_certificate(p)
    except ValueError as exc:  # e.g. no legal candidate at all because the original is invalid
        mismatches.append(f"recomputation failed: {exc}")
        return {"verifier_version": VERIFIER_VERSION, "mismatches": mismatches, "recomputed": {}}
    for key, value in recomputed.items():
        if core.get(key) != value:
            mismatches.append(f"{key}: stored {core.get(key)!r} != recomputed {value!r}")
    # The stored witnesses must themselves evaluate to the stated objective.
    for label in ("best_witness", "worst_witness"):
        wt = core.get(label, {})
        result = evaluate_answer(p, wt.get("remove", []), wt.get("add", []))
        if not result["valid"] or result["objective"] != wt.get("objective"):
            mismatches.append(f"{label} does not evaluate to its stated objective")
    return {"verifier_version": VERIFIER_VERSION, "mismatches": mismatches, "recomputed": recomputed}
