import { useEffect, useRef, useState } from "react";
import {
  getHomeworkProgress,
  listHomework,
  openMaterialFile,
  renameHomeworkSession,
} from "../api/materials";
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
  const [title, setTitle] = useState(session.subtopic || "My homework");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const startEditing = () => {
    setDraft(title);
    setEditing(true);
  };

  const commitRename = async () => {
    const next = draft.trim();
    setEditing(false);
    if (!next || next === title) return;
    setSaving(true);
    const previous = title;
    setTitle(next); // optimistic
    try {
      await renameHomeworkSession(session.id, next);
    } catch {
      setTitle(previous);
    } finally {
      setSaving(false);
    }
  };

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
    <div className="homework-session-row" data-session-id={session.id}>
      <button
        type="button"
        className="homework-session-main"
        onClick={() => (editing ? undefined : onOpen(session.id))}
      >
        <span className="material-symbols-outlined">assignment</span>
        <span className="homework-session-text">
          {editing ? (
            <input
              ref={inputRef}
              className="homework-session-rename-input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              onBlur={commitRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  commitRename();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  setEditing(false);
                }
              }}
            />
          ) : (
            <strong>{title}</strong>
          )}
          <small>{formatDate(session.created_at)}</small>
        </span>
      </button>

      {!editing && (
        <button
          type="button"
          className="homework-session-rename"
          onClick={(e) => {
            e.stopPropagation();
            startEditing();
          }}
          disabled={saving}
          aria-label="Rename session"
          title="Rename session"
        >
          <span className="material-symbols-outlined">edit</span>
        </button>
      )}

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
            data-material-id={file.id}
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
