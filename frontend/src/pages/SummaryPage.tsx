import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getLessonSummary, getPracticeSummary } from "../api/tutor";
import type { PracticeSummary } from "../types";

export function SummaryPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);

  const [summary, setSummary] = useState<PracticeSummary | null>(null);
  const [summaryMessage, setSummaryMessage] = useState<string | null>(null);

  useEffect(() => {
    getPracticeSummary(id).then(setSummary).catch(() => null);
    // Use the dedicated endpoint so we always get the lesson summary text,
    // not whatever happens to be the last message in the DB.
    getLessonSummary(id)
      .then((r) => setSummaryMessage(r.summary_text))
      .catch(() => null);
  }, [id]);

  const levelLabel: Record<string, string> = {
    achieved: "Excellent",
    partially: "Good effort",
    not_achieved: "Keep practicing",
  };

  return (
    <div className="container">
      <h2>Lesson Complete</h2>

      {summaryMessage && (
        <div className="card">
          <p>{summaryMessage}</p>
        </div>
      )}

      {summary && (
        <div className="card summary-head">
          <div>
            <strong>
              Practice score: {summary.total_correct} / {summary.total_questions}
            </strong>
            {summary.success_level && (
              <span className="muted" style={{ marginLeft: "1rem" }}>
                {levelLabel[summary.success_level] ?? summary.success_level}
              </span>
            )}
          </div>
        </div>
      )}

      <div className="lesson-actions">
        <Link to="/progress">View progress</Link>
        <Link to="/new">Start another lesson</Link>
      </div>
    </div>
  );
}
