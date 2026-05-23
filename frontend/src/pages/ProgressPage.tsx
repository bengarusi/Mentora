import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getProgress, getProgressMap } from "../api/progress";
import { MATH_CURRICULUM } from "../data/mathCurriculum";
import { ScoreBadge } from "../components/ScoreBadge";
import type { ProgressMap, StudentProgress } from "../types";

const STATUS_LABEL: Record<string, string> = {
  mastered: "Mastered",
  in_progress: "In Progress",
  needs_practice: "Needs Practice",
  not_started: "Not Started",
};

interface MergedSub {
  id: string;
  title: string;
  status: string;
  mastery: number | null;
  lastSessionId: number | null;
}
interface MergedTopic {
  id: string;
  title: string;
  icon: string;
  status: string;
  mastery: number | null;
  subtopics: MergedSub[];
}

function mergeWithCurriculum(map: ProgressMap | null): MergedTopic[] {
  const backendTopics = new Map(map?.topics.map((t) => [t.topic, t]) ?? []);
  return MATH_CURRICULUM.map((ct) => {
    const bt = backendTopics.get(ct.title);
    const backendSubs = new Map(
      bt?.subtopics.map((s) => [s.subtopic, s]) ?? []
    );
    const subtopics: MergedSub[] = ct.subtopics.map((cs) => {
      const bs = backendSubs.get(cs.title);
      return {
        id: cs.id,
        title: cs.title,
        status: bs?.status ?? "not_started",
        mastery: bs?.mastery_percentage ?? null,
        lastSessionId: bs?.last_session_id ?? null,
      };
    });
    return {
      id: ct.id,
      title: ct.title,
      icon: ct.icon,
      status: bt?.status ?? "not_started",
      mastery: bt?.mastery_percentage ?? null,
      subtopics,
    };
  });
}

export function ProgressPage() {
  const [progress, setProgress] = useState<StudentProgress | null>(null);
  const [map, setMap] = useState<ProgressMap | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());

  useEffect(() => {
    getProgress().then(setProgress).catch(() => null);
    getProgressMap().then(setMap).catch(() => null);
  }, []);

  const topics = useMemo(() => mergeWithCurriculum(map), [map]);

  function toggle(topicId: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(topicId)) next.delete(topicId);
      else next.add(topicId);
      return next;
    });
  }

  if (!progress) {
    return <div className="page-shell">Loading progress…</div>;
  }

  const hasQuestions = progress.total_questions_answered > 0;

  return (
    <div className="page-shell">
      <div className="page-header">
        <h1>My Progress</h1>
        <p className="muted">Track how you&apos;re doing across every math topic.</p>
      </div>

      <div className="progress-overview">
        <div className="overview-stat">
          <span className="stat-value">{progress.total_sessions}</span>
          <span className="stat-label">Total lessons</span>
        </div>
        <div className="overview-stat">
          <span className="stat-value">{progress.completed_sessions}</span>
          <span className="stat-label">Completed</span>
        </div>
        <div className="overview-stat">
          <span className="stat-value">
            {hasQuestions ? `${progress.average_percentage?.toFixed(0)}%` : "—"}
          </span>
          <span className="stat-label">Average score</span>
        </div>
        <div className="overview-stat">
          <span className="stat-value">
            {hasQuestions
              ? `${progress.total_correct_answered}/${progress.total_questions_answered}`
              : "—"}
          </span>
          <span className="stat-label">Questions correct</span>
        </div>
      </div>

      <p className="section-label">Topics</p>
      {topics.map((t) => {
        const isOpen = open.has(t.id);
        return (
          <div key={t.id} className={`progress-topic-card${isOpen ? " open" : ""}`}>
            <button
              type="button"
              className="progress-topic-head"
              onClick={() => toggle(t.id)}
              aria-expanded={isOpen}
            >
              <span className="progress-topic-icon">
                <span className="material-symbols-outlined">{t.icon}</span>
              </span>
              <span className="progress-topic-title">{t.title}</span>
              <span className="progress-topic-meta">
                <span className={`status-badge ${t.status}`}>
                  {STATUS_LABEL[t.status] ?? t.status}
                </span>
                <span className="progress-topic-pct">
                  {t.mastery !== null ? `${t.mastery}%` : ""}
                </span>
                <span className="material-symbols-outlined progress-topic-chevron">
                  expand_more
                </span>
              </span>
            </button>

            {isOpen && (
              <div className="progress-subtopics">
                {t.subtopics.map((s) => (
                  <div key={s.id} className="progress-subtopic-row">
                    <span className="progress-subtopic-title">{s.title}</span>
                    <div className="mastery-bar">
                      <span style={{ width: `${s.mastery ?? 0}%` }} />
                    </div>
                    <span className="progress-subtopic-pct">
                      {s.mastery !== null ? `${s.mastery}%` : "—"}
                    </span>
                    <span className={`status-badge ${s.status}`}>
                      {STATUS_LABEL[s.status] ?? s.status}
                    </span>
                    {s.lastSessionId ? (
                      <Link to={`/lesson/${s.lastSessionId}`} className="back-link">
                        Open
                      </Link>
                    ) : (
                      <span style={{ width: "2.5rem" }} />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      <p className="section-label">Recent Lessons</p>
      {progress.recent.length === 0 && (
        <p className="muted">No lessons yet — pick a topic to get started!</p>
      )}
      {progress.recent.map((s) => (
        <div key={s.session_id} className="progress-recent-row">
          <div>
            <div className="recent-title">{s.topic}</div>
            <div className="recent-sub">{s.goal_text}</div>
          </div>
          <div className="progress-recent-meta">
            {s.score !== null && s.total_questions !== null && (
              <span className="muted">
                {s.score}/{s.total_questions}
              </span>
            )}
            <ScoreBadge level={s.success_level} />
            <Link to={`/lesson/${s.session_id}`} className="back-link">
              Open
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}
