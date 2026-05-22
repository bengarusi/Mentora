import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { getMessages } from "../api/sessions";
import { startPractice } from "../api/tutor";
import { RichText } from "../components/RichText";

export function PrePracticeExamplePage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();
  const location = useLocation();

  // The example content may be passed via navigation state (from LessonPage advance call).
  // If not (e.g., page refresh), we fall back to fetching the last tutor message.
  const [exampleContent, setExampleContent] = useState<string>(
    (location.state as { exampleContent?: string })?.exampleContent ?? ""
  );
  const [busy, setBusy] = useState(false);

  const loadFallback = useCallback(async () => {
    if (exampleContent) return;
    const messages = await getMessages(id);
    const tutorMessages = messages.filter((m) => m.role === "tutor");
    if (tutorMessages.length > 0) {
      setExampleContent(tutorMessages[tutorMessages.length - 1].content);
    }
  }, [id, exampleContent]);

  useEffect(() => {
    loadFallback();
  }, [loadFallback]);

  async function handleStartPractice() {
    setBusy(true);
    try {
      const result = await startPractice(id);
      navigate(`/lesson/${id}/practice`, {
        state: { initialSet: result },
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container">
      <h2>Before You Practice</h2>
      <p className="muted">
        Here is a fully solved example to help you prepare. Read through it
        carefully before starting the practice questions.
      </p>

      <div className="card pre-practice-example">
        {exampleContent ? (
          <div className="example-content">
            <RichText content={exampleContent} />
          </div>
        ) : (
          <p className="muted">Loading example…</p>
        )}
      </div>

      <div className="lesson-actions">
        <button
          className="btn-primary"
          onClick={handleStartPractice}
          disabled={busy || !exampleContent}
        >
          {busy ? "Loading questions…" : "Start Practice"}
        </button>
      </div>
    </div>
  );
}
