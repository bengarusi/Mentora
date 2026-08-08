import type { MaterialStatus, StudyMaterial } from "../types";

/** Child-friendly wording for each extraction state, plus the icon and the
 * modifier class that colours the badge. */
const STATUS_META: Record<
  MaterialStatus,
  { label: string; icon: string; tone: string }
> = {
  pending: { label: "Waiting", icon: "schedule", tone: "pending" },
  processing: { label: "Reading…", icon: "hourglass_top", tone: "pending" },
  ready: { label: "Ready to use", icon: "check_circle", tone: "ready" },
  unsupported: { label: "Can't read yet", icon: "help", tone: "warn" },
  failed: { label: "Couldn't read", icon: "error", tone: "failed" },
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface MaterialCardProps {
  material: StudyMaterial;
  onDelete?: (material: StudyMaterial) => void;
  onRetry?: (material: StudyMaterial) => void;
  busy?: boolean;
}

export function MaterialCard({
  material,
  onDelete,
  onRetry,
  busy = false,
}: MaterialCardProps) {
  const status = STATUS_META[material.status] ?? STATUS_META.pending;
  // Retrying only makes sense once extraction has actually settled.
  const canRetry =
    onRetry && (material.status === "unsupported" || material.status === "failed");

  return (
    <article className="material-card">
      <div className="material-card-head">
        <span className="material-symbols-outlined material-card-icon">
          description
        </span>
        <div className="material-card-titles">
          <h3 className="material-card-title">
            {material.title || material.filename}
          </h3>
          <p className="material-card-meta">
            {formatSize(material.size_bytes)}
            {material.page_count ? ` · ${material.page_count} pages` : ""}
            {material.chunk_count > 0 ? ` · ${material.chunk_count} sections` : ""}
          </p>
        </div>
        <span className={`material-status ${status.tone}`}>
          <span className="material-symbols-outlined">{status.icon}</span>
          {status.label}
        </span>
      </div>

      {(material.topic || material.subject) && (
        <div className="material-tags">
          {material.subject && (
            <span className="material-tag">{material.subject}</span>
          )}
          {material.topic && (
            <span className="material-tag topic">{material.topic}</span>
          )}
        </div>
      )}

      {material.status_detail && (
        <p className="material-card-detail">{material.status_detail}</p>
      )}

      {(canRetry || onDelete) && (
        <div className="material-card-actions">
          {canRetry && (
            <button
              type="button"
              className="link-button"
              onClick={() => onRetry(material)}
              disabled={busy}
            >
              Try reading again
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              className="link-button danger"
              onClick={() => onDelete(material)}
              disabled={busy}
            >
              Remove
            </button>
          )}
        </div>
      )}
    </article>
  );
}
