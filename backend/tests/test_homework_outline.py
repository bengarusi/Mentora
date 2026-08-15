from app.files.homework import segment_exercises


def test_segment_exercises_preserves_server_held_question_refs():
    outline = segment_exercises(
        "Exercise 1: What is 1/2 + 1/4?\nExercise 2: Simplify 6/8. Answer: 3/4"
    )

    assert [item["ref"] for item in outline] == ["exercise-1", "exercise-2"]
    assert outline[0]["text"] == "Exercise 1: What is 1/2 + 1/4?"
    assert outline[1]["expected_answer"] == "3/4"
