import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { startAssessment, submitAnswer } from "../api/tutor";
import { QuestionCard } from "../components/QuestionCard";
import type { Question } from "../types";

interface AnswerState {
  isCorrect: boolean;
  feedback: string;
}

export function AssessmentPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();

  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<number, AnswerState>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setQuestions(await startAssessment(id));
    } catch {
      setError("Could not load the assessment.");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSubmit(questionId: number, answer: string) {
    setBusy(true);
    try {
      const result = await submitAnswer(id, questionId, answer);
      setAnswers((prev) => ({
        ...prev,
        [questionId]: { isCorrect: result.is_correct, feedback: result.feedback },
      }));
    } finally {
      setBusy(false);
    }
  }

  const allAnswered =
    questions.length > 0 &&
    questions.every((q) => answers[q.id] !== undefined);

  return (
    <div className="container">
      <h2>Check your understanding</h2>
      {error && <p className="error">{error}</p>}
      {questions.map((q, index) => {
        const state = answers[q.id];
        return (
          <QuestionCard
            key={q.id}
            question={q}
            index={index}
            answered={state !== undefined}
            isCorrect={state?.isCorrect ?? null}
            feedback={state?.feedback ?? null}
            onSubmit={(answer) => handleSubmit(q.id, answer)}
            disabled={busy}
          />
        );
      })}

      {allAnswered && (
        <button onClick={() => navigate(`/lesson/${id}`)}>
          Continue the lesson
        </button>
      )}
    </div>
  );
}
