import { useCallback, useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { advancePhase, setLessonDifficulty } from "../api/tutor";
import { BoardModal } from "../components/BoardModal";
import { ChatComposer } from "../components/ChatComposer";
import { ChatWindow } from "../components/ChatWindow";
import { LearningPathSidebar } from "../components/LearningPathSidebar";
import { TeacherAvatar } from "../components/TeacherAvatar";
import { useBoardExplanation } from "../hooks/useBoardExplanation";
import { useTutorChat } from "../hooks/useTutorChat";
import type { DifficultyLevel, LessonPhase, Message } from "../types";

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
    speakTutorReply,
  } = useTutorChat(id);

  const board = useBoardExplanation(id);
  const introAttemptedRef = useRef(false);

  // The lesson opens on the board: once the student has picked a difficulty and
  // the tutor has said something, the explanation is delivered as a narrated
  // board rather than only as a wall of text. Guarded so it happens once per
  // lesson — on a later visit the board already exists and is replayed from the
  // card in the transcript instead of ambushing the student again.
  const lessonIntroBoard = board.summaries.find((b) => b.kind === "lesson_intro");
  useEffect(() => {
    if (!board.enabled || introAttemptedRef.current) return;
    if (session?.phase !== "teaching" || !session.difficulty) return;
    if (lessonIntroBoard || messages.length === 0) return;
    introAttemptedRef.current = true;
    board.teachOnBoard();
  }, [board, session?.phase, session?.difficulty, lessonIntroBoard, messages.length]);

  /** Ask for a board about whatever the lesson is on right now.
   *
   * The focus is the tail of the conversation rather than the student's last
   * message: when the tutor has just asked "what is 3 times 4?" the student
   * presses this without replying, so their last message is unrelated — that
   * mistake made the board re-teach the topic instead of the question. */
  const handleExplainOnBoard = useCallback(() => {
    const recent = messages
      .filter((m) => m.content.trim())
      .slice(-3)
      .map((m) => `${m.role === "tutor" ? "Tutor" : "Student"}: ${m.content}`)
      .join("\n");
    board.teachOnBoard(recent || "explain this part of the lesson on the board");
  }, [board, messages]);

  /** The replay card under a tutor turn that has a board. */
  const boardCardFor = useCallback(
    (message: Message) => {
      const summary = board.boardForMessage(message.id);
      if (!summary) return null;
      return (
        <button
          type="button"
          className="board-card"
          onClick={() => board.replayBoard(summary.id)}
        >
          <span className="material-symbols-outlined" aria-hidden="true">
            draw
          </span>
          <span>
            <span className="board-card-title">{summary.title}</span>
            <br />
            <span className="board-card-hint">Watch it on the board again</span>
          </span>
        </button>
      );
    },
    [board]
  );

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
      let startedSpeaking = false;
      try {
        const result = await setLessonDifficulty(id, level);
        await reload();
        // When the board feature is active, its narration owns this opening;
        // otherwise this complete (non-streaming) tutor reply needs explicit TTS.
        if (!board.enabled) {
          startedSpeaking = await speakTutorReply(result.tutor_message);
        }
      } catch {
        setAvatarState("idle");
      } finally {
        if (!startedSpeaking) setAvatarState("idle");
        setBusy(false);
      }
    },
    [board.enabled, id, reload, speakTutorReply]
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
        <ChatWindow messages={messages} footerFor={boardCardFor} />

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
            {board.enabled && (
              <button
                type="button"
                className="pill-button pressable-button"
                onClick={handleExplainOnBoard}
                disabled={busy}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  draw
                </span>
                Explain on board
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
          <div className="context-row-label">
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
