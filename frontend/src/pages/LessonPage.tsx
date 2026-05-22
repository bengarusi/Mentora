import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getMessages, getSession } from "../api/sessions";
import { advancePhase, sendTurn } from "../api/tutor";
import { ChatWindow } from "../components/ChatWindow";
import { PhaseBadge } from "../components/PhaseBadge";
import type { Message, Session } from "../types";

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

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    setBusy(true);
    try {
      await sendTurn(id, draft.trim());
      setDraft("");
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function handleLetsPractice() {
    setBusy(true);
    try {
      const result = await advancePhase(id);
      // Result phase will be "pre_practice_example"; pass the generated example via nav state
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
      await advancePhase(id);  // SUMMARY → COMPLETED
      navigate(`/lesson/${id}/summary`);
    } finally {
      setBusy(false);
    }
  }

  if (!session) {
    return <div className="container">Loading lesson…</div>;
  }

  const phase = session.phase;
  const canChat = phase === "teaching" || phase === "summary";

  return (
    <div className="container lesson">
      <div className="lesson-header">
        <div>
          <h2>
            {session.subject} — {session.topic}
          </h2>
          <p className="muted">Goal: {session.goal_text}</p>
        </div>
        <PhaseBadge phase={phase} />
      </div>

      <ChatWindow messages={messages} />

      {canChat && (
        <form className="turn-form" onSubmit={handleSend}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask the tutor a question…"
            disabled={busy}
          />
          <button type="submit" disabled={busy || !draft.trim()}>
            Send
          </button>
        </form>
      )}

      <div className="lesson-actions">
        {phase === "teaching" && (
          <button
            className="btn-primary"
            onClick={handleLetsPractice}
            disabled={busy}
          >
            Let's Practice
          </button>
        )}
        {phase === "summary" && (
          <button onClick={handleFinishLesson} disabled={busy}>
            Finish Lesson
          </button>
        )}
        {phase === "completed" && (
          <button onClick={() => navigate(`/lesson/${id}/summary`)}>
            View Summary
          </button>
        )}
        {phase === "practice_summary" && (
          <button onClick={() => navigate(`/lesson/${id}/practice/summary`)}>
            View Practice Results
          </button>
        )}
      </div>
    </div>
  );
}
