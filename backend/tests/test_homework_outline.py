from app.files.homework import segment_exercises


def test_segment_exercises_preserves_server_held_question_refs():
    outline = segment_exercises(
        "Exercise 1: What is 1/2 + 1/4?\nExercise 2: Simplify 6/8. Answer: 3/4"
    )

    assert [item["ref"] for item in outline] == ["exercise-1", "exercise-2"]
    assert outline[0]["text"] == "Exercise 1: What is 1/2 + 1/4?"
    assert outline[1]["expected_answer"] == "3/4"


def test_segment_exercises_preserves_all_mixed_marker_questions_in_order():
    text = (
        "Question 1: One Star Point is worth 7 points. Emma has 8. How many points?\n"
        "2. Write 0.6 as a fraction in simplest form.\n"
        "3) Round 4.786 to the nearest tenth.\n"
        "4. Simplify 18/30.\n"
        "5) What is 25% of 80?\n"
        "6. Calculate 36 ÷ 6.\n"
        "7) What is 8 × 7?"
    )

    outline = segment_exercises(text)

    assert [item["ref"] for item in outline] == [
        "exercise-1",
        "exercise-2",
        "exercise-3",
        "exercise-4",
        "exercise-5",
        "exercise-6",
        "exercise-7",
    ]
    assert [item["text"] for item in outline] == text.splitlines()


def test_segment_exercises_keeps_numbered_working_inside_its_labeled_exercise():
    text = (
        "Exercise 1: Add the fractions.\n"
        "1. Find a common denominator.\n"
        "2. Add the numerators.\n"
        "3. Simplify the result."
    )

    outline = segment_exercises(text)

    assert len(outline) == 1
    assert outline[0]["text"] == text
