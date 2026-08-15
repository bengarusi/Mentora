import { useCallback, useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Rendered as the dialog heading and wired to aria-labelledby. */
  title: ReactNode;
  titleId: string;
  children: ReactNode;
  /** Optional actions rendered in the footer (retry, close, …). */
  footer?: ReactNode;
  labelClose?: string;
}

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * The app's first dialog. Deliberately generic — it knows nothing about boards —
 * because the codebase has no modal pattern and will want more than one.
 *
 * Handles the things a dialog has to get right and a div cannot: it renders in a
 * portal so it escapes any transformed/overflowed ancestor, traps Tab inside
 * itself, closes on Escape, restores focus to whatever opened it, and stops the
 * page behind it from scrolling.
 */
export function Modal({
  open,
  onClose,
  title,
  titleId,
  children,
  footer,
  labelClose = "Close",
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  // Whatever had focus when we opened, so it can be handed back on close.
  const restoreRef = useRef<HTMLElement | null>(null);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      // Wrap at both ends so focus can never escape into the page behind.
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();

    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = overflow;
      restoreRef.current?.focus();
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div
      className="modal-backdrop"
      // Only a click that starts and ends on the backdrop closes; dragging a
      // selection out of the panel should not dismiss the dialog.
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={handleKeyDown}
    >
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={panelRef}
      >
        <header className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <button
            type="button"
            className="ghost-button modal-close"
            onClick={onClose}
            aria-label={labelClose}
            ref={closeRef}
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </header>

        <div className="modal-body">{children}</div>

        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>,
    document.body
  );
}
