import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getMessages, getSession } from "../api/sessions";
import { advancePhase, sendVoiceTurn, streamSpeechTurn, streamTurn } from "../api/tutor";
import { ChatWindow } from "../components/ChatWindow";
import { LearningPathSidebar } from "../components/LearningPathSidebar";
import { TeacherAvatar } from "../components/TeacherAvatar";
import type { AvatarState } from "../components/TeacherAvatar";
import type { LessonPhase, Message, Session } from "../types";

// Temporary latency instrumentation. Flip to true to log time-to-first-text /
// time-to-first-audio in the browser console; keep false in normal use.
const SPEECH_DEBUG = false;
const debugTime = (label: string) => {
  if (SPEECH_DEBUG) console.debug(`[speech] ${label} @ ${performance.now().toFixed(1)}ms`);
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

  // ---- low-latency speech-stream playback state ----
  const streamAbortRef = useRef<AbortController | null>(null);
  const audioQueueRef = useRef<string[]>([]); // blob URLs, ready to play in order
  const chunkBytesRef = useRef<Map<number, Uint8Array[]>>(new Map()); // bytes per chunk_id
  const readyChunksRef = useRef<Map<number, string>>(new Map()); // completed URLs awaiting release
  const nextChunkRef = useRef(1); // next chunk_id eligible to enqueue
  const isPlayingRef = useRef(false);
  const streamDoneRef = useRef(false);
  const turnGenRef = useRef(0); // generation token; bumping it invalidates stale callbacks
  const playNextRef = useRef<() => void>(() => {});
  const autoplayBlockedRef = useRef(false); // set if the browser rejects play()

  const reload = useCallback(async () => {
    const [s, m] = await Promise.all([getSession(id), getMessages(id)]);
    setSession(s);
    setMessages(m);
  }, [id]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Full teardown on unmount so nothing keeps running or leaks after the user
  // leaves the page (mid-recording, mid-stream, or mid-playback).
  useEffect(() => {
    return () => {
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop()); // release mic
      streamAbortRef.current?.abort(); // abort active speech stream
      if (audioElRef.current) {
        audioElRef.current.onended = null; // clear onended
        audioElRef.current.pause(); // pause current audio
      }
      audioQueueRef.current.forEach((u) => URL.revokeObjectURL(u)); // revoke queued URLs
      audioQueueRef.current = [];
      readyChunksRef.current.forEach((u) => URL.revokeObjectURL(u)); // revoke buffered URLs
      readyChunksRef.current.clear();
      chunkBytesRef.current.clear(); // clear chunk byte buffers
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

  // Play the next queued speech-stream chunk on the per-turn audio element.
  // Recurses via playNextRef so the same stable callback can chain onended.
  const playNext = useCallback(() => {
    const audio = audioElRef.current;
    if (!audio) return;
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      // Nothing left to play and the stream is over → return to idle.
      if (streamDoneRef.current && readyChunksRef.current.size === 0) {
        debugTime("audio_queue_empty");
        setAvatarState("idle");
      }
      return;
    }
    const gen = turnGenRef.current;
    const url = audioQueueRef.current.shift()!;
    isPlayingRef.current = true;
    audio.src = url;
    setAvatarState("speaking");
    audio.onended = () => {
      if (gen !== turnGenRef.current) return; // stale after barge-in
      URL.revokeObjectURL(url);
      playNextRef.current();
    };
    audio.play().catch(() => {
      if (gen !== turnGenRef.current) return;
      // Autoplay blocked / playback failed: stop trying for this turn, drop any
      // buffered audio (we can't play it), and return to idle. The text reply is
      // already visible and the text stream keeps going independently.
      autoplayBlockedRef.current = true;
      URL.revokeObjectURL(url);
      audioQueueRef.current.forEach((u) => URL.revokeObjectURL(u));
      audioQueueRef.current = [];
      readyChunksRef.current.forEach((u) => URL.revokeObjectURL(u));
      readyChunksRef.current.clear();
      chunkBytesRef.current.clear();
      isPlayingRef.current = false;
      setAvatarState("idle");
      setVoiceError("Tap to enable sound — autoplay was blocked by the browser.");
    });
  }, []);
  playNextRef.current = playNext;

  // Barge-in: abort the active speech stream, stop + clear all audio, and bump
  // the generation token so stale onended/handlers from the old turn no-op.
  const stopSpeechAndAudio = useCallback(() => {
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    turnGenRef.current += 1;
    if (audioElRef.current) {
      audioElRef.current.onended = null;
      audioElRef.current.pause();
    }
    audioQueueRef.current.forEach((u) => URL.revokeObjectURL(u));
    audioQueueRef.current = [];
    readyChunksRef.current.forEach((u) => URL.revokeObjectURL(u));
    readyChunksRef.current.clear();
    chunkBytesRef.current.clear();
    nextChunkRef.current = 1;
    isPlayingRef.current = false;
    autoplayBlockedRef.current = false; // a fresh turn may retry playback
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;

      // Barge-in: stop any in-flight stream/audio before starting a new turn.
      stopSpeechAndAudio();

      setBusy(true);
      setAvatarState("thinking");
      debugTime("message_sent");

      const studentId = -Date.now();
      const tutorId = studentId - 1;
      setMessages((prev) => [
        ...prev,
        { id: studentId, session_id: id, role: "student", content: trimmed, created_at: null },
        { id: tutorId, session_id: id, role: "tutor", content: "", created_at: null },
      ]);
      setDraft("");

      const appendTutor = (delta: string) =>
        setMessages((prev) =>
          prev.map((m) =>
            m.id === tutorId ? { ...m, content: m.content + delta } : m
          )
        );

      // New turn generation; reset per-turn playback state.
      const gen = ++turnGenRef.current;
      streamDoneRef.current = false;
      nextChunkRef.current = 1;

      if (voicePlayback) {
        // One audio element per turn, created up front and reused across chunks
        // (src is swapped) so the lip-sync analyser stays attached the whole turn.
        audioElRef.current = new Audio();
        const controller = new AbortController();
        streamAbortRef.current = controller;
        let firstText = false;
        let firstAudio = false;
        try {
          await streamSpeechTurn(
            id,
            trimmed,
            {
              onTextDelta: (delta) => {
                if (gen !== turnGenRef.current) return;
                if (!firstText) { firstText = true; debugTime("first_text_delta_received"); }
                appendTutor(delta);
              },
              onAudioChunk: (chunkId, bytes) => {
                if (gen !== turnGenRef.current || autoplayBlockedRef.current) return;
                if (!firstAudio) { firstAudio = true; debugTime("first_audio_delta_received"); }
                const arr = chunkBytesRef.current.get(chunkId) ?? [];
                arr.push(bytes);
                chunkBytesRef.current.set(chunkId, arr);
              },
              onAudioEnd: (chunkId) => {
                if (gen !== turnGenRef.current || autoplayBlockedRef.current) return;
                const parts = chunkBytesRef.current.get(chunkId) ?? [];
                chunkBytesRef.current.delete(chunkId);
                if (parts.length === 0) return;
                const blob = new Blob(parts as BlobPart[], { type: "audio/mpeg" });
                readyChunksRef.current.set(chunkId, URL.createObjectURL(blob));
                debugTime("first_audio_chunk_completed");
                // Release now-contiguous chunks into the play queue, in id order.
                while (readyChunksRef.current.has(nextChunkRef.current)) {
                  const u = readyChunksRef.current.get(nextChunkRef.current)!;
                  readyChunksRef.current.delete(nextChunkRef.current);
                  audioQueueRef.current.push(u);
                  nextChunkRef.current += 1;
                }
                if (!isPlayingRef.current) {
                  debugTime("first_audio_play_requested");
                  playNextRef.current();
                }
              },
              onDone: () => {
                if (gen !== turnGenRef.current) return;
                streamDoneRef.current = true;
                debugTime("stream_done");
                // Stream finished with no audio left to play → idle now.
                if (
                  !isPlayingRef.current &&
                  audioQueueRef.current.length === 0 &&
                  readyChunksRef.current.size === 0
                ) {
                  setAvatarState("idle");
                }
              },
              onError: () => {
                if (gen !== turnGenRef.current) return;
                setAvatarState("idle"); // text is already visible; just stop spinning
              },
            },
            controller.signal
          );
        } catch (err) {
          // AbortError from barge-in is expected; anything else → recover.
          if ((err as Error)?.name !== "AbortError" && gen === turnGenRef.current) {
            setAvatarState("idle");
            await reload();
          }
        } finally {
          if (gen === turnGenRef.current) setBusy(false);
        }
      } else {
        // Voice off: cheap text-only stream, no TTS cost.
        try {
          await streamTurn(id, trimmed, (delta) => {
            if (gen !== turnGenRef.current) return;
            appendTutor(delta);
          });
          if (gen === turnGenRef.current) setAvatarState("idle");
        } catch {
          if (gen === turnGenRef.current) {
            setAvatarState("idle");
            await reload();
          }
        } finally {
          if (gen === turnGenRef.current) setBusy(false);
        }
      }
    },
    [busy, id, reload, voicePlayback, stopSpeechAndAudio]
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
    // Starting to record is a barge-in: cut off the tutor's current speech.
    stopSpeechAndAudio();
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
  }, [submitVoice, stopSpeechAndAudio]);

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
