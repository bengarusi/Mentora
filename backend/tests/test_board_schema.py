"""Structural contract for a visual board explanation.

These tests pin the shape the model must produce. They deliberately say nothing
about whether the mathematics is right — that lives in test_board_validation.py.
"""

import pytest
from pydantic import ValidationError

from app.schemas.board import (
    BoardSpec,
    CoordinatePlaneBlock,
    FractionBarsBlock,
    GeometryFigureBlock,
    NumberLineBlock,
    StepsBlock,
)


def _steps_block(**overrides) -> dict:
    block = {
        "kind": "steps",
        "id": "s1",
        "caption": "Solving step by step",
        "narration": "We will take this one step at a time.",
        "items": [{"math": "3x + 5 = 20"}, {"math": "3x = 15", "operation": "subtract 5"}],
    }
    block.update(overrides)
    return block


def _spec(*blocks, **overrides) -> dict:
    spec = {
        "title": "Balancing an equation",
        "intro": "Let's undo each operation one at a time.",
        "blocks": list(blocks) or [_steps_block()],
    }
    spec.update(overrides)
    return spec


def test_a_minimal_board_with_one_steps_block_is_valid():
    spec = BoardSpec.model_validate(_spec())

    assert len(spec.blocks) == 1
    assert isinstance(spec.blocks[0], StepsBlock)


def test_blocks_are_discriminated_by_kind():
    spec = BoardSpec.model_validate(
        _spec(
            _steps_block(),
            {
                "kind": "callout",
                "id": "c1",
                "caption": "A tip",
                "narration": "Here is something worth remembering.",
                "tone": "insight",
                "text": "Balance both sides.",
            },
        )
    )

    assert [block.kind for block in spec.blocks] == ["steps", "callout"]


def test_a_block_with_an_unknown_kind_is_rejected():
    """The union is closed. Dropping such a block is validate_board's job, but the
    schema itself must never accept a shape no renderer can draw."""
    with pytest.raises(ValidationError):
        BoardSpec.model_validate(_spec({"kind": "venn_diagram", "id": "v1", "caption": "Sets"}))


def test_a_block_carrying_extra_fields_is_rejected():
    """extra='forbid' — a model inventing a field is expressing intent we cannot
    render, so failing the block beats silently ignoring half of it."""
    with pytest.raises(ValidationError):
        BoardSpec.model_validate(_spec(_steps_block(colour="red")))


def test_a_board_needs_at_least_one_block():
    with pytest.raises(ValidationError):
        BoardSpec.model_validate(_spec(blocks=[]))


def test_every_block_must_carry_an_accessible_caption():
    """The caption is the SVG <title> and the screen-reader text. A block nobody
    can describe is a block nobody can hear."""
    block = _steps_block()
    del block["caption"]

    with pytest.raises(ValidationError):
        BoardSpec.model_validate(_spec(block))


def test_step_emphasis_is_limited_to_the_renderable_set():
    with pytest.raises(ValidationError):
        StepsBlock.model_validate(
            _steps_block(items=[{"math": "3x = 15", "emphasis": "sparkle"}])
        )


# ---- number_line -----------------------------------------------------------

def test_number_line_with_max_below_min_is_rejected():
    with pytest.raises(ValidationError, match="greater than min"):
        NumberLineBlock.model_validate(
            {"kind": "number_line", "id": "n1", "caption": "A line",
                "narration": "Look at this together.", "min": 5, "max": 1, "tick": 1}
        )


def test_number_line_too_dense_to_render_is_rejected():
    with pytest.raises(ValidationError, match="ticks"):
        NumberLineBlock.model_validate(
            {"kind": "number_line", "id": "n1", "caption": "A line",
                "narration": "Look at this together.", "min": 0, "max": 1000, "tick": 1}
        )


