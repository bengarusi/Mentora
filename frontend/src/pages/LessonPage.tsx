import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getMessages, getSession } from "../api/sessions";
import { advancePhase, streamTurn } from "../api/tutor";
import { ChatWindow } from "../components/ChatWindow";
import { LearningPathSidebar } from "../components/LearningPathSidebar";
import type { LessonPhase, Message, Session } from "../types";

const PHASE_ORDER: LessonPhase[] = [
  "teaching",
  "pre_practice_example",
  "practice",
  "practice_summary",
  "summary",
  "completed",
];

const PHASE_LABEL: Record<LessonPhase, string> = {
  teaching: "Teaching",
  pre_practice_example: "Guided Example",
  practice: "Practice",
  practice_summary: "Practice Results",
  summary: "Summary",
  completed: "Completed",
};

export function LessonPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();

  const [session, setSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    const [s, m] = await Promise.all([getSession(id), getMessages(id)]);
    setSession(s);
    setMessages(m);
  }, [id]);

  useEffect(() => {
    reload();
  }, [reload]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;
      setBusy(true);

      const studentId = -Date.now();
      const tutorId = studentId - 1;
      setMessages((prev) => [
        ...prev,
        { id: studentId, session_id: id, role: "student", content: trimmed, created_at: null },
        { id: tutorId, session_id: id, role: "tutor", content: "", created_at: null },
      ]);
      setDraft("");

      try {
        await streamTurn(id, trimmed, (delta) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === tutorId ? { ...m, content: m.content + delta } : m
            )
          );
        });
      } catch {
        await reload();
      } finally {
        setBusy(false);
      }
    },
    [busy, id, reload]
  );

  async function handleStartPractice() {
    setBusy(true);
    try {
      const result = await advancePhase(id);
      navigate(`/lesson/${id}/pre-practice`, {
        state: { exampleContent: result.tutor_message },
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleFinishLesson() {
    setBusy(true);
    try {
      await advancePhase(id); // SUMMARY → COMPLETED
      navigate(`/lesson/${id}/summary`);
    } finally {
      setBusy(false);
    }
  }

  if (!session) {
    return (
      <div className="lesson-layout no-right">
        <LearningPathSidebar active="lessons" />
        <div className="chat-main">
          <p className="chat-empty">Loading lesson…</p>
        </div>
      </div>
    );
  }

  const phase = (session.phase ?? "teaching") as LessonPhase;
  const isTeaching = phase === "teaching";
  const canChat = phase === "teaching" || phase === "summary";
  const progressPct =
    ((PHASE_ORDER.indexOf(phase) + 1) / PHASE_ORDER.length) * 100;

  return (
    <div className="lesson-layout">
      <LearningPathSidebar
        active="lessons"
        action={
          isTeaching ? (
            <button
              type="button"
              className="primary-button pressable-button"
              onClick={handleStartPractice}
              disabled={busy}
            >
              <span className="material-symbols-outlined">fitness_center</span>
              Start Practice
            </button>
          ) : undefined
        }
      />

      <section className="chat-main">
        <ChatWindow messages={messages} />

        {isTeaching && (
          <div className="quick-actions">
            <button
              type="button"
              className="pill-button pressable-button"
              onClick={() => sendMessage("Can you explain this again in a simpler way?")}
              disabled={busy}
            >
              Explain again
            </button>
            <button
              type="button"
              className="pill-button pressable-button"
              onClick={() => sendMessage("Can you give me another example?")}
              disabled={busy}
            >
              Give me an example
            </button>
            <button
              type="button"
              className="pill-button pressable-button"
              onClick={handleStartPractice}
              disabled={busy}
            >
              I&apos;m ready to practice
            </button>
          </div>
        )}

        {canChat && (
          <form
            className="chat-input-bar"
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage(draft);
            }}
          >
            <span className="material-symbols-outlined chat-add">add_circle</span>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Type your message here…"
              disabled={busy}
            />
            <button
              type="submit"
              className="primary-button pressable-button chat-send"
              disabled={busy || !draft.trim()}
            >
              Send
              <span className="material-symbols-outlined">send</span>
            </button>
          </form>
        )}

        {!canChat && (
          <div className="lesson-cta-row">
            {phase === "pre_practice_example" && (
              <button
                className="primary-button pressable-button"
                onClick={() => navigate(`/lesson/${id}/pre-practice`)}
              >
                Continue to Example
              </button>
            )}
            {phase === "practice" && (
              <button
                className="primary-button pressable-button"
                onClick={() => navigate(`/lesson/${id}/practice`)}
              >
                Go to Practice
              </button>
            )}
            {phase === "practice_summary" && (
              <button
                className="primary-button pressable-button"
                onClick={() => navigate(`/lesson/${id}/practice/summary`)}
              >
                View Practice Results
              </button>
            )}
            {phase === "completed" && (
              <button
                className="primary-button pressable-button"
                onClick={() => navigate(`/lesson/${id}/summary`)}
              >
                View Summary
              </button>
            )}
          </div>
        )}

        {phase === "summary" && (
          <div className="lesson-cta-row">
            <button
              className="secondary-button pressable-button"
              onClick={handleFinishLesson}
              disabled={busy}
            >
              Finish Lesson
            </button>
          </div>
        )}
      </section>

      <aside className="lesson-progress-panel">
        <h3 className="progress-panel-title">Your Progress</h3>

        <div className="context-card">
          <div className="context-row">
            <span className="material-symbols-outlined">menu_book</span>
            <div>
              <div className="context-row-label">Topic</div>
              <div className="context-row-value">{session.topic}</div>
            </div>
          </div>
          {session.subtopic && (
            <div className="context-row">
              <span className="material-symbols-outlined">target</span>
              <div>
                <div className="context-row-label">Subtopic</div>
                <div className="context-row-value">{session.subtopic}</div>
              </div>
            </div>
          )}
          <div className="context-row">
            <span className="material-symbols-outlined">flag</span>
            <div>
              <div className="context-row-label">Phase</div>
              <div className="context-row-value">{PHASE_LABEL[phase]}</div>
            </div>
          </div>
        </div>

        <div className="context-card">
          <div className="mastery-block">
            <div className="mastery-head">
              <span>Lesson progress</span>
              <span>{Math.round(progressPct)}%</span>
            </div>
            <div className="mastery-bar">
              <span style={{ width: `${progressPct}%` }} />
            </div>
          </div>
          <div className="context-row-label" style={{ marginTop: "0.25rem" }}>
            Goal
          </div>
          <p style={{ margin: 0, fontSize: "0.9rem" }}>{session.goal_text}</p>
        </div>

        <div className="mentor-tip-card">
          <h4>
            <span className="material-symbols-outlined">tips_and_updates</span>
            Mentor Tip
          </h4>
          <p>
            Take your time and think out loud. Asking the tutor questions is one
            of the best ways to learn!
          </p>
        </div>

        <div className="panel-visual">
          <span className="material-symbols-outlined">calculate</span>
          <span className="caption">{session.subtopic || session.topic}</span>
        </div>
      </aside>
    </div>
  );
}
