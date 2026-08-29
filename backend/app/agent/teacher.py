from __future__ import annotations

import json

from app.agent.schemas import HomeworkExercise, SessionState
from app.llm.tooling import Msg


class TeacherAgent:
    """Homework-only policy. It chooses tools and prose, never verdicts."""

    exposed_tools = (
        "evaluateAnswer",
        "analyzeHomework",
        "recordLearningAnnotation",
        "searchStudyMaterials",
    )

    def messages(
        self,
        *,
        state: SessionState,
        outline: list[HomeworkExercise],
        history: list[tuple[str, str]],
        student_text: str,
    ) -> list[Msg]:
        outline_json = json.dumps(
            [
                {"ref": item.ref, "text": item.text, "target_type": item.target_type}
                for item in outline
            ],
            ensure_ascii=False,
        )
        # Which exercises are done is state the model cannot infer from the
        # transcript alone — the index alone once had it re-opening an exercise
        # the student had already solved. Both facts are spelled out, and the
        # empty-remaining case is called out separately because "index past the
        # end of the outline" is not something a model reads as "finished".
        solved = sorted(state.solved_refs)
        remaining = [item.ref for item in outline if item.ref not in state.solved_refs]
        finished = bool(outline) and not remaining
        completion = (
            "\nEVERY exercise in this homework is now solved. Do not open another one and do "
            "not re-ask a solved exercise. Congratulate the student, offer to go back over "
            "anything they want to revisit, and append no control tag.\n"
            if finished
            else ""
        )
        system = f"""You are Mentora's Homework Tutor. Guide, do not give away unsolved final answers.
The server is the sole authority on correctness and state. When evaluateAnswer returns an
authoritative verdict, obey it exactly and never re-grade it. For an incorrect answer, do not
quote correct_answer or hidden steps. Intermediate text next to tool calls is discarded.
Use tools when evidence is needed. Keep the final response concise and ask one useful question.
When the final response asks the student for an answer, append exactly one invisible control tag:
<response_target question_ref="exercise-N" target_type="exercise"/>. For a substep, the only
allowed reference is exercise-N-step-K where N is the current exercise and K is hint level + 1.
Use a reference from the outline for a full exercise. Never invent any other reference. If no
answer is expected, append no tag.
Never ask again about an exercise listed as solved; move to the next unsolved one.
{completion}Current exercise index: {state.current_exercise_index}; hint level: {state.hint_level}.
Solved: {json.dumps(solved)}. Still unsolved: {json.dumps(remaining)}.
Awaiting: {state.response_target}. Outline: {outline_json}"""
        messages = [Msg("system", system)]
        messages.extend(Msg("assistant" if role == "tutor" else "user", content) for role, content in history)
        messages.append(Msg("user", student_text))
        return messages