def test_number_line_point_outside_the_range_is_rejected():
    with pytest.raises(ValidationError, match="outside the visible range"):
        NumberLineBlock.model_validate(
            {
                "kind": "number_line",
                "id": "n1",
                "caption": "A line",
                "narration": "Look at this together.",
                "min": 0,
                "max": 10,
                "tick": 1,
                "points": [{"value": 42}],
            }
        )


# ---- coordinate_plane ------------------------------------------------------

def test_coordinate_plane_with_inverted_ranges_is_rejected():
    with pytest.raises(ValidationError, match="ordered"):
        CoordinatePlaneBlock.model_validate(
            {
                "kind": "coordinate_plane",
                "id": "p1",
                "caption": "A graph",
                "narration": "Look at this together.",
                "x_min": 5,
                "x_max": -5,
                "y_min": 0,
                "y_max": 10,
            }
        )


def test_coordinate_plane_point_outside_the_window_is_rejected():
    with pytest.raises(ValidationError, match="outside the visible window"):
        CoordinatePlaneBlock.model_validate(
            {
                "kind": "coordinate_plane",
                "id": "p1",
                "caption": "A graph",
                "narration": "Look at this together.",
                "x_min": 0,
                "x_max": 5,
                "y_min": 0,
                "y_max": 5,
                "points": [{"x": 99, "y": 1}],
            }
        )


def test_coordinate_plane_slope_triangle_needs_a_line_to_sit_on():
    with pytest.raises(ValidationError, match="needs a line"):
        CoordinatePlaneBlock.model_validate(
            {
                "kind": "coordinate_plane",
                "id": "p1",
                "caption": "A graph",
                "narration": "Look at this together.",
                "x_min": 0,
                "x_max": 5,
                "y_min": 0,
                "y_max": 5,
                "slope_triangle": 1,
            }
        )


# ---- fraction_bars ---------------------------------------------------------

def test_fraction_bar_denominator_cannot_be_zero():
    with pytest.raises(ValidationError):
        FractionBarsBlock.model_validate(
            {
                "kind": "fraction_bars",
                "id": "f1",
                "caption": "Two fractions",
                "narration": "Look at this together.",
                "bars": [{"numerator": 3, "denominator": 0}],
            }
        )


# ---- geometry_figure -------------------------------------------------------

def test_geometry_dimensions_must_belong_to_the_declared_shape():
    with pytest.raises(ValidationError, match="not a dimension of a circle"):
        GeometryFigureBlock.model_validate(
            {
                "kind": "geometry_figure",
                "id": "g1",
                "caption": "A circle",
                "narration": "Look at this together.",
                "shape": "circle",
                "dimensions": {"width": 4},
            }
        )


def test_geometry_dimensions_must_be_positive():
    with pytest.raises(ValidationError, match="must be positive"):
        GeometryFigureBlock.model_validate(
            {
                "kind": "geometry_figure",
                "id": "g1",
                "caption": "A triangle",
                "narration": "Look at this together.",
                "shape": "triangle",
                "dimensions": {"base": -6, "height": 4},
            }
        )


def test_geometry_labels_must_target_a_slot_the_shape_actually_has():
    with pytest.raises(ValidationError, match="not a label slot on a rectangle"):
        GeometryFigureBlock.model_validate(
            {
                "kind": "geometry_figure",
                "id": "g1",
                "caption": "A rectangle",
                "narration": "Look at this together.",
                "shape": "rectangle",
                "dimensions": {"width": 6, "height": 4},
                "labels": [{"target": "radius", "text": "3 cm"}],
            }
        )


def test_a_valid_triangle_passes():
    block = GeometryFigureBlock.model_validate(
        {
            "kind": "geometry_figure",
            "id": "g1",
            "caption": "A triangle with base 6 and height 4",
                "narration": "Look at this together.",
            "shape": "triangle",
            "dimensions": {"base": 6, "height": 4},
            "labels": [{"target": "base", "text": "6 cm"}],
            "right_angle_at": "height",
        }
    )

    assert block.dimensions == {"base": 6, "height": 4}
