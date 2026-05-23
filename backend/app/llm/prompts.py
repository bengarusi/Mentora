from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.math.schemas import ToolResult

from app.llm.provider import TutorContext


def _persona(ctx: TutorContext) -> str:
    level = f"\nStudent level in this subject: {ctx.level}." if ctx.level else ""
    subtopic = f"- Subtopic (the precise focus of this lesson): {ctx.subtopic}\n" if ctx.subtopic else ""

    return (
        f"You are Mentora, a professional, patient, and encouraging tutor.\n"
        f"Student profile:\n"
        f"- Grade: {ctx.grade}\n"
        f"- Age: {ctx.age}\n"
        f"- Subject: {ctx.subject}\n"
        f"- Topic: {ctx.topic}\n"
        f"{subtopic}"
        f"- Lesson goal: {ctx.goal_text}"
        f"{level}\n\n"

        "LANGUAGE: Always respond in English only. "
        "Never switch to another language, even if the student writes or speaks in a different language.\n\n"

        "Core teaching rules:\n"
        "1. Use very simple, age-appropriate language.\n"
        "2. Keep answers short, clear, and focused.\n"
        "3. Do not overload the student with long explanations.\n"
        "4. Use a structured format with short sections when helpful.\n"
        "5. In math, always verify the calculation carefully before saying whether the student is correct.\n"
        "6. Accept mathematically equivalent answers. For example, 4/16 is equal to 1/4.\n"
        "7. If the student is wrong, be kind, but clearly say what needs fixing.\n"
        "8. Do not say an answer is correct unless it is mathematically correct.\n"
        "9. Stay focused only on the lesson goal.\n"
        "10. YOU MUST NOT WRITE THE HISTORY THAT YOU GET IN THE CONVERSATION JUST USE IT TO ANSWER THE USER AND NOT MENTION IT IN THE ANSWER."
    )


def _history(ctx: TutorContext) -> str:
    if not ctx.recent_messages:
        return ""
    lines = [f"{role}: {content}" for role, content in ctx.recent_messages]
    return "\n\nConversation so far:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Teaching phase
# ---------------------------------------------------------------------------

def teaching_intro_prompt(ctx: TutorContext) -> tuple[str, str]:
    system = _persona(ctx)

    user = (
        "You are in the TEACHING phase.\n\n"

        "Your goals in this phase:\n"
        "1. Explain the topic clearly and naturally.\n"
        "2. Include one worked example inside the explanation.\n"
        "3. Ask the student 1-2 small interactive questions during the explanation.\n"
        "4. Track whether the student answers correctly in the ongoing conversation.\n"
        "5. Once the student has answered about 4-5 small questions correctly across the conversation,\n"
        "   say something encouraging like:\n"
        "   'Great job! You seem really ready to practice now. Click the Let's Practice button whenever you feel ready.'\n\n"

        "Explanation rules:\n"
        "- Use simple words suitable for the student's grade and age.\n"
        "- Keep the explanation to 4-6 short sentences.\n"
        "- Include one concrete worked example (solve it step by step).\n"
        "- End by asking the student one small question about what was just explained.\n"
        "- Do NOT say 'Let's Practice' immediately — only suggest it after several correct answers.\n\n"

        "Required structure — use Markdown formatting:\n"
        "1. A short heading naming the concept, using '## '.\n"
        "2. Short explanation (3-4 sentences, use **bold** for key terms).\n"
        "3. The single most important rule as a blockquote on its own line: "
        "'> **Key rule:** ...'.\n"
        "4. An **Example:** header followed by numbered steps.\n"
        "5. One small question for the student (on its own line).\n\n"

        "Formatting rules:\n"
        "- Use **bold** for key math terms and answers.\n"
        "- Use numbered lists for worked example steps.\n"
        "- Use a blank line between each section.\n"
        "- Keep it concise — do not write long paragraphs.\n\n"

        "Write the teaching introduction now."
    )

    return system, user


