import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createSession } from "../api/sessions";
import { getTopicById, type Subtopic } from "../data/mathCurriculum";

export function SubTopicSelectionPage() {
  const navigate = useNavigate();
  const { topicId } = useParams<{ topicId: string }>();
  const topic = getTopicById(topicId);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!topic) {
    return (
      <div className="page-shell">
        <div className="surface-card">
          <h1>We couldn&apos;t find that topic</h1>
          <p className="muted">Let&apos;s head back and pick one together.</p>
          <Link to="/" className="primary-button pressable-button">
            Back to topics
          </Link>
        </div>
      </div>
    );
  }

  const selected = topic.subtopics.find((s) => s.id === selectedId) || null;

  async function startLesson(subtopic: Subtopic) {
    if (!topic) return;
    setError(null);
    setBusy(true);
    try {
      const session = await createSession({
        subject: "math",
        topic: topic.title,
        subtopic: subtopic.title,
        goal_text: subtopic.goal_text,
      });
      navigate(`/lesson/${session.id}`);
    } catch {
      setError("Something went wrong starting your lesson. Let's try again.");
      setBusy(false);
    }
  }

  return (
    <div className="page-shell">
      <div className="page-header">
        <Link to="/" className="back-link">
          <span className="material-symbols-outlined">arrow_back</span>
          All topics
        </Link>
        <h1>{topic.title}</h1>
        <p className="muted">Choose exactly what you&apos;d like to work on.</p>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="subtopic-grid">
        {topic.subtopics.map((sub) => {
          const isSelected = sub.id === selectedId;
          return (
            <button
              key={sub.id}
              type="button"
              className={`subtopic-card pressable-button${isSelected ? " selected" : ""}`}
              aria-pressed={isSelected}
              onClick={() => setSelectedId(sub.id)}
            >
              <div className="subtopic-card-head">
                <span className="subtopic-card-title">{sub.title}</span>
                {sub.difficulty && (
                  <span className={`difficulty-badge ${sub.difficulty}`}>
                    {sub.difficulty}
                  </span>
                )}
              </div>
              <span className="subtopic-card-desc">{sub.description}</span>
              <span className="subtopic-card-goal">
                <span className="material-symbols-outlined">flag</span>
                {sub.goal_text}
              </span>
            </button>
          );
        })}
      </div>

      <div className="page-footer-actions">
        <button
          type="button"
          className="primary-button pressable-button"
          disabled={!selected || busy}
          onClick={() => selected && startLesson(selected)}
        >
          {busy ? "Starting lesson…" : "Start Lesson"}
          {!busy && <span className="material-symbols-outlined">rocket_launch</span>}
        </button>
      </div>
    </div>
  );
}
