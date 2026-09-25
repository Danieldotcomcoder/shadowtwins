"""Compact text protocol (``st-protocol-1.0.0``): the exact authored text a model receives.

One independent user message per instance. It contains the rules, the grid as four labelled
binary layers, the entrances, the editable cells with their IDs, the budget and the answer format.
It never contains the optimum, previous answers, feedback, images or solver hints.
"""

from __future__ import annotations

from benchcore.contracts import ChatMessage, RenderedPrompt
from benchcore.hashing import content_hash

from . import grid
from .contracts import ShadowTwinsInstance
from .versions import BENCHMARK_ID, PROTOCOL_VERSION

LABELS = "ABCDEFGH"


def _cell(c: tuple[int, int, int] | list[int]) -> str:
    return f"({c[0]},{c[1]},{c[2]})"


def render_user_text(inst: ShadowTwinsInstance) -> str:
    occ = inst.occupancy_mask
    layers = grid.occupancy_layers(occ)
    b = inst.core.budget
    layer_lines = []
    for z in range(grid.N):
        name = " (bottom)" if z == 0 else " (top)" if z == grid.N - 1 else ""
        rows = " ".join("".join(str(v) for v in layers[z][y]) for y in range(grid.N))
        layer_lines.append(f"z={z}{name}: {rows}")
    entrances = " ".join(f"{LABELS[k]}{_cell(c)}" for k, c in enumerate(inst.core.entrances))
    solid = [f"{k}:{_cell(c)}" for k, c in enumerate(inst.core.editable)
             if (occ >> grid.index(*c)) & 1]
    empty = [f"{k}:{_cell(c)}" for k, c in enumerate(inst.core.editable)
             if not (occ >> grid.index(*c)) & 1]
    moves = "1 move" if b == 1 else f"{b} moves"
    return "\n".join([
        "Shadow Twins puzzle.",
        "A 4x4x4 grid of cells (x,y,z), each coordinate 0-3. 1 = solid cube, 0 = empty.",
        "Each line below is one layer z (z=0 bottom, z=3 top) and shows its rows y=0,1,2,3 "
        "from left to right; each row lists x=0,1,2,3 from left to right.",
        *layer_lines,
        f"Entrances (fixed empty boundary cells): {entrances}",
        "Editable cells as id:(x,y,z).",
        "Solid now: " + " ".join(solid),
        "Empty now: " + " ".join(empty),
        "",
        "A move takes the cube out of one solid editable cell and puts it into one empty editable "
        f"cell. Make at most {moves} (zero is allowed); all moves happen at once. The result must "
        "keep:",
        "1. Every non-editable cell unchanged.",
        "2. The three shadows: every straight line of 4 cells parallel to the x, y or z axis "
        "contains a solid cube after the moves exactly when it did before.",
        "3. All solid cubes as one piece joined through shared faces.",
        "Two entrances are linked when a path of empty cells joins them, stepping only between "
        "cells that share a face and never leaving the grid.",
        "Goal: change the linked/unlinked status of as many entrance pairs as possible "
        "(opening and closing both count).",
        "",
        'Reply with only JSON: {"remove":[ids of solid cells to empty],"add":[ids of empty '
        'cells to fill]}. Both lists must have the same length. No moves: {"remove":[],"add":[]}',
    ])


def render_prompt(inst: ShadowTwinsInstance) -> RenderedPrompt:
    messages = [ChatMessage(role="user", content=render_user_text(inst))]
    return RenderedPrompt(
        benchmark_id=BENCHMARK_ID,
        instance_id=inst.instance_id,
        protocol_version=PROTOCOL_VERSION,
        messages=messages,
        text_hash=content_hash([m.model_dump() for m in messages]),
    )
