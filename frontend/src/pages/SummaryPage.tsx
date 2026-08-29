import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { createSession, getSession } from "../api/sessions";
import { advancePhase, getLessonSummary, getPracticeSummary } from "../api/tutor";
import { LearningPathSidebar } from "../components/LearningPathSidebar";
import { RichText } from "../components/RichText";
import type { PracticeSummary, Session } from "../types";

const LEVEL_LABEL: Record<string, string> = {
  achieved: "Excellent",
  partially: "Good effort",
  not_achieved: "Keep practicing",
};

export function SummaryPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();
  const { student } = useAuth();

  const [summary, setSummary] = useState<PracticeSummary | null>(null);
  const [summaryText, setSummaryText] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPracticeSummary(id).then(setSummary).catch(() => null);
    getLessonSummary(id).then((r) => setSummaryText(r.summary_text)).catch(() => null);
    getSession(id).then(setSession).catch(() => null);
  }, [id]);

  /** Close the lesson for good — the only route to the COMPLETED phase, and so
   * the only thing that moves the "Completed" count on the progress page. */
  async function handleFinishLesson() {
    setBusy(true);
    try {
      await advancePhase(id); // SUMMARY → COMPLETED
      // Straight to the progress page: the lesson is over, and what the student
      // wants to see next is what it added up to.
      navigate("/progress");
    } finally {
      setBusy(false);
    }
  }

  async function handlePracticeAgain() {
    if (!session) return;
    setBusy(true);
    try {
      // Moving on closes this lesson: it is already at its summary, so one step
      // finishes it. Best-effort, like on the practice results screen.
      if (session.phase === "summary") {
        try {
          await advancePhase(id); // SUMMARY → COMPLETED
        } catch {
          // Left open — nothing the student did is lost by it.
        }
      }
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

  const name = student?.full_name?.trim().split(" ")[0];
  const greeting = name ? `Awesome Work, ${name}!` : "Awesome Work!";

  const hasScore = !!summary && summary.total_questions > 0;
  const pct = hasScore
    ? Math.round((summary!.total_correct / summary!.total_questions) * 100)
    : 100;
  const level = summary?.success_level
    ? LEVEL_LABEL[summary.success_level] ?? summary.success_level
    : null;
  const achieved = summary?.success_level === "achieved";

  const subtopic = session?.subtopic;
  const focusText = !summary
    ? "Great effort today — keep up the good work!"
    : achieved
    ? `You've got a strong grasp of ${subtopic ?? "this topic"}!`
    : `Keep practicing ${subtopic ?? "this topic"} to build your confidence.`;

  return (
    <div className="lesson-layout no-right">
      <LearningPathSidebar active="lessons" />

      <section className="summary-page">
        <div className="summary-inner">
          <div className="summary-hero">
            <div className="summary-hero-text">
              <h1>{greeting}</h1>
              <p>
                {session
                  ? `You finished ${session.subtopic || session.topic}. Here's how it went!`
                  : "Here's how your lesson went!"}
              </p>
              <div className="summary-chips">
                <span className="status-chip green">
                  <span className="material-symbols-outlined">verified</span>
                  Lesson complete
                </span>
                {level && (
                  <span className={`status-chip ${achieved ? "green" : "amber"}`}>
                    <span className="material-symbols-outlined">military_tech</span>
                    {level}
                  </span>
                )}
              </div>
            </div>
            <div className="summary-ring" style={{ ["--pct" as string]: pct }}>
              <div className="ring-label">
                <span className="ring-pct">{pct}%</span>
                <span className="ring-cap">Completed</span>
              </div>
            </div>
          </div>

          <div className="summary-grid">
            <div className="learned-card">
              <h3>
                <span className="material-symbols-outlined">done_all</span>
                What you learned
              </h3>
              <ul className="summary-list">
                {session && (
                  <li>
                    <span className="material-symbols-outlined">check_circle</span>
                    <div>
                      <strong>{session.subtopic || session.topic}</strong>
                      <div className="muted" style={{ fontSize: "0.85rem" }}>
                        {session.goal_text}
                      </div>
                    </div>
                  </li>
                )}
                {hasScore && (
                  <li>
                    <span className="material-symbols-outlined">check_circle</span>
                    <div>
                      <strong>
                        {summary!.total_correct} / {summary!.total_questions} practice
                        questions correct
                      </strong>
                    </div>
                  </li>
                )}
              </ul>
            </div>

            <div className="tutor-note-card">
              <h3>
                <span className="material-symbols-outlined">auto_awesome</span>
                Tutor&apos;s Note
              </h3>
              {summaryText ? (
                <RichText content={summaryText} />
              ) : (
                <p>Great work finishing this lesson. Keep it up!</p>
              )}
            </div>
          </div>

          <div className="focus-card">
            <div className="focus-body">
              <h3>
                <span className="material-symbols-outlined">flag</span>
                Focus Area
              </h3>
              <p className="muted" style={{ margin: 0 }}>{focusText}</p>
            </div>
            {hasScore && (
              <div className="mastery-block">
                <div className="mastery-head">
                  <span>Practice score</span>
                  <span>{pct}%</span>
                </div>
                <div className="mastery-bar">
                  <span style={{ width: `${pct}%` }} />
                </div>
              </div>
            )}
          </div>

          <div className="summary-actions">
            {/* The lesson ends here or nowhere: this is the screen every
                finished lesson lands on, and until now nothing on it could
                close one, so "Completed" on the progress page stayed at 0. */}
            {session?.phase === "summary" && (
              <button
                className="primary-button pressable-button"
                onClick={handleFinishLesson}
                disabled={busy}
              >
                <span className="material-symbols-outlined">task_alt</span>
                Finish Lesson
              </button>
            )}
            {session?.phase === "completed" && (
              <span className="status-badge mastered">
                <span className="material-symbols-outlined">check_circle</span>
                Lesson completed
              </span>
            )}
            {/* Same action, same name as on the practice results screen: this
                lesson is finished, so it is closed and a new one on the same
                subtopic takes its place. */}
            <button
              className="secondary-button pressable-button"
              onClick={handlePracticeAgain}
              disabled={busy || !session}
            >
              <span className="material-symbols-outlined">refresh</span>
              Start New Lesson
            </button>
            <button
              className="ghost-button pressable-button"
              onClick={() => navigate("/")}
            >
              <span className="material-symbols-outlined">arrow_forward</span>
              Choose Another Topic
            </button>
            <button
              className="ghost-button pressable-button"
              onClick={() => navigate("/progress")}
            >
              View Progress
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
