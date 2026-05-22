import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { finishPractice, nextPracticeSet, startPractice, submitPracticeSet } from "../api/tutor";
import { RichText } from "../components/RichText";
import type {
  GradedPracticeItem,
  PracticeAnswerItem,
  PracticeQuestion,
  PracticeStartResult,
} from "../types";

type SetPhase = "answering" | "graded";

export function PracticePage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();
  const location = useLocation();

  const initialSet = (location.state as { initialSet?: PracticeStartResult })
    ?.initialSet ?? null;

  const [questions, setQuestions] = useState<PracticeQuestion[]>(
    initialSet?.questions ?? []
  );
  const [setNumber, setSetNumber] = useState(initialSet?.set_number ?? 1);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [grades, setGrades] = useState<GradedPracticeItem[]>([]);
  const [setPhase, setSetPhase] = useState<SetPhase>("answering");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadInitialSet = useCallback(async () => {
    if (questions.length > 0) return;
    setBusy(true);
    try {
      const result = await startPractice(id);
      setQuestions(result.questions);
      setSetNumber(result.set_number);
    } catch {
      setError("Could not load practice questions. Please try again.");
    } finally {
      setBusy(false);
    }
  }, [id, questions.length]);

  useEffect(() => {
    loadInitialSet();
  }, [loadInitialSet]);

  function handleAnswerChange(questionId: number, value: string) {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  }

  const allAnswered =
    questions.length > 0 &&
    questions.every((q) => (answers[q.id] ?? "").trim().length > 0);

  async function handleSubmit() {
    const payload: PracticeAnswerItem[] = questions.map((q) => ({
      question_id: q.id,
      answer: answers[q.id] ?? "",
    }));
    setBusy(true);
    setError(null);
    try {
      const result = await submitPracticeSet(id, payload);
      setGrades(result.grades);
      setSetPhase("graded");
    } catch {
      setError("Could not submit answers. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handlePracticeMore() {
    setBusy(true);
    setError(null);
    try {
      const result = await nextPracticeSet(id);
      setQuestions(result.questions);
      setSetNumber(result.set_number);
      setAnswers({});
      setGrades([]);
      setSetPhase("answering");
    } catch {
      setError("Could not load next practice set. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleFinishPractice() {
    setBusy(true);
    try {
      await finishPractice(id);
      navigate(`/lesson/${id}/practice/summary`);
    } finally {
      setBusy(false);
    }
  }

  const correctCount = grades.filter((g) => g.is_correct).length;

  return (
    <div className="container">
      <h2>Practice — Set {setNumber}</h2>
      <p className="muted">Answer all 3 questions, then submit them together.</p>

      {error && <p className="error">{error}</p>}

      {setPhase === "answering" && (
        <>
          {questions.map((q, idx) => (
            <div key={q.id} className="card question-card">
              <div className="question-header">
                <strong>Question {idx + 1}</strong>
                <span className="muted">difficulty {q.difficulty}</span>
              </div>
              <RichText content={q.question_text} />
              <input
                value={answers[q.id] ?? ""}
                onChange={(e) => handleAnswerChange(q.id, e.target.value)}
                placeholder="Your answer"
                disabled={busy}
              />
            </div>
          ))}

          <div className="lesson-actions">
            <button
              className="btn-primary"
              onClick={handleSubmit}
              disabled={busy || !allAnswered}
            >
              {busy ? "Grading…" : "Submit Answers"}
            </button>
          </div>
        </>
      )}

      {setPhase === "graded" && (
        <>
          <div className="card">
            <p>
              <strong>
                You got {correctCount} out of {grades.length} correct.
              </strong>
            </p>
          </div>

          {grades.map((g, idx) => (
            <div
              key={g.question_id}
              className={`card question-card ${
                g.is_correct ? "answer-correct" : "answer-wrong"
              }`}
            >
              <div className="question-header">
                <strong>Question {idx + 1}</strong>
                <span className={g.is_correct ? "feedback-correct" : "feedback-wrong"}>
                  {g.is_correct ? "Correct" : "Incorrect"}
                </span>
              </div>
              <RichText content={g.question_text} />
              <p className="muted">Your answer: {g.student_answer}</p>
              <div className={g.is_correct ? "feedback-correct" : "feedback-wrong"}>
                <RichText content={g.feedback} />
              </div>
            </div>
          ))}

          <div className="lesson-actions">
            <button onClick={handlePracticeMore} disabled={busy}>
              Practice More
            </button>
            <button
              className="btn-primary"
              onClick={handleFinishPractice}
              disabled={busy}
            >
              Finish Practice
            </button>
          </div>
        </>
      )}
    </div>
  );
}
