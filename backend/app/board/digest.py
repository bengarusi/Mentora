"""Compact text rendering of a board, for the tutor to reason about later.

After the student closes a board they will refer back to it — "why did you cross
that out?", "I didn't get step 2". The tutor needs to know what was on the board
to answer, but shipping the whole BoardSpec into every later prompt would be
expensive and mostly noise: coordinates, ranges and render hints say nothing a
conversation needs.

So the full spec stays rendering data, and this is the reasoning data. It is
derived deterministically — no second model call — and blocks are numbered so the
model and the student can agree on what "step 2" means.
"""

from __future__ import annotations

from app.schemas.board import (
    BoardSpec,
    CalloutBlock,
    CoordinatePlaneBlock,
    ExpressionCompareBlock,
    FractionBarsBlock,
    GeometryFigureBlock,
    NumberLineBlock,
    StepsBlock,
)


def _describe(block) -> str:
    if isinstance(block, StepsBlock):
        parts = []
        for item in block.items:
            marks = []
            if item.operation:
                marks.append(item.operation)
            if item.emphasis != "none":
                marks.append(f"{item.emphasis} mark")
            if item.note:
                marks.append(item.note)
            suffix = f" ({'; '.join(marks)})" if marks else ""
            parts.append(f"{item.math}{suffix}")
        return "steps: " + " | ".join(parts)

    if isinstance(block, CalloutBlock):
        return f"{block.tone} note: {block.text}"

    if isinstance(block, ExpressionCompareBlock):
        rewrite = (
            f", rewritten as {block.rewrite_left} {block.relation} {block.rewrite_right}"
            if block.rewrite_left and block.rewrite_right
            else ""
        )
        return f"comparison: {block.left} {block.relation} {block.right}{rewrite}"

    if isinstance(block, FractionBarsBlock):
        bars = ", ".join(f"{bar.numerator}/{bar.denominator}" for bar in block.bars)
        return f"fraction bars showing {bars}"

    if isinstance(block, NumberLineBlock):
        points = ", ".join(
            f"{point.label or point.value} at {point.value}" for point in block.points
        )
        return f"number line from {block.min} to {block.max}" + (f" marking {points}" if points else "")

    if isinstance(block, CoordinatePlaneBlock):
        lines = ", ".join(
            f"y = {line.slope}x + {line.intercept}" for line in block.lines
        )
        return f"graph showing {lines}" if lines else "graph"

    if isinstance(block, GeometryFigureBlock):
        dims = ", ".join(f"{name} {value}" for name, value in block.dimensions.items())
        return f"{block.shape} with {dims}"

    return block.caption


def digest_for(spec: BoardSpec, *, char_budget: int) -> str:
    """One board rendered as numbered lines the tutor can refer back to.

    Truncated to the budget rather than dropped, because a partial memory of the
    board is far more useful than none: the student is asking about it either way.
    """
    lines = [f'Board titled "{spec.title}":']
    for index, block in enumerate(spec.blocks, start=1):
        lines.append(f"  {index}. {_describe(block)}")
    if spec.final_answer:
        lines.append(f"  Final answer shown: {spec.final_answer}")

    text = "\n".join(lines)
    if len(text) > char_budget:
        text = text[: char_budget - 1].rstrip() + "…"
    return text
