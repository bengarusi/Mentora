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

  async function handleAdvance(thenSummary = false) {
    setBusy(true);
    try {
      await advancePhase(id);
      if (thenSummary) {
        navigate(`/lesson/${id}/summary`);
      } else {
        await reload();
      }
    } finally {
      setBusy(false);
    }
  }

  if (!session) {
    return <div className="container">Loading lesson…</div>;
  }

  const phase = session.phase;
  const canChat =
    phase === "explanation" ||
    phase === "example" ||
    phase === "correction" ||
    phase === "level_adjustment";

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
        {phase === "explanation" && (
          <button onClick={() => handleAdvance()} disabled={busy}>
            Continue to example
          </button>
        )}
        {phase === "example" && (
          <button onClick={() => navigate(`/lesson/${id}/assessment`)} disabled={busy}>
            Start assessment
          </button>
        )}
        {phase === "assessment" && (
          <button onClick={() => navigate(`/lesson/${id}/assessment`)}>
            Go to assessment
          </button>
        )}
        {phase === "correction" && (
          <button onClick={() => handleAdvance()} disabled={busy}>
            Continue
          </button>
        )}
        {phase === "level_adjustment" && (
          <button onClick={() => handleAdvance(true)} disabled={busy}>
            Finish lesson
          </button>
        )}
        {phase === "completed" && (
          <button onClick={() => navigate(`/lesson/${id}/summary`)}>
            View summary
          </button>
        )}
      </div>
    </div>
  );
}
