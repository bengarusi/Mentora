import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getSummary } from "../api/tutor";
import { ScoreBadge } from "../components/ScoreBadge";
import type { SessionSummary } from "../types";

export function SummaryPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const [summary, setSummary] = useState<SessionSummary | null>(null);

  useEffect(() => {
    getSummary(id).then(setSummary);
  }, [id]);

  if (!summary) {
    return <div className="container">Loading summary…</div>;
  }

  return (
    <div className="container">
      <h2>Lesson summary</h2>
      <div className="card">
        <div className="summary-head">
          <ScoreBadge level={summary.success_level} />
          {summary.score !== null && (
            <span className="muted">Score: {summary.score} / 3</span>
          )}
        </div>
        {summary.summary_text && <p>{summary.summary_text}</p>}
      </div>

      <h3>Questions</h3>
      {summary.questions.map((q) => (
        <div key={q.id} className="card">
          <p>
            <strong>Q{q.difficulty}:</strong> {q.question_text}
          </p>
          {q.student_answer && (
            <p className="muted">Your answer: {q.student_answer}</p>
          )}
          {q.is_correct !== null && (
            <p className={q.is_correct ? "feedback-correct" : "feedback-wrong"}>
              {q.is_correct ? "Correct" : "Incorrect"}
              {q.feedback ? ` — ${q.feedback}` : ""}
            </p>
          )}
        </div>
      ))}

      <div className="lesson-actions">
        <Link to="/progress">View progress</Link>
        <Link to="/new">Start another lesson</Link>
      </div>
    </div>
  );
}