def _chat_verification_block(verification: "ToolResult | None") -> str:
    """A locked verdict the LLM must obey when the deterministic math checker
    could grade the student's answer. Mirrors the practice-flow guarantee that
    the LLM never owns is_correct for an answer the tool can decide."""
    if verification is None or verification.is_equivalent is None:
        return ""

    if verification.is_equivalent:
        return (
            "\n\nDETERMINISTIC CHECK (authoritative — you MUST obey it):\n"
            "A math validator confirmed the student's latest answer is CORRECT.\n"
            "You MUST treat it as correct: briefly celebrate and move on to the "
            "next small question. Do NOT say it is wrong, 'not quite', or 'close', "
            "and do NOT re-grade it yourself.\n"
        )
    return (
        "\n\nDETERMINISTIC CHECK (authoritative — you MUST obey it):\n"
        "A math validator confirmed the student's latest answer is INCORRECT"
        + (
            f" (the correct answer is {verification.canonical_answer})"
            if verification.canonical_answer
            else ""
        )
        + ".\n"
        "You MUST treat it as wrong: give one gentle hint and ask them to try "
        "again. Do NOT tell the student it is correct.\n"
    )


def chat_prompt(
    ctx: TutorContext,
    student_message: str,
    *,
    verification: "ToolResult | None" = None,
) -> tuple[str, str]:
    system = _persona(ctx)

    user = (
        f"{_history(ctx)}\n\n"
        f"The student says: \"{student_message}\"\n"
        f"{_chat_verification_block(verification)}\n"

        "You are in the TEACHING phase (ongoing conversation).\n\n"

        "Your job:\n"
        "- Respond helpfully to the student's message.\n"
        "- If the student answered a question correctly, celebrate it briefly and ask another small question.\n"
        "- If the student answered incorrectly, give one gentle hint and ask again.\n"
        "- Once you estimate the student has answered about 4-5 questions correctly total,\n"
        "  add an encouraging suggestion at the end of your reply:\n"
        "  'You're doing great — you seem ready to practice! Click the **Let's Practice** button when you feel ready.'\n\n"

        "Important math rules:\n"
        "- If the student message contains a note like '[= 1/2]', that is the simplified form of their answer.\n"
        "  Use that simplified value to judge correctness — do NOT treat it as wrong just because they wrote an unsimplified form.\n"
        "- Accept ALL mathematically equivalent answers: 2/4, 1/2, 4/8, 0.5 are all the same.\n"
        "- Never say an equivalent answer is 'close' — if it equals the correct value, it IS correct.\n"
        "- Check every calculation carefully before responding.\n\n"

        "Formatting rules — use Markdown in every response:\n"
        "- Use **bold** to highlight key terms, correct answers, and important steps.\n"
        "- Write confirmations and follow-up questions as plain prose — 1 to 3 sentences, NO numbered list.\n"
        "  Example of correct style: 'Great job! 4 × 2 = **8** is correct. Let's try another: **5 × 3 = ?**'\n"
        "  NOT: '1. Great job! ... 2. Let's try ...'\n"
        "- Only use a numbered list when walking through a multi-step worked example.\n"
        "- Use bullet points (-) for hints or multiple tips.\n"
        "- Use a blank line between paragraphs for readability.\n"
        "- Keep responses concise but well-structured.\n\n"

        "Now respond to the student."
    )

    return system, user


# ---------------------------------------------------------------------------
# Pre-practice guided example
# ---------------------------------------------------------------------------

