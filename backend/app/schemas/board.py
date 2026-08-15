"""Visual board explanations — the model-facing contract and the API DTOs.

A board is a small, closed set of typed blocks rather than free-form drawing
instructions. The governing principle is that the model supplies *parameters*
(slope, numerator, dimensions) and the renderer computes pixels, so a drawing can
never disagree with the numbers it was built from.

That buys rendering consistency, not mathematical truth: nothing here can tell
whether `slope=2` is the right slope for the question. Fidelity checks live in
app/board/validation.py, which is explicit about how far they reach.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Keeps a number line readable: enough ticks to be useful, few enough to render.
MAX_NUMBER_LINE_TICKS = 40

# Dimension keys each geometry shape is allowed to declare, and the label slots
# a label may attach to. Anything else is a block the renderer cannot place.
GEOMETRY_DIMENSIONS: dict[str, frozenset[str]] = {
    "triangle": frozenset({"base", "height", "side_a", "side_b", "side_c"}),
    "rectangle": frozenset({"width", "height"}),
    "circle": frozenset({"radius", "diameter"}),
}
GEOMETRY_LABEL_TARGETS: dict[str, frozenset[str]] = {
    "triangle": frozenset(
        {"base", "height", "side_a", "side_b", "side_c", "angle_a", "angle_b", "angle_c", "area"}
    ),
    "rectangle": frozenset({"width", "height", "area", "perimeter"}),
    "circle": frozenset({"radius", "diameter", "center", "area", "circumference"}),
}


class _BoardModel(BaseModel):
    """Every board model forbids unknown fields.

    Same posture as the agent tool args (app/agent/registry.py): a model that
    invents a field is producing something we cannot render, so it is better to
    fail the block and drop it than to silently ignore half its intent.
    """

    model_config = ConfigDict(extra="forbid")


class _BoardBlock(_BoardModel):
    # Stable handle so a later conversational turn can refer to one block by name
    # ("the part on the left") without shipping the whole spec to the model.
    id: str = Field(min_length=1, max_length=32)
    # Doubles as the SVG <title> and the screen-reader description. Required —
    # a block nobody can describe is a block nobody can hear.
    caption: str = Field(min_length=1, max_length=200)
    # What the tutor says out loud while this block is being written. Drives both
    # the spoken narration and the caption bar, so it is written to be heard
    # rather than read: second person, one or two short sentences.
    narration: str = Field(min_length=1, max_length=280)


# ---- steps -----------------------------------------------------------------

class StepItem(_BoardModel):
    math: str = Field(min_length=1, max_length=200)  # LaTeX, no $ delimiters
    operation: str | None = Field(default=None, max_length=120)  # "subtract 5 from both sides"
    note: str | None = Field(default=None, max_length=200)
    # The marks a teacher actually makes at a board. Drawn as hand-styled SVG
    # strokes over the maths rather than as CSS text decoration, so they animate
    # as if being drawn.
    emphasis: Literal["none", "highlight", "underline", "circle", "strike"] = "none"
    # Colour of that mark: neutral emphasis, a correct pairing, or a wrong one.
    emphasis_tone: Literal["neutral", "good", "bad"] = "neutral"


class StepsBlock(_BoardBlock):
    kind: Literal["steps"]
    items: list[StepItem] = Field(min_length=1, max_length=8)


# ---- callout ---------------------------------------------------------------

class CalloutBlock(_BoardBlock):
    kind: Literal["callout"]
    tone: Literal["insight", "warning", "common_mistake"]
    text: str = Field(min_length=1, max_length=300)


# ---- expression_compare ----------------------------------------------------

class ExpressionCompareBlock(_BoardBlock):
    kind: Literal["expression_compare"]
    left: str = Field(min_length=1, max_length=120)
    right: str = Field(min_length=1, max_length=120)
    relation: Literal["<", ">", "=", "≈"]
    left_label: str | None = Field(default=None, max_length=40)
    right_label: str | None = Field(default=None, max_length=40)
    # Optional second row showing both sides rewritten comparably, e.g. over a
    # common denominator. Validated against its own side, not against the question.
    rewrite_left: str | None = Field(default=None, max_length=120)
    rewrite_right: str | None = Field(default=None, max_length=120)


# ---- fraction_bars ---------------------------------------------------------

class FractionBar(_BoardModel):
    numerator: int = Field(ge=0, le=24)
    denominator: int = Field(ge=1, le=24)
    label: str | None = Field(default=None, max_length=40)


class FractionBarsBlock(_BoardBlock):
    kind: Literal["fraction_bars"]
    bars: list[FractionBar] = Field(min_length=1, max_length=3)


# ---- number_line -----------------------------------------------------------

class NumberLinePoint(_BoardModel):
    value: float
    label: str | None = Field(default=None, max_length=40)
    style: Literal["dot", "open", "filled"] = "dot"


class NumberLineInterval(_BoardModel):
    start: float | None = None
    end: float | None = None
    inclusive_start: bool = False
    inclusive_end: bool = False


class NumberLineBlock(_BoardBlock):
    kind: Literal["number_line"]
    min: float
    max: float
    tick: float = Field(gt=0)
    points: list[NumberLinePoint] = Field(default_factory=list, max_length=6)
    interval: NumberLineInterval | None = None

    @model_validator(mode="after")
    def _check_range(self) -> "NumberLineBlock":
        if self.max <= self.min:
            raise ValueError("number_line max must be greater than min")
        if (self.max - self.min) / self.tick > MAX_NUMBER_LINE_TICKS:
            raise ValueError(
                f"number_line would need more than {MAX_NUMBER_LINE_TICKS} ticks to render"
            )
        for point in self.points:
            if not self.min <= point.value <= self.max:
                raise ValueError("number_line point falls outside the visible range")
        if self.interval is not None:
            for bound in (self.interval.start, self.interval.end):
                if bound is not None and not self.min <= bound <= self.max:
                    raise ValueError("number_line interval falls outside the visible range")
        return self


# ---- coordinate_plane ------------------------------------------------------

class PlaneLine(_BoardModel):
    # Slope-intercept, never a point list: the renderer derives the geometry, so
    # the drawn line always agrees with the equation the block states.
    slope: float
    intercept: float
    label: str | None = Field(default=None, max_length=40)


class PlanePoint(_BoardModel):
    x: float
    y: float
    label: str | None = Field(default=None, max_length=40)


class CoordinatePlaneBlock(_BoardBlock):
    kind: Literal["coordinate_plane"]
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    lines: list[PlaneLine] = Field(default_factory=list, max_length=3)
    points: list[PlanePoint] = Field(default_factory=list, max_length=6)
    # x at which to draw the rise/run triangle on the first line.
    slope_triangle: float | None = None

    @model_validator(mode="after")
    def _check_window(self) -> "CoordinatePlaneBlock":
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("coordinate_plane ranges must be ordered")
        for point in self.points:
            if not (self.x_min <= point.x <= self.x_max and self.y_min <= point.y <= self.y_max):
                raise ValueError("coordinate_plane point falls outside the visible window")
        if self.slope_triangle is not None:
            if not self.x_min <= self.slope_triangle <= self.x_max:
                raise ValueError("coordinate_plane slope_triangle falls outside the visible window")
            if not self.lines:
                raise ValueError("coordinate_plane slope_triangle needs a line to sit on")
        return self


# ---- geometry_figure -------------------------------------------------------

class GeometryLabel(_BoardModel):
    target: str = Field(min_length=1, max_length=24)
    text: str = Field(min_length=1, max_length=40)


class GeometryFigureBlock(_BoardBlock):
    kind: Literal["geometry_figure"]
    shape: Literal["triangle", "rectangle", "circle"]
    dimensions: dict[str, float]
    labels: list[GeometryLabel] = Field(default_factory=list, max_length=8)
    right_angle_at: str | None = Field(default=None, max_length=24)

    @model_validator(mode="after")
    def _check_shape(self) -> "GeometryFigureBlock":
        allowed_dimensions = GEOMETRY_DIMENSIONS[self.shape]
        allowed_targets = GEOMETRY_LABEL_TARGETS[self.shape]
        if not self.dimensions:
            raise ValueError(f"geometry_figure {self.shape} needs at least one dimension")
        for name, value in self.dimensions.items():
            if name not in allowed_dimensions:
                raise ValueError(f"'{name}' is not a dimension of a {self.shape}")
            if value <= 0:
                raise ValueError(f"geometry_figure dimension '{name}' must be positive")
        for label in self.labels:
            if label.target not in allowed_targets:
                raise ValueError(f"'{label.target}' is not a label slot on a {self.shape}")
        if self.right_angle_at is not None and self.right_angle_at not in allowed_targets:
            raise ValueError(f"'{self.right_angle_at}' is not a slot on a {self.shape}")
        return self


BoardBlock = Annotated[
    StepsBlock
    | CalloutBlock
    | ExpressionCompareBlock
    | FractionBarsBlock
    | NumberLineBlock
    | CoordinatePlaneBlock
    | GeometryFigureBlock,
    Field(discriminator="kind"),
]


class BoardSpec(_BoardModel):
    """One board explanation, scoped to one question.

    `blocks` has no upper bound here — the cap is settings.BOARD_MAX_BLOCKS,
    applied where blocks are assembled, so it stays operationally tunable.
    """

    title: str = Field(min_length=1, max_length=80)
    intro: str = Field(min_length=1, max_length=300)
    blocks: list[BoardBlock] = Field(min_length=1)
    # Withheld in method mode; enforced by app/board/validation.py, which also
    # scans the prose fields for the answer stated another way.
    final_answer: str | None = Field(default=None, max_length=120)


# ---- API request / response DTOs -------------------------------------------

# Where a board came from. lesson_intro opens the lesson on the board; chat is an
# explicit mid-lesson request; practice_review is remediation on a question the
# student has already been graded on. There is deliberately no board while a
# student is still answering — that is theirs to work through.
BoardKind = Literal["lesson_intro", "chat", "practice_review"]


class BoardLessonRequest(BaseModel):
    # Absent for the lesson opening. Present when the student asks mid-lesson for
    # something specific, so the board addresses what they're stuck on rather
    # than re-teaching the topic.
    focus: str | None = Field(default=None, max_length=500)


class BoardSummary(BaseModel):
    """Board metadata for the list endpoint — deliberately without the spec, so
    one request can drive every affordance on the page cheaply."""

    id: int
    kind: BoardKind
    # Exactly one of these is set, depending on kind.
    message_id: int | None = None
    question_id: int | None = None
    title: str
    created_at: datetime | None = None


class BoardListResponse(BaseModel):
    # How the frontend learns the feature flag's state: there is no frontend flag
    # system, so the capability is communicated as data.
    enabled: bool
    boards: list[BoardSummary]


class BoardResponse(BaseModel):
    id: int
    kind: BoardKind
    message_id: int | None = None
    question_id: int | None = None
    spec: BoardSpec
    created_at: datetime | None = None
