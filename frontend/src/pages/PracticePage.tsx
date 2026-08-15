import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { getSession } from "../api/sessions";
import {
  finishPractice,
  nextPracticeSet,
  startPractice,
  submitPracticeSet,
} from "../api/tutor";
import { BoardButton } from "../components/BoardButton";
import { BoardModal } from "../components/BoardModal";
import { LearningPathSidebar } from "../components/LearningPathSidebar";
import { RichText } from "../components/RichText";
import { useBoardExplanation } from "../hooks/useBoardExplanation";
import type {
  GradedPracticeItem,
  PracticeAnswerItem,
  PracticeQuestion,
  PracticeStartResult,
  Session,
} from "../types";

type SetPhase = "answering" | "graded";

export function PracticePage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();
  const location = useLocation();

  const initialSet =
    (location.state as { initialSet?: PracticeStartResult })?.initialSet ?? null;

  const [questions, setQuestions] = useState<PracticeQuestion[]>(
    initialSet?.questions ?? []
  );
  const [setNumber, setSetNumber] = useState(initialSet?.set_number ?? 1);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [grades, setGrades] = useState<GradedPracticeItem[]>([]);
  const [setPhase, setSetPhase] = useState<SetPhase>("answering");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topicLabel, setTopicLabel] = useState("Practice");
  // Practice has no voice toggle of its own, so follow the preference the
  // student set in the lesson chat.
  const [voicePlayback] = useState(
    () => localStorage.getItem("mentora_tutor_voice") !== "off"
  );

  // Board explanations are opt-in per question and never open on their own.
  const board = useBoardExplanation(id);

  const loadInitialSet = useCallback(async () => {
    if (questions.length > 0) return;
    setBusy(true);
    try {
      const result = await startPractice(id);
      setQuestions(result.questions);
      setSetNumber(result.set_number);
    } catch {
      setError("I couldn't load your practice questions yet. Let's try again.");
    } finally {
      setBusy(false);
    }
  }, [id, questions.length]);

  useEffect(() => {
    loadInitialSet();
  }, [loadInitialSet]);

  useEffect(() => {
    getSession(id)
      .then((s: Session) => setTopicLabel(`${s.subtopic || s.topic} Practice`))
      .catch(() => undefined);
  }, [id]);

  const total = questions.length;
  const currentQ = questions[currentIndex];
  const currentAnswer = currentQ ? answers[currentQ.id] ?? "" : "";
  const allAnswered =
    total > 0 && questions.every((q) => (answers[q.id] ?? "").trim().length > 0);
  const isLast = currentIndex === total - 1;

  function setAnswer(value: string) {
    if (!currentQ) return;
    setAnswers((prev) => ({ ...prev, [currentQ.id]: value }));
  }

  async function handleSubmit() {
    const payload: PracticeAnswerItem[] = questions.map((q) => ({
      question_id: q.id,
      answer: answers[q.id] ?? "",
    }));
    setBusy(true);
    setError(null);
    try {
      const result = await submitPracticeSet(id, payload);
      setGrades(result.grades);
      setSetPhase("graded");
      // A question only becomes reviewable once it has been checked.
      board.refresh();
    } catch {
      setError("I couldn't submit your answers. Let's try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handlePracticeMore() {
    setBusy(true);
    setError(null);
    try {
      const result = await nextPracticeSet(id);
      setQuestions(result.questions);
      setSetNumber(result.set_number);
      setAnswers({});
      setGrades([]);
      setCurrentIndex(0);
      setSetPhase("answering");
    } catch {
      setError("I couldn't load the next set. Let's try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleFinishPractice() {
    setBusy(true);
    try {
      await finishPractice(id);
      navigate(`/lesson/${id}/practice/summary`);
    } finally {
      setBusy(false);
    }
  }

  const correctCount = grades.filter((g) => g.is_correct).length;
  const progressPct =
    setPhase === "graded" || total === 0
      ? 100
      : ((currentIndex + 1) / total) * 100;

  return (
    <div className="lesson-layout no-right">
      <LearningPathSidebar active="practice" />

      <section className="practice-main">
        <div className="practice-inner">
          <div className="practice-head">
            <span className="practice-step">
              {setPhase === "graded"
                ? `Set ${setNumber} Results`
                : `Question ${Math.min(currentIndex + 1, total || 1)} of ${total || 3}`}
            </span>
            <span className="practice-topic-label">{topicLabel}</span>
          </div>
          <div className="practice-progress-track">
            <span style={{ width: `${progressPct}%` }} />
          </div>

          {error && <p className="error">{error}</p>}

          {setPhase === "answering" && (
            <>
              {!currentQ && <p className="muted">Loading questions…</p>}
              {currentQ && (
                <>
                  <div className="practice-card">
                    <div className="practice-prompt-label">Solve the problem</div>
                    <div className="practice-question">
                      <RichText content={currentQ.question_text} />
                    </div>
                    <input
                      className="answer-input"
                      value={currentAnswer}
                      onChange={(e) => setAnswer(e.target.value)}
                      placeholder="Type your answer"
                      disabled={busy}
                      autoFocus
                    />
                    {isLast ? (
                      <button
                        className="primary-button pressable-button"
                        onClick={handleSubmit}
                        disabled={busy || !allAnswered}
                      >
                        {busy ? "Grading…" : "Submit Answers"}
                        {!busy && (
                          <span className="material-symbols-outlined">check</span>
                        )}
                      </button>
                    ) : (
                      <button
                        className="primary-button pressable-button"
                        onClick={() => setCurrentIndex((i) => i + 1)}
                        disabled={!currentAnswer.trim()}
                      >
                        Next
                        <span className="material-symbols-outlined">arrow_forward</span>
                      </button>
                    )}
                  </div>

                  <div className="practice-nav">
                    <button
                      className="ghost-button pressable-button"
                      onClick={() => setCurrentIndex((i) => Math.max(0, i - 1))}
                      disabled={currentIndex === 0 || busy}
                    >
                      <span className="material-symbols-outlined">arrow_back</span>
                      Back
                    </button>
                    {!allAnswered && (
                      <span className="muted" style={{ alignSelf: "center" }}>
                        Answer all {total} questions to submit
                      </span>
                    )}
                  </div>

                  <div className="practice-hint">
                    <span className="material-symbols-outlined">lightbulb</span>
                    <p>
                      Take it one step at a time. Write what you know first, then
                      work toward the answer.
                    </p>
                  </div>
                </>
              )}
            </>
          )}

          {setPhase === "graded" && (
            <>
              <div className="result-summary">
                <div className="result-score">
                  {correctCount} / {grades.length}
                </div>
                <p className="muted">questions correct this round</p>
              </div>

              {grades.map((g, idx) => (
                <div
                  key={g.question_id}
                  className={`result-card ${g.is_correct ? "correct" : "incorrect"}`}
                >
                  <div className="result-card-head">
                    <strong>Question {idx + 1}</strong>
                    <span
                      className={`result-tag ${g.is_correct ? "correct" : "incorrect"}`}
                    >
                      <span className="material-symbols-outlined">
                        {g.is_correct ? "check_circle" : "cancel"}
                      </span>
                      {g.is_correct ? "Correct" : "Incorrect"}
                    </span>
                  </div>
                  <div className="practice-question" style={{ fontSize: "1.05rem", textAlign: "left", marginBottom: "0.5rem" }}>
                    <RichText content={g.question_text} />
                  </div>
                  <p className="result-answer">Your answer: {g.student_answer || "—"}</p>
                  {!g.is_correct && g.correct_answer && (
                    <p className="result-answer">Correct answer: {g.correct_answer}</p>
                  )}
                  {g.feedback && <RichText content={g.feedback} />}
                  {board.enabled && (
                    <div className="board-action-row">
                      <BoardButton
                        hasBoard={board.boardForQuestion(g.question_id) !== null}
                        generating={
                          board.open?.anchor === `question:${g.question_id}` &&
                          board.open.phase === "generating"
                        }
                        disabled={busy}
                        onClick={() => board.reviewQuestion(g.question_id)}
                      />
                    </div>
                  )}
                </div>
              ))}

              <div className="page-footer-actions" style={{ justifyContent: "space-between" }}>
                <button
                  className="ghost-button pressable-button"
                  onClick={() => navigate(`/lesson/${id}`)}
                  disabled={busy}
                >
                  Back to Chat
                </button>
                <div style={{ display: "flex", gap: "0.75rem" }}>
                  <button
                    className="secondary-button pressable-button"
                    onClick={handlePracticeMore}
                    disabled={busy}
                  >
                    Practice More
                  </button>
                  <button
                    className="primary-button pressable-button"
                    onClick={handleFinishPractice}
                    disabled={busy}
                  >
                    Finish Practice
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </section>

      {/* Lives outside the practice card so closing it returns the student to
          exactly the question and typed answer they left. */}
      <BoardModal
        open={board.open !== null}
        phase={board.open?.phase ?? "generating"}
        board={board.open?.board ?? null}
        sessionId={id}
        voice={voicePlayback}
        onClose={board.close}
        onRetry={board.retry}
      />
    </div>
  );
}
