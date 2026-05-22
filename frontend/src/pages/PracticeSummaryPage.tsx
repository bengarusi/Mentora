import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { advancePhase, getPracticeSummary } from "../api/tutor";
import type { GradedPracticeItem, PracticeSummary } from "../types";

export function PracticeSummaryPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();

  const [summary, setSummary] = useState<PracticeSummary | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPracticeSummary(id).then(setSummary);
  }, [id]);

  async function handleContinueToSummary() {
    setBusy(true);
    try {
      const result = await advancePhase(id);  // PRACTICE_SUMMARY → SUMMARY
      navigate(`/lesson/${id}`, {
        state: { summaryMessage: result.tutor_message },
      });
    } finally {
      setBusy(false);
    }
  }

  function toggleExpand(questionId: number) {
    setExpandedId((prev) => (prev === questionId ? null : questionId));
  }

  if (!summary) {
    return <div className="container">Loading practice results…</div>;
  }

  const pct =
    summary.total_questions > 0
      ? Math.round((summary.total_correct / summary.total_questions) * 100)
      : 0;

  const levelLabel: Record<string, string> = {
    achieved: "Excellent",
    partially: "Good effort",
    not_achieved: "Keep practicing",
  };

  return (
    <div className="container">
      <h2>Practice Results</h2>

      <div className="card summary-head">
        <div>
          <strong>
            {summary.total_correct} / {summary.total_questions} correct ({pct}%)
          </strong>
          {summary.success_level && (
            <span className="muted" style={{ marginLeft: "1rem" }}>
              {levelLabel[summary.success_level] ?? summary.success_level}
            </span>
          )}
        </div>
      </div>

      {summary.sets.map((set) => (
        <div key={set.set_number}>
          <h3>Practice Set {set.set_number}</h3>
          {set.questions.map((q: GradedPracticeItem, idx: number) => (
            <div
              key={q.question_id}
              className={`card question-card ${
                q.is_correct ? "answer-correct" : "answer-wrong"
              }`}
            >
              <div className="question-header">
                <strong>Question {idx + 1}</strong>
                <span className={q.is_correct ? "feedback-correct" : "feedback-wrong"}>
                  {q.is_correct ? "Correct" : "Incorrect"}
                </span>
              </div>

              <p>{q.question_text}</p>

              {q.student_answer && (
                <p className="muted">Your answer: {q.student_answer}</p>
              )}

              {q.feedback && (
                <p className={q.is_correct ? "feedback-correct" : "feedback-wrong"}>
                  {q.feedback}
                </p>
              )}

              {!q.is_correct && (
                <button
                  className="link-button expand-btn"
                  onClick={() => toggleExpand(q.question_id)}
                >
                  {expandedId === q.question_id
                    ? "Hide solution"
                    : "Show solution"}
                </button>
              )}

              {expandedId === q.question_id && (
                <div className="solution-panel">
                  {q.correct_answer && (
                    <p>
                      <strong>Correct answer:</strong> {q.correct_answer}
                    </p>
                  )}
                  {q.solution_steps && (
                    <div>
                      <strong>Solution steps:</strong>
                      <pre className="solution-steps">{q.solution_steps}</pre>
                    </div>
                  )}
                  {q.explanation && (
                    <p>
                      <strong>What to remember:</strong> {q.explanation}
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}

      <div className="lesson-actions">
        <button
          className="btn-primary"
          onClick={handleContinueToSummary}
          disabled={busy}
        >
          {busy ? "Loading…" : "Continue to Lesson Summary"}
        </button>
      </div>
    </div>
  );
}
