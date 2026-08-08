import { useEffect, useState } from "react";
import { getHomeworkProgress, listHomework, openMaterialFile } from "../api/materials";
import type { HomeworkProgress, Session, StudyMaterial } from "../types";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

interface HomeworkSessionRowProps {
  session: Session;
  onOpen: (sessionId: number) => void;
}

/**
 * One resumable Homework Help session: its progress ("3 / 5 solved") and a
 * link back to the file(s) that were uploaded into it. Progress and files are
 * fetched per-row (not bulk-loaded by the page) so one slow/failed session
 * never blocks the rest of the list from rendering.
 */
export function HomeworkSessionRow({ session, onOpen }: HomeworkSessionRowProps) {
  const [progress, setProgress] = useState<HomeworkProgress | null>(null);
  const [files, setFiles] = useState<StudyMaterial[]>([]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getHomeworkProgress(session.id).catch(() => null),
      listHomework(session.id).catch(() => []),
    ]).then(([p, f]) => {
      if (cancelled) return;
      setProgress(p);
      setFiles(f);
    });
    return () => {
      cancelled = true;
    };
  }, [session.id]);

  return (
    <div className="homework-session-row">
      <button
        type="button"
        className="homework-session-main"
        onClick={() => onOpen(session.id)}
      >
        <span className="material-symbols-outlined">assignment</span>
        <span className="homework-session-text">
          <strong>{session.subtopic || "My homework"}</strong>
          <small>{formatDate(session.created_at)}</small>
        </span>
      </button>

      <span className="homework-session-progress">
        {progress
          ? `${progress.solved_exercises} / ${progress.total_exercises} solved`
          : "…"}
      </span>

      <span className="homework-session-files">
        {files.map((file, index) => (
          <button
            key={file.id}
            type="button"
            className="homework-file-link"
            title={file.title || file.filename}
            onClick={(e) => {
              e.stopPropagation();
              openMaterialFile(file.id);
            }}
          >
            <span className="material-symbols-outlined">description</span>
            {files.length > 1 ? `File ${index + 1}` : "View homework"}
          </button>
        ))}
      </span>

      <button
        type="button"
        className="homework-session-open"
        onClick={() => onOpen(session.id)}
        aria-label="Open session"
      >
        <span className="material-symbols-outlined">chevron_right</span>
      </button>
    </div>
  );
}