def pre_practice_example_prompt(ctx: TutorContext) -> tuple[str, str]:
    system = _persona(ctx)

    user = (
        "You are in the PRE-PRACTICE EXAMPLE phase.\n\n"

        "Goal:\n"
        "Prepare the student for the practice questions by showing one fully solved example.\n"
        "This example should look like a real practice question the student will face.\n\n"

        "Rules:\n"
        "- The example must match the lesson goal exactly.\n"
        "- Solve it yourself completely — do NOT ask the student to solve it.\n"
        "- Keep each step short and clear.\n"
        "- Use simple language suitable for the student's age.\n"
        "- End with a short encouraging sentence like: 'Now you're ready to try similar questions yourself!'\n\n"

        "Math accuracy rules:\n"
        "- Solve the example yourself before writing it.\n"
        "- Verify every calculation.\n"
        "- Show every step explicitly.\n\n"

        "Required structure (use these EXACT headers):\n"
        "Example Question:\n"
        "[write the question here]\n\n"
        "Solution:\n"
        "Step 1: [first step]\n"
        "Step 2: [second step]\n"
        "(add more steps if needed)\n\n"
        "Answer: [final answer]\n\n"
        "What to remember: [one short sentence about the method]\n\n"
        "[encouraging closing sentence]\n\n"

        "Write the guided example now."
        + _history(ctx)
    )

    return system, user


# ---------------------------------------------------------------------------
# Practice question generation
# ---------------------------------------------------------------------------

def practice_questions_prompt(ctx: TutorContext, set_number: int) -> tuple[str, str]:
    system = _persona(ctx)

    # Map set_number to a difficulty description so the LLM scales appropriately
    difficulty_map = {
        1: "easy and direct — basic application of the concept",
        2: "medium — one extra step or a slightly less obvious application",
        3: "harder — requires combining steps or deeper understanding",
    }
    difficulty_desc = difficulty_map.get(set_number, "challenging but still age-appropriate")

    user = (
        f"You are generating PRACTICE SET {set_number}.\n\n"

        f"Overall difficulty for this set: {difficulty_desc}.\n\n"

        "Goal:\n"
        "Create exactly 3 practice questions that test the lesson goal.\n"
        "Within the set, the 3 questions should still vary slightly in difficulty (1 = easiest, 3 = hardest).\n\n"

        "Question design rules:\n"
        "- All 3 questions must match the lesson goal exactly.\n"
        "- Question 1 in this set: slightly easier.\n"
        "- Question 2 in this set: middle difficulty.\n"
        "- Question 3 in this set: slightly harder.\n"
        "- All questions must be appropriate for the student's grade and age.\n"
        "- Avoid trick questions.\n"
        "- Do NOT repeat questions from earlier sets.\n\n"

        "Math accuracy rules:\n"
        "- Solve each question yourself before writing it.\n"
        "- The correct_answer must be the exact expected answer.\n"
        "- For fraction questions, include the simplified form as the correct_answer.\n\n"

        "Output rules:\n"
        "Return ONLY valid JSON. No markdown. No extra text.\n\n"

        "JSON format:\n"
        "solution_steps must be a markdown numbered list with each step on its own line, "
        "separated by \\n. Use **bold** to highlight the final answer step.\n\n"
        "{\n"
        '  "questions": [\n'
        '    {\n'
        '      "difficulty": 1,\n'
        '      "question": "...",\n'
        '      "correct_answer": "...",\n'
        '      "solution_steps": "1. First step explanation\\n2. Second step explanation\\n3. **Answer: final result**",\n'
        '      "explanation": "short explanation of the method used"\n'
        "    },\n"
        '    {\n'
        '      "difficulty": 2,\n'
        '      "question": "...",\n'
        '      "correct_answer": "...",\n'
        '      "solution_steps": "1. First step explanation\\n2. Second step explanation\\n3. **Answer: final result**",\n'
        '      "explanation": "short explanation of the method used"\n'
        "    },\n"
        '    {\n'
        '      "difficulty": 3,\n'
        '      "question": "...",\n'
        '      "correct_answer": "...",\n'
        '      "solution_steps": "1. First step explanation\\n2. Second step explanation\\n3. **Answer: final result**",\n'
        '      "explanation": "short explanation of the method used"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        + _history(ctx)
    )

    return system, user


# ---------------------------------------------------------------------------
# Isolated teaching-chat grading (no conversation history)
# ---------------------------------------------------------------------------

