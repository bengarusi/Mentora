from __future__ import annotations

import json

from app.agent.schemas import HomeworkExercise, SessionState
from app.llm.tooling import Msg


def stage_note(state: SessionState, outline: list[HomeworkExercise]) -> str:
    """What is left of the worksheet, and what to do about it.

    Shared with the runner: after an answer settles the last untouched exercise,
    the model has already been given its instructions for this turn, so the same
    words go into the tool observation — otherwise the offer to return to parked
    work arrives a turn late, after the student has said something else.
    """
    skipped = sorted(state.skipped_refs)
    untouched = [
        item.ref
        for item in outline
        if item.ref not in state.solved_refs and item.ref not in state.skipped_refs
    ]
    if not outline or untouched:
        return ""
    if not skipped:
        return (
            "\nEVERY exercise in this homework is now solved. Do not open another one and do "
            "not re-ask a solved exercise. Congratulate the student, offer to go back over "
            "anything they want to revisit, and append no control tag.\n"
        )
    # Nothing is left but parked work, so there is nowhere to move on to. The
    # student may still decline, and is told what declining means rather than
    # being quietly let off.
    press = (
        "This is all that is left of the homework, so there is nothing to move on to and nothing "
        "to stop for. If the student says they would rather stop or leave it, do NOT agree and do "
        "NOT say goodbye. Say that everything else is finished and only this one is left, give "
        "them the first step of it, and end by asking them what that step gives."
    )
    if len(skipped) == 1:
        return (
            f"\nEverything is done except {skipped[0]}, which the student skipped earlier. "
            f"Tell them that plainly and encourage them to try it now. {press}\n"
        )
    return (
        f"\nEvery exercise has been reached. These were skipped and are still owed: "
        f"{json.dumps(skipped)}. Ask which one they want to go back to, one at a time. {press}\n"
    )


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
        just_skipped: str | None = None,
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
        current = (
            outline[state.current_exercise_index - 1]
            if 0 <= state.current_exercise_index - 1 < len(outline)
            else None
        )
        current_ref = current.ref if current else None
        # The transcript argues against the state: the last thing in it is the
        # tutor posing the exercise the student then asked to leave, which reads
        # as "the next one" all over again. So the exercise to ask is named
        # outright, with its text, last — nearest the student's turn.
        directive = ""
        if just_skipped:
            directive += (
                f"\nThe student has just asked to move on. {just_skipped} is now PARKED: do not "
                "ask it again in this reply, and do not tell them to finish it first.\n"
            )
        if current is not None:
            directive += (
                f'\nThe exercise to work on right now is {current.ref}: "{current.text}". '
                "Ask about this one and no other, and end that question with its control tag: "
                f'<response_target question_ref="{current.ref}" target_type="exercise"/>. '
                "Without the tag nothing the student answers can be checked.\n"
                "If their message is an attempt at this exercise, call evaluateAnswer for "
                f"{current.ref} — you may never judge an answer yourself.\n"
            )
        stage = stage_note(state, outline)
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
Current exercise index: {state.current_exercise_index} ({current_ref}); hint level: {state.hint_level}.
Solved: {json.dumps(solved)}. Skipped, still owed: {json.dumps(skipped)}.
Not yet reached: {json.dumps(untouched)}.
Awaiting: {state.response_target}. Outline: {outline_json}
{directive}{stage}"""
        messages = [Msg("system", system)]
        messages.extend(Msg("assistant" if role == "tutor" else "user", content) for role, content in history)
        messages.append(Msg("user", student_text))
        return messages
