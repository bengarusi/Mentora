"""Deterministic validation of a model-generated board spec.

Three different things get conflated when a generated diagram is called
"validated". Keeping them apart:

  * Rendering consistency — the drawing matches the parameters the model gave.
    Total, by construction: the schema takes slope/intercept and
    numerator/denominator, never pixels.
  * Internal consistency — the board does not contradict itself. Good: step
    chains, relation glyphs and fraction labels are cross-checked here.
  * Fidelity to the question — the board is correct *for this exercise*. Weak and
    block-dependent. Only two blocks get a real check, plus the final
    answer. geometry_figure and callout get no fidelity check at all.

Nothing is withheld here. A lesson board teaches an idea and a review board
explains a question the student has already been graded on, so in both cases the
answer is fair game, which means the final-answer check below always applies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.math.normalizer import parse_to_fraction
from app.math.sympy_service import SymPyMathService
from app.math.validator import AnswerValidationService
from app.schemas.board import (
    BoardBlock,
    BoardSpec,
    CoordinatePlaneBlock,
    ExpressionCompareBlock,
    FractionBarsBlock,
    StepsBlock,
)

_block_adapter: TypeAdapter[Any] = TypeAdapter(BoardBlock)
_sympy = SymPyMathService()
_answers = AnswerValidationService()


@dataclass(frozen=True)
class DroppedBlock:
    index: int
    kind: str
    reason: str


@dataclass(frozen=True)
class BoardValidation:
    """Outcome of validating one raw model response.

    `spec` is None exactly when `rejection` is set. `dropped` is advisory: blocks
    that could not be rendered were removed, but the board survived.
    """

    spec: BoardSpec | None = None
    dropped: tuple[DroppedBlock, ...] = ()
    rejection: str | None = None

    @property
    def ok(self) -> bool:
        return self.spec is not None


def validate_board(
    raw: Any,
    *,
    question_text: str,
    correct_answer: str | None,
    max_blocks: int,
) -> BoardValidation:
    """Validate a raw model response into a renderable, non-contradictory board.

    Structural problems drop the offending block; mathematical contradictions
    reject the whole board so the caller can retry with the reason attached.
    """
    if not isinstance(raw, dict):
        return BoardValidation(rejection="schema_invalid")

    raw_blocks = raw.get("blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        return BoardValidation(rejection="no_valid_blocks")

    blocks, dropped = _validate_blocks(raw_blocks, max_blocks)
    if not blocks:
        return BoardValidation(dropped=dropped, rejection="no_valid_blocks")
    # A board is a worked explanation first and a picture second. Without steps
    # there is nothing to reason along, and nothing the chain check can verify.
    if not any(isinstance(block, StepsBlock) for block in blocks):
        return BoardValidation(dropped=dropped, rejection="no_steps_block")

    try:
        # Re-validate with only the surviving blocks so the board-level fields
        # (title, intro, final_answer) are checked against a list we can render.
        spec = BoardSpec.model_validate(
            {**raw, "blocks": [block.model_dump() for block in blocks]}
        )
    except ValidationError:
        return BoardValidation(dropped=dropped, rejection="schema_invalid")

    rejection = _check_semantics(
        spec, question_text=question_text, correct_answer=correct_answer
    )
    if rejection:
        return BoardValidation(dropped=dropped, rejection=rejection)

    return BoardValidation(spec=spec, dropped=dropped)


def _validate_blocks(
    raw_blocks: list, max_blocks: int
) -> tuple[list[Any], tuple[DroppedBlock, ...]]:
    """Validate each block alone so one bad block cannot sink the board."""
    blocks: list[Any] = []
    dropped: list[DroppedBlock] = []
    for index, raw_block in enumerate(raw_blocks):
        kind = raw_block.get("kind", "?") if isinstance(raw_block, dict) else "?"
        if len(blocks) >= max_blocks:
            dropped.append(DroppedBlock(index, str(kind), "over_block_budget"))
            continue
        try:
            blocks.append(_block_adapter.validate_python(raw_block))
        except ValidationError:
            dropped.append(DroppedBlock(index, str(kind), "block_invalid"))
    return blocks, tuple(dropped)


# ---------------------------------------------------------------------------
# Semantic checks
# ---------------------------------------------------------------------------

def _check_semantics(
    spec: BoardSpec, *, question_text: str, correct_answer: str | None
) -> str | None:
    if spec.final_answer and correct_answer:
        # The strongest fidelity signal available.
        verdict = _answers.validate(spec.final_answer, correct_answer)
        if verdict.is_equivalent is False:
            return "answer_mismatch"

    for block in spec.blocks:
        if isinstance(block, StepsBlock):
            if _steps_are_inconsistent(block):
                return "step_chain_inconsistent"
        elif isinstance(block, ExpressionCompareBlock):
            reason = _compare_is_wrong(block)
            if reason:
                return reason
        elif isinstance(block, FractionBarsBlock):
            if _fraction_label_disagrees(block):
                return "fraction_label_mismatch"
        elif isinstance(block, CoordinatePlaneBlock):
            if _plane_contradicts_question(block, question_text):
                return "plane_slope_mismatch"
    return None


def _steps_are_inconsistent(block: StepsBlock) -> bool:
    """Every step of a valid equation chain has the same solution set.

    Catches `3x = 15 -> x = 7`. Steps that do not parse as one-variable equations
    are skipped, never failed, so prose-mixed or multi-variable chains abstain.
    """
    solutions: list[set[str]] = []
    for item in block.items:
        expr = _to_sympy(item.math)
        if expr is None or "=" not in expr:
            continue
        solved = _sympy.solve_equation(expr)
        if not solved:
            continue
        solutions.append({str(value) for value in solved})
    return len(solutions) > 1 and any(entry != solutions[0] for entry in solutions[1:])


def _compare_is_wrong(block: ExpressionCompareBlock) -> str | None:
    """Verify the asserted relation, and that each rewrite equals its own side."""
    for original, rewrite in ((block.left, block.rewrite_left), (block.right, block.rewrite_right)):
        if rewrite is None:
            continue
        a, b = _to_sympy(original), _to_sympy(rewrite)
        if a is None or b is None:
            continue
        if _sympy.are_equivalent(a, b) is False:
            return "expression_rewrite_mismatch"

    left, right = _numeric_value(block.left), _numeric_value(block.right)
    if left is None or right is None:
        return None  # symbolic comparison — abstain
    if block.relation == "<" and not left < right:
        return "expression_relation_false"
    if block.relation == ">" and not left > right:
        return "expression_relation_false"
    if block.relation == "=" and left != right:
        return "expression_relation_false"
    return None


def _fraction_label_disagrees(block: FractionBarsBlock) -> bool:
    """A bar labelled 3/4 but shaded 8/12 contradicts itself."""
    for bar in block.bars:
        if not bar.label:
            continue
        labelled = parse_to_fraction(_strip_latex(bar.label))
        if labelled is None:
            continue
        if labelled != Fraction(bar.numerator, bar.denominator):
            return True
    return False


_Y_EQUALS_MX_B = re.compile(
    r"y\s*=\s*(?P<slope>[+-]?\s*\d*\.?\d*)\s*\*?\s*x\s*(?P<intercept>[+-]\s*\d+\.?\d*)?(?![\w.])",
    re.IGNORECASE,
)


def _plane_contradicts_question(block: CoordinatePlaneBlock, question_text: str) -> bool:
    """Narrow fidelity check: when the question states y = mx + b outright, the
    plotted line must match it. Abstains whenever the question says no such thing,
    which is most of the time."""
    if not block.lines:
        return False
    match = _Y_EQUALS_MX_B.search(_strip_latex(question_text))
    if match is None:
        return False

    raw_slope = match.group("slope").replace(" ", "")
    if raw_slope in ("", "+"):
        slope = 1.0
    elif raw_slope == "-":
        slope = -1.0
    else:
        try:
            slope = float(raw_slope)
        except ValueError:
            return False
    raw_intercept = (match.group("intercept") or "0").replace(" ", "")
    try:
        intercept = float(raw_intercept)
    except ValueError:
        return False

    line = block.lines[0]
    return not (
        abs(line.slope - slope) < 1e-9 and abs(line.intercept - intercept) < 1e-9
    )


# ---------------------------------------------------------------------------
# LaTeX / SymPy bridging
# ---------------------------------------------------------------------------

_LATEX_REPLACEMENTS = (
    (re.compile(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}"), r"((\1)/(\2))"),
    (re.compile(r"\\d?frac"), ""),
    (re.compile(r"\\(?:times|cdot)"), "*"),
    (re.compile(r"\\div"), "/"),
    (re.compile(r"\\text\s*\{[^{}]*\}"), ""),
    (re.compile(r"\\(?:left|right|,|;|!|:|quad|qquad)"), ""),
    (re.compile(r"\\\\"), " "),
)


def _strip_latex(text: str) -> str:
    out = text
    for pattern, replacement in _LATEX_REPLACEMENTS:
        out = pattern.sub(replacement, out)
    return out.replace("{", "(").replace("}", ")").strip()


def _to_sympy(text: str) -> str | None:
    """Convert LaTeX-ish math into something sympify can read, or None.

    Returning None on anything unrecognised is the safety valve that keeps this
    module from producing false rejections: if a single backslash survives, we
    did not understand the expression and must not judge it.
    """
    if not text:
        return None
    out = _strip_latex(text)
    if "\\" in out:
        return None
    out = out.replace("^", "**")
    # Implicit multiplication: sympify reads "3*x", never "3x".
    out = re.sub(r"(\d)\s*([a-zA-Z(])", r"\1*\2", out)
    out = re.sub(r"(\))\s*([a-zA-Z0-9(])", r"\1*\2", out)
    out = re.sub(r"\s+", " ", out).strip()
    if not out or out.count("=") > 1:
        return None
    return out


def _numeric_value(text: str) -> Fraction | None:
    """Exact rational value of an expression, or None if it isn't numeric."""
    direct = parse_to_fraction(_strip_latex(text))
    if direct is not None:
        return direct
    expr = _to_sympy(text)
    if expr is None or "=" in expr:
        return None
    return _sympy.evaluate_expression(expr)
