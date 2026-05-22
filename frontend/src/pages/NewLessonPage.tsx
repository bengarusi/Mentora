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
      const session = await createSession({
        subject,
        topic,
        goal_text: goal,
      });
      navigate(`/lesson/${session.id}`);
    } catch {
      setError("Could not start the lesson. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container">
      <form className="card form" onSubmit={handleSubmit}>
        <h2>Start a new lesson</h2>
        {error && <p className="error">{error}</p>}
        <label>
          Subject
          <select
            value={subject}
            onChange={(e) => setSubject(e.target.value as Subject)}
          >
            <option value="math">Math</option>
            <option value="english">English</option>
          </select>
        </label>
        <label>
          Topic
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. Fractions"
            required
          />
        </label>
        <label>
          Goal for this lesson
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="e.g. I want to be able to add fractions"
            required
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Starting…" : "Start lesson"}
        </button>
      </form>
    </div>
  );
}