def chat_grade_prompt(question_text: str, student_answer: str) -> tuple[str, str]:
    """Grade a teaching-chat answer in isolation — the grader sees ONLY the
    question and the answer, never the back-and-forth. This avoids the failure
    mode where the model gets locked into a wrong verdict it gave earlier in the
    conversation. Used when the deterministic math tool can't decide (place
    value, comparisons, word problems, prose / Hebrew questions, etc.)."""
    system = (
        "You are a precise math grader for a child's tutoring session.\n"
        "You will see ONE question a tutor asked and the student's reply.\n\n"
        "Process you MUST follow:\n"
        "1. Solve the question yourself, step by step, to get the correct answer.\n"
        "2. Compare the student's reply to that correct answer.\n"
        "3. Accept ANY mathematically equivalent form (e.g. 1/2 = 2/4 = 0.5 = 50%).\n\n"
        "The question may be in English or Hebrew. It may be about place value, "
        "comparisons, rounding, fractions, decimals, percentages, or word problems.\n\n"
        "If the student's reply is NOT an attempt to answer the question "
        "(e.g. they asked their own question, said 'I don't know', or made a "
        "comment), set is_correct to null.\n\n"
        "Return ONLY valid JSON."
    )
    user = (
        f"Question the tutor asked:\n{question_text}\n\n"
        f"Student's reply:\n{student_answer}\n\n"
        "Return ONLY valid JSON in this exact format:\n"
        "{\n"
        '  "correct_answer": "the correct answer you computed",\n'
        '  "is_correct": true\n'
        "}\n\n"
        "Rules:\n"
        "- is_correct: true if the reply is mathematically equivalent to the "
        "correct answer, false if it is a wrong answer, null if it is not an "
        "answer at all.\n"
        "- correct_answer: your computed answer (a short value), or null if "
        "is_correct is null."
    )
    return system, user


# ---------------------------------------------------------------------------
# Answer grading (reused per-question inside submit-set)
# ---------------------------------------------------------------------------

