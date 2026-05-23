import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { getMessages } from "../api/sessions";
import { startPractice } from "../api/tutor";
import { LearningPathSidebar } from "../components/LearningPathSidebar";
import { RichText } from "../components/RichText";

export function PrePracticeExamplePage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();
  const location = useLocation();

  // Prefer the explicit example produced by advancePhase (passed via nav state).
  // Only if that's missing (e.g. a page refresh) do we fall back to the last
  // tutor message — and we label that fallback honestly as a review, since it
  // isn't guaranteed to be a fully solved example.
  const stateExample =
    (location.state as { exampleContent?: string })?.exampleContent ?? "";
  const [exampleContent, setExampleContent] = useState<string>(stateExample);
  const [isFallback, setIsFallback] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadFallback = useCallback(async () => {
    if (exampleContent) return;
    const messages = await getMessages(id);
    const tutorMessages = messages.filter((m) => m.role === "tutor");
    if (tutorMessages.length > 0) {
      setExampleContent(tutorMessages[tutorMessages.length - 1].content);
      setIsFallback(true);
    }
  }, [id, exampleContent]);

  useEffect(() => {
    loadFallback();
  }, [loadFallback]);

  async function handleStartPractice() {
    setBusy(true);
    setError(null);
    try {
      const result = await startPractice(id);
      navigate(`/lesson/${id}/practice`, { state: { initialSet: result } });
    } catch {
      setError("Couldn't load your practice questions yet. Let's try again.");
      setBusy(false);
    }
  }

  return (
    <div className="lesson-layout no-right">
      <LearningPathSidebar active="practice" />

      <section className="practice-main">
        <div className="practice-inner">
          <div className="page-header">
            <h1>{isFallback ? "Review before practice" : "Before You Practice"}</h1>
            <p className="muted">
              {isFallback
                ? "Take another look at what you learned, then jump into practice."
                : "Here's a worked example to get you ready. Read it through, then start practicing."}
            </p>
          </div>

          {error && <p className="error">{error}</p>}

          <div className="surface-card">
            {exampleContent ? (
              <RichText content={exampleContent} />
            ) : (
              <p className="muted">Loading example…</p>
            )}
          </div>

          <div className="page-footer-actions">
            <button
              className="primary-button pressable-button"
              onClick={handleStartPractice}
              disabled={busy || !exampleContent}
            >
              {busy ? "Loading questions…" : "Start Practice"}
              {!busy && <span className="material-symbols-outlined">arrow_forward</span>}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
