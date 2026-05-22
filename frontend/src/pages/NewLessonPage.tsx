import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createSession } from "../api/sessions";
import type { Subject } from "../types";

export function NewLessonPage() {
  const navigate = useNavigate();
  const [subject, setSubject] = useState<Subject>("math");
  const [topic, setTopic] = useState("");
  const [goal, setGoal] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const session = await createSession({ subject, topic, goal_text: goal });
      navigate(`/lesson/${session.id}`);
    } catch {
      setError("Could not start the lesson. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="new-lesson-page">
      <form className="new-lesson-form" onSubmit={handleSubmit}>
        <div className="new-lesson-brand">Mentora</div>
        <h2 className="new-lesson-title">Start a new lesson</h2>
        <p className="new-lesson-subtitle">
          Tell the tutor what you want to learn today.
        </p>

        {error && <p className="error">{error}</p>}

        <label className="new-lesson-label">
          Subject
          <select
            value={subject}
            onChange={(e) => setSubject(e.target.value as Subject)}
          >
            <option value="math">Math</option>
            <option value="english">English</option>
          </select>
        </label>

        <label className="new-lesson-label">
          Topic
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. Adding fractions"
            required
          />
        </label>

        <label className="new-lesson-label">
          What do you want to learn?
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="e.g. I want to be able to add fractions with different denominators"
            required
          />
        </label>

        <button className="new-lesson-submit" type="submit" disabled={busy}>
          {busy ? "Starting lesson…" : "Start lesson"}
        </button>
      </form>
    </div>
  );
}
