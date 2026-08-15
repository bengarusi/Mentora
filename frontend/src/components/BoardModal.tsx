import { useEffect } from "react";
import { BoardBlock } from "./BoardBlock";
import { Modal } from "./Modal";
import { TeacherAvatar } from "./TeacherAvatar";
import { useBoardPlayer } from "../hooks/useBoardPlayer";
import type { BoardResponse } from "../types";

export type BoardPhase = "generating" | "ready" | "error";

interface BoardModalProps {
  open: boolean;
  phase: BoardPhase;
  board: BoardResponse | null;
  sessionId: number;
  /** Mirrors the chat's "Tutor voice" toggle: on means the tutor speaks the
   * board, off means the same sequence runs silently with captions. */
  voice: boolean;
  onClose: () => void;
  onRetry: () => void;
}

export function BoardModal({
  open,
  phase,
  board,
  sessionId,
  voice,
  onClose,
  onRetry,
}: BoardModalProps) {
  const ready = phase === "ready" && board !== null;
  const player = useBoardPlayer(sessionId, ready ? board : null, { voice });
  const { play, stop } = player;

  // Start writing as soon as the board is on screen, and stop the moment it
  // leaves — a modal that keeps talking after it is closed is the worst bug
  // this feature could have.
  useEffect(() => {
    if (open && ready) play();
    else stop();
  }, [open, ready, board?.id, play, stop]);

  const blocks = board?.spec.blocks ?? [];
  const finished = player.revealed >= blocks.length;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={ready ? board!.spec.title : "On the board"}
      titleId="board-modal-title"
      labelClose="Close board"
      footer={
        phase === "error" ? (
          <button type="button" className="primary-button pressable-button" onClick={onRetry}>
            Try again
          </button>
        ) : ready ? (
          <>
            {!finished && (
              <button
                type="button"
                className="ghost-button pressable-button"
                onClick={player.skipToEnd}
              >
                Show it all
              </button>
            )}
            <button
              type="button"
              className="secondary-button pressable-button"
              onClick={play}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                replay
              </span>
              Watch again
            </button>
          </>
        ) : undefined
      }
    >
      {phase === "generating" && (
        <div className="board-loading" aria-live="polite">
          <p className="board-loading-text">
            <span className="agent-spinner" aria-hidden="true" />
            Your tutor is heading to the board…
          </p>
        </div>
      )}

      {phase === "error" && (
        <p className="error">
          Your tutor couldn&apos;t get to the board just now. Nothing else has changed —
          you can keep going and try again whenever you like.
        </p>
      )}

      {ready && (
        <div className="board-stage">
          <div className="board-surface">
            <h3 className="board-heading">{board!.spec.title}</h3>
            {/* Only written blocks are in the document at all, so the board
                fills the way a real one does rather than fading things in. */}
            {blocks.slice(0, player.revealed).map((block) => (
              <BoardBlock key={block.id} block={block} active />
            ))}
            {finished && board!.spec.final_answer && (
              <p className="board-final">
                Answer: <strong>{board!.spec.final_answer}</strong>
              </p>
            )}
          </div>

          <div className="board-teacher">
            <TeacherAvatar
              state={player.avatarState}
              audioElementRef={player.audioElRef}
            />
          </div>

          {/* Always present, even silently: a child who cannot hear the tutor
              still needs to know what is being said about each step. */}
          <p className="board-captions" aria-live="polite">
            {player.caption ?? board!.spec.intro}
          </p>
        </div>
      )}
    </Modal>
  );
}