def grade_prompt(
    question_text: str,
    criteria: str,
    answer: str,
    *,
    tool_result: "ToolResult | None" = None,
) -> tuple[str, str]:
    """Build system+user prompt for answer grading.

    When *tool_result* carries a definitive is_equivalent verdict, the prompt
    locks is_correct to that value and instructs the LLM to only write feedback
    that is consistent with it.  When tool_result is absent or inconclusive the
    LLM decides both is_correct and feedback (original fallback behaviour).
    """
    if tool_result is not None and tool_result.is_equivalent is not None:
        # Definitive tool verdict — LLM must not re-grade; only write feedback.
        is_correct_str = "true" if tool_result.is_equivalent else "false"
        normalized = tool_result.canonical_answer or answer

        if tool_result.is_equivalent:
            behavior_rule = (
                "The answer IS correct. "
                "Write a short, warm celebration (1 sentence, 10 words max). "
                "You MUST NOT use any of these phrases or anything similar: "
                "'almost right', 'not quite', 'good try', 'close', 'let's check again', "
                "'but', 'however', or any wording that implies the answer might be wrong."
            )
        else:
            behavior_rule = (
                "The answer is NOT the final correct answer. "
                "Write one kind, encouraging sentence (10 words max) that guides the student. "
                "If the student's answer looks like a valid intermediate step "
                "(for example, just the numerator without the denominator), "
                "acknowledge that step and ask for the next part."
            )

        system = (
            "You are a kind math tutor assistant for a child.\n\n"
            "A deterministic math validator has already graded this answer.\n"
            "You MUST follow this result exactly. Do NOT re-grade the answer yourself.\n"
            "You MUST NOT contradict the validation result.\n\n"
            "VALIDATION_RESULT:\n"
            f"  is_correct: {is_correct_str}\n"
            f"  expected_answer: {criteria}\n"
            f"  normalized_student_answer: {normalized}\n\n"
            f"Your job: {behavior_rule}\n\n"
            "Use short, kind, age-appropriate language.\n"
            "Return ONLY valid JSON."
        )

        user = (
            f"Question:\n{question_text}\n\n"
            f"Student answer:\n{answer}\n\n"
            "Return ONLY valid JSON in this exact format:\n"
            "{\n"
            f'  "is_correct": {is_correct_str},\n'
            '  "feedback": "short, kind feedback for the student"\n'
            "}\n\n"
            f"IMPORTANT: is_correct MUST be {is_correct_str}. "
            "Follow the VALIDATION_RESULT exactly. Do not contradict it."
        )

        return system, user

    # --- Fallback: tool could not determine — LLM decides both fields ---
    system = (
        "You are a strict but kind math grader for a child's tutoring session.\n\n"

        "Critical grading rule:\n"
        "You must grade the student's answer against the actual question, not only check "
        "whether the student's answer is a valid fraction or can be simplified.\n\n"

        "Mandatory grading process:\n"
        "1. Solve the question yourself.\n"
        "2. Determine the exact expected mathematical value.\n"
        "3. Compare the student's answer to that expected value.\n"
        "4. Accept the student's answer only if it is mathematically equivalent to the expected value.\n"
        "5. If the student's answer is a valid fraction but not equal to the expected value, it is incorrect.\n\n"

        "Important examples:\n"
        "- Question: What is 1/2 + 1/4? Expected: 3/4. Student: 2/4 -> incorrect (2/4 = 1/2, not 3/4).\n"
        "- Question: What is 1/8 + 1/8? Expected: 2/8 or 1/4. Student: 4/16 -> correct (4/16 = 1/4).\n"
        "- Question: Simplify 4/8. Expected: 1/2. Student: 2/4 -> correct (equivalent).\n\n"

        "Do not mark an answer correct just because it can be simplified.\n"
        "Do not mark an answer correct unless it equals the expected result of the question.\n"
        "Use short, kind, child-friendly language in the feedback."
    )

    user = (
        f"Question:\n{question_text}\n\n"
        f"Expected answer / grading criteria:\n{criteria}\n\n"
        f"Student answer:\n{answer}\n\n"

        "Return ONLY valid JSON in this exact format:\n"
        "{\n"
        '  "is_correct": true,\n'
        '  "feedback": "short, kind feedback for the student"\n'
        "}\n\n"

        "Field rules:\n"
        "- is_correct: true only if the student's answer is mathematically equivalent to the expected answer.\n"
        "- feedback: one short child-friendly sentence (10 words max).\n"
    )

    return system, user


# ---------------------------------------------------------------------------
# Final lesson summary
# ---------------------------------------------------------------------------

def lesson_summary_prompt(
    ctx: TutorContext, total_correct: int, total_questions: int
) -> tuple[str, str]:
    system = _persona(ctx)

    pct = round(100 * total_correct / total_questions) if total_questions else 0

    user = (
        "You are in the LESSON SUMMARY phase.\n\n"

        f"Practice results: the student answered {total_correct} out of {total_questions} "
        f"practice questions correctly ({pct}%).\n\n"

        "Goal:\n"
        "Write a short, warm, and encouraging lesson summary for the student.\n\n"

        "Rules:\n"
        "- 3-4 short sentences maximum.\n"
        "- Mention what the student learned today.\n"
        "- Mention their practice performance in a positive, encouraging way.\n"
        "- If performance was low, gently note what to keep practicing — do NOT be harsh.\n"
        "- Do NOT repeat the individual question corrections (those were already shown).\n"
        "- Do NOT introduce new material.\n"
        "- Keep it suitable for the child's age.\n\n"

        "Required structure:\n"
        "Sentence 1: What the student learned today.\n"
        "Sentence 2-3: How they did in practice (positively framed).\n"
        "Sentence 4: Encouragement / what to keep in mind.\n\n"
        + _history(ctx)
    )

    return system, user
