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

/** Sentinel folder for materials with no topic tag — not a real curriculum id. */
const UNTAGGED_TOPIC = "__untagged__";

interface TopicFolder {
  key: string;
  title: string;
  icon: string;
  count: number;
}

export function FilesPage() {
  const navigate = useNavigate();
  const [flow, setFlow] = useState<Flow>("study");
  const [materials, setMaterials] = useState<StudyMaterial[]>([]);
  const [homeworkSessions, setHomeworkSessions] = useState<Session[]>([]);
  const [formats, setFormats] = useState<SupportedFormats>(FALLBACK_FORMATS);
  const [openTopic, setOpenTopic] = useState<string | null>(null);
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
      const topicTag =
        openTopic && openTopic !== UNTAGGED_TOPIC ? openTopic : undefined;
      setBusy(true);
      setError(null);
      try {
        // Sequential so each file's status lands predictably and one failure
        // doesn't take the rest of the batch down with it.
        for (const file of files) {
          await uploadStudyMaterial(file, { subject: "math", topic: topicTag });
        }
        await refresh();
      } catch {
        setError("That upload didn't work. Please try again.");
      } finally {
        setBusy(false);
      }
    },
    [refresh, openTopic]
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

  const folders = useMemo<TopicFolder[]>(() => {
    const knownTitles = new Set(MATH_CURRICULUM.map((t) => t.title));
    const countByTitle = new Map<string, number>();
    let untaggedCount = 0;
    for (const m of materials) {
      if (m.topic && knownTitles.has(m.topic)) {
        countByTitle.set(m.topic, (countByTitle.get(m.topic) ?? 0) + 1);
      } else {
        untaggedCount += 1;
      }
    }
    const curriculumFolders = MATH_CURRICULUM.map((t) => ({
      key: t.title,
      title: t.title,
      icon: t.icon,
      count: countByTitle.get(t.title) ?? 0,
    }));
    if (untaggedCount > 0) {
      curriculumFolders.push({
        key: UNTAGGED_TOPIC,
        title: "Untagged files",
        icon: "folder_off",
        count: untaggedCount,
      });
    }
    return curriculumFolders;
  }, [materials]);

  const openFolder = folders.find((f) => f.key === openTopic) ?? null;
  const visibleMaterials = useMemo(() => {
    if (!openTopic) return materials;
    if (openTopic === UNTAGGED_TOPIC) {
      const knownTitles = new Set(MATH_CURRICULUM.map((t) => t.title));
      return materials.filter((m) => !m.topic || !knownTitles.has(m.topic));
    }
    return materials.filter((m) => m.topic === openTopic);
  }, [materials, openTopic]);

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
          {openFolder ? (
            <>
              <button
                type="button"
                className="link-button folder-back"
                onClick={() => setOpenTopic(null)}
              >
                <span className="material-symbols-outlined">arrow_back</span>
                All topics
              </button>

              <div className="flow-intro">
                <h2>{openFolder.title}</h2>
                <p className="muted">
                  Upload worksheets, slides, or notes for this topic. Your
                  tutor will use them when you're learning it.
                </p>
              </div>

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
                  {openFolder.title}
                  {visibleMaterials.length > 0 && (
                    <span className="muted"> · {visibleMaterials.length} file{visibleMaterials.length === 1 ? "" : "s"}</span>
                  )}
                </h3>
              </div>

              {visibleMaterials.length === 0 ? (
                <div className="empty-state">
                  <span className="material-symbols-outlined">folder_open</span>
                  <p>No files in this topic yet. Upload your first one above!</p>
                </div>
              ) : (
                <div className="material-grid">
                  {visibleMaterials.map((material) => (
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
            </>
          ) : (
            <>
              <div className="flow-intro">
                <h2>Your study materials</h2>
                <p className="muted">
                  Upload worksheets, slides, or notes from class, organized by
                  topic. When you start a lesson on a matching topic, your
                  tutor will use the parts that actually help — not
                  everything at once.
                </p>
              </div>

              <div className="materials-head">
                <h3>
                  Topics
                  {materials.length > 0 && (
                    <span className="muted"> · {readyCount} file{readyCount === 1 ? "" : "s"} ready to use</span>
                  )}
                </h3>
              </div>

              {loading ? (
                <p className="muted">Loading your files…</p>
              ) : (
                <div className="material-folder-list">
                  {folders.map((folder) => (
                    <button
                      key={folder.key}
                      type="button"
                      className="material-folder-row"
                      onClick={() => setOpenTopic(folder.key)}
                    >
                      <span className="material-symbols-outlined material-folder-icon">
                        {folder.icon}
                      </span>
                      <span className="material-folder-title">{folder.title}</span>
                      <span className="material-folder-count">
                        {folder.count} file{folder.count === 1 ? "" : "s"}
                      </span>
                      <span className="material-symbols-outlined">chevron_right</span>
                    </button>
                  ))}
                </div>
              )}
            </>
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
