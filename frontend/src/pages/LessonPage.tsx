import { useCallback, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { advancePhase, setLessonDifficulty } from "../api/tutor";
import { ChatComposer } from "../components/ChatComposer";
import { ChatWindow } from "../components/ChatWindow";
import { LearningPathSidebar } from "../components/LearningPathSidebar";
import { TeacherAvatar } from "../components/TeacherAvatar";
import { useTutorChat } from "../hooks/useTutorChat";
import type { DifficultyLevel, LessonPhase } from "../types";

const NEXT_DIFFICULTY: Record<DifficultyLevel, DifficultyLevel | null> = {
  easy: "medium",
  medium: "hard",
  hard: null,
};

const DIFFICULTY_LABEL: Record<DifficultyLevel, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

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
  // Homework Help never renders in this page's progress panel (it has its own
  // route), but the map must stay exhaustive over LessonPhase.
  homework_help: "Homework Help",
};

export function LessonPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();

  // The conversation engine (history, streaming, voice, barge-in) is shared
  // with Homework Help; this page adds only the lesson's phase controls.
  const {
    session,
    reload,
    messages,
    draft,
    setDraft,
    busy,
    setBusy,
    setAvatarState,
    avatarState,
    recording,
    voicePlayback,
    voiceError,
    audioElRef,
    sendMessage,
    toggleRecording,
    handleVoicePlaybackToggle,
  } = useTutorChat(id);

  // A Homework Help session has no phase ladder, so the lesson UI can't drive
  // it — send it to its own page rather than rendering a dead screen.
  useEffect(() => {
    if (session?.mode === "homework") {
      navigate(`/homework/${id}`, { replace: true });
    }
  }, [session?.mode, id, navigate]);

  const handlePickDifficulty = useCallback(
    async (level: DifficultyLevel) => {
      setBusy(true);
      setAvatarState("thinking");
      try {
        await setLessonDifficulty(id, level);
        await reload();
        setAvatarState("idle");
      } catch {
        setAvatarState("idle");
      } finally {
        setBusy(false);
      }
    },
    [id, reload]
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
  const pickingDifficulty = isTeaching && !session.difficulty;
  const canChat = (isTeaching && !pickingDifficulty) || phase === "summary";
  const nextDifficulty = session.difficulty ? NEXT_DIFFICULTY[session.difficulty] : null;
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

        {isTeaching && pickingDifficulty && (
          <div className="quick-actions">
            {(Object.keys(DIFFICULTY_LABEL) as DifficultyLevel[]).map((level) => (
              <button
                key={level}
                type="button"
                className="pill-button pressable-button"
                onClick={() => handlePickDifficulty(level)}
                disabled={busy}
              >
                {DIFFICULTY_LABEL[level]}
              </button>
            ))}
          </div>
        )}

        {isTeaching && !pickingDifficulty && (
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
            {nextDifficulty && (
              <button
                type="button"
                className="pill-button pressable-button"
                onClick={() => handlePickDifficulty(nextDifficulty)}
                disabled={busy}
              >
                Increase difficulty
              </button>
            )}
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
          <ChatComposer
            draft={draft}
            onDraftChange={setDraft}
            onSend={sendMessage}
            busy={busy}
            recording={recording}
            onToggleRecording={toggleRecording}
            voicePlayback={voicePlayback}
            onVoicePlaybackChange={handleVoicePlaybackToggle}
            voiceError={voiceError}
          />
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
        <div className="teacher-avatar-section">
          <TeacherAvatar state={avatarState} audioElementRef={audioElRef} />
        </div>

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
          {session.difficulty && (
            <div className="context-row">
              <span className="material-symbols-outlined">speed</span>
              <div>
                <div className="context-row-label">Difficulty</div>
                <div className="context-row-value">
                  {DIFFICULTY_LABEL[session.difficulty]}
                </div>
              </div>
            </div>
          )}
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

      </aside>
    </div>
  );
}
