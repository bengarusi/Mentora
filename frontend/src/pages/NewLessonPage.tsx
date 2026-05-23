import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { MATH_CURRICULUM } from "../data/mathCurriculum";

export function NewLessonPage() {
  const navigate = useNavigate();
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);

  function startLesson() {
    if (!selectedTopic) return;
    navigate(`/topic/${selectedTopic}`);
  }

  return (
    <div className="page-start">
      <section className="start-hero">
        <div className="start-hero-text">
          <h1 className="start-headline">What would you like to learn today?</h1>
          <p className="start-subtitle">
            Every master was once a beginner. Pick a topic and let&apos;s start!
          </p>
        </div>
        <div className="start-hero-visual" aria-hidden="true">
          <span className="material-symbols-outlined">school</span>
        </div>
      </section>

      <p className="section-label">Primary Subjects</p>
      <div className="subject-row">
        <div className="subject-card is-active">
          <span className="material-symbols-outlined">calculate</span>
          Math
        </div>
        <span className="subject-note">More subjects coming later</span>
      </div>

      <p className="section-label">Math Topics</p>
      <div className="topic-grid">
        {MATH_CURRICULUM.map((topic) => {
          const selected = topic.id === selectedTopic;
          return (
            <button
              key={topic.id}
              type="button"
              className={`topic-card pressable-button${selected ? " selected" : ""}`}
              aria-pressed={selected}
              onClick={() => setSelectedTopic(topic.id)}
            >
              <span className="topic-card-icon">
                <span className="material-symbols-outlined">{topic.icon}</span>
              </span>
              <span className="topic-card-title">{topic.title}</span>
              <span className="topic-card-desc">{topic.description}</span>
            </button>
          );
        })}
      </div>

      <div className="start-banner">
        <div className="start-banner-text">
          <h3>Ready to learn?</h3>
          <p>Pick a topic above, then choose exactly what you want to practice.</p>
        </div>
        <button
          type="button"
          className="primary-button pressable-button"
          disabled={!selectedTopic}
          onClick={startLesson}
        >
          Start Lesson
          <span className="material-symbols-outlined">rocket_launch</span>
        </button>
      </div>
    </div>
  );
}
