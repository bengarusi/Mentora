interface BoardButtonProps {
  /** Whether a board already exists for this question, which changes the action
   * from "draw me one" to "show me the one I have". */
  hasBoard: boolean;
  generating: boolean;
  disabled?: boolean;
  onClick: () => void;
}

/**
 * The only way a board is ever created. There is no automatic trigger anywhere
 * in the app — the tutor cannot decide to open the board.
 */
export function BoardButton({ hasBoard, generating, disabled, onClick }: BoardButtonProps) {
  return (
    <button
      type="button"
      className={`${hasBoard ? "secondary-button" : "pill-button"} pressable-button board-button`}
      onClick={onClick}
      disabled={disabled || generating}
    >
      <span className="material-symbols-outlined" aria-hidden="true">
        {hasBoard ? "visibility" : "draw"}
      </span>
      {generating ? "Drawing…" : hasBoard ? "Open board explanation" : "Explain on board"}
    </button>
  );
}
