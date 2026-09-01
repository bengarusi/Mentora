from app.files.homework import count_exercises


def test_counts_labeled_exercises():
    text = "Exercise 1: What is 2+2?\nExercise 2: What is 3+3?\nExercise 3: What is 4+4?"
    assert count_exercises(text) == 3


def test_counts_question_and_problem_labels_too():
    text = "Question 1: ...\nProblem 2: ...\nExercise 3: ..."
    assert count_exercises(text) == 3


def test_is_case_insensitive():
    assert count_exercises("exercise 1: x\nEXERCISE 2: y") == 2


def test_falls_back_to_bare_numbered_items():
    text = "1. What is 2+2?\n2. What is 3+3?\n3) What is 4+4?"
    assert count_exercises(text) == 3


def test_prefers_labeled_over_numbered_when_both_present():
    """A worksheet with 'Exercise 1' headers, each followed by a numbered
    sub-step list, should count exercises, not sub-steps."""
    text = (
        "Exercise 1: Add the fractions.\n"
        "1. Find a common denominator.\n"
        "2. Add the numerators.\n"
        "Exercise 2: Simplify the result.\n"
    )
    assert count_exercises(text) == 2


def test_numbered_steps_after_the_only_labeled_exercise_are_not_questions():
    text = (
        "Exercise 1: Add the fractions.\n"
        "1. Find a common denominator.\n"
        "2. Add the numerators.\n"
        "3. Simplify the result.\n"
    )

    assert count_exercises(text) == 1


def test_mixed_question_markers_do_not_drop_the_unlabeled_questions():
    """OCR can recognize one printed heading but transcribe the remaining
    question numbers without their labels.  Every top-level question still
    belongs in the worksheet total."""
    text = (
        "Question 1: One Star Point is worth 7 points. Emma has 8. How many points?\n"
        "2. Write 0.6 as a fraction in simplest form.\n"
        "3) Round 4.786 to the nearest tenth.\n"
        "4. Simplify 18/30.\n"
        "5) What is 25% of 80?\n"
        "6. Calculate 36 ÷ 6.\n"
        "7) What is 8 × 7?"
    )

    assert count_exercises(text) == 7


def test_unstructured_text_counts_as_one_exercise():
    assert count_exercises("What is 1/2 + 1/4?") == 1


def test_empty_or_whitespace_counts_as_zero():
    assert count_exercises("") == 0
    assert count_exercises("   \n\n  ") == 0
