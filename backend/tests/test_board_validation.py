"""Deterministic checks on a generated board.

The recurring theme: every check must abstain on ambiguity. A false rejection
makes the feature look broken to a student, so the tests that assert a board is
*accepted* matter as much as the ones that assert it is rejected.
"""

from app.board.validation import validate_board

MAX_BLOCKS = 6


def _steps(*items, block_id="s1", caption="Working through it") -> dict:
    return {
        "kind": "steps",
        "id": block_id,
        "caption": caption,
        "narration": "We will take this one step at a time.",
        "items": list(items),
    }


def _raw(*blocks, **overrides) -> dict:
    raw = {
        "title": "Balancing an equation",
        "intro": "Let's undo each operation.",
        "blocks": list(blocks) or [_steps({"math": "3x + 5 = 20"})],
    }
    raw.update(overrides)
    return raw


def _validate(raw, *, question_text="Solve 3x + 5 = 20", correct_answer="5"):
    return validate_board(
        raw,
        question_text=question_text,
        correct_answer=correct_answer,
        max_blocks=MAX_BLOCKS,
    )


# ---- board-level structure -------------------------------------------------

def test_a_non_dict_response_is_rejected_rather_than_raising():
    assert _validate("not a board").rejection == "schema_invalid"


def test_an_unknown_block_kind_is_dropped_without_failing_the_board():
    """Graceful degradation: an unsupported visualisation disappears, the
    explanation survives."""
    result = _validate(
        _raw(_steps({"math": "3x = 15"}), {"kind": "venn_diagram", "id": "v1", "caption": "Sets"})
    )

    assert result.ok
    assert [block.kind for block in result.spec.blocks] == ["steps"]
    assert [(d.kind, d.reason) for d in result.dropped] == [("venn_diagram", "block_invalid")]


def test_a_board_whose_blocks_all_fail_is_rejected():
    result = _validate(_raw({"kind": "venn_diagram", "id": "v1", "caption": "Sets"}))

    assert result.rejection == "no_valid_blocks"
    assert result.spec is None


def test_a_board_without_a_steps_block_is_rejected():
    """A board is a worked explanation first and a picture second."""
    result = _validate(
        _raw({"kind": "callout", "id": "c1", "caption": "Tip",
        "narration": "Look at this together.", "tone": "insight", "text": "Balance."})
    )

    assert result.rejection == "no_steps_block"


def test_blocks_beyond_the_budget_are_dropped_not_rejected():
    blocks = [_steps({"math": "3x = 15"}, block_id=f"s{i}") for i in range(MAX_BLOCKS + 2)]

    result = _validate(_raw(*blocks))

    assert result.ok
    assert len(result.spec.blocks) == MAX_BLOCKS
    assert all(d.reason == "over_block_budget" for d in result.dropped)


# ---- step chain ------------------------------------------------------------

def test_a_valid_equation_chain_passes():
    result = _validate(
        _raw(_steps({"math": "3x + 5 = 20"}, {"math": "3x = 15"}, {"math": "x = 5"}))
    )

    assert result.ok, result.rejection


def test_a_step_chain_with_inconsistent_solutions_is_rejected():
    """3x = 15 does not become x = 7 — the transformation is wrong."""
    result = _validate(_raw(_steps({"math": "3x = 15"}, {"math": "x = 7"})))

    assert result.rejection == "step_chain_inconsistent"


def test_a_latex_equation_chain_is_understood():
    result = _validate(
        _raw(
            _steps(
                {"math": "3x = 15"},
                {"math": "\\frac{3x}{3} = \\frac{15}{3}"},
                {"math": "x = 5"},
            )
        )
    )

    assert result.ok, result.rejection


def test_unparseable_steps_do_not_cause_a_false_rejection():
    """Prose-mixed and multi-variable chains abstain rather than fail."""
    result = _validate(
        _raw(
            _steps(
                {"math": "A = \\pi r^2"},
                {"math": "\\text{substitute } r = 3"},
                {"math": "A \\approx 28.3"},
            )
        )
    )

    assert result.ok, result.rejection


# ---- final answer ----------------------------------------------------------

def test_a_final_answer_disagreeing_with_the_stored_answer_is_rejected():
    result = _validate(_raw(final_answer="7"), correct_answer="5")

    assert result.rejection == "answer_mismatch"


def test_a_final_answer_matching_in_a_different_form_is_accepted():
    result = _validate(_raw(final_answer="x = 5"), correct_answer="5")

    assert result.ok, result.rejection


# ---- expression_compare ----------------------------------------------------

def _compare(**overrides) -> dict:
    block = {
        "kind": "expression_compare",
        "id": "e1",
        "caption": "Comparing two fractions",
        "narration": "Look at this together.",
        "left": "\\frac{3}{4}",
        "right": "\\frac{2}{3}",
        "relation": ">",
    }
    block.update(overrides)
    return block


