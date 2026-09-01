import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  analyzeHomework,
  getSupportedFormats,
  listHomework,
  reprocessMaterial,
  uploadHomework,
} from "../api/materials";
import { ChatComposer } from "../components/ChatComposer";
import { AgentActivity } from "../components/AgentActivity";
import { ChatWindow } from "../components/ChatWindow";
import { FileDropzone } from "../components/FileDropzone";
import { LearningPathSidebar } from "../components/LearningPathSidebar";
import { MaterialCard } from "../components/MaterialCard";
import { TeacherAvatar } from "../components/TeacherAvatar";
import { useTutorChat } from "../hooks/useTutorChat";
import type { StudyMaterial, SupportedFormats } from "../types";

const FALLBACK_FORMATS: SupportedFormats = {
  extensions: [".pdf", ".docx", ".png", ".jpg", ".jpeg", ".webp", ".txt"],
  max_upload_mb: 20,
};

export function HomeworkPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();

  // Same conversation engine as a lesson — streaming, voice, and barge-in all
  // behave identically here; only the surrounding flow differs.
  const {
    session,
    messages,
    reload,
    draft,
    setDraft,
    busy,
    setBusy,
    setAvatarState,
    avatarState,
    toolActivity,
    recording,
    voicePlayback,
    voiceError,
    audioElRef,
    sendMessage,
    toggleRecording,
    handleVoicePlaybackToggle,
    speakTutorReply,
  } = useTutorChat(id);

  const [materials, setMaterials] = useState<StudyMaterial[]>([]);
  const [formats, setFormats] = useState<SupportedFormats>(FALLBACK_FORMATS);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Mirror of the lesson page's guard: a normal lesson belongs in the lesson
  // UI, which has the phase controls this page deliberately lacks.
  useEffect(() => {
    if (session && session.mode !== "homework") {
      navigate(`/lesson/${id}`, { replace: true });
    }
  }, [session, id, navigate]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [rows, supported] = await Promise.all([
          listHomework(id),
          getSupportedFormats().catch(() => FALLBACK_FORMATS),
        ]);
        if (cancelled) return;
        setMaterials(rows);
        setFormats(supported);
      } catch {
        if (!cancelled) setError("We couldn't load this homework session.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  /** Ask the tutor to read what's already uploaded and open the conversation.
   * Separate from upload so a failed analysis (e.g. the tutor service being
   * briefly unavailable) can be retried without re-uploading the file. */
  const runAnalysis = useCallback(async () => {
    setBusy(true);
    setError(null);
    setAvatarState("thinking");
    let startedSpeaking = false;
    try {
      const result = await analyzeHomework(id);
      await reload();
      startedSpeaking = await speakTutorReply(result.tutor_message);
    } catch {
      setError(
        "Your tutor couldn't read the homework just now. Please try again."
      );
    } finally {
      if (!startedSpeaking) setAvatarState("idle");
      setBusy(false);
    }
  }, [id, reload, setAvatarState, setBusy, speakTutorReply]);

  const handleUpload = useCallback(
    async (files: File[]) => {
      const file = files[0];
      if (!file) return;
      setBusy(true);
      setError(null);
      setAvatarState("thinking");
      let uploaded: StudyMaterial;
      try {
        uploaded = await uploadHomework(id, file);
        setMaterials((prev) => [...prev, uploaded]);
      } catch {
        setError("That upload didn't work. Please try again.");
        setAvatarState("idle");
        setBusy(false);
        return;
      }

      if (uploaded.status !== "ready") {
        // Nothing readable came out, so there is no point asking the tutor to
        // analyze it — tell the student what to try instead.
        setError(
          uploaded.status_detail ||
            "We couldn't read that file. Try a clearer photo, or type the question out."
        );
        setAvatarState("idle");
        setBusy(false);
        return;
      }

      setBusy(false);
      await runAnalysis();
    },
    [id, runAnalysis, setAvatarState, setBusy]
  );

  /** Retry extraction on a file that was parked as unsupported/failed — e.g. a
   * server-side dependency wasn't installed yet when it was first uploaded. */
  const handleRetry = useCallback(
    async (material: StudyMaterial) => {
      setBusy(true);
      setError(null);
      try {
        const updated = await reprocessMaterial(material.id);
        setMaterials((prev) =>
          prev.map((m) => (m.id === updated.id ? updated : m))
        );
        if (updated.status === "ready") {
          await runAnalysis();
        } else {
          setError(
            updated.status_detail || "We still couldn't read that file."
          );
        }
      } catch {
        setError("We still couldn't read that file.");
      } finally {
        setBusy(false);
      }
    },
    [runAnalysis]
  );

  const hasReadableHomework = materials.some((m) => m.status === "ready");
  const started = messages.length > 0;

  if (!session && loading) {
    return (
      <div className="lesson-layout no-right">
        <LearningPathSidebar active="files" />
        <div className="chat-main">
          <p className="chat-empty">Loading homework…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="lesson-layout">
      <LearningPathSidebar active="files" />

      <section className="chat-main">
        {started ? (
          <ChatWindow messages={messages} />
        ) : (
          <div className="homework-intake">
            <Link to="/files" className="back-link">
              <span className="material-symbols-outlined">arrow_back</span>
              All files
            </Link>
            <h1>Let&apos;s look at your homework</h1>
            <p className="muted">
              Upload a photo or file of the exercises. Your tutor will read them
              and help you work through it — one step at a time.
            </p>

            <FileDropzone
              onFiles={handleUpload}
              accept={formats.extensions}
              maxSizeMb={formats.max_upload_mb}
              disabled={busy}
              icon="assignment"
              title={busy ? "Reading your homework…" : "Upload your homework"}
              hint="Take a photo, or drag a PDF or Word file here"
            />

            {error && <p className="error">{error}</p>}

            {/* The file is readable but the tutor never opened the
                conversation (analysis failed, or the page was closed
                mid-flow) — offer a way forward that isn't re-uploading. */}
            {hasReadableHomework && (
              <div className="page-footer-actions">
                <button
                  type="button"
                  className="primary-button pressable-button"
                  onClick={runAnalysis}
                  disabled={busy}
                >
                  {busy ? "Reading…" : "Start working on it"}
                  {!busy && (
                    <span className="material-symbols-outlined">rocket_launch</span>
                  )}
                </button>
              </div>
            )}

            {materials.length > 0 && (
              <div className="material-grid">
                {materials.map((material) => (
                  <MaterialCard
                    key={material.id}
                    material={material}
                    onRetry={handleRetry}
                    busy={busy}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {started && (
          <>
            <div className="quick-actions">
              <button
                type="button"
                className="pill-button pressable-button"
                onClick={() => sendMessage("Can you give me a hint?")}
                disabled={busy}
              >
                Give me a hint
              </button>
              <button
                type="button"
                className="pill-button pressable-button"
                onClick={() =>
                  sendMessage("Can you explain how to do this step by step?")
                }
                disabled={busy}
              >
                Explain the method
              </button>
              <button
                type="button"
                className="pill-button pressable-button"
                onClick={() => sendMessage("I'm ready for the next exercise.")}
                disabled={busy}
              >
                {/* A skip, not an abandonment: the tutor brings every skipped
                    exercise back once the rest of the worksheet is done. */}
                Skip for now
              </button>
            </div>

            {error && <p className="error">{error}</p>}

            <AgentActivity activity={toolActivity} />

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
              placeholder="Type your answer or ask a question…"
            />
          </>
        )}
      </section>

      <aside className="lesson-progress-panel">
        <div className="teacher-avatar-section">
          <TeacherAvatar state={avatarState} audioElementRef={audioElRef} />
        </div>

        <h3 className="progress-panel-title">Homework Help</h3>

        <div className="context-card">
          <div className="context-row">
            <span className="material-symbols-outlined">assignment</span>
            <div>
              <div className="context-row-label">Session</div>
              <div className="context-row-value">
                {hasReadableHomework ? "Working through it" : "Waiting for upload"}
              </div>
            </div>
          </div>
          <div className="context-row">
            <span className="material-symbols-outlined">description</span>
            <div>
              <div className="context-row-label">Files</div>
              <div className="context-row-value">{materials.length}</div>
            </div>
          </div>
        </div>

        {started && (
          <div className="context-card">
            <FileDropzone
              onFiles={handleUpload}
              accept={formats.extensions}
              maxSizeMb={formats.max_upload_mb}
              disabled={busy}
              icon="add_photo_alternate"
              title="Add another page"
              hint="Upload the next exercise"
            />
          </div>
        )}

        <div className="mentor-tip-card">
          <h4>
            <span className="material-symbols-outlined">tips_and_updates</span>
            Mentor Tip
          </h4>
          <p>
            Try the step yourself first, even if you&apos;re not sure. Your tutor
            can give much better help once they see your thinking!
          </p>
        </div>
      </aside>
    </div>
  );
}
