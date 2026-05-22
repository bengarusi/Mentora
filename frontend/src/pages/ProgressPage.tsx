import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getProgress } from "../api/progress";
import { ScoreBadge } from "../components/ScoreBadge";
import type { StudentProgress } from "../types";

export function ProgressPage() {
  const [progress, setProgress] = useState<StudentProgress | null>(null);

  useEffect(() => {
    getProgress().then(setProgress);
  }, []);

  if (!progress) {
    return <div className="container">Loading progress…</div>;
  }

  return (
    <div className="container">
      <h2>My progress</h2>

      <div className="stats">
        <div className="card stat">
          <span className="stat-value">{progress.total_sessions}</span>
          <span className="muted">Total lessons</span>
        </div>
        <div className="card stat">
          <span className="stat-value">{progress.completed_sessions}</span>
          <span className="muted">Completed</span>
        </div>
        <div className="card stat">
          <span className="stat-value">
            {progress.average_score !== null
              ? progress.average_score.toFixed(1)
              : "—"}
          </span>
          <span className="muted">Avg score / 3</span>
        </div>
      </div>

      <h3>Outcomes</h3>
      <div className="card">
        {Object.entries(progress.success_distribution).map(([level, count]) => (
          <div key={level} className="dist-row">
            <ScoreBadge level={level} />
            <span>{count}</span>
          </div>
        ))}
      </div>

      <h3>Recent lessons</h3>
      {progress.recent.length === 0 && <p className="muted">No lessons yet.</p>}
      {progress.recent.map((s) => (
        <div key={s.session_id} className="card recent-row">
          <div>
            <strong>
              {s.subject} — {s.topic}
            </strong>
            <p className="muted">{s.goal_text}</p>
          </div>
          <div className="recent-meta">
            <ScoreBadge level={s.success_level} />
            <Link to={`/lesson/${s.session_id}`}>Open</Link>
          </div>
        </div>
      ))}
    </div>
  );
}
