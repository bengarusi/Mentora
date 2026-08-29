import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createSession, getSession } from "../api/sessions";
import { advancePhase, getPracticeSummary } from "../api/tutor";
import { LearningPathSidebar } from "../components/LearningPathSidebar";
import { RichText } from "../components/RichText";
import type { GradedPracticeItem, PracticeSummary, Session } from "../types";

// Convert legacy flat "Step 1: ... Step 2: ..." strings to a markdown list.
function normalizeSolutionSteps(steps: string): string {
  if (!steps || steps.includes("\n")) return steps;
  return steps.replace(/Step\s+(\d+):\s*/g, "\n$1. ").trimStart();
}

const LEVEL_LABEL: Record<string, string> = {
  achieved: "Excellent",
  partially: "Good effort",
  not_achieved: "Keep practicing",
};

export function PracticeSummaryPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();

  const [summary, setSummary] = useState<PracticeSummary | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPracticeSummary(id).then(setSummary).catch(() => null);
    getSession(id).then(setSession).catch(() => null);
  }, [id]);

  async function handleContinueToSummary() {
    setBusy(true);
    try {
      await advancePhase(id); // PRACTICE_SUMMARY → SUMMARY
      navigate(`/lesson/${id}/summary`);
    } finally {
      setBusy(false);
    }
  }

  async function handlePracticeAgain() {
    if (!session) return;
    setBusy(true);
    try {
      // Safe: start a fresh lesson for the same topic/subtopic rather than
      // forcing a completed session back into the practice phase.
      const fresh = await createSession({
        subject: "math",
        topic: session.topic,
        subtopic: session.subtopic,
        goal_text: session.goal_text,
      });
      navigate(`/lesson/${fresh.id}`);
    } catch {
      setBusy(false);
    }
  }

  if (!summary) {
    return (
      <div className="lesson-layout no-right">
        <LearningPathSidebar active="practice" />
        <div className="summary-page">
          <p className="muted">Loading practice results…</p>
        </div>
      </div>
    );
  }

  const pct =
    summary.total_questions > 0
      ? Math.round((summary.total_correct / summary.total_questions) * 100)
      : 0;
  const level = summary.success_level
    ? LEVEL_LABEL[summary.success_level] ?? summary.success_level
    : null;

  const allGraded = summary.sets.flatMap((s) => s.questions);
  const wrong = allGraded.filter((q) => !q.is_correct);

  return (
    <div className="lesson-layout no-right">
      <LearningPathSidebar active="practice" />

      <section className="summary-page">
        <div className="summary-inner">
          <div className="summary-hero">
            <div className="summary-hero-text">
              <h1>Nice practicing!</h1>
              <p>
                You got <strong>{summary.total_correct}</strong> of{" "}
                <strong>{summary.total_questions}</strong> correct.
              </p>
              {level && (
                <div className="summary-chips">
                  <span
                    className={`status-chip ${pct >= 50 ? "green" : "amber"}`}
                  >
                    <span className="material-symbols-outlined">star</span>
                    {level}
                  </span>
                </div>
              )}
            </div>
            <div className="summary-ring" style={{ ["--pct" as string]: pct }}>
              <div className="ring-label">
                <span className="ring-pct">{pct}%</span>
                <span className="ring-cap">Correct</span>
              </div>
            </div>
          </div>

          {wrong.length > 0 && (
            <div className="learned-card">
              <h3>
                <span className="material-symbols-outlined">target</span>
                What to practice more
              </h3>
              <ul className="summary-list">
                {wrong.slice(0, 4).map((q) => (
                  <li key={q.question_id}>
                    <span className="material-symbols-outlined">chevron_right</span>
                    <RichText content={q.question_text} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {summary.sets.map((set) => (
            <div key={set.set_number}>
              <p className="section-label">Practice Set {set.set_number}</p>
              {set.questions.map((q: GradedPracticeItem, idx: number) => (
                <div
                  key={q.question_id}
                  className={`result-card ${q.is_correct ? "correct" : "incorrect"}`}
                >
                  <div className="result-card-head">
                    <strong>Question {idx + 1}</strong>
                    <span
                      className={`result-tag ${q.is_correct ? "correct" : "incorrect"}`}
                    >
                      <span className="material-symbols-outlined">
                        {q.is_correct ? "check_circle" : "cancel"}
                      </span>
                      {q.is_correct ? "Correct" : "Incorrect"}
                    </span>
                  </div>
                  <RichText content={q.question_text} />
                  {q.student_answer && (
                    <p className="result-answer">Your answer: {q.student_answer}</p>
                  )}
                  {q.feedback && <RichText content={q.feedback} />}

                  {!q.is_correct &&
                    (q.correct_answer || q.solution_steps || q.explanation) && (
                      <button
                        className="ghost-button pressable-button"
                        style={{ marginTop: "0.5rem", padding: "0.4rem 0.8rem" }}
                        onClick={() =>
                          setExpandedId((p) =>
                            p === q.question_id ? null : q.question_id
                          )
                        }
                      >
                        {expandedId === q.question_id ? "Hide solution" : "Show solution"}
                      </button>
                    )}

                  {expandedId === q.question_id && (
                    <div className="solution-panel">
                      {q.correct_answer && (
                        <div className="solution-row">
                          <strong>Correct answer:</strong>
                          <RichText content={q.correct_answer} />
                        </div>
                      )}
                      {q.solution_steps && (
                        <div className="solution-row">
                          <strong>Solution steps:</strong>
                          <RichText content={normalizeSolutionSteps(q.solution_steps)} />
                        </div>
                      )}
                      {q.explanation && (
                        <div className="solution-row">
                          <strong>What to remember:</strong>
                          <RichText content={q.explanation} />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))}

          <div className="summary-actions">
            {/* Named for what it does: this opens a fresh lesson on the same
                subtopic and starts its chat over. This one stays exactly as it
                is — its questions, its score and the progress they earned are
                already saved. */}
            <button
              className="secondary-button pressable-button"
              onClick={handlePracticeAgain}
              disabled={busy || !session}
            >
              <span className="material-symbols-outlined">refresh</span>
              Start New Lesson
            </button>
            <button
              className="primary-button pressable-button"
              onClick={handleContinueToSummary}
              disabled={busy}
            >
              {busy ? "Loading…" : "Continue to Lesson Summary"}
              {!busy && <span className="material-symbols-outlined">arrow_forward</span>}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