def test_a_true_relation_is_accepted():
    result = _validate(_raw(_steps({"math": "3x = 15"}), _compare()))

    assert result.ok, result.rejection


def test_a_false_relation_is_rejected():
    result = _validate(_raw(_steps({"math": "3x = 15"}), _compare(relation="<")))

    assert result.rejection == "expression_relation_false"


def test_a_rewrite_that_does_not_equal_its_own_side_is_rejected():
    result = _validate(
        _raw(_steps({"math": "3x = 15"}), _compare(rewrite_left="\\frac{7}{12}"))
    )

    assert result.rejection == "expression_rewrite_mismatch"


def test_a_correct_common_denominator_rewrite_is_accepted():
    result = _validate(
        _raw(
            _steps({"math": "3x = 15"}),
            _compare(rewrite_left="\\frac{9}{12}", rewrite_right="\\frac{8}{12}"),
        )
    )

    assert result.ok, result.rejection


def test_a_symbolic_comparison_abstains_instead_of_rejecting():
    result = _validate(
        _raw(_steps({"math": "3x = 15"}), _compare(left="2n", right="n", relation=">"))
    )

    assert result.ok, result.rejection


# ---- fraction_bars ---------------------------------------------------------

def test_a_bar_label_disagreeing_with_its_shading_is_rejected():
    """Labelled 3/4 but shaded 8/12 — the picture contradicts its own caption."""
    result = _validate(
        _raw(
            _steps({"math": "3x = 15"}),
            {
                "kind": "fraction_bars",
                "id": "f1",
                "caption": "Two fractions",
        "narration": "Look at this together.",
                "bars": [{"numerator": 8, "denominator": 12, "label": "3/4"}],
            },
        )
    )

    assert result.rejection == "fraction_label_mismatch"


def test_an_equivalent_bar_label_is_accepted():
    result = _validate(
        _raw(
            _steps({"math": "3x = 15"}),
            {
                "kind": "fraction_bars",
                "id": "f1",
                "caption": "Two fractions",
        "narration": "Look at this together.",
                "bars": [{"numerator": 9, "denominator": 12, "label": "3/4"}],
            },
        )
    )

    assert result.ok, result.rejection


def test_a_non_numeric_bar_label_abstains():
    result = _validate(
        _raw(
            _steps({"math": "3x = 15"}),
            {
                "kind": "fraction_bars",
                "id": "f1",
                "caption": "Two fractions",
        "narration": "Look at this together.",
                "bars": [{"numerator": 3, "denominator": 4, "label": "most of the pizza"}],
            },
        )
    )

    assert result.ok, result.rejection


# ---- coordinate_plane ------------------------------------------------------

def _plane(**overrides) -> dict:
    block = {
        "kind": "coordinate_plane",
        "id": "p1",
        "caption": "The line y = 2x + 1",
        "narration": "Look at this together.",
        "x_min": -1,
        "x_max": 5,
        "y_min": -1,
        "y_max": 11,
        "lines": [{"slope": 2, "intercept": 1, "label": "y = 2x + 1"}],
    }
    block.update(overrides)
    return block


def test_a_plotted_line_matching_the_question_equation_is_accepted():
    result = _validate(
        _raw(_steps({"math": "3x = 15"}), _plane()),
        question_text="What does the slope of y = 2x + 1 mean?",
    )

    assert result.ok, result.rejection


def test_a_plotted_line_contradicting_the_question_equation_is_rejected():
    result = _validate(
        _raw(_steps({"math": "3x = 15"}), _plane()),
        question_text="What does the slope of y = 3x + 1 mean?",
    )

    assert result.rejection == "plane_slope_mismatch"


def test_the_plane_check_abstains_when_the_question_states_no_equation():
    """Most questions do not state y = mx + b. Those must pass untouched."""
    result = _validate(
        _raw(_steps({"math": "3x = 15"}), _plane()),
        question_text="Draw a line that goes up steeply and explain its slope.",
    )

    assert result.ok, result.rejection


def test_an_implicit_slope_of_one_is_understood():
    result = _validate(
        _raw(_steps({"math": "3x = 15"}), _plane(lines=[{"slope": 1, "intercept": 0}])),
        question_text="Graph y = x and describe it.",
    )

    assert result.ok, result.rejection


# ---- geometry --------------------------------------------------------------

def test_geometry_figures_receive_structural_validation_only():
    """Documents a known gap so its absence reads as a decision, not an oversight:
    nothing verifies that base 6 is the base in the question."""
    result = _validate(
        _raw(
            _steps({"math": "A = \\frac{1}{2} b h"}),
            {
                "kind": "geometry_figure",
                "id": "g1",
                "caption": "A triangle",
        "narration": "Look at this together.",
                "shape": "triangle",
                "dimensions": {"base": 999, "height": 999},
            },
        ),
        question_text="A triangle has base 6 cm and height 4 cm. Find its area.",
    )

    assert result.ok, result.rejection
