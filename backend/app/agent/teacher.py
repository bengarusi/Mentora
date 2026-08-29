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
        # the student had already solved. Every bucket is spelled out, and each
        # end-state is called out separately: "index past the end of the
        # outline" is not something a model reads as "finished", and a parked
        # exercise is not something it can guess is still owed.
        solved = sorted(state.solved_refs)
        skipped = sorted(state.skipped_refs)
        untouched = [
            item.ref
            for item in outline
            if item.ref not in state.solved_refs and item.ref not in state.skipped_refs
        ]
        current_ref = (
            outline[state.current_exercise_index - 1].ref
            if 0 <= state.current_exercise_index - 1 < len(outline)
            else None
        )
        if not outline or untouched:
            stage = ""
        elif not skipped:
            stage = (
                "\nEVERY exercise in this homework is now solved. Do not open another one and do "
                "not re-ask a solved exercise. Congratulate the student, offer to go back over "
                "anything they want to revisit, and append no control tag.\n"
            )
        elif len(skipped) == 1:
            stage = (
                f"\nEverything is done except {skipped[0]}, which the student skipped earlier. "
                "It is the only exercise left. Tell them that plainly and encourage them to try "
                "it now — offer a first step or a hint rather than another way out. Do not offer "
                "to move on, because there is nowhere left to move on to.\n"
            )
        else:
            stage = (
                f"\nEvery exercise has been reached, and these were skipped and are still owed: "
                f"{json.dumps(skipped)}. Ask the student which one they would like to go back to, "
                f"suggesting {current_ref}. Ask one at a time.\n"
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
When an exercise is finished and another is unsolved, ask that next exercise outright and tag it,
rather than asking whether the student would like to continue. A question that expects only "yes"
leaves nothing for the server to check.
A student who asks to move on has already been moved on by the server: the exercise they left is
listed as skipped and the current exercise below is the new one. Go straight to it — never tell
them they must finish the one they just left.
{stage}Current exercise index: {state.current_exercise_index} ({current_ref}); hint level: {state.hint_level}.
Solved: {json.dumps(solved)}. Skipped, still owed: {json.dumps(skipped)}.
Not yet reached: {json.dumps(untouched)}.
Awaiting: {state.response_target}. Outline: {outline_json}"""
        messages = [Msg("system", system)]
        messages.extend(Msg("assistant" if role == "tutor" else "user", content) for role, content in history)
        messages.append(Msg("user", student_text))
        return messages
