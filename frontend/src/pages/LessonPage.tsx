import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getMessages, getSession } from "../api/sessions";
import { advancePhase, sendVoiceTurn, speakTutorMessage, streamTurn } from "../api/tutor";
import { ChatWindow } from "../components/ChatWindow";
import { LearningPathSidebar } from "../components/LearningPathSidebar";
import { TeacherAvatar } from "../components/TeacherAvatar";
import type { AvatarState } from "../components/TeacherAvatar";
import type { LessonPhase, Message, Session } from "../types";

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
};

export function LessonPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();

  const [session, setSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [avatarState, setAvatarState] = useState<AvatarState>("idle");

  // ---- voice interaction state (thin layer over the existing chat) ----
  const [recording, setRecording] = useState(false);
  const [voicePlayback, setVoicePlayback] = useState(true);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);

  const reload = useCallback(async () => {
    const [s, m] = await Promise.all([getSession(id), getMessages(id)]);
    setSession(s);
    setMessages(m);
  }, [id]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Release the microphone if the user leaves the page mid-recording.
  useEffect(() => {
    return () => {
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
      audioElRef.current?.pause();
    };
  }, []);

  const playTutorAudio = useCallback((audioBase64: string) => {
    // Stop any previous TTS audio before starting a new one.
    // Clear onended first so the stale callback can't fire after pause() and
    // incorrectly reset the avatar state while the new clip is starting.
    if (audioElRef.current) {
      audioElRef.current.onended = null;
      audioElRef.current.pause();
    }
    const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
    audioElRef.current = audio;
    audio.onended = () => setAvatarState("idle");
    // Autoplay can be rejected by the browser; the text reply is already shown,
    // so a failed playback is non-fatal.
    setAvatarState("speaking");
    audio.play().catch(() => {
      setAvatarState("idle");
      setVoiceError("Tap to enable sound — autoplay was blocked by the browser.");
    });
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;
      setBusy(true);
      setAvatarState("thinking");

      const studentId = -Date.now();
      const tutorId = studentId - 1;
      setMessages((prev) => [
        ...prev,
        { id: studentId, session_id: id, role: "student", content: trimmed, created_at: null },
        { id: tutorId, session_id: id, role: "tutor", content: "", created_at: null },
      ]);
      setDraft("");

      try {
        let fullReply = "";
        await streamTurn(id, trimmed, (delta) => {
          fullReply += delta;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === tutorId ? { ...m, content: m.content + delta } : m
            )
          );
        });

        // Speak every tutor reply when voice playback is on, not just voice turns.
        let ttsPlaying = false;
        if (voicePlayback && fullReply.trim()) {
          try {
            const audio = await speakTutorMessage(id, fullReply.trim());
            if (audio) {
              playTutorAudio(audio); // sets avatarState → "speaking" then "idle"
              ttsPlaying = true;
            }
          } catch {
            // TTS failure is non-fatal — text is already visible in the chat.
          }
        }
        // If no TTS was started, return avatar to idle now.
        if (!ttsPlaying) setAvatarState("idle");
      } catch {
        setAvatarState("idle");
        await reload();
      } finally {
        setBusy(false);
      }
    },
    [busy, id, reload, voicePlayback, playTutorAudio]
  );

  // Called once the recorder has stopped and we have the audio blob.
  const submitVoice = useCallback(
    async (audioBlob: Blob) => {
      setBusy(true);
      setAvatarState("thinking");
      try {
        const result = await sendVoiceTurn(id, audioBlob);
        const studentId = -Date.now();
        const tutorId = studentId - 1;
        // Message order: student transcript first, then the tutor reply.
        setMessages((prev) => [
          ...prev,
          { id: studentId, session_id: id, role: "student", content: result.student_text, created_at: null },
          { id: tutorId, session_id: id, role: "tutor", content: result.tutor_message, created_at: null },
        ]);
        if (result.audio_base64 && voicePlayback) {
          playTutorAudio(result.audio_base64); // sets avatarState → "speaking" then "idle"
        } else {
          setAvatarState("idle");
        }
      } catch (err: unknown) {
        setAvatarState("idle");
        const resp = (err as {
          response?: { status?: number; data?: { detail?: string } };
        })?.response;
        // Log the real reason (e.g. an OpenAI model-access error) for debugging;
        // keep the on-screen message child-friendly.
        console.error("voice-turn failed:", resp?.status, resp?.data?.detail ?? err);
        setVoiceError(
          resp?.status === 422
            ? "I couldn't understand that. Please try speaking again."
            : "Voice message failed. Please try again."
        );
      } finally {
        setBusy(false);
      }
    },
    [id, voicePlayback, playTutorAudio]
  );

  const startRecording = useCallback(async () => {
    setVoiceError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setVoiceError("Microphone access was denied. Please allow it to use voice.");
      return;
    }
    mediaStreamRef.current = stream;
    audioChunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      // Always release the mic tracks once recording stops.
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
      const blob = new Blob(audioChunksRef.current, {
        type: recorder.mimeType || "audio/webm",
      });
      if (blob.size > 0) submitVoice(blob);
    };
    mediaRecorderRef.current = recorder;
    recorder.start();
    setRecording(true);
  }, [submitVoice]);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }, []);

  const toggleRecording = useCallback(() => {
    if (recording) stopRecording();
    else startRecording();
  }, [recording, startRecording, stopRecording]);

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
  const canChat = phase === "teaching" || phase === "summary";
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

        {isTeaching && (
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
          <>
            <div className="voice-bar">
              <label className="voice-toggle">
                <input
                  type="checkbox"
                  checked={voicePlayback}
                  onChange={(e) => setVoicePlayback(e.target.checked)}
                />
                <span className="material-symbols-outlined">
                  {voicePlayback ? "volume_up" : "volume_off"}
                </span>
                Tutor voice
              </label>
              {recording && (
                <span className="voice-status recording">
                  <span className="rec-dot" />
                  Recording… click the mic to stop
                </span>
              )}
              {voiceError && <span className="voice-status error">{voiceError}</span>}
            </div>

            <form
              className="chat-input-bar"
              onSubmit={(e) => {
                e.preventDefault();
                sendMessage(draft);
              }}
            >
              <span className="material-symbols-outlined chat-add">add_circle</span>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Type your message here…"
                disabled={busy || recording}
              />
              <button
                type="button"
                className={`mic-button pressable-button${recording ? " recording" : ""}`}
                onClick={toggleRecording}
                disabled={busy}
                aria-label={recording ? "Stop recording" : "Start voice message"}
                title={recording ? "Stop recording" : "Start voice message"}
              >
                <span className="material-symbols-outlined">
                  {recording ? "stop" : "mic"}
                </span>
              </button>
              <button
                type="submit"
                className="primary-button pressable-button chat-send"
                disabled={busy || recording || !draft.trim()}
              >
                Send
                <span className="material-symbols-outlined">send</span>
              </button>
            </form>
          </>
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
