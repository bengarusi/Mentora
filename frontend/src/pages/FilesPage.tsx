import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createHomeworkSession,
  deleteMaterial,
  getSupportedFormats,
  listHomeworkSessions,
  listStudyMaterials,
  reprocessMaterial,
  uploadStudyMaterial,
} from "../api/materials";
import { FileDropzone } from "../components/FileDropzone";
import { HomeworkSessionRow } from "../components/HomeworkSessionRow";
import { MaterialCard } from "../components/MaterialCard";
import { MATH_CURRICULUM } from "../data/mathCurriculum";
import type { Session, StudyMaterial, SupportedFormats } from "../types";

type Flow = "study" | "homework";

const FALLBACK_FORMATS: SupportedFormats = {
  extensions: [".pdf", ".docx", ".pptx", ".txt", ".md", ".png", ".jpg", ".jpeg"],
  max_upload_mb: 20,
};

export function FilesPage() {
  const navigate = useNavigate();
  const [flow, setFlow] = useState<Flow>("study");
  const [materials, setMaterials] = useState<StudyMaterial[]>([]);
  const [homeworkSessions, setHomeworkSessions] = useState<Session[]>([]);
  const [formats, setFormats] = useState<SupportedFormats>(FALLBACK_FORMATS);
  const [topic, setTopic] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const rows = await listStudyMaterials();
    setMaterials(rows);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [rows, supported, sessions] = await Promise.all([
          listStudyMaterials(),
          // A stale fallback list is better than an empty picker, so a failure
          // here isn't fatal.
          getSupportedFormats().catch(() => FALLBACK_FORMATS),
          listHomeworkSessions().catch(() => []),
        ]);
        if (cancelled) return;
        setMaterials(rows);
        setFormats(supported);
        setHomeworkSessions(sessions);
      } catch {
        if (!cancelled) setError("We couldn't load your files. Please refresh.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleUpload = useCallback(
    async (files: File[]) => {
      setBusy(true);
      setError(null);
      try {
        // Sequential so each file's status lands predictably and one failure
        // doesn't take the rest of the batch down with it.
        for (const file of files) {
          await uploadStudyMaterial(file, { subject: "math", topic: topic || undefined });
        }
        await refresh();
      } catch {
        setError("That upload didn't work. Please try again.");
      } finally {
        setBusy(false);
      }
    },
    [refresh, topic]
  );

  const handleDelete = useCallback(
    async (material: StudyMaterial) => {
      setBusy(true);
      try {
        await deleteMaterial(material.id);
        await refresh();
      } catch {
        setError("We couldn't remove that file.");
      } finally {
        setBusy(false);
      }
    },
    [refresh]
  );

  const handleRetry = useCallback(
    async (material: StudyMaterial) => {
      setBusy(true);
      try {
        await reprocessMaterial(material.id);
        await refresh();
      } catch {
        setError("We still couldn't read that file.");
      } finally {
        setBusy(false);
      }
    },
    [refresh]
  );

  const startHomework = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const session = await createHomeworkSession("math");
      navigate(`/homework/${session.id}`);
    } catch {
      setError("We couldn't start a homework session. Please try again.");
      setBusy(false);
    }
  }, [navigate]);

  const readyCount = useMemo(
    () => materials.filter((m) => m.status === "ready").length,
    [materials]
  );

  return (
    <div className="page-shell">
      <div className="page-header">
        <h1>My Files</h1>
        <p className="muted">
          Keep your class materials here, or get help with tonight&apos;s homework.
        </p>
      </div>

      <div className="flow-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={flow === "study"}
          className={`flow-tab${flow === "study" ? " active" : ""}`}
          onClick={() => setFlow("study")}
        >
          <span className="material-symbols-outlined">library_books</span>
          <span className="flow-tab-text">
            <strong>Study Materials</strong>
            <small>Save notes your tutor can use in lessons</small>
          </span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={flow === "homework"}
          className={`flow-tab${flow === "homework" ? " active" : ""}`}
          onClick={() => setFlow("homework")}
        >
          <span className="material-symbols-outlined">assignment</span>
          <span className="flow-tab-text">
            <strong>Homework Help</strong>
            <small>Upload an exercise and solve it together</small>
          </span>
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {flow === "study" ? (
        <section className="flow-panel">
          <div className="flow-intro">
            <h2>Your study materials</h2>
            <p className="muted">
              Upload worksheets, slides, or notes from class. When you start a
              lesson on a matching topic, your tutor will use the parts that
              actually help — not everything at once.
            </p>
          </div>

          <label className="field topic-field">
            <span>Tag these files with a topic (optional)</span>
            <select value={topic} onChange={(e) => setTopic(e.target.value)}>
              <option value="">No specific topic</option>
              {MATH_CURRICULUM.map((t) => (
                <option key={t.id} value={t.title}>
                  {t.title}
                </option>
              ))}
            </select>
          </label>

          <FileDropzone
            onFiles={handleUpload}
            accept={formats.extensions}
            maxSizeMb={formats.max_upload_mb}
            disabled={busy}
            multiple
            icon="library_books"
            title={busy ? "Uploading…" : "Add study materials"}
            hint="Drag files here, or click to choose"
          />

          <div className="materials-head">
            <h3>
              Saved files
              {materials.length > 0 && (
                <span className="muted"> · {readyCount} ready to use</span>
              )}
            </h3>
          </div>

          {loading ? (
            <p className="muted">Loading your files…</p>
          ) : materials.length === 0 ? (
            <div className="empty-state">
              <span className="material-symbols-outlined">folder_open</span>
              <p>No study materials yet. Upload your first one above!</p>
            </div>
          ) : (
            <div className="material-grid">
              {materials.map((material) => (
                <MaterialCard
                  key={material.id}
                  material={material}
                  onDelete={handleDelete}
                  onRetry={handleRetry}
                  busy={busy}
                />
              ))}
            </div>
          )}
        </section>
      ) : (
        <section className="flow-panel">
          <div className="flow-intro">
            <h2>Homework Help</h2>
            <p className="muted">
              Stuck on an exercise? Start a session, upload a photo or file of
              your homework, and your tutor will work through it with you —
              guiding you step by step instead of handing over the answers.
            </p>
          </div>

          <div className="homework-steps">
            <div className="homework-step">
              <span className="homework-step-num">1</span>
              <div>
                <strong>Upload your homework</strong>
                <p className="muted">A photo, PDF, or Word file all work.</p>
              </div>
            </div>
            <div className="homework-step">
              <span className="homework-step-num">2</span>
              <div>
                <strong>Your tutor reads it</strong>
                <p className="muted">They&apos;ll start with the first exercise.</p>
              </div>
            </div>
            <div className="homework-step">
              <span className="homework-step-num">3</span>
              <div>
                <strong>Solve it together</strong>
                <p className="muted">Hints and questions, not just answers.</p>
              </div>
            </div>
          </div>

          <div className="page-footer-actions">
            <button
              type="button"
              className="primary-button pressable-button"
              onClick={startHomework}
              disabled={busy}
            >
              {busy ? "Starting…" : "Start Homework Help"}
              {!busy && (
                <span className="material-symbols-outlined">rocket_launch</span>
              )}
            </button>
          </div>

          {homeworkSessions.length > 0 && (
            <>
              <div className="materials-head">
                <h3>Pick up where you left off</h3>
              </div>
              <div className="homework-session-list">
                {homeworkSessions.map((s) => (
                  <HomeworkSessionRow
                    key={s.id}
                    session={s}
                    onOpen={(id) => navigate(`/homework/${id}`)}
                  />
                ))}
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
