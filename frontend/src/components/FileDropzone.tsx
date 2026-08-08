import { useCallback, useRef, useState } from "react";

interface FileDropzoneProps {
  onFiles: (files: File[]) => void;
  accept: string[];
  maxSizeMb: number;
  disabled?: boolean;
  multiple?: boolean;
  title: string;
  hint: string;
  icon?: string;
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

/**
 * Click-or-drag file picker.
 *
 * Validates extension and size in the browser so the obvious mistakes get an
 * instant, friendly message instead of a round-trip and an error toast — the
 * server re-checks both regardless.
 */
export function FileDropzone({
  onFiles,
  accept,
  maxSizeMb,
  disabled = false,
  multiple = false,
  title,
  hint,
  icon = "upload_file",
}: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;
      const files = Array.from(fileList);
      const maxBytes = maxSizeMb * 1024 * 1024;

      const rejected = files.find(
        (f) => !accept.includes(extensionOf(f.name)) || f.size > maxBytes
      );
      if (rejected) {
        setError(
          rejected.size > maxBytes
            ? `"${rejected.name}" is larger than ${maxSizeMb} MB.`
            : `"${rejected.name}" isn't a supported file type.`
        );
        return;
      }

      setError(null);
      onFiles(multiple ? files : files.slice(0, 1));
    },
    [accept, maxSizeMb, multiple, onFiles]
  );

  return (
    <div className="dropzone-wrap">
      <button
        type="button"
        className={`dropzone${dragging ? " dragging" : ""}`}
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled) handleFiles(e.dataTransfer.files);
        }}
      >
        <span className="material-symbols-outlined dropzone-icon">{icon}</span>
        <span className="dropzone-title">{title}</span>
        <span className="dropzone-hint">{hint}</span>
        <span className="dropzone-formats">
          {accept.join("  ·  ")} — up to {maxSizeMb} MB
        </span>
      </button>

      <input
        ref={inputRef}
        type="file"
        hidden
        multiple={multiple}
        accept={accept.join(",")}
        onChange={(e) => {
          handleFiles(e.target.files);
          // Reset so picking the same file twice in a row still fires onChange.
          e.target.value = "";
        }}
      />

      {error && <p className="error dropzone-error">{error}</p>}
    </div>
  );
}
